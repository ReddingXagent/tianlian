"""test_models.py — Runbook 枚举与数据模型契约测试

被测: app/services/runbook_engine/models.py
覆盖:
1. 三个枚举 (RunbookActionType 9 / RunbookStatus 6 / RiskLevel 4) 的
   成员名与 string value 一一对应 —— str-Enum 契约, 下游 switch / 模板匹配依赖 value
2. RunbookStep (16 字段) / RunbookExecution (18 字段) 默认值正确性
3. 边界: 仅传必填字段, 其余走 default; 可变默认 (params/steps) 实例间隔离
4. str-Enum 行为: == 比较 / 直接当字符串用 (下游模板 ``status == "completed"``)

设计原则: 纯数据契约断言, 不依赖 DB / 运行时, 与 test_templates_exception 同目录风格。
"""
from dataclasses import is_dataclass
from datetime import datetime

from app.services.runbook_engine.models import (
    RiskLevel,
    RunbookActionType,
    RunbookExecution,
    RunbookStatus,
    RunbookStep,
)


# ─── 1. RunbookActionType (9 成员) ───


class TestRunbookActionType:
    EXPECTED = {
        "REMOTE_COMMAND": "remote_command",
        "API_CALL": "api_call",
        "CONFIG_CHANGE": "config_change",
        "RESTART_SERVICE": "restart_service",
        "RESET_PARAMETER": "reset_parameter",
        "CLEAR_CACHE": "clear_cache",
        "CREATE_WORKORDER": "create_workorder",
        "SEND_NOTIFICATION": "send_notification",
        "WAIT_AND_RECHECK": "wait_and_recheck",
    }

    def test_member_count(self):
        assert len(RunbookActionType) == 9

    def test_values(self):
        for name, value in self.EXPECTED.items():
            member = RunbookActionType[name]
            assert member.value == value

    def test_is_str_enum(self):
        # str-Enum: 直接当字符串用, 下游模板按 value 比较
        assert RunbookActionType.API_CALL == "api_call"
        assert RunbookActionType.API_CALL in {"api_call", "remote_command"}


# ─── 2. RunbookStatus (6 成员) ───


class TestRunbookStatus:
    EXPECTED = {
        "PENDING": "pending",
        "RUNNING": "running",
        "COMPLETED": "completed",
        "FAILED": "failed",
        "SKIPPED": "skipped",
        "ROLLED_BACK": "rolled_back",
    }

    def test_member_count(self):
        assert len(RunbookStatus) == 6

    def test_values(self):
        for name, value in self.EXPECTED.items():
            assert RunbookStatus[name].value == value

    def test_is_str_enum(self):
        assert RunbookStatus.COMPLETED == "completed"


# ─── 3. RiskLevel (4 成员) ───


class TestRiskLevel:
    EXPECTED = {
        "LOW": "low",
        "MEDIUM": "medium",
        "HIGH": "high",
        "CRITICAL": "critical",
    }

    def test_member_count(self):
        assert len(RiskLevel) == 4

    def test_values(self):
        for name, value in self.EXPECTED.items():
            assert RiskLevel[name].value == value

    def test_is_str_enum(self):
        assert RiskLevel.HIGH == "high"


# ─── 4. RunbookStep (16 字段) ───


class TestRunbookStep:
    def test_is_dataclass(self):
        assert is_dataclass(RunbookStep)

    def test_field_count(self):
        assert len(RunbookStep.__dataclass_fields__) == 16

    def test_defaults_with_only_required_fields(self):
        # 必填: step_id / action_type / description
        step = RunbookStep(step_id=1, action_type="api_call", description="重启")

        assert step.step_id == 1
        assert step.action_type == "api_call"
        assert step.description == "重启"
        # 默认值
        assert step.command == ""
        assert step.params == {}
        assert step.risk_level == "low"
        assert step.timeout_sec == 60
        assert step.rollback_command == ""
        assert step.pre_check == ""
        assert step.post_check == ""
        assert step.auto_execute is True
        assert step.trusted is False
        assert step.status == "pending"
        assert step.result == ""
        assert step.duration_ms == 0
        assert step.error_message == ""

    def test_params_is_instance_isolated(self):
        # field(default_factory=dict) —— 两个实例不能共享同一 dict
        a = RunbookStep(step_id=1, action_type="x", description="a")
        b = RunbookStep(step_id=2, action_type="x", description="b")
        a.params["k"] = "v"
        assert b.params == {}

    def test_full_construction(self):
        step = RunbookStep(
            step_id=7,
            action_type="remote_command",
            description="清缓存",
            command="redis-cli flushdb",
            params={"db": 0},
            risk_level="medium",
            timeout_sec=30,
            rollback_command="echo rollback",
            pre_check="echo pre",
            post_check="echo post",
            auto_execute=False,
            trusted=True,
            status="completed",
            result="ok",
            duration_ms=42,
            error_message="",
        )
        assert step.trusted is True
        assert step.auto_execute is False
        assert step.timeout_sec == 30
        assert step.params == {"db": 0}


# ─── 5. RunbookExecution (18 字段) ───


class TestRunbookExecution:
    def test_is_dataclass(self):
        assert is_dataclass(RunbookExecution)

    def test_field_count(self):
        assert len(RunbookExecution.__dataclass_fields__) == 18

    def test_defaults_with_only_required_fields(self):
        # 必填: runbook_id / alarm_id
        exe = RunbookExecution(runbook_id="rb-1", alarm_id=10)

        assert exe.runbook_id == "rb-1"
        assert exe.alarm_id == 10
        # 可选 / 默认
        assert exe.diagnosis_record_id is None
        assert exe.device_id == 0
        assert exe.station_id == 0
        assert exe.fault_type == ""
        assert exe.status == "pending"
        assert exe.steps == []
        assert exe.start_time is None
        assert exe.end_time is None
        assert exe.total_duration_ms == 0
        assert exe.success_steps == 0
        assert exe.failed_steps == 0
        assert exe.skipped_steps == 0
        assert exe.auto_executed == 0
        assert exe.manual_required == 0
        assert exe.workorder_id is None
        assert exe.error_message == ""

    def test_steps_is_instance_isolated(self):
        a = RunbookExecution(runbook_id="a", alarm_id=1)
        b = RunbookExecution(runbook_id="b", alarm_id=2)
        a.steps.append(RunbookStep(step_id=1, action_type="x", description="x"))
        assert b.steps == []

    def test_full_construction(self):
        now = datetime(2026, 8, 14, 12, 0, 0)
        step = RunbookStep(step_id=1, action_type="api_call", description="d")
        exe = RunbookExecution(
            runbook_id="rb-2",
            alarm_id=5,
            diagnosis_record_id=99,
            device_id=3,
            station_id=7,
            fault_type="overheat",
            status="running",
            steps=[step],
            start_time=now,
            end_time=None,
            total_duration_ms=1500,
            success_steps=1,
            failed_steps=0,
            skipped_steps=0,
            auto_executed=1,
            manual_required=0,
            workorder_id=None,
            error_message="",
        )
        assert exe.steps == [step]
        assert exe.start_time == now
        assert exe.diagnosis_record_id == 99
        assert exe.fault_type == "overheat"
