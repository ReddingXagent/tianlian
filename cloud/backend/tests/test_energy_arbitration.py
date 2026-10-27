"""
P1-2 多策略仲裁层 + StorageOptimizer 配置化 + 能量流优先级链 测试

覆盖 (SPEC §3 能量流 / §4 多策略仲裁 / §4.3 安全底线):
- EnergyArbitrator: 反向冲突裁决 / 同向取最大 / SOC 底线裁剪 / BMS 钳位 / 循环次数 / 权重模式 / 叠加模式
- StorageOptimizer 配置化: 有配置覆盖 / 无配置走默认 / 类常量向后兼容
- EnergyFlowPlanner: 默认链路 / 环节开关(关上网→弃光) / 顺序可调(储能放电优先) / 环节限参

纯计算单元测试, 不连 DB —— 仲裁器/能量流/StorageOptimizer 均从外部入参取配置。
"""
import pytest

from app.services.charging.arbitrator import (
    AdviceDirection,
    ArbitrationMode,
    ArbitrationResult,
    EnergyArbitrator,
    HardConstraints,
    StrategyAdvice,
    StrategyType,
)
from app.services.charging.energy_flow import (
    EnergyFlowInput,
    EnergyFlowPlanner,
    EnergyFlowResult,
    FlowStage,
)
from app.services.charging.storage_optimizer import (
    StorageAction,
    StorageOptimizer,
    StorageOptimizerConfig,
)


# ═══════════════════════════════════════════════════════════════
# StrategyType 枚举
# ═══════════════════════════════════════════════════════════════

class TestStrategyType:
    """策略类型枚举 (对齐 SPEC §4 优先级链: 保供>安全>需量>增容>套利>消纳)"""

    def test_has_six_types(self):
        # 5 个业务策略 + SAFETY(电池安全, 仅次于保供)
        assert len(StrategyType) == 6

    def test_values(self):
        assert StrategyType.BACKUP.value == "backup"
        assert StrategyType.SAFETY.value == "safety"
        assert StrategyType.DEMAND.value == "demand"
        assert StrategyType.BOOSTING.value == "boosting"
        assert StrategyType.ARBITRAGE.value == "arbitrage"
        assert StrategyType.SOLAR_ABSORB.value == "solar_absorb"

    def test_is_str_enum(self):
        assert isinstance(StrategyType.BACKUP, str)
        assert StrategyType.BACKUP == "backup"


# ═══════════════════════════════════════════════════════════════
# EnergyArbitrator — 反向冲突裁决
# ═══════════════════════════════════════════════════════════════

class TestArbitrationReverseConflict:
    """反向冲突: 一策略要充、另一要放 → 按优先级裁决"""

    def test_backup_beats_arbitrage(self):
        # 保供(高优先级)要充电保持, 套利(低优先级)要放电 → 保供胜, 方向=充电
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.BACKUP, AdviceDirection.CHARGE, 20, reason="保供预留"),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, 50, reason="峰谷套利"),
        ]
        result = arb.arbitrate(advices, HardConstraints(soc=0.5))
        assert result.direction == AdviceDirection.CHARGE
        assert result.power_kw == pytest.approx(20)
        assert result.winning_strategy == StrategyType.BACKUP

    def test_demand_beats_boosting_same_as_arbitrage(self):
        # 需量 > 增容 > 套利: 需量要放电, 套利要充电 → 需量胜
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.DEMAND, AdviceDirection.DISCHARGE, 30, reason="削峰"),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, 40, reason="套利"),
        ]
        result = arb.arbitrate(advices, HardConstraints(soc=0.6))
        assert result.winning_strategy == StrategyType.DEMAND
        assert result.direction == AdviceDirection.DISCHARGE

    def test_higher_priority_direction_wins_regardless_of_power(self):
        # 即使低优先级策略功率更大, 反向冲突时仍按优先级裁决
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.BACKUP, AdviceDirection.DISCHARGE, 10, reason="保供放"),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, 200, reason="套利充"),
        ]
        result = arb.arbitrate(advices, HardConstraints(soc=0.7))
        assert result.direction == AdviceDirection.DISCHARGE
        assert result.winning_strategy == StrategyType.BACKUP
        assert result.power_kw == pytest.approx(10)

    def test_priority_override_changes_winner(self):
        # 场站级覆盖: 把套利优先级抬到保供之上 → 套利胜
        arb = EnergyArbitrator(priority_override={
            StrategyType.ARBITRAGE: 0,
            StrategyType.BACKUP: 10,
        })
        advices = [
            StrategyAdvice(StrategyType.BACKUP, AdviceDirection.CHARGE, 20),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, 50),
        ]
        result = arb.arbitrate(advices, HardConstraints(soc=0.5))
        assert result.winning_strategy == StrategyType.ARBITRAGE
        assert result.direction == AdviceDirection.DISCHARGE


# ═══════════════════════════════════════════════════════════════
# EnergyArbitrator — 同向取最大
# ═══════════════════════════════════════════════════════════════

class TestArbitrationSameDirection:
    """同向: 多策略都要放电 → 默认取最大功率建议(不叠加)"""

    def test_take_max_discharge(self):
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.DISCHARGE, 30, reason="增容"),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, 50, reason="套利"),
        ]
        result = arb.arbitrate(advices, HardConstraints(soc=0.8))
        assert result.direction == AdviceDirection.DISCHARGE
        assert result.power_kw == pytest.approx(50)  # 取大, 不是 80
        assert result.winning_strategy == StrategyType.ARBITRAGE

    def test_take_max_charge(self):
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.SOLAR_ABSORB, AdviceDirection.CHARGE, 25, reason="消纳"),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, 40, reason="套利"),
        ]
        result = arb.arbitrate(advices, HardConstraints(soc=0.3))
        assert result.direction == AdviceDirection.CHARGE
        assert result.power_kw == pytest.approx(40)

    def test_stack_mode_sums_within_cap(self):
        # 叠加模式: 同向叠加, 但受 stack_cap 限制
        arb = EnergyArbitrator(default_mode=ArbitrationMode.STACK, stack_cap_kw=60)
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.DISCHARGE, 30),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, 50),
        ]
        result = arb.arbitrate(advices, HardConstraints(soc=0.8))
        assert result.direction == AdviceDirection.DISCHARGE
        assert result.power_kw == pytest.approx(60)  # 30+50=80 钳到 cap 60


# ═══════════════════════════════════════════════════════════════
# EnergyArbitrator — 硬约束裁剪 (SPEC §4.3)
# ═══════════════════════════════════════════════════════════════

class TestArbitrationHardConstraints:
    """硬约束: SOC 底线 / BMS 功率 / 变压器容量 / 循环次数 → 裁剪后下发"""

    def test_soc_floor_blocks_discharge(self):
        # SOC 低于底线 → 禁止一切套利性放电
        arb = EnergyArbitrator()
        advices = [StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, 50)]
        result = arb.arbitrate(advices, HardConstraints(soc=0.05, soc_floor=0.10))
        assert result.direction == AdviceDirection.IDLE
        assert result.power_kw == 0.0
        assert "SOC" in result.reason or "底线" in result.reason or "soc" in result.reason.lower()

    def test_soc_ceiling_blocks_charge(self):
        # SOC 高于上限 → 禁止充电
        arb = EnergyArbitrator()
        advices = [StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, 50)]
        result = arb.arbitrate(advices, HardConstraints(soc=0.95, soc_ceiling=0.90))
        assert result.direction == AdviceDirection.IDLE
        assert result.power_kw == 0.0

    def test_bms_clamps_discharge_power(self):
        # BMS 放电功率上限钳位
        arb = EnergyArbitrator()
        advices = [StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, 80)]
        result = arb.arbitrate(advices, HardConstraints(soc=0.8, bms_max_discharge_kw=30))
        assert result.direction == AdviceDirection.DISCHARGE
        assert result.power_kw == pytest.approx(30)

    def test_bms_clamps_charge_power(self):
        arb = EnergyArbitrator()
        advices = [StrategyAdvice(StrategyType.SOLAR_ABSORB, AdviceDirection.CHARGE, 60)]
        result = arb.arbitrate(advices, HardConstraints(soc=0.3, bms_max_charge_kw=20))
        assert result.direction == AdviceDirection.CHARGE
        assert result.power_kw == pytest.approx(20)

    def test_cycles_exhausted_blocks_activity(self):
        # 当日循环次数用尽 → 禁止充放(SPEC §4.3 循环寿命保护)
        arb = EnergyArbitrator()
        advices = [StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, 50)]
        result = arb.arbitrate(
            advices,
            HardConstraints(soc=0.8, cycles_today=3, max_daily_cycles=3),
        )
        assert result.direction == AdviceDirection.IDLE
        assert result.power_kw == 0.0


# ═══════════════════════════════════════════════════════════════
# EnergyArbitrator — 权重模式 + 决策日志
# ═══════════════════════════════════════════════════════════════

class TestArbitrationWeightedAndLog:
    """权重模式(可选高级) + 决策日志"""

    def test_weighted_mode_blends_same_direction(self):
        # 权重加权: (50*0.3 + 30*0.7) / (0.3+0.7) = 36
        arb = EnergyArbitrator(default_mode=ArbitrationMode.WEIGHTED)
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.DISCHARGE, 50, weight=0.3),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, 30, weight=0.7),
        ]
        result = arb.arbitrate(advices, HardConstraints(soc=0.8))
        assert result.direction == AdviceDirection.DISCHARGE
        assert result.power_kw == pytest.approx(36, abs=0.01)

    def test_decision_log_records_all_advices(self):
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.BACKUP, AdviceDirection.CHARGE, 20, reason="保供"),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, 50, reason="套利"),
        ]
        result = arb.arbitrate(advices, HardConstraints(soc=0.5))
        assert isinstance(result.decision_log, list)
        assert len(result.decision_log) == 2
        # 日志含每个策略的 type/direction/power/是否采纳
        strategies_in_log = {entry["strategy_type"] for entry in result.decision_log}
        assert "backup" in strategies_in_log
        assert "arbitrage" in strategies_in_log

    def test_empty_advices_returns_idle(self):
        arb = EnergyArbitrator()
        result = arb.arbitrate([], HardConstraints(soc=0.5))
        assert result.direction == AdviceDirection.IDLE
        assert result.power_kw == 0.0

    def test_all_idle_advices_returns_idle(self):
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.IDLE, 0),
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.IDLE, 0),
        ]
        result = arb.arbitrate(advices, HardConstraints(soc=0.5))
        assert result.direction == AdviceDirection.IDLE


# ═══════════════════════════════════════════════════════════════
# StorageOptimizer 配置化
# ═══════════════════════════════════════════════════════════════

class TestStorageOptimizerConfig:
    """StorageOptimizer 配置化: 阈值/SOC底线 从外部注入, 无配置走默认"""

    def test_class_constants_preserved_backward_compat(self):
        # 类常量保留, 防止外部引用(如 vpp.py 风格)断裂
        assert StorageOptimizer.VALLEY_PRICE == 0.40
        assert StorageOptimizer.PEAK_PRICE == 0.90
        assert StorageOptimizer.SOC_MIN == 0.10

    def test_no_config_uses_defaults(self):
        # 无 config → 行为与原硬编码一致
        opt = StorageOptimizer()
        # grid_price=0.30 <= VALLEY_PRICE(0.40) → 低谷充电
        action = opt.optimize(soc=0.5, grid_price=0.30)
        assert action.action == "charge"
        assert "低谷" in action.reason

    def test_custom_valley_threshold(self):
        # 配置 valley=0.25 → grid_price=0.30 不再算低谷(0.30>0.25) → 不充电
        opt = StorageOptimizer(StorageOptimizerConfig(valley_price_threshold=0.25))
        action = opt.optimize(soc=0.5, grid_price=0.30)
        assert action.action == "idle"

    def test_custom_peak_threshold(self):
        # 配置 peak=0.70 → grid_price=0.80 >= 0.70 触发放电(默认 0.90 时 0.80 不触发)
        opt = StorageOptimizer(StorageOptimizerConfig(peak_price_threshold=0.70))
        action = opt.optimize(soc=0.5, grid_price=0.80, load_kw=20)
        assert action.action == "discharge"

    def test_custom_soc_floor(self):
        # 配置 soc_floor=0.20 → soc=0.15 触发强制充电(默认 0.10 时 0.15 不触发)
        opt = StorageOptimizer(StorageOptimizerConfig(soc_floor=0.20))
        action = opt.optimize(soc=0.15)
        assert action.action == "charge"
        assert not action.health_ok  # 低于底线 → 健康告警

    def test_default_soc_floor_does_not_trigger_at_015(self):
        # 对照组: 默认 soc_floor=0.10, soc=0.15 不强制充电
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.15)
        assert action.action != "charge" or action.health_ok

    def test_config_does_not_break_pv_surplus(self):
        opt = StorageOptimizer(StorageOptimizerConfig())
        action = opt.optimize(soc=0.5, pv_surplus_kw=30)
        assert action.action == "charge"
        assert isinstance(action, StorageAction)


# ═══════════════════════════════════════════════════════════════
# EnergyFlowPlanner — 默认链路 (SPEC §3)
# ═══════════════════════════════════════════════════════════════

class TestEnergyFlowDefaultChain:
    """默认链: P1直供→P2余电储能→P3上网(off)→P4储能放电→P5电网兜底"""

    def test_pv_direct_first(self):
        # 光伏 50, 负载 30 → 直供 30, 余 20
        planner = EnergyFlowPlanner()
        result = planner.plan(EnergyFlowInput(
            pv_output_kw=50, charger_load_kw=30, soc=0.5,
            ess_charge_cap_kw=50, ess_discharge_cap_kw=50,
        ))
        assert result.pv_direct_kw == pytest.approx(30)
        assert result.pv_to_ess_kw == pytest.approx(20)  # 余电储能
        assert result.grid_purchase_kw == pytest.approx(0)

    def test_pv_insufficient_ess_then_grid(self):
        # 光伏 10, 负载 50, 储能可放 25 → 直供10 + 储能25 + 电网15
        planner = EnergyFlowPlanner()
        result = planner.plan(EnergyFlowInput(
            pv_output_kw=10, charger_load_kw=50, soc=0.8,
            ess_charge_cap_kw=50, ess_discharge_cap_kw=25,
        ))
        assert result.pv_direct_kw == pytest.approx(10)
        assert result.ess_discharge_kw == pytest.approx(25)
        assert result.grid_purchase_kw == pytest.approx(15)

    def test_pv_surplus_ess_full_curtailed_when_export_off(self):
        # 光伏 50, 负载 10, 储能已满(SOC>ceiling 不能充) → 上网关 → 弃光 30
        planner = EnergyFlowPlanner()
        result = planner.plan(EnergyFlowInput(
            pv_output_kw=50, charger_load_kw=10, soc=0.95, soc_ceiling=0.90,
            ess_charge_cap_kw=50, ess_discharge_cap_kw=50,
        ))
        assert result.pv_direct_kw == pytest.approx(10)
        assert result.pv_to_ess_kw == pytest.approx(0)  # 储能满, 不充
        assert result.grid_export_kw == pytest.approx(0)  # 上网关
        assert result.curtailed_kw == pytest.approx(40)  # 弃光保护

    def test_export_when_enabled_and_allowed(self):
        # 上网环节开 + allow_export → 余电上网
        planner = EnergyFlowPlanner(allow_export=True)
        result = planner.plan(EnergyFlowInput(
            pv_output_kw=50, charger_load_kw=10, soc=0.95, soc_ceiling=0.90,
            ess_charge_cap_kw=50, ess_discharge_cap_kw=50,
            allow_export=True,
        ))
        assert result.grid_export_kw == pytest.approx(40)
        assert result.curtailed_kw == pytest.approx(0)

    def test_soc_floor_blocks_ess_discharge(self):
        # 光伏 0, 负载 50, SOC 低于底线 → 储能不放 → 电网兜底 50
        planner = EnergyFlowPlanner()
        result = planner.plan(EnergyFlowInput(
            pv_output_kw=0, charger_load_kw=50, soc=0.05, soc_floor=0.10,
            ess_charge_cap_kw=50, ess_discharge_cap_kw=50,
        ))
        assert result.ess_discharge_kw == pytest.approx(0)
        assert result.grid_purchase_kw == pytest.approx(50)


# ═══════════════════════════════════════════════════════════════
# EnergyFlowPlanner — 环节开关 + 顺序可调
# ═══════════════════════════════════════════════════════════════

class TestEnergyFlowConfigurable:
    """可编排: 环节开关 / 顺序可调 / 环节限参"""

    def test_disable_grid_backup_leaves_unmet_load(self):
        # 关电网兜底(离网站) → 负荷缺口变未满足
        planner = EnergyFlowPlanner()
        planner.disable(FlowStage.GRID_BACKUP)
        result = planner.plan(EnergyFlowInput(
            pv_output_kw=10, charger_load_kw=50, soc=0.05, soc_floor=0.10,
            ess_charge_cap_kw=50, ess_discharge_cap_kw=50,
        ))
        assert result.grid_purchase_kw == pytest.approx(0)
        assert result.unmet_load_kw == pytest.approx(40)  # 50-10-0(储能不放)

    def test_order_ess_discharge_before_pv_direct(self):
        # 顺序可调: 储能放电优先于光伏直供 → 先放储能满足负载, 光伏变余电
        planner = EnergyFlowPlanner(chain=[
            FlowStage.ESS_DISCHARGE,
            FlowStage.PV_DIRECT,
            FlowStage.PV_TO_ESS,
            FlowStage.GRID_BACKUP,
        ])
        result = planner.plan(EnergyFlowInput(
            pv_output_kw=40, charger_load_kw=50, soc=0.8,
            ess_charge_cap_kw=50, ess_discharge_cap_kw=50,
        ))
        # 储能先放 50 满足负载, 光伏不再直供 → 余 40 进储能
        assert result.ess_discharge_kw == pytest.approx(50)
        assert result.pv_direct_kw == pytest.approx(0)
        assert result.pv_to_ess_kw == pytest.approx(40)

    def test_stage_power_cap(self):
        # 环节限参: 光伏直供 cap=20 → 只直供 20
        planner = EnergyFlowPlanner()
        planner.set_cap(FlowStage.PV_DIRECT, 20)
        result = planner.plan(EnergyFlowInput(
            pv_output_kw=50, charger_load_kw=50, soc=0.5,
            ess_charge_cap_kw=50, ess_discharge_cap_kw=50,
        ))
        assert result.pv_direct_kw == pytest.approx(20)

    def test_from_config_parses_json(self):
        # 解析 station_energy_strategy.energy_flow_priority JSON
        config_json = {
            "stages": [
                {"stage": "pv_direct", "enabled": True, "priority": 1},
                {"stage": "pv_to_ess", "enabled": True, "priority": 2},
                {"stage": "export_to_grid", "enabled": False, "priority": 3},
                {"stage": "ess_discharge", "enabled": True, "priority": 4},
                {"stage": "grid_backup", "enabled": True, "priority": 5},
            ]
        }
        planner = EnergyFlowPlanner.from_config(config_json)
        result = planner.plan(EnergyFlowInput(
            pv_output_kw=30, charger_load_kw=20, soc=0.5,
            ess_charge_cap_kw=50, ess_discharge_cap_kw=50,
        ))
        assert result.pv_direct_kw == pytest.approx(20)
        assert result.pv_to_ess_kw == pytest.approx(10)

    def test_result_has_stage_log(self):
        planner = EnergyFlowPlanner()
        result = planner.plan(EnergyFlowInput(
            pv_output_kw=50, charger_load_kw=30, soc=0.5,
            ess_charge_cap_kw=50, ess_discharge_cap_kw=50,
        ))
        assert isinstance(result, EnergyFlowResult)
        assert isinstance(result.stages_log, list)
        assert len(result.stages_log) > 0
