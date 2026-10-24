# -*- coding: utf-8 -*-
"""
维护计划调度检查测试 - 覆盖率补强 ≥70%

被测: app/services/maintenance_schedule.py (MaintenanceScheduleChecker + 全局单例)
设计: 主流程走真测试库 (patched_db fixture), 异常路径用 MagicMock 隔离 DB,
      私有 _check_single_device 的 alarm_map=None 兼容回退分支直调覆盖。

模块级 SessionLocal 绑定坑 (与 test_maintenance_tasks 同源):
  maintenance_schedule line 11 `from app.core.database import SessionLocal` 按值
  绑定到导入时对象, 绕过 conftest 对 db_module.SessionLocal 的覆盖 → 显式
  monkeypatch 模块属性 (patched_db fixture 内完成)。

覆盖:
- check_maintenance_schedule   overdue/soon/warning 三态 + 状态计数日志
                              无维护计划跳过 / 自动计算 next_maintenance
                              已有告警去重 (ACTIVE/ACKNOWLEDGED 命中, RESOLVED 不算)
                              正常设备不提醒 / DB 错误 rollback+raise / 单设备异常 continue
                              should_close_db: 不传 db(commit+close) vs 传 db(不碰 SessionLocal)
- _load_maintenance_alarms    只索引 ACTIVE/ACKNOWLEDGED, RESOLVED 被过滤
- _check_single_device        alarm_map=None 旧调用回退查 DB (创建 / 命中 existing)
- get_upcoming_maintenance    状态分类 (overdue/soon/warning/upcoming) + asc 排序
                              过滤 None 与超期 future / should_close_db 两路径
- smoke                       全局单例 + 阈值配置
"""
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.services import maintenance_schedule as maint_mod
from app.services.maintenance_schedule import (
    MaintenanceScheduleChecker,
    maintenance_schedule_checker,
)
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus


# ═══════════════════════════════════════════════════════════════
# Fixture / 辅助
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def patched_db(test_db, monkeypatch):
    """注入测试库到 maintenance_schedule 模块 (绕过 from-import 按值绑定坑)。"""
    monkeypatch.setattr(maint_mod, "SessionLocal", test_db["SessionLocal"])
    return test_db


def _dev(db, did, name=None, station_id=1, status=DeviceStatus.ONLINE,
         dtype=DeviceType.CHARGER_DC,
         next_maint=None, last_maint=None, interval=None):
    """构造并 add 一个 Device。interval 默认 None 以精确控制"无计划"分支。"""
    d = Device(
        id=did, sn=f"SN-MS-{did}", name=name or f"设备{did}", code=f"MS{did}",
        type=dtype, status=status, station_id=station_id,
        next_maintenance=next_maint, last_maintenance=last_maint,
        maintenance_interval_days=interval,
    )
    db.add(d)
    return d


def _fresh(test_db):
    """新开 session 读 checker 提交的写入 (避开测试 session 快照)。"""
    return test_db["SessionLocal"]()


TODAY = date.today


# ═══════════════════════════════════════════════════════════════
# smoke: 单例与阈值
# ═══════════════════════════════════════════════════════════════

class TestSingleton:

    def test_global_singleton_exists(self):
        assert isinstance(maintenance_schedule_checker, MaintenanceScheduleChecker)

    def test_threshold_config(self):
        checker = MaintenanceScheduleChecker()
        assert checker.warning_days == 14
        assert checker.soon_days == 7


# ═══════════════════════════════════════════════════════════════
# check_maintenance_schedule - 三态 + 计数
# ═══════════════════════════════════════════════════════════════

class TestCheckScheduleStatus:

    def test_overdue_creates_alarm(self, patched_db):
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8101, next_maint=today - timedelta(days=3))
        db.commit()

        checker = MaintenanceScheduleChecker()
        # 不传 db → should_close_db=True, 方法内部 commit, _fresh 可读到 alarm
        results = checker.check_maintenance_schedule()

        assert len(results) == 1
        r = results[0]
        assert r["device_id"] == 8101
        assert r["status"] == "overdue"
        assert r["days_until"] == -3
        assert r["alarm_level"] == AlarmLevel.WARNING.value

        s = _fresh(patched_db)
        try:
            alarm = s.query(Alarm).filter_by(device_id=8101).one()
            assert alarm.alarm_type == "maintenance_overdue"
            assert alarm.level == AlarmLevel.WARNING
            assert alarm.status == AlarmStatus.ACTIVE
        finally:
            s.close()

    def test_soon_creates_alarm(self, patched_db):
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8102, next_maint=today + timedelta(days=5))   # 5 <= soon_days(7)
        db.commit()

        checker = MaintenanceScheduleChecker()
        results = checker.check_maintenance_schedule(db=db)

        assert len(results) == 1
        assert results[0]["status"] == "soon"
        assert results[0]["days_until"] == 5
        assert results[0]["alarm_level"] == AlarmLevel.WARNING.value

    def test_soon_boundary_equal_seven_days(self, patched_db):
        # days_until == soon_days(7) → soon (<=)
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8103, next_maint=today + timedelta(days=7))
        db.commit()

        results = MaintenanceScheduleChecker().check_maintenance_schedule(db=db)
        assert results[0]["status"] == "soon"

    def test_warning_creates_alarm(self, patched_db):
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8104, next_maint=today + timedelta(days=10))  # soon<10<=warning
        db.commit()

        results = MaintenanceScheduleChecker().check_maintenance_schedule(db=db)

        assert len(results) == 1
        assert results[0]["status"] == "warning"
        assert results[0]["alarm_level"] == AlarmLevel.INFO.value

    def test_warning_boundary_equal_fourteen_days(self, patched_db):
        # days_until == warning_days(14) → warning (<=)
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8105, next_maint=today + timedelta(days=14))
        db.commit()

        results = MaintenanceScheduleChecker().check_maintenance_schedule(db=db)
        assert results[0]["status"] == "warning"

    def test_mixed_status_counts(self, patched_db):
        # 三态混合 → 返回 3 条, 覆盖状态计数日志 (overdue/soon/warning 求和)
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8201, next_maint=today - timedelta(days=1))   # overdue
        _dev(db, 8202, next_maint=today + timedelta(days=3))   # soon
        _dev(db, 8203, next_maint=today + timedelta(days=10))  # warning
        db.commit()

        results = MaintenanceScheduleChecker().check_maintenance_schedule(db=db)
        statuses = sorted(r["status"] for r in results)
        assert statuses == ["overdue", "soon", "warning"]


# ═══════════════════════════════════════════════════════════════
# check_maintenance_schedule - 跳过 / 自动计算 / 正常
# ═══════════════════════════════════════════════════════════════

class TestCheckScheduleSkip:

    def test_no_maintenance_plan_skipped(self, patched_db):
        # next=None 且无 (last + interval) → return None, 不创建告警
        db = patched_db["session"]
        _dev(db, 8301, next_maint=None, last_maint=None, interval=None)
        db.commit()

        results = MaintenanceScheduleChecker().check_maintenance_schedule(db=db)
        assert results == []

        s = _fresh(patched_db)
        try:
            assert s.query(Alarm).filter_by(device_id=8301).count() == 0
        finally:
            s.close()

    def test_autocalc_next_maintenance(self, patched_db):
        # next=None 但有 last + interval → 自动算 next; last-100+90=今天-10 → overdue
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8302, next_maint=None,
             last_maint=today - timedelta(days=100), interval=90)
        db.commit()

        # 不传 db → 方法自动 commit, 持久化自动算出的 next_maintenance
        results = MaintenanceScheduleChecker().check_maintenance_schedule()

        assert len(results) == 1
        assert results[0]["status"] == "overdue"
        assert results[0]["next_maintenance"] == str(today - timedelta(days=10))

        # 自动设置的 next_maintenance 被持久化
        s = _fresh(patched_db)
        try:
            d = s.query(Device).filter_by(id=8302).one()
            assert d.next_maintenance == today - timedelta(days=10)
        finally:
            s.close()

    def test_normal_device_not_reminded(self, patched_db):
        # days_until > warning_days(14) → 正常, 返回 None
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8303, next_maint=today + timedelta(days=30))
        db.commit()

        results = MaintenanceScheduleChecker().check_maintenance_schedule(db=db)
        assert results == []


# ═══════════════════════════════════════════════════════════════
# check_maintenance_schedule - 已有告警去重
# ═══════════════════════════════════════════════════════════════

class TestCheckScheduleDedup:

    def _seed_overdue_device_and_alarm(self, db, did, status):
        today = TODAY()
        _dev(db, did, next_maint=today - timedelta(days=2))
        db.add(Alarm(
            device_id=did, station_id=1, alarm_type="maintenance_overdue",
            level=AlarmLevel.WARNING, content="已存在", status=status,
        ))
        db.commit()

    def test_existing_active_alarm_skips_creation(self, patched_db):
        db = patched_db["session"]
        self._seed_overdue_device_and_alarm(db, 8401, AlarmStatus.ACTIVE)

        results = MaintenanceScheduleChecker().check_maintenance_schedule(db=db)

        assert len(results) == 1
        assert results[0]["existing_alarm"] is True
        assert "alarm_id" not in results[0]
        # 不新增: 仍是 1 条
        s = _fresh(patched_db)
        try:
            assert s.query(Alarm).filter_by(device_id=8401).count() == 1
        finally:
            s.close()

    def test_existing_acknowledged_alarm_skips_creation(self, patched_db):
        db = patched_db["session"]
        self._seed_overdue_device_and_alarm(db, 8402, AlarmStatus.ACKNOWLEDGED)

        results = MaintenanceScheduleChecker().check_maintenance_schedule(db=db)
        assert results[0]["existing_alarm"] is True

    def test_resolved_alarm_not_treated_as_existing(self, patched_db):
        # RESOLVED 被 _load_maintenance_alarms 过滤 → 视为无 existing, 新建告警
        db = patched_db["session"]
        self._seed_overdue_device_and_alarm(db, 8403, AlarmStatus.RESOLVED)

        # 不传 db → 方法自动 commit, _fresh 可读到新增的 ACTIVE 告警
        results = MaintenanceScheduleChecker().check_maintenance_schedule()

        assert len(results) == 1
        assert "existing_alarm" not in results[0]
        s = _fresh(patched_db)
        try:
            # 原 RESOLVED + 新 ACTIVE = 2 条
            assert s.query(Alarm).filter_by(device_id=8403).count() == 2
        finally:
            s.close()


# ═══════════════════════════════════════════════════════════════
# check_maintenance_schedule - 异常路径 + should_close_db
# ═══════════════════════════════════════════════════════════════

class TestCheckScheduleErrors:

    def test_db_error_rollback_and_raise(self, patched_db, monkeypatch):
        # 不传 db → should_close_db=True; db.query 抛错 → rollback + finally close + raise
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("db down")
        monkeypatch.setattr(maint_mod, "SessionLocal", lambda: mock_db)

        checker = MaintenanceScheduleChecker()
        with pytest.raises(RuntimeError, match="db down"):
            checker.check_maintenance_schedule()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    def test_single_device_error_continues(self, patched_db, monkeypatch):
        # 单设备 _check_single_device 抛错 → 记日志 continue, 不中断其余设备
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8501, next_maint=today - timedelta(days=1))
        _dev(db, 8502, next_maint=today - timedelta(days=1))
        db.commit()

        checker = MaintenanceScheduleChecker()
        real = checker._check_single_device
        state = {"n": 0}

        def flaky(d, device, tday, alarm_map=None):
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("device boom")
            return real(d, device, tday, alarm_map)

        monkeypatch.setattr(checker, "_check_single_device", flaky)

        results = checker.check_maintenance_schedule(db=db)

        assert len(results) == 1
        assert results[0]["device_id"] == 8502


class TestShouldCloseDb:

    def test_no_db_arg_commits_and_closes(self, patched_db, monkeypatch):
        # 不传 db → 内部 SessionLocal() 开新 session, 处理完 commit+close
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8601, next_maint=today - timedelta(days=2))
        db.commit()  # 让新 session 能查到 device

        calls = {"n": 0}
        orig = patched_db["SessionLocal"]

        def counting():
            calls["n"] += 1
            return orig()

        monkeypatch.setattr(maint_mod, "SessionLocal", counting)

        results = MaintenanceScheduleChecker().check_maintenance_schedule()

        assert calls["n"] == 1                 # 仅开一次新 session
        assert len(results) == 1
        # commit 生效: 新 session 能读到 alarm
        s = _fresh(patched_db)
        try:
            assert s.query(Alarm).filter_by(device_id=8601).count() == 1
        finally:
            s.close()

    def test_passed_db_arg_skips_sessionlocal(self, patched_db, monkeypatch):
        # 传 db → should_close_db=False, 不调 SessionLocal, 不 close 传入的 session
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8602, next_maint=today + timedelta(days=3))
        db.commit()

        def _boom():
            raise AssertionError("SessionLocal 不应被调用")

        monkeypatch.setattr(maint_mod, "SessionLocal", _boom)

        results = MaintenanceScheduleChecker().check_maintenance_schedule(db=db)
        db.flush()   # should_close_db=False 不 commit; flush 推送 pending 入库供同 session 查询

        assert len(results) == 1
        # 传入的 session 未被 close, 仍可查询
        assert db.query(Alarm).filter_by(device_id=8602).count() == 1


# ═══════════════════════════════════════════════════════════════
# _check_single_device - alarm_map=None 旧调用回退
# ═══════════════════════════════════════════════════════════════

class TestCheckSingleDeviceLegacy:

    def test_no_alarm_map_fallback_creates_alarm(self, patched_db):
        # 直调不传 alarm_map → 走 line 150-156 db.query 回退; 无 existing → 创建
        db = patched_db["session"]
        today = TODAY()
        d = _dev(db, 8701, next_maint=today + timedelta(days=4))
        db.commit()

        checker = MaintenanceScheduleChecker()
        record = checker._check_single_device(db, d, today)   # alarm_map 缺省 None
        db.flush()   # add 后未 commit; flush 让同 session 查询可见

        assert record is not None
        assert record["status"] == "soon"
        assert db.query(Alarm).filter_by(device_id=8701).count() == 1

    def test_no_alarm_map_fallback_finds_existing(self, patched_db):
        # 回退查询命中已有 ACTIVE 告警 → existing_alarm=True, 不新建
        db = patched_db["session"]
        today = TODAY()
        d = _dev(db, 8702, next_maint=today - timedelta(days=1))
        db.add(Alarm(
            device_id=8702, station_id=1, alarm_type="maintenance_overdue",
            level=AlarmLevel.WARNING, content="旧", status=AlarmStatus.ACTIVE,
        ))
        db.commit()

        record = MaintenanceScheduleChecker()._check_single_device(db, d, today)

        assert record["existing_alarm"] is True
        assert db.query(Alarm).filter_by(device_id=8702).count() == 1


# ═══════════════════════════════════════════════════════════════
# get_upcoming_maintenance
# ═══════════════════════════════════════════════════════════════

class TestGetUpcoming:

    def test_status_breakdown_and_order(self, patched_db):
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8801, name="逾期", next_maint=today - timedelta(days=5))   # overdue
        _dev(db, 8802, name="即将", next_maint=today + timedelta(days=5))   # soon
        _dev(db, 8803, name="临近", next_maint=today + timedelta(days=12))  # warning
        _dev(db, 8804, name="未来", next_maint=today + timedelta(days=25))  # upcoming(<=30)
        _dev(db, 8805, name="超窗", next_maint=today + timedelta(days=40))  # > days_ahead 过滤
        _dev(db, 8806, name="无计划", next_maint=None)                      # None 过滤
        db.commit()

        results = MaintenanceScheduleChecker().get_upcoming_maintenance(db=db, days_ahead=30)

        assert [r["device_id"] for r in results] == [8801, 8802, 8803, 8804]
        by_id = {r["device_id"]: r for r in results}
        assert by_id[8801]["status"] == "overdue"
        assert by_id[8802]["status"] == "soon"
        assert by_id[8803]["status"] == "warning"
        assert by_id[8804]["status"] == "upcoming"
        # type.value 序列化
        assert by_id[8801]["type"] == DeviceType.CHARGER_DC.value
        assert by_id[8801]["sn"] == "SN-MS-8801"
        assert by_id[8801]["station_id"] == 1

    def test_empty_when_no_devices(self, patched_db):
        db = patched_db["session"]
        db.commit()
        results = MaintenanceScheduleChecker().get_upcoming_maintenance(db=db)
        assert results == []

    def test_no_db_arg_uses_sessionlocal(self, patched_db, monkeypatch):
        # 不传 db → should_close_db=True, 内部 SessionLocal() + finally close
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8901, next_maint=today + timedelta(days=5))
        db.commit()

        results = MaintenanceScheduleChecker().get_upcoming_maintenance()
        assert len(results) == 1
        assert results[0]["device_id"] == 8901

    def test_passed_db_arg_skips_sessionlocal(self, patched_db, monkeypatch):
        # 传 db → 不调 SessionLocal
        db = patched_db["session"]
        today = TODAY()
        _dev(db, 8902, next_maint=today + timedelta(days=5))
        db.commit()

        def _boom():
            raise AssertionError("SessionLocal 不应被调用")

        monkeypatch.setattr(maint_mod, "SessionLocal", _boom)

        results = MaintenanceScheduleChecker().get_upcoming_maintenance(db=db)
        assert len(results) == 1


# ═══════════════════════════════════════════════════════════════
# 业务时区边界 (卡 48bc65fe, 时区缺陷族第5弹)
# 云端 UTC 容器: 上海 00:00-08:00 = UTC 前日 16:00-24:00, date.today() 返回 UTC
# 前日 = 业务昨天 → 维护到期判定/未来窗口起算整体错位 1 天。
# ═══════════════════════════════════════════════════════════════

class TestBizTimezoneBoundary:
    """凌晨窗口 (上海 00:30 = UTC 前日 16:30) 业务日判定。"""

    BIZ_TODAY = date(2026, 8, 7)   # 业务时区"今天"
    UTC_TODAY = date(2026, 8, 6)   # UTC 容器 date.today() = 业务昨天

    def _freeze_window(self, monkeypatch):
        """模拟云端 UTC 容器在上海凌晨窗口。

        date.today()        取 UTC 前日 (业务昨天) —— 复现旧实现错位;
        today_in_biz_tz()   取业务今天            —— 修复后正确基准。

        datetime.date 为 C 实现不可变类型, 不能 monkeypatch 其 today —— 用子类替换模块
        date 引用。raising=False: RED 阶段 maint_mod 尚未 import today_in_biz_tz。
        """
        class _FrozenDate(date):
            @classmethod
            def today(cls):
                return self.UTC_TODAY
        monkeypatch.setattr(maint_mod, "date", _FrozenDate, raising=False)
        monkeypatch.setattr(maint_mod, "today_in_biz_tz", lambda: self.BIZ_TODAY, raising=False)

    def test_check_maintenance_uses_biz_today(self, patched_db, monkeypatch):
        """业务昨天到期的维护: 业务日看应判 overdue。

        next_maintenance = BIZ_TODAY-1d (业务昨天):
          修复后 today_in_biz_tz()=BIZ_TODAY → days_until=-1 → overdue ✓
          旧 date.today()=UTC_TODAY(=业务昨天) → days_until=0 → soon (漏判逾期) ✗
        """
        self._freeze_window(monkeypatch)
        db = patched_db["session"]
        _dev(db, 8501, next_maint=self.BIZ_TODAY - timedelta(days=1))
        db.commit()

        results = MaintenanceScheduleChecker().check_maintenance_schedule(db=db)

        matched = [r for r in results if r["device_id"] == 8501]
        assert matched, "业务昨天到期的维护应触发提醒"
        assert matched[0]["status"] == "overdue", matched[0]["status"]

    def test_get_upcoming_window_uses_biz_today(self, patched_db, monkeypatch):
        """未来 N 天窗口起算自业务今天。

        next_maintenance = BIZ_TODAY+7, days_ahead=7 (含边界):
          修复后 future = BIZ_TODAY+7 → 含该设备 ✓
          旧 date.today()=UTC_TODAY → future = UTC_TODAY+7 = BIZ_TODAY+6 → 漏排 ✗
        """
        self._freeze_window(monkeypatch)
        db = patched_db["session"]
        _dev(db, 8502, next_maint=self.BIZ_TODAY + timedelta(days=7))
        db.commit()

        results = MaintenanceScheduleChecker().get_upcoming_maintenance(db=db, days_ahead=7)

        ids = [r["device_id"] for r in results]
        assert 8502 in ids, f"业务今天起 7 天后的维护应进入窗口, got {ids}"
