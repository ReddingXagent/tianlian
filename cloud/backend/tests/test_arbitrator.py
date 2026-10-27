"""EnergyArbitrator 单元测试 — 多策略仲裁层 (SPEC §4 反向冲突/同向叠加 + §4.3 安全底线)

纯计算模块, 无 DB/外部依赖。覆盖:
- 数据结构 (StrategyAdvice/HardConstraints/ArbitrationResult)
- 默认优先级序 (保供 > 安全 > 需量 > 增容 > 套利 > 消纳)
- 反向冲突裁决 (按组内最高优先级胜出方向)
- 同向叠加 (MAX/STACK/WEIGHTED)
- 硬约束裁剪 (SOC 底线/上限, BMS 功率, 循环次数)
- 决策日志 (accepted 标记)
"""
import pytest

from app.services.charging.arbitrator import (
    DEFAULT_PRIORITY,
    AdviceDirection,
    ArbitrationMode,
    ArbitrationResult,
    EnergyArbitrator,
    HardConstraints,
    StrategyAdvice,
    StrategyType,
)


def _constraints(**kw):
    """构造 HardConstraints, soc 默认 0.5 (安全区)。"""
    base = dict(soc=0.5)
    base.update(kw)
    return HardConstraints(**base)


# ─── 数据结构 ───

class TestStrategyAdvice:
    def test_defaults(self):
        a = StrategyAdvice(StrategyType.BACKUP, AdviceDirection.CHARGE)
        assert a.strategy_type is StrategyType.BACKUP
        assert a.direction is AdviceDirection.CHARGE
        assert a.power_kw == 0.0
        assert a.weight == 1.0
        assert a.reason == ""

    def test_custom_fields(self):
        a = StrategyAdvice(
            StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE,
            power_kw=42.5, weight=2.0, reason="peak",
        )
        assert a.power_kw == 42.5
        assert a.weight == 2.0
        assert a.reason == "peak"


class TestHardConstraints:
    def test_defaults(self):
        c = HardConstraints(soc=0.5)
        assert c.soc == 0.5
        assert c.soc_floor == 0.10
        assert c.soc_ceiling == 0.90
        assert c.bms_max_charge_kw is None
        assert c.bms_max_discharge_kw is None
        assert c.cycles_today == 0
        assert c.max_daily_cycles is None

    def test_custom(self):
        c = HardConstraints(soc=0.3, soc_floor=0.2, bms_max_charge_kw=50, max_daily_cycles=6)
        assert c.soc_floor == 0.2
        assert c.bms_max_charge_kw == 50
        assert c.max_daily_cycles == 6


class TestArbitrationResult:
    def test_defaults(self):
        r = ArbitrationResult(direction=AdviceDirection.IDLE, power_kw=0.0)
        assert r.direction is AdviceDirection.IDLE
        assert r.winning_strategy is None
        assert r.mode is ArbitrationMode.MAX
        assert r.decision_log == []
        assert r.reason == ""


def test_default_priority_order():
    """默认优先级序: 保供(1) > 安全(2) > 需量(3) > 增容(4) > 套利(5) > 消纳(6)。"""
    assert DEFAULT_PRIORITY[StrategyType.BACKUP] == 1
    assert DEFAULT_PRIORITY[StrategyType.SAFETY] == 2
    assert DEFAULT_PRIORITY[StrategyType.DEMAND] == 3
    assert DEFAULT_PRIORITY[StrategyType.BOOSTING] == 4
    assert DEFAULT_PRIORITY[StrategyType.ARBITRAGE] == 5
    assert DEFAULT_PRIORITY[StrategyType.SOLAR_ABSORB] == 6
    order = [StrategyType.BACKUP, StrategyType.SAFETY, StrategyType.DEMAND,
             StrategyType.BOOSTING, StrategyType.ARBITRAGE, StrategyType.SOLAR_ABSORB]
    prios = [DEFAULT_PRIORITY[s] for s in order]
    assert prios == sorted(prios)


# ─── 无活跃 / 单方向 ───

class TestArbitrateBasic:
    def test_no_active_returns_idle(self):
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.IDLE, power_kw=10),
            StrategyAdvice(StrategyType.BACKUP, AdviceDirection.CHARGE, power_kw=0.0),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert r.direction is AdviceDirection.IDLE
        assert r.power_kw == 0.0
        assert r.winning_strategy is None
        assert "无活跃" in r.reason

    def test_single_charge(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=30)],
            _constraints(),
        )
        assert r.direction is AdviceDirection.CHARGE
        assert r.power_kw == 30.0
        assert r.winning_strategy is StrategyType.BOOSTING

    def test_single_discharge(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=25)],
            _constraints(),
        )
        assert r.direction is AdviceDirection.DISCHARGE
        assert r.power_kw == 25.0
        assert r.winning_strategy is StrategyType.SAFETY


# ─── 同向合成 ───

class TestSameDirectionCombine:
    def test_max_mode_takes_largest(self):
        arb = EnergyArbitrator(default_mode=ArbitrationMode.MAX)
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, power_kw=30),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert r.power_kw == 50.0  # MAX 取最大, 不叠加
        assert r.winning_strategy is StrategyType.BOOSTING  # 代表=组内最大功率者

    def test_stack_mode_sums(self):
        arb = EnergyArbitrator(default_mode=ArbitrationMode.STACK)
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, power_kw=30),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert r.power_kw == 80.0  # 50+30

    def test_stack_mode_with_cap(self):
        arb = EnergyArbitrator(default_mode=ArbitrationMode.STACK, stack_cap_kw=60)
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, power_kw=30),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert r.power_kw == 60.0  # min(80, 60)

    def test_weighted_mode(self):
        arb = EnergyArbitrator(default_mode=ArbitrationMode.WEIGHTED)
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=100, weight=1.0),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, power_kw=50, weight=3.0),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert r.power_kw == 62.5  # (100*1 + 50*3)/(1+3) = 250/4
        assert r.winning_strategy is StrategyType.BOOSTING  # 代表=最大功率者


# ─── 反向冲突 ───

class TestReverseConflict:
    def test_discharge_wins_by_priority(self):
        # 充电 BOOSTING(prio4) vs 放电 SAFETY(prio2) → 放电组优先级更高, 胜出
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50),
            StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=30),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert r.direction is AdviceDirection.DISCHARGE
        assert r.power_kw == 30.0
        assert r.winning_strategy is StrategyType.SAFETY
        assert "反向冲突" in r.reason

    def test_charge_wins_by_priority(self):
        # 充电 BACKUP(prio1) vs 放电 ARBITRAGE(prio5) → 充电胜出
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.BACKUP, AdviceDirection.CHARGE, power_kw=50),
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, power_kw=30),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert r.direction is AdviceDirection.CHARGE
        assert r.power_kw == 50.0
        assert r.winning_strategy is StrategyType.BACKUP

    def test_equal_priority_charge_wins(self):
        # override 让两边同优先级 → 条件 `<` 不成立 → 充电胜出
        arb = EnergyArbitrator(priority_override={StrategyType.BOOSTING: 3, StrategyType.DEMAND: 3})
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50),
            StrategyAdvice(StrategyType.DEMAND, AdviceDirection.DISCHARGE, power_kw=30),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert r.direction is AdviceDirection.CHARGE

    def test_priority_override_changes_outcome(self):
        # 默认 BOOSTING(4) charge vs SAFETY(2) discharge → 放电胜; override 反转优先级
        arb = EnergyArbitrator(priority_override={StrategyType.BOOSTING: 1, StrategyType.SAFETY: 9})
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50),
            StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=30),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert r.direction is AdviceDirection.CHARGE
        assert r.winning_strategy is StrategyType.BOOSTING


# ─── 硬约束裁剪 ───

class TestHardConstraintsClipping:
    def test_soc_floor_blocks_discharge(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, power_kw=30)],
            _constraints(soc=0.05, soc_floor=0.10),
        )
        assert r.direction is AdviceDirection.IDLE
        assert r.power_kw == 0.0
        assert "底线" in r.reason

    def test_soc_at_floor_blocks_discharge(self):
        # soc <= floor 触发 (含等于)
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, power_kw=30)],
            _constraints(soc=0.10, soc_floor=0.10),
        )
        assert r.direction is AdviceDirection.IDLE

    def test_soc_ceiling_blocks_charge(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=30)],
            _constraints(soc=0.95, soc_ceiling=0.90),
        )
        assert r.direction is AdviceDirection.IDLE
        assert r.power_kw == 0.0
        assert "上限" in r.reason

    def test_bms_discharge_limit(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=50)],
            _constraints(soc=0.5, bms_max_discharge_kw=30),
        )
        assert r.direction is AdviceDirection.DISCHARGE
        assert r.power_kw == 30.0  # min(50, 30)

    def test_bms_charge_limit(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50)],
            _constraints(soc=0.5, bms_max_charge_kw=20),
        )
        assert r.direction is AdviceDirection.CHARGE
        assert r.power_kw == 20.0  # min(50, 20)

    def test_bms_limit_not_applied_when_above(self):
        # BMS 限制大于请求功率 → 原值下发
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50)],
            _constraints(soc=0.5, bms_max_charge_kw=100),
        )
        assert r.power_kw == 50.0

    def test_daily_cycles_limit(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50)],
            _constraints(soc=0.5, cycles_today=5, max_daily_cycles=5),
        )
        assert r.direction is AdviceDirection.IDLE
        assert r.power_kw == 0.0
        assert "循环次数" in r.reason

    def test_daily_cycles_not_reached_allows(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50)],
            _constraints(soc=0.5, cycles_today=4, max_daily_cycles=5),
        )
        assert r.direction is AdviceDirection.CHARGE
        assert r.power_kw == 50.0


# ─── 决策日志 ───

class TestDecisionLog:
    def test_log_entries_for_all_advice(self):
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50),
            StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=30),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert len(r.decision_log) == 2
        assert r.decision_log[0]["strategy_type"] == "boosting"
        assert r.decision_log[0]["direction"] == "charge"
        assert r.decision_log[0]["power_kw"] == 50.0
        assert r.decision_log[0]["weight"] == 1.0
        assert "accepted" in r.decision_log[0]

    def test_accepted_marking_reverse_conflict(self):
        # 放电胜出 → 放电建议 accepted, 充电建议 not accepted
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50),
            StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=30),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert r.decision_log[1]["accepted"] is True
        assert r.decision_log[0]["accepted"] is False

    def test_accepted_false_when_clipped_to_idle(self):
        # 被硬约束裁剪到 IDLE → 胜出组建议 accepted=False
        arb = EnergyArbitrator()
        advices = [StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, power_kw=30)]
        r = arb.arbitrate(advices, _constraints(soc=0.05, soc_floor=0.10))
        assert r.decision_log[0]["accepted"] is False


def test_power_rounding_to_four_decimals():
    """最终功率 round(final_power, 4)。"""
    arb = EnergyArbitrator(default_mode=ArbitrationMode.WEIGHTED)
    advices = [
        StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=10, weight=1.0),
        StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, power_kw=5, weight=2.0),
    ]
    r = arb.arbitrate(advices, _constraints())
    # (10*1 + 5*2)/3 = 20/3 = 6.6666...
    assert r.power_kw == round(20 / 3, 4)


# ─── 边界加固: NaN/inf 穿透 (卡 f5017f52) ───

class TestFiniteBoundary:
    """NaN/inf 穿透 isinstance(int,float) 且令所有大小比较恒为 False 的安全隐患。

    - NaN soc: soc<=floor 与 soc>=ceiling 均为 False → 充放电硬约束双双放行。
    - inf power: 穿过 active 过滤 (power_kw>1e-9) 与 MAX 合成 → 下发 inf。
    修法: math.isfinite 校验, 非有限 → IDLE。
    """

    def test_nan_soc_blocks_discharge(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=30)],
            _constraints(soc=float("nan")),
        )
        assert r.direction is AdviceDirection.IDLE
        assert r.power_kw == 0.0
        assert r.winning_strategy is None

    def test_nan_soc_blocks_charge(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=30)],
            _constraints(soc=float("nan")),
        )
        assert r.direction is AdviceDirection.IDLE
        assert r.power_kw == 0.0

    def test_inf_soc_blocks_action(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=30)],
            _constraints(soc=float("inf")),
        )
        assert r.direction is AdviceDirection.IDLE

    def test_nan_soc_floor_falls_back_to_default(self):
        # soc_floor 非有限 → 回退默认 0.10; 低 soc 放电仍被底线拦下 (旧码: 0.05<=NaN=False 放行)
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, power_kw=30)],
            _constraints(soc=0.05, soc_floor=float("nan")),
        )
        assert r.direction is AdviceDirection.IDLE
        assert "底线" in r.reason

    def test_nan_soc_floor_safe_soc_allows_discharge(self):
        # soc_floor 回退 0.10; 安全 soc(0.5) 放电放行, 证明回退而非一刀切 IDLE
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=30)],
            _constraints(soc=0.5, soc_floor=float("nan")),
        )
        assert r.direction is AdviceDirection.DISCHARGE
        assert r.power_kw == 30.0

    def test_nan_soc_ceiling_falls_back_to_default(self):
        # soc_ceiling 非有限 → 回退默认 0.90; 高 soc 充电被上限拦下
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=30)],
            _constraints(soc=0.95, soc_ceiling=float("nan")),
        )
        assert r.direction is AdviceDirection.IDLE
        assert "上限" in r.reason

    def test_inf_power_kw_charge_blocks(self):
        # inf 穿过 active 过滤(power_kw>1e-9) 与 MAX 合成 → 旧码下发 inf; 须 IDLE
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=float("inf"))],
            _constraints(soc=0.5),
        )
        assert r.direction is AdviceDirection.IDLE
        assert r.power_kw == 0.0
        assert r.winning_strategy is None

    def test_inf_power_kw_discharge_blocks(self):
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=float("inf"))],
            _constraints(soc=0.5),
        )
        assert r.direction is AdviceDirection.IDLE
        assert r.power_kw == 0.0

    def test_inf_power_does_not_leak_via_reason(self):
        # IDLE 安全结果, reason 不应回显 inf 作为可下发功率
        arb = EnergyArbitrator()
        r = arb.arbitrate(
            [StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=float("inf"))],
            _constraints(soc=0.5),
        )
        assert "非有限" in r.reason


# ─── decision_log 索引错位修复 (卡 f5017f52) ───

class TestDecisionLogWithNone:
    """advices 含 None 时 decision_log 的 accepted 归属。

    旧码: log = [.. for a in advices if a is not None] (比 advices 短),
    但标记循环用 enumerate(advices) 的原始 idx 索引 log → 索引错位:
      [A,None,B] 胜方 B 的 idx=2 越界永不标记;
      [None,A,B] 胜方 A 的 accepted 错写到 B 的条目。
    修法: 建 id(advice)->entry 映射再标记。
    """

    def test_log_skips_none_entries(self):
        arb = EnergyArbitrator()
        advices = [
            StrategyAdvice(StrategyType.BOOSTING, AdviceDirection.CHARGE, power_kw=50),
            None,
            StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, power_kw=30),
        ]
        r = arb.arbitrate(advices, _constraints())
        assert len(r.decision_log) == 2
        assert r.decision_log[0]["strategy_type"] == "boosting"
        assert r.decision_log[1]["strategy_type"] == "arbitrage"

    def test_none_in_middle_winner_is_last(self):
        # [A(charge,ARBITRAGE prio5), None, B(discharge,SAFETY prio2)] → 放电 B 胜
        # 旧码: B 的 accepted 永不标记 (idx=2 越界) → False (错误)
        arb = EnergyArbitrator()
        A = StrategyAdvice(StrategyType.ARBITRAGE, AdviceDirection.CHARGE, power_kw=50)
        B = StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=30)
        r = arb.arbitrate([A, None, B], _constraints())
        assert r.direction is AdviceDirection.DISCHARGE
        assert r.winning_strategy is StrategyType.SAFETY
        safety_entry = next(e for e in r.decision_log if e["strategy_type"] == "safety")
        arbitrage_entry = next(e for e in r.decision_log if e["strategy_type"] == "arbitrage")
        assert safety_entry["accepted"] is True
        assert arbitrage_entry["accepted"] is False

    def test_none_at_start_winner_is_second(self):
        # [None, A(charge,BACKUP prio1), B(discharge,SAFETY prio2)] → 充电 A 胜
        # 旧码: A 的 accepted 错写到 B 的条目 (idx=1→log[1]=safety) → safety=True (错误)
        arb = EnergyArbitrator()
        A = StrategyAdvice(StrategyType.BACKUP, AdviceDirection.CHARGE, power_kw=50)
        B = StrategyAdvice(StrategyType.SAFETY, AdviceDirection.DISCHARGE, power_kw=30)
        r = arb.arbitrate([None, A, B], _constraints())
        assert r.direction is AdviceDirection.CHARGE
        assert r.winning_strategy is StrategyType.BACKUP
        backup_entry = next(e for e in r.decision_log if e["strategy_type"] == "backup")
        safety_entry = next(e for e in r.decision_log if e["strategy_type"] == "safety")
        assert backup_entry["accepted"] is True
        assert safety_entry["accepted"] is False
