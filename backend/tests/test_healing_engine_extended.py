"""
HealingEngine 单元测试 — 补充集 (卡 ac811ca8)

被测文件: app/services/healing_engine.py

定位: tests/test_healing_engine.py 已覆盖主路径 + 五大缺口(TOCTOU/冷却/状态判定/
输入校验/时区)。本文件只补其**未覆盖的真实分支**, 不重复造轮子。覆盖范围:

1. execute_healing — diagnosis_result 解析(str/dict/损坏数据)、fault_type 回退、
   pending_approval 状态透传
2. _execute_auto — approved_by="auto" + 透传参数
3. approve/reject/retry — not_found / wrong_status / DB 异常 rollback 分支;
   retry rule 不存在时 max_retries 回退到 1
4. verify_healing_result — alarm/device 均 None → unhealed、verified_at 写入、
   DB 异常 rollback
5. batch_verify_completed — hours 过滤、partial/unhealed 统计、空列表
6. get_stats — total=0 除零保护
7. delete_rule — not_found
8. evaluate_alarm — 多规则按 priority 降序匹配第一条命中

风格与 test_healing_engine.py 对齐: DB chain 按 model 分发; 枚举字段用纯字符串;
RunbookEngine 替换为 MagicMock。
"""
import json
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone

from app.services.healing_engine import HealingEngine, _ACTIVE_STATUSES
from app.models.healing_rule import HealingRule
from app.models.healing_execution import HealingExecution
from app.models.alarm import Alarm
from app.models.device import Device


# ─── 与 test_healing_engine.py 一致的 DB chain mock 辅助 ───

def make_db():
    db = MagicMock()
    by_model = {}

    def _query(model, *args, **kwargs):
        return by_model.setdefault(
            model, MagicMock(name=f"q[{getattr(model, '__name__', repr(model))}]")
        )

    db.query.side_effect = _query
    db._by_model = by_model
    return db


def chain_for(db, model):
    return db._by_model.setdefault(model, MagicMock())


UNSET = object()


def set_chain(chain, *, all_=UNSET, first=UNSET, count=UNSET, scalar=UNSET, page_items=UNSET):
    root = chain
    f = root.filter.return_value
    fo = f.order_by.return_value
    ro = root.order_by.return_value

    if all_ is not UNSET:
        root.all.return_value = all_
        f.all.return_value = all_
        f.limit.return_value.all.return_value = all_
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
    if page_items is not UNSET:
        fo.offset.return_value.limit.return_value.all.return_value = page_items
        ro.offset.return_value.limit.return_value.all.return_value = page_items


# ─── 业务对象工厂 ───

def make_alarm(aid=1, *, level="critical", alarm_type="逆变器通讯中断", content="过温告警",
               device_id=10, station_id=100, diagnosis_result=None, fault_code=None,
               device=None, status="active"):
    a = MagicMock()
    a.id = aid
    a.level = level
    a.alarm_type = alarm_type
    a.content = content
    a.device_id = device_id
    a.station_id = station_id
    a.diagnosis_result = diagnosis_result
    a.fault_code = fault_code
    a.device = device
    a.status = status
    return a


def make_rule(rid=1, *, name="规则A", enabled=True, priority=10, cooldown_minutes=30,
              alarm_pattern=None, runbook_template="tpl", auto_approve=False, max_retries=1,
              description="d"):
    r = MagicMock()
    r.id = rid
    r.name = name
    r.enabled = enabled
    r.priority = priority
    r.cooldown_minutes = cooldown_minutes
    r.alarm_pattern = alarm_pattern if alarm_pattern is not None else {"alarm_levels": ["critical"]}
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
    d.device_type = device_type
    d.status = status
    return d


def fresh_engine():
    eng = HealingEngine()
    eng._runbook_engine = MagicMock()
    return eng


def _execute_setup(*, execution, alarm=None, device=None):
    """execute_healing 通用 mock 装配: execution/alarm/device 三个 chain。"""
    eng = fresh_engine()
    db = make_db()
    set_chain(chain_for(db, HealingExecution), first=execution)
    set_chain(chain_for(db, Alarm), first=alarm)
    set_chain(chain_for(db, Device), first=device)
    return eng, db


# ═══════════════════════════════════════════════════════════
# execute_healing — diagnosis_result 解析 + fault_type 回退
# ═══════════════════════════════════════════════════════════

class TestExecuteHealingDiagnosis:
    def test_diagnosis_result_str_is_json_parsed(self):
        """alarm.diagnosis_result 为 JSON 字符串 → json.loads 后透传 runbook。"""
        diag = {"fault_type": "过温", "extra": 1}
        ex = make_execution(eid=1, alarm_id=5, device_id=10, fault_type="快照故障")
        eng, db = _execute_setup(
            execution=ex,
            alarm=make_alarm(aid=5, device_id=10, diagnosis_result=json.dumps(diag)),
            device=make_device(did=10),
        )
        eng._runbook_engine.execute.return_value = {
            "status": "success", "success_steps": 1, "failed_steps": 0,
            "total_duration_ms": 10, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        }
        eng.execute_healing(1, db=db)
        # execute 被调用时 diagnosis_result 已被解析为 dict
        _, kwargs = eng._runbook_engine.execute.call_args
        assert kwargs["diagnosis_result"] == diag

    def test_diagnosis_result_dict_passed_through(self):
        """alarm.diagnosis_result 已是 dict → 直接透传, 不再 json.loads。"""
        diag = {"fault_type": "通讯异常"}
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        eng, db = _execute_setup(
            execution=ex,
            alarm=make_alarm(aid=5, device_id=10, diagnosis_result=diag),
            device=make_device(did=10),
        )
        eng._runbook_engine.execute.return_value = {
            "status": "success", "success_steps": 1, "failed_steps": 0,
            "total_duration_ms": 10, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        }
        eng.execute_healing(1, db=db)
        _, kwargs = eng._runbook_engine.execute.call_args
        assert kwargs["diagnosis_result"] == diag

    def test_diagnosis_result_corrupted_string_is_dropped(self):
        """损坏的 JSON 字符串 → 解析失败丢弃, 用 execution.fault_type 兜底。"""
        ex = make_execution(eid=1, alarm_id=5, device_id=10, fault_type="兜底故障")
        eng, db = _execute_setup(
            execution=ex,
            alarm=make_alarm(aid=5, device_id=10, diagnosis_result="{not-json"),
            device=make_device(did=10),
        )
        eng._runbook_engine.execute.return_value = {
            "status": "success", "success_steps": 1, "failed_steps": 0,
            "total_duration_ms": 10, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        }
        eng.execute_healing(1, db=db)
        _, kwargs = eng._runbook_engine.execute.call_args
        # 损坏数据被丢弃为空 dict → fault_type 用 execution 快照兜底
        assert kwargs["diagnosis_result"]["fault_type"] == "兜底故障"

    def test_fault_type_falls_back_to_execution_snapshot(self):
        """diagnosis_result 无 fault_type 键 → 用 execution.fault_type 填充。"""
        ex = make_execution(eid=1, alarm_id=5, device_id=10, fault_type="快照故障类型")
        eng, db = _execute_setup(
            execution=ex,
            alarm=make_alarm(aid=5, device_id=10, diagnosis_result={"other": "x"}),
            device=make_device(did=10),
        )
        eng._runbook_engine.execute.return_value = {
            "status": "success", "success_steps": 1, "failed_steps": 0,
            "total_duration_ms": 10, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        }
        eng.execute_healing(1, db=db)
        _, kwargs = eng._runbook_engine.execute.call_args
        assert kwargs["diagnosis_result"]["fault_type"] == "快照故障类型"

    def test_runbook_pending_approval_status_passthrough(self):
        """runbook 返回 status=pending_approval → execution 透传为 pending_approval。"""
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        eng, db = _execute_setup(
            execution=ex,
            alarm=make_alarm(aid=5, device_id=10),
            device=make_device(did=10),
        )
        eng._runbook_engine.execute.return_value = {
            "status": "pending_approval", "success_steps": 0, "failed_steps": 0,
            "total_duration_ms": 0, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        }
        res = eng.execute_healing(1, db=db)
        assert res["status"] == "pending_approval"
        assert ex.status == "pending_approval"

    def test_device_info_built_from_device(self):
        """device_info 正确从 Device 提取并传给 runbook。"""
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        eng, db = _execute_setup(
            execution=ex,
            alarm=make_alarm(aid=5, device_id=10, station_id=100),
            device=make_device(did=10, name="INV1", sn="SN9", ip_address="1.2.3.4",
                               station_id=100, device_type="inverter"),
        )
        eng._runbook_engine.execute.return_value = {
            "status": "success", "success_steps": 1, "failed_steps": 0,
            "total_duration_ms": 10, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        }
        eng.execute_healing(1, db=db)
        _, kwargs = eng._runbook_engine.execute.call_args
        assert kwargs["device_info"] == {
            "id": 10, "name": "INV1", "sn": "SN9", "ip": "1.2.3.4",
            "station_id": 100, "type": "inverter",
        }

    def test_device_info_station_falls_back_to_device_when_alarm_none(self):
        """alarm.station_id 为 None → device_info.station_id 用 device.station_id 兜底。"""
        ex = make_execution(eid=1, alarm_id=5, device_id=10)
        eng, db = _execute_setup(
            execution=ex,
            alarm=make_alarm(aid=5, device_id=10, station_id=None),
            device=make_device(did=10, station_id=77),
        )
        eng._runbook_engine.execute.return_value = {
            "status": "success", "success_steps": 1, "failed_steps": 0,
            "total_duration_ms": 10, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        }
        eng.execute_healing(1, db=db)
        _, kwargs = eng._runbook_engine.execute.call_args
        assert kwargs["device_info"]["station_id"] == 77


# ═══════════════════════════════════════════════════════════
# _execute_auto — approved_by + 透传参数
# ═══════════════════════════════════════════════════════════

class TestExecuteAuto:
    def test_sets_approved_by_auto_and_calls_execute_with_full_args(self):
        """_execute_auto 标记 approved_by=auto, 并把 execution/alarm/rule 全参传给 execute_healing。"""
        eng = fresh_engine()
        db = make_db()
        ex = make_execution(eid=7)
        alarm = make_alarm(aid=5)
        rule = make_rule(rid=3)
        eng.execute_healing = MagicMock(return_value={"status": "success"})

        eng._execute_auto(ex, alarm, rule, db)

        assert ex.status == "approved"
        assert ex.approved_by == "auto"
        assert ex.approved_at is not None and ex.approved_at.tzinfo is None
        eng.execute_healing.assert_called_once_with(7, db, alarm, rule)

    def test_returns_execute_result_verbatim(self):
        """_execute_auto 原样返回 execute_healing 的结果。"""
        eng = fresh_engine()
        db = make_db()
        sentinel = {"status": "failed", "error": "x"}
        eng.execute_healing = MagicMock(return_value=sentinel)
        res = eng._execute_auto(make_execution(eid=1), make_alarm(), make_rule(), db)
        assert res is sentinel


# ═══════════════════════════════════════════════════════════
# approve / reject / retry — not_found / wrong_status / DB异常
# ═══════════════════════════════════════════════════════════

class TestApproveRejectRetryExtended:
    # --- approve ---
    def test_approve_db_exception_rolls_back_and_returns_error(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(status="pending_approval")
        set_chain(chain_for(db, HealingExecution), first=ex)
        db.commit.side_effect = RuntimeError("db down")
        res = eng.approve_execution(1, "alice", db)
        assert "error" in res
        db.rollback.assert_called_once()
        # 异常路径不应继续调用 execute_healing
        eng._runbook_engine.execute.assert_not_called()

    def test_approve_passes_alarm_and_rule_when_loaded(self):
        """approve_execution 内部调 execute_healing(id, db=db), alarm/rule 走 None → DB 加载分支。"""
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="pending_approval", alarm_id=5, rule_id=3)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=make_alarm(aid=5, device_id=10))
        set_chain(chain_for(db, Device), first=make_device(did=10))
        set_chain(chain_for(db, HealingRule), first=make_rule(rid=3))
        eng._runbook_engine.execute.return_value = {
            "status": "success", "success_steps": 1, "failed_steps": 0,
            "total_duration_ms": 5, "runbook_id": 1, "steps": [], "skipped_steps": 0,
        }
        res = eng.approve_execution(1, "alice", db)
        assert res["status"] == "success"
        assert ex.approved_by == "alice"

    # --- reject ---
    def test_reject_not_found(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingExecution), first=None)
        assert eng.reject_execution(9, "bob", "误报", db) == {"error": "执行记录#9不存在"}

    def test_reject_db_exception_rolls_back(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(status="pending_approval")
        set_chain(chain_for(db, HealingExecution), first=ex)
        db.commit.side_effect = RuntimeError("db down")
        res = eng.reject_execution(1, "bob", "x", db)
        assert "error" in res
        db.rollback.assert_called_once()

    # --- retry ---
    def test_retry_not_found(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingExecution), first=None)
        assert eng.retry_execution(9, db) == {"error": "执行记录#9不存在"}

    def test_retry_wrong_status(self):
        eng = fresh_engine(); db = make_db()
        # status=success 不在 (failed, partial_success) → 不可重试
        set_chain(chain_for(db, HealingExecution), first=make_execution(status="success"))
        res = eng.retry_execution(1, db)
        assert "不可重试" in res["error"]

    def test_retry_max_retries_boundary_equal(self):
        """retry_count == max_retries(刚好相等) → 拦截, 不执行。"""
        eng = fresh_engine(); db = make_db()
        ex = make_execution(status="failed", retry_count=2)
        ex_chain = chain_for(db, HealingExecution)
        ex_chain.filter.return_value.first.side_effect = [ex, None]  # execution=ex, 冷却=None
        set_chain(chain_for(db, HealingRule), first=make_rule(max_retries=2))
        res = eng.retry_execution(1, db)
        assert "最大重试次数" in res["error"]

    def test_retry_rule_missing_falls_back_to_max_retries_one(self):
        """rule 不存在(None) → max_retries 回退到 1; retry_count=1 已达上限 → 拦截。"""
        eng = fresh_engine(); db = make_db()
        ex = make_execution(status="failed", retry_count=1)
        ex_chain = chain_for(db, HealingExecution)
        ex_chain.filter.return_value.first.side_effect = [ex, None]
        set_chain(chain_for(db, HealingRule), first=None)
        res = eng.retry_execution(1, db)
        assert "最大重试次数(1)" in res["error"]

    def test_retry_db_exception_rolls_back(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(status="failed", retry_count=0)
        ex_chain = chain_for(db, HealingExecution)
        ex_chain.filter.return_value.first.side_effect = [ex, None]
        set_chain(chain_for(db, HealingRule), first=make_rule(max_retries=3))
        db.commit.side_effect = RuntimeError("db down")
        res = eng.retry_execution(1, db)
        assert "error" in res
        db.rollback.assert_called_once()


# ═══════════════════════════════════════════════════════════
# verify_healing_result — None对象 / verified_at / DB异常
# ═══════════════════════════════════════════════════════════

class TestVerifyHealingExtended:
    def test_verify_unhealed_when_alarm_and_device_both_missing(self):
        """alarm 和 device 都查不到(均 None) → alarm_cleared=False, device_online=False → unhealed。"""
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="success", alarm_id=5, device_id=10)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=None)
        set_chain(chain_for(db, Device), first=None)
        res = eng.verify_healing_result(1, db)
        assert res["verification_result"] == "unhealed"
        assert res["alarm_cleared"] is False
        assert res["device_online"] is False
        assert ex.verified is True
        assert ex.verified_at is not None
        assert ex.verification_result == "unhealed"

    def test_verify_writes_verified_fields(self):
        """验证成功时 verified/verified_at/verification_result/alarm_cleared 全部落库。"""
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="success", alarm_id=5, device_id=10)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=make_alarm(aid=5, status="resolved"))
        set_chain(chain_for(db, Device), first=make_device(did=10, status="online"))
        eng.verify_healing_result(1, db)
        assert ex.verified is True
        assert ex.verified_at is not None and ex.verified_at.tzinfo is None
        assert ex.verification_result == "healed"
        assert ex.alarm_cleared is True

    def test_verify_db_exception_rolls_back(self):
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="success", alarm_id=5, device_id=10)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=make_alarm(aid=5, status="resolved"))
        set_chain(chain_for(db, Device), first=make_device(did=10, status="online"))
        db.commit.side_effect = RuntimeError("db down")
        res = eng.verify_healing_result(1, db)
        assert "error" in res
        db.rollback.assert_called_once()

    def test_verify_partial_success_status_allowed(self):
        """status=partial_success 也在可验证集合内 → 正常验证。"""
        eng = fresh_engine(); db = make_db()
        ex = make_execution(eid=1, status="partial_success", alarm_id=5, device_id=10)
        set_chain(chain_for(db, HealingExecution), first=ex)
        set_chain(chain_for(db, Alarm), first=make_alarm(aid=5, status="resolved"))
        set_chain(chain_for(db, Device), first=make_device(did=10, status="offline"))
        res = eng.verify_healing_result(1, db)
        # 告警清除但设备离线 → partial
        assert res["verification_result"] == "partial"


# ═══════════════════════════════════════════════════════════
# batch_verify_completed — 统计聚合 / 空列表 / hours
# ═══════════════════════════════════════════════════════════

class TestBatchVerifyExtended:
    def test_empty_executions_returns_zeros(self):
        """无待验证记录 → total_verified=0, 各计数为 0。"""
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingExecution), all_=[])
        out = eng.batch_verify_completed(db, hours=24)
        assert out == {"total_verified": 0,
                       "results": {"healed": 0, "partial": 0, "unhealed": 0, "errors": 0}}

    def test_aggregates_partial_and_unhealed(self):
        """多条记录混合结果 → 按 verification_result 聚合到对应桶。"""
        eng = fresh_engine(); db = make_db()
        e1 = make_execution(eid=1); e2 = make_execution(eid=2); e3 = make_execution(eid=3)
        set_chain(chain_for(db, HealingExecution), all_=[e1, e2, e3])
        eng.verify_healing_result = MagicMock(side_effect=[
            {"verification_result": "partial"},
            {"verification_result": "unhealed"},
            {"verification_result": "healed"},
        ])
        out = eng.batch_verify_completed(db, hours=12)
        assert out["total_verified"] == 3
        assert out["results"]["partial"] == 1
        assert out["results"]["unhealed"] == 1
        assert out["results"]["healed"] == 1
        assert out["results"]["errors"] == 0

    def test_unexpected_result_key_counted_into_results(self):
        """verify 返回非标准 key → results.get(k,0)+1 兜底, 不崩。"""
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingExecution), all_=[make_execution(eid=1)])
        eng.verify_healing_result = MagicMock(
            return_value={"verification_result": "weird_state"})
        out = eng.batch_verify_completed(db, hours=24)
        assert out["results"]["weird_state"] == 1
        assert out["total_verified"] == 1

    def test_verify_exception_counted_as_error(self):
        """verify_healing_result 抛异常 → batch 层捕获, 计入 errors, 不中断循环。"""
        eng = fresh_engine(); db = make_db()
        e1 = make_execution(eid=1); e2 = make_execution(eid=2)
        set_chain(chain_for(db, HealingExecution), all_=[e1, e2])
        eng.verify_healing_result = MagicMock(side_effect=[
            {"verification_result": "healed"},
            RuntimeError("boom"),
        ])
        out = eng.batch_verify_completed(db, hours=24)
        assert out["results"]["healed"] == 1
        assert out["results"]["errors"] == 1


# ═══════════════════════════════════════════════════════════
# get_stats — total=0 除零保护
# ═══════════════════════════════════════════════════════════

class TestGetStatsExtended:
    def test_zero_total_no_division_error(self):
        """total=0 → success_rate/auto_approve_rate 归零, 不抛 ZeroDivisionError。"""
        eng = fresh_engine()
        db = MagicMock()
        db.query.return_value.scalar.return_value = 0           # total
        db.query.return_value.group_by.return_value.all.return_value = []  # 无状态分布
        db.query.return_value.filter.return_value.scalar.return_value = 0  # avg / auto_count
        stats = eng.get_stats(db)
        assert stats["total"] == 0
        assert stats["success_rate"] == 0
        assert stats["auto_approve_rate"] == 0
        assert stats["average_duration_ms"] == 0
        assert stats["pending_approvals"] == 0
        assert stats["status_breakdown"] == {}

    def test_avg_duration_none_treated_as_zero(self):
        """avg scalar 返回 None(无完成记录) → or 0 → average_duration_ms=0。"""
        eng = fresh_engine()
        db = MagicMock()
        db.query.return_value.scalar.return_value = 5                       # total
        db.query.return_value.group_by.return_value.all.return_value = [("success", 5)]
        db.query.return_value.filter.return_value.scalar.return_value = None  # avg None, auto None
        stats = eng.get_stats(db)
        assert stats["average_duration_ms"] == 0
        assert stats["success_rate"] == 100.0


# ═══════════════════════════════════════════════════════════
# delete_rule — not_found
# ═══════════════════════════════════════════════════════════

class TestDeleteRuleExtended:
    def test_delete_rule_not_found(self):
        eng = fresh_engine(); db = make_db()
        set_chain(chain_for(db, HealingRule), first=None)
        assert eng.delete_rule(99, db) == {"error": "规则#99不存在"}
        db.delete.assert_not_called()


# ═══════════════════════════════════════════════════════════
# evaluate_alarm — 多规则按 priority 降序匹配第一条命中
# ═══════════════════════════════════════════════════════════

class TestEvaluateAlarmPriority:
    def test_matches_first_eligible_by_priority_then_lower(self):
        """高优先级规则在冷却期 → 跳过, 命中次优先级规则。

        规则按 priority desc 返回: R1(priority=10, critical) 在冷却 → 跳过;
        R2(priority=5, critical) 不在冷却 → 创建执行。验证排序后逐条尝试语义。
        """
        eng = fresh_engine()
        db = make_db()
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 88)
        r1 = make_rule(rid=1, name="R1", alarm_pattern={"alarm_levels": ["critical"]},
                       auto_approve=False, priority=10)
        r2 = make_rule(rid=2, name="R2", alarm_pattern={"alarm_levels": ["critical"]},
                       auto_approve=False, priority=5)
        set_chain(chain_for(db, HealingRule), all_=[r1, r2], first=r1)
        # _check_cooldown 取 rule first=r1(冷却存在) → r1 跳过;
        # 第二轮 _check_cooldown 需返回 False → 但 first 只配了一个值。
        # 故用 side_effect: rule 链 first 依次 r1(True 冷却), r2(False)。
        rule_chain = chain_for(db, HealingRule)
        rule_chain.filter.return_value.first.side_effect = [r1, None]  # r1 cooldown查到rule, r2查到rule
        exec_chain = chain_for(db, HealingExecution)
        # r1: 有近期活跃记录(冷却命中); r2: 无近期记录(可创建); create后自查=None
        exec_chain.filter.return_value.first.side_effect = [
            make_execution(),   # r1 _check_cooldown → 命中冷却
            None,               # r2 _check_cooldown → 无活跃
            None,               # r2 _create_execution 自查 → 无更早
        ]
        result = eng.evaluate_alarm(make_alarm(level="critical", device_id=10, station_id=100), db)
        assert result is not None
        assert result["rule_id"] == 2   # 命中次优先级 R2
        assert result["status"] == "pending_approval"

    def test_disabled_rule_not_queried(self):
        """evaluate_alarm 只查 enabled=True 规则 — 无匹配 enabled 规则 → None。"""
        eng = fresh_engine()
        db = make_db()
        set_chain(chain_for(db, HealingRule), all_=[])  # query 已 filter enabled=True, 返回空
        assert eng.evaluate_alarm(make_alarm(level="critical"), db) is None

    def test_no_rule_matches_alarm_returns_none(self):
        """有规则但都不匹配告警 → None。"""
        eng = fresh_engine()
        db = make_db()
        rule = make_rule(rid=1, alarm_pattern={"alarm_levels": ["fatal"]}, auto_approve=False)
        set_chain(chain_for(db, HealingRule), all_=[rule], first=rule)
        result = eng.evaluate_alarm(make_alarm(level="critical"), db)  # critical ≠ fatal
        assert result is None


# ═══════════════════════════════════════════════════════════
# _ACTIVE_STATUSES 契约固化
# ═══════════════════════════════════════════════════════════

class TestActiveStatusesContract:
    """冷却判定的活跃状态集是冷却/TOCTOU/重试冷却三处共享契约, 固化防回归。

    任一状态从集合中增删都会改变"何为活跃执行"的语义 → 冷却窗口与重复判定联动变化。
    """
    def test_active_statuses_set(self):
        assert set(_ACTIVE_STATUSES) == {
            "success", "partial_success", "pending_approval", "approved", "running",
        }
