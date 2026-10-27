"""
Runbook Engine 真实缺陷修复测试 — 任务卡 9d85812f

针对 memory/runbook-engine-two-latent-bugs.md 记录的两个缺陷:
1. Bug1: _save_execution 把 datetime.now().isoformat() 字符串塞进 DateTime 列
        → 持久化必失败(StatementError)、except 静默吞错、成功日志行不可达。
2. Bug2: _SHELL_INJECTION_CHARS 黑名单含 & |, 内置模板大量用 &&/||
        → 非 dry_run 执行时 safe_command_list 抛 ValueError, 步骤全 FAILED。

每个 bug 先 RED(证明缺陷) 再 GREEN(证明修复), 并守住"用户自定义命令防御不弱化"红线。
"""
import shlex
import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.runbook_engine import (
    RunbookActionType,
    RunbookEngine,
    RunbookStep,
    RunbookTemplate,
    safe_command_list,
)


def _proc(returncode=0, stdout="", stderr=""):
    """构造 subprocess.run 的伪返回对象。"""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _dev():
    return {"id": 1, "name": "d", "sn": "s", "ip": "1.1.1.1",
            "type": "general", "station_id": 1}


# ========== Bug1: 执行记录持久化 ==========

class TestBug1ExecutionPersisted:
    def test_bug1_execution_record_persisted_with_datetime(self, monkeypatch, db_session):
        """RED→GREEN: 执行记录必须成功落库, start_time/end_time 为 datetime 对象。

        缺陷现状: _save_execution 把 isoformat 字符串塞 DateTime 列 →
        SQLite 抛 StatementError → except 回滚 → 表里 0 条记录, 982 成功日志行不可达。
        """
        from app.models.runbook_execution import RunbookExecutionRecord

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok\n", ""))
        engine = RunbookEngine()
        engine.execute(
            alarm_id=9001,
            diagnosis_result={"fault_type": "完全不存在的故障BUG1"},
            device_info=_dev(),
            db=db_session,
        )
        records = db_session.query(RunbookExecutionRecord).filter_by(alarm_id=9001).all()
        assert len(records) == 1, (
            f"执行记录应落库 1 条, 实际 {len(records)} 条 "
            "(Bug1: isoformat 字符串塞 DateTime 列致 commit 失败被回滚)"
        )
        # DateTime 列落库后应为 datetime 对象(SQLAlchemy result processor)
        assert isinstance(records[0].start_time, datetime)
        assert isinstance(records[0].end_time, datetime)

    def test_bug1_success_log_reachable(self, monkeypatch, db_session, caplog):
        """RED→GREEN: 持久化成功后 982 行 logger.info 应可达(缺陷下被 except 屏蔽)。"""
        import logging
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok\n", ""))
        engine = RunbookEngine()
        with caplog.at_level(logging.INFO, logger="app.services.runbook_engine"):
            engine.execute(
                alarm_id=9002,
                diagnosis_result={"fault_type": "完全不存在的故障BUG1b"},
                device_info=_dev(),
                db=db_session,
            )
        assert any("执行记录已保存" in r.message for r in caplog.records), (
            "持久化成功日志应出现(缺陷下因 commit 失败该行不可达)"
        )


# ========== Bug2: 内置模板命令信任通道 ==========

class TestBug2BuiltinTemplateTrusted:
    def test_builtin_templates_contain_shell_ops(self):
        """前置事实: 内置模板确实存在含 &&/|| 的硬编码命令(否则 Bug2 测试前提不成立)。"""
        found = []
        for name, tpl in RunbookTemplate.TEMPLATES.items():
            for step in tpl["steps"]:
                for field in ("command", "rollback_command", "pre_check"):
                    cmd = getattr(step, field, "") or ""
                    if "&&" in cmd or "||" in cmd:
                        found.append((name, step.step_id, field))
        assert found, "内置模板应存在含 &&/|| 的命令(Bug2 前提)"

    def test_bug2_builtin_step_not_rejected_in_execute(self, monkeypatch):
        """RED→GREEN: 内置模板含 &&/|| 的命令在非 dry_run 执行时不应被自家防御拦成 FAILED。

        缺陷现状: 设备离线 step1 `ping ... && echo ONLINE || echo OFFLINE` 经
        safe_command_list 时, & 与 | 命中黑名单 → ValueError → step FAILED,
        error_message 含"危险 shell 元字符"。
        """
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ONLINE\n", ""))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=9003,
            diagnosis_result={"fault_type": "设备离线"},
            device_info=_dev(),
        )
        step1 = result["steps"][0]
        # 不应因防御拦截而 FAILED
        assert step1["status"] != "failed", (
            f"内置模板 step1 不应失败: {step1.get('error_message')}"
        )
        assert "危险 shell 元字符" not in (step1.get("error_message") or ""), (
            f"内置硬编码命令被自家 shell 防御误伤: {step1.get('error_message')}"
        )

    def test_bug2_builtin_compound_command_uses_shell(self, monkeypatch):
        """RED→GREEN: 内置模板的复合命令应通过 shell=True 执行(支持 &&/|| 操作符)。

        缺陷现状: 即便绕过黑名单, shell=False 下 &&/|| 被 shlex 当普通 token 喂给首命令,
        复合命令无法正确执行。修复须对可信内置命令走 shell=True。
        """
        seen = {}

        def fake_run(*args, **kwargs):
            seen["shell"] = kwargs.get("shell", False)
            seen["args"] = args[0] if args else kwargs.get("args")
            return _proc(0, "OK\n", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        engine = RunbookEngine()
        engine.execute(
            alarm_id=9004,
            diagnosis_result={"fault_type": "设备离线"},
            device_info=_dev(),
        )
        assert seen.get("shell") is True, (
            "内置模板含 shell 操作符的命令必须以 shell=True 执行"
        )


# ========== 红线: 用户自定义命令防御不弱化 ==========

class TestUserCommandDefenseNotWeakened:
    def test_safe_command_list_still_rejects_shell_ops(self):
        """safe_command_list 默认(trusted=False)对 & | ; 等的拦截一行不减。"""
        for cmd in (
            "echo a && echo b",
            "echo a || echo b",
            "echo a ; rm -rf /",
            "echo $(whoami)",
            "echo `whoami`",
        ):
            with pytest.raises(ValueError, match="危险 shell 元字符"):
                safe_command_list(cmd)

    def test_db_custom_template_command_still_rejected(self, monkeypatch, db_session):
        """DB(用户自定义)模板命令含 && 时, 执行路径仍必须拒绝 → 防御未弱化。

        DB 模板不是硬编码可信源, 必须走完整黑名单 + shell=False。
        """
        from app.models.runbook import RunbookTemplateModel
        db_session.add(RunbookTemplateModel(
            name="用户注入测试", alarm_type="用户注入测试", category="general",
            steps=[{"step_id": 1, "action_type": "remote_command", "description": "x",
                    "command": "echo user && rm -rf /", "risk_level": "low",
                    "auto_execute": True}],
            status="active", version=1,
        ))
        db_session.commit()

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0, "ok", ""))
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=9005,
            diagnosis_result={"fault_type": "用户注入测试"},
            device_info=_dev(),
            db=db_session,
        )
        step1 = result["steps"][0]
        assert step1["status"] == "failed", "用户自定义命令含 && 必须被拒绝执行"
        assert "危险 shell 元字符" in (step1.get("error_message") or "")


# ========== _run_command 两条信任通道(Bug2 修复引入) ==========

class TestRunCommandHelper:
    def test_trusted_empty_command_rejected(self):
        """trusted 通道仍拒绝空命令(防御性校验)。"""
        engine = RunbookEngine()
        with pytest.raises(ValueError, match="命令为空"):
            engine._run_command("", 10, trusted=True)
        with pytest.raises(ValueError, match="命令为空"):
            engine._run_command("   ", 10, trusted=True)

    def test_untrusted_path_uses_safe_command_list(self, monkeypatch):
        """trusted=False → safe_command_list 黑名单 + shlex argv + shell=False。"""
        captured = {}

        def fake_run(*args, **kwargs):
            captured["shell"] = kwargs.get("shell", False)
            captured["argv"] = args[0]
            return _proc(0, "ok", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        engine = RunbookEngine()
        engine._run_command("echo hello", 10, trusted=False)
        assert captured["shell"] is False
        assert captured["argv"] == ["echo", "hello"]  # shlex.split 产物

    def test_trusted_path_uses_shell_true(self, monkeypatch):
        """trusted=True → 原串 shell=True, 保留 &&/||。"""
        captured = {}

        def fake_run(*args, **kwargs):
            captured["shell"] = kwargs.get("shell", False)
            captured["cmd"] = args[0]
            return _proc(0, "ok", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        engine = RunbookEngine()
        engine._run_command("echo a && echo b", 10, trusted=True)
        assert captured["shell"] is True
        assert captured["cmd"] == "echo a && echo b"  # 原串未被拆分


# ========== 既有 miss 覆盖(733 部分成功 / 752-753 import 兜底) ==========

class TestExecutePartialSuccess:
    def test_partial_success_status(self, monkeypatch):
        """733: success_steps>0 且 failed_steps>0 → 部分成功(状态 COMPLETED)。

        设备离线模板 step1(ping) 成功 + step2(nc) 失败 → 部分成功分支。
        """
        def fake_run(*args, **kwargs):
            cmd = args[0] if args else ""
            if isinstance(cmd, str) and cmd.startswith("nc"):
                return _proc(1, "", "closed\n")
            return _proc(0, "ONLINE\n", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=9006,
            diagnosis_result={"fault_type": "设备离线"},
            device_info=_dev(),
        )
        assert result["success_steps"] >= 1
        assert result["failed_steps"] >= 1
        assert result["status"] == "completed"  # 部分成功


class TestMatchTemplateDbImportFailure:
    def test_import_failure_returns_none(self, monkeypatch, db_session):
        """752-753: app.models.runbook import 失败 → except → return None。"""
        import sys
        monkeypatch.setitem(sys.modules, "app.models.runbook", None)
        engine = RunbookEngine()
        assert engine._match_template_db("任何故障", "inverter", db_session) is None


# ========== _save_execution except 分支覆盖(补因 Bug1 修复而失去的覆盖) ==========

class TestSaveExecutionExceptionBranch:
    def test_persist_exception_logged_and_rolled_back(self, caplog):
        """持久化层故障时: logger.error + db.rollback, 不向上抛、不静默吞。

        Bug1 修复前该分支由 isoformat 字符串触发; 修复后用 mock db 显式覆盖,
        保证 except 分支与回滚行为始终被测试约束。
        """
        import logging
        engine = RunbookEngine()

        class BoomDB:
            def __init__(self):
                self.rolled_back = False

            def add(self, *a, **k):
                pass

            def commit(self):
                raise RuntimeError("db down")

            def rollback(self):
                self.rolled_back = True

        from app.services.runbook_engine import RunbookExecution
        execution = RunbookExecution(
            runbook_id="RB-EXC", alarm_id=1,
            start_time=datetime.now(), end_time=datetime.now(),
        )
        db = BoomDB()
        with caplog.at_level(logging.ERROR, logger="app.services.runbook_engine"):
            engine._save_execution(execution, db)  # 不抛即通过

        assert db.rolled_back is True, "持久化失败必须回滚"
        assert any("保存失败" in r.message and r.levelno >= logging.ERROR
                   for r in caplog.records), "持久化失败必须记 error 日志(不静默吞)"


# ========== 任务卡 361760d7: 内置模板变量替换 shlex.quote 防注入加固 ==========
#
# 背景: Bug2 修复(9d85812f)给内置硬编码模板开了 trusted=True → shell=True 信任通道,
# 以支持 &&/|| 操作符。但 _substitute_vars 用 str(val) 裸替换 device_info 变量值
# (device_ip/device_sn/device_name ...)。若设备字段被污染(如 device_ip 含 `;`),
# 经 shell=True 通道时元字符会被 shell 解释 → 命令注入。
#
# 修法(方案1, 最小改动): _substitute_vars 替换变量值时统一用 shlex.quote() 转义。
# 内置模板自身的 &&/|| 在硬编码模板里(非变量值), 不受影响。
# 用户自定义(DB)模板防御一行不弱化(见 TestUserCommandDefenseNotWeakened)。

class TestBuiltinTemplateVarInjectionHardened:
    def test_substituted_var_value_is_shlex_quoted(self):
        """RED→GREEN: 污染 device_ip 经 _substitute_vars 后必须被 shlex.quote 包裹。

        缺陷现状: str(val) 裸替换 →
          ping -c 5 {device_ip}  ⇒  ping -c 5 1.2.3.4; echo INJECTED
        shell=True 下 `; echo INJECTED` 作为独立命令执行 → 注入。
        修复后应 ⇒  ping -c 5 '1.2.3.4; echo INJECTED' (元字符失活)。
        """
        engine = RunbookEngine()
        steps = [RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="Ping设备", command="ping -c 5 {device_ip}",
        )]
        poisoned = "1.2.3.4; echo INJECTED"
        result = engine._substitute_vars(steps, {"device_ip": poisoned})
        assert shlex.quote(poisoned) in result[0].command, (
            f"污染 device_ip 必须经 shlex.quote 包裹, 实际: {result[0].command}"
        )
        # 裸的注入分隔符不应残留(整个值应在单引号定界内)
        assert "; echo INJECTED" not in result[0].command.replace(
            shlex.quote(poisoned), ""), (
            f"注入分隔符未被中和, 实际: {result[0].command}"
        )

    def test_all_device_info_vars_quoted_when_poisoned(self):
        """RED→GREEN: 所有 device_info 来源变量(device_ip/sn/name/type/id/station)
        被污染时, 替换值均须经 shlex.quote 中和 —— 通道是 shell=True, 任一漏网即注入。
        """
        engine = RunbookEngine()
        poison = "x; echo PWN"
        steps = [RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="t",
            command="{device_ip} {device_sn} {device_name} {device_type} "
                     "{station_id} {device_id}",
        )]
        ctx = {
            "device_ip": poison, "device_sn": poison, "device_name": poison,
            "device_type": poison, "station_id": poison, "device_id": poison,
        }
        result = engine._substitute_vars(steps, ctx)
        expected = " ".join([shlex.quote(poison)] * 6)
        assert result[0].command == expected, (
            f"所有变量值均需 shlex.quote 包裹, 实际: {result[0].command}"
        )

    def test_real_shell_injection_neutralized(self):
        """端到端真实 shell: _substitute_vars 产物经 _run_command(trusted=True→shell=True)
        执行, 污染值中的 INJECTED 不作为独立命令执行。

        RED(裸替换): `echo safe; echo INJECTED` → stdout 两行 ['safe', 'INJECTED']。
        GREEN(quote): `echo 'safe; echo INJECTED'` → stdout 单行 ['safe; echo INJECTED']。
        """
        engine = RunbookEngine()
        steps = [RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="echo", command="echo {device_ip}",
            timeout_sec=10,
        )]
        poisoned = "safe; echo INJECTED"
        [step] = engine._substitute_vars(steps, {"device_ip": poisoned})
        proc = engine._run_command(step.command, step.timeout_sec, trusted=True)
        out_lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        assert out_lines == ["safe; echo INJECTED"], (
            f"注入未中和, shell 真实执行了注入片段, stdout={proc.stdout!r}"
        )

    def test_normal_var_value_unchanged_by_quote(self):
        """回归保护: 正常 IP/SN(仅含 shlex 安全字符)替换后命令字符串保持不变。

        shlex.quote 对 [a-zA-Z0-9@%_+=:,./-] 原样返回不加引号, 故:
          ping -c 3 {device_ip} && echo OK  ⇒  ping -c 3 192.168.1.100 && echo OK
        内置模板的 &&/|| 操作符保留, 现有 158 测试无回归。
        """
        engine = RunbookEngine()
        steps = [RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="ping", command="ping -c 3 {device_ip} && echo OK",
        )]
        [step] = engine._substitute_vars(steps, {"device_ip": "192.168.1.100"})
        assert step.command == "ping -c 3 192.168.1.100 && echo OK", (
            f"正常 IP 不应被引号包裹(回归风险): {step.command}"
        )
