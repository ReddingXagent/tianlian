"""test_service_db_exception_safety.py — 12个service函数DB写操作异常保护测试

验证目标函数在 db.add / db.commit / db.delete 抛异常时:
1. 不向调用方裸抛(被 try/except 兜底)
2. 调用 db.rollback() 回滚事务
3. 记录 logger.error
4. 返回合理的降级值 (Dict 返回 {"error": ...}, 对象/辅助函数返回 None)

被测卡片: 7d8e16b6
覆盖函数:
- healing_engine: _create_execution / approve_execution / reject_execution /
  retry_execution / create_rule / update_rule / delete_rule / verify_healing_result
- alarm_rule_service: _escalate_single
- notification_sender: _log_notification
- maintenance_schedule: _check_single_device
- code_generator: _get_or_create_sequence

设计: 全部用 MagicMock 隔离 DB, 通过 *.side_effect 注入写异常。
"""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.healing_engine import HealingEngine
from app.services.alarm_rule_service import AlarmRuleEngine
from app.services.notification_sender import NotificationSender
from app.services.maintenance_schedule import MaintenanceScheduleChecker
from app.services.code_generator import CodeGenerator

from app.models.healing_rule import HealingRule
from app.models.healing_execution import HealingExecution
from app.models.alarm import Alarm, AlarmLevel
from app.models.device import Device


# ─── 辅助: 按模型分发的 db.query mock (多次 query 互不干扰) ───

def make_db_query_by_model():
    """db.query(Model) 按模型分发到独立 chain mock, 便于多次查询分别配置。"""
    db = MagicMock()
    by_model = {}

    def _query(model, *args, **kwargs):
        return by_model.setdefault(model, MagicMock())

    db.query.side_effect = _query
    db._by_model = by_model
    return db


def chain_for(db, model):
    return db._by_model.setdefault(model, MagicMock())


# ═══════════════════════════════════════════════════════════════
# healing_engine — 8 个函数
# ═══════════════════════════════════════════════════════════════

class TestHealingCreateExecution:
    def test_db_failure_returns_none_and_rolls_back(self):
        eng = HealingEngine()
        rule = MagicMock(id=1, name="规则", runbook_template="tpl")
        alarm = MagicMock(id=2, device_id=10, station_id=100,
                          alarm_type="故障", fault_code=None)
        db = MagicMock()
        db.commit.side_effect = RuntimeError("db down")

        result = eng._create_execution(rule, alarm, db)  # 不应抛出

        assert result is None
        db.rollback.assert_called_once()

    def test_db_failure_logs_error(self, caplog):
        eng = HealingEngine()
        rule = MagicMock(id=1, name="规则", runbook_template="tpl")
        alarm = MagicMock(id=2, device_id=10, station_id=100,
                          alarm_type="故障", fault_code=None)
        db = MagicMock()
        db.commit.side_effect = RuntimeError("db down")

        with caplog.at_level("ERROR", logger="app.services.healing_engine"):
            eng._create_execution(rule, alarm, db)

        assert any("db down" in r.getMessage() or "创建" in r.getMessage()
                   for r in caplog.records)


class TestHealingApproveExecution:
    def test_db_failure_returns_error_and_rolls_back(self):
        eng = HealingEngine()
        eng.execute_healing = MagicMock()  # commit 失败不应进入执行
        db = MagicMock()
        execution = MagicMock(id=1, status="pending_approval")
        db.query.return_value.filter.return_value.first.return_value = execution
        db.commit.side_effect = RuntimeError("db down")

        result = eng.approve_execution(1, "admin", db)

        assert "error" in result
        db.rollback.assert_called_once()
        eng.execute_healing.assert_not_called()


class TestHealingRejectExecution:
    def test_db_failure_returns_error_and_rolls_back(self):
        eng = HealingEngine()
        db = MagicMock()
        execution = MagicMock(id=1, status="pending_approval")
        db.query.return_value.filter.return_value.first.return_value = execution
        db.commit.side_effect = RuntimeError("db down")

        result = eng.reject_execution(1, "admin", "误报", db)

        assert "error" in result
        db.rollback.assert_called_once()


class TestHealingRetryExecution:
    def test_db_failure_returns_error_and_rolls_back(self):
        eng = HealingEngine()
        eng.execute_healing = MagicMock()  # commit 失败不应进入执行
        db = make_db_query_by_model()
        execution = MagicMock(id=1, status="failed", retry_count=0, rule_id=1)
        # retry_execution 重试前查冷却(缺口2): rule.cooldown_minutes 须为 int(_check_cooldown
        # 比较 <=0); HealingExecution.filter().first() 被消费两次:
        # ① 取待重试 execution  ② 冷却检查=None(无活跃,放行到 commit 路径)。
        rule = MagicMock(max_retries=3, cooldown_minutes=30)
        chain_for(db, HealingExecution).filter.return_value.first.side_effect = [execution, None]
        chain_for(db, HealingRule).filter.return_value.first.return_value = rule
        db.commit.side_effect = RuntimeError("db down")

        result = eng.retry_execution(1, db)

        assert "error" in result
        db.rollback.assert_called_once()
        eng.execute_healing.assert_not_called()


class TestHealingCreateRule:
    def test_db_failure_returns_error_and_rolls_back(self):
        eng = HealingEngine()
        data = {"name": "规则", "alarm_pattern": {"alarm_levels": ["critical"]}}
        db = MagicMock()
        db.commit.side_effect = RuntimeError("db down")

        result = eng.create_rule(data, db)

        assert "error" in result
        db.rollback.assert_called_once()


class TestHealingUpdateRule:
    def test_db_failure_returns_error_and_rolls_back(self):
        eng = HealingEngine()
        db = MagicMock()
        rule = MagicMock(id=1, name="规则")
        db.query.return_value.filter.return_value.first.return_value = rule
        db.commit.side_effect = RuntimeError("db down")

        result = eng.update_rule(1, {"name": "新规则"}, db)

        assert "error" in result
        db.rollback.assert_called_once()


class TestHealingDeleteRule:
    def test_db_failure_returns_error_and_rolls_back(self):
        eng = HealingEngine()
        db = MagicMock()
        rule = MagicMock(id=1)
        chain = db.query.return_value.filter.return_value
        chain.first.return_value = rule
        chain.count.return_value = 0  # 无活跃执行记录
        db.commit.side_effect = RuntimeError("db down")

        result = eng.delete_rule(1, db)

        assert "error" in result
        db.rollback.assert_called_once()


class TestHealingVerifyHealingResult:
    def test_db_failure_returns_error_and_rolls_back(self):
        eng = HealingEngine()
        db = make_db_query_by_model()
        execution = MagicMock(id=1, status="success", alarm_id=2, device_id=10)
        chain_for(db, HealingExecution).filter.return_value.first.return_value = execution
        chain_for(db, Alarm).filter.return_value.first.return_value = None
        chain_for(db, Device).filter.return_value.first.return_value = None
        db.commit.side_effect = RuntimeError("db down")

        result = eng.verify_healing_result(1, db)

        assert "error" in result
        db.rollback.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# alarm_rule_service — _escalate_single (两个升级分支)
# ═══════════════════════════════════════════════════════════════

class TestAlarmEscalateSingle:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_warn_to_critical_db_failure_returns_none(self):
        now = datetime.now(timezone.utc)
        alarm = MagicMock()
        alarm.id = 1
        alarm.device_id = 10
        alarm.level = AlarmLevel.WARNING
        alarm.created_at = now - timedelta(minutes=60)  # 超过默认 30 分钟
        alarm.rule_id = None
        alarm.original_level = None
        alarm.content = "过温"
        db = MagicMock()
        db.commit.side_effect = RuntimeError("db down")

        result = self.eng._escalate_single(alarm, now, db)

        assert result is None
        db.rollback.assert_called_once()

    def test_critical_to_fatal_db_failure_returns_none(self):
        now = datetime.now(timezone.utc)
        alarm = MagicMock()
        alarm.id = 2
        alarm.device_id = 11
        alarm.level = AlarmLevel.CRITICAL
        alarm.created_at = now - timedelta(minutes=20)  # 超过 max(15, timeout//2)
        alarm.rule_id = None
        alarm.original_level = None
        alarm.content = "通讯中断"
        db = MagicMock()
        db.commit.side_effect = RuntimeError("db down")

        result = self.eng._escalate_single(alarm, now, db)

        assert result is None
        db.rollback.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# notification_sender — _log_notification (best-effort 日志)
# ═══════════════════════════════════════════════════════════════

class TestNotificationLogNotification:
    def test_db_failure_does_not_raise_and_rolls_back(self):
        sender = NotificationSender()
        db = MagicMock()
        db.add.side_effect = RuntimeError("db down")
        receiver = {"type": "user", "id": "138", "name": "张三"}

        # 不应抛出 (best-effort 日志, 不影响主通知流程)
        result = sender._log_notification(
            db, config_id=None, event_type="alarm_trigger", event_id="1",
            event_data={}, channel="sms", template=None, receiver=receiver,
            subject=None, content="内容", status="sent",
        )

        assert result is None
        # 实现用 begin_nested() (SAVEPOINT) 隔离单条日志失败, 不调用 db.rollback()
        db.begin_nested.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# maintenance_schedule — _check_single_device
# ═══════════════════════════════════════════════════════════════

def _make_maintenance_device(dev_id=1, *, next_maintenance):
    d = MagicMock()
    d.id = dev_id
    d.name = f"Dev{dev_id}"
    d.station_id = 1
    d.next_maintenance = next_maintenance
    return d


class TestMaintenanceCheckSingleDevice:
    def test_db_failure_returns_none_and_rolls_back(self):
        checker = MaintenanceScheduleChecker()
        today = date(2026, 8, 5)
        dev = _make_maintenance_device(next_maintenance=today - timedelta(days=3))  # overdue
        db = MagicMock()
        db.add.side_effect = RuntimeError("db down")

        result = checker._check_single_device(db, dev, today, {})

        assert result is None
        db.rollback.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# code_generator — _get_or_create_sequence
# ═══════════════════════════════════════════════════════════════

class TestCodeGetOrCreateSequence:
    def test_db_failure_returns_none_and_rolls_back(self):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None  # 走创建分支
        db.flush.side_effect = RuntimeError("db down")

        result = CodeGenerator._get_or_create_sequence(db, "seq:test:x")

        assert result is None
        db.rollback.assert_called_once()
