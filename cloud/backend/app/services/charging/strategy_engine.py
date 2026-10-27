"""充电策略引擎调度器 — 模式管理 / 切换 / 优先级 / 冲突解决

StrategyEngine 负责:
- 注册并持有全部充电策略实例
- 维护全局默认模式 + 按站点覆盖模式
- 模式切换(字符串/枚举, 校验非法值)
- 优先级排序(list_strategies)
- 冲突解决(resolve): 手动指令抢占当前模式, 否则按当前模式评估
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

from app.services.charging.strategy_base import (
    ChargingContext,
    ChargingDecision,
    ChargingMode,
    ChargingStrategy,
)
from app.services.charging.mode_manual import ManualStrategy
from app.services.charging.mode_timed import TimedStrategy
from app.services.charging.mode_solar import SolarStrategy
from app.services.charging.mode_price import PriceStrategy
from app.services.charging.mode_balanced import BalancedStrategy


ModeLike = Union[ChargingMode, str]


class StrategyEngine:
    """充电策略引擎调度器"""

    def __init__(self, default_mode: ChargingMode = ChargingMode.BALANCED):
        self.strategies: Dict[ChargingMode, ChargingStrategy] = {
            ChargingMode.MANUAL: ManualStrategy(),
            ChargingMode.TIMED: TimedStrategy(),
            ChargingMode.SOLAR: SolarStrategy(),
            ChargingMode.PRICE: PriceStrategy(),
            ChargingMode.BALANCED: BalancedStrategy(),
        }
        self._default_mode = default_mode
        self._global_mode: ChargingMode = default_mode
        self._station_modes: Dict[str, ChargingMode] = {}
        self._switched_at: Optional[str] = None

    # ─── 当前模式 ───

    @property
    def current_mode(self) -> ChargingMode:
        """全局当前模式"""
        return self._global_mode

    @property
    def last_switched_at(self) -> Optional[str]:
        """最近一次模式切换的 ISO 时间戳"""
        return self._switched_at

    def get_current_mode(self, station_id: Optional[str] = None) -> ChargingMode:
        """获取生效模式: 站点级覆盖优先, 否则全局"""
        if station_id and station_id in self._station_modes:
            return self._station_modes[station_id]
        return self._global_mode

    # ─── 模式切换 ───

    def switch_mode(
        self,
        mode: ModeLike,
        station_id: Optional[str] = None,
    ) -> ChargingMode:
        """切换模式(可按站点)。非法模式抛 ValueError。"""
        resolved = self._resolve_mode(mode)
        self._switched_at = datetime.now(timezone.utc).isoformat()
        if station_id:
            self._station_modes[station_id] = resolved
        else:
            self._global_mode = resolved
        return resolved

    def get_strategy(self, mode: ModeLike) -> ChargingStrategy:
        """按模式取策略实例"""
        return self.strategies[self._resolve_mode(mode)]

    # ─── 列举 / 优先级 ───

    def list_strategies(self) -> List[Dict]:
        """按优先级升序返回所有策略描述"""
        items = [
            {
                "mode": s.mode.value,
                "name": s.name,
                "description": s.description,
                "priority": s.priority,
            }
            for s in self.strategies.values()
        ]
        return sorted(items, key=lambda x: x["priority"])

    # ─── 评估 ───

    def evaluate(
        self,
        ctx: ChargingContext,
        mode: Optional[ModeLike] = None,
    ) -> ChargingDecision:
        """用指定模式评估; 未指定则用站点/全局当前模式"""
        if mode is None:
            resolved = self.get_current_mode(ctx.station_id)
        else:
            resolved = self._resolve_mode(mode)
        return self.strategies[resolved].evaluate(ctx)

    def resolve(self, ctx: ChargingContext) -> ChargingDecision:
        """冲突解决: 上下文含手动指令时手动模式抢占, 否则用当前模式"""
        if ctx.manual_power_kw is not None:
            return self.strategies[ChargingMode.MANUAL].evaluate(ctx)
        return self.evaluate(ctx)

    # ─── 内部 ───

    @staticmethod
    def _resolve_mode(mode: ModeLike) -> ChargingMode:
        if isinstance(mode, ChargingMode):
            return mode
        try:
            return ChargingMode(mode)
        except ValueError:
            raise ValueError(
                f"无效充电模式: {mode} (支持: "
                + "/".join(m.value for m in ChargingMode)
                + ")"
            )


# ─── 单例 ───

_engine: Optional[StrategyEngine] = None
_lock = threading.Lock()


def get_charging_engine() -> StrategyEngine:
    """获取充电策略引擎单例 (双重检查锁, 线程安全)"""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = StrategyEngine()
    return _engine
