#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app/ws/ 包覆盖率补测 — 任务卡 935c514b

目标: app/ws/ 包 TOTAL 56% → ≥70%, 源码零改动。
补测三个低覆盖文件:
  - app/ws/manager.py              (42%, 连接管理/心跳/广播/计数)
  - app/ws/digital_twin_handler.py (19%, 数字孪生数据查询)
  - app/ws/routes.py               (59%, 未测端点 + 广播函数 + 客户端消息处理)

策略:
  - manager.py / digital_twin_handler.py: 直接实例化单测, 不走网络
  - routes.py: httpx-ws ASGI transport 连真实端点校验握手, 广播函数直接 await
  - digital_twin_handler 模块级 `from app.core.database import SessionLocal` 在
    import 时绑定, test_db 对 db_module.SessionLocal 的属性覆盖不会传播到该绑定,
    故测试内 monkeypatch handler 模块的 SessionLocal 指向测试库 (仅测试侧改引用)

== 源码 bug 清单 (仅记录, 铁律不动手) ==
  app/ws/digital_twin_handler.py:
    BUG-1 L186  ThreeDModelType.GENERIC 不存在 (枚举无 GENERIC 成员)。该引用是
                device_type_mapping.get(key, ThreeDModelType.GENERIC) 的默认参数,
                被急切求值 → create_default_digital_twin_config 对任何设备都抛
                AttributeError, L188-262 类型分支全部不可达。
    BUG-2 L123  get_station_digital_twin_data 引用 station.latitude / station.longitude,
                但 Station 模型列名为 lat / lon → 任何存在站点都在 L123 崩。
    BUG-3 L77/L150  DataCollectorService 从未 import (NameError 被 except 吞),
                且 try 块内从不给 realtime_data 赋值 (L112/L155 靠 except / mock 兜底)。
  app/ws/routes.py:
    BUG-4 L472  /dashboard/large-screen 用 channel="large_screen", 不在
                WebSocketMessage.channel 白名单 → create_connected_message 抛
                ValidationError → 大屏端点从不发任何消息, L469-545 整段死代码。
  app/ws/manager.py:
    BUG-5 L185  _heartbeat_loop 用 channel="system" 构造心跳消息, 不在白名单 →
                WebSocketMessage 构造抛 ValidationError, 被 send 的 except 吞掉 →
                存活连接也被判 stale 清理 (心跳循环实际清空全部连接)。

这些 bug 的存在路径用 pytest.raises 锁定崩溃行为并覆盖崩溃前代码; 不可达分支不计入。
"""
import asyncio
import time
from datetime import datetime

import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.main import app
from app.ws import manager as ws_manager_mod
from app.ws.digital_twin_handler import DigitalTwinHandler
import app.ws.digital_twin_handler as dth_mod
from app.ws.manager import WebSocketManager
from app.ws.schemas import WebSocketMessage, create_data_message
from fastapi.testclient import TestClient

client = TestClient(app)


def _ws_token():
    """登录 admin 拿 JWT, 供 WS 端点 ?token= 鉴权 (P1 修复后 /ws/v1/* 强制鉴权)。"""
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


@pytest.fixture(autouse=True)
def _setup_ws_db(test_db):
    """每个测试独立 DB (seed admin + 覆盖 SessionLocal), 供 WS 鉴权查询用户。"""
    pass


# ----------------------------------------------------------------------
# 测试替身: 轻量 WebSocket, 满足 manager 调用的 accept/send_json/close
# ----------------------------------------------------------------------

class FakeWS:
    """记录发送消息的假 WebSocket, 可模拟 send/close 失败。"""

    def __init__(self, *, raise_on_send=False, raise_on_close=False):
        self.sent = []
        self.raise_on_send = raise_on_send
        self.raise_on_close = raise_on_close
        self.closed = None
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=""):
        if self.raise_on_close:
            raise RuntimeError("close failed")
        self.closed = (code, reason)

    async def send_json(self, data):
        if self.raise_on_send:
            raise RuntimeError("send failed")
        self.sent.append(data)


# ======================================================================
# manager.py — 连接管理 / 限流 / 心跳 / 广播 / 计数
# ======================================================================

class TestWebSocketManagerConnect:
    """connect / disconnect 路径与连接数限制。"""

    @pytest.mark.asyncio
    async def test_connect_rejected_by_total_limit(self, monkeypatch):
        """总连接数达上限 → 拒绝 (code 1013), 不 accept。"""
        monkeypatch.setattr(ws_manager_mod, "MAX_TOTAL_CONNECTIONS", 0)
        mgr = WebSocketManager()
        ws = FakeWS()
        result = await mgr.connect(ws, channel="realtime")
        assert result["rejected"] is True
        assert ws.accepted is False
        assert ws.closed is not None and ws.closed[0] == 1013
        assert ws not in mgr.all_connections

    @pytest.mark.asyncio
    async def test_connect_rejected_by_channel_limit(self, monkeypatch):
        """单频道连接数达上限 → 拒绝 (code 1013)。"""
        monkeypatch.setattr(ws_manager_mod, "MAX_TOTAL_CONNECTIONS", 100)
        monkeypatch.setattr(ws_manager_mod, "MAX_CHANNEL_CONNECTIONS", 0)
        mgr = WebSocketManager()
        ws = FakeWS()
        result = await mgr.connect(ws, channel="realtime")
        assert result["rejected"] is True
        assert ws.closed is not None and ws.closed[0] == 1013

    @pytest.mark.asyncio
    async def test_connect_with_station_id_creates_station_bucket(self):
        """带 station_id 连接 → 建站点连接桶 + 元数据 + 心跳时间戳。"""
        mgr = WebSocketManager()
        ws = FakeWS()
        result = await mgr.connect(ws, channel="digital_twin", station_id=42,
                                   metadata={"client": "web"})
        assert result == {"channel": "digital_twin", "station_id": 42}
        assert ws.accepted is True
        assert ws in mgr.all_connections
        assert ws in mgr.station_connections[42]
        assert mgr.connection_metadata[ws]["station_id"] == 42
        assert mgr.connection_metadata[ws]["metadata"] == {"client": "web"}
        assert ws in mgr._last_heartbeat

    @pytest.mark.asyncio
    async def test_disconnect_removes_station_and_device_subs(self):
        """disconnect 清理频道 / 站点桶 / 设备订阅 / 元数据。"""
        mgr = WebSocketManager()
        ws = FakeWS()
        await mgr.connect(ws, channel="digital_twin", station_id=7)
        mgr.subscribe_device(ws, 99)
        assert ws in mgr.station_connections[7]
        assert ws in mgr.device_subscriptions[99]

        mgr.disconnect(ws)
        assert ws not in mgr.all_connections
        assert 7 not in mgr.station_connections or ws not in mgr.station_connections[7]
        assert 99 not in mgr.device_subscriptions or ws not in mgr.device_subscriptions[99]
        assert ws not in mgr.connection_metadata
        assert ws not in mgr._last_heartbeat

    @pytest.mark.asyncio
    async def test_disconnect_unknown_ws_is_noop(self):
        """disconnect 一个未登记的 ws 不报错 (meta 走默认 channel)。"""
        mgr = WebSocketManager()
        ws = FakeWS()
        mgr.disconnect(ws)  # 无 metadata, 走 channel 默认值
        assert ws not in mgr.all_connections


class TestWebSocketManagerHeartbeat:
    """心跳: _is_ws_alive / record_heartbeat / 后台循环 / 启停。"""

    @pytest.mark.asyncio
    async def test_is_ws_alive_and_record_heartbeat(self):
        mgr = WebSocketManager()
        ws = FakeWS()
        # 未登记 → 不存活
        assert mgr._is_ws_alive(ws) is False
        await mgr.connect(ws, channel="realtime")
        # 刚连接 → 存活
        assert mgr._is_ws_alive(ws) is True
        # record_heartbeat 刷新时间戳与 last_activity_at
        before = mgr.connection_metadata[ws]["last_activity_at"]
        await asyncio.sleep(0.01)
        mgr.record_heartbeat(ws)
        assert mgr.connection_metadata[ws]["last_activity_at"] >= before

    @pytest.mark.asyncio
    async def test_is_ws_alive_stale(self, monkeypatch):
        """心跳超时 → 判定不存活。"""
        monkeypatch.setattr(ws_manager_mod, "WS_HEARTBEAT_TIMEOUT", 0.01)
        mgr = WebSocketManager()
        ws = FakeWS()
        await mgr.connect(ws, channel="realtime")
        # 人工把心跳拨到很久以前
        mgr._last_heartbeat[ws] = datetime.now().timestamp() - 1000
        assert mgr._is_ws_alive(ws) is False

    @pytest.mark.asyncio
    async def test_heartbeat_loop_cleans_stale_connections(self, monkeypatch):
        """心跳循环: 清理超时连接 (elapsed > TIMEOUT 路径)。

        原 BUG-5 (见文件头): _heartbeat_loop 用 channel="system" 构造心跳消息,
        不在 WebSocketMessage 白名单 → ValidationError → 存活连接也被误清。
        已随卡 faead57b 修复 (心跳消息改用合法 channel="realtime")。
        """
        monkeypatch.setattr(ws_manager_mod, "WS_HEARTBEAT_INTERVAL", 0)
        monkeypatch.setattr(ws_manager_mod, "WS_HEARTBEAT_TIMEOUT", 10.0)
        mgr = WebSocketManager()

        stale = FakeWS()  # 超时连接
        fresh = FakeWS()  # 存活连接
        await mgr.connect(stale, channel="realtime")
        await mgr.connect(fresh, channel="realtime")
        # stale 心跳拨旧 → 走 elapsed>TIMEOUT 分支
        mgr._last_heartbeat[stale] = datetime.now().timestamp() - 100

        await mgr.start_heartbeat()
        await asyncio.sleep(0.3)  # 让循环跑一轮
        await mgr.stop_heartbeat()

        # 超时连接被清理并以 1000 关闭
        assert stale not in mgr.all_connections
        assert stale.closed is not None and stale.closed[0] == 1000
        # fresh 收到心跳 ping, 不再被误清 (BUG-5 修复)
        assert fresh in mgr.all_connections
        assert any(m.get("type") == "heartbeat" for m in fresh.sent)

    @pytest.mark.asyncio
    async def test_start_stop_heartbeat_idempotent(self):
        """多次 start 不重复建任务, stop 幂等。"""
        mgr = WebSocketManager()
        await mgr.start_heartbeat()
        task1 = mgr._heartbeat_task
        await mgr.start_heartbeat()  # 任务未完成 → 跳过
        assert mgr._heartbeat_task is task1
        await mgr.stop_heartbeat()
        assert mgr._heartbeat_task.done()
        await mgr.stop_heartbeat()  # 再 stop 不报错


class TestWebSocketManagerBroadcast:
    """广播: personal / channel / station / device / all, 含异常吞掉路径。"""

    @pytest.mark.asyncio
    async def test_send_personal_message_and_error_path(self):
        mgr = WebSocketManager()
        ws = FakeWS()
        msg = create_data_message("realtime", {"x": 1})
        await mgr.send_personal_message(msg, ws)
        assert ws.sent and ws.sent[0]["type"] == "data"
        # send 失败被吞, 不抛
        broken = FakeWS(raise_on_send=True)
        await mgr.send_personal_message(msg, broken)

    @pytest.mark.asyncio
    async def test_broadcast_channel_and_error_path(self):
        mgr = WebSocketManager()
        good = FakeWS()
        broken = FakeWS(raise_on_send=True)
        await mgr.connect(good, channel="alerts")
        await mgr.connect(broken, channel="alerts")
        msg = create_data_message("alerts", {"a": 1})
        await mgr.broadcast_channel(msg, "alerts")
        assert any(m["payload"] == {"a": 1} for m in good.sent)  # good 收到
        # 未知频道 → 无操作不报错
        await mgr.broadcast_channel(msg, "no_such_channel")

    @pytest.mark.asyncio
    async def test_broadcast_station(self):
        mgr = WebSocketManager()
        ws = FakeWS()
        await mgr.connect(ws, channel="digital_twin", station_id=5)
        msg = create_data_message("digital_twin", {"s": 1})
        await mgr.broadcast_station(5, msg)
        assert ws.sent and ws.sent[0]["payload"] == {"s": 1}
        # 未知站点 → 无操作
        await mgr.broadcast_station(999, msg)

    @pytest.mark.asyncio
    async def test_broadcast_device_subscribers(self):
        mgr = WebSocketManager()
        ws = FakeWS()
        await mgr.connect(ws, channel="digital_twin")
        mgr.subscribe_device(ws, 11)
        msg = WebSocketMessage(type="update", channel="device", payload={"d": 1}, device_id=11)
        await mgr.broadcast_device_subscribers(11, msg)
        assert ws.sent and ws.sent[0]["payload"] == {"d": 1}
        # 无订阅者 → 无操作
        await mgr.broadcast_device_subscribers(999, msg)

    @pytest.mark.asyncio
    async def test_broadcast_all(self):
        mgr = WebSocketManager()
        ws = FakeWS()
        await mgr.connect(ws, channel="realtime")
        msg = create_data_message("realtime", {"all": True})
        await mgr.broadcast_all(msg)
        assert ws.sent and ws.sent[0]["payload"] == {"all": True}


class TestWebSocketManagerCounts:
    """计数与状态查询方法。"""

    @pytest.mark.asyncio
    async def test_counts_and_status(self):
        mgr = WebSocketManager()
        ws1 = FakeWS()
        ws2 = FakeWS()
        await mgr.connect(ws1, channel="digital_twin", station_id=3)
        await mgr.connect(ws2, channel="realtime")
        mgr.subscribe_device(ws1, 11)

        assert mgr.get_channel_count("realtime") == 1
        assert mgr.get_station_count(3) == 1
        assert mgr.get_device_subscriber_count(11) == 1
        assert mgr.get_total_count() == 2
        # 未知键返回 0
        assert mgr.get_channel_count("nope") == 0
        assert mgr.get_station_count(999) == 0
        assert mgr.get_device_subscriber_count(999) == 0

        status = mgr.get_status()
        assert status["total"] == 2
        assert "channels" in status and "stations" in status
        assert status["channels"]["realtime"] == 1
        assert status["max_channel"] == ws_manager_mod.MAX_CHANNEL_CONNECTIONS


class TestWebSocketManagerSubscriptions:
    """subscribe_device / unsubscribe_device。"""

    @pytest.mark.asyncio
    async def test_subscribe_and_unsubscribe(self):
        mgr = WebSocketManager()
        ws = FakeWS()
        await mgr.connect(ws, channel="digital_twin")
        mgr.subscribe_device(ws, 21)
        assert ws in mgr.device_subscriptions[21]
        mgr.unsubscribe_device(ws, 21)
        assert ws not in mgr.device_subscriptions[21]
        # 再取消 (已无) 与取消未订阅设备 → 不报错
        mgr.unsubscribe_device(ws, 21)
        mgr.unsubscribe_device(ws, 999)


# ======================================================================
# digital_twin_handler.py — 数据查询 (monkeypatch SessionLocal → 测试库)
# ======================================================================

def _patch_dth_session(test_db, monkeypatch):
    """把 handler 引用的 SessionLocal 指向测试库 (卡 60596021: handler 改为
    _db_module.SessionLocal 运行时读取, 这里同样 patch _db_module 上的属性)。"""
    monkeypatch.setattr(dth_mod._db_module, "SessionLocal", test_db["SessionLocal"])
    return test_db["session"]


def _seed_station(db, code="DTHSTA"):
    from app.models.station import Station, StationStatus
    st = Station(name=f"孪生站{code}", code=code, address="测试地址",
                 status=StationStatus.NORMAL)
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


def _seed_device(db, station_id, *, dtype, status, sn, code):
    from app.models.device import Device
    dev = Device(sn=sn, name=f"设备{code}", code=code, type=dtype,
                 status=status, station_id=station_id)
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


class TestDigitalTwinHandlerStation:
    """get_station_digital_twin_data。

    快乐路径被 BUG-1 (L186 GENERIC) 与 BUG-2 (L123 latitude) 阻断:
      - 站点不存在 → 正常返回 error (唯一可用路径);
      - 有 twin_config → 走完整构造后 L123 latitude 崩;
      - 无 twin_config → L70 调 create_default → L186 GENERIC 崩。
    后两者用 pytest.raises 锁定崩溃并覆盖崩溃前代码。
    """

    def test_station_nonexistent_returns_error(self, test_db, monkeypatch):
        _patch_dth_session(test_db, monkeypatch)
        result = DigitalTwinHandler().get_station_digital_twin_data(999977)
        assert "error" in result
        assert "999977" in result["error"]

    def test_station_with_config_full_payload(self, test_db, monkeypatch):
        """有 scene + twin_config → 走完整构造 (卡 e2ad0b7d 修复 BUG-2:
        latitude → lat/lon 列名, 不再 AttributeError)。

        覆盖 L29-122: 既有 scene 命中、既有 config 命中、设备段构造、mock 实时数据。
        """
        db = _patch_dth_session(test_db, monkeypatch)
        from app.models.digital_twin import DigitalTwinScene, DigitalTwinModel, ThreeDModelType
        from app.models.device import DeviceType, DeviceStatus
        st = _seed_station(db, code="DTHB")
        dev = _seed_device(db, st.id, dtype=DeviceType.CHARGER_DC,
                           status=DeviceStatus.CHARGING, sn="SN-DTH-CHG", code="DTHCHG")
        db.add(DigitalTwinScene(station_id=st.id, name="既有场景",
                                scene_config={"background": "#000"}))
        db.add(DigitalTwinModel(device_id=dev.id, model_type=ThreeDModelType.CHARGER_DC,
                                scale_x=2.0, scale_y=2.0, scale_z=2.0,
                                color_primary="#fff", color_secondary="#fff",
                                color_accent="#fff", animations={"x": 1},
                                status_mapping={"online": "#0f0"}))
        db.commit()
        result = DigitalTwinHandler().get_station_digital_twin_data(st.id)
        assert "station" in result
        assert "latitude" in result["station"] and "longitude" in result["station"]

    def test_station_without_config_creates_default(self, test_db, monkeypatch):
        """无 scene/config → 建默认 scene + 默认孪生配置 (卡 e2ad0b7d 修复 BUG-1:
        ThreeDModelType.GENERIC → GATEWAY 兜底, 不再 AttributeError)。

        覆盖 L29-70 + 默认 scene 创建 L35-56。
        """
        db = _patch_dth_session(test_db, monkeypatch)
        from app.models.device import DeviceType, DeviceStatus
        st = _seed_station(db, code="DTHA")
        _seed_device(db, st.id, dtype=DeviceType.PV_INVERTER,
                     status=DeviceStatus.ONLINE, sn="SN-DTH-INV", code="DTHINV")
        result = DigitalTwinHandler().get_station_digital_twin_data(st.id)
        assert "station" in result and result.get("devices") is not None


class TestDigitalTwinHandlerDevice:
    """get_device_realtime_update: 不存在 / 命中 (该路径无 latitude/GENERIC 阻断)。"""

    def test_device_nonexistent_returns_error(self, test_db, monkeypatch):
        _patch_dth_session(test_db, monkeypatch)
        result = DigitalTwinHandler().get_device_realtime_update(999977)
        assert "error" in result and "999977" in result["error"]

    def test_device_existing_returns_mock_realtime(self, test_db, monkeypatch):
        db = _patch_dth_session(test_db, monkeypatch)
        from app.models.device import DeviceType, DeviceStatus
        st = _seed_station(db, code="DTHC")
        dev = _seed_device(db, st.id, dtype=DeviceType.BATTERY,
                           status=DeviceStatus.ONLINE, sn="SN-DTH-BAT", code="DTHBAT")
        result = DigitalTwinHandler().get_device_realtime_update(dev.id)
        assert result["device_id"] == dev.id
        assert result["status"] == "online"
        assert "realtime_data" in result and "timestamp" in result
        # battery → 电池分支 mock (DataCollectorService 未导入 → 走 mock, BUG-3)
        assert "soc_percent" in result["realtime_data"]


class TestDigitalTwinHandlerDefaultConfig:
    """create_default_digital_twin_config。

    BUG-1: L186 ThreeDModelType.GENERIC 不存在 (是 .get 默认参数, 急切求值) →
    该方法对任何设备都抛 AttributeError, L188-262 类型分支不可达。
    此处锁定崩溃行为, 覆盖 L172-185 (映射字典构造)。
    """

    def test_create_default_returns_config(self, test_db, monkeypatch):
        """卡 e2ad0b7d 修复 BUG-1: 未知设备类型回退 GATEWAY, 不再抛 AttributeError。"""
        db = _patch_dth_session(test_db, monkeypatch)
        from app.models.digital_twin import ThreeDModelType
        from app.models.device import DeviceType, DeviceStatus
        st = _seed_station(db, code="DTHD")
        dev = _seed_device(db, st.id, dtype=DeviceType.PV_INVERTER,
                           status=DeviceStatus.ONLINE, sn="SN-CD-1", code="CD1")
        cfg = DigitalTwinHandler().create_default_digital_twin_config(db, dev)
        assert cfg.model_type == ThreeDModelType.SOLAR_INVERTER

        unknown = _seed_device(db, st.id, dtype=DeviceType.GATEWAY,
                               status=DeviceStatus.ONLINE, sn="SN-CD-2", code="CD2")
        cfg2 = DigitalTwinHandler().create_default_digital_twin_config(db, unknown)
        assert cfg2.model_type == ThreeDModelType.GATEWAY


class TestDigitalTwinHandlerMockRealtime:
    """generate_mock_realtime_data: 各设备类型分支 (该方法无阻断, 完整可测)。"""

    def test_all_type_branches(self):
        from app.models.device import Device, DeviceType, DeviceStatus
        h = DigitalTwinHandler()

        # 光伏分支 (inverter / pv_inverter)
        inv = Device(type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE)
        d = h.generate_mock_realtime_data(inv)
        assert "power_kw" in d and "efficiency" in d and d["status"] == "online"

        # 电池分支 (battery / battery_rack)
        bat = Device(type=DeviceType.BATTERY, status=DeviceStatus.ONLINE)
        d = h.generate_mock_realtime_data(bat)
        assert "soc_percent" in d and "cycle_count" in d

        # 充电桩分支: online → connected
        chg_on = Device(type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE)
        d = h.generate_mock_realtime_data(chg_on)
        assert "output_power_kw" in d and d["connector_status"] == "connected"

        # 充电桩分支: offline → disconnected
        chg_ac = Device(type=DeviceType.CHARGER_AC, status=DeviceStatus.OFFLINE)
        d = h.generate_mock_realtime_data(chg_ac)
        assert d["connector_status"] == "disconnected"

        # 通用分支 (pcs / gateway / meter 等)
        pcs = Device(type=DeviceType.PCS, status=DeviceStatus.FAULT)
        d = h.generate_mock_realtime_data(pcs)
        assert "operating_hours" in d and "uptime_percent" in d

    def test_status_fallback_when_none(self):
        from app.models.device import Device, DeviceType
        h = DigitalTwinHandler()
        # type/status 为 None → "generic" / "offline", 走通用分支
        dev = Device(type=DeviceType.PCS)
        dev.status = None
        d = h.generate_mock_realtime_data(dev)
        assert d["status"] == "offline"
        assert "operating_hours" in d  # 通用分支


# ======================================================================
# routes.py — 广播辅助函数 (直接 await)
# ======================================================================

class TestRoutesBroadcastHelpers:
    """供 service 层调用的广播函数: 无订阅者时为空操作, 但函数体被执行。"""

    @pytest.mark.asyncio
    async def test_all_broadcast_helpers_run_without_subscribers(self):
        from app.ws.routes import (
            broadcast_workorder_to_all,
        )
        # 无订阅者 → broadcast 遍历空集, 不抛
        await broadcast_workorder_to_all({"wo_id": 1})


# ======================================================================
# routes.py — 真实 WS 端点连接 (未测端点握手 + 客户端消息处理)
# 注: /dashboard/large-screen 因 BUG-4 (channel="large_screen" 不在白名单)
#     从不发消息, 整段死代码, 不测。
# ======================================================================

async def _connect_collect(url, want, per_msg_timeout=4.0):
    """连接端点, 收集至多 want 条消息; 容忍 httpx-ws ASGI teardown 时序 quirk。

    断言放在 teardown 之外 (参考现有 test_websocket_api 模式)。
    """
    transport = ASGIWebSocketTransport(app=app)
    msgs = []
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                for _ in range(want):
                    try:
                        m = await asyncio.wait_for(ws.receive_json(), timeout=per_msg_timeout)
                        msgs.append(m)
                    except asyncio.TimeoutError:
                        break
                await ws.close()
    except Exception:
        pass
    try:
        await transport.aclose()
    except Exception:
        pass
    return msgs


@pytest.mark.asyncio
async def test_ws_connect_digital_twin_station():
    """/ws/v1/digital-twin/station/{id}: connected 握手 + initial_data。"""
    msgs = await asyncio.wait_for(
        _connect_collect(f"ws://test/ws/v1/digital-twin/station/999977?token={_ws_token()}", 2),
        timeout=15.0,
    )
    assert msgs, "未收到任何消息"
    assert msgs[0]["type"] == "connected"
    assert msgs[0]["channel"] == "digital_twin"
    assert any(m["type"] == "initial_data" for m in msgs)


@pytest.mark.asyncio
async def test_ws_connect_digital_twin_device():
    """/ws/v1/digital-twin/device/{id}: connected 握手 + initial_data。"""
    msgs = await asyncio.wait_for(
        _connect_collect(f"ws://test/ws/v1/digital-twin/device/999977?token={_ws_token()}", 2),
        timeout=15.0,
    )
    assert msgs, "未收到任何消息"
    assert msgs[0]["type"] == "connected"
    assert msgs[0]["channel"] == "digital_twin"
    assert any(m["type"] == "initial_data" for m in msgs)


@pytest.mark.asyncio
async def test_ws_connect_digital_twin_device_registers_in_manager():
    """卡 6c62e375: device 端点须走 ws_manager 登记, 连接期间 digital_twin 频道计数可见。"""
    from app.ws.routes import ws_manager
    transport = ASGIWebSocketTransport(app=app)
    registered = False
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(
                f"ws://test/ws/v1/digital-twin/device/999977?token={_ws_token()}", client=ac
            ) as ws:
                m = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
                assert m["type"] == "connected"
                registered = ws_manager.get_channel_count("digital_twin") >= 1
                await ws.close()
    except Exception:
        pass
    try:
        await transport.aclose()
    except Exception:
        pass
    assert registered, "连接期间 digital_twin 频道计数为 0 —— 端点未走 ws_manager.connect 登记"


@pytest.mark.asyncio
async def test_ws_connect_digital_twin_global():
    """/ws/v1/digital-twin/global: connected 握手 (纯 receive 断连传感器)。"""
    msgs = await asyncio.wait_for(
        _connect_collect(f"ws://test/ws/v1/digital-twin/global?token={_ws_token()}", 1),
        timeout=15.0,
    )
    assert msgs, "未收到任何消息"
    assert msgs[0]["type"] == "connected"
    assert msgs[0]["channel"] == "digital_twin"


@pytest.mark.asyncio
async def test_ws_realtime_handles_ping_and_subscribe():
    """/realtime handle_client_messages: ping → heartbeat, subscribe → subscribed。"""
    transport = ASGIWebSocketTransport(app=app)
    heartbeat = None
    subscribed = None
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"ws://test/ws/v1/realtime?token={_ws_token()}", client=ac) as ws:
                hello = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                assert hello["type"] == "connected"
                await ws.send_json({"type": "ping"})
                await ws.send_json({"type": "subscribe", "channel": "alerts"})
                deadline = time.monotonic() + 6.0
                while time.monotonic() < deadline and (heartbeat is None or subscribed is None):
                    try:
                        m = await asyncio.wait_for(ws.receive_json(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    if (m.get("type") == "heartbeat"
                            and m.get("payload", {}).get("ping") == "pong"):
                        heartbeat = m
                    elif m.get("type") == "subscribed":
                        subscribed = m
                await ws.close()
    except Exception:
        pass
    try:
        await transport.aclose()
    except Exception:
        pass

    assert heartbeat is not None, "ping 未触发 heartbeat 响应"
    assert subscribed is not None, "subscribe 未触发 subscribed 响应"
    assert subscribed["channel"] == "alerts"


@pytest.mark.asyncio
async def test_ws_digital_twin_station_device_subscribe():
    """/digital-twin/station handle_client_messages: subscribe_device/unsubscribe_device/ping。"""
    transport = ASGIWebSocketTransport(app=app)
    sub_resp = None
    unsub_resp = None
    ping_resp = None
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"ws://test/ws/v1/digital-twin/station/999977?token={_ws_token()}", client=ac) as ws:
                # 消费 connected + initial_data
                for _ in range(2):
                    try:
                        await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                    except asyncio.TimeoutError:
                        break
                await ws.send_json({"type": "subscribe_device", "device_id": 123})
                await ws.send_json({"type": "unsubscribe_device", "device_id": 123})
                await ws.send_json({"type": "ping"})
                deadline = time.monotonic() + 6.0
                while time.monotonic() < deadline and (sub_resp is None or ping_resp is None):
                    try:
                        m = await asyncio.wait_for(ws.receive_json(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    if m.get("type") == "subscribed" and sub_resp is None:
                        sub_resp = m
                    elif m.get("type") == "unsubscribed" and unsub_resp is None:
                        unsub_resp = m
                    elif m.get("type") == "heartbeat" and ping_resp is None:
                        ping_resp = m
                await ws.close()
    except Exception:
        pass
    try:
        await transport.aclose()
    except Exception:
        pass

    assert sub_resp is not None, "subscribe_device 未响应"
    assert sub_resp["device_id"] == 123
    assert unsub_resp is not None, "unsubscribe_device 未响应"
    assert ping_resp is not None, "ping 未响应"


# ======================================================================
# manager.py — 并发安全 (任务卡 9a2ba0d0)
#   问题1: connect() check→accept→add 非原子, 并发可越过连接数限制
#   问题2: 三个 broadcast 边遍历边 await, 期间 disconnect 修改集合 → RuntimeError
# ======================================================================

class SlowAcceptWS(FakeWS):
    """accept 时主动多次让出控制权, 放大 check→accept→add 之间的并发窗口。"""

    async def accept(self):
        # 多次 sleep(0) 强制调度切换, 让其他并发 connect 也通过 limit 检查
        for _ in range(3):
            await asyncio.sleep(0)
        self.accepted = True


class SelfRemovingWS(FakeWS):
    """send_json 时把自己从 manager 断开 → 模拟广播中途连接失效。

    用于暴露"边遍历集合边在其 await 期间被 disconnect 修改"的竞态。
    """

    def __init__(self, mgr, **kwargs):
        super().__init__(**kwargs)
        self._mgr = mgr

    async def send_json(self, data):
        # 广播到达本连接时立即断开 (从正在遍历的 list/set 移除自身)
        self._mgr.disconnect(self)


class TestWebSocketManagerConcurrency:
    """并发安全: connect 限流竞态 + broadcast 遍历中集合变更。"""

    @pytest.mark.asyncio
    async def test_connect_concurrent_does_not_exceed_total_limit(self, monkeypatch):
        """并发 connect 不应越过总连接数上限。

        修复前: check(limit) → await accept → add 三步非原子, 多个协程
        在 await accept 让出期间都通过 check → 全部 accept/add → 超限。
        修复后: connect 用 asyncio.Lock 串行化 check-accept-add。
        """
        monkeypatch.setattr(ws_manager_mod, "MAX_TOTAL_CONNECTIONS", 1)
        monkeypatch.setattr(ws_manager_mod, "MAX_CHANNEL_CONNECTIONS", 100)
        mgr = WebSocketManager()
        clients = [SlowAcceptWS() for _ in range(4)]

        await asyncio.gather(*(mgr.connect(ws, channel="realtime") for ws in clients))

        accepted = [ws for ws in clients if ws.accepted]
        assert len(accepted) <= 1, f"总连接数超限: {len(accepted)} 个连接被接受"
        assert len(mgr.all_connections) <= 1

    @pytest.mark.asyncio
    async def test_broadcast_channel_survives_mid_iteration_disconnect(self):
        """遍历频道 list 时, send 期间 disconnect 移除元素 → 修复前 RuntimeError。

        list 在迭代中被 remove 会抛 "list changed size during iteration"。
        修复: 遍历前用 list(...) 快照 (参照 broadcast_all)。
        """
        mgr = WebSocketManager()
        conns = [SelfRemovingWS(mgr) for _ in range(3)]
        for ws in conns:
            await mgr.connect(ws, channel="alerts")

        msg = create_data_message("alerts", {"x": 1})
        # 不应抛 RuntimeError
        await mgr.broadcast_channel(msg, "alerts")
        # 三个连接都在广播到达时被自身断开
        assert len(mgr.all_connections) == 0

    @pytest.mark.asyncio
    async def test_broadcast_station_survives_mid_iteration_disconnect(self):
        """遍历站点 set 时, send 期间 disconnect 移除元素 → 修复前 RuntimeError。

        set 在迭代中被 discard 会抛 "Set changed size during iteration"。
        修复: 遍历前用 set(...) 快照。
        """
        mgr = WebSocketManager()
        conns = [SelfRemovingWS(mgr) for _ in range(3)]
        for ws in conns:
            await mgr.connect(ws, channel="digital_twin", station_id=5)

        msg = create_data_message("digital_twin", {"s": 1})
        # 不应抛 RuntimeError
        await mgr.broadcast_station(5, msg)
        assert len(mgr.all_connections) == 0
