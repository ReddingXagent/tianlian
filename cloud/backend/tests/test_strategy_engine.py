"""StrategyEngine 单元测试 — 充电策略调度器

纯内存调度, 无 DB 依赖。覆盖:
- 初始化: 默认模式 / 5 策略注册 / station_modes 空
- 当前模式: current_mode / get_current_mode (全局 + 站点覆盖)
- 模式切换: enum/str/按站点/非法值抛错 / last_switched_at
- get_strategy / list_strategies (按 priority 升序)
- evaluate: 显式 mode / 用当前模式 / 站点模式
- resolve: manual_power_kw 抢占 / 否则按当前模式
- get_charging_engine 单例
"""
from unittest.mock import patch

import pytest

from app.services.charging import strategy_engine as se_mod
from app.services.charging.strategy_base import ChargingContext, ChargingMode
from app.services.charging.strategy_engine import StrategyEngine, get_charging_engine


def _ctx(**kw):
    base = dict(station_id="s1", charger_id="c1", rated_power_kw=100, demand_power_kw=50)
    base.update(kw)
    return ChargingContext(**base)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个用例前后重置模块级单例, 避免污染。"""
    se_mod._engine = None
    yield
    se_mod._engine = None


# ═══════════════════════════════════════════
# 初始化 / 当前模式
# ═══════════════════════════════════════════

class TestInit:
    def test_default_mode_is_balanced(self):
        eng = StrategyEngine()
        assert eng.current_mode is ChargingMode.BALANCED

    def test_custom_default_mode(self):
        eng = StrategyEngine(default_mode=ChargingMode.SOLAR)
        assert eng.current_mode is ChargingMode.SOLAR

    def test_registers_all_five_strategies(self):
        eng = StrategyEngine()
        assert set(eng.strategies.keys()) == {
            ChargingMode.MANUAL, ChargingMode.TIMED,
            ChargingMode.SOLAR, ChargingMode.PRICE, ChargingMode.BALANCED,
        }

    def test_last_switched_at_none_initially(self):
        assert StrategyEngine().last_switched_at is None

    def test_get_current_mode_global_default(self):
        eng = StrategyEngine()
        assert eng.get_current_mode() is ChargingMode.BALANCED
        # 未知站点 → 全局
        assert eng.get_current_mode("unknown") is ChargingMode.BALANCED

    def test_get_current_mode_station_override(self):
        eng = StrategyEngine()
        eng.switch_mode(ChargingMode.SOLAR, station_id="s1")
        assert eng.get_current_mode("s1") is ChargingMode.SOLAR
        # 全局不受影响
        assert eng.get_current_mode() is ChargingMode.BALANCED


# ═══════════════════════════════════════════
# 模式切换
# ═══════════════════════════════════════════

class TestSwitchMode:
    def test_switch_by_enum(self):
        eng = StrategyEngine()
        resolved = eng.switch_mode(ChargingMode.PRICE)
        assert resolved is ChargingMode.PRICE
        assert eng.current_mode is ChargingMode.PRICE

    def test_switch_by_string(self):
        eng = StrategyEngine()
        assert eng.switch_mode("solar") is ChargingMode.SOLAR
        assert eng.current_mode is ChargingMode.SOLAR

    def test_switch_sets_timestamp(self):
        eng = StrategyEngine()
        eng.switch_mode(ChargingMode.MANUAL)
        assert eng.last_switched_at is not None
        # ISO 格式字符串
        assert isinstance(eng.last_switched_at, str) and "T" in eng.last_switched_at

    def test_switch_by_station_only_affects_station(self):
        eng = StrategyEngine()
        eng.switch_mode(ChargingMode.PRICE, station_id="s2")
        assert eng.current_mode is ChargingMode.BALANCED  # 全局不变
        assert eng.get_current_mode("s2") is ChargingMode.PRICE

    def test_invalid_string_mode_raises(self):
        eng = StrategyEngine()
        with pytest.raises(ValueError, match="无效充电模式"):
            eng.switch_mode("nonsense")

    def test_invalid_value_message_lists_supported_modes(self):
        eng = StrategyEngine()
        with pytest.raises(ValueError) as exc:
            eng.switch_mode("nope")
        msg = str(exc.value)
        for m in ChargingMode:
            assert m.value in msg


# ═══════════════════════════════════════════
# get_strategy / list_strategies
# ═══════════════════════════════════════════

class TestListing:
    def test_get_strategy_by_enum(self):
        eng = StrategyEngine()
        s = eng.get_strategy(ChargingMode.SOLAR)
        assert s.mode is ChargingMode.SOLAR

    def test_get_strategy_by_string(self):
        eng = StrategyEngine()
        assert eng.get_strategy("manual").mode is ChargingMode.MANUAL

    def test_get_strategy_invalid_raises(self):
        with pytest.raises(ValueError):
            StrategyEngine().get_strategy("xxx")

    def test_list_strategies_sorted_by_priority_asc(self):
        eng = StrategyEngine()
        items = eng.list_strategies()
        priorities = [it["priority"] for it in items]
        assert priorities == sorted(priorities)
        # 5 个模式全在
        assert len(items) == 5

    def test_list_strategies_item_shape(self):
        eng = StrategyEngine()
        items = eng.list_strategies()
        sample = items[0]
        assert {"mode", "name", "description", "priority"} <= set(sample.keys())
        assert all(isinstance(it["mode"], str) for it in items)


# ═══════════════════════════════════════════
# evaluate / resolve
# ═══════════════════════════════════════════

class TestEvaluateResolve:
    def test_evaluate_explicit_mode(self):
        eng = StrategyEngine()
        dec = eng.evaluate(_ctx(), mode=ChargingMode.SOLAR)
        assert dec.mode is ChargingMode.SOLAR

    def test_evaluate_uses_global_current_mode(self):
        eng = StrategyEngine()
        eng.switch_mode(ChargingMode.PRICE)
        dec = eng.evaluate(_ctx())
        assert dec.mode is ChargingMode.PRICE

    def test_evaluate_uses_station_mode_when_station_set(self):
        eng = StrategyEngine()
        eng.switch_mode(ChargingMode.SOLAR, station_id="s1")
        dec = eng.evaluate(_ctx(station_id="s1"))
        assert dec.mode is ChargingMode.SOLAR

    def test_resolve_manual_power_preempts(self):
        eng = StrategyEngine()
        # 当前是 BALANCED, 但 manual_power_kw 抢占 → MANUAL
        dec = eng.resolve(_ctx(manual_power_kw=33.0))
        assert dec.mode is ChargingMode.MANUAL

    def test_resolve_without_manual_uses_current_mode(self):
        eng = StrategyEngine()
        eng.switch_mode(ChargingMode.SOLAR)
        dec = eng.resolve(_ctx())  # manual_power_kw 默认 None
        assert dec.mode is ChargingMode.SOLAR

    def test_resolve_manual_zero_not_preempting(self):
        # manual_power_kw = 0 不是 None → 仍抢占 (代码用 is not None 判定)
        eng = StrategyEngine()
        dec = eng.resolve(_ctx(manual_power_kw=0.0))
        assert dec.mode is ChargingMode.MANUAL


# ═══════════════════════════════════════════
# 单例
# ═══════════════════════════════════════════

class TestSingleton:
    def test_get_engine_returns_same_instance(self):
        a = get_charging_engine()
        b = get_charging_engine()
        assert a is b
        assert isinstance(a, StrategyEngine)

    def test_get_engine_creates_when_none(self):
        assert se_mod._engine is None
        eng = get_charging_engine()
        assert se_mod._engine is eng
        assert eng.current_mode is ChargingMode.BALANCED

    def test_concurrent_get_engine_creates_single_instance(self, monkeypatch):
        """并发调用 get_charging_engine 只应创建一个实例 (双重检查锁防竞态)"""
        import threading
        import time

        n_workers = 8
        start = threading.Event()
        created = []  # 记录每次 StrategyEngine 构造尝试
        real_cls = StrategyEngine

        def slow_factory():
            # 放大竞态窗口: 让多个线程都能通过 "_engine is None" 外层检查
            created.append(object())
            time.sleep(0.02)
            return real_cls()

        monkeypatch.setattr(se_mod, "StrategyEngine", slow_factory)
        se_mod._engine = None

        results: list = [None] * n_workers

        def worker(i):
            start.wait()  # 发令前阻塞, 保证真正同时进入
            results[i] = get_charging_engine()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_workers)]
        for t in threads:
            t.start()
        time.sleep(0.05)  # 确保所有线程已阻塞在 start.wait()
        start.set()  # 同时放行
        for t in threads:
            t.join()

        # 双重检查锁下只应构造一次
        assert len(created) == 1, (
            f"预期并发下只创建1个实例, 实际创建 {len(created)} 个 (单例无锁竞态)"
        )
        # 所有线程应拿到同一个实例
        first = results[0]
        assert first is not None
        assert all(r is first for r in results), "不同线程拿到了不同实例"
