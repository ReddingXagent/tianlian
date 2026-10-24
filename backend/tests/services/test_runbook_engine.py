#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runbook 引擎服务测试 — 覆盖率 69% → 85%+

覆盖范围:
- shell 注入防御 (validate_shell_command / safe_command_list)
- 模板匹配 (精确/模糊/设备类型兜底/默认模板)
- 别名方法 (approve_runbook / execute_runbook_step / get_runbook_templates)
- execute 主流程 (dry_run / 审批工作流 / 无DB降级 / 最终状态判定)
- _match_template_db (精确/模糊/category/import失败/未命中)
- _run_command (trusted/non-trusted 通道)
- _execute_step (各 action_type 分支 / 前置检查 / 回滚 / 超时 / 异常)
- 人工步骤处理 + 通知发送 (ImportError 回退 / 成功 / 异常)
- 工单创建 / 执行记录保存 (成功 + 失败)
- 变量替换 (command/rollback/pre_check/post_check)
- 便捷函数 execute_runbook_for_alarm
"""
import sys
import subprocess
from unittest.mock import MagicMock

import pytest

from app.services.runbook_engine import (
    RunbookEngine,
    RunbookTemplate,
    RunbookStep,
    RunbookExecution,
    RunbookStatus,
    RunbookActionType,
    RiskLevel,
    execute_runbook_for_alarm,
    validate_shell_command,
    safe_command_list,
)


def _cp(returncode=0, stdout="", stderr=""):
    """构造 subprocess.CompletedProcess，供 patch _run_command 返回。"""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _BoomDB:
    """commit 必炸的假 DB，用于触发 _save_execution / _create_workorder 的异常分支。"""

    def add(self, *a, **kw):
        pass

    def commit(self):
        raise RuntimeError("db boom")

    def rollback(self):
        pass

    def refresh(self, *a, **kw):
        pass


# ========== 基础冒烟测试（保留原有） ==========

class TestRunbookEngineBasics:
    def test_engine_initialization(self):
        assert RunbookEngine() is not None
        assert RunbookEngine(dry_run=True).dry_run is True

    def test_has_methods(self):
        engine = RunbookEngine()
        for name in ("execute_runbook", "get_runbook_templates",
                     "approve_runbook", "execute_runbook_step", "execute"):
            assert hasattr(engine, name)
            assert callable(getattr(engine, name))

    def test_get_templates_returns_list(self):
        templates = RunbookEngine().get_runbook_templates()
        assert isinstance(templates, list)
        assert "逆变器通讯中断" in templates

    def test_execute_function_exists(self):
        assert callable(execute_runbook_for_alarm)

    def test_execute_runbook_returns_id(self, test_db):
        result = RunbookEngine().execute_runbook(
            template="reboot_device", device_id=1, alarm_id=1, db=test_db["session"]
        )
        test_db["session"].close()
        assert result is not None and result > 0


# ========== shell 注入防御 ==========

class TestShellValidation:
    def test_validate_rejects_empty(self):
        # L48-49: 命令为空拒绝
        for cmd in ("", "   ", None):
            with pytest.raises(ValueError):
                validate_shell_command(cmd)

    @pytest.mark.parametrize("ch", [";", "&", "|", "$", "`", "(", ")", "<", ">", "\n"])
    def test_validate_rejects_injection_chars(self, ch):
        # L50-52: 危险元字符拒绝
        with pytest.raises(ValueError):
            validate_shell_command(f"echo hi{ch}rm -rf /")

    def test_validate_accepts_safe(self):
        validate_shell_command("echo hello")  # 不抛即通过
        validate_shell_command("ping 192.168.1.1")

    def test_safe_command_list_parses(self):
        # L64-66 正常路径
        assert safe_command_list("echo hello world") == ["echo", "hello", "world"]

    def test_safe_command_list_shlex_error(self):
        # L64-68: 引号未闭合 → shlex 失败 → ValueError
        # (双引号不在元字符黑名单, 可通过 validate, 但 shlex 解析会炸)
        with pytest.raises(ValueError):
            safe_command_list('echo "unclosed')

    def test_safe_command_list_empty_argv(self, monkeypatch):
        # L69-70: 防御性断言 — shlex.split 返回空 argv 时拒绝
        # (validate 已保证 strip 非空, 此分支正常不可达, 故 mock shlex 验证防御生效)
        import app.services.runbook_engine as mod
        monkeypatch.setattr(mod.shlex, "split", lambda s: [])
        with pytest.raises(ValueError):
            safe_command_list("echo hi")


# ========== 模板匹配 ==========

class TestRunbookTemplate:
    def test_match_exact(self):
        # L477: 精确命中
        t = RunbookTemplate.match("逆变器通讯中断")
        assert t is not None
        assert t["category"] == "inverter"

    def test_match_fuzzy(self):
        # L482: 关键词模糊命中(精确不中)
        # 注: 模糊匹配按空格分词, 中文用单字段子串"过温"匹配"逆变器过温告警"
        t = RunbookTemplate.match("过温")
        assert t is not None
        assert t["category"] == "inverter"

    def test_match_by_device_type(self):
        # L493-494: 设备类型兜底
        t = RunbookTemplate.match("totally_unknown_fault", device_type="charger")
        assert t is not None
        assert t["category"] == "charger"

    def test_match_returns_none(self):
        # L496: 完全不匹配
        assert RunbookTemplate.match("zzz_unknown", device_type="unknown") is None

    def test_get_default(self):
        # L501: 默认模板
        d = RunbookTemplate.get_default()
        assert d["category"] == "general"
        assert len(d["steps"]) >= 2


# ========== 别名方法 ==========

class TestAliasMethods:
    def test_approve_runbook(self):
        # L565
        r = RunbookEngine().approve_runbook(runbook_id="RB-1", approved=True)
        assert r["runbook_id"] == "RB-1" and r["status"] == "approved"

    def test_execute_runbook_step(self):
        # L569
        r = RunbookEngine().execute_runbook_step(step_id=3, runbook_id="RB-1")
        assert r["step_id"] == 3 and r["status"] == "completed"


# ========== execute 主流程 ==========

class TestExecute:
    """端到端测 execute, 用 monkeypatch _execute_step 精确控制结果, 避免真跑命令。"""

    def _dev(self, dtype="inverter"):
        return {
            "id": 1, "ip": "10.0.0.1", "sn": "DEV-0001",
            "name": "Device-1", "type": dtype, "station_id": 1,
        }

    def test_dry_run_skips_all(self):
        # L660-665: DRY_RUN 全跳过
        engine = RunbookEngine(dry_run=True)
        res = engine.execute(
            alarm_id=1,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info=self._dev(),
        )
        assert res["status"] == RunbookStatus.COMPLETED
        assert res["skipped_steps"] == len(res["steps"])
        assert res["success_steps"] == 0
        # 每个步骤均 SKIPPED
        assert all(s["status"] == RunbookStatus.SKIPPED for s in res["steps"])

    def test_default_fallback_when_no_match(self):
        # L615-616: 未知故障 + 未知设备类型 → get_default 兜底
        engine = RunbookEngine(dry_run=True)
        res = engine.execute(
            alarm_id=2,
            diagnosis_result={"fault_type": "zzz_no_such_fault"},
            device_info={"id": 1, "type": "weirdtype"},
        )
        # get_default 模板特征: 2 个步骤
        assert len(res["steps"]) == 2

    def test_approval_workflow_with_db(self, test_db):
        # L670-685: 有 DB + MEDIUM → 创建审批请求 + PENDING
        # L704: PENDING pass 分支
        # L905-906 + L958-975: manual SEND_NOTIFICATION 走通知(ImportError 回退)
        # L731: failed==0 → COMPLETED
        engine = RunbookEngine()
        s = test_db["session"]

        def fake_exec(step, info):
            step.status = RunbookStatus.COMPLETED  # LOW 步骤成功

        monkeypatch_ctx = pytest.MonkeyPatch()
        monkeypatch_ctx.setattr(engine, "_execute_step", fake_exec)
        try:
            res = engine.execute(
                alarm_id=10,
                diagnosis_result={"fault_type": "逆变器过温告警"},  # 含 MEDIUM CONFIG_CHANGE
                device_info=self._dev(),
                db=s,
            )
        finally:
            monkeypatch_ctx.undo()

        assert res["approval_needed"] == 1
        assert res["status"] == RunbookStatus.COMPLETED  # success=1 → L731
        from app.models.runbook_approval import RunbookApproval
        pending = s.query(RunbookApproval).filter(
            RunbookApproval.runbook_id == res["runbook_id"]
        ).all()
        assert len(pending) == 1
        assert pending[0].status == "pending"
        assert pending[0].risk_level == RiskLevel.MEDIUM
        s.close()

    def test_pending_approval_final_status(self, test_db):
        # L729: approval>0 且 success==0 且 failed==0 → "pending_approval"
        engine = RunbookEngine()
        s = test_db["session"]

        def fake_exec(step, info):
            step.status = RunbookStatus.SKIPPED  # LOW 步骤跳过 → success/failed 均为 0

        mp = pytest.MonkeyPatch()
        mp.setattr(engine, "_execute_step", fake_exec)
        try:
            res = engine.execute(
                alarm_id=11,
                diagnosis_result={"fault_type": "逆变器过温告警"},
                device_info=self._dev(),
                db=s,
            )
        finally:
            mp.undo()

        assert res["approval_needed"] == 1
        assert res["success_steps"] == 0 and res["failed_steps"] == 0
        assert res["status"] == "pending_approval"
        s.close()

    def test_failed_final_status_no_db(self):
        # L735: 全失败 → FAILED
        # L719-722: 无 DB + manual_steps 仅记录日志
        # L700-702: failed 累加 + error_message 拼接
        engine = RunbookEngine()

        def fake_exec(step, info):
            step.status = RunbookStatus.FAILED
            step.error_message = "boom"

        mp = pytest.MonkeyPatch()
        mp.setattr(engine, "_execute_step", fake_exec)
        try:
            res = engine.execute(
                alarm_id=12,
                diagnosis_result={"fault_type": "设备离线"},
                device_info=self._dev("general"),
                db=None,  # 无 DB → manual_steps 走 L719-722
            )
        finally:
            mp.undo()

        assert res["status"] == RunbookStatus.FAILED
        assert res["failed_steps"] >= 1
        assert "boom" in res["error_message"]

    def test_partial_success_final_status(self):
        # L733: success>0 且 failed>0 → COMPLETED(部分成功)
        engine = RunbookEngine()
        it = iter([RunbookStatus.COMPLETED, RunbookStatus.FAILED])

        def fake_exec(step, info):
            st = next(it)
            step.status = st
            if st == RunbookStatus.FAILED:
                step.error_message = "partial fail"

        mp = pytest.MonkeyPatch()
        mp.setattr(engine, "_execute_step", fake_exec)
        try:
            res = engine.execute(
                alarm_id=13,
                diagnosis_result={"fault_type": "设备离线"},  # 2 个 auto LOW 步骤
                device_info=self._dev("general"),
                db=None,
            )
        finally:
            mp.undo()

        assert res["success_steps"] == 1 and res["failed_steps"] == 1
        assert res["status"] == RunbookStatus.COMPLETED  # L733

    def test_medium_executed_no_db(self):
        # L688-689: 无 DB + MEDIUM → 降级执行
        engine = RunbookEngine()
        called = {"n": 0}

        def fake_exec(step, info):
            called["n"] += 1
            step.status = RunbookStatus.COMPLETED

        mp = pytest.MonkeyPatch()
        mp.setattr(engine, "_execute_step", fake_exec)
        try:
            res = engine.execute(
                alarm_id=14,
                diagnosis_result={"fault_type": "逆变器过温告警"},  # LOW + MEDIUM
                device_info=self._dev(),
                db=None,  # MEDIUM 走 L688-689 执行
            )
        finally:
            mp.undo()

        # LOW + MEDIUM 均执行(都调 _execute_step)
        assert called["n"] == 2
        assert res["approval_needed"] == 0

    def test_high_critical_skipped_no_db(self):
        # L690-693: 无 DB + HIGH/CRITICAL → 跳过
        engine = RunbookEngine()

        def fake_exec(step, info):
            step.status = RunbookStatus.COMPLETED  # 仅 LOW step1 走这

        mp = pytest.MonkeyPatch()
        mp.setattr(engine, "_execute_step", fake_exec)
        try:
            res = engine.execute(
                alarm_id=15,
                diagnosis_result={"fault_type": "储能系统过充过放"},  # 含 CRITICAL
                device_info=self._dev("ess"),
                db=None,
            )
        finally:
            mp.undo()

        # step2 CRITICAL 被 L690-693 跳过(不调 _execute_step)
        skipped_critical = [s for s in res["steps"] if s["status"] == RunbookStatus.SKIPPED]
        assert len(skipped_critical) >= 1

    def test_workorder_created_with_db(self, test_db):
        # L709-718: manual CREATE_WORKORDER 有 DB → 创建工单 + 回填 workorder_id
        # L903-904, L912-950: _create_workorder_from_runbook 成功路径
        engine = RunbookEngine()
        s = test_db["session"]

        def fake_exec(step, info):
            step.status = RunbookStatus.COMPLETED

        mp = pytest.MonkeyPatch()
        mp.setattr(engine, "_execute_step", fake_exec)
        try:
            res = engine.execute(
                alarm_id=16,
                diagnosis_result={"fault_type": "设备离线"},  # manual=CREATE_WORKORDER
                device_info=self._dev("general"),
                db=s,
            )
        finally:
            mp.undo()

        assert res["workorder_id"] is not None
        from app.models.workorder import WorkOrder
        wo = s.query(WorkOrder).filter(WorkOrder.id == res["workorder_id"]).first()
        assert wo is not None
        assert "Runbook自动" in wo.fault_desc
        s.close()


# ========== _match_template_db / _db_row_to_template_dict ==========

class TestMatchTemplateDb:
    def _seed(self, session, name, alarm_type, category="general", steps=None, status="active"):
        from app.models.runbook import RunbookTemplateModel
        row = RunbookTemplateModel(
            name=name, category=category, alarm_type=alarm_type,
            description=name, steps=steps or [], status=status,
        )
        session.add(row)
        session.commit()
        return row

    def test_exact_match(self, test_db):
        # L757-762, L781, L797-801
        s = test_db["session"]
        self._seed(s, "T精确", "过温", "inverter",
                   steps=[{"step_id": 1, "action_type": "remote_command",
                           "description": "d", "command": "echo"}])
        engine = RunbookEngine()
        t = engine._match_template_db("过温", "inverter", s)
        assert t is not None
        assert t["category"] == "inverter"
        assert len(t["steps"]) == 1
        s.close()

    def test_fuzzy_match(self, test_db):
        # L768-770: 关键词模糊匹配
        s = test_db["session"]
        self._seed(s, "T模糊", "逆变器过温告警特殊", steps=[])
        engine = RunbookEngine()
        t = engine._match_template_db("逆变器过温", "inverter", s)  # 精确不中
        assert t is not None
        s.close()

    def test_category_fallback(self, test_db):
        # L773-777: 设备类别兜底
        s = test_db["session"]
        self._seed(s, "T类别", "zzz_unique_alarm", category="charger", steps=[])
        engine = RunbookEngine()
        t = engine._match_template_db("yyy_no_match", "charger", s)
        assert t is not None
        assert t["category"] == "charger"
        s.close()

    def test_empty_fault_type(self, test_db):
        # L754-755: fault_type 空 → None
        s = test_db["session"]
        assert RunbookEngine()._match_template_db("", "inverter", s) is None
        s.close()

    def test_none_when_no_match(self, test_db):
        # L779-780
        s = test_db["session"]
        self._seed(s, "T存在", "存在告警", category="inverter", steps=[])
        assert RunbookEngine()._match_template_db("完全不匹配的词", "unknown", s) is None
        s.close()

    def test_inactive_template_ignored(self, test_db):
        # inactive 不参与匹配(status != active)
        s = test_db["session"]
        self._seed(s, "T停用", "停用告警", status="inactive", steps=[])
        assert RunbookEngine()._match_template_db("停用告警", "general", s) is None
        s.close()

    def test_db_row_to_template_dict_skips_bad_step(self, test_db):
        # L795-796: 坏 step(缺必填字段) → 跳过
        s = test_db["session"]
        from app.models.runbook import RunbookTemplateModel
        row = RunbookTemplateModel(
            name="T坏步", category="general", alarm_type="坏步告警",
            description="d",
            steps=[
                {"step_id": 1, "action_type": "remote_command",
                 "description": "ok", "command": "echo ok"},
                {"bad_field_only": "missing required"},  # 缺必填 → TypeError 跳过
            ],
        )
        s.add(row)
        s.commit()
        d = RunbookEngine._db_row_to_template_dict(row)
        assert len(d["steps"]) == 1  # 仅 1 个有效 step
        s.close()

    def test_match_template_db_import_error(self, monkeypatch, test_db):
        # L751-753: 模型 import 失败 → 返回 None
        s = test_db["session"]
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "app.models.runbook":
                raise ImportError("forced")
            return orig_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert RunbookEngine()._match_template_db("anything", "inverter", s) is None
        s.close()


# ========== _run_command ==========

class TestRunCommand:
    def test_trusted_empty_raises(self):
        # L813-815: trusted 通道空命令 → ValueError
        with pytest.raises(ValueError):
            RunbookEngine()._run_command("   ", 10, trusted=True)

    def test_trusted_executes(self):
        # L816-819: trusted → shell=True 执行
        r = RunbookEngine()._run_command("echo trusted_ok", 10, trusted=True)
        assert r.returncode == 0
        assert "trusted_ok" in r.stdout

    def test_untrusted_executes(self):
        # L820-823: non-trusted → safe_command_list + shell=False
        r = RunbookEngine()._run_command("echo untrusted_ok", 10, trusted=False)
        assert r.returncode == 0
        assert "untrusted_ok" in r.stdout


# ========== _execute_step 各分支 ==========

class TestExecuteStep:
    def _step(self, **kw):
        defaults = dict(step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                        description="d", command="echo hi", trusted=False)
        defaults.update(kw)
        return RunbookStep(**defaults)

    def test_no_command_skipped(self):
        # L834-837
        step = self._step(command="")
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.SKIPPED
        assert step.result == "No command"

    def test_pre_check_failure_skips(self, monkeypatch):
        # L843-851: 前置检查失败 → 跳过
        step = self._step(pre_check="check_something")
        eng = RunbookEngine()
        monkeypatch.setattr(eng, "_run_command", lambda *a: _cp(1, stdout="pre fail"))
        eng._execute_step(step, {})
        assert step.status == RunbookStatus.SKIPPED
        assert "Pre-check failed" in step.result

    def test_pre_check_timeout_continues(self, monkeypatch):
        # L852-853: 前置检查超时 → 继续执行主命令
        step = self._step(pre_check="check_something")
        eng = RunbookEngine()
        results = iter([
            subprocess.TimeoutExpired(cmd="x", timeout=1),  # pre_check 超时
            _cp(0, "main ok"),  # 主命令成功
        ])

        def fake_run(*a, **kw):
            val = next(results)
            if isinstance(val, BaseException):  # 异常实例 → 抛出, 触发内层 except
                raise val
            return val

        monkeypatch.setattr(eng, "_run_command", fake_run)
        eng._execute_step(step, {})
        assert step.status == RunbookStatus.COMPLETED

    def test_remote_command_success(self, monkeypatch):
        # L856-863
        step = self._step()
        eng = RunbookEngine()
        monkeypatch.setattr(eng, "_run_command", lambda *a, **kw: _cp(0, "done"))
        eng._execute_step(step, {})
        assert step.status == RunbookStatus.COMPLETED
        assert step.result == "done"

    def test_remote_command_failure(self, monkeypatch):
        # L859-861
        step = self._step()
        eng = RunbookEngine()
        monkeypatch.setattr(eng, "_run_command", lambda *a, **kw: _cp(1, stderr="oops"))
        eng._execute_step(step, {})
        assert step.status == RunbookStatus.FAILED
        assert "oops" in step.error_message

    def test_restart_service_success(self, monkeypatch):
        # L865-868, L877-878
        step = self._step(action_type=RunbookActionType.RESTART_SERVICE)
        eng = RunbookEngine()
        monkeypatch.setattr(eng, "_run_command", lambda *a, **kw: _cp(0, "restarted"))
        eng._execute_step(step, {})
        assert step.status == RunbookStatus.COMPLETED

    def test_config_change_failure_triggers_rollback(self, monkeypatch):
        # L869-876: CONFIG_CHANGE 失败 → 自动回滚 → ROLLED_BACK
        step = self._step(
            action_type=RunbookActionType.CONFIG_CHANGE,
            rollback_command="rollback_cmd",
        )
        eng = RunbookEngine()
        results = iter([_cp(1, stderr="cfg fail"), _cp(0, "rolled back")])
        monkeypatch.setattr(eng, "_run_command", lambda *a, **kw: next(results))
        eng._execute_step(step, {})
        assert step.status == RunbookStatus.ROLLED_BACK

    def test_unknown_action_skipped(self, monkeypatch):
        # L880-882: 未知 action_type → SKIPPED (requires manual handling)
        step = self._step(action_type=RunbookActionType.WAIT_AND_RECHECK)
        eng = RunbookEngine()
        eng._execute_step(step, {})
        assert step.status == RunbookStatus.SKIPPED
        assert "manual handling" in step.result

    def test_timeout_expired(self, monkeypatch):
        # L884-886
        step = self._step()
        eng = RunbookEngine()

        def boom(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="x", timeout=step.timeout_sec)

        monkeypatch.setattr(eng, "_run_command", boom)
        eng._execute_step(step, {})
        assert step.status == RunbookStatus.FAILED
        assert "Timeout" in step.error_message

    def test_general_exception(self, monkeypatch):
        # L887-889
        step = self._step()
        eng = RunbookEngine()

        def boom(*a, **kw):
            raise ValueError("unexpected")

        monkeypatch.setattr(eng, "_run_command", boom)
        eng._execute_step(step, {})
        assert step.status == RunbookStatus.FAILED
        assert "unexpected" in step.error_message


# ========== 通知发送 ==========

class TestSendNotification:
    def _step(self, **params):
        return RunbookStep(
            step_id=1, action_type=RunbookActionType.SEND_NOTIFICATION,
            description="notify", params=params,
        )

    def test_import_error_fallback(self):
        # L958-975: notification_dispatcher 无 dispatch_notification → ImportError 回退到日志
        # (默认 sys.modules 中真实模块不含该函数, 不 mock)
        RunbookEngine()._send_notification(
            self._step(message="hi", urgency="medium"), alarm_id=1, device_info={}
        )
        # 不抛即通过(回退到 logger)

    def test_dispatch_success(self, monkeypatch):
        # L966-972: dispatch_notification 可用且成功
        mock_mod = MagicMock()
        monkeypatch.setitem(sys.modules, "app.services.notification_dispatcher", mock_mod)
        RunbookEngine()._send_notification(
            self._step(message="ok", urgency="high"), alarm_id=2, device_info={"id": 1}
        )
        assert mock_mod.dispatch_notification.called
        kw = mock_mod.dispatch_notification.call_args.kwargs
        assert kw["content"] == "ok" and kw["urgency"] == "high"

    def test_dispatch_exception(self, monkeypatch):
        # L976-977: dispatch_notification 抛异常 → 仅记录日志
        mock_mod = MagicMock()
        mock_mod.dispatch_notification.side_effect = RuntimeError("send boom")
        monkeypatch.setitem(sys.modules, "app.services.notification_dispatcher", mock_mod)
        RunbookEngine()._send_notification(
            self._step(message="x"), alarm_id=3, device_info={}
        )
        # 不抛即通过

    def test_handle_manual_steps_routes_notification(self):
        # L905-906: _handle_manual_steps 对 SEND_NOTIFICATION 调 _send_notification
        step = self._step(message="route test")
        RunbookEngine()._handle_manual_steps([step], alarm_id=4, device_info={}, db=None)
        # 不抛即通过


# ========== 工单创建 + 执行记录保存 ==========

class TestWorkorderAndSave:
    def test_create_workorder_success(self, test_db):
        # L912-950
        s = test_db["session"]
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.CREATE_WORKORDER,
            description="派发工单", params={"urgency": "high", "type": "紧急检修"},
        )
        RunbookEngine()._create_workorder_from_runbook(
            step, alarm_id=1, device_info={"id": 1, "station_id": 1}, db=s
        )
        assert getattr(step, "_workorder_id", None) is not None
        from app.models.workorder import WorkOrder
        assert s.query(WorkOrder).filter(WorkOrder.id == step._workorder_id).first() is not None
        s.close()

    def test_create_workorder_failure(self):
        # L952-954: 异常 → rollback
        step = RunbookStep(
            step_id=2, action_type=RunbookActionType.CREATE_WORKORDER,
            description="x", params={"urgency": "medium", "type": "检修"},
        )
        # 不抛(异常被捕获 + rollback)
        RunbookEngine()._create_workorder_from_runbook(
            step, alarm_id=1, device_info={"id": 1, "station_id": 1}, db=_BoomDB()
        )
        assert not hasattr(step, "_workorder_id")

    def test_save_execution_success(self, test_db):
        # L979-1005
        s = test_db["session"]
        execution = RunbookExecution(
            runbook_id="RB-TEST-SAVE-1", alarm_id=1, device_id=1, station_id=1,
            fault_type="测试", status=RunbookStatus.COMPLETED,
            steps=[RunbookStep(step_id=1, action_type="remote_command",
                               description="d", command="echo")],
        )
        RunbookEngine()._save_execution(execution, s)
        from app.models.runbook_execution import RunbookExecutionRecord
        rec = s.query(RunbookExecutionRecord).filter(
            RunbookExecutionRecord.runbook_id == "RB-TEST-SAVE-1").first()
        assert rec is not None
        assert rec.success_steps == 0
        s.close()

    def test_save_execution_failure(self):
        # L1007-1009: 异常 → rollback
        execution = RunbookExecution(runbook_id="RB-BOOM", alarm_id=1)
        RunbookEngine()._save_execution(execution, _BoomDB())  # 不抛即通过


# ========== 变量替换 + 便捷函数 ==========

class TestSubstituteAndConvenience:
    def test_substitute_vars_all_fields(self):
        # L1029, L1031, L1033, L1035: command/rollback/pre_check/post_check 全替换
        step = RunbookStep(
            step_id=1, action_type="remote_command", description="d",
            command="cmd {device_id}",
            rollback_command="rb {device_id}",
            pre_check="pre {device_id}",
            post_check="post {device_id}",
        )
        out = RunbookEngine()._substitute_vars([step], {"device_id": 42})
        s = out[0]
        assert "42" in s.command
        assert "42" in s.rollback_command
        assert "42" in s.pre_check
        assert "42" in s.post_check
        # 原对象不被修改(deepcopy)
        assert "{device_id}" in step.command

    def test_substitute_vars_quotes_shell_metachar(self):
        # 安全: device_ip 含 shell 元字符 → shlex.quote 转义失活
        step = RunbookStep(
            step_id=1, action_type="remote_command", description="d",
            command="ping {device_ip}",
        )
        out = RunbookEngine()._substitute_vars([step], {"device_ip": "1.1.1.1; rm -rf /"})
        # shlex.quote 包裹单引号使 ; 失活
        assert "'" in out[0].command

    def test_execute_runbook_for_alarm(self, test_db):
        # L1074-1075: 便捷函数
        res = execute_runbook_for_alarm(
            alarm_id=99,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info={"id": 1, "type": "inverter"},
            db=test_db["session"],
            dry_run=True,  # 避免真跑命令
        )
        assert res["status"] == RunbookStatus.COMPLETED
        assert res["alarm_id"] == 99
        test_db["session"].close()
