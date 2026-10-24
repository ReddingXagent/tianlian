"""Runbook 模板库 — 从原 runbook_engine.py 拆出 (卡 1ed83abf)。

对外符号 ``RunbookTemplate`` 由包 ``__init__`` 重导出, import 路径不变。
"""
import logging
from typing import Dict, Optional

from .models import RunbookStep, RunbookActionType, RiskLevel


logger = logging.getLogger(__name__)


# ========== Runbook 模板库 ==========

class RunbookTemplate:
    """
    Runbook模板库 - 针对不同类型故障的标准化修复流程

    每个模板包含:
    - 触发条件: 匹配诊断结果的fault_type
    - 执行步骤: 自动+人工步骤
    - 风险评估: 每个步骤的风险等级
    """

    TEMPLATES: Dict[str, Dict] = {
        # --- 逆变器类 ---
        "逆变器通讯中断": {
            "category": "inverter",
            "description": "逆变器通讯中断自动修复",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="检查逆变器网络连通性",
                    command="ping -c 3 {device_ip} && echo OK || echo FAIL",
                    risk_level=RiskLevel.LOW, timeout_sec=15,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.RESTART_SERVICE,
                    description="重启逆变器通讯模块",
                    command="systemctl restart modbus-gateway && sleep 3 && systemctl status modbus-gateway --no-pager",
                    risk_level=RiskLevel.LOW, timeout_sec=30,
                    rollback_command="systemctl stop modbus-gateway",
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=3, action_type=RunbookActionType.WAIT_AND_RECHECK,
                    description="等待60秒后重新读取通讯状态",
                    command="sleep 60 && mosquitto_pub -h localhost -t 'modbus/request' -m '{{\"device_id\": {device_id}, \"action\": \"status\"}}'",
                    risk_level=RiskLevel.LOW, timeout_sec=75,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=4, action_type=RunbookActionType.CREATE_WORKORDER,
                    description="通讯仍不通, 派发巡检工单",
                    risk_level=RiskLevel.LOW,
                    auto_execute=False,
                    params={"urgency": "high", "type": "巡检"}
                ),
            ]
        },
        "逆变器过温告警": {
            "category": "inverter",
            "description": "逆变器过温告警处理",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="读取当前温度传感器数据",
                    command="mosquitto_sub -h localhost -t 'telemetry/{device_sn}/temperature' -C 1 -W 10",
                    risk_level=RiskLevel.LOW, timeout_sec=15,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.CONFIG_CHANGE,
                    description="降低逆变器输出功率至80%",
                    command="mosquitto_pub -h localhost -t 'modbus/write/{device_sn}' -m '{{\"register\": \"power_limit\", \"value\": 80}}'",
                    risk_level=RiskLevel.MEDIUM, timeout_sec=15,
                    rollback_command="mosquitto_pub -h localhost -t 'modbus/write/{device_sn}' -m '{{\"register\": \"power_limit\", \"value\": 100}}'",
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=3, action_type=RunbookActionType.SEND_NOTIFICATION,
                    description="通知运维人员检查散热风扇",
                    auto_execute=False,
                    params={"message": "逆变器{device_name}过温告警,已自动降功率,请检查散热系统", "urgency": "medium"}
                ),
            ]
        },
        "逆变器绝缘阻抗低": {
            "category": "inverter",
            "description": "绝缘阻抗低 - 需人工介入",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="读取绝缘阻抗实时数据",
                    command="mosquitto_sub -h localhost -t 'telemetry/{device_sn}/insulation' -C 1 -W 10",
                    risk_level=RiskLevel.LOW, timeout_sec=15,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.RESTART_SERVICE,
                    description="尝试重启逆变器恢复",
                    command="mosquitto_pub -h localhost -t 'modbus/write/{device_sn}' -m '{{\"register\": \"restart\", \"value\": 1}}'",
                    risk_level=RiskLevel.MEDIUM, timeout_sec=30,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=3, action_type=RunbookActionType.CREATE_WORKORDER,
                    description="派发现场检测工单",
                    auto_execute=False,
                    params={"urgency": "high", "type": "绝缘检测", "message": "绝缘阻抗低告警,需现场检测电缆和接线"}
                ),
            ]
        },
        # --- 充电桩类 ---
        "充电桩通讯异常": {
            "category": "charger",
            "description": "充电桩通讯异常自动修复",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="检查充电桩网络连通性",
                    command="ping -c 3 {device_ip} && echo OK || echo FAIL",
                    risk_level=RiskLevel.LOW, timeout_sec=15,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.RESTART_SERVICE,
                    description="重启充电桩网关服务",
                    command="systemctl restart charger-gateway && sleep 3 && systemctl status charger-gateway --no-pager",
                    risk_level=RiskLevel.LOW, timeout_sec=30,
                    rollback_command="systemctl stop charger-gateway",
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=3, action_type=RunbookActionType.CREATE_WORKORDER,
                    description="通讯仍不通, 派发检修工单",
                    risk_level=RiskLevel.LOW,
                    auto_execute=False,
                    params={"urgency": "medium", "type": "检修"}
                ),
            ]
        },
        "充电桩急停触发": {
            "category": "charger",
            "description": "急停触发 - 必须人工处理",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="确认急停状态",
                    command="mosquitto_sub -h localhost -t 'telemetry/{device_sn}/emergency' -C 1 -W 10",
                    risk_level=RiskLevel.LOW, timeout_sec=15,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.SEND_NOTIFICATION,
                    description="紧急通知运维人员到现场",
                    auto_execute=False,
                    params={"urgency": "critical", "message": "充电桩{device_name}急停触发,请立即到现场处理"}
                ),
                RunbookStep(
                    step_id=3, action_type=RunbookActionType.CREATE_WORKORDER,
                    description="创建紧急工单",
                    auto_execute=False,
                    params={"urgency": "critical", "type": "紧急检修", "message": "急停触发需现场排查"}
                ),
            ]
        },
        # --- 储能PCS类 ---
        "PCS通讯异常": {
            "category": "pcs",
            "description": "储能PCS通讯异常自动修复",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="检查PCS网关连通性",
                    command="ping -c 3 {device_ip} && echo OK || echo FAIL",
                    risk_level=RiskLevel.LOW, timeout_sec=15,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.RESTART_SERVICE,
                    description="重启PCS通讯网关",
                    command="systemctl restart pcs-gateway && sleep 5 && systemctl status pcs-gateway --no-pager",
                    risk_level=RiskLevel.MEDIUM, timeout_sec=30,
                    rollback_command="systemctl stop pcs-gateway",
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=3, action_type=RunbookActionType.WAIT_AND_RECHECK,
                    description="等待60秒后重查PCS状态",
                    command="sleep 60 && mosquitto_pub -h localhost -t 'pcs/request' -m '{{\"device_id\": {device_id}, \"action\": \"status\"}}'",
                    risk_level=RiskLevel.LOW, timeout_sec=75,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=4, action_type=RunbookActionType.CREATE_WORKORDER,
                    description="PCS通讯未恢复, 派发检修工单",
                    risk_level=RiskLevel.LOW,
                    auto_execute=False,
                    params={"urgency": "high", "type": "PCS检修"}
                ),
            ]
        },
        "BMS电池告警": {
            "category": "bms",
            "description": "BMS电池管理系统告警处理",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="读取BMS电池组状态数据",
                    command="mosquitto_sub -h localhost -t 'telemetry/{device_sn}/bms_status' -C 1 -W 10",
                    risk_level=RiskLevel.LOW, timeout_sec=15,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.CONFIG_CHANGE,
                    description="降低充放电功率至安全范围",
                    command="mosquitto_pub -h localhost -t 'bms/write/{device_sn}' -m '{{\"register\": \"power_limit\", \"value\": 50}}'",
                    risk_level=RiskLevel.HIGH, timeout_sec=15,
                    rollback_command="mosquitto_pub -h localhost -t 'bms/write/{device_sn}' -m '{{\"register\": \"power_limit\", \"value\": 100}}'",
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=3, action_type=RunbookActionType.SEND_NOTIFICATION,
                    description="通知运维人员检查电池组状态",
                    auto_execute=False,
                    params={"message": "BMS告警: 电池组{device_name}异常, 已降功率运行, 请尽快检查", "urgency": "high"}
                ),
                RunbookStep(
                    step_id=4, action_type=RunbookActionType.CREATE_WORKORDER,
                    description="派发电池检测工单",
                    auto_execute=False,
                    params={"urgency": "high", "type": "电池检测", "message": "BMS告警需现场检测电池模组"}
                ),
            ]
        },
        "EMS调度异常": {
            "category": "ems",
            "description": "能量管理系统调度异常处理",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="检查EMS服务进程状态",
                    command="systemctl status ems-scheduler --no-pager",
                    risk_level=RiskLevel.LOW, timeout_sec=10,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.RESTART_SERVICE,
                    description="重启EMS调度服务",
                    command="systemctl restart ems-scheduler && sleep 5 && systemctl status ems-scheduler --no-pager",
                    risk_level=RiskLevel.HIGH, timeout_sec=30,
                    rollback_command="systemctl stop ems-scheduler",
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=3, action_type=RunbookActionType.WAIT_AND_RECHECK,
                    description="等待30秒后检查调度恢复",
                    command="sleep 30 && curl -sf http://localhost:8081/api/ems/status || echo EMS_DOWN",
                    risk_level=RiskLevel.LOW, timeout_sec=45,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=4, action_type=RunbookActionType.SEND_NOTIFICATION,
                    description="通知值班人员EMS调度异常",
                    auto_execute=False,
                    params={"message": "EMS调度异常, 已尝试自动重启, 请关注系统状态", "urgency": "critical"}
                ),
            ]
        },
        "储能系统过充过放": {
            "category": "ess",
            "description": "储能系统过充/过放保护处理",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="读取SOC和充放电状态",
                    command="mosquitto_sub -h localhost -t 'telemetry/{device_sn}/soc' -C 1 -W 10",
                    risk_level=RiskLevel.LOW, timeout_sec=15,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.CONFIG_CHANGE,
                    description="紧急停止充放电",
                    command="mosquitto_pub -h localhost -t 'ess/control/{device_sn}' -m '{{\"action\": \"stop_charge_discharge\"}}'",
                    risk_level=RiskLevel.CRITICAL, timeout_sec=10,
                    rollback_command="mosquitto_pub -h localhost -t 'ess/control/{device_sn}' -m '{{\"action\": \"resume\"}}'",
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=3, action_type=RunbookActionType.SEND_NOTIFICATION,
                    description="紧急通知运维人员",
                    auto_execute=False,
                    params={"urgency": "critical", "message": "储能系统{device_name}过充/过放保护触发, 已紧急停止充放电, 请立即检查"}
                ),
                RunbookStep(
                    step_id=4, action_type=RunbookActionType.CREATE_WORKORDER,
                    description="创建紧急检修工单",
                    auto_execute=False,
                    params={"urgency": "critical", "type": "紧急检修", "message": "过充过放保护, 需现场检查电池和PCS"}
                ),
            ]
        },
        # --- 通用类 ---
        "设备离线": {
            "category": "general",
            "description": "设备离线自动排查",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="Ping检测",
                    command="ping -c 5 -W 2 {device_ip} && echo ONLINE || echo OFFLINE",
                    risk_level=RiskLevel.LOW, timeout_sec=20,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="检查端口状态",
                    command="nc -z -w 3 {device_ip} 502 && echo PORT_OPEN || echo PORT_CLOSED",
                    risk_level=RiskLevel.LOW, timeout_sec=10,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=3, action_type=RunbookActionType.CREATE_WORKORDER,
                    description="设备完全离线, 派发现场巡检",
                    auto_execute=False,
                    params={"urgency": "high", "type": "现场巡检"}
                ),
            ]
        },
    }

    @classmethod
    def match(cls, fault_type: str, device_type: str = "") -> Optional[Dict]:
        """根据故障类型匹配Runbook模板

        顶层异常保护: 意外异常 → 记录 logger.exception 并返回 None, 让调用方
        (engine.py:138-143) 回退 get_default。
        """
        try:
            return cls._match_impl(fault_type, device_type)
        except Exception:
            logger.exception(
                "Runbook 模板匹配异常, 返回 None(回退默认), fault_type=%s",
                fault_type,
            )
            return None

    @classmethod
    def _match_impl(cls, fault_type: str, device_type: str = "") -> Optional[Dict]:
        """match 的实现 (异常保护由 match 顶层兜底)。"""
        # 精确匹配
        if fault_type in cls.TEMPLATES:
            return cls.TEMPLATES[fault_type]

        # 模糊匹配 - 关键词
        for template_name, template in cls.TEMPLATES.items():
            if fault_type and any(kw in template_name for kw in fault_type.split()):
                return template

        # 设备类型兜底
        category_map = {
            "inverter": "逆变器通讯中断",
            "charger": "充电桩通讯异常",
            "pcs": "PCS通讯异常",
            "bms": "BMS电池告警",
            "ems": "EMS调度异常",
            "ess": "储能系统过充过放",
        }
        if device_type and device_type.lower() in category_map:
            return cls.TEMPLATES.get(category_map[device_type.lower()])

        return None

    @classmethod
    def get_default(cls) -> Dict:
        """默认Runbook模板

        顶层异常保护: 意外异常 → 记录 logger.exception 并返回最小通用模板
        (含 ``steps`` key, engine 后续 ``template["steps"]`` 解引用安全)。
        """
        try:
            return cls._get_default_impl()
        except Exception:
            logger.exception("Runbook 默认模板构造异常, 返回最小通用模板")
            return {
                "category": "general",
                "description": "通用故障处理流程(异常降级)",
                "steps": [],
            }

    @classmethod
    def _get_default_impl(cls) -> Dict:
        """get_default 的实现 (异常保护由 get_default 顶层兜底)。"""
        return {
            "category": "general",
            "description": "通用故障处理流程",
            "steps": [
                RunbookStep(
                    step_id=1, action_type=RunbookActionType.REMOTE_COMMAND,
                    description="检查设备状态",
                    command="echo '检查设备 {device_id} 状态'",
                    risk_level=RiskLevel.LOW, timeout_sec=30,
                    auto_execute=True
                ),
                RunbookStep(
                    step_id=2, action_type=RunbookActionType.CREATE_WORKORDER,
                    description="创建诊断工单",
                    auto_execute=False,
                    params={"urgency": "medium", "type": "故障排查"}
                ),
            ]
        }
