"""
充电策略引擎 — 接口与数据模型

定义 5 种充电模式共享的契约:
- ChargingMode: 模式枚举
- ChargingContext: 决策输入(场站/桩/需求/光伏/储能/电价/时段)
- ChargingDecision: 决策输出(目标功率 + 三源功率 + 来源 + 原因)
- ChargingStrategy: 抽象基类(evaluate / get_mode / priority)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ChargingMode(str, Enum):
    """充电模式"""
    MANUAL = "manual"        # 手动: 用户直接指定功率
    TIMED = "timed"          # 定时: 峰谷时段调度(低谷充、高峰停)
    SOLAR = "solar"          # 光伏优先: 余电充、不足降功率
    PRICE = "price"          # 电价优先: 低谷时段集中充电
    BALANCED = "balanced"    # 均衡: 光伏+储能+电网三源协同


@dataclass
class ChargingContext:
    """充电决策上下文(策略评估的唯一输入)"""
    station_id: str
    charger_id: str
    rated_power_kw: float                       # 充电桩额定功率
    demand_power_kw: float = 0.0                # 车辆充电需求功率
    current_soc: Optional[float] = None         # 车辆电池 SOC (0-1)
    target_soc: Optional[float] = None          # 目标 SOC
    # 光伏
    pv_output_kw: float = 0.0                   # 当前光伏出力
    # 储能
    battery_soc: Optional[float] = None         # 储能 SOC (0-1)
    battery_capacity_kwh: float = 0.0           # 储能容量
    battery_available_kw: float = 0.0           # 储能可放电功率
    battery_temp_c: Optional[float] = None      # 储能温度(℃)
    # 电网
    grid_price: Optional[float] = None          # 实时电价(元/kWh)
    grid_power_limit_kw: Optional[float] = None # 电网取电上限
    # 辅助参数
    in_valley_period: Optional[bool] = None     # 当前是否低谷时段(timed/price 用)
    manual_power_kw: Optional[float] = None     # 手动指定功率(manual 用)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ChargingDecision:
    """充电决策结果

    功率约定: target_power_kw = pv_power_kw + battery_power_kw + grid_power_kw
    各源功率均 >= 0(本决策只描述"能量从哪来",不描述回馈)。
    """
    mode: ChargingMode
    target_power_kw: float = 0.0
    pv_power_kw: float = 0.0       # 来自光伏
    battery_power_kw: float = 0.0  # 来自储能放电
    grid_power_kw: float = 0.0     # 来自电网
    source: str = "grid"           # pv / battery / grid / mixed
    curtailed: bool = False        # 是否相对需求降了功率
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def reconcile_source(self) -> None:
        """根据各源功率推断 source 标签,并钳位目标功率为各源之和"""
        active = []
        if self.pv_power_kw > 1e-9:
            active.append("pv")
        if self.battery_power_kw > 1e-9:
            active.append("battery")
        if self.grid_power_kw > 1e-9:
            active.append("grid")
        if len(active) == 0:
            self.source = "none"
        elif len(active) == 1:
            self.source = active[0]
        else:
            self.source = "mixed"
        self.target_power_kw = round(
            self.pv_power_kw + self.battery_power_kw + self.grid_power_kw, 4
        )


class ChargingStrategy(ABC):
    """充电策略抽象基类

    每个具体策略实现 evaluate(): 读 ChargingContext, 返回 ChargingDecision。
    priority 决定在自动/冲突场景下的抢占顺序(1 最高)。
    """

    @property
    @abstractmethod
    def mode(self) -> ChargingMode:
        """策略对应模式"""

    @property
    @abstractmethod
    def priority(self) -> int:
        """调度优先级(数字越小优先级越高)"""

    @property
    def name(self) -> str:
        """人类可读名称"""
        return _MODE_NAMES.get(self.mode, self.mode.value)

    @property
    def description(self) -> str:
        return _MODE_DESCRIPTIONS.get(self.mode, "")

    @abstractmethod
    def evaluate(self, ctx: ChargingContext) -> ChargingDecision:
        """评估上下文返回充电决策"""

    def get_mode(self) -> ChargingMode:
        """返回策略模式(供引擎/路由统一访问)"""
        return self.mode

    # ─── 工具方法 ───

    @staticmethod
    def clamp_power(power: float, rated: float) -> float:
        """功率钳位到 [0, rated]"""
        if power < 0:
            return 0.0
        if rated < 0:
            return 0.0
        return min(power, rated)


_MODE_NAMES = {
    ChargingMode.MANUAL: "手动模式",
    ChargingMode.TIMED: "定时模式",
    ChargingMode.SOLAR: "光伏优先",
    ChargingMode.PRICE: "电价优先",
    ChargingMode.BALANCED: "均衡模式",
}

_MODE_DESCRIPTIONS = {
    ChargingMode.MANUAL: "由用户直接指定充电功率,策略不做自动调整",
    ChargingMode.TIMED: "依据峰谷时段调度:低谷时段满功率充电,高峰时段停充以降低成本",
    ChargingMode.SOLAR: "光伏优先:光伏出力大于充电需求时按需求充,否则降功率至光伏水平",
    ChargingMode.PRICE: "电价优先:在实时电价最低的时段集中充电,高电价时段暂停",
    ChargingMode.BALANCED: "光伏+储能+电网三源均衡:优先消纳光伏,其次储能,不足取电网",
}
