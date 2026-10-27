"""遥测采集 API 路由测试 (工作卡 a5154112)

覆盖 app/api/v1/telemetry/routes.py (801 行, 挂 /api/v1/telemetry 前缀) 7 个端点:
- POST /report                单条遥测上报 (按设备类型路由到 PV/Battery/Charger 专表)
- POST /batch-report          批量上报 (上限 MAX_BATCH_SIZE, 孤儿设备隔离)
- GET  /device/{id}/latest    设备最新遥测
- GET  /device/{id}/history   设备遥测历史 (时间范围 hours 过滤)
- GET  /device/{id}/stats     设备统计聚合 (avg/max/min)
- GET  /station/{id}/overview 场站多设备概览
- POST /device/{id}/simulate  模拟数据注入

鉴权: get_current_gateway_or_user 双路 —— X-API-Key (网关, caller=dict, team 豁免) 或
Bearer token (用户, caller=User, 触发 team scoping; admin 平台级豁免)。
查询: TDENGINE_ENABLED 默认 False → _get_telemetry_reader() 返回 None → 走 SQLAlchemy。
所有断言对齐被测代码的真实行为 (经探针验证), 不打真实网络。

⚠ 历史缺陷已修复 (卡 cfc527e6):
routes.py:150/155 原调 error_response(message=...) 漏传 code 位置参数
(error_response(code, message, data)) → 空数组 / 超 MAX_BATCH_SIZE 抛 TypeError → 500。
已补 code=400, 现两条路径返回业务错误响应 (HTTP 200, body code=400)。
"""
from datetime import datetime, timezone, timedelta

import bcrypt
import pytest

from app.models.api_gateway import ApiClient, GatewayApiKey
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus
from app.models.telemetry import Telemetry
from app.models.telemetry_v2 import (
    TelemetryBattery,
    TelemetryCharger,
    TelemetryPV,
)
from app.models.user import User, UserRole

URL = "/api/v1/telemetry"


# ─── fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def station(client):
    s = client._sesh
    st = Station(name="遥测站A", code="TLM-A", status=StationStatus.NORMAL)
    s.add(st)
    s.commit()
    s.refresh(st)
    return st


def _make_device(session, *, sn, name, code, dtype, station_id,
                 status=DeviceStatus.ONLINE):
    d = Device(sn=sn, name=name, code=code, type=dtype,
               status=status, station_id=station_id)
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


@pytest.fixture
def devices(client, station):
    """四类设备: PV / Charger / Battery / Meter(→legacy 旧表)。"""
    s = client._sesh
    return {
        "pv": _make_device(s, sn="TLM-PV", name="光伏#1", code="TLMPV",
                           dtype=DeviceType.PV_INVERTER, station_id=station.id),
        "charger": _make_device(s, sn="TLM-CHG", name="充电桩#1", code="TLMCHG",
                                dtype=DeviceType.CHARGER_DC, station_id=station.id),
        "battery": _make_device(s, sn="TLM-BAT", name="储能#1", code="TLMBAT",
                                dtype=DeviceType.BATTERY_INVERTER, station_id=station.id),
        "meter": _make_device(s, sn="TLM-METER", name="电表#1", code="TLMMET",
                              dtype=DeviceType.METER, station_id=station.id),
    }


@pytest.fixture
def gateway_key(client):
    """签发一张 active 网关 X-API-Key。"""
    s = client._sesh
    ac = ApiClient(client_id="tlm-cli", client_secret_hash="x", name="tlm")
    s.add(ac)
    s.commit()
    s.refresh(ac)
    gk = GatewayApiKey(key_id="tlm-k1", client_id=ac.id, name="k",
                       api_key="tlm-gw-key-secret")
    s.add(gk)
    s.commit()
    return "tlm-gw-key-secret"


def _gw_headers(key):
    return {"X-API-Key": key}


# ─── POST /report ───────────────────────────────────────────────────────────

class TestReport:
    """单条遥测上报: 设备类型→专表路由 + 鉴权 + payload 校验。"""

    def test_pv_routes_to_pv_table(self, client, devices):
        d = devices["pv"]
        r = client.post(f"{URL}/report", json={
            "device_id": d.id, "grid_power_total": 12.5,
            "pv_power_total": 9.0, "grid_voltage_a": 220.0,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 200
        data = body["data"]
        assert data["device_id"] == d.id
        assert data["table_type"] == "pv"
        assert data["region_id"] == "default"
        assert data["pod_id"] == "pod-01"
        # 实际落 PV 专表
        s = client._sesh
        row = s.query(TelemetryPV).filter(TelemetryPV.device_id == d.id).first()
        assert row is not None
        assert row.grid_power_total == 12.5

    def test_charger_routes_to_charger_table(self, client, devices):
        d = devices["charger"]
        r = client.post(f"{URL}/report", json={
            "device_id": d.id, "charger_power": 30.0,
            "charger_soc": 65.0, "gun_status": 1,
        })
        assert r.status_code == 200, r.text
        assert r.json()["data"]["table_type"] == "charger"
        row = (client._sesh.query(TelemetryCharger)
               .filter(TelemetryCharger.device_id == d.id).first())
        assert row is not None and row.charger_power == 30.0

    def test_battery_routes_to_battery_table(self, client, devices):
        d = devices["battery"]
        r = client.post(f"{URL}/report", json={
            "device_id": d.id, "battery_soc": 80.0,
            "battery_power": -5.0, "battery_voltage": 400.0,
        })
        assert r.status_code == 200, r.text
        assert r.json()["data"]["table_type"] == "battery"
        row = (client._sesh.query(TelemetryBattery)
               .filter(TelemetryBattery.device_id == d.id).first())
        assert row is not None and row.battery_soc == 80.0

    def test_meter_falls_back_to_legacy_table(self, client, devices):
        """meter/gateway 类型不映射专表 → 落旧 Telemetry 表 (无 station_id 列)。"""
        d = devices["meter"]
        r = client.post(f"{URL}/report", json={
            "device_id": d.id, "grid_power_total": 3.0,
        })
        assert r.status_code == 200, r.text
        assert r.json()["data"]["table_type"] == "legacy"
        row = (client._sesh.query(Telemetry)
               .filter(Telemetry.device_id == d.id).first())
        assert row is not None

    def test_invalid_payload_returns_422(self, client, devices):
        """device_id 非整数 → Pydantic 校验 422。"""
        r = client.post(f"{URL}/report", json={"device_id": "not-an-int"})
        assert r.status_code == 422

    def test_missing_device_returns_404(self, client):
        r = client.post(f"{URL}/report", json={"device_id": 999999})
        assert r.status_code == 404
        assert r.json()["detail"] == "设备不存在"

    def test_no_auth_returns_401(self, client, devices):
        d = devices["pv"]
        saved = client.headers.pop("Authorization", None)
        try:
            r = client.post(f"{URL}/report", json={"device_id": d.id})
            assert r.status_code == 401
            assert "认证" in r.json()["detail"]
        finally:
            if saved:
                client.headers["Authorization"] = saved

    def test_gateway_key_auth_accepted(self, client, devices, gateway_key):
        """X-API-Key 网关鉴权路径: caller 为 dict → 上报成功。"""
        d = devices["pv"]
        saved = client.headers.pop("Authorization", None)
        try:
            r = client.post(f"{URL}/report", json={"device_id": d.id, "grid_power_total": 1.0},
                            headers=_gw_headers(gateway_key))
            assert r.status_code == 200, r.text
            assert r.json()["data"]["table_type"] == "pv"
        finally:
            if saved:
                client.headers["Authorization"] = saved

    def test_invalid_gateway_key_rejected(self, client, devices):
        saved = client.headers.pop("Authorization", None)
        try:
            r = client.post(f"{URL}/report", json={"device_id": devices["pv"].id},
                            headers=_gw_headers("bogus-key"))
            assert r.status_code == 401
        finally:
            if saved:
                client.headers["Authorization"] = saved


# ─── POST /batch-report ─────────────────────────────────────────────────────

class TestBatchReport:
    def test_normal_batch_routes_by_type(self, client, devices):
        pv, chg = devices["pv"], devices["charger"]
        r = client.post(f"{URL}/batch-report", json={
            "records": [
                {"device_id": pv.id, "grid_power_total": 5.0},
                {"device_id": chg.id, "charger_power": 8.0},
            ]
        })
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total_received"] == 2
        assert data["total_success"] == 2
        assert data["stats"]["pv"] == 1
        assert data["stats"]["charger"] == 1
        assert data["stats"]["battery"] == 0
        assert data["stats"]["legacy"] == 0

    def test_empty_batch_returns_business_error(self, client):
        """空 records 提前返回业务错误响应: HTTP 200, body code=400 + 错误消息。
        (原 routes.py:150 error_response 漏传 code 致 TypeError, 卡 cfc527e6 已修。)"""
        r = client.post(f"{URL}/batch-report", json={"records": []})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 400
        assert body["message"] == "数据列表不能为空"

    def test_over_max_batch_size_returns_business_error(self, client, devices):
        """超 MAX_BATCH_SIZE(默认 500) 提前返回业务错误响应: HTTP 200, body code=400。
        发 501 条触发超限分支。(原 routes.py:155 同漏 code 致 TypeError, 已修。)"""
        d = devices["pv"]
        records = [{"device_id": d.id} for _ in range(501)]
        r = client.post(f"{URL}/batch-report", json={"records": records})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 400
        assert "批量数据上限" in body["message"]

    def test_at_max_batch_size_accepted(self, client, devices):
        """边界: 恰好 MAX_BATCH_SIZE 条放行 (不超过上限)。"""
        d = devices["pv"]
        records = [{"device_id": d.id, "grid_power_total": 1.0}
                   for _ in range(500)]
        r = client.post(f"{URL}/batch-report", json={"records": records})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["total_success"] == 500

    def test_nonexistent_device_collected_to_errors(self, client, devices):
        """设备不存在的记录不连坐, 计入 errors, 健康记录照常落库。"""
        pv = devices["pv"]
        r = client.post(f"{URL}/batch-report", json={
            "records": [
                {"device_id": pv.id, "grid_power_total": 2.0},
                {"device_id": 999999, "grid_power_total": 2.0},
            ]
        })
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total_success"] == 1
        assert any("999999" in e for e in data["stats"]["errors"])

    def test_orphan_device_isolated(self, client, devices):
        """孤儿设备(场站被硬删): 跳过并记 errors, 不连坐同批健康记录。"""
        s = client._sesh
        # 直接 DELETE 场站, 制造孤儿设备 (绕过 ORM 关系, 模拟硬删)
        pv = devices["pv"]
        meter = devices["meter"]
        from app.models.station import Station as StModel
        st = s.query(StModel).filter(StModel.id == pv.station_id).first()
        s.delete(st)
        s.commit()
        # 设备仍指向已删场站 → 孤儿
        r = client.post(f"{URL}/batch-report", json={
            "records": [
                {"device_id": pv.id, "grid_power_total": 2.0},
                {"device_id": meter.id, "grid_power_total": 2.0},
            ]
        })
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        # PV 走专表有 station_id FK 守卫 → 孤儿跳过; meter 走 legacy 无 station_id
        # 但 station_id 不在 valid_station_ids → 同样被孤儿检查跳过
        assert data["total_success"] == 0
        assert len(data["stats"]["errors"]) == 2


# ─── GET /device/{id}/latest ────────────────────────────────────────────────

class TestLatest:
    def test_latest_with_data(self, client, devices):
        s = client._sesh
        d = devices["pv"]
        now = datetime.now(timezone.utc)
        s.add(TelemetryPV(device_id=d.id, station_id=d.station_id,
                          timestamp=now, region_id="default", pod_id="pod-01",
                          grid_power_total=42.0, internal_temperature=50.0))
        s.commit()
        r = client.get(f"{URL}/device/{d.id}/latest")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["device_id"] == d.id
        assert data["table_type"] == "pv"
        assert data["grid_power_total"] == 42.0
        assert data["region_id"] == "default"

    def test_latest_no_data_returns_404(self, client, devices):
        r = client.get(f"{URL}/device/{devices['pv'].id}/latest")
        assert r.status_code == 404
        assert r.json()["detail"] == "无遥测数据"

    def test_latest_nonexistent_device_returns_404(self, client):
        r = client.get(f"{URL}/device/999999/latest")
        assert r.status_code == 404
        assert r.json()["detail"] == "设备不存在"

    def test_latest_region_filter(self, client, devices):
        """默认 region=default; 其他 region 的数据不被默认查询命中。"""
        s = client._sesh
        d = devices["pv"]
        now = datetime.now(timezone.utc)
        # 一条 default region (应被命中)
        s.add(TelemetryPV(device_id=d.id, station_id=d.station_id,
                          timestamp=now, region_id="default", pod_id="pod-01",
                          grid_power_total=10.0))
        # 一条 other region (默认查询不应命中)
        s.add(TelemetryPV(device_id=d.id, station_id=d.station_id,
                          timestamp=now + timedelta(seconds=1),
                          region_id="other", pod_id="pod-01",
                          grid_power_total=999.0))
        s.commit()
        r = client.get(f"{URL}/device/{d.id}/latest")
        assert r.status_code == 200
        # 命中 default region 的 10.0 而非 other region 更新的 999
        assert r.json()["data"]["grid_power_total"] == 10.0

    def test_latest_legacy_fallback(self, client, devices):
        """专表无数据时 fallback 到旧 Telemetry 表。"""
        s = client._sesh
        d = devices["pv"]
        now = datetime.now(timezone.utc)
        s.add(Telemetry(device_id=d.id, timestamp=now,
                        internal_temperature=37.0))
        s.commit()
        r = client.get(f"{URL}/device/{d.id}/latest")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["table_type"] == "legacy"


# ─── GET /device/{id}/history ───────────────────────────────────────────────

class TestHistory:
    def test_history_time_range_filter(self, client, devices):
        """hours 窗口过滤: 48h 前的记录不在 24h 窗口内, 最近 3 条在窗口内。
        数据点远离窗口边界, 避免运行时耗时导致的边界 flaky。"""
        s = client._sesh
        d = devices["pv"]
        now = datetime.now(timezone.utc)
        # 3 条最近记录 (10/20/30 分钟前), 均在任何 ≥1h 窗口内
        for i, v in enumerate([10, 20, 30]):
            s.add(TelemetryPV(
                device_id=d.id, station_id=d.station_id,
                timestamp=now - timedelta(minutes=v),
                region_id="default", pod_id="pod-01",
                grid_power_total=float(v),
            ))
        # 1 条 48 小时前的老记录, 应被 24h 窗口排除
        s.add(TelemetryPV(
            device_id=d.id, station_id=d.station_id,
            timestamp=now - timedelta(hours=48),
            region_id="default", pod_id="pod-01",
            grid_power_total=999.0,
        ))
        s.commit()

        r24 = client.get(f"{URL}/device/{d.id}/history?hours=24")
        assert r24.status_code == 200
        data24 = r24.json()["data"]
        assert data24["mode"] == "sqlalchemy"
        assert data24["count"] == 3  # 排除 48h 老记录

        r72 = client.get(f"{URL}/device/{d.id}/history?hours=72")
        assert r72.json()["data"]["count"] == 4  # 含 48h 老记录

    def test_history_no_data_returns_count_zero(self, client, devices):
        r = client.get(f"{URL}/device/{devices['pv'].id}/history?hours=24")
        assert r.status_code == 200
        assert r.json()["data"]["count"] == 0

    def test_history_nonexistent_device_returns_404(self, client):
        r = client.get(f"{URL}/device/999999/history")
        assert r.status_code == 404


# ─── GET /device/{id}/stats ─────────────────────────────────────────────────

class TestStats:
    def test_pv_stats_aggregation(self, client, devices):
        s = client._sesh
        d = devices["pv"]
        now = datetime.now(timezone.utc)
        for i, v in enumerate([10.0, 20.0, 30.0]):
            s.add(TelemetryPV(device_id=d.id, station_id=d.station_id,
                              timestamp=now - timedelta(minutes=i * 10),
                              region_id="default", pod_id="pod-01",
                              grid_power_total=v, pv_power_total=v,
                              grid_voltage_a=220.0 + i,
                              internal_temperature=40.0 + i))
        s.commit()
        r = client.get(f"{URL}/device/{d.id}/stats?hours=24")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["table_type"] == "pv"
        grid = data["stats"]["grid"]
        assert grid["max_power"] == 30.0
        assert grid["avg_power"] == pytest.approx(20.0)
        assert grid["max_voltage_a"] == 222.0
        assert data["stats"]["pv"]["max_power"] == 30.0
        assert data["stats"]["thermal"]["max_temp"] == 42.0

    def test_charger_stats_aggregation(self, client, devices):
        s = client._sesh
        d = devices["charger"]
        now = datetime.now(timezone.utc)
        # charger_kwh 为 modbus 累计计数器（odometer 口径，卡 6e80d5d6：SUM→MAX-MIN 净增量）
        # 三次快照 100.0/102.0/105.0 → 窗口内净增电量 = max-min = 5.0
        for i, kwh in enumerate([100.0, 102.0, 105.0]):
            s.add(TelemetryCharger(
                device_id=d.id, station_id=d.station_id,
                timestamp=now - timedelta(minutes=i * 10),
                region_id="default", pod_id="pod-01",
                charger_power=10.0 + i, charger_soc=50.0,
                charger_kwh=kwh, internal_temperature=45.0,
            ))
        s.commit()
        r = client.get(f"{URL}/device/{d.id}/stats?hours=24")
        assert r.status_code == 200
        charger = r.json()["data"]["stats"]["charger"]
        assert charger["max_power"] == 12.0
        assert charger["total_kwh"] == pytest.approx(5.0)  # 105.0-100.0 净增量，非求和

    def test_stats_empty_returns_zeros(self, client, devices):
        """无数据 → 聚合 None 经 `or 0` 归零, 不崩。"""
        r = client.get(f"{URL}/device/{devices['pv'].id}/stats?hours=24")
        assert r.status_code == 200
        grid = r.json()["data"]["stats"]["grid"]
        assert grid["avg_power"] == 0.0
        assert grid["max_power"] == 0.0

    def test_stats_nonexistent_device_returns_404(self, client):
        r = client.get(f"{URL}/device/999999/stats")
        assert r.status_code == 404


# ─── GET /station/{id}/overview ─────────────────────────────────────────────

class TestOverview:
    def test_overview_multi_devices(self, client, devices, station):
        s = client._sesh
        now = datetime.now(timezone.utc)
        # PV 设备有遥测
        s.add(TelemetryPV(device_id=devices["pv"].id, station_id=station.id,
                          timestamp=now, region_id="default", pod_id="pod-01",
                          grid_power_total=15.0, internal_temperature=41.0))
        # charger 设备有遥测
        s.add(TelemetryCharger(device_id=devices["charger"].id, station_id=station.id,
                               timestamp=now, region_id="default", pod_id="pod-01",
                               charger_power=22.0))
        s.commit()
        r = client.get(f"{URL}/station/{station.id}/overview")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["station_id"] == station.id
        assert data["device_count"] == 4  # pv/charger/battery/meter
        assert len(data["overview"]) == 4
        by_id = {o["device_id"]: o for o in data["overview"]}
        # PV: power 取 grid_power_total, temperature 取 internal_temperature
        pv_ov = by_id[devices["pv"].id]
        assert pv_ov["device_type"] == "pv_inverter"
        assert pv_ov["latest_telemetry"]["power"] == 15.0
        assert pv_ov["latest_telemetry"]["temperature"] == 41.0
        # Charger: power 取 charger_power
        assert by_id[devices["charger"].id]["latest_telemetry"]["power"] == 22.0
        # 无遥测设备: latest_telemetry 字段为 None
        no_data = by_id[devices["battery"].id]
        assert no_data["latest_telemetry"]["power"] is None

    def test_overview_empty_station(self, client):
        """空站: device_count=0, overview=[]。"""
        s = client._sesh
        empty = Station(name="空站", code="TLM-EMPTY", status=StationStatus.NORMAL)
        s.add(empty)
        s.commit()
        s.refresh(empty)
        r = client.get(f"{URL}/station/{empty.id}/overview")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["device_count"] == 0
        assert data["overview"] == []

    def test_overview_nonexistent_station_returns_404(self, client):
        """不存在的 station_id: assert_station_team_access 查无站点 → 404 (admin 亦然)。"""
        r = client.get(f"{URL}/station/999999/overview")
        assert r.status_code == 404
        assert r.json()["detail"] == "站点不存在"


# ─── POST /device/{id}/simulate ─────────────────────────────────────────────

class TestSimulate:
    def test_simulate_pv_creates_records(self, client, devices):
        d = devices["pv"]
        # hours=1, interval=1800 → 1*3600//1800 = 2 条
        r = client.post(f"{URL}/device/{d.id}/simulate?hours=1&interval_seconds=1800")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["table_type"] == "pv"
        assert data["records_created"] == 2
        assert data["device_id"] == d.id
        rows = (client._sesh.query(TelemetryPV)
                .filter(TelemetryPV.device_id == d.id).all())
        assert len(rows) == 2

    def test_simulate_count_formula(self, client, devices):
        """records_created = hours*3600//interval_seconds。"""
        d = devices["charger"]
        # 2*3600//3600 = 2
        r = client.post(f"{URL}/device/{d.id}/simulate?hours=2&interval_seconds=3600")
        assert r.status_code == 200
        assert r.json()["data"]["records_created"] == 2

    def test_simulate_nonexistent_device_returns_404(self, client):
        r = client.post(f"{URL}/device/999999/simulate")
        assert r.status_code == 404

    def test_simulate_no_auth_returns_401(self, client, devices):
        d = devices["pv"]
        saved = client.headers.pop("Authorization", None)
        try:
            r = client.post(f"{URL}/device/{d.id}/simulate")
            assert r.status_code == 401
        finally:
            if saved:
                client.headers["Authorization"] = saved


# ─── team access (跨团队隔离) ───────────────────────────────────────────────

def _add_team_user(session, *, username, team_id, role=UserRole.ENGINEER):
    u = User(
        username=username, real_name=username, role=role, team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(b"pw123456", bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login(client, username, password="pw123456"):
    r = client.post("/api/v1/auth/login",
                    data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


class TestTeamAccess:
    """用户态 (Bearer) 触发 team scoping; device.station→station.team_id 必须匹配
    user.team_id, 否则 404 (不泄露存在)。admin 平台级豁免。"""

    @pytest.fixture
    def team_setup(self, client):
        """两站两团队: station_a→team_a, station_b→team_b; 各挂一 PV 设备。
        user_a 属 team_a。"""
        s = client._sesh
        st_a = Station(name="团队A站", code="TEAM-A", status=StationStatus.NORMAL,
                       team_id=100)
        st_b = Station(name="团队B站", code="TEAM-B", status=StationStatus.NORMAL,
                       team_id=200)
        s.add_all([st_a, st_b])
        s.commit()
        s.refresh(st_a)
        s.refresh(st_b)
        dev_a = _make_device(s, sn="TEAM-PV-A", name="A光伏", code="TEAMA",
                             dtype=DeviceType.PV_INVERTER, station_id=st_a.id)
        dev_b = _make_device(s, sn="TEAM-PV-B", name="B光伏", code="TEAMB",
                             dtype=DeviceType.PV_INVERTER, station_id=st_b.id)
        user_a = _add_team_user(s, username="team_user_a", team_id=100)
        token_a = _login(client, "team_user_a")
        return {
            "st_a": st_a, "st_b": st_b,
            "dev_a": dev_a, "dev_b": dev_b,
            "user_a": user_a, "token_a": token_a,
        }

    def test_cross_team_device_access_denied(self, client, team_setup):
        """user_a (team 100) 访问 team_b 的设备 → 404。"""
        saved = client.headers.get("Authorization")
        try:
            client.headers["Authorization"] = f"Bearer {team_setup['token_a']}"
            r = client.get(f"{URL}/device/{team_setup['dev_b'].id}/latest")
            assert r.status_code == 404
            assert r.json()["detail"] == "设备不存在"
        finally:
            if saved:
                client.headers["Authorization"] = saved

    def test_same_team_device_access_allowed(self, client, team_setup):
        """user_a (team 100) 访问本团队设备 → 放行 (设备无遥测 → 404 '无遥测数据',
        但已通过 team 校验, 区别于跨团队的 '设备不存在')。"""
        saved = client.headers.get("Authorization")
        try:
            client.headers["Authorization"] = f"Bearer {team_setup['token_a']}"
            r = client.get(f"{URL}/device/{team_setup['dev_a'].id}/latest")
            # 通过 team 校验 → 走到 '无遥测数据' 404, 而非 '设备不存在'
            assert r.status_code == 404
            assert r.json()["detail"] == "无遥测数据"
        finally:
            if saved:
                client.headers["Authorization"] = saved

    def test_cross_team_station_overview_denied(self, client, team_setup):
        """user_a 访问 team_b 的场站概览 → 404。"""
        saved = client.headers.get("Authorization")
        try:
            client.headers["Authorization"] = f"Bearer {team_setup['token_a']}"
            r = client.get(f"{URL}/station/{team_setup['st_b'].id}/overview")
            assert r.status_code == 404
            assert r.json()["detail"] == "站点不存在"
        finally:
            if saved:
                client.headers["Authorization"] = saved

    def test_admin_exempt_from_team_scoping(self, client, team_setup):
        """admin (平台级) 豁免 team scoping: 访问任意团队设备不返回 404 team 拒绝。
        admin token 已由 client fixture 默认注入。"""
        r = client.get(f"{URL}/device/{team_setup['dev_b'].id}/latest")
        # 设备存在 + admin 豁免 → 走到 '无遥测数据' 而非 team 拒绝
        assert r.status_code == 404
        assert r.json()["detail"] == "无遥测数据"
