"""
Runbook 自动化执行引擎单元测试

被测对象: app/services/runbook_engine.py

测试范围:
- 枚举: RunbookActionType / RunbookStatus / RiskLevel
- RunbookTemplate: 精确/模糊/设备类型兜底/默认模板
- RunbookEngine.execute: dry_run / 状态流转 / 审批流 / 无DB降级 / 人工步骤 / DB持久化
- RunbookEngine._execute_step: 各 action_type 分支 / pre_check / 回滚 / 超时 / 异常
- 工单生成 / 通知 / 执行记录保存
- 便捷函数 execute_runbook_for_alarm
- 边界: 空输入 / 无匹配 / 全失败 / 部分成功

铁律: 所有 subprocess 调用一律 mock, 绝不真实执行任何系统命令。
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.services.runbook_engine import (
    RunbookActionType,
    RunbookStatus,
    RiskLevel,
    RunbookStep,
    RunbookExecution,
    RunbookTemplate,
    RunbookEngine,
    execute_runbook_for_alarm,
)


# ========== 辅助函数 ==========

def _mkresult(returncode=0, stdout="ok", stderr=""):
    """构造一个 subprocess.run 的返回值 mock"""
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ========== 枚举测试 ==========

class TestEnums:
    def test_action_type_values(self):
        assert RunbookActionType.REMOTE_COMMAND == "remote_command"
        assert RunbookActionType.API_CALL == "api_call"
        assert RunbookActionType.CONFIG_CHANGE == "config_change"
        assert RunbookActionType.RESTART_SERVICE == "restart_service"
        assert RunbookActionType.RESET_PARAMETER == "reset_parameter"
        assert RunbookActionType.CLEAR_CACHE == "clear_cache"
        assert RunbookActionType.CREATE_WORKORDER == "create_workorder"
        assert RunbookActionType.SEND_NOTIFICATION == "send_notification"
        assert RunbookActionType.WAIT_AND_RECHECK == "wait_and_recheck"

    def test_runbook_status_values(self):
        assert RunbookStatus.PENDING == "pending"
        assert RunbookStatus.RUNNING == "running"
        assert RunbookStatus.COMPLETED == "completed"
        assert RunbookStatus.FAILED == "failed"
        assert RunbookStatus.SKIPPED == "skipped"
        assert RunbookStatus.ROLLED_BACK == "rolled_back"

    def test_risk_level_values(self):
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.CRITICAL == "critical"

    def test_enums_are_str_serializable(self):
        # 状态流转/JSON序列化依赖 str 子类语义
        assert isinstance(RunbookStatus.COMPLETED, str)
        assert isinstance(RunbookActionType.REMOTE_COMMAND, str)
        assert isinstance(RiskLevel.HIGH, str)

    def test_status_transition_flow(self):
        """模拟一次完整状态流转: pending → running → completed"""
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND, description="x"
        )
        assert step.status == "pending"
        step.status = RunbookStatus.RUNNING
        assert step.status == "running"
        step.status = RunbookStatus.COMPLETED
        assert step.status == "completed"

    def test_status_transition_to_rolled_back(self):
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.CONFIG_CHANGE, description="x"
        )
        step.status = RunbookStatus.RUNNING
        step.status = RunbookStatus.FAILED
        step.status = RunbookStatus.ROLLED_BACK
        assert step.status == "rolled_back"


# ========== RunbookTemplate 测试 ==========

class TestRunbookTemplate:
    def test_match_exact(self):
        tpl = RunbookTemplate.match("逆变器通讯中断")
        assert tpl is not None
        assert tpl["category"] == "inverter"
        assert len(tpl["steps"]) == 4

    def test_match_fuzzy_by_keyword(self):
        # fault_type 含 "过温" 关键词, 命中 "逆变器过温告警"
        tpl = RunbookTemplate.match("过温")
        assert tpl is not None
        assert tpl["category"] == "inverter"
        assert "过温" in tpl["description"]

    def test_match_fuzzy_multi_word(self):
        # 多关键词: 任一关键词命中即匹配
        tpl = RunbookTemplate.match("电池 告警")
        assert tpl is not None
        assert tpl["category"] in ("inverter", "bms")

    def test_match_returns_none_when_nothing_matches(self):
        assert RunbookTemplate.match("zzz_unknown", device_type="unknown") is None

    def test_match_empty_fault_and_device(self):
        assert RunbookTemplate.match("", device_type="") is None

    @pytest.mark.parametrize("dev_type,category", [
        ("inverter", "inverter"),
        ("charger", "charger"),
        ("pcs", "pcs"),
        ("bms", "bms"),
        ("ems", "ems"),
        ("ess", "ess"),
    ])
    def test_match_device_type_all_mappings(self, dev_type, category):
        tpl = RunbookTemplate.match("不存在故障", device_type=dev_type)
        assert tpl is not None
        assert tpl["category"] == category

    def test_match_device_type_case_insensitive(self):
        tpl = RunbookTemplate.match("x", device_type="INVERTER")
        assert tpl is not None
        assert tpl["category"] == "inverter"

    def test_get_default_structure(self):
        default = RunbookTemplate.get_default()
        assert default["category"] == "general"
        assert len(default["steps"]) >= 2
        auto = [s for s in default["steps"] if s.auto_execute]
        manual = [s for s in default["steps"] if not s.auto_execute]
        assert len(auto) >= 1
        assert len(manual) >= 1

    def test_all_templates_have_required_keys(self):
        # 模板库结构完整性回归
        for name, tpl in RunbookTemplate.TEMPLATES.items():
            assert "category" in tpl, f"{name} 缺 category"
            assert "description" in tpl, f"{name} 缺 description"
            assert isinstance(tpl["steps"], list) and len(tpl["steps"]) > 0, f"{name} steps 为空"
            for step in tpl["steps"]:
                assert isinstance(step, RunbookStep)


# ========== _substitute_vars 测试 ==========

class TestSubstituteVars:
    def test_replaces_all_command_fields(self):
        engine = RunbookEngine()
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="x", command="ping {device_ip}",
            rollback_command="undo {device_ip}",
            pre_check="check {device_ip}", post_check="post {device_ip}",
        )
        result = engine._substitute_vars([step], {"device_ip": "1.2.3.4"})
        assert result[0].command == "ping 1.2.3.4"
        assert result[0].rollback_command == "undo 1.2.3.4"
        assert result[0].pre_check == "check 1.2.3.4"
        assert result[0].post_check == "post 1.2.3.4"

    def test_substitutes_multiple_vars(self):
        engine = RunbookEngine()
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="x", command="{device_id}:{device_ip}:{device_sn}",
        )
        result = engine._substitute_vars([step], {
            "device_id": 7, "device_ip": "10.0.0.1", "device_sn": "SN001",
        })
        assert result[0].command == "7:10.0.0.1:SN001"

    def test_handles_missing_placeholders(self):
        engine = RunbookEngine()
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="x", command="echo hello",
        )
        result = engine._substitute_vars([step], {"device_ip": "1.2.3.4"})
        assert result[0].command == "echo hello"

    def test_does_not_mutate_shared_template(self):
        """关键回归: TEMPLATES 是类变量, deepcopy 必须保证原模板不被污染"""
        engine = RunbookEngine(dry_run=True)
        tpl_key = "逆变器通讯中断"
        original_cmd = RunbookTemplate.TEMPLATES[tpl_key]["steps"][0].command
        engine.execute(1, {"fault_type": tpl_key}, {"id": 1, "ip": "9.9.9.9"})
        after_cmd = RunbookTemplate.TEMPLATES[tpl_key]["steps"][0].command
        assert original_cmd == after_cmd
        assert "{device_ip}" in after_cmd  # 占位符仍在, 说明未被替换


# ========== _execute_step 测试 (核心, subprocess 全 mock) ==========

class TestExecuteStep:
    @patch("app.services.runbook_engine.subprocess.run")
    def test_no_command_skipped(self, mock_run):
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.SEND_NOTIFICATION,
            description="notify", command="",
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.SKIPPED
        assert step.result == "No command"
        mock_run.assert_not_called()

    @patch("app.services.runbook_engine.subprocess.run")
    def test_remote_command_success(self, mock_run):
        mock_run.return_value = _mkresult(stdout="pong")
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="ping", command="ping x", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.COMPLETED
        assert step.result == "pong"
        mock_run.assert_called_once()

    @patch("app.services.runbook_engine.subprocess.run")
    def test_remote_command_failure(self, mock_run):
        mock_run.return_value = _mkresult(returncode=1, stderr="err")
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="ping", command="ping x", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.FAILED
        assert step.error_message == "err"
        assert mock_run.call_count == 1  # 失败不回滚

    @patch("app.services.runbook_engine.subprocess.run")
    def test_restart_service_success(self, mock_run):
        mock_run.return_value = _mkresult(stdout="active")
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.RESTART_SERVICE,
            description="restart", command="systemctl restart x", timeout_sec=30,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.COMPLETED
        assert step.result == "active"

    @patch("app.services.runbook_engine.subprocess.run")
    def test_restart_service_failure_no_rollback(self, mock_run):
        # RESTART_SERVICE 失败, 即使配置了 rollback_command 也不回滚
        mock_run.return_value = _mkresult(returncode=1, stderr="fail")
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.RESTART_SERVICE,
            description="restart", command="cmd",
            rollback_command="undo cmd", timeout_sec=30,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.FAILED
        assert mock_run.call_count == 1  # 主命令一次, 不回滚

    @patch("app.services.runbook_engine.subprocess.run")
    def test_config_change_success_no_rollback(self, mock_run):
        mock_run.return_value = _mkresult(stdout="done")
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.CONFIG_CHANGE,
            description="cfg", command="set x",
            rollback_command="unset x", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.COMPLETED
        assert mock_run.call_count == 1

    @patch("app.services.runbook_engine.subprocess.run")
    def test_config_change_failure_triggers_rollback(self, mock_run):
        # 主命令失败 + CONFIG_CHANGE + rollback_command → ROLLED_BACK
        mock_run.side_effect = [
            _mkresult(returncode=1, stderr="bad"),   # 主命令失败
            _mkresult(stdout="rolled back"),          # 回滚命令成功
        ]
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.CONFIG_CHANGE,
            description="cfg", command="set x",
            rollback_command="unset x", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.ROLLED_BACK
        assert mock_run.call_count == 2
        # 第二次调用的命令字符串是回滚命令
        assert mock_run.call_args_list[1].args[0] == ["unset", "x"]

    @patch("app.services.runbook_engine.subprocess.run")
    def test_clear_cache_action(self, mock_run):
        mock_run.return_value = _mkresult(stdout="cleared")
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.CLEAR_CACHE,
            description="clear", command="flushall", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.COMPLETED

    @patch("app.services.runbook_engine.subprocess.run")
    def test_reset_parameter_action(self, mock_run):
        mock_run.return_value = _mkresult(stdout="reset")
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.RESET_PARAMETER,
            description="reset", command="reset cmd", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.COMPLETED

    @patch("app.services.runbook_engine.subprocess.run")
    def test_pre_check_failure_skips(self, mock_run):
        mock_run.return_value = _mkresult(returncode=1, stdout="precheck fail")
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="x", command="real cmd",
            pre_check="precheck cmd", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.SKIPPED
        assert "Pre-check failed" in step.result
        assert mock_run.call_count == 1
        assert mock_run.call_args.args[0] == ["precheck", "cmd"]

    @patch("app.services.runbook_engine.subprocess.run")
    def test_pre_check_timeout_continues(self, mock_run):
        # pre_check 超时不阻断, 继续执行主命令
        mock_run.side_effect = [
            subprocess.TimeoutExpired("precheck", 10),
            _mkresult(stdout="main ok"),
        ]
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="x", command="main cmd",
            pre_check="precheck", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.COMPLETED
        assert step.result == "main ok"
        assert mock_run.call_count == 2

    @patch("app.services.runbook_engine.subprocess.run")
    def test_command_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5)
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="x", command="slow cmd", timeout_sec=5,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.FAILED
        assert "Timeout" in step.error_message

    @patch("app.services.runbook_engine.subprocess.run")
    def test_unexpected_exception(self, mock_run):
        mock_run.side_effect = OSError("boom")
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="x", command="cmd", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.FAILED
        assert "boom" in step.error_message

    @patch("app.services.runbook_engine.subprocess.run")
    def test_manual_action_type_skipped(self, mock_run):
        # API_CALL 走 else 分支 → SKIPPED "requires manual handling", 不调 subprocess
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.API_CALL,
            description="api", command="do api", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.SKIPPED
        assert "manual handling" in step.result
        mock_run.assert_not_called()

    @patch("app.services.runbook_engine.subprocess.run")
    def test_wait_and_recheck_skipped(self, mock_run):
        # WAIT_AND_RECHECK 不在可执行 action 集合, 走 else 分支
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.WAIT_AND_RECHECK,
            description="wait", command="sleep 60", timeout_sec=75,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.SKIPPED

    @patch("app.services.runbook_engine.subprocess.run")
    def test_duration_recorded(self, mock_run):
        mock_run.return_value = _mkresult()
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="x", command="cmd", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.duration_ms >= 0

    @patch("app.services.runbook_engine.subprocess.run")
    def test_error_message_truncated(self, mock_run):
        # stderr 超长应被截断到 500 字符
        long_err = "E" * 2000
        mock_run.return_value = _mkresult(returncode=1, stderr=long_err)
        step = RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="x", command="cmd", timeout_sec=10,
        )
        RunbookEngine()._execute_step(step, {})
        assert step.status == RunbookStatus.FAILED
        assert len(step.error_message) <= 500


# ========== RunbookEngine.execute 测试 ==========

class TestExecuteFlow:
    @patch("app.services.runbook_engine.subprocess.run")
    def test_dry_run_skips_all(self, mock_run):
        engine = RunbookEngine(dry_run=True)
        result = engine.execute(
            alarm_id=1,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info={"id": 1, "ip": "1.1.1.1", "name": "INV-1"},
        )
        assert result["status"] == RunbookStatus.COMPLETED
        assert result["skipped_steps"] == len(result["steps"])
        assert result["success_steps"] == 0
        assert result["failed_steps"] == 0
        mock_run.assert_not_called()  # dry run 绝不执行

    @patch("app.services.runbook_engine.subprocess.run")
    def test_empty_inputs_uses_default_template(self, mock_run):
        mock_run.return_value = _mkresult()
        engine = RunbookEngine()
        result = engine.execute(alarm_id=1, diagnosis_result={}, device_info={})
        # 无 fault_type → 无匹配 → 默认模板 (2 步)
        assert len(result["steps"]) == 2
        assert result["fault_type"] == ""
        assert result["runbook_id"].startswith("RB-1-")

    @patch("app.services.runbook_engine.subprocess.run")
    def test_no_match_uses_default_template(self, mock_run):
        mock_run.return_value = _mkresult()
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=2,
            diagnosis_result={"fault_type": "完全不认识的故障XYZ"},
            device_info={"id": 1, "ip": "1.1.1.1", "type": "unknown"},
        )
        assert len(result["steps"]) == 2

    @patch("app.services.runbook_engine.subprocess.run")
    def test_low_risk_auto_steps_execute_success(self, mock_run):
        mock_run.return_value = _mkresult(stdout="ONLINE")
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=3,
            diagnosis_result={"fault_type": "设备离线"},
            device_info={"id": 5, "ip": "10.0.0.5"},
        )
        # 设备离线: 2 个 REMOTE_COMMAND LOW auto 步骤
        assert result["success_steps"] == 2
        assert result["failed_steps"] == 0
        assert result["status"] == RunbookStatus.COMPLETED
        assert mock_run.call_count == 2

    @patch.object(RunbookEngine, "_execute_step")
    def test_all_steps_failed(self, mock_exec):
        def _fail(step, device_info):
            step.status = RunbookStatus.FAILED
            step.error_message = "boom"
        mock_exec.side_effect = _fail
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=4,
            diagnosis_result={"fault_type": "设备离线"},
            device_info={"id": 5, "ip": "10.0.0.5"},
        )
        assert result["status"] == RunbookStatus.FAILED
        assert result["failed_steps"] == 2
        assert result["success_steps"] == 0
        assert "boom" in result["error_message"]

    @patch.object(RunbookEngine, "_execute_step")
    def test_partial_success_marks_completed(self, mock_exec):
        # 部分成功部分失败 → success>0 → COMPLETED
        seq = iter([RunbookStatus.COMPLETED, RunbookStatus.FAILED])

        def _vary(step, device_info):
            step.status = next(seq)
            if step.status == RunbookStatus.FAILED:
                step.error_message = "x"
        mock_exec.side_effect = _vary
        engine = RunbookEngine()
        result = engine.execute(
            alarm_id=5,
            diagnosis_result={"fault_type": "设备离线"},
            device_info={"id": 5, "ip": "10.0.0.5"},
        )
        assert result["status"] == RunbookStatus.COMPLETED  # 部分成功
        assert result["success_steps"] == 1
        assert result["failed_steps"] == 1

    @patch.object(RunbookEngine, "_match_template_db", return_value=None)
    @patch("app.api.v1.runbook_approval.create_approval_request")
    @patch("app.services.runbook_engine.RunbookTemplate.match")
    def test_pending_approval_when_all_high_risk_with_db(self, mock_match, mock_approval, mock_db_match):
        # 自定义模板: 全是 HIGH 风险 auto step → 全部走审批, 无执行
        mock_match.return_value = {
            "category": "test", "description": "t",
            "steps": [RunbookStep(
                step_id=1, action_type=RunbookActionType.CONFIG_CHANGE,
                description="高危", command="dangerous cmd",
                risk_level=RiskLevel.HIGH, auto_execute=True,
            )],
        }
        db = MagicMock()
        result = RunbookEngine().execute(
            alarm_id=10, diagnosis_result={"fault_type": "x"},
            device_info={"id": 1, "ip": "1.1.1.1"}, db=db,
        )
        assert result["status"] == "pending_approval"
        assert result["approval_needed"] == 1
        assert result["success_steps"] == 0
        mock_approval.assert_called_once()
        assert mock_approval.call_args.kwargs["runbook_id"].startswith("RB-10-")
        assert mock_approval.call_args.kwargs["risk_level"] == RiskLevel.HIGH

    @patch.object(RunbookEngine, "_match_template_db", return_value=None)
    @patch("app.api.v1.runbook_approval.create_approval_request")
    @patch("app.services.runbook_engine.subprocess.run")
    def test_mixed_risk_with_db(self, mock_run, mock_approval, mock_db_match):
        # 真实模板 "逆变器过温告警": step1 LOW 执行, step2 MEDIUM 走审批
        mock_run.return_value = _mkresult(stdout="ok")
        db = MagicMock()
        result = RunbookEngine().execute(
            alarm_id=11,
            diagnosis_result={"fault_type": "逆变器过温告警"},
            device_info={"id": 1, "ip": "1.1.1.1", "sn": "SN1", "name": "INV"},
            db=db,
        )
        assert result["approval_needed"] == 1
        assert result["success_steps"] >= 1
        # success>0 → COMPLETED (不是 pending_approval)
        assert result["status"] == RunbookStatus.COMPLETED
        mock_approval.assert_called_once()

    @patch("app.services.runbook_engine.RunbookTemplate.match")
    @patch("app.services.runbook_engine.subprocess.run")
    def test_high_risk_no_db_skipped(self, mock_run, mock_match):
        mock_match.return_value = {
            "category": "test", "description": "t",
            "steps": [RunbookStep(
                step_id=1, action_type=RunbookActionType.CONFIG_CHANGE,
                description="高危", command="cmd",
                risk_level=RiskLevel.HIGH, auto_execute=True,
            )],
        }
        result = RunbookEngine().execute(
            1, {"fault_type": "x"}, {"id": 1, "ip": "1.1.1.1"},
        )
        # HIGH + 无DB → 降级跳过
        assert result["skipped_steps"] == 1
        assert result["success_steps"] == 0
        mock_run.assert_not_called()

    @patch("app.services.runbook_engine.RunbookTemplate.match")
    @patch("app.services.runbook_engine.subprocess.run")
    def test_critical_risk_no_db_skipped(self, mock_run, mock_match):
        mock_match.return_value = {
            "category": "test", "description": "t",
            "steps": [RunbookStep(
                step_id=1, action_type=RunbookActionType.CONFIG_CHANGE,
                description="极高", command="cmd",
                risk_level=RiskLevel.CRITICAL, auto_execute=True,
            )],
        }
        result = RunbookEngine().execute(
            1, {"fault_type": "x"}, {"id": 1, "ip": "1.1.1.1"},
        )
        assert result["skipped_steps"] == 1
        mock_run.assert_not_called()

    @patch("app.services.runbook_engine.RunbookTemplate.match")
    @patch("app.services.runbook_engine.subprocess.run")
    def test_medium_risk_no_db_executes(self, mock_run, mock_match):
        # 无DB时中风险可执行 (降级策略)
        mock_run.return_value = _mkresult()
        mock_match.return_value = {
            "category": "test", "description": "t",
            "steps": [RunbookStep(
                step_id=1, action_type=RunbookActionType.CONFIG_CHANGE,
                description="中危", command="cmd",
                risk_level=RiskLevel.MEDIUM, auto_execute=True,
            )],
        }
        result = RunbookEngine().execute(
            1, {"fault_type": "x"}, {"id": 1, "ip": "1.1.1.1"},
        )
        assert result["success_steps"] == 1
        mock_run.assert_called_once()

    @patch.object(RunbookEngine, "_save_execution")
    @patch("app.services.runbook_engine.subprocess.run")
    def test_save_called_when_db_provided(self, mock_run, mock_save):
        mock_run.return_value = _mkresult()
        db = MagicMock()
        RunbookEngine().execute(
            1, {"fault_type": "设备离线"}, {"id": 1, "ip": "1.1.1.1"}, db=db,
        )
        mock_save.assert_called_once()

    @patch.object(RunbookEngine, "_save_execution")
    @patch("app.services.runbook_engine.subprocess.run")
    def test_save_not_called_without_db(self, mock_run, mock_save):
        mock_run.return_value = _mkresult()
        RunbookEngine().execute(
            1, {"fault_type": "设备离线"}, {"id": 1, "ip": "1.1.1.1"},
        )
        mock_save.assert_not_called()

    @patch.object(RunbookEngine, "_match_template_db", return_value=None)
    @patch.object(RunbookEngine, "_handle_manual_steps")
    @patch("app.services.runbook_engine.subprocess.run")
    def test_handle_manual_steps_called_with_db(self, mock_run, mock_handle, mock_db_match):
        mock_run.return_value = _mkresult()
        db = MagicMock()
        RunbookEngine().execute(
            1, {"fault_type": "设备离线"}, {"id": 1, "ip": "1.1.1.1"}, db=db,
        )
        # 设备离线有 1 个 manual step → 触发人工处理
        mock_handle.assert_called_once()

    @patch("app.services.runbook_engine.subprocess.run")
    def test_result_dict_structure(self, mock_run):
        mock_run.return_value = _mkresult()
        result = RunbookEngine().execute(
            7, {"fault_type": "设备离线"}, {"id": 1, "ip": "1.1.1.1", "name": "dev"},
        )
        expected_keys = {
            "runbook_id", "alarm_id", "fault_type", "status", "total_duration_ms",
            "success_steps", "failed_steps", "skipped_steps", "auto_executed",
            "manual_required", "workorder_id", "error_message", "steps", "approval_needed",
        }
        assert expected_keys.issubset(result.keys())
        assert result["alarm_id"] == 7
        assert result["fault_type"] == "设备离线"
        assert result["approval_needed"] == 0
        assert isinstance(result["steps"], list)
        assert isinstance(result["total_duration_ms"], int)


# ========== 人工步骤 / 工单 / 通知 / 持久化 测试 ==========

class TestManualSteps:
    def test_handle_manual_steps_dispatches_both(self):
        engine = RunbookEngine()
        with patch.object(engine, "_create_workorder_from_runbook") as mock_wo, \
             patch.object(engine, "_send_notification") as mock_notify:
            steps = [
                RunbookStep(step_id=1, action_type=RunbookActionType.CREATE_WORKORDER,
                            description="wo", auto_execute=False, params={}),
                RunbookStep(step_id=2, action_type=RunbookActionType.SEND_NOTIFICATION,
                            description="notify", auto_execute=False, params={}),
            ]
            engine._handle_manual_steps(steps, alarm_id=1, device_info={}, db=MagicMock())
            mock_wo.assert_called_once()
            mock_notify.assert_called_once()

    @patch("app.models.workorder.WorkOrder")
    def test_create_workorder_success(self, MockWorkOrder):
        wo_instance = MagicMock(id="WO-X")
        MockWorkOrder.return_value = wo_instance
        db = MagicMock()
        step = RunbookStep(
            step_id=2, action_type=RunbookActionType.CREATE_WORKORDER,
            description="派发工单", auto_execute=False,
            params={"urgency": "high", "type": "巡检", "message": "通讯故障"},
        )
        RunbookEngine()._create_workorder_from_runbook(
            step, alarm_id=1, device_info={"id": 9, "station_id": 3}, db=db,
        )
        MockWorkOrder.assert_called_once()
        db.add.assert_called_once_with(wo_instance)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(wo_instance)

    @patch("app.models.workorder.WorkOrder")
    def test_create_workorder_exception_rolls_back(self, MockWorkOrder):
        MockWorkOrder.side_effect = RuntimeError("db error")
        db = MagicMock()
        step = RunbookStep(
            step_id=2, action_type=RunbookActionType.CREATE_WORKORDER,
            description="派发工单", auto_execute=False,
            params={"urgency": "medium", "type": "检修"},
        )
        # 不应抛异常, 应回滚
        RunbookEngine()._create_workorder_from_runbook(
            step, alarm_id=1, device_info={"id": 1}, db=db,
        )
        db.rollback.assert_called_once()

    def test_send_notification_with_message(self):
        step = RunbookStep(
            step_id=3, action_type=RunbookActionType.SEND_NOTIFICATION,
            description="notify", auto_execute=False,
            params={"urgency": "critical", "message": "急停触发"},
        )
        # 不抛异常即通过
        RunbookEngine()._send_notification(step, alarm_id=1, device_info={"name": "X"})

    def test_send_notification_default_message_uses_alarm_id(self):
        step = RunbookStep(
            step_id=3, action_type=RunbookActionType.SEND_NOTIFICATION,
            description="notify", auto_execute=False, params={},
        )
        with patch("app.services.runbook_engine.logger") as mock_logger:
            RunbookEngine()._send_notification(step, alarm_id=42, device_info={})
            mock_logger.info.assert_called_once()
            logged = " ".join(str(a) for a in mock_logger.info.call_args.args)
            assert "42" in logged


class TestSaveExecution:
    @patch("app.models.runbook_execution.RunbookExecutionRecord")
    def test_save_success(self, MockRecord):
        instance = MagicMock()
        MockRecord.return_value = instance
        db = MagicMock()
        execution = RunbookExecution(
            runbook_id="RB-1", alarm_id=1, device_id=1,
            status=RunbookStatus.COMPLETED,
        )
        RunbookEngine()._save_execution(execution, db)
        MockRecord.assert_called_once()
        db.add.assert_called_once_with(instance)
        db.commit.assert_called_once()

    @patch("app.models.runbook_execution.RunbookExecutionRecord")
    def test_save_exception_rolls_back(self, MockRecord):
        MockRecord.side_effect = RuntimeError("schema mismatch")
        db = MagicMock()
        execution = RunbookExecution(runbook_id="RB-1", alarm_id=1)
        # 不抛异常, 应回滚
        RunbookEngine()._save_execution(execution, db)
        db.rollback.assert_called_once()


class TestToDict:
    def test_to_dict_keys_and_step_serialization(self):
        execution = RunbookExecution(
            runbook_id="RB-1", alarm_id=1, device_id=2, station_id=3,
            fault_type="逆变器通讯中断", status=RunbookStatus.COMPLETED,
            success_steps=2, failed_steps=0, skipped_steps=1,
            auto_executed=3, manual_required=1,
        )
        execution.steps = [RunbookStep(
            step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
            description="x", command="cmd",
        )]
        d = RunbookEngine()._to_dict(execution)
        assert d["runbook_id"] == "RB-1"
        assert d["alarm_id"] == 1
        assert d["status"] == RunbookStatus.COMPLETED
        assert d["success_steps"] == 2
        assert isinstance(d["steps"], list)
        assert d["steps"][0]["step_id"] == 1
        assert d["steps"][0]["action_type"] == RunbookActionType.REMOTE_COMMAND


# ========== 便捷函数 ==========

class TestConvenienceFunction:
    @patch("app.services.runbook_engine.subprocess.run")
    def test_execute_runbook_for_alarm_delegates(self, mock_run):
        # dry_run 避免真实 subprocess
        result = execute_runbook_for_alarm(
            alarm_id=99,
            diagnosis_result={"fault_type": "设备离线"},
            device_info={"id": 1, "ip": "1.1.1.1"},
            dry_run=True,
        )
        assert result["alarm_id"] == 99
        assert result["runbook_id"].startswith("RB-99-")
        mock_run.assert_not_called()
