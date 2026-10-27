"""储能调度优化器 — SOC 目标管理 + 充放电策略 + 电池健康保护

调度优先级:
1. 健康保护: SOC<10% 强制充电恢复; SOC>90% 禁充电; 温度>45℃ 禁充电
2. 光伏余电 → 充入储能
3. 电网低谷电价 → 充电(套利)
4. 电网高峰电价 + 有负荷 → 放电供给
5. 否则待机

功率约定: power_kw 正=充电, 负=放电, 0=待机
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass
class StorageAction:
    """储能调度动作"""
    action: str               # charge / discharge / idle
    power_kw: float           # 正=充电, 负=放电
    target_soc: float         # 目标 SOC
    reason: str               # 决策原因
    health_ok: bool           # 电池健康状态是否允许该调度
    within_safe_range: bool   # SOC 是否在安全区间


@dataclass
class StorageOptimizerConfig:
    """StorageOptimizer 可配置参数 (来自 station_energy_strategy.strategy_config)

    strategy_config JSON schema (相关字段):
        {
          "valley_price_threshold": <float>,  # 低谷充电电价阈值 (元/kWh), 默认 0.40
          "peak_price_threshold": <float>,    # 高峰放电电价阈值 (元/kWh), 默认 0.90
          "soc_floor": <float>,               # SOC 下限, 默认 0.10 (对应 station_energy_strategy.soc_floor)
          "soc_ceiling": <float>              # SOC 上限, 默认 0.90
        }
    所有字段可选; 未提供 (或 StorageOptimizer 无 config) 时走类常量默认, 向后兼容。
    """
    valley_price_threshold: float = 0.40
    peak_price_threshold: float = 0.90
    soc_floor: float = 0.10
    soc_ceiling: float = 0.90
    discharge_soc_floor: float = 0.20   # 放电SOC下限(放电需 soc 高于此值, 不低于 0.10)


class StorageOptimizer:
    """储能调度优化器"""

    SOC_MIN = 0.10            # 安全下限
    SOC_MAX = 0.90            # 安全上限
    DISCHARGE_SOC_FLOOR = 0.20   # 放电SOC下限(放电需 soc 高于此值, 绝对不低于 SOC_MIN)
    TARGET_SOC = 0.50         # 默认目标 SOC
    TEMP_MAX_C = 45.0         # 温度上限(℃)
    VALLEY_PRICE = 0.40       # 低谷充电电价阈值(元/kWh)
    PEAK_PRICE = 0.90         # 高峰放电电价阈值(元/kWh)
    DEFAULT_CHARGE_KW = 50.0      # 默认充电功率
    DEFAULT_DISCHARGE_KW = 50.0   # 默认放电功率

    def __init__(self, config: Optional[StorageOptimizerConfig] = None) -> None:
        """注入场站级配置; config=None 时走类常量默认 (向后兼容)。"""
        self._config = config

    @property
    def _soc_floor(self) -> float:
        return self._config.soc_floor if self._config is not None else self.SOC_MIN

    @property
    def _soc_ceiling(self) -> float:
        return self._config.soc_ceiling if self._config is not None else self.SOC_MAX

    @property
    def _valley_price(self) -> float:
        return self._config.valley_price_threshold if self._config is not None else self.VALLEY_PRICE

    @property
    def _peak_price(self) -> float:
        return self._config.peak_price_threshold if self._config is not None else self.PEAK_PRICE

    @property
    def _discharge_soc_floor(self) -> float:
        """放电SOC下限: 动态取 config/常量的较大值, 兜底不低于 SOC_MIN(0.10)"""
        cfg_val = self._config.discharge_soc_floor if self._config is not None else self.DISCHARGE_SOC_FLOOR
        return max(cfg_val, self.SOC_MIN)

    def optimize(
        self,
        soc: float,
        pv_surplus_kw: float = 0.0,
        grid_price: Optional[float] = None,
        load_kw: float = 0.0,
        temp_c: Optional[float] = None,
        target_soc: Optional[float] = None,
    ) -> StorageAction:
        """根据 SOC / 光伏余电 / 电价 / 负荷 / 温度 决策储能动作

        顶层异常保护: 意外异常(ValueError 以外) → 记录 logger.exception 并降级为
        安全待机(idle, power_kw=0), 避免调用方(charging_strategy.py 直接解引用
        action 字段)裸抛 HTTP 500。输入校验 ValueError 属 fail-fast 正常契约,
        保留向上传播, 不被兜底吞掉。
        """
        try:
            return self._optimize(
                soc=soc,
                pv_surplus_kw=pv_surplus_kw,
                grid_price=grid_price,
                load_kw=load_kw,
                temp_c=temp_c,
                target_soc=target_soc,
            )
        except ValueError:
            # 输入校验 fail-fast 是正常流程契约, 不被兜底吞掉
            raise
        except Exception:
            logger.exception(
                "储能调度 optimize 异常, 返回安全待机(idle), soc=%s", soc
            )
            safe_target = target_soc if target_soc is not None else self.TARGET_SOC
            return StorageAction(
                action="idle",
                power_kw=0.0,
                target_soc=safe_target,
                reason="优化过程内部异常, 安全降级为待机",
                health_ok=False,
                within_safe_range=False,
            )

    def _optimize(
        self,
        soc: float,
        pv_surplus_kw: float = 0.0,
        grid_price: Optional[float] = None,
        load_kw: float = 0.0,
        temp_c: Optional[float] = None,
        target_soc: Optional[float] = None,
    ) -> StorageAction:
        """optimize 的纯计算实现 (异常保护由 optimize 顶层兜底)。"""
        # 输入校验: 与 API Query(ge/le) 约束一致, 明确拒绝非法值(fail-fast)
        if not 0.0 <= soc <= 1.0:
            raise ValueError(f"soc 必须在 [0,1] 区间, 实际: {soc}")
        if pv_surplus_kw < 0:
            raise ValueError(f"pv_surplus_kw 不能为负, 实际: {pv_surplus_kw}")
        if load_kw < 0:
            raise ValueError(f"load_kw 不能为负, 实际: {load_kw}")
        if grid_price is not None and grid_price < 0:
            raise ValueError(f"grid_price 不能为负, 实际: {grid_price}")
        if target_soc is not None and not 0.0 <= target_soc <= 1.0:
            raise ValueError(f"target_soc 必须在 [0,1] 区间, 实际: {target_soc}")
        if temp_c is not None and (temp_c < -50 or temp_c > 100):
            raise ValueError(f"temp_c 必须在 [-50,100]℃, 实际: {temp_c}")

        target = target_soc if target_soc is not None else self.TARGET_SOC
        safe = self._soc_floor <= soc <= self._soc_ceiling
        temp_ok = temp_c is None or temp_c <= self.TEMP_MAX_C

        # 1. SOC 过低 → 强制充电恢复(健康告警)
        if soc < self._soc_floor:
            kw = self.DEFAULT_CHARGE_KW
            return StorageAction(
                action="charge",
                power_kw=kw,
                target_soc=target,
                reason=f"SOC={soc:.0%}低于安全下限{self._soc_floor:.0%},强制充电恢复",
                health_ok=False,
                within_safe_range=safe,
            )

        # 2. SOC 过高 → 禁充电(可放电或待机)
        if soc > self._soc_ceiling:
            if (grid_price is not None and grid_price >= self._peak_price) or load_kw > 0:
                kw = -min(self.DEFAULT_DISCHARGE_KW, max(load_kw, 1.0))
                return StorageAction(
                    action="discharge",
                    power_kw=kw,
                    target_soc=target,
                    reason=f"SOC={soc:.0%}高于安全上限,放电回归安全区间",
                    health_ok=False,
                    within_safe_range=safe,
                )
            return StorageAction(
                action="idle",
                power_kw=0.0,
                target_soc=target,
                reason=f"SOC={soc:.0%}高于安全上限,待机等待放电时机",
                health_ok=False,
                within_safe_range=safe,
            )

        # 3. 温度过高 → 禁充电(可放电或待机)
        if not temp_ok:
            if (grid_price is not None and grid_price >= self._peak_price) and soc > self._discharge_soc_floor:
                kw = -min(self.DEFAULT_DISCHARGE_KW, max(load_kw, 1.0))
                return StorageAction(
                    action="discharge",
                    power_kw=kw,
                    target_soc=target,
                    reason=f"温度{temp_c}℃超限,仅允许放电",
                    health_ok=False,
                    within_safe_range=safe,
                )
            return StorageAction(
                action="idle",
                power_kw=0.0,
                target_soc=target,
                reason=f"温度{temp_c}℃超限,暂停充电保护电池",
                health_ok=False,
                within_safe_range=safe,
            )

        # 4. 光伏余电 → 优先充入储能
        if pv_surplus_kw > 0:
            kw = min(pv_surplus_kw, self.DEFAULT_CHARGE_KW)
            return StorageAction(
                action="charge",
                power_kw=kw,
                target_soc=target,
                reason=f"光伏余电{pv_surplus_kw:.1f}kW充入储能",
                health_ok=True,
                within_safe_range=safe,
            )

        # 5. 低谷电价 → 电网充电(套利)
        if grid_price is not None and grid_price <= self._valley_price:
            kw = self.DEFAULT_CHARGE_KW
            return StorageAction(
                action="charge",
                power_kw=kw,
                target_soc=target,
                reason=f"低谷电价{grid_price:.2f}元/kWh,电网充电",
                health_ok=True,
                within_safe_range=safe,
            )

        # 6. 高峰电价 + 有负荷 → 放电供给 (放电SOC下限保护, 不让电池放空至 0.10 以下)
        if grid_price is not None and grid_price >= self._peak_price and soc > self._discharge_soc_floor:
            kw = -min(self.DEFAULT_DISCHARGE_KW, max(load_kw, 1.0))
            return StorageAction(
                action="discharge",
                power_kw=kw,
                target_soc=target,
                reason=f"高峰电价{grid_price:.2f}元/kWh,放电供给负荷",
                health_ok=True,
                within_safe_range=safe,
            )

        # 7. 平段无余电 → 待机
        return StorageAction(
            action="idle",
            power_kw=0.0,
            target_soc=target,
            reason="无光伏余电、电价中性,储能待机",
            health_ok=True,
            within_safe_range=safe,
        )
