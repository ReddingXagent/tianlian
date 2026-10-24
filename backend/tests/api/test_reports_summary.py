"""汇总报表 API 测试 (app/api/v1/reports/summary.py, 卡 96f676b3)

覆盖端点 (前缀 /api/v1/reports):
- GET /summary  汇总报表: 全局指标 + 站点健康分布 + 团队绩效 + 导出

覆盖维度:
(a) 正常路径: overview (设备/工单/告警计数 + online_rate/completion_rate) 字段正确
(b) 站点健康分布: 设备全离线 → critical; 无设备 → offline; 正常 → normal
(c) 工单完成率: total_workorders / completed_workorders
(d) days 时间窗过滤
(e) 导出: format=csv/xlsx/pdf → StreamingResponse
(f) 参数校验: days 越界 → 422
(g) 空数据: 无任何资源时各计数为 0, 不报错
(h) 权限门: router-level get_current_user — 匿名 → 401

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


def _station(session, name="汇总站", team_id=None):
    s = Station(name=name, code=f"SUM{name}", status=StationStatus.NORMAL, team_id=team_id)
    session.add(s)
    session.flush()
    return s


def _device(session, station_id, name, status=DeviceStatus.ONLINE):
    d = Device(
        sn=f"SN{name}", name=name, code=f"DEV{name}",
        type=DeviceType.PV_INVERTER, status=status, station_id=station_id,
    )
    session.add(d)
    session.flush()
    return d


# ═══════════════════════════════════════════════════════════════
# 1. overview 计数
# ═══════════════════════════════════════════════════════════════

class TestOverview:
    def test_device_and_alarm_counts(self, client):
        s = client._sesh
        sta = _station(s)
        _device(s, sta.id, "ON1", DeviceStatus.ONLINE)
        _device(s, sta.id, "OFF1", DeviceStatus.OFFLINE)
        _device(s, sta.id, "FAULT1", DeviceStatus.FAULT)
        _device(s, sta.id, "MAIN1", DeviceStatus.MAINTENANCE)
        now = datetime.now(timezone.utc)
        s.add(Alarm(device_id=1, station_id=sta.id, level=AlarmLevel.WARNING,
                    status=AlarmStatus.ACTIVE, created_at=now))
        s.commit()

        r = client.get(f"{REPORTS}/summary")
        assert r.status_code == 200
        ov = r.json()["data"]["overview"]
        assert ov["total_devices"] == 4
        assert ov["online_devices"] == 1
        assert ov["offline_devices"] == 1
        assert ov["fault_devices"] == 1
        assert ov["maintenance_devices"] == 1
        assert ov["online_rate"] == 25.0  # 1/4
        assert ov["total_stations"] == 1
        assert ov["total_alarms"] == 1
        assert ov["active_alarms"] == 1

    def test_completion_rate(self, client):
        s = client._sesh
        sta = _station(s)
        now = datetime.now(timezone.utc)
        for i, st in enumerate([WorkOrderStatus.COMPLETED, WorkOrderStatus.PENDING, WorkOrderStatus.COMPLETED]):
            s.add(WorkOrder(
                id=f"WO-SUM-{i}", station_id=sta.id, fault_desc="f", status=st,
                create_time=now,
            ))
        s.commit()

        ov = client.get(f"{REPORTS}/summary").json()["data"]["overview"]
        assert ov["total_workorders"] == 3
        assert ov["completed_workorders"] == 2
        assert ov["completion_rate"] == 66.7  # 2/3 * 100 round 1


# ═══════════════════════════════════════════════════════════════
# 2. 站点健康分布
# ═══════════════════════════════════════════════════════════════

class TestStationHealth:
    def test_no_devices_station_is_offline(self, client):
        """站点无任何设备 → 计入 offline。"""
        s = client._sesh
        _station(s, "空站")
        s.commit()
        dist = client.get(f"{REPORTS}/summary").json()["data"]["station_health"]["distribution"]
        assert dist["offline"] == 1
        assert dist["normal"] == 0

    def test_normal_station(self, client):
        """设备在线且无活跃告警 → normal。"""
        s = client._sesh
        sta = _station(s)
        _device(s, sta.id, "OK1", DeviceStatus.ONLINE)
        s.commit()
        dist = client.get(f"{REPORTS}/summary").json()["data"]["station_health"]["distribution"]
        assert dist["normal"] == 1

    def test_mostly_offline_station_is_critical(self, client):
        """超半数设备离线 → critical。"""
        s = client._sesh
        sta = _station(s)
        _device(s, sta.id, "ON", DeviceStatus.ONLINE)
        _device(s, sta.id, "OFF1", DeviceStatus.OFFLINE)
        _device(s, sta.id, "OFF2", DeviceStatus.OFFLINE)
        s.commit()
        dist = client.get(f"{REPORTS}/summary").json()["data"]["station_health"]["distribution"]
        assert dist["critical"] == 1


# ═══════════════════════════════════════════════════════════════
# 3. days 时间窗 + 空数据
# ═══════════════════════════════════════════════════════════════

class TestDaysWindowAndEmpty:
    def test_empty_db(self, client):
        r = client.get(f"{REPORTS}/summary")
        assert r.status_code == 200
        ov = r.json()["data"]["overview"]
        assert ov["total_devices"] == 0
        assert ov["online_rate"] == 0
        assert ov["completion_rate"] == 0.0

    def test_days_filters_old_workorders(self, client):
        """days=7 窗口外的工单不计入 total_workorders。"""
        s = client._sesh
        sta = _station(s)
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=30)
        s.add(WorkOrder(id="WO-SUM-OLD", station_id=sta.id, fault_desc="f",
                        status=WorkOrderStatus.PENDING, create_time=old))
        s.add(WorkOrder(id="WO-SUM-NEW", station_id=sta.id, fault_desc="f",
                        status=WorkOrderStatus.PENDING, create_time=now))
        s.commit()

        ov = client.get(f"{REPORTS}/summary", params={"days": 7}).json()["data"]["overview"]
        assert ov["total_workorders"] == 1  # 仅近 7 天


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
        r = client.get(f"{REPORTS}/summary", params={"format": fmt})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith(expected_mime)
        assert f"summary.{fmt}" in r.headers["content-disposition"]


# ═══════════════════════════════════════════════════════════════
# 5. 参数校验 + 权限门
# ═══════════════════════════════════════════════════════════════

class TestValidationAndPermission:
    def test_days_too_small_422(self, client):
        assert client.get(f"{REPORTS}/summary", params={"days": 0}).status_code == 422

    def test_days_too_large_422(self, client):
        assert client.get(f"{REPORTS}/summary", params={"days": 91}).status_code == 422

    def test_anonymous_401(self, anon_client):
        assert anon_client.get(f"{REPORTS}/summary").status_code == 401
