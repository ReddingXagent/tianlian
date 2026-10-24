"""
HealingEngine 单元测试

被测文件: app/services/healing_engine.py

设计要点:
- DB 用 MagicMock 隔离; 查询链按"模型"分发 (db.query.side_effect), 每个 model 独立 chain
- 枚举字段 (alarm.level / device.device_type / device.status) 用纯字符串, 避免
  MagicMock 自动属性导致 hasattr(x,'value') 永真 的歧义
- RunbookEngine 在 __init__ 内实例化, 测试中替换 engine._runbook_engine = MagicMock()
- get_stats 用 func.count/func.avg 作 query 目标, 与按模型分发不兼容, 单独用扁平 MagicMock
"""
from unittest.mock import MagicMock
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest

from app.services.healing_engine import HealingEngine
from app.models.healing_rule import HealingRule
from app.models.healing_execution import HealingExecution
from app.models.alarm import Alarm
from app.models.device import Device


# ─── DB chain mock 辅助 ───

def make_db():
    """db.query(Model) 按 Model 分发到独立 chain mock。"""
    db = MagicMock()
    by_model = {}

    def _query(model, *args, **kwargs):
        return by_model.setdefault(model, MagicMock(name=f"q[{getattr(model, '__name__', repr(model))}]"))

    db.query.side_effect = _query
    db._by_model = by_model
    return db


def chain_for(db, model):
    return db._by_model.setdefault(model, MagicMock())


UNSET = object()  # sentinel: 区分"未提供"与"显式 None"(None 是 .first() 的合法未找到返回)


def set_chain(chain, *, all_=UNSET, first=UNSET, count=UNSET, scalar=UNSET,
              group_rows=UNSET, page_items=UNSET):
    """统一配置查询链的常见终止调用 (覆盖 filter / order_by / 根级多种路径)。

    用 UNSET sentinel 而非 None 默认值, 这样 first=None / all_=[] 也能正确写入。
    """
    root = chain
    f = root.filter.return_value
    fo = f.order_by.return_value
    ro = root.order_by.return_value

    if all_ is not UNSET:
        root.all.return_value = all_
        f.all.return_value = all_
        f.limit.return_value.all.return_value = all_  # batch_verify 走 filter().limit().all()
        fo.all.return_value = all_
        ro.all.return_value = all_
    if first is not UNSET:
        root.first.return_value = first
        f.first.return_value = first
        fo.first.return_value = first
        ro.first.return_value = first
    if count is not UNSET:
        f.count.return_value = count
        fo.count.return_value = count
        root.count.return_value = count
    if scalar is not UNSET:
        root.scalar.return_value = scalar
        f.scalar.return_value = scalar
    if group_rows is not UNSET:
        root.group_by.return_value.all.return_value = group_rows
        f.group_by.return_value.all.return_value = group_rows
    if page_items is not UNSET:
        fo.offset.return_value.limit.return_value.all.return_value = page_items
        ro.offset.return_value.limit.return_value.all.return_value = page_items


# ─── 业务对象工厂 (MagicMock + 纯字符串枚举字段) ───

def make_alarm(aid=1, *, level="critical", alarm_type="逆变器通讯中断", content="过温告警",
               device_id=10, station_id=100, diagnosis_result=None, fault_code=None,
               device=None, status="active"):
    a = MagicMock()
    a.id = aid
    a.level = level                      # 纯字符串 → str(level)
    a.alarm_type = alarm_type
    a.content = content
    a.device_id = device_id
    a.station_id = station_id
    a.diagnosis_result = diagnosis_result
    a.fault_code = fault_code
    a.device = device                    # None 或 MagicMock
    a.status = status
    return a


_DEFAULT_PATTERN = {"alarm_levels": ["critical"]}  # 共享只读, 不在测试中修改


def make_rule(rid=1, *, name="规则A", enabled=True, priority=10, cooldown_minutes=30,
              alarm_pattern=_DEFAULT_PATTERN, runbook_template="tpl", auto_approve=False, max_retries=1,
              description="d"):
    r = MagicMock()
    r.id = rid
    r.name = name
    r.enabled = enabled
    r.priority = priority
    r.cooldown_minutes = cooldown_minutes
    r.alarm_pattern = alarm_pattern  # 传 None 即 None (用于测空 pattern 分支)
    r.runbook_template = runbook_template
    r.auto_approve = auto_approve
    r.max_retries = max_retries
    r.description = description
    r.created_at = datetime(2026, 1, 1)
    r.updated_at = datetime(2026, 1, 2)
    return r


def make_execution(eid=42, *, status="pending_approval", rule_id=1, alarm_id=1, device_id=10,
                   station_id=100, fault_type="未知故障", retry_count=0):
    e = MagicMock()
    e.id = eid
    e.rule_id = rule_id
    e.rule_name = "规则A"
    e.alarm_id = alarm_id
    e.device_id = device_id
    e.station_id = station_id
    e.runbook_id = None
    e.runbook_template = "tpl"
    e.fault_type = fault_type
    e.status = status
    e.steps = []
    e.approved_by = None
    e.approved_at = None
    e.reject_reason = None
    e.total_duration_ms = 0
    e.success_steps = 0
    e.failed_steps = 0
    e.retry_count = retry_count
    e.result = None
    e.error_message = None
    e.completed_at = None
    e.started_at = None
    e.created_at = datetime(2026, 1, 1)
    e.verified = False
    e.verified_at = None
    e.verification_result = None
    e.alarm_cleared = False
    return e


def make_device(did=10, *, name="逆变器#1", sn="SN001", ip_address="10.0.0.1",
                station_id=100, device_type="inverter", status="online"):
    d = MagicMock()
    d.id = did
    d.name = name
    d.sn = sn
    d.ip_address = ip_address
    d.station_id = station_id
    d.device_type = device_type          # 纯字符串
    d.status = status                    # 纯字符串
    return d


def fresh_engine():
    """构造 HealingEngine 并替换 runbook_engine 为 MagicMock。"""
    eng = HealingEngine()
    eng._runbook_engine = MagicMock()
    return eng


# ─── 真实 SQLite 持久化 helper (用于 TOCTOU / 冷却 / 时区的真实 SQL 验证) ───

def _persist_rule(db, *, name="R", cooldown_minutes=30, max_retries=1, priority=1,
                  alarm_pattern=None, auto_approve=False):
    rule = HealingRule(
        name=name,
        alarm_pattern=alarm_pattern or {"alarm_levels": ["critical"]},
        cooldown_minutes=cooldown_minutes,
        max_retries=max_retries,
        priority=priority,
        auto_approve=auto_approve,
        enabled=True,
    )
    db.add(rule); db.commit(); db.refresh(rule)
    return rule


def _persist_execution(db, rule, *, device_id=10, status="pending_approval",
                       alarm_id=1, station_id=100, created_at=None):
    ex = HealingExecution(
        rule_id=rule.id, rule_name=rule.name, alarm_id=alarm_id,
        device_id=device_id, station_id=station_id, fault_type="x",
        status=status, steps=[],
    )
    if created_at is not None:
        ex.created_at = created_at
    db.add(ex); db.commit(); db.refresh(ex)
    return ex


def _alarm_obj(aid=999, device_id=10, station_id=100, alarm_type="过温"):
    """带真实标量属性的 alarm (供 _create_execution 读取, 非 MagicMock 自动属性)。"""
    return SimpleNamespace(
        id=aid, device_id=device_id, station_id=station_id,
        alarm_type=alarm_type, fault_code=None,
    )


# ═══════════════════════════════════════════════════════════
# _match_alarm — 条件匹配全分支 (纯函数, 不用 db)
# ═══════════════════════════════════════════════════════════

class TestMatchAlarm:
    def setup_method(self):
        self.eng = fresh_engine()

    def test_empty_pattern_returns_false(self):
        rule = make_rule(alarm_pattern=None)
        assert self.eng._match_alarm(make_alarm(), rule) is False

    def test_alarm_level_match_and_mismatch(self):
        rule = make_rule(alarm_pattern={"alarm_levels": ["critical"]})
        assert self.eng._match_alarm(make_alarm(level="critical"), rule) is True
        assert self.eng._match_alarm(make_alarm(level="warning"), rule) is False

    def test_alarm_type_substring_match(self):
        rule = make_rule(alarm_pattern={"alarm_types": ["通讯中断"]})
        assert self.eng._match_alarm(make_alarm(alarm_type="逆变器通讯中断"), rule) is True
        assert self.eng._match_alarm(make_alarm(alarm_type="电压异常"), rule) is False

    def test_alarm_type_blank_when_pattern_required(self):
        # alarm_type=None 时, any(...) 对 ["xxx"] 为 False
        rule = make_rule(alarm_pattern={"alarm_types": ["xxx"]})
        assert self.eng._match_alarm(make_alarm(alarm_type=None), rule) is False

    def test_device_type_match(self):
        dev = MagicMock()
        dev.device_type = "inverter"
        rule = make_rule(alarm_pattern={"device_types": ["inverter"]})
        assert self.eng._match_alarm(make_alarm(device=dev), rule) is True
        dev.device_type = "meter"
        assert self.eng._match_alarm(make_alarm(device=dev), rule) is False

    def test_device_ids_filter(self):
        rule = make_rule(alarm_pattern={"device_ids": [10, 11]})
        assert self.eng._match_alarm(make_alarm(device_id=10), rule) is True
        assert self.eng._match_alarm(make_alarm(device_id=99), rule) is False

    def test_station_ids_filter(self):
        rule = make_rule(alarm_pattern={"station_ids": [100]})
        assert self.eng._match_alarm(make_alarm(station_id=100), rule) is True
        assert self.eng._match_alarm(make_alarm(station_id=200), rule) is False

    def test_content_keywords_match(self):
        rule = make_rule(alarm_pattern={"content_keywords": ["过温", "通讯"]})
        assert self.eng._match_alarm(make_alarm(content="设备过温告警"), rule) is True
        assert self.eng._match_alarm(make_alarm(content="电压偏低"), rule) is False

    def test_all_fields_match_returns_true(self):
        dev = MagicMock()
        dev.device_type = "inverter"
        rule = make_rule(alarm_pattern={
            "alarm_levels": ["critical"],
            "alarm_types": ["通讯中断"],
            "device_types": ["inverter"],
            "device_ids": [10],
            "station_ids": [100],
            "content_keywords": ["过温"],
        })
        assert self.eng._match_alarm(
            make_alarm(level="critical", alarm_type="逆变器通讯中断", content="过温",
                       device_id=10, station_id=100, device=dev),
            rule) is True

    def test_device_types_pattern_with_none_device_returns_false(self):
        """缺陷2: 配了 device_types 但 alarm.device=None(设备删除/关联断裂) → 判不匹配。

        回归保护: 旧逻辑 `if device_types and alarm.device:` 在 device=None 时
        静默跳过过滤 → 规则过度匹配错误目标。
        """
        rule = make_rule(alarm_pattern={"device_types": ["inverter"]})
        assert self.eng._match_alarm(make_alarm(device=None), rule) is False

    def test_content_keywords_pattern_with_empty_content_returns_false(self):
        """缺陷2: 配了 content_keywords 但告警 content 为空 → 判不匹配。

        回归保护: 旧逻辑 `if content_keywords and alarm.content:` 在 content 为空时
        静默跳过关键词过滤。
        """
        rule = make_rule(alarm_pattern={"content_keywords": ["过温"]})
        assert self.eng._match_alarm(make_alarm(content=None), rule) is False
        assert self.eng._match_alarm(make_alarm(content=""), rule) is False


# ═══════════════════════════════════════════════════════════
# _check_cooldown / _create_execution
# ═══════════════════════════════════════════════════════════

class TestCooldownAndCreate:
    def test_no_rule_returns_false(self):
        eng = fresh_engine()
        db = make_db()
        set_chain(chain_for(db, HealingRule), first=None)
        assert eng._check_cooldown(1, 10, db) is False

    def test_zero_cooldown_returns_false(self):
        eng = fresh_engine()
        db = make_db()
        rule = make_rule(cooldown_minutes=0)
        set_chain(chain_for(db, HealingRule), first=rule)
        assert eng._check_cooldown(1, 10, db) is False

    def test_recent_execution_means_in_cooldown(self):
        eng = fresh_engine()
        db = make_db()
        set_chain(chain_for(db, HealingRule), first=make_rule(cooldown_minutes=30))
        set_chain(chain_for(db, HealingExecution), first=make_execution())  # 近期记录存在
        assert eng._check_cooldown(1, 10, db) is True

    def test_no_recent_execution_not_in_cooldown(self):
        eng = fresh_engine()
        db = make_db()
        set_chain(chain_for(db, HealingRule), first=make_rule(cooldown_minutes=30))
        set_chain(chain_for(db, HealingExecution), first=None)
        assert eng._check_cooldown(1, 10, db) is False

    def test_create_execution_persists_and_returns(self):
        eng = fresh_engine()
        db = make_db()
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 777)
        rule = make_rule(rid=5, name="R5", runbook_template="tplX")
        alarm = make_alarm(aid=9, device_id=10, station_id=100, alarm_type="过温")
        # 新契约: _create_execution 插入后自查重复 (查 HealingExecution 近期活跃记录)。
        # 配 first=None 表示无并发更早记录 → 不撤销。
        set_chain(chain_for(db, HealingExecution), first=None)

        ex = eng._create_execution(rule, alarm, db)
        db.add.assert_called_once_with(ex)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(ex)
        assert ex.id == 777
        assert ex.rule_id == 5
        assert ex.alarm_id == 9
        assert ex.fault_type == "过温"
        assert ex.status == "pending_approval"


# ═══════════════════════════════════════════════════════════
# evaluate_alarm
# ═══════════════════════════════════════════════════════════

class TestEvaluateAlarm:
    def test_no_rules_returns_none(self):
        eng = fresh_engine()
        db = make_db()
        set_chain(chain_for(db, HealingRule), all_=[])
        assert eng.evaluate_alarm(make_alarm(), db) is None

    def test_matching_rule_in_cooldown_is_skipped(self):
        eng = fresh_engine()
        db = make_db()
        rule = make_rule(rid=1, alarm_pattern={"alarm_levels": ["critical"]}, auto_approve=False)
        set_chain(chain_for(db, HealingRule), all_=[rule], first=rule)
        set_chain(chain_for(db, HealingExecution), first=make_execution())  # 在冷却期
        result = eng.evaluate_alarm(make_alarm(level="critical"), db)
        assert result is None  # 唯一规则被冷却跳过 → 无匹配

    def test_matching_rule_pending_approval(self):
        eng = fresh_engine()
        db = make_db()
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 55)
        rule = make_rule(rid=3, name="R3", alarm_pattern={"alarm_levels": ["critical"]},
                         auto_approve=False)
        set_chain(chain_for(db, HealingRule), all_=[rule], first=rule)
        set_chain(chain_for(db, HealingExecution), first=None)  # 不在冷却期
        result = eng.evaluate_alarm(make_alarm(aid=7, level="critical", device_id=10, station_id=100), db)
        assert result["status"] == "pending_approval"
        assert result["execution_id"] == 55
        assert result["rule_id"] == 3
        assert result["alarm_id"] == 7

    def test_matching_auto_approve_calls_execute_auto(self):
        eng = fresh_engine()
        db = make_db()
        sentinel = {"status": "success", "execution_id": 55}
        eng._execute_auto = MagicMock(return_value=sentinel)
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 55)
        rule = make_rule(rid=3, alarm_pattern={"alarm_levels": ["critical"]}, auto_approve=True)
        set_chain(chain_for(db, HealingRule), all_=[rule], first=rule)
        set_chain(chain_for(db, HealingExecution), first=None)
        result = eng.evaluate_alarm(make_alarm(level="critical"), db)
        assert result is sentinel
        eng._execute_auto.assert_called_once()

    def test_create_execution_none_skips_rule_no_crash(self):
        """缺陷1: _create_execution 返回 None(DB异常) 时 evaluate_alarm 不崩溃。

        回归保护: 旧逻辑拿到 None 后直接 execution.id → AttributeError。修复后跳过该规则。
        """
        eng = fresh_engine()
        db = make_db()
        rule = make_rule(rid=1, alarm_pattern={"alarm_levels": ["critical"]}, auto_approve=False)
        set_chain(chain_for(db, HealingRule), all_=[rule], first=rule)
        set_chain(chain_for(db, HealingExecution), first=None)  # 不在冷却期
        eng._create_execution = MagicMock(return_value=None)  # 模拟创建失败
        # 不抛 AttributeError；唯一规则创建失败 → 无匹配 → None
        result = eng.evaluate_alarm(make_alarm(level="critical"), db)
        assert result is None
        eng._create_execution.assert_called_once()

    def test_create_execution_failure_continues_to_next_rule(self):
        """缺陷1: 第一条规则 _create_execution 失败后 continue，仍尝试第二条规则。"""
        eng = fresh_engine()
        db = make_db()
        r1 = make_rule(rid=1, name="R1", alarm_pattern={"alarm_levels": ["critical"]},
                       auto_approve=False, priority=10)
        r2 = make_rule(rid=2, name="R2", alarm_pattern={"alarm_levels": ["critical"]},
                       auto_approve=False, priority=5)
        set_chain(chain_for(db, HealingRule), all_=[r1, r2], first=r1)
        set_chain(chain_for(db, HealingExecution), first=None)  # 不在冷却期
        created_ids = []

        def fake_create(rule, alarm, db):
            created_ids.append(rule.id)
            return None if rule.id == 1 else make_execution(eid=88)

        eng._create_execution = MagicMock(side_effect=fake_create)
        result = eng.evaluate_alarm(make_alarm(level="critical"), db)
        assert result is not None
        assert result["execution_id"] == 88
        assert result["status"] == "pending_approval"
        assert created_ids == [1, 2]  # r1 失败 → continue → r2 成功


# ═══════════════════════════════════════════════════════════
# execute_healing
# ═══════════════════════════════════════════════════════════

class TestExecuteHealing:
    def _setup(self, *, execution, alarm=None, device=None):
        eng = fresh_engine()
        db = make_db()
        set_chain(chain_for(db, HealingExecution), first=execution)
        set_chain(chain_for(db, Alarm), first=alarm)
        set_chain(chain_for(db, Device), first=device)
        return eng, db

    def test_execution_not_found(self):
        eng = fresh_engine()
        db = make_db()
        set_chain(chain_for(db, HealingExecution), first=None)
        res = eng.execute_healing(999, db=db)
        assert res == {"error": "执行记录#999不存在"}

    def test_alarm_not_found_marks_failed(self):
        ex = make_execution(eid=1, alarm_id=5)
        eng, db = self._setup(execution=ex, alarm=None, device=None)
        res = eng.execute_healing(1, db=db)
        assert res == {"error": "告警不存在"}
        assert ex.status == "failed"

    def test_device_not_found_marks_failed(self):
        ex = make_execution(eid=1, alarm_id=5)
        eng, db = self._setup(execution=ex, alarm=make_alarm(aid=5, device_id=10), device=None)
        res = eng.execute_healing(1, db=db)
        assert res == {"error": "设备不存在"}
        assert ex.status == "failed"

    def test_success_status(self):
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        eng, db = self._setup(execution=ex, alarm=make_alarm(aid=5, device_id=10),
                              device=make_device(did=10))
        eng._runbook_engine.execute.return_value = {
            "status": "success", "runbook_id": 9, "steps": [{"n": 1}],
            "total_duration_ms": 120, "success_steps": 3, "failed_steps": 0, "skipped_steps": 0,
        }
        res = eng.execute_healing(1, db=db)
        assert res["status"] == "success"
        assert ex.status == "success"
        assert ex.runbook_id == 9
        assert ex.success_steps == 3
        assert ex.completed_at is not None

    def test_partial_success_status(self):
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        eng, db = self._setup(execution=ex, alarm=make_alarm(aid=5, device_id=10),
                              device=make_device(did=10))
        eng._runbook_engine.execute.return_value = {
            "status": "failed", "success_steps": 2, "failed_steps": 1, "skipped_steps": 0,
            "total_duration_ms": 100, "runbook_id": 1, "steps": [],
        }
        res = eng.execute_healing(1, db=db)
        assert res["status"] == "partial_success"
        assert ex.status == "partial_success"

    def test_all_steps_failed(self):
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        eng, db = self._setup(execution=ex, alarm=make_alarm(aid=5, device_id=10),
                              device=make_device(did=10))
        eng._runbook_engine.execute.return_value = {
            "status": "failed", "success_steps": 0, "failed_steps": 3, "skipped_steps": 0,
            "total_duration_ms": 100, "runbook_id": 1, "steps": [],
        }
        res = eng.execute_healing(1, db=db)
        assert res["status"] == "failed"
        assert ex.status == "failed"

    def test_exception_marks_failed_and_returns_error(self):
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        eng, db = self._setup(execution=ex, alarm=make_alarm(aid=5, device_id=10),
                              device=make_device(did=10))
        eng._runbook_engine.execute.side_effect = RuntimeError("boom")
        res = eng.execute_healing(1, db=db)
        assert res["status"] == "failed"
        assert res["error"]  # cc2272b84: 底层异常脱敏为通用消息
        assert ex.status == "failed"
        assert ex.completed_at is not None


# ═══════════════════════════════════════════════════════════
# 审批 / 拒绝 / 重试
# ═══════════════════════════════════════════════════════════

class TestApproveRejectRetry:
    def test_approve_not_found(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingExecution), first=None)
        assert eng.approve_execution(9, "alice", db) == {"error": "执行记录#9不存在"}

    def test_approve_wrong_status(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingExecution), first=make_execution(status="success"))
        res = eng.approve_execution(1, "alice", db)
        assert "不可审批" in res["error"]

    def test_approve_success_runs_execute(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="pending_approval")
        set_chain(chain_for(db, HealingExecution), first=ex)
        eng.execute_healing = MagicMock(return_value={"status": "success"})
        res = eng.approve_execution(1, "alice", db)
        assert res == {"status": "success"}
        assert ex.status == "approved"
        assert ex.approved_by == "alice"
        eng.execute_healing.assert_called_once_with(1, db=db)

    def test_reject_success(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(status="pending_approval")
        set_chain(chain_for(db, HealingExecution), first=ex)
        res = eng.reject_execution(1, "bob", "误报", db)
        assert res["status"] == "rejected"
        assert ex.status == "rejected"
        assert ex.reject_reason == "误报"
        assert ex.approved_by == "bob"

    def test_reject_wrong_status(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingExecution), first=make_execution(status="success"))
        assert "不可拒绝" in eng.reject_execution(1, "bob", "x", db)["error"]

    def test_retry_exceeds_max(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(status="failed", retry_count=3)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, HealingRule), first=make_rule(max_retries=3))
        res = eng.retry_execution(1, db)
        assert "最大重试次数" in res["error"]

    def test_retry_success_runs_execute(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(status="failed", retry_count=1)
        # 新契约: retry 重试前查冷却 (HealingExecution 近期活跃记录)。
        # filter().first() 被消费两次: ① 取待重试 execution=ex ② 冷却检查=None(无活跃)。
        ex_chain = chain_for(db, HealingExecution)
        ex_chain.filter.return_value.first.side_effect = [ex, None]
        set_chain(chain_for(db, HealingRule), first=make_rule(max_retries=3))
        eng.execute_healing = MagicMock(return_value={"status": "success"})
        res = eng.retry_execution(1, db)
        assert res == {"status": "success"}
        assert ex.retry_count == 2
        assert ex.status == "approved"


# ═══════════════════════════════════════════════════════════
# 规则 CRUD
# ═══════════════════════════════════════════════════════════

class TestRuleCRUD:
    def test_create_rule(self):
        eng = fresh_engine(); db = make_db()
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 8)
        res = eng.create_rule({"name": "新规则", "alarm_pattern": {"alarm_levels": ["warning"]}}, db)
        assert res == {"id": 8, "name": "新规则", "message": "创建成功"}
        db.add.assert_called_once(); db.commit.assert_called_once()

    def test_update_rule_not_found(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingRule), first=None)
        assert eng.update_rule(1, {"name": "x"}, db) == {"error": "规则#1不存在"}

    def test_update_rule_success(self):
        eng = fresh_engine(); db = make_db()
        rule = make_rule(rid=2, name="旧")
        set_chain(chain_for(db, HealingRule), first=rule)
        res = eng.update_rule(2, {"name": "新", "priority": 99}, db)
        assert res["message"] == "更新成功"
        assert rule.name == "新"
        assert rule.priority == 99

    def test_delete_rule_blocked_by_active_executions(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingRule), first=make_rule(rid=1))
        set_chain(chain_for(db, HealingExecution), count=2)
        res = eng.delete_rule(1, db)
        assert "正在执行" in res["error"]
        db.delete.assert_not_called()

    def test_delete_rule_success(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingRule), first=make_rule(rid=1))
        set_chain(chain_for(db, HealingExecution), count=0)
        res = eng.delete_rule(1, db)
        assert res == {"message": "删除成功"}
        db.delete.assert_called_once()

    def test_list_rules_enabled_only_filter(self):
        eng = fresh_engine(); db = make_db()
        r1 = make_rule(rid=1, name="A", enabled=True, priority=5)
        set_chain(chain_for(db, HealingRule), all_=[r1])
        out = eng.list_rules(db, enabled_only=True)
        assert len(out) == 1
        assert out[0]["name"] == "A"
        assert out[0]["created_at"] == r1.created_at.isoformat()


# ═══════════════════════════════════════════════════════════
# 执行记录查询 / 统计
# ═══════════════════════════════════════════════════════════

class TestExecutionsAndStats:
    def test_list_executions_pagination_and_team_scoping(self):
        eng = fresh_engine(); db = make_db()
        e1 = make_execution(eid=1, station_id=100)
        set_chain(chain_for(db, HealingExecution), count=5, page_items=[e1])
        out = eng.list_executions(db, page=2, page_size=10, station_ids=[100, 200])
        assert out["total"] == 5
        assert out["page"] == 2
        assert out["page_size"] == 10
        assert len(out["items"]) == 1
        assert out["items"][0]["id"] == 1

    def test_get_execution_not_found(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingExecution), first=None)
        assert eng.get_execution(1, db) is None

    def test_get_execution_returns_detail(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=7, status="success")
        set_chain(chain_for(db, HealingExecution), first=ex)
        out = eng.get_execution(7, db)
        assert out["id"] == 7
        assert out["status"] == "success"
        assert out["approved_at"] is None  # isoformat 分支

    def test_get_stats_math(self):
        # get_stats 用 func.count/avg 作 query 目标, 单独用扁平 MagicMock
        eng = fresh_engine()
        db = MagicMock()
        db.query.return_value.scalar.return_value = 10                       # q1 total
        db.query.return_value.group_by.return_value.all.return_value = [
            ("success", 5), ("partial_success", 2), ("failed", 3)
        ]                                                                     # q2 状态分布
        db.query.return_value.filter.return_value.scalar.return_value = 3    # q3 avg & q4 auto_count
        stats = eng.get_stats(db)
        assert stats["total"] == 10
        assert stats["status_breakdown"] == {"success": 5, "partial_success": 2, "failed": 3}
        # success_count=7 → 70.0%
        assert stats["success_rate"] == 70.0
        assert stats["pending_approvals"] == 0
        # auto_count=3, total=10 → 30.0%
        assert stats["auto_approve_rate"] == 30.0


# ═══════════════════════════════════════════════════════════
# 自愈效果验证
# ═══════════════════════════════════════════════════════════

class TestVerifyHealing:
    def test_verify_not_found(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingExecution), first=None)
        assert eng.verify_healing_result(9, db) == {"error": "执行记录#9不存在"}

    def test_verify_wrong_status(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingExecution), first=make_execution(status="failed"))
        assert "不可验证" in eng.verify_healing_result(1, db)["error"]

    def test_verify_healed_when_alarm_cleared_and_device_online(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="success", alarm_id=5, device_id=10)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=make_alarm(aid=5, status="cleared"))
        set_chain(chain_for(db, Device), first=make_device(did=10, status="online"))
        res = eng.verify_healing_result(1, db)
        assert res["verification_result"] == "healed"
        assert res["alarm_cleared"] is True
        assert res["device_online"] is True
        assert ex.verified is True

    def test_verify_partial_when_only_one_condition(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="success", alarm_id=5, device_id=10)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=make_alarm(aid=5, status="active"))  # 未清除
        set_chain(chain_for(db, Device), first=make_device(did=10, status="online"))
        res = eng.verify_healing_result(1, db)
        assert res["verification_result"] == "partial"
        assert res["alarm_cleared"] is False
        assert res["device_online"] is True

    def test_verify_unhealed(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="partial_success", alarm_id=5, device_id=10)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=make_alarm(aid=5, status="active"))
        set_chain(chain_for(db, Device), first=make_device(did=10, status="offline"))
        res = eng.verify_healing_result(1, db)
        assert res["verification_result"] == "unhealed"

    def test_batch_verify_completed(self):
        eng = fresh_engine(); db = make_db()
        e1 = make_execution(eid=1); e2 = make_execution(eid=2)
        set_chain(chain_for(db, HealingExecution), all_=[e1, e2])
        eng.verify_healing_result = MagicMock(side_effect=[
            {"verification_result": "healed"},
            {"error": "执行记录#2不存在"},
        ])
        out = eng.batch_verify_completed(db, hours=24)
        assert out["total_verified"] == 2
        assert out["results"]["healed"] == 1
        assert out["results"]["errors"] == 1

    def test_batch_verify_completed_applies_limit(self):
        """次要: batch_verify_completed 必须应用 limit，避免全量加载。"""
        eng = fresh_engine(); db = make_db()
        chain = chain_for(db, HealingExecution)
        set_chain(chain, all_=[])
        eng.verify_healing_result = MagicMock()
        out = eng.batch_verify_completed(db, hours=24, limit=200)
        chain.filter.return_value.limit.assert_called_once_with(200)
        assert out["total_verified"] == 0


# ═══════════════════════════════════════════════════════════
# 冷却期时区一致性 (真实 SQLite session)
# ═══════════════════════════════════════════════════════════

class TestCooldownTimezoneConsistency:
    """缺陷3: _check_cooldown cutoff 与 created_at 时区一致性契约。

    背景: HealingExecution.created_at = server_default func.now() → SQLite 存 naive UTC。
    cutoff 须与之同形态(naive UTC)才稳健。固化契约: naive(func.now 写入)与
    aware(应用层写入)两种 created_at 都不抛错且判定正确。
    """

    def _make_rule(self, db):
        rule = HealingRule(
            name="TZ规则", alarm_pattern={"alarm_levels": ["critical"]},
            cooldown_minutes=30, enabled=True, priority=1,
        )
        db.add(rule); db.commit(); db.refresh(rule)
        return rule

    def _make_exec(self, db, rule, device_id, created_at):
        ex = HealingExecution(
            rule_id=rule.id, rule_name=rule.name, alarm_id=device_id,
            device_id=device_id, station_id=1, fault_type="x",
            status="success", steps=[],
        )
        ex.created_at = created_at
        db.add(ex); db.commit()
        return ex

    def test_recent_naive_created_at_is_in_cooldown(self, test_db):
        """naive created_at(func.now 风格, 5分钟前) → 在冷却期。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = self._make_rule(db)
        self._make_exec(db, rule, device_id=10,
                        created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5))
        assert eng._check_cooldown(rule.id, 10, db) is True

    def test_recent_aware_created_at_is_in_cooldown(self, test_db):
        """aware created_at(应用层写入, 5分钟前) → 在冷却期。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = self._make_rule(db)
        self._make_exec(db, rule, device_id=11,
                        created_at=datetime.now(timezone.utc) - timedelta(minutes=5))  # aware
        assert eng._check_cooldown(rule.id, 11, db) is True

    def test_old_naive_created_at_not_in_cooldown(self, test_db):
        """远期 naive created_at(2小时前) → 不在冷却期。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = self._make_rule(db)
        self._make_exec(db, rule, device_id=12,
                        created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2))
        assert eng._check_cooldown(rule.id, 12, db) is False

    def test_old_aware_created_at_not_in_cooldown(self, test_db):
        """远期 aware created_at(2小时前) → 不在冷却期。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = self._make_rule(db)
        self._make_exec(db, rule, device_id=13,
                        created_at=datetime.now(timezone.utc) - timedelta(hours=2))  # aware
        assert eng._check_cooldown(rule.id, 13, db) is False


# ═══════════════════════════════════════════════════════════
# 缺口1: _create_execution TOCTOU 自查 (真实 SQLite)
# ═══════════════════════════════════════════════════════════

class TestCreateExecutionTOCTOU:
    """缺口1: _check_cooldown 通过 → _create_execution 插入之间无锁无唯一约束。

    同 rule+device 并发告警风暴(自动链+手动 API 双入口)下, 两线程都过冷却检查 → 双执行
    记录; auto_approve 时同设备双 runbook 并行(重复重启/重复下发)。修复: 插入后立即自查,
    发现更早插入(id < 自身)的近期活跃记录则自判重复 → 删除自身并返回 None, evaluate_alarm
    据 None 跳过本规则, 最终只保留最早那条。
    """

    def test_revokes_when_earlier_active_execution_exists(self, test_db):
        """并发: 已有近期活跃 execution → 新插入者自判重复, 撤销, 库里只留 1 条。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = _persist_rule(db, cooldown_minutes=30)
        _persist_execution(db, rule, device_id=10, status="pending_approval", alarm_id=1)

        result = eng._create_execution(rule, _alarm_obj(device_id=10), db)

        assert result is None  # 自判重复 → 撤销
        cnt = db.query(HealingExecution).filter(HealingExecution.rule_id == rule.id).count()
        assert cnt == 1  # 只留最早那条

    def test_keeps_when_no_earlier_execution(self, test_db):
        """无并发: 无更早记录 → 正常创建, 库里 1 条。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = _persist_rule(db, cooldown_minutes=30)

        result = eng._create_execution(rule, _alarm_obj(device_id=10), db)

        assert result is not None
        assert result.id is not None
        cnt = db.query(HealingExecution).filter(HealingExecution.rule_id == rule.id).count()
        assert cnt == 1

    def test_not_revoked_when_earlier_outside_cooldown(self, test_db):
        """更早记录但在冷却窗外(2 小时前) → 不判重, 正常创建, 库里 2 条。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = _persist_rule(db, cooldown_minutes=30)
        old_dt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        _persist_execution(db, rule, device_id=10, status="success", created_at=old_dt)

        result = eng._create_execution(rule, _alarm_obj(device_id=10), db)

        assert result is not None
        cnt = db.query(HealingExecution).filter(HealingExecution.rule_id == rule.id).count()
        assert cnt == 2

    def test_not_revoked_when_earlier_is_failed(self, test_db):
        """更早记录但状态=failed(非活跃集) → 不判重, 正常创建。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = _persist_rule(db, cooldown_minutes=30)
        _persist_execution(db, rule, device_id=10, status="failed", alarm_id=1)

        result = eng._create_execution(rule, _alarm_obj(device_id=10), db)

        assert result is not None

    def test_zero_cooldown_skips_duplicate_check(self, test_db):
        """cooldown=0 → 不自查(与 _check_cooldown 短路一致), 即使有活跃记录也正常创建。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = _persist_rule(db, cooldown_minutes=0)
        _persist_execution(db, rule, device_id=10, status="pending_approval", alarm_id=1)

        result = eng._create_execution(rule, _alarm_obj(device_id=10), db)

        assert result is not None
        cnt = db.query(HealingExecution).filter(HealingExecution.rule_id == rule.id).count()
        assert cnt == 2  # 不判重 → 两条都保留


# ═══════════════════════════════════════════════════════════
# 缺口2: retry_execution 重试前必须查冷却
# ═══════════════════════════════════════════════════════════

class TestRetryCooldown:
    """缺口2: retry_execution 旧逻辑直接 approved+execute, 绕过 _check_cooldown。

    同 rule+device 若有活跃执行(如人工已审批在跑), 重试将与之并发 → 重复下发。修复:
    重试次数检查通过后再查冷却, 命中则返回 {"error":...} 不执行。
    """

    def test_retry_blocked_by_cooldown(self, test_db):
        """同 rule+device 有活跃 execution → 拦截重试, 不执行 runbook。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = _persist_rule(db, cooldown_minutes=30, max_retries=5)
        target = _persist_execution(db, rule, device_id=10, status="failed", alarm_id=1)
        target.retry_count = 1
        db.commit()
        # 同 rule+device 另一条活跃 execution → 触发冷却
        _persist_execution(db, rule, device_id=10, status="pending_approval", alarm_id=2)

        eng._runbook_engine = MagicMock()
        res = eng.retry_execution(target.id, db)

        assert "error" in res
        assert "冷却" in res["error"]
        eng._runbook_engine.execute.assert_not_called()

    def test_retry_passes_when_no_active_execution(self, test_db):
        """无其他活跃 execution(target 自身 failed 不计入活跃集) → 正常重试。"""
        db = test_db["session"]
        eng = fresh_engine()
        rule = _persist_rule(db, cooldown_minutes=30, max_retries=5)
        target = _persist_execution(db, rule, device_id=10, status="failed", alarm_id=1)
        target.retry_count = 1
        db.commit()

        eng.execute_healing = MagicMock(return_value={"status": "success"})
        res = eng.retry_execution(target.id, db)

        assert res == {"status": "success"}
        eng.execute_healing.assert_called_once()


# ═══════════════════════════════════════════════════════════
# 缺口3: execute_healing 最终状态判定优先尊重 status==failed
# ═══════════════════════════════════════════════════════════

class TestExecuteHealingStatusDecision:
    """缺口3: 旧判定 `status==failed and success==0 → failed`, 其余落到 else=success。

    漏洞: runbook 返回 status==failed + success_steps>0 + failed_steps==0 时,
    第一分支不满足(success≠0), 第二分支不满足(failed==0), 落入 else → 记 success。
    修复: 有失败步骤且有成功步骤才 partial; 否则 status==failed → failed (尊重信号)。
    """

    def _run_with(self, rb_result):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=make_alarm(aid=5, device_id=10))
        set_chain(chain_for(db, Device), first=make_device(did=10))
        eng._runbook_engine.execute.return_value = rb_result
        eng.execute_healing(1, db=db)
        return ex

    def test_failed_status_with_success_but_zero_failed_is_failed(self):
        """漏洞用例: status=failed + success=2 + failed=0 → 旧逻辑误判 success, 修复后 failed。"""
        ex = self._run_with({
            "status": "failed", "success_steps": 2, "failed_steps": 0,
            "total_duration_ms": 50, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        })
        assert ex.status == "failed"

    def test_failed_status_all_zero_is_failed(self):
        """status=failed + success=0 + failed=0 → failed (runbook 级失败, 无步骤统计)。"""
        ex = self._run_with({
            "status": "failed", "success_steps": 0, "failed_steps": 0,
            "total_duration_ms": 50, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        })
        assert ex.status == "failed"


# ═══════════════════════════════════════════════════════════
# 缺口4: create_rule / update_rule 服务层输入校验
# ═══════════════════════════════════════════════════════════

class TestRuleValidation:
    """缺口4: 服务层零输入校验。

    router Pydantic 仅约束 HTTP 入口; alarm_rule_service 自愈链等内部/直调路径绕过 Pydantic,
    缺 name/alarm_pattern → KeyError 被吞成 500; 负数/非数值/max_retries 等被直接 setattr。
    服务层兜底校验, 返回 {"error":...} 由 router 映射 400。
    """

    _VALID = {"name": "R", "alarm_pattern": {"alarm_levels": ["critical"]}}

    def test_create_rule_missing_name(self):
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({"alarm_pattern": {"alarm_levels": ["critical"]}}, db)
        assert "error" in res and "名称" in res["error"]
        db.add.assert_not_called()

    def test_create_rule_blank_name(self):
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({"name": "  ", "alarm_pattern": {"alarm_levels": ["critical"]}}, db)
        assert "error" in res
        db.add.assert_not_called()

    def test_create_rule_missing_alarm_pattern(self):
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({"name": "R"}, db)
        assert "error" in res
        db.add.assert_not_called()

    def test_create_rule_empty_alarm_pattern(self):
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({"name": "R", "alarm_pattern": {}}, db)
        assert "error" in res
        db.add.assert_not_called()

    def test_create_rule_negative_max_retries(self):
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({**self._VALID, "max_retries": -1}, db)
        assert "error" in res and "max_retries" in res["error"]
        db.add.assert_not_called()

    def test_create_rule_negative_cooldown(self):
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({**self._VALID, "cooldown_minutes": -5}, db)
        assert "error" in res and "cooldown_minutes" in res["error"]

    def test_create_rule_negative_priority(self):
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({**self._VALID, "priority": -1}, db)
        assert "error" in res and "priority" in res["error"]

    def test_create_rule_non_int_max_retries(self):
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({**self._VALID, "max_retries": "abc"}, db)
        assert "error" in res
        db.add.assert_not_called()

    def test_create_rule_non_int_cooldown(self):
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({**self._VALID, "cooldown_minutes": "x"}, db)
        assert "error" in res

    def test_create_rule_bool_not_accepted_as_int(self):
        """bool 是 int 子类, 但作为 max_retries 应拒绝(语义错误)。"""
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({**self._VALID, "max_retries": True}, db)
        assert "error" in res

    def test_create_rule_non_bool_auto_approve(self):
        eng = fresh_engine(); db = make_db()
        res = eng.create_rule({**self._VALID, "auto_approve": "yes"}, db)
        assert "error" in res

    def test_create_rule_valid_passes(self):
        eng = fresh_engine(); db = make_db()
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 9)
        res = eng.create_rule({**self._VALID, "max_retries": 0, "priority": 0}, db)
        assert res.get("id") == 9

    def test_update_rule_not_found_passthrough(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingRule), first=None)
        assert eng.update_rule(1, {"name": "x"}, db) == {"error": "规则#1不存在"}

    def test_update_rule_negative_max_retries(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingRule), first=make_rule(rid=1))
        res = eng.update_rule(1, {"max_retries": -1}, db)
        assert "error" in res and "max_retries" in res["error"]
        db.commit.assert_not_called()

    def test_update_rule_negative_priority(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingRule), first=make_rule(rid=1))
        res = eng.update_rule(1, {"priority": -2}, db)
        assert "error" in res
        db.commit.assert_not_called()

    def test_update_rule_non_bool_auto_approve(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingRule), first=make_rule(rid=1))
        res = eng.update_rule(1, {"auto_approve": 1}, db)
        assert "error" in res
        db.commit.assert_not_called()

    def test_update_rule_empty_name_rejected(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingRule), first=make_rule(rid=1))
        res = eng.update_rule(1, {"name": ""}, db)
        assert "error" in res
        db.commit.assert_not_called()


# ═══════════════════════════════════════════════════════════
# 缺口5: 时间戳统一 naive-UTC 写入
# ═══════════════════════════════════════════════════════════

class TestTimestampTimezone:
    """缺口5: approved_at/started_at/completed_at 旧写 aware(datetime.now(timezone.utc)),
    而 _check_cooldown / batch_verify 的 cutoff 用 .replace(tzinfo=None) (naive)。

    SQLite 下 created_at=func.now() 实存 naive UTC; aware 写入与之混用会导致冷却/批量验证的
    cutoff 比较错位。统一为 naive-UTC 写入 (与 created_at 对齐)。
    """

    def test_execute_healing_writes_naive_started_and_completed(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=make_alarm(aid=5, device_id=10))
        set_chain(chain_for(db, Device), first=make_device(did=10))
        eng._runbook_engine.execute.return_value = {
            "status": "success", "success_steps": 1, "failed_steps": 0,
            "total_duration_ms": 10, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        }
        eng.execute_healing(1, db=db)
        assert ex.started_at is not None and ex.started_at.tzinfo is None
        assert ex.completed_at is not None and ex.completed_at.tzinfo is None

    def test_execute_healing_failure_path_writes_naive_completed(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=make_alarm(aid=5, device_id=10))
        set_chain(chain_for(db, Device), first=make_device(did=10))
        eng._runbook_engine.execute.side_effect = RuntimeError("boom")
        eng.execute_healing(1, db=db)
        assert ex.completed_at is not None and ex.completed_at.tzinfo is None

    def test_execute_auto_writes_naive_approved_at(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1)
        eng.execute_healing = MagicMock(return_value={"status": "success"})
        eng._execute_auto(ex, make_alarm(aid=1), make_rule(rid=1), db)
        assert ex.approved_at is not None and ex.approved_at.tzinfo is None

    def test_approve_writes_naive_approved_at(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="pending_approval")
        set_chain(chain_for(db, HealingExecution), first=ex)
        eng.execute_healing = MagicMock(return_value={"status": "success"})
        eng.approve_execution(1, "alice", db)
        assert ex.approved_at is not None and ex.approved_at.tzinfo is None

    def test_reject_writes_naive_completed_at(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="pending_approval")
        set_chain(chain_for(db, HealingExecution), first=ex)
        eng.reject_execution(1, "bob", "误报", db)
        assert ex.completed_at is not None and ex.completed_at.tzinfo is None
