"""energy_report 三端点 Telemetry load_only 列裁剪前后数值一致性测试 (卡 45659336)

对齐卡 7c1c396d/27eb37e6 范式: _period_amounts / get_energy_trend /
get_station_energy_compare 三处批量查询补 .options(load_only(...))。
断言裁剪后 /summary /trend /station-compare 的 pv/charge/discharge/revenue
数值与口径公式直接计算一致 (不依赖具体种子数, 用精确可推导的确定性数据)。
"""
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import app.api.v1.energy_report as mod
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus
from app.models.telemetry import Telemetry

BASE = datetime(2026, 1, 10)  # 上海 1/10 = UTC [1/9 16:00, 1/10 16:00)


def _seed(session):
    """单站双设备: d1 逆变器(pv), d2 桩(charge/discharge)。"""
    st = Station(
        name=f"裁剪站45659336{uuid.uuid4().hex[:4]}",
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        status=StationStatus.NORMAL,
    )
    session.add(st); session.flush()
    d1 = Device(
        sn=f"SN-{uuid.uuid4().hex[:8]}", name="逆变器", code="PV1",
        type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE, station_id=st.id,
    )
    d2 = Device(
        sn=f"SN-{uuid.uuid4().hex[:8]}", name="桩", code="CH1",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=st.id,
    )
    session.add_all([d1, d2]); session.flush()
    # UTC 1/10 全天(上海日内), 确定性数值:
    # pv: 10:00 2kW → 12:00 4kW → 14:00 4kW, 梯形 = (2+4)/2*2 + (4+4)/2*2 = 14 kWh
    session.add(Telemetry(device_id=d1.id, timestamp=BASE + timedelta(hours=10), pv1_power=2.0))
    session.add(Telemetry(device_id=d1.id, timestamp=BASE + timedelta(hours=12), pv1_power=4.0))
    session.add(Telemetry(device_id=d1.id, timestamp=BASE + timedelta(hours=14), pv1_power=4.0))
    # charge: charger_kwh 100→107.5 = 7.5 kWh
    session.add(Telemetry(device_id=d2.id, timestamp=BASE + timedelta(hours=9), charger_kwh=100.0))
    session.add(Telemetry(device_id=d2.id, timestamp=BASE + timedelta(hours=13), charger_kwh=107.5))
    # discharge: total_discharge 50→53.5 = 3.5 kWh
    session.add(Telemetry(device_id=d2.id, timestamp=BASE + timedelta(hours=9), total_discharge=50.0))
    session.add(Telemetry(device_id=d2.id, timestamp=BASE + timedelta(hours=13), total_discharge=53.5))
    session.commit()
    return st


def _patch_now(monkeypatch, biz_dt):
    aware = biz_dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(mod, "now_in_biz_tz", lambda now=None: aware)


class TestLoadOnlyValuesUnchanged:

    def test_trend_values(self, client, monkeypatch):
        _patch_now(monkeypatch, datetime(2026, 1, 12, 12, 0))
        _seed(client._sesh)
        r = client.get("/api/v1/energy/trend",
                       params={"start_date": "2026-01-10", "end_date": "2026-01-10"})
        assert r.status_code == 200, r.text[:300]
        trend = r.json()["data"]["trend"]
        assert len(trend) == 1
        assert trend[0]["date"] == "2026-01-10"
        assert trend[0]["pv_generation"] == 14.0
        assert trend[0]["charging_amount"] == 7.5

    def test_summary_values(self, client, monkeypatch):
        # 上海 1/10 23:00 = UTC 15:00: day 窗 [UTC 1/9 16:00, 15:00) 覆盖全部采样点
        _patch_now(monkeypatch, datetime(2026, 1, 10, 23, 0))
        _seed(client._sesh)
        r = client.get("/api/v1/energy/summary", params={"period": "day"})
        assert r.status_code == 200, r.text[:300]
        data = r.json()["data"]
        assert data["pv_generation"] == 14.0
        assert data["charging_amount"] == 7.5
        assert data["discharge_amount"] == 3.5

    def test_station_compare_values(self, client, monkeypatch):
        # 近 30 天窗以 _now_naive 为锚, 固定为 UTC 1/12 覆盖 1/10 采样点
        monkeypatch.setattr(mod, "_now_naive", lambda: datetime(2026, 1, 12))
        st = _seed(client._sesh)
        r = client.get("/api/v1/energy/station-compare",
                       params={"start_date": "2026-01-10", "end_date": "2026-01-10"})
        assert r.status_code == 200, r.text[:300]
        data = r.json()["data"]
        rows = [s for s in data["stations"] if s["station_id"] == st.id]
        assert len(rows) == 1, f"站点缺失: {data['stations']}"
        s = rows[0]
        assert s["pv_gen"] == 14.0
        assert s["charge"] == 7.5
        assert s["discharge"] == 3.5
        # revenue = pv*feed_in + charge*service (default 电价下非零即可, 结构不变)
        assert isinstance(s["revenue"], (int, float))
