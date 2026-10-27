"""
虚拟电厂(VPP)调度优化服务 — 数据模型与枚举

原 app/services/vpp/dispatch_optimizer.py(1138行) 按职责拆分而来(卡 61109a8a)。
本模块定义 VPP 调度所需的全部数据结构, 无业务逻辑, 仅依赖标准库。
"""
from typing import List, Optional
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field


# ─── 数据模型 ───

class ResourceType(str, Enum):
    PV = "pv"             # 光伏
    BATTERY = "battery"   # 储能
    EV_CHARGER = "ev"     # 充电桩
    LOAD = "load"         # 可调负荷


class DispatchMode(str, Enum):
    ECONOMIC = "economic"           # 经济调度(峰谷套利)
    PEAK_SHAVING = "peak_shaving"   # 削峰填谷
    DEMAND_RESPONSE = "demand_response"  # 需求响应
    GRID_SUPPORT = "grid_support"   # 电网支撑
    EMERGENCY = "emergency"         # 应急调度


class GridSignalType(str, Enum):
    PRICE = "price"                 # 电价信号
    DEMAND_RESPONSE = "demand_response"  # 需求响应邀约
    FREQUENCY_REGULATION = "frequency_regulation"  # 调频
    PEAK_ALERT = "peak_alert"       # 峰值预警
    EMERGENCY = "emergency"         # 紧急调度


@dataclass
class ResourceCapability:
    """单个资源的能力描述"""
    resource_id: str
    resource_type: ResourceType
    station_id: str
    rated_power_kw: float          # 额定功率
    current_power_kw: float        # 当前功率
    available_power_kw: float      # 可调度功率
    soc: Optional[float] = None    # 储能SOC (0-1), 仅battery
    efficiency: float = 0.95       # 转换效率
    min_power_kw: float = 0.0      # 最小功率
    ramp_rate_kw_per_min: float = 100.0  # 爬坡速率
    priority: int = 5              # 调度优先级(1最高)
    cost_per_kwh: float = 0.0      # 边际成本


@dataclass
class GridSignal:
    """电网调度信号"""
    signal_type: GridSignalType
    timestamp: datetime
    target_power_kw: Optional[float] = None    # 目标功率
    duration_min: Optional[int] = None          # 持续时间
    price_per_kwh: Optional[float] = None       # 电价
    reward_per_kwh: Optional[float] = None      # 响应奖励
    penalty_per_kwh: Optional[float] = None     # 未响应惩罚
    urgency: float = 0.5                        # 紧急程度(0-1)


@dataclass
class StationStatus:
    """站点运行状态"""
    station_id: str
    station_name: str
    total_pv_kw: float           # 光伏总装机
    total_battery_kwh: float     # 储能总容量
    total_ev_chargers: int       # 充电桩数量
    current_load_kw: float       # 当前负荷
    current_pv_output_kw: float  # 当前光伏出力
    current_battery_soc: float   # 平均储能SOC
    available_dispatch_kw: float # 可调度容量
    online: bool = True


@dataclass
class DispatchCommand:
    """调度指令"""
    resource_id: str
    station_id: str
    resource_type: ResourceType
    target_power_kw: float       # 目标功率(正=放电/出力, 负=充电/吸收)
    duration_min: int            # 执行时长
    priority: int                # 优先级
    estimated_revenue: float = 0.0   # 预估收益
    estimated_cost: float = 0.0      # 预估成本
    dispatch_mode: DispatchMode = DispatchMode.ECONOMIC
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class DispatchPlan:
    """调度计划"""
    plan_id: str
    mode: DispatchMode
    trigger: str                    # 触发原因
    stations_involved: List[str]    # 参与站点
    commands: List[DispatchCommand] # 调度指令列表
    total_dispatch_kw: float        # 总调度功率
    estimated_revenue: float        # 预估总收益
    estimated_cost: float           # 预估总成本
    net_profit: float               # 净利润
    created_at: datetime = field(default_factory=datetime.now)
    executed: bool = False
