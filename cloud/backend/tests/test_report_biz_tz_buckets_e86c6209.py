#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报表日趋势业务时区切桶测试 (卡 e86c6209)
alarms/faults/v2g 三处日桶曾按 UTC strftime 切日，上海 00:00-08:00 的记录
错落前一日桶。现经 _biz_day_key 按业务时区墙钟切日（对齐 energy_report 卡 20cb47ed）。
参考 test_reports_coverage.py 的模块级 client + autouse test_db 模式。
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.reports._shared import _biz_day_key
from app.tasks.tz_utils import get_biz_tz

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """覆盖 SessionLocal，使模块级 client 走测试库"""
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, f"login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _data(resp):
    return resp.json().get("data", resp.json())


def _seed_base(test_db):
    """team + station + device 基础数据，返回 session 与 device"""
    from app.models.user import Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    s = test_db["session"]
    team = Team(name="时区报表组", code="TZ001", description="业务时区切桶")
    s.add(team)
    s.flush()
    st = Station(name="时区测试站", code="TZSTA001", status=StationStatus.NORMAL, team_id=team.id)
    s.add(st)
    s.flush()
    dev = Device(sn="TZD001", name="时区设备#1", code="TZD001",
                 type=DeviceType.PCS, status=DeviceStatus.ONLINE,
                 station_id=st.id, health_score=90.0, rated_power=50.0)
    s.add(dev)
    s.flush()
    return s, dev


# ═══════════════════════════════════════════════
# 单元: _biz_day_key
# ═══════════════════════════════════════════════

def test_biz_day_key_unit():
    """None → unknown; UTC 正午(=上海20:00同日) → 同日; UTC 17:30 → 上海次日"""
    assert _biz_day_key(None) == "unknown"
    # UTC 2026-09-04 12:00 = 上海 2026-09-04 20:00 → 同日
    assert _biz_day_key(datetime(2026, 9, 4, 12, 0, 0)) == "2026-09-04"
    # UTC 2026-09-04 17:30 = 上海 2026-09-05 01:30 → 次日
    assert _biz_day_key(datetime(2026, 9, 4, 17, 30, 0)) == "2026-09-05"
    # aware 输入直接 astimezone，不重复挂 UTC
    aware = datetime(2026, 9, 4, 17, 30, 0, tzinfo=timezone.utc)
    assert _biz_day_key(aware) == "2026-09-05"
    aware_biz = datetime(2026, 9, 5, 1, 30, 0, tzinfo=get_biz_tz())
    assert _biz_day_key(aware_biz) == "2026-09-05"


# ═══════════════════════════════════════════════
# 端点: alarm_trend
# ═══════════════════════════════════════════════

def test_alarm_trend_biz_tz_bucket(test_db):
    """告警 created_at = UTC 2026-09-04 17:30 (上海 09-05 01:30) → 落 09-05 桶"""
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

    s, dev = _seed_base(test_db)
    s.add(Alarm(device_id=dev.id, station_id=dev.station_id, alarm_type="comm_fault",
                level=AlarmLevel.CRITICAL, content="跨午夜", status=AlarmStatus.ACTIVE,
                created_at=datetime(2026, 9, 4, 17, 30, 0)))
    s.commit()

    token = _login()
    resp = client.get("/api/v1/reports/alarms?days=90", headers=_hdr(token))
    assert resp.status_code == 200, resp.text
    trend = _data(resp)["daily_trend"]
    buckets = {t["date"]: t["count"] for t in trend}
    # 旧代码落 2026-09-04，业务时区应落 2026-09-05
    assert buckets.get("2026-09-05") == 1
    assert buckets.get("2026-09-04") is None


# ═══════════════════════════════════════════════
# 端点: fault_trend
# ═══════════════════════════════════════════════

def test_fault_trend_biz_tz_bucket(test_db):
    """故障告警跨 UTC 午夜样本 → fault_trend 落业务时区次日桶"""
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

    s, dev = _seed_base(test_db)
    s.add(Alarm(device_id=dev.id, station_id=dev.station_id, alarm_type="over_temp",
                level=AlarmLevel.WARNING, content="跨午夜故障", status=AlarmStatus.ACTIVE,
                created_at=datetime(2026, 9, 4, 17, 30, 0)))
    s.commit()

    token = _login()
    resp = client.get("/api/v1/reports/faults?days=90", headers=_hdr(token))
    assert resp.status_code == 200, resp.text
    data = _data(resp)
    trend = {t["date"]: t["count"] for t in data["fault_trend"]}
    assert trend.get("2026-09-05") == 1
    assert trend.get("2026-09-04") is None
    # by_type 同款切桶
    by_type = {e["type"]: {p["date"]: p["count"] for p in e["data"]}
               for e in data["fault_trend_by_type"]}
    assert by_type["over_temp"].get("2026-09-05") == 1


# ═══════════════════════════════════════════════
# 端点: v2g daily_trend
# ═══════════════════════════════════════════════

def test_v2g_daily_trend_biz_tz_bucket(test_db):
    """V2GDispatchLog start_at = UTC 2026-09-04 17:30 → daily_trend 落 09-05 桶"""
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.v2g_dispatch import V2GDispatchLog

    s, dev = _seed_base(test_db)
    s.add(Device(sn="TZV2G001", name="V2G桩#TZ", code="TZV2G001",
                 type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE,
                 station_id=dev.station_id, health_score=90.0, rated_power=50.0))
    s.flush()
    v2g_dev = s.query(Device).filter(Device.sn == "TZV2G001").first()
    s.add(V2GDispatchLog(device_id=v2g_dev.id, dispatch_type="charge",
                         target_power_kw=10.0, actual_power_kw=9.5,
                         actual_energy_kwh=20.0, status="completed",
                         start_at=datetime(2026, 9, 4, 17, 30, 0)))
    s.commit()

    token = _login()
    resp = client.get("/api/v1/reports/v2g?days=90", headers=_hdr(token))
    assert resp.status_code == 200, resp.text
    trend = _data(resp)["daily_trend"]
    buckets = {t["date"]: t["charge_kwh"] for t in trend}
    assert buckets.get("2026-09-05") == 20.0
    assert buckets.get("2026-09-04") is None
