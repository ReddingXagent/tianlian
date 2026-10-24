"""
充电交易缓存与回传测试 (卡 83f06883)

覆盖场景:
  ① mock 云端 200 -> 验证 POST payload 字段完整正确
  ② mock 云端 500/超时 -> 进重试队列不丢
  ③ Start -> Stop 全流程组装正确
  ④ start 缓存缺失场景不崩
  + handler 行为: 先回 Accepted 再异步回传 / start 时缓存
"""
import asyncio
import json
from typing import Any, Dict, List

import httpx
import pytest

from app.modules import transaction_store as ts_mod


# ========== 测试替身 ==========

class FakeCloudClient:
    """替身云端客户端: 记录调用, 按 mode 决定返回/抛异常。"""

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.calls: List[Dict[str, Any]] = []

    async def post(self, path: str, data: Dict[str, Any]):
        self.calls.append({"path": path, "data": data})
        if self.mode == "ok":
            return {"id": 1, "status": "created"}
        if self.mode == "http_error":
            raise httpx.HTTPError("simulated 5xx")
        if self.mode == "timeout":
            raise httpx.TimeoutException("simulated timeout")
        if self.mode == "return_none":
            return None
        return None


class FakeWebSocket:
    """替身 WebSocket: 记录 send 的 OCPP 帧。"""

    def __init__(self):
        self.sent: List[Any] = []

    async def send(self, data: str):
        self.sent.append(json.loads(data))


def make_store(tmp_path) -> "ts_mod.TransactionStore":
    """独立 db_path 的 TransactionStore 实例, 不污染全局 data/transactions.db。"""
    return ts_mod.TransactionStore(db_path=str(tmp_path / "tx.db"))


# ========== 单元测试: TransactionStore ==========

class TestTransactionStoreStartCache:
    """StartTransaction 缓存读写 + 持久化"""

    async def test_record_and_get_start(self, tmp_path):
        store = make_store(tmp_path)
        await store._init_db()
        try:
            await store.record_start(
                transaction_id="42",
                charge_point_id="CP-001",
                connector_id=1,
                id_tag="TAG1",
                meter_start=100,
                timestamp_start="2026-07-28T10:00:00",
            )
            cached = await store.get_start("42")
            assert cached is not None
            assert cached["charge_point_id"] == "CP-001"
            assert cached["connector_id"] == 1
            assert cached["id_tag"] == "TAG1"
            assert cached["meter_start"] == 100
            assert cached["timestamp_start"] == "2026-07-28T10:00:00"
        finally:
            await store.stop()

    async def test_get_start_miss(self, tmp_path):
        store = make_store(tmp_path)
        await store._init_db()
        try:
            assert await store.get_start("nope") is None
        finally:
            await store.stop()

    async def test_start_cache_survives_reload(self, tmp_path):
        """重启后内存缓存从 sqlite 恢复 (防重启丢失)。"""
        db_path = str(tmp_path / "tx.db")
        store1 = ts_mod.TransactionStore(db_path=db_path)
        await store1._init_db()
        await store1.record_start(
            transaction_id="77",
            charge_point_id="CP-002",
            connector_id=2,
            id_tag="VIN-XYZ",
            meter_start=500,
            timestamp_start="2026-07-28T09:00:00",
        )
        await store1.stop()

        # 模拟重启: 新实例同一 db_path
        store2 = ts_mod.TransactionStore(db_path=db_path)
        await store2._init_db()
        try:
            cached = await store2.get_start("77")
            assert cached is not None
            assert cached["id_tag"] == "VIN-XYZ"
            assert cached["meter_start"] == 500
        finally:
            await store2.stop()


class TestTransactionStoreBuildSession:
    """build_session 组装完整会话 (场景③/④)"""

    async def test_build_session_full_flow(self, tmp_path):
        """场景③: Start -> Stop 全流程组装正确, 字段完整。"""
        store = make_store(tmp_path)
        await store._init_db()
        try:
            await store.record_start(
                transaction_id="42",
                charge_point_id="CP-001",
                connector_id=1,
                id_tag="TAG1",
                meter_start=100,
                timestamp_start="2026-07-28T10:00:00",
            )
            stop_payload = {
                "transactionId": 42,
                "meterStop": 5000,
                "timestamp": "2026-07-28T11:00:00",
                "reason": "Local",
            }
            session = await store.build_session("CP-001", stop_payload)

            assert session["charge_point_id"] == "CP-001"
            assert session["connector_id"] == 1
            assert session["id_tag"] == "TAG1"
            assert session["transaction_id"] == "42"
            assert session["meter_start"] == 100
            assert session["meter_stop"] == 5000
            assert session["timestamp_start"] == "2026-07-28T10:00:00"
            assert session["timestamp_stop"] == "2026-07-28T11:00:00"
            assert session["reason"] == "Local"
            # station_id 可选字段存在
            assert "station_id" in session
        finally:
            await store.stop()

    async def test_build_session_missing_start(self, tmp_path, caplog):
        """场景④: start 缓存缺失不崩, meter_start/timestamp_start 为 null, 记 warning。"""
        store = make_store(tmp_path)
        await store._init_db()
        try:
            stop_payload = {
                "transactionId": 9999,
                "meterStop": 8000,
                "timestamp": "2026-07-28T12:00:00",
                "reason": "Emergency",
            }
            session = await store.build_session("CP-009", stop_payload)

            # 不丢交易: 关键字段齐全
            assert session["charge_point_id"] == "CP-009"
            assert session["transaction_id"] == "9999"
            assert session["meter_stop"] == 8000
            assert session["timestamp_stop"] == "2026-07-28T12:00:00"
            assert session["reason"] == "Emergency"
            # 缺省为 null
            assert session["meter_start"] is None
            assert session["timestamp_start"] is None

            # 记 warning
            assert any(
                "9999" in r.getMessage() and r.levelname == "WARNING"
                for r in caplog.records
            )
        finally:
            await store.stop()


class TestTransactionStoreSubmit:
    """submit_session 回传 + outbox 队列 (场景①/②)"""

    async def test_submit_success_posts_full_payload(self, tmp_path, monkeypatch):
        """场景①: mock 200 -> POST /charging-sessions, payload 字段完整正确。"""
        store = make_store(tmp_path)
        await store._init_db()
        fake = FakeCloudClient(mode="ok")
        monkeypatch.setattr(ts_mod, "cloud_client", fake)
        try:
            session = {
                "charge_point_id": "CP-001",
                "connector_id": 1,
                "id_tag": "TAG1",
                "transaction_id": "42",
                "meter_start": 100,
                "meter_stop": 5000,
                "timestamp_start": "2026-07-28T10:00:00",
                "timestamp_stop": "2026-07-28T11:00:00",
                "reason": "Local",
                "station_id": 1,
            }
            ok = await store.submit_session(session)
            assert ok is True
            assert len(fake.calls) == 1
            assert fake.calls[0]["path"] == "/charging-sessions"
            # payload 字段完整正确
            data = fake.calls[0]["data"]
            for key in (
                "charge_point_id", "connector_id", "id_tag", "transaction_id",
                "meter_start", "meter_stop", "timestamp_start", "timestamp_stop",
                "reason", "station_id",
            ):
                assert key in data, f"payload 缺字段 {key}"
            assert data["transaction_id"] == "42"
            assert data["meter_stop"] == 5000
            # 成功不入队
            assert await store.outbox_pending_count() == 0
        finally:
            await store.stop()

    async def test_submit_http_error_enqueues(self, tmp_path, monkeypatch):
        """场景②a: 云端 5xx (httpx.HTTPError) -> 进重试队列不丢。"""
        store = make_store(tmp_path)
        await store._init_db()
        fake = FakeCloudClient(mode="http_error")
        monkeypatch.setattr(ts_mod, "cloud_client", fake)
        try:
            session = {"transaction_id": "42", "charge_point_id": "CP-001"}
            ok = await store.submit_session(session)
            assert ok is False
            assert await store.outbox_pending_count() == 1
        finally:
            await store.stop()

    async def test_submit_timeout_enqueues(self, tmp_path, monkeypatch):
        """场景②b: 云端超时 -> 进重试队列不丢。"""
        store = make_store(tmp_path)
        await store._init_db()
        fake = FakeCloudClient(mode="timeout")
        monkeypatch.setattr(ts_mod, "cloud_client", fake)
        try:
            session = {"transaction_id": "43", "charge_point_id": "CP-001"}
            ok = await store.submit_session(session)
            assert ok is False
            assert await store.outbox_pending_count() == 1
        finally:
            await store.stop()

    async def test_submit_return_none_enqueues(self, tmp_path, monkeypatch):
        """场景②c: cloud_client 吞异常返回 None (真实失败路径) -> 进队。"""
        store = make_store(tmp_path)
        await store._init_db()
        fake = FakeCloudClient(mode="return_none")
        monkeypatch.setattr(ts_mod, "cloud_client", fake)
        try:
            session = {"transaction_id": "44", "charge_point_id": "CP-001"}
            ok = await store.submit_session(session)
            assert ok is False
            assert await store.outbox_pending_count() == 1
        finally:
            await store.stop()

    async def test_flush_outbox_retries_then_succeeds(self, tmp_path, monkeypatch):
        """outbox 重传: 失败入队 -> 云端恢复 -> flush 成功 -> 出队。"""
        store = make_store(tmp_path)
        await store._init_db()
        fake_fail = FakeCloudClient(mode="http_error")
        monkeypatch.setattr(ts_mod, "cloud_client", fake_fail)
        session = {"transaction_id": "42", "charge_point_id": "CP-001"}
        await store.submit_session(session)
        assert await store.outbox_pending_count() == 1

        # 云端恢复
        fake_ok = FakeCloudClient(mode="ok")
        monkeypatch.setattr(ts_mod, "cloud_client", fake_ok)
        try:
            flushed = await store.flush_outbox()
            assert flushed == 1
            assert len(fake_ok.calls) == 1
            assert fake_ok.calls[0]["data"]["transaction_id"] == "42"
            assert await store.outbox_pending_count() == 0
        finally:
            await store.stop()


# ========== 集成测试: OCPP handler ==========

class TestOCPPHandlerIntegration:
    """handler 行为: 先回 Accepted 再异步回传 / start 时缓存"""

    async def test_stop_handler_accepts_then_submits_async(self, tmp_path, monkeypatch):
        """StopTransaction: 先回 Accepted, 再异步回传 (Accepted 不被回传阻塞)。"""
        from app.modules import ocpp_server as ocpp_mod

        store = make_store(tmp_path)
        await store._init_db()
        await store.record_start(
            transaction_id="42",
            charge_point_id="CP-001",
            connector_id=1,
            id_tag="TAG1",
            meter_start=100,
            timestamp_start="2026-07-28T10:00:00",
        )
        fake = FakeCloudClient(mode="ok")
        monkeypatch.setattr(ts_mod, "cloud_client", fake)
        monkeypatch.setattr(ocpp_mod, "transaction_store", store)

        ws = FakeWebSocket()
        stop_payload = {
            "transactionId": 42,
            "meterStop": 5000,
            "timestamp": "2026-07-28T11:00:00",
            "reason": "Local",
        }
        try:
            await ocpp_mod.ocpp_server._handle_stop_transaction(
                ws, "msg-1", "CP-001", stop_payload
            )

            # ① 立即回 Accepted,且回传尚未发生 (异步, 未让出控制权)
            assert len(ws.sent) == 1
            frame = ws.sent[0]
            assert frame[0] == 3            # CALLRESULT
            assert frame[1] == "msg-1"
            assert frame[2]["idTagInfo"]["status"] == "Accepted"
            assert len(fake.calls) == 0     # Accepted 先于回传

            # ② 让出控制权, 异步回传跑完
            await asyncio.sleep(0.05)
            assert len(fake.calls) == 1
            assert fake.calls[0]["data"]["transaction_id"] == "42"
            assert fake.calls[0]["data"]["meter_stop"] == 5000
        finally:
            await store.stop()

    async def test_stop_handler_accepts_even_when_cloud_down(self, tmp_path, monkeypatch):
        """云端不可达: Accepted 照常回, 交易进 outbox 不丢。"""
        from app.modules import ocpp_server as ocpp_mod

        store = make_store(tmp_path)
        await store._init_db()
        await store.record_start(
            transaction_id="55",
            charge_point_id="CP-001",
            connector_id=1,
            id_tag="TAG1",
            meter_start=0,
            timestamp_start="2026-07-28T10:00:00",
        )
        monkeypatch.setattr(ts_mod, "cloud_client", FakeCloudClient(mode="timeout"))
        monkeypatch.setattr(ocpp_mod, "transaction_store", store)

        ws = FakeWebSocket()
        stop_payload = {
            "transactionId": 55,
            "meterStop": 3000,
            "timestamp": "2026-07-28T11:00:00",
            "reason": "Remote",
        }
        try:
            await ocpp_mod.ocpp_server._handle_stop_transaction(
                ws, "msg-9", "CP-001", stop_payload
            )
            # Accepted 照常
            assert ws.sent[0][2]["idTagInfo"]["status"] == "Accepted"
            await asyncio.sleep(0.05)
            # 进 outbox 不丢
            assert await store.outbox_pending_count() == 1
        finally:
            await store.stop()

    async def test_start_handler_caches_transaction(self, tmp_path, monkeypatch):
        """StartTransaction: 响应 transactionId, 并缓存供后续 Stop 组装。"""
        from app.modules import ocpp_server as ocpp_mod

        store = make_store(tmp_path)
        await store._init_db()
        monkeypatch.setattr(ocpp_mod, "transaction_store", store)

        ws = FakeWebSocket()
        start_payload = {"connectorId": 1, "idTag": "TAG1", "meterStart": 100}
        try:
            await ocpp_mod.ocpp_server._handle_start_transaction(
                ws, "msg-1", "CP-001", start_payload
            )
            # 响应含 transactionId
            assert ws.sent[0][2]["idTagInfo"]["status"] == "Accepted"
            tx_id = ws.sent[0][2]["transactionId"]
            assert tx_id is not None

            # 缓存命中
            cached = await store.get_start(str(tx_id))
            assert cached is not None
            assert cached["charge_point_id"] == "CP-001"
            assert cached["connector_id"] == 1
            assert cached["id_tag"] == "TAG1"
            assert cached["meter_start"] == 100
        finally:
            await store.stop()
