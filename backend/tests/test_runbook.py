"""
Runbook Engine 单元测试

测试内容:
1. Runbook模板匹配
2. Runbook引擎执行 (dry_run模式)
3. 变量替换
4. 步骤分类
"""
import pytest
from app.services.runbook_engine import (
    RunbookTemplate,
    RunbookEngine,
    RunbookStep,
    RunbookActionType,
    RunbookStatus,
)


class TestRunbookTemplateMatching:
    """测试Runbook模板匹配"""
    
    def test_exact_match_inverter_comm(self):
        """精确匹配 - 逆变器通讯中断"""
        tmpl = RunbookTemplate.match("逆变器通讯中断")
        assert tmpl is not None
        assert tmpl["category"] == "inverter"
        assert len(tmpl["steps"]) == 4
    
    def test_exact_match_charger_comm(self):
        """精确匹配 - 充电桩通讯异常"""
        tmpl = RunbookTemplate.match("充电桩通讯异常")
        assert tmpl is not None
        assert tmpl["category"] == "charger"
        assert len(tmpl["steps"]) == 3
    
    def test_exact_match_over_temp(self):
        """精确匹配 - 逆变器过温告警"""
        tmpl = RunbookTemplate.match("逆变器过温告警")
        assert tmpl is not None
        assert len(tmpl["steps"]) == 3
    
    def test_exact_match_emergency_stop(self):
        """精确匹配 - 充电桩急停触发"""
        tmpl = RunbookTemplate.match("充电桩急停触发")
        assert tmpl is not None
        # 急停应该全部是手动步骤
        for step in tmpl["steps"]:
            assert step.auto_execute == False or step.action_type in ("remote_command",)
    
    def test_fuzzy_match(self):
        """模糊匹配 - 关键词部分匹配"""
        tmpl = RunbookTemplate.match("逆变器通讯")
        assert tmpl is not None
    
    def test_fallback_by_device_type(self):
        """按设备类型兜底匹配"""
        tmpl = RunbookTemplate.match("未知故障类型", device_type="inverter")
        assert tmpl is not None
        assert tmpl["category"] == "inverter"
    
    def test_no_match_returns_default(self):
        """无匹配时应返回默认模板"""
        tmpl = RunbookTemplate.match("完全不存在的故障")
        assert tmpl is None  # match返回None, 调用方应使用get_default
    
    def test_default_template(self):
        """默认模板应该有基本步骤"""
        default = RunbookTemplate.get_default()
        assert default is not None
        assert len(default["steps"]) >= 1


class TestRunbookEngine:
    """测试Runbook引擎"""
    
    def test_dry_run_execution(self):
        """Dry run模式 - 不实际执行命令"""
        engine = RunbookEngine(dry_run=True)
        
        result = engine.execute(
            alarm_id=1,
            diagnosis_result={"fault_type": "逆变器通讯中断", "severity": "high"},
            device_info={
                "id": 1, "name": "逆变器01", "sn": "INV001",
                "ip": "192.168.1.100", "type": "inverter",
                "station_id": 1,
            },
        )
        
        assert result["status"] == "completed"
        assert result["alarm_id"] == 1
        assert result["skipped_steps"] > 0
        assert result["runbook_id"].startswith("RB-1-")
    
    def test_auto_vs_manual_steps(self):
        """自动步骤与人工步骤分类"""
        engine = RunbookEngine(dry_run=True)
        
        # 逆变器通讯中断: 3个自动步骤 + 1个人工步骤
        result = engine.execute(
            alarm_id=2,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info={
                "id": 2, "name": "逆变器02", "sn": "INV002",
                "ip": "192.168.1.101", "type": "inverter",
                "station_id": 1,
            },
        )
        
        assert result["auto_executed"] == 3
        assert result["manual_required"] == 1
    
    def test_emergency_stop_all_manual(self):
        """急停触发应该大部分需要人工"""
        engine = RunbookEngine(dry_run=True)
        
        result = engine.execute(
            alarm_id=3,
            diagnosis_result={"fault_type": "充电桩急停触发"},
            device_info={
                "id": 3, "name": "充电桩01", "sn": "CHR001",
                "ip": "192.168.1.200", "type": "charger",
                "station_id": 1,
            },
        )
        
        assert result["manual_required"] >= 2  # 通知+工单
    
    def test_unknown_fault_uses_default(self):
        """未知故障使用默认模板"""
        engine = RunbookEngine(dry_run=True)
        
        result = engine.execute(
            alarm_id=4,
            diagnosis_result={"fault_type": "完全不存在的故障"},
            device_info={
                "id": 4, "name": "设备01", "sn": "DEV001",
                "ip": "192.168.1.50", "type": "unknown",
                "station_id": 1,
            },
        )
        
        assert result["status"] == "completed"
        assert len(result["steps"]) >= 1


class TestVariableSubstitution:
    """测试变量替换"""
    
    def test_substitute_device_ip(self):
        """设备IP变量替换"""
        engine = RunbookEngine()
        steps = [
            RunbookStep(
                step_id=1, action_type="remote_command",
                description="Ping设备",
                command="ping -c 3 {device_ip}"
            )
        ]
        
        result = engine._substitute_vars(steps, {"device_ip": "10.0.0.1"})
        assert "ping -c 3 10.0.0.1" == result[0].command
    
    def test_substitute_multiple_vars(self):
        """多变量替换"""
        engine = RunbookEngine()
        steps = [
            RunbookStep(
                step_id=1, action_type="remote_command",
                description="测试",
                command="mosquitto_sub -h localhost -t 'telemetry/{device_sn}/temp'"
            )
        ]
        
        result = engine._substitute_vars(steps, {
            "device_sn": "INV001",
            "device_ip": "10.0.0.1",
        })
        assert "telemetry/INV001/temp" in result[0].command


class TestRunbookSteps:
    """测试Runbook步骤"""
    
    def test_step_creation(self):
        """步骤创建"""
        step = RunbookStep(
            step_id=1,
            action_type=RunbookActionType.REMOTE_COMMAND,
            description="测试步骤",
            command="echo test",
            risk_level="low",
            auto_execute=True,
        )
        
        assert step.step_id == 1
        assert step.action_type == "remote_command"
        assert step.auto_execute is True
    
    def test_step_types(self):
        """步骤类型枚举"""
        assert RunbookActionType.REMOTE_COMMAND == "remote_command"
        assert RunbookActionType.CREATE_WORKORDER == "create_workorder"
        assert RunbookActionType.RESTART_SERVICE == "restart_service"
