"""能量流优先级链 — SPEC §3 (可编排优先级链路)

光伏出力的去向按「可编排优先级链」分配, 每个场站可调顺序 / 环节开关 / 环节限参。
纯计算模块, 不依赖 DB, 配置从外部传入。

默认优先级链 (SPEC §3):
    P1 就地直供 (光伏→充电桩负载)
    P2 余电储能 (光伏 > 负载 → 储能充电)
    P3 余电上网 (默认关闭; 关闭时执行弃光保护)
    P4 储能放电 (光伏不足 → 储能补充负载)
    P5 电网兜底 (剩余缺口 → 电网购电)

硬约束 (不可被配置突破):
- SOC 底线: SOC ≤ soc_floor 时禁止储能放电
- SOC 上限: SOC ≥ soc_ceiling 时禁止储能充电
- 防逆流: allow_export=False 时余电上网环节强制关闭 → 弃光保护

energy_flow_priority JSON schema (来自 station_energy_strategy.energy_flow_priority):
    {
      "stages": [
        {"stage": "pv_direct",      "enabled": true,  "priority": 1, "power_cap_kw": null},
        {"stage": "pv_to_ess",      "enabled": true,  "priority": 2, "power_cap_kw": null},
        {"stage": "export_to_grid", "enabled": false, "priority": 3, "power_cap_kw": null},
        {"stage": "ess_discharge",  "enabled": true,  "priority": 4, "power_cap_kw": null},
        {"stage": "grid_backup",    "enabled": true,  "priority": 5, "power_cap_kw": null}
      ]
    }
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FlowStage(str, Enum):
    """能量流环节"""
    PV_DIRECT = "pv_direct"            # P1 光伏就地直供
    PV_TO_ESS = "pv_to_ess"            # P2 余电储能
    EXPORT_TO_GRID = "export_to_grid"  # P3 余电上网
    ESS_DISCHARGE = "ess_discharge"    # P4 储能放电
    GRID_BACKUP = "grid_backup"        # P5 电网兜底


# 默认链顺序 (SPEC §3)
DEFAULT_CHAIN: List[FlowStage] = [
    FlowStage.PV_DIRECT,
    FlowStage.PV_TO_ESS,
    FlowStage.EXPORT_TO_GRID,
    FlowStage.ESS_DISCHARGE,
    FlowStage.GRID_BACKUP,
]


@dataclass
class EnergyFlowInput:
    """能量流分配输入 (纯数据, 不连 DB)"""
    pv_output_kw: float               # 当前光伏出力 (kW)
    charger_load_kw: float            # 充电桩负载需求 (kW)
    soc: float                        # 储能 SOC (0-1)
    soc_floor: float = 0.10           # SOC 下限 (低于此储能不放)
    soc_ceiling: float = 0.90         # SOC 上限 (高于此储能不充)
    ess_charge_cap_kw: float = 0.0    # 储能最大充电功率 (0=无充电能力)
    ess_discharge_cap_kw: float = 0.0  # 储能最大放电功率 (0=无放电能力)
    allow_export: bool = False        # 防逆流开关 (False=禁止上网)


@dataclass
class EnergyFlowResult:
    """能量流分配输出: 各环节功率 (kW)"""
    pv_direct_kw: float = 0.0        # 光伏就地直供
    pv_to_ess_kw: float = 0.0        # 余电充入储能
    ess_discharge_kw: float = 0.0    # 储能放电
    grid_purchase_kw: float = 0.0    # 电网购电 (兜底)
    grid_export_kw: float = 0.0      # 余电上网
    curtailed_kw: float = 0.0        # 弃光 (上网关时的余电)
    unmet_load_kw: float = 0.0       # 未满足负荷 (电网兜底关时)
    stages_log: List[dict] = field(default_factory=list)


class EnergyFlowPlanner:
    """能量流优先级链编排器"""

    def __init__(
        self,
        chain: Optional[List[FlowStage]] = None,
        allow_export: bool = False,
    ) -> None:
        """
        Args:
            chain: 环节顺序 (None=默认链)。顺序可调 (SPEC §3): 例把储能放电排到光伏直供之前。
            allow_export: 是否允许余电上网。默认 False (SPEC §3 默认关 → 弃光保护)。
        """
        self._chain: List[FlowStage] = list(chain) if chain is not None else list(DEFAULT_CHAIN)
        self._disabled: set = set()
        self._caps: Dict[FlowStage, float] = {}
        self._allow_export = allow_export
        # 上网环节默认随 allow_export 关闭
        if not allow_export:
            self._disabled.add(FlowStage.EXPORT_TO_GRID)

    @classmethod
    def from_config(cls, config_json: Optional[dict]) -> "EnergyFlowPlanner":
        """解析 station_energy_strategy.energy_flow_priority JSON 构建编排器。

        缺省 (None/空) → 默认链 + 上网关。
        解析异常 → 回退默认链 + 上网关 (不抛, 保证调用方安全)。
        """
        try:
            if not config_json or not config_json.get("stages"):
                return cls()
            stages_data = config_json.get("stages", [])
            # 按 priority 排序构建链
            ordered = sorted(stages_data, key=lambda x: x.get("priority", 99))
            chain: List[FlowStage] = []
            disabled: set = set()
            caps: Dict[FlowStage, float] = {}
            export_enabled = True
            for item in ordered:
                stage = FlowStage(item["stage"])
                chain.append(stage)
                if not item.get("enabled", True):
                    disabled.add(stage)
                if item.get("power_cap_kw") is not None:
                    caps[stage] = float(item["power_cap_kw"])
                if stage == FlowStage.EXPORT_TO_GRID and item.get("enabled", False):
                    export_enabled = True
            # 上网开关: 链中显式 enabled 才视为允许
            allow_export = (
                FlowStage.EXPORT_TO_GRID in chain
                and FlowStage.EXPORT_TO_GRID not in disabled
            )
            planner = cls(chain=chain, allow_export=allow_export)
            for stage in disabled:
                planner.disable(stage)
            for stage, cap in caps.items():
                planner.set_cap(stage, cap)
            return planner
        except Exception:
            logger.exception(
                "energy_flow from_config 解析失败，回退默认链 config=%s",
                config_json,
            )
            return cls()

    # ─── 配置 API ───

    def disable(self, stage: FlowStage) -> "EnergyFlowPlanner":
        try:
            self._disabled.add(stage)
        except Exception:
            logger.exception("disable 环节失败 stage=%s", stage)
        return self

    def enable(self, stage: FlowStage) -> "EnergyFlowPlanner":
        try:
            self._disabled.discard(stage)
        except Exception:
            logger.exception("enable 环节失败 stage=%s", stage)
        return self

    def set_cap(self, stage: FlowStage, cap_kw: float) -> "EnergyFlowPlanner":
        """环节限参: 该环节功率上限 (SPEC §3 环节限参)"""
        try:
            self._caps[stage] = float(cap_kw)
        except (TypeError, ValueError):
            logger.warning("set_cap 无效限参，忽略 stage=%s cap_kw=%s", stage, cap_kw)
        except Exception:
            logger.exception("set_cap 异常 stage=%s", stage)
        return self

    # ─── 计算 ───

    def plan(self, inp: EnergyFlowInput) -> EnergyFlowResult:
        """按链顺序分配光伏出力与负荷缺口, 返回各环节功率。

        异常时返回全零 EnergyFlowResult (安全默认: 不分配任何功率)。
        """
        try:
            r = EnergyFlowResult()
            # 入口数值守卫: 非法 pv/load 兜底为 0，避免 max(0.0, None) TypeError
            try:
                remaining_pv = max(0.0, float(inp.pv_output_kw or 0))
                remaining_load = max(0.0, float(inp.charger_load_kw or 0))
            except (TypeError, ValueError):
                remaining_pv = 0.0
                remaining_load = 0.0

            for stage in self._chain:
                if stage in self._disabled:
                    r.stages_log.append({"stage": stage.value, "kw": 0.0, "skipped": "disabled"})
                    continue
                try:
                    cap = self._caps.get(stage)
                    kw = self._run_stage(stage, inp, r, remaining_pv, remaining_load, cap)
                    # 同步本环节消耗后的余量
                    if stage == FlowStage.PV_DIRECT:
                        remaining_pv -= r.pv_direct_kw
                        remaining_load -= r.pv_direct_kw
                    elif stage == FlowStage.PV_TO_ESS:
                        remaining_pv -= r.pv_to_ess_kw
                    elif stage == FlowStage.EXPORT_TO_GRID:
                        remaining_pv -= r.grid_export_kw
                    elif stage == FlowStage.ESS_DISCHARGE:
                        remaining_load -= r.ess_discharge_kw
                    elif stage == FlowStage.GRID_BACKUP:
                        remaining_load -= r.grid_purchase_kw
                    remaining_pv = max(0.0, remaining_pv)
                    remaining_load = max(0.0, remaining_load)
                    r.stages_log.append({"stage": stage.value, "kw": round(kw, 4)})
                except Exception:
                    # 单环节失败不中断整条链, 跳过该环节继续
                    logger.exception(
                        "能量流环节执行失败，跳过 stage=%s",
                        getattr(stage, "value", stage),
                    )
                    r.stages_log.append({
                        "stage": getattr(stage, "value", str(stage)),
                        "kw": 0.0,
                        "skipped": "error",
                    })
                    continue

            # 链末余量结算
            r.curtailed_kw = round(max(0.0, remaining_pv), 4)
            r.unmet_load_kw = round(max(0.0, remaining_load), 4)
            return r
        except Exception:
            logger.exception("能量流分配异常 inp=%s", inp)
            return EnergyFlowResult()

    # ─── 内部: 单环节分配 ───

    def _run_stage(
        self,
        stage: FlowStage,
        inp: EnergyFlowInput,
        r: EnergyFlowResult,
        remaining_pv: float,
        remaining_load: float,
        cap: Optional[float],
    ) -> float:
        """执行单个环节, 写入 r 对应字段, 返回本环节分配功率"""
        def clamp(x: float) -> float:
            return min(x, cap) if cap is not None else x

        if stage == FlowStage.PV_DIRECT:
            # 光伏就地直供: 取光伏余量与负荷缺口的较小值
            direct = clamp(min(remaining_pv, remaining_load))
            r.pv_direct_kw = round(direct, 4)
            return r.pv_direct_kw

        if stage == FlowStage.PV_TO_ESS:
            # 余电储能: SOC 低于上限才充
            if remaining_pv > 1e-9 and inp.soc < inp.soc_ceiling:
                charge = clamp(min(remaining_pv, inp.ess_charge_cap_kw))
                r.pv_to_ess_kw = round(max(0.0, charge), 4)
            return r.pv_to_ess_kw

        if stage == FlowStage.EXPORT_TO_GRID:
            # 余电上网: 需 planner 允许 + inp 防逆流未触发
            if remaining_pv > 1e-9 and self._allow_export and inp.allow_export:
                export = clamp(remaining_pv)
                r.grid_export_kw = round(max(0.0, export), 4)
            return r.grid_export_kw

        if stage == FlowStage.ESS_DISCHARGE:
            # 储能放电补负载: SOC 高于底线才放
            if remaining_load > 1e-9 and inp.soc > inp.soc_floor:
                discharge = clamp(min(remaining_load, inp.ess_discharge_cap_kw))
                r.ess_discharge_kw = round(max(0.0, discharge), 4)
            return r.ess_discharge_kw

        if stage == FlowStage.GRID_BACKUP:
            # 电网兜底: 补足剩余缺口
            purchase = clamp(remaining_load)
            r.grid_purchase_kw = round(max(0.0, purchase), 4)
            return r.grid_purchase_kw

        return 0.0
