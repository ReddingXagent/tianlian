"""故障分析报表 API 测试 (app/api/v1/reports/faults.py, 卡 96f676b3)

覆盖端点 (前缀 /api/v1/reports):
- GET /faults  故障分析报表: 类型/级别分布, TOP10设备, MTBF/MTTR, 趋势 + 导出

覆盖维度:
(a) 正常路径: 分布/排行/MTBF/MTTR/趋势字段正确
(b) 过滤: 排除 INFO 级别; days 时间窗
(c) station_id 过滤 (admin 传任意站点, 空站点返回空)
(d) 导出: format=csv/xlsx/pdf 返回 StreamingResponse
(e) 参数校验: days < 1 / > 90 → 422
(f) 空数据: 无告警时 total_faults=0, 不报错
(g) 权限门: router-level get_current_user — 匿名 → 401

铁律: 仅加测试, 不改业务代码。
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus
from app.models.workorder import WorkOrder, WorkOrderStatus

REPORTS = "/api/v1/reports"


# ───────────────────────── seed helpers ─────────────────────────


def _station(session, name="故障站", team_id=None):
    s = Station(name=name, code=f"FLT{name}", status=StationStatus.NORMAL, team_id=team_id)
    session.add(s)
    session.flush()
    return s


def _device(session, station_id, name="设备A"):
    d = Device(
        sn=f"SN{name}", name=name, code=f"DEV{name}",
        type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
        station_id=station_id,
    )
    session.add(d)
    session.flush()
    return d


def _alarm(session, device_id, station_id, *, alarm_type="over_temp",
           level=AlarmLevel.WARNING, status=AlarmStatus.ACTIVE,
           created_at=None):
    a = Alarm(
        device_id=device_id, station_id=station_id, alarm_type=alarm_type,
        level=level, content="c", status=status,
        created_at=created_at or datetime.now(timezone.utc),
    )
    session.add(a)
    session.flush()
    return a


# ═══════════════════════════════════════════════════════════════
# 1. 正常路径: 分布 / 排行 / 趋势
# ═══════════════════════════════════════════════════════════════

class TestFaultsReport:
    def test_distribution_and_counts(self, client):
        s = client._sesh
        sta = _station(s)
        d1 = _device(s, sta.id, "D1")
        d2 = _device(s, sta.id, "D2")
        now = datetime.now(timezone.utc)
        _alarm(s, d1.id, sta.id, alarm_type="over_temp", level=AlarmLevel.WARNING, created_at=now)
        _alarm(s, d1.id, sta.id, alarm_type="over_temp", level=AlarmLevel.CRITICAL, created_at=now)
        _alarm(s, d2.id, sta.id, alarm_type="comm_fault", level=AlarmLevel.FATAL, created_at=now)
        s.commit()

        r = client.get(f"{REPORTS}/faults")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_faults"] == 3
        assert d["fault_type_distribution"]["over_temp"] == 2
        assert d["fault_type_distribution"]["comm_fault"] == 1
        assert d["fault_level_distribution"]["warning"] == 1
        assert d["fault_level_distribution"]["critical"] == 1
        assert d["fault_level_distribution"]["fatal"] == 1

    def test_top_devices_sorted_desc(self, client):
        """TOP10 按故障数降序, 首位是故障最多的设备。"""
        s = client._sesh
        sta = _station(s)
        d1 = _device(s, sta.id, "多故障")
        d2 = _device(s, sta.id, "少故障")
        now = datetime.now(timezone.utc)
        for _ in range(3):
            _alarm(s, d1.id, sta.id, created_at=now)
        _alarm(s, d2.id, sta.id, created_at=now)
        s.commit()

        r = client.get(f"{REPORTS}/faults")
        top = r.json()["data"]["top_fault_devices"]
        assert top[0]["device_name"] == "多故障"
        assert top[0]["fault_count"] == 3
        assert top[1]["fault_count"] == 1

    def test_excludes_info_level(self, client):
        """INFO 级别告警不计入故障。"""
        s = client._sesh
        sta = _station(s)
        d = _device(s, sta.id)
        now = datetime.now(timezone.utc)
        _alarm(s, d.id, sta.id, level=AlarmLevel.WARNING, created_at=now)
        _alarm(s, d.id, sta.id, level=AlarmLevel.INFO, created_at=now)  # 被排除
        s.commit()

        r = client.get(f"{REPORTS}/faults")
        assert r.json()["data"]["total_faults"] == 1

    def test_trend_by_day(self, client):
        s = client._sesh
        sta = _station(s)
        d = _device(s, sta.id)
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        _alarm(s, d.id, sta.id, created_at=now)
        _alarm(s, d.id, sta.id, created_at=yesterday)
        s.commit()

        r = client.get(f"{REPORTS}/faults")
        trend = r.json()["data"]["fault_trend"]
        assert len(trend) == 2  # 两天各一条
        assert all("date" in t and "count" in t for t in trend)


# ═══════════════════════════════════════════════════════════════
# 2. MTBF / MTTR (基于已完成工单)
# ═══════════════════════════════════════════════════════════════

class TestMtbfMttr:
    def test_mttr_computed_from_completed_workorders(self, client):
        s = client._sesh
        sta = _station(s)
        d = _device(s, sta.id)
        now = datetime.now(timezone.utc)
        # 一条告警
        _alarm(s, d.id, sta.id, created_at=now)
        # 一个已完成工单: accept→finish 间隔 2 小时
        accept = now - timedelta(hours=3)
        finish = now - timedelta(hours=1)
        wo = WorkOrder(
            id="WO-FAULTS-MTTR-001", station_id=sta.id, fault_desc="f",
            status=WorkOrderStatus.COMPLETED,
            create_time=now - timedelta(hours=4), accept_time=accept, finish_time=finish,
        )
        s.add(wo)
        s.commit()

        r = client.get(f"{REPORTS}/faults")
        d2 = r.json()["data"]
        assert d2["mttr_hours"] == 2.0  # (finish-accept) = 2h
        assert d2["mtbf_hours"] > 0


# ═══════════════════════════════════════════════════════════════
# 3. station_id 过滤 + 空数据
# ═══════════════════════════════════════════════════════════════

class TestStationFilterAndEmpty:
    def test_station_id_filter(self, client):
        """admin 传 station_id → 仅该站点告警。"""
        s = client._sesh
        sa = _station(s, "站A")
        sb = _station(s, "站B")
        da = _device(s, sa.id, "DA")
        db = _device(s, sb.id, "DB")
        now = datetime.now(timezone.utc)
        _alarm(s, da.id, sa.id, created_at=now)
        _alarm(s, db.id, sb.id, created_at=now)
        s.commit()

        r = client.get(f"{REPORTS}/faults", params={"station_id": sa.id})
        assert r.json()["data"]["total_faults"] == 1

    def test_empty_data(self, client):
        r = client.get(f"{REPORTS}/faults")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_faults"] == 0
        assert d["top_fault_devices"] == []
        assert d["fault_trend"] == []


# ═══════════════════════════════════════════════════════════════
# 4. 导出 (format)
# ═══════════════════════════════════════════════════════════════

class TestExport:
    @pytest.mark.parametrize("fmt,expected_mime", [
        ("csv", "text/csv"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("pdf", "application/pdf"),
    ])
    def test_export_formats(self, client, fmt, expected_mime):
        s = client._sesh
        sta = _station(s)
        d = _device(s, sta.id)
        _alarm(s, d.id, sta.id, created_at=datetime.now(timezone.utc))
        s.commit()

        r = client.get(f"{REPORTS}/faults", params={"format": fmt})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith(expected_mime)
        assert f"faults.{fmt}" in r.headers["content-disposition"]


# ═══════════════════════════════════════════════════════════════
# 5. 参数校验 + 权限门
# ═══════════════════════════════════════════════════════════════

class TestValidationAndPermission:
    def test_days_too_small_422(self, client):
        assert client.get(f"{REPORTS}/faults", params={"days": 0}).status_code == 422

    def test_days_too_large_422(self, client):
        assert client.get(f"{REPORTS}/faults", params={"days": 91}).status_code == 422

    def test_anonymous_401(self, anon_client):
        assert anon_client.get(f"{REPORTS}/faults").status_code == 401
