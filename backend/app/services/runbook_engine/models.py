"""Runbook 枚举与数据模型 — 从原 runbook_engine.py 拆出 (卡 1ed83abf)。

对外符号 RunbookActionType / RunbookStatus / RiskLevel / RunbookStep /
RunbookExecution 由包 ``__init__`` 重导出, import 路径不变。
"""
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, field
from enum import Enum


# ========== 枚举 ==========

class RunbookActionType(str, Enum):
    """Runbook动作类型"""
    REMOTE_COMMAND = "remote_command"     # 远程SSH命令
    API_CALL = "api_call"                  # 调用设备API
    CONFIG_CHANGE = "config_change"        # 配置变更
    RESTART_SERVICE = "restart_service"    # 重启服务
    RESET_PARAMETER = "reset_parameter"    # 重置参数
    CLEAR_CACHE = "clear_cache"            # 清除缓存
    CREATE_WORKORDER = "create_workorder"  # 创建工单(需人工)
    SEND_NOTIFICATION = "send_notification" # 发送通知
    WAIT_AND_RECHECK = "wait_and_recheck"  # 等待后重新检查


class RunbookStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class RiskLevel(str, Enum):
    LOW = "low"           # 自动执行, 无需审批
    MEDIUM = "medium"     # 需简单确认
    HIGH = "high"         # 需审批
    CRITICAL = "critical" # 需高级审批


# ========== 数据模型 ==========

@dataclass
class RunbookStep:
    """Runbook执行步骤"""
    step_id: int
    action_type: str
    description: str
    command: str = ""           # 执行命令/API调用参数
    params: dict = field(default_factory=dict)
    risk_level: str = "low"
    timeout_sec: int = 60
    rollback_command: str = ""  # 回滚命令
    pre_check: str = ""         # 前置检查命令
    post_check: str = ""        # 后置验证命令
    auto_execute: bool = True   # 是否自动执行(需人工的设为False)
    trusted: bool = False       # 内置硬编码可信模板标记(True 时允许 &&/|| 等 shell 操作符)
    status: str = "pending"
    result: str = ""
    duration_ms: int = 0
    error_message: str = ""


@dataclass
class RunbookExecution:
    """Runbook执行上下文"""
    runbook_id: str
    alarm_id: int
    diagnosis_record_id: Optional[int] = None
    device_id: int = 0
    station_id: int = 0
    fault_type: str = ""
    status: str = "pending"
    steps: List[RunbookStep] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_duration_ms: int = 0
    success_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    auto_executed: int = 0
    manual_required: int = 0
    workorder_id: Optional[int] = None
    error_message: str = ""
