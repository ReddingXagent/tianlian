"""test_maintenance_schedule.py — 维护计划调度检查器单元测试

覆盖: MaintenanceScheduleChecker 初始化, check_maintenance_schedule (空/正常/异常),
_check_single_device (overdue/soon/warning/正常/自动计算next_maintenance/已有告警),
_load_maintenance_alarms, get_upcoming_maintenance, 全局实例。
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.services.maintenance_schedule import (
    MaintenanceScheduleChecker,
    maintenance_schedule_checker,
)


def make_device(
    dev_id=1, name="Dev1", station_id=1, sn="SN001",
    next_maintenance=None, last_maintenance=None,
    maintenance_interval_days=None, device_type=None,
):
    d = MagicMock()
    d.id = dev_id
    d.name = name
    d.station_id = station_id
    d.sn = sn
    d.type = device_type
    d.next_maintenance = next_maintenance
    d.last_maintenance = last_maintenance
    d.maintenance_interval_days = maintenance_interval_days
    return d


# ─── 初始化 ───

class TestInit:
    def test_default_thresholds(self):
        c = MaintenanceScheduleChecker()
        assert c.warning_days == 14
        assert c.soon_days == 7

    def test_singleton_exists(self):
        assert maintenance_schedule_checker is not None
        assert isinstance(maintenance_schedule_checker, MaintenanceScheduleChecker)


# ─── _check_single_device ───

class TestCheckSingleDevice:
    def setup_method(self):
        self.checker = MaintenanceScheduleChecker()
        self.today = date(2026, 8, 2)

    def test_no_maintenance_info_skipped(self):
        dev = make_device(next_maintenance=None, last_maintenance=None, maintenance_interval_days=None)
        db = MagicMock()
        result = self.checker._check_single_device(db, dev, self.today, {})
        assert result is None

    def test_auto_calc_next_maintenance(self):
        last = self.today - timedelta(days=25)
        dev = make_device(
            next_maintenance=None,
            last_maintenance=last,
            maintenance_interval_days=30,
        )
        db = MagicMock()
        result = self.checker._check_single_device(db, dev, self.today, {})
        # next_maintenance should be set to last + 30 days = 5 days from now → "soon"
        assert dev.next_maintenance == last + timedelta(days=30)
        assert result is not None
        assert result["status"] == "soon"
        assert result["days_until"] == 5

    def test_overdue(self):
        dev = make_device(next_maintenance=self.today - timedelta(days=3))
        db = MagicMock()
        result = self.checker._check_single_device(db, dev, self.today, {})
        assert result["status"] == "overdue"
        assert result["days_until"] == -3
        assert db.add.called  # alarm created

    def test_soon(self):
        dev = make_device(next_maintenance=self.today + timedelta(days=5))
        db = MagicMock()
        result = self.checker._check_single_device(db, dev, self.today, {})
        assert result["status"] == "soon"

    def test_warning(self):
        dev = make_device(next_maintenance=self.today + timedelta(days=12))
        db = MagicMock()
        result = self.checker._check_single_device(db, dev, self.today, {})
        assert result["status"] == "warning"

    def test_normal_not_flagged(self):
        dev = make_device(next_maintenance=self.today + timedelta(days=30))
        db = MagicMock()
        result = self.checker._check_single_device(db, dev, self.today, {})
        assert result is None

    def test_existing_alarm_in_map_skips_new(self):
        dev = make_device(next_maintenance=self.today - timedelta(days=5))
        db = MagicMock()
        existing_alarm = MagicMock()
        alarm_map = {(dev.id, "maintenance_overdue"): existing_alarm}
        result = self.checker._check_single_device(db, dev, self.today, alarm_map)
        assert result is not None
        assert result["existing_alarm"] is True
        assert not db.add.called  # no new alarm

    def test_boundary_soon_at_7_days(self):
        dev = make_device(next_maintenance=self.today + timedelta(days=7))
        db = MagicMock()
        result = self.checker._check_single_device(db, dev, self.today, {})
        assert result["status"] == "soon"

    def test_boundary_warning_at_14_days(self):
        dev = make_device(next_maintenance=self.today + timedelta(days=14))
        db = MagicMock()
        result = self.checker._check_single_device(db, dev, self.today, {})
        assert result["status"] == "warning"


# ─── _load_maintenance_alarms ───

class TestLoadMaintenanceAlarms:
    def test_returns_map(self):
        db = MagicMock()
        a1 = MagicMock(device_id=1, alarm_type="maintenance_overdue")
        a2 = MagicMock(device_id=2, alarm_type="maintenance_soon")
        db.query.return_value.filter.return_value.all.return_value = [a1, a2]
        result = MaintenanceScheduleChecker()._load_maintenance_alarms(db)
        assert (1, "maintenance_overdue") in result
        assert (2, "maintenance_soon") in result

    def test_empty(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        result = MaintenanceScheduleChecker()._load_maintenance_alarms(db)
        assert result == {}


# ─── check_maintenance_schedule ───

class TestCheckMaintenanceSchedule:
    def test_empty_devices(self):
        db = MagicMock()
        db.query.return_value.all.return_value = []
        checker = MaintenanceScheduleChecker()
        result = checker.check_maintenance_schedule(db=db)
        assert result == []

    def test_with_devices(self):
        today = date.today()
        dev = make_device(dev_id=1, next_maintenance=today - timedelta(days=1))
        db = MagicMock()
        # query(Device).all() → devices, query(Alarm)...all() → alarms
        db.query.return_value.all.return_value = [dev]
        db.query.return_value.filter.return_value.all.return_value = []  # no existing alarms
        db.query.return_value.filter.return_value.first.return_value = None
        checker = MaintenanceScheduleChecker()
        result = checker.check_maintenance_schedule(db=db)
        # Should find the overdue device
        assert len(result) >= 1
        assert result[0]["status"] == "overdue"


# ─── get_upcoming_maintenance ───

class TestGetUpcomingMaintenance:
    def test_empty(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        checker = MaintenanceScheduleChecker()
        result = checker.get_upcoming_maintenance(db=db, days_ahead=30)
        assert result == []

    def test_with_upcoming(self):
        today = date.today()
        dev = make_device(
            dev_id=1, next_maintenance=today + timedelta(days=10),
            last_maintenance=today - timedelta(days=20),
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [dev]
        checker = MaintenanceScheduleChecker()
        result = checker.get_upcoming_maintenance(db=db, days_ahead=30)
        assert len(result) == 1
        assert result[0]["device_id"] == 1
        assert result[0]["status"] == "warning"
