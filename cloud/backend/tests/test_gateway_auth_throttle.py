"""网关 X-API-Key 鉴权路径性能优化测试 (卡 round2b auth 段瓶颈)

生产实证 (timing 埋点): 同一 client IP 突发并发时 auth_ms 飙到 850-1842ms,
常态仅 5ms。优化: ① last_used_at 按 key_id 节流, 进程内 60s/key 最多写一次 DB,
消除并发行锁串行; ② key 查询结果 30s TTL 内存缓存, 免 auth 段 DB SELECT。

覆盖:
- 节流函数单测 (60s 窗口内第二次不写, 窗口外放行, key_id 互不影响)
- 缓存函数单测 (命中 / 未命中 / TTL 过期)
- 端到端: 同一 api_key 连续两次 batch-report, 通过 event listener 计数确认
  UPDATE gateway_api_keys 仅 1 次 (节流) + SELECT gateway_api_keys 仅 1 次 (缓存)
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import app
from app.core import auth_throttle as tel_mod

# 模块级 client (绑定全局 app), 由 conftest._auth_module_level_client 注入 admin
# token; 测网关 X-API-Key 分支前 pop Authorization, 强制走 gateway 分支。
client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """注入 test_db (覆盖 SessionLocal) + 每个测试前后清空进程内节流/缓存状态。"""
    tel_mod._reset_gateway_auth_caches()
    yield
    tel_mod._reset_gateway_auth_caches()


@pytest.fixture
def test_station(test_db):
    db = test_db["session"]
    from app.models.station import Station, StationStatus
    station = Station(
        name="网关鉴权站", code="GW-AUTH-STATION-001", status=StationStatus.NORMAL
    )
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@pytest.fixture
def test_device(test_db, test_station):
    db = test_db["session"]
    from app.models.device import Device, DeviceType, DeviceStatus
    device = Device(
        sn="GW-AUTH-DEV-001",
        name="网关鉴权设备",
        type=DeviceType.PV_INVERTER,
        status=DeviceStatus.ONLINE,
        station_id=test_station.id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@pytest.fixture
def gateway_key(test_db):
    """建 ApiClient (父行) + GatewayApiKey, 返回 active key ORM 对象。"""
    db = test_db["session"]
    from app.models.api_gateway import ApiClient, GatewayApiKey
    ac = ApiClient(client_id="gw_client_001", client_secret_hash="x", name="gw client")
    db.add(ac)
    db.commit()
    db.refresh(ac)
    k = GatewayApiKey(
        key_id="gw_key_001",
        client_id=ac.id,
        name="k",
        api_key="gw-test-key-001",
        status="active",
    )
    db.add(k)
    db.commit()
    db.refresh(k)
    # 脱离 session: test_station/test_device 复用同一 test_db session, 其 commit
    # 会 expire 本对象, 致 test body 读取 k.api_key 时触发延迟 SELECT (WHERE id=?,
    # 测试噪声, 干扰 gateway_api_keys 计数)。expunge 后属性已加载, 读取不再打 DB。
    db.expunge(k)
    return k


class TestGatewayLastUsedThrottle:
    """last_used_at 节流函数单测"""

    def test_first_write_allowed_second_blocked_within_window(self):
        # 首次写放行
        assert tel_mod._should_record_last_used(101) is True
        # 60s 窗口内第二次拒绝
        assert tel_mod._should_record_last_used(101) is False
        assert tel_mod._should_record_last_used(101) is False

    def test_distinct_key_ids_independent(self):
        assert tel_mod._should_record_last_used(101) is True
        # 不同 key_id 不受 101 的影响
        assert tel_mod._should_record_last_used(202) is True
        assert tel_mod._should_record_last_used(202) is False

    def test_allows_again_after_window_expires(self):
        assert tel_mod._should_record_last_used(303) is True
        assert tel_mod._should_record_last_used(303) is False
        # 把上次写入时刻拨到 61s 前, 模拟窗口过期
        tel_mod._last_used_recorded_at[303] -= 61
        assert tel_mod._should_record_last_used(303) is True


class TestGatewayCallerCache:
    """key 查询结果缓存单测"""

    def test_miss_then_hit(self):
        assert tel_mod._get_cached_gateway_caller("nope") is None
        caller = {"type": "gateway", "key_id": 1, "client_id": 1}
        tel_mod._set_cached_gateway_caller("k1", caller)
        assert tel_mod._get_cached_gateway_caller("k1") == caller

    def test_expires_after_ttl(self):
        caller = {"type": "gateway", "key_id": 2, "client_id": 2}
        tel_mod._set_cached_gateway_caller("k2", caller)
        # 把过期时间拨到过去, 模拟 TTL(30s) 过期
        ent = tel_mod._gateway_caller_cache["k2"]
        tel_mod._gateway_caller_cache["k2"] = (ent[0], ent[1] - 31)
        assert tel_mod._get_cached_gateway_caller("k2") is None


class TestBatchReportGatewayPerf:
    """端到端: 同一 api_key 连续请求, 节流 + 缓存吸收 DB 压力"""

    def test_second_request_skips_last_used_update_and_db_lookup(
        self, test_db, gateway_key, test_device
    ):
        engine = test_db["engine"]
        counts = {"update": 0, "select": 0}

        @event.listens_for(engine, "before_cursor_execute")
        def _counter(conn, cursor, statement, params, context, executemany):
            s = statement.upper()
            if "GATEWAY_API_KEYS" not in s:
                return
            if s.lstrip().startswith("UPDATE"):
                counts["update"] += 1
            elif "FROM GATEWAY_API_KEYS" in s:
                counts["select"] += 1

        try:
            for _ in range(2):
                client.headers.pop("Authorization", None)  # 走 X-API-Key 网关分支
                r = client.post(
                    "/api/v1/telemetry/batch-report",
                    headers={"X-API-Key": gateway_key.api_key},
                    json={
                        "records": [
                            {"device_id": test_device.id, "grid_voltage_a": 220.0}
                        ]
                    },
                )
                assert r.status_code == 200, r.text
        finally:
            event.remove(engine, "before_cursor_execute", _counter)

        # 第一次请求写 last_used_at (1), 第二次节流跳过 (0) → 合计 1
        assert counts["update"] == 1, counts
        # 第一次查 key (1), 第二次缓存命中免查 (0) → 合计 1
        assert counts["select"] == 1, counts

    def test_invalid_api_key_still_rejected(self, test_db, gateway_key):
        """契约回归: 缓存只缓存有效 key, 无效 key 仍 401。"""
        client.headers.pop("Authorization", None)
        r = client.post(
            "/api/v1/telemetry/batch-report",
            headers={"X-API-Key": "not-a-real-key"},
            json={"records": []},
        )
        assert r.status_code == 401


class TestExpiredKeyLifecycle:
    """卡片 ba9d3461: cache-miss 路径 expires_at 判定 — 过期 key 401 + 惰性落 expired。"""

    def test_expired_key_rejected_and_status_flipped(
        self, test_db, gateway_key, test_device
    ):
        from datetime import datetime as dt, timedelta, timezone

        db = test_db["session"]
        # 直接把 key 的过期时间拨到过去 (naive UTC, 对齐 DB 实际存储形态)
        db.query(type(gateway_key)).filter(
            type(gateway_key).id == gateway_key.id
        ).update({"expires_at": dt.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)})
        db.commit()

        client.headers.pop("Authorization", None)  # 走 X-API-Key 网关分支
        r = client.post(
            "/api/v1/telemetry/batch-report",
            headers={"X-API-Key": gateway_key.api_key},
            json={"records": [{"device_id": test_device.id, "grid_voltage_a": 220.0}]},
        )
        assert r.status_code == 401, r.text

        # 惰性 UPDATE: 行状态落 expired
        db.expire_all()
        row = db.query(type(gateway_key)).filter(
            type(gateway_key).id == gateway_key.id
        ).first()
        assert row.status == "expired", row.status

    def test_unexpired_key_with_expires_at_still_works(
        self, test_db, gateway_key, test_device
    ):
        from datetime import datetime as dt, timedelta, timezone

        db = test_db["session"]
        db.query(type(gateway_key)).filter(
            type(gateway_key).id == gateway_key.id
        ).update({"expires_at": dt.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)})
        db.commit()

        client.headers.pop("Authorization", None)
        r = client.post(
            "/api/v1/telemetry/batch-report",
            headers={"X-API-Key": gateway_key.api_key},
            json={"records": [{"device_id": test_device.id, "grid_voltage_a": 220.0}]},
        )
        assert r.status_code == 200, r.text
