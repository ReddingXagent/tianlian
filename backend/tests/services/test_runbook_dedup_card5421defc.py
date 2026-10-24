"""卡 5421defc: Runbook 执行同告警去重闸回归测试。

背景: execute() 每次调用都新建执行记录并立即跑全部 LOW auto_execute 步骤
(含设备写命令), 三个触发路径(手动/重复诊断/自愈重试)可重复进入 →
重复下发设备写命令、审批请求堆积。

覆盖:
- 同告警 running 态重复 execute → 短路 deduplicated, 零命令/零新审批/零新记录
- 同告警 pending_approval 态重复 execute → 同上
- 同告警 COMPLETED 后再 execute → 允许新执行 (手动重跑语义保留)
- create_approval_request 同 (runbook_id, step_index) pending 重复 → 不新建
"""
import pytest

from app.services.runbook_engine import RunbookEngine
from app.services.runbook_engine.models import RunbookStatus, RiskLevel


def _dev():
    return {
        "id": 1, "ip": "10.0.0.1", "sn": "DEV-0001",
        "name": "Device-1", "type": "inverter", "station_id": 1,
    }


def _seed_record(session, alarm_id, status, runbook_id=None):
    from app.models.runbook_execution import RunbookExecutionRecord
    rec = RunbookExecutionRecord(
        runbook_id=runbook_id or f"RB-{alarm_id}-seed",
        alarm_id=alarm_id,
        device_id=1,
        station_id=1,
        fault_type="逆变器通讯中断",
        status=status,
    )
    session.add(rec)
    session.commit()
    return rec


class TestExecuteDedup:
    def test_running_blocks_reexecute(self, test_db):
        # 同告警 running 态 → 短路, 零命令执行
        s = test_db["session"]
        _seed_record(s, 101, "running")

        engine = RunbookEngine()
        commands = []
        engine._run_command = lambda *a, **kw: commands.append(a)  # 拦截真命令
        called = []
        engine._execute_step = lambda step, info: called.append(step.step_id)

        res = engine.execute(
            alarm_id=101,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info=_dev(),
            db=s,
        )
        assert res["status"] == "deduplicated"
        assert res["original_status"] == "running"
        assert res["runbook_id"] == "RB-101-seed"
        assert called == []  # 零命令执行
        assert commands == []  # _run_command 亦未被触达

        from app.models.runbook_execution import RunbookExecutionRecord
        from app.models.runbook_approval import RunbookApproval
        assert s.query(RunbookExecutionRecord).filter(
            RunbookExecutionRecord.alarm_id == 101).count() == 1  # 零新记录
        assert s.query(RunbookApproval).filter(
            RunbookApproval.alarm_id == 101).count() == 0  # 零新审批
        s.close()

    def test_pending_approval_blocks_reexecute(self, test_db):
        s = test_db["session"]
        _seed_record(s, 102, "pending_approval")

        engine = RunbookEngine()
        called = []
        engine._execute_step = lambda step, info: called.append(step.step_id)

        res = engine.execute(
            alarm_id=102,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info=_dev(),
            db=s,
        )
        assert res["status"] == "deduplicated"
        assert res["original_status"] == "pending_approval"
        assert called == []

        from app.models.runbook_execution import RunbookExecutionRecord
        assert s.query(RunbookExecutionRecord).filter(
            RunbookExecutionRecord.alarm_id == 102).count() == 1
        s.close()

    def test_completed_allows_reexecute(self, test_db):
        # 终态历史不挡 → 手动重跑语义保留
        s = test_db["session"]
        _seed_record(s, 103, "completed")

        engine = RunbookEngine()
        def fake_exec(step, info):
            step.status = RunbookStatus.COMPLETED
        engine._execute_step = fake_exec

        res = engine.execute(
            alarm_id=103,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info=_dev(),
            db=s,
        )
        assert res["status"] != "deduplicated"
        assert res["runbook_id"].startswith("RB-103-")

        from app.models.runbook_execution import RunbookExecutionRecord
        assert s.query(RunbookExecutionRecord).filter(
            RunbookExecutionRecord.alarm_id == 103).count() == 2  # 新记录已建
        s.close()

    def test_failed_allows_reexecute(self, test_db):
        s = test_db["session"]
        _seed_record(s, 104, "failed")

        engine = RunbookEngine(dry_run=True)
        res = engine.execute(
            alarm_id=104,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info=_dev(),
            db=s,
        )
        assert res["status"] != "deduplicated"
        s.close()

    def test_no_db_no_dedup(self):
        # 无 db (轻量调用路径) 不做去重, 行为不变
        engine = RunbookEngine(dry_run=True)
        res = engine.execute(
            alarm_id=1,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info=_dev(),
        )
        assert res["status"] == RunbookStatus.COMPLETED


class TestApprovalDedup:
    def test_pending_same_step_not_recreated(self, test_db):
        from app.api.v1.runbook_approval import create_approval_request
        from app.models.runbook_approval import RunbookApproval

        s = test_db["session"]
        kw = dict(
            alarm_id=201, step_index=3, step_description="重启设备",
            action_type="remote_command", command_preview="reboot",
            risk_level=RiskLevel.MEDIUM,
        )
        a1 = create_approval_request(db=s, runbook_id="RB-201-a", **kw)
        a2 = create_approval_request(
            db=s, runbook_id="RB-201-a", alarm_id=201, step_index=3,
            step_description="重启设备", action_type="remote_command",
            command_preview="reboot", risk_level=RiskLevel.MEDIUM,
        )
        assert a2.id == a1.id  # 返回已有 pending, 不新建
        assert s.query(RunbookApproval).filter(
            RunbookApproval.runbook_id == "RB-201-a",
            RunbookApproval.step_index == 3,
        ).count() == 1
        s.close()

    def test_different_step_creates_new(self, test_db):
        from app.api.v1.runbook_approval import create_approval_request
        from app.models.runbook_approval import RunbookApproval

        s = test_db["session"]
        create_approval_request(
            db=s, runbook_id="RB-202-a", alarm_id=202, step_index=1,
            step_description="d", action_type="remote_command",
            command_preview="c", risk_level=RiskLevel.MEDIUM,
        )
        create_approval_request(
            db=s, runbook_id="RB-202-a", alarm_id=202, step_index=2,
            step_description="d", action_type="remote_command",
            command_preview="c", risk_level=RiskLevel.MEDIUM,
        )
        assert s.query(RunbookApproval).filter(
            RunbookApproval.runbook_id == "RB-202-a").count() == 2
        s.close()
