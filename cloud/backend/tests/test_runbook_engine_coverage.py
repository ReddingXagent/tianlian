"""
Runbook Engine 覆盖补充测试 — 任务卡 538d4f46

目标: 将 app/services/runbook_engine.py 覆盖从 63% 提升至 ≥70%。
纯新增测试, 不改源码, 不弱化既有断言。

覆盖盲区:
- validate_shell_command / safe_command_list (头部 shell 防御)
- RunbookEngine 兼容别名方法 (execute_runbook/get_runbook_templates/approve_runbook/execute_runbook_step)
- _execute_step 全分支 (空命令/前置检查/各类 action_type/回滚/超时/异常)
- _send_notification (ImportError 回退 / 成功 / 异常)
- _substitute_vars pre_check/post_check 替换
- _match_template_db (空 fault_type / 关键词模糊 / category 兜底)
- _db_row_to_template_dict 坏 step 跳过
- 非 dry_run 执行循环 + 最终状态判定
- _handle_manual_steps (SEND_NOTIFICATION 分发 / CREATE_WORKORDER 建单)
- _create_workorder_from_runbook 异常分支
- execute_runbook_for_alarm 便捷函数
"""
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.services.runbook_engine import (
    RunbookEngine,
    RunbookStep,
    RunbookActionType,
    RunbookStatus,
    validate_shell_command,
    safe_command_list,
    execute_runbook_for_alarm,
)


def _proc(returncode=0, stdout="", stderr=""):
    """构造 subprocess.run 的伪返回对象。"""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


# ========== Shell 注入防御 (48-52, 64-71) ==========

class TestShellValidation:
    def test_empty_command_rejected(self):
        with pytest.raises(ValueError, match="命令为空"):
            validate_shell_command("")

    def test_whitespace_command_rejected(self):
        with pytest.raises(ValueError, match="命令为空"):
            validate_shell_command("   \t  ")

    @pytest.mark.parametrize("ch", [
        ";", "&", "|", "$", "`", "(", ")", "{", "}", "<", ">", "\\", "\n", "\r",
    ])
    def test_injection_chars_rejected(self, ch):
        with pytest.raises(ValueError, match="危险 shell 元字符"):
            validate_shell_command(f"echo {ch} rm")

    def test_valid_command_passes(self):
        # 不抛即通过
        validate_shell_command("echo hello-world")
        validate_shell_command("ping 192.168.1.1 -c 3")


class TestSafeCommandList:
    def test_ok_returns_argv(self):
        assert safe_command_list("echo hello world") == ["echo", "hello", "world"]

    def test_injection_rejected(self):
        with pytest.raises(ValueError, match="危险 shell 元字符"):
            safe_command_list("echo a; rm -rf /")

    def test_shlex_parse_failure_wrapped(self):
        # 未闭合引号 → shlex 抛 ValueError → 包装为 "命令解析失败"
        with pytest.raises(ValueError, match="命令解析失败"):
            safe_command_list("echo 'unclosed")

    def test_empty_argv_after_split_rejected(self, monkeypatch):
        import app.services.runbook_engine as eng
        # shlex.split 正常不会返回空(validate 已拦空白), 用 monkeypatch 模拟边界
        monkeypatch.setattr(eng.shlex, "split", lambda c: [])
        with pytest.raises(ValueError, match="命令解析后为空"):
            safe_command_list("echo ok")


# ========== 兼容别名方法 (541-568) ==========

class TestEngineCompatMethods:
    def test_execute_runbook_alias_returns_int(self):
        engine = RunbookEngine(dry_run=True)
        rb_id = engine.execute_runbook(template="逆变器通讯中断", device_id=5, alarm_id=7)
        assert isinstance(rb_id, int)
        assert rb_id > 0

    def test_execute_runbook_alias_default_template(self):
        engine = RunbookEngine(dry_run=True)
        rb_id = engine.execute_runbook()  # 默认 template='设备离线'
        assert isinstance(rb_id, int)

    def test_get_runbook_templates(self):
        engine = RunbookEngine()
        names = engine.get_runbook_templates()
        assert isinstance(names, list)
        assert "逆变器通讯中断" in names
        assert len(names) == 10  # 内置 10 模板

    def test_approve_runbook(self):
        engine = RunbookEngine()
        r = engine.approve_runbook(runbook_id="RB-1", approved=True)
        assert r == {"runbook_id": "RB-1", "approved": True, "status": "approved"}

    def test_execute_runbook_step(self):
        engine = RunbookEngine()
        r = engine.execute_runbook_step(step_id=2, runbook_id="RB-1")
        assert r == {"step_id": 2, "runbook_id": "RB-1", "status": "completed"}


# ========== _execute_step 全分支 (794-870) ==========

class TestExecuteStep:
    def _engine(self):
        return RunbookEngine()  # dry_run=False

    def test_no_command_skipped(self, monkeypatch):
        # 空 command → SKIPPED, 不应触达 subprocess
        def fail(*a, **k):
            raise AssertionError("subprocess 不应被调用")
        monkeypatch.setattr(subprocess, "run", fail)
        step = RunbookStep(step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                           description="t", command="")
        self._engine()._execute_step(step, {"id": 1})
        assert step.status == RunbookStatus.SKIPPED
        assert step.result == "No command"

    def test_remote_command_success(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "OK\n", ""))
        step = RunbookStep(step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                           description="t", command="echo OK")
        self._engine()._execute_step(step, {"id": 1})
        assert step.status == RunbookStatus.COMPLETED
        assert step.result == "OK"
        assert step.duration_ms >= 0

    def test_remote_command_failed(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(2, "out", "boom\n"))
        step = RunbookStep(step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                           description="t", command="false")
        self._engine()._execute_step(step, {"id": 1})
        assert step.status == RunbookStatus.FAILED
        assert step.error_message == "boom"

    def test_config_change_success(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "done", ""))
        step = RunbookStep(step_id=1, action_type=RunbookActionType.CONFIG_CHANGE,
                           description="t", command="set x", rollback_command="unset x")
        self._engine()._execute_step(step, {"id": 1})
        assert step.status == RunbookStatus.COMPLETED

    def test_config_change_failed_with_rollback(self, monkeypatch):
        calls = []

        def fake(argv, **k):
            calls.append(list(argv))
            # 主命令(set)失败, 回滚命令(unset)成功
            if "set" in argv:
                return _proc(1, "out", "err")
            return _proc(0, "rolled", "")

        monkeypatch.setattr(subprocess, "run", fake)
        step = RunbookStep(step_id=1, action_type=RunbookActionType.CONFIG_CHANGE,
                           description="t", command="set x", rollback_command="unset x")
        self._engine()._execute_step(step, {"id": 1})
        assert step.status == RunbookStatus.ROLLED_BACK
        assert len(calls) == 2  # 主命令 + 回滚命令

    def test_restart_failed_no_rollback(self, monkeypatch):
        # RESTART_SERVICE 失败: 即使有 rollback, action_type!=CONFIG_CHANGE 也不回滚
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(1, "o", "e"))
        step = RunbookStep(step_id=1, action_type=RunbookActionType.RESTART_SERVICE,
                           description="t", command="restart svc",
                           rollback_command="stop svc")
        self._engine()._execute_step(step, {"id": 1})
        assert step.status == RunbookStatus.FAILED

    def test_unknown_action_skipped(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "", ""))
        step = RunbookStep(step_id=1, action_type=RunbookActionType.WAIT_AND_RECHECK,
                           description="t", command="sleep 1")
        self._engine()._execute_step(step, {"id": 1})
        assert step.status == RunbookStatus.SKIPPED
        assert "manual handling" in step.result

    def test_timeout(self, monkeypatch):
        def boom(argv, **k):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=1)
        monkeypatch.setattr(subprocess, "run", boom)
        step = RunbookStep(step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                           description="t", command="sleep 999", timeout_sec=1)
        self._engine()._execute_step(step, {"id": 1})
        assert step.status == RunbookStatus.FAILED
        assert "Timeout" in step.error_message

    def test_generic_exception(self, monkeypatch):
        def boom(argv, **k):
            raise RuntimeError("kaboom")
        monkeypatch.setattr(subprocess, "run", boom)
        step = RunbookStep(step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                           description="t", command="echo x")
        self._engine()._execute_step(step, {"id": 1})
        assert step.status == RunbookStatus.FAILED
        assert "kaboom" in step.error_message

    def test_pre_check_fail_skips(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(1, "pre-fail-output", ""))
        step = RunbookStep(step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                           description="t", command="echo ok", pre_check="check x")
        self._engine()._execute_step(step, {"id": 1})
        assert step.status == RunbookStatus.SKIPPED
        assert "Pre-check failed" in step.result

    def test_pre_check_timeout_continues(self, monkeypatch):
        calls = []

        def fake(argv, **k):
            calls.append(list(argv))
            if "check" in argv:  # pre_check 超时
                raise subprocess.TimeoutExpired(cmd=argv, timeout=1)
            return _proc(0, "OK", "")

        monkeypatch.setattr(subprocess, "run", fake)
        step = RunbookStep(step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                           description="t", command="echo ok", pre_check="check x")
        self._engine()._execute_step(step, {"id": 1})
        # 前置检查超时不中断, 继续执行主命令
        assert step.status == RunbookStatus.COMPLETED
        assert len(calls) == 2  # pre_check + 主命令


# ========== _send_notification (935-954) ==========

class TestSendNotification:
    def _step(self, **params):
        return RunbookStep(
            step_id=1, action_type=RunbookActionType.SEND_NOTIFICATION,
            description="通知", auto_execute=False, params=params,
        )

    def test_importerror_fallback_to_log(self):
        # 真实 notification_dispatcher 无 dispatch_notification 符号 → ImportError → 仅记日志
        engine = RunbookEngine()
        engine._send_notification(self._step(message="hi", urgency="high"),
                                  5, {"id": 1, "name": "d"})  # 不抛即通过

    def test_default_message_when_missing(self):
        engine = RunbookEngine()
        # params 无 message → 使用默认 "告警#{alarm_id} Runbook通知"
        engine._send_notification(self._step(), 9, {"id": 1})  # 不抛

    def test_dispatch_success_path(self, monkeypatch):
        # 注入伪 dispatch_notification 让 import 成功 → 走成功日志
        import types as _t
        fake_mod = _t.ModuleType("app.services.notification_dispatcher")
        dispatched = {}

        def fake_dispatch(**kw):
            dispatched.update(kw)
            return None

        fake_mod.dispatch_notification = fake_dispatch
        monkeypatch.setitem(sys.modules, "app.services.notification_dispatcher", fake_mod)
        engine = RunbookEngine()
        engine._send_notification(self._step(message="m", urgency="critical"),
                                  7, {"id": 1})
        assert dispatched.get("urgency") == "critical"
        assert "告警#7" in dispatched.get("title", "")

    def test_dispatch_exception_swallowed(self, monkeypatch):
        import types as _t
        fake_mod = _t.ModuleType("app.services.notification_dispatcher")

        def boom(**kw):
            raise RuntimeError("dispatch failed")

        fake_mod.dispatch_notification = boom
        monkeypatch.setitem(sys.modules, "app.services.notification_dispatcher", fake_mod)
        engine = RunbookEngine()
        engine._send_notification(self._step(message="m"), 7, {"id": 1})  # 异常被吞, 不抛


# ========== _substitute_vars pre/post_check (1001, 1003) ==========

class TestSubstitutePrePostCheck:
    def test_pre_post_check_substituted(self):
        engine = RunbookEngine()
        step = RunbookStep(
            step_id=1, action_type="remote_command", description="t",
            command="echo {device_id}",
            pre_check="check {device_ip}",
            post_check="verify {device_sn}",
        )
        result = engine._substitute_vars([step], {
            "device_id": 42, "device_ip": "10.0.0.1", "device_sn": "SN1",
        })
        assert result[0].command == "echo 42"
        assert result[0].pre_check == "check 10.0.0.1"
        assert result[0].post_check == "verify SN1"

    def test_original_step_not_mutated(self):
        engine = RunbookEngine()
        step = RunbookStep(step_id=1, action_type="remote_command", description="t",
                           command="echo {device_id}")
        engine._substitute_vars([step], {"device_id": 99})
        # deepcopy: 原步骤命令不变
        assert step.command == "echo {device_id}"


# ========== execute_runbook_for_alarm 便捷函数 (1042-1043) ==========

class TestExecuteRunbookForAlarmHelper:
    def test_helper_executes(self):
        result = execute_runbook_for_alarm(
            alarm_id=1,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info={"id": 1, "name": "d", "sn": "s",
                         "ip": "1.1.1.1", "type": "inverter", "station_id": 1},
            dry_run=True,
        )
        assert result["status"] == "completed"
        assert result["runbook_id"].startswith("RB-1-")


# ========== 非 dry_run 执行循环 + 状态判定 (656-695, 708, 718-724) ==========

class TestExecuteNonDryRun:
    def _dev(self):
        return {"id": 1, "name": "d", "sn": "s", "ip": "1.1.1.1",
                "type": "general", "station_id": 1}

    def test_low_risk_auto_executed_no_db(self, monkeypatch):
        # 无 db: 未知故障 → 默认模板, step1 LOW 'echo ...' 干净命令(无 && || ;) → 执行成功
        # 注: 内置 "设备离线" 等模板命令含 && / || 会被 shell 注入防御拦截 → FAILED,
        # 故此处用默认模板的 echo 命令验证 LOW 风险成功执行分支。
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok\n", ""))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=10,
            diagnosis_result={"fault_type": "完全不存在的故障XYZ"},
            device_info=self._dev(),
        )
        assert result["status"] == "completed"
        assert result["success_steps"] >= 1

    def test_high_risk_skipped_without_db(self, monkeypatch):
        # 无 db: HIGH/CRITICAL 风险跳过 (储能过充过放 step2 CONFIG_CHANGE CRITICAL)
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok", ""))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=11,
            diagnosis_result={"fault_type": "储能系统过充过放"},
            device_info={"id": 1, "name": "d", "sn": "s", "ip": "1.1.1.1",
                         "type": "ess", "station_id": 1},
        )
        assert result["skipped_steps"] >= 1  # CRITICAL 步骤被跳过

    def test_medium_risk_executed_without_db(self, monkeypatch):
        # 无 db: MEDIUM 风险降级执行 (逆变器过温告警 step2 CONFIG_CHANGE MEDIUM)
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok", ""))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=12,
            diagnosis_result={"fault_type": "逆变器过温告警"},
            device_info={"id": 1, "name": "d", "sn": "s", "ip": "1.1.1.1",
                         "type": "inverter", "station_id": 1},
        )
        assert result["success_steps"] >= 1

    def test_failed_step_marks_execution_failed(self, monkeypatch):
        # 主命令失败 → execution.failed_steps, 最终 status=failed
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(1, "out", "err"))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=13,
            diagnosis_result={"fault_type": "设备离线"},
            device_info=self._dev(),
        )
        assert result["failed_steps"] >= 1
        assert result["status"] == "failed"

    def test_manual_steps_without_db_logged(self, monkeypatch):
        # 无 db + 有人工步骤 → 走 elif 日志分支 (709-711)
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok", ""))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=14,
            diagnosis_result={"fault_type": "充电桩急停触发"},
            device_info={"id": 1, "name": "d", "sn": "s", "ip": "1.1.1.1",
                         "type": "charger", "station_id": 1},
        )
        # 急停: 全 manual, auto 步骤只有 1 个 remote_command(LOW)
        assert result["manual_required"] >= 2


# ========== db 路径: 审批流 / 工单 / 通知 / 持久化 ==========

class TestExecuteWithDb:
    def _dev(self):
        return {"id": 1, "name": "d", "sn": "s", "ip": "1.1.1.1",
                "type": "inverter", "station_id": 1}

    def test_send_notification_manual_step_dispatched(self, monkeypatch, db_session):
        # db + SEND_NOTIFICATION manual step → _handle_manual_steps 分发 (882-883)
        # + manual step 非 CREATE_WORKORDER → status=PENDING (708)
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok", ""))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=15,
            diagnosis_result={"fault_type": "逆变器过温告警"},
            device_info=self._dev(),
            db=db_session,
        )
        # 逆变器过温: 1 LOW remote + 1 MEDIUM config(需审批) + 1 SEND_NOTIFICATION manual
        assert result["manual_required"] >= 1
        assert result["approval_needed"] >= 1  # MEDIUM 步骤触发审批请求

    def test_workorder_created_from_runbook(self, monkeypatch, db_session):
        # db + CREATE_WORKORDER manual step → _create_workorder_from_runbook 建单 (885-927)
        # + execution.workorder_id 被填充 (704-707)
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok", ""))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=16,
            diagnosis_result={"fault_type": "设备离线"},
            device_info={"id": 1, "name": "d", "sn": "s", "ip": "1.1.1.1",
                         "type": "general", "station_id": 1},
            db=db_session,
        )
        assert result["workorder_id"] is not None
        assert str(result["workorder_id"]).startswith("WO-")

    def test_save_execution_failure_graceful(self, monkeypatch, db_session):
        # 已知缺陷(记录给丁哥, 本 coverage 任务不改源码):
        # execution.start_time/end_time 用 datetime.now().isoformat() 存为字符串,
        # 而 RunbookExecutionRecord.start_time/end_time 是 DateTime 列 →
        # SQLite (及大概率 PG) 拒绝字符串 → _save_execution 捕获异常回滚 (984-986),
        # execute 仍正常返回。982 成功行因此不可达, 此处覆盖 except 分支。
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok", ""))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=17,
            diagnosis_result={"fault_type": "未知故障QQQ"},
            device_info={"id": 1, "name": "d", "sn": "s", "ip": "1.1.1.1",
                         "type": "general", "station_id": 1},
            db=db_session,
        )
        # 持久化失败不阻断 execute 返回
        assert result["runbook_id"].startswith("RB-17-")

    def test_pending_approval_when_only_approval_steps(self, monkeypatch, db_session):
        # 构造一个仅含中高风险自动步骤、无成功步骤的场景 → status=pending_approval (717-718)
        # 用 db 自定义模板: step1 MEDIUM CONFIG_CHANGE(auto), step2 CREATE_WORKORDER(manual)
        from app.models.runbook import RunbookTemplateModel
        custom_steps = [
            {"step_id": 1, "action_type": "config_change", "description": "改配置",
             "command": "set x", "risk_level": "medium", "auto_execute": True},
            {"step_id": 2, "action_type": "create_workorder", "description": "建单",
             "risk_level": "low", "auto_execute": False, "params": {"type": "检修"}},
        ]
        db_session.add(RunbookTemplateModel(
            name="仅审批场景", alarm_type="仅审批场景", category="general",
            steps=custom_steps, status="active", version=1,
        ))
        db_session.commit()

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok", ""))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=18,
            diagnosis_result={"fault_type": "仅审批场景"},
            device_info={"id": 1, "name": "d", "sn": "s", "ip": "1.1.1.1",
                         "type": "general", "station_id": 1},
            db=db_session,
        )
        assert result["approval_needed"] >= 1
        assert result["status"] == "pending_approval"
        assert result["success_steps"] == 0


# ========== _create_workorder_from_runbook 异常分支 (929-931) ==========

class TestCreateWorkorderException:
    def test_workorder_construct_failure_rolls_back(self, monkeypatch, db_session):
        # patch WorkOrder 构造抛异常 → except → db.rollback (929-931)
        import app.models.workorder as womod

        class BoomWO:
            def __init__(self, *a, **k):
                raise RuntimeError("construct fail")

        monkeypatch.setattr(womod, "WorkOrder", BoomWO)
        engine = RunbookEngine()
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.CREATE_WORKORDER,
            description="t", auto_execute=False,
            params={"type": "检修", "urgency": "medium"},
        )
        # 不抛(异常被 catch + rollback)
        engine._create_workorder_from_runbook(step, 1, {"id": 1, "station_id": 1}, db_session)


# ========== _db_row_to_template_dict 坏 step 跳过 (784-785) ==========

class TestDbRowToTemplateDict:
    def test_bad_step_dict_skipped(self):
        # step dict 缺必填字段 → RunbookStep(**kw) 抛 TypeError → except continue (784-785)
        class FakeRow:
            category = "general"
            description = "d"
            steps = [{"description": "缺 step_id 和 action_type"}]

        d = RunbookEngine._db_row_to_template_dict(FakeRow())
        assert d["category"] == "general"
        assert d["description"] == "d"
        assert d["steps"] == []  # 坏 step 被跳过

    def test_none_steps_yields_empty(self):
        class FakeRow:
            category = None
            description = None
            steps = None

        d = RunbookEngine._db_row_to_template_dict(FakeRow())
        assert d["category"] == "general"
        assert d["description"] == ""
        assert d["steps"] == []


# ========== _match_template_db 边缘 (744, 757-759, 762-766) ==========

class TestMatchTemplateDb:
    def test_empty_fault_type_returns_none(self, db_session):
        engine = RunbookEngine()
        assert engine._match_template_db("", "inverter", db_session) is None

    def test_keyword_fuzzy_match(self, db_session):
        from app.models.runbook import RunbookTemplateModel
        db_session.add(RunbookTemplateModel(
            name="关键词测试", alarm_type="通讯中断XYZ", category="general",
            steps=[{"step_id": 1, "action_type": "remote_command",
                    "description": "x", "command": "echo ok",
                    "risk_level": "low", "auto_execute": True}],
            status="active", version=1,
        ))
        db_session.commit()
        engine = RunbookEngine()
        # fault_type="通讯" 关键词命中 alarm_type "通讯中断XYZ"
        t = engine._match_template_db("通讯", "", db_session)
        assert t is not None
        assert len(t["steps"]) == 1

    def test_category_fallback(self, db_session):
        from app.models.runbook import RunbookTemplateModel
        db_session.add(RunbookTemplateModel(
            name="类别兜底测试", alarm_type="完全不同的告警", category="charger",
            steps=[], status="active", version=1,
        ))
        db_session.commit()
        engine = RunbookEngine()
        # fault_type 不匹配 alarm_type, 但 device_type=charger 命中 category
        t = engine._match_template_db("随机故障词", "charger", db_session)
        assert t is not None
        assert t["category"] == "charger"

    def test_no_match_returns_none(self, db_session):
        engine = RunbookEngine()
        # 空库, 任何 fault_type 都不命中
        assert engine._match_template_db("不存在", "unknown", db_session) is None
