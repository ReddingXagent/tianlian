"""test_storage_optimizer.py — 储能调度优化器单元测试

覆盖: StorageAction dataclass, StorageOptimizerConfig 默认/覆盖,
StorageOptimizer.optimize() 全分支(SOC过低/过高, 温度超限, 光伏余电,
低谷充电, 高峰放电, 平段待机), config 注入优先级, 安全区间判定。
"""
import pytest
from unittest.mock import patch

from app.services.charging.storage_optimizer import (
    StorageAction,
    StorageOptimizerConfig,
    StorageOptimizer,
)


# ─── StorageAction dataclass ───

class TestStorageAction:
    def test_create_charge_action(self):
        a = StorageAction(
            action="charge", power_kw=50, target_soc=0.5,
            reason="test", health_ok=True, within_safe_range=True
        )
        assert a.action == "charge"
        assert a.power_kw == 50
        assert a.health_ok is True

    def test_create_discharge_action_negative_power(self):
        a = StorageAction("discharge", -30, 0.5, "peak", True, True)
        assert a.power_kw == -30
        assert a.action == "discharge"

    def test_action_fields_are_mutable(self):
        a = StorageAction("idle", 0, 0.5, "", True, True)
        a.action = "charge"
        a.power_kw = 100
        assert a.action == "charge"
        assert a.power_kw == 100


# ─── StorageOptimizerConfig ───

class TestStorageOptimizerConfig:
    def test_defaults(self):
        c = StorageOptimizerConfig()
        assert c.valley_price_threshold == 0.40
        assert c.peak_price_threshold == 0.90
        assert c.soc_floor == 0.10
        assert c.soc_ceiling == 0.90

    def test_custom_values(self):
        c = StorageOptimizerConfig(
            valley_price_threshold=0.30,
            peak_price_threshold=1.20,
            soc_floor=0.15,
            soc_ceiling=0.85,
        )
        assert c.valley_price_threshold == 0.30
        assert c.peak_price_threshold == 1.20
        assert c.soc_floor == 0.15
        assert c.soc_ceiling == 0.85


# ─── StorageOptimizer — SOC 分支 ───

class TestStorageOptimizerSocBranches:
    def setup_method(self):
        self.opt = StorageOptimizer()

    def test_soc_below_floor_forces_charge(self):
        r = self.opt.optimize(soc=0.05)
        assert r.action == "charge"
        assert r.power_kw == StorageOptimizer.DEFAULT_CHARGE_KW
        assert r.health_ok is False
        assert r.within_safe_range is False

    def test_soc_below_floor_custom_config(self):
        opt = StorageOptimizer(StorageOptimizerConfig(soc_floor=0.20))
        r = opt.optimize(soc=0.15)  # 0.15 < 0.20
        assert r.action == "charge"
        assert r.health_ok is False

    def test_soc_above_ceiling_with_peak_price_discharges(self):
        r = self.opt.optimize(soc=0.95, grid_price=1.0, load_kw=20)
        assert r.action == "discharge"
        assert r.power_kw < 0
        assert r.health_ok is False

    def test_soc_above_ceiling_with_load_discharges(self):
        r = self.opt.optimize(soc=0.95, load_kw=30)
        assert r.action == "discharge"
        assert r.power_kw < 0

    def test_soc_above_ceiling_no_load_idles(self):
        r = self.opt.optimize(soc=0.95)
        assert r.action == "idle"
        assert r.power_kw == 0.0

    def test_soc_above_ceiling_below_peak_price_idles(self):
        r = self.opt.optimize(soc=0.95, grid_price=0.50, load_kw=0)
        assert r.action == "idle"

    def test_soc_within_safe_range_flag(self):
        r = self.opt.optimize(soc=0.5)
        assert r.within_safe_range is True

    def test_soc_at_floor_boundary(self):
        """SOC == floor is safe (boundary inclusive)"""
        r = self.opt.optimize(soc=0.10)
        assert r.within_safe_range is True
        assert r.health_ok is True

    def test_soc_at_ceiling_boundary(self):
        """SOC == ceiling is safe (boundary inclusive)"""
        r = self.opt.optimize(soc=0.90)
        assert r.within_safe_range is True


# ─── StorageOptimizer — 温度分支 ───

class TestStorageOptimizerTemperature:
    def setup_method(self):
        self.opt = StorageOptimizer()

    def test_temp_above_max_with_peak_price_discharges(self):
        r = self.opt.optimize(soc=0.5, temp_c=50, grid_price=1.0, load_kw=10)
        assert r.action == "discharge"
        assert r.health_ok is False

    def test_temp_above_max_without_peak_price_idles(self):
        r = self.opt.optimize(soc=0.5, temp_c=50, grid_price=0.50)
        assert r.action == "idle"
        assert r.health_ok is False

    def test_temp_at_max_ok(self):
        """温度 == 45℃ 仍在安全范围"""
        r = self.opt.optimize(soc=0.5, temp_c=45.0)
        assert r.health_ok is True

    def test_temp_none_is_ok(self):
        r = self.opt.optimize(soc=0.5, temp_c=None)
        assert r.health_ok is True


# ─── StorageOptimizer — 光伏/电价/负荷 ───

class TestStorageOptimizerDispatch:
    def setup_method(self):
        self.opt = StorageOptimizer()

    def test_pv_surplus_charges(self):
        r = self.opt.optimize(soc=0.5, pv_surplus_kw=30)
        assert r.action == "charge"
        assert r.power_kw == 30
        assert "光伏" in r.reason

    def test_pv_surplus_capped_at_default_charge_kw(self):
        r = self.opt.optimize(soc=0.5, pv_surplus_kw=200)
        assert r.power_kw == StorageOptimizer.DEFAULT_CHARGE_KW

    def test_valley_price_charges_from_grid(self):
        r = self.opt.optimize(soc=0.5, grid_price=0.30)
        assert r.action == "charge"
        assert r.power_kw == StorageOptimizer.DEFAULT_CHARGE_KW
        assert "低谷" in r.reason

    def test_valley_price_custom_config(self):
        opt = StorageOptimizer(StorageOptimizerConfig(valley_price_threshold=0.20))
        r = opt.optimize(soc=0.5, grid_price=0.25)  # 0.25 > 0.20 → no valley
        assert r.action != "charge" or "低谷" not in r.reason

    def test_peak_price_with_load_discharges(self):
        r = self.opt.optimize(soc=0.5, grid_price=1.0, load_kw=40)
        assert r.action == "discharge"
        assert r.power_kw == -min(50, max(40, 1.0))

    def test_peak_price_no_load_still_discharges(self):
        """高峰电价即使无负荷也放电（load_kw=0 → max(0,1.0)=1.0）"""
        r = self.opt.optimize(soc=0.5, grid_price=1.0, load_kw=0)
        assert r.action == "discharge"

    def test_mid_price_no_pv_idles(self):
        r = self.opt.optimize(soc=0.5, grid_price=0.60)
        assert r.action == "idle"
        assert r.power_kw == 0.0

    def test_default_target_soc(self):
        r = self.opt.optimize(soc=0.5)
        assert r.target_soc == StorageOptimizer.TARGET_SOC

    def test_custom_target_soc(self):
        r = self.opt.optimize(soc=0.5, target_soc=0.8)
        assert r.target_soc == 0.8

    def test_pv_takes_priority_over_valley_price(self):
        """光伏余电优先于低谷电价"""
        r = self.opt.optimize(soc=0.5, pv_surplus_kw=20, grid_price=0.10)
        assert r.action == "charge"
        assert "光伏" in r.reason


# ─── Discharge power formula ───

class TestDischargePowerFormula:
    def test_discharge_power_capped_by_default(self):
        opt = StorageOptimizer()
        r = opt.optimize(soc=0.5, grid_price=1.0, load_kw=200)
        assert r.power_kw == -StorageOptimizer.DEFAULT_DISCHARGE_KW

    def test_discharge_power_follows_load_when_smaller(self):
        opt = StorageOptimizer()
        r = opt.optimize(soc=0.5, grid_price=1.0, load_kw=10)
        assert r.power_kw == -10.0

    def test_discharge_power_min_one_kw(self):
        """load_kw=0 时放电功率至少 1kW (max(0, 1.0)=1.0)"""
        opt = StorageOptimizer()
        r = opt.optimize(soc=0.5, grid_price=1.0, load_kw=0)
        assert r.power_kw == -1.0


# ─── 输入校验: SOC 范围 + 负值拒绝 (任务1+2) ───

class TestInputValidation:
    def setup_method(self):
        self.opt = StorageOptimizer()

    def test_soc_negative_raises(self):
        with pytest.raises(ValueError):
            self.opt.optimize(soc=-0.1)

    def test_soc_over_one_raises(self):
        with pytest.raises(ValueError):
            self.opt.optimize(soc=1.5)

    def test_negative_pv_surplus_raises(self):
        with pytest.raises(ValueError):
            self.opt.optimize(soc=0.5, pv_surplus_kw=-10)

    def test_negative_load_raises(self):
        with pytest.raises(ValueError):
            self.opt.optimize(soc=0.5, load_kw=-5)

    def test_negative_grid_price_raises(self):
        with pytest.raises(ValueError):
            self.opt.optimize(soc=0.5, grid_price=-0.3)

    def test_soc_boundary_zero_ok(self):
        """soc=0 合法(边界)→ 强制充电恢复, 不抛"""
        r = self.opt.optimize(soc=0)
        assert r.action == "charge"

    def test_soc_boundary_one_ok(self):
        """soc=1 合法(边界)→ 禁充, 不抛"""
        r = self.opt.optimize(soc=1.0)
        assert r.action in ("idle", "discharge")

    def test_grid_price_none_ok(self):
        """grid_price=None 合法(未知电价)"""
        r = self.opt.optimize(soc=0.5, grid_price=None)
        assert r.action == "idle"

    # ─── target_soc 范围校验 [0,1] (卡 2af0f1ce) ───

    def test_target_soc_over_one_raises(self):
        """target_soc > 1 → 拒绝"""
        with pytest.raises(ValueError):
            self.opt.optimize(soc=0.5, target_soc=1.5)

    def test_target_soc_negative_raises(self):
        """target_soc < 0 → 拒绝"""
        with pytest.raises(ValueError):
            self.opt.optimize(soc=0.5, target_soc=-0.5)

    def test_target_soc_boundary_zero_ok(self):
        """target_soc=0 合法(闭区间边界)→ 不抛"""
        r = self.opt.optimize(soc=0.5, target_soc=0.0)
        assert r.target_soc == 0.0

    def test_target_soc_boundary_one_ok(self):
        """target_soc=1 合法(闭区间边界)→ 不抛"""
        r = self.opt.optimize(soc=0.5, target_soc=1.0)
        assert r.target_soc == 1.0

    def test_target_soc_none_ok(self):
        """target_soc=None → 走默认值, 不抛"""
        r = self.opt.optimize(soc=0.5, target_soc=None)
        assert r.target_soc == StorageOptimizer.TARGET_SOC

    # ─── temp_c 合理性范围校验 [-50, 100] (卡 2af0f1ce) ───

    def test_temp_too_high_raises(self):
        """temp_c > 100 → 传感器故障/脏数据, 拒绝"""
        with pytest.raises(ValueError):
            self.opt.optimize(soc=0.5, temp_c=150)

    def test_temp_too_low_raises(self):
        """temp_c < -50 → 物理不合理, 拒绝"""
        with pytest.raises(ValueError):
            self.opt.optimize(soc=0.5, temp_c=-100)

    def test_temp_boundary_high_ok(self):
        """temp_c=100 合法(闭区间边界, 仍走温度过高分支禁充电)→ 不抛"""
        r = self.opt.optimize(soc=0.5, temp_c=100)
        # 100 > 45(TEMP_MAX_C) → 温度过高分支, 无峰价无负荷 → idle, health_ok=False
        assert r.health_ok is False

    def test_temp_boundary_low_ok(self):
        """temp_c=-50 合法(闭区间边界)→ 不抛"""
        r = self.opt.optimize(soc=0.5, temp_c=-50)
        assert r.health_ok is True


# ─── 放电 SOC 下限动态校验 (任务3: 不低于 0.10) ───

class TestDischargeSocFloor:
    def test_discharge_below_floor_idles_not_discharge(self):
        """soc 在安全区间但低于放电下限(默认0.20) + 峰价 → 保护性 idle, 不放电"""
        opt = StorageOptimizer()
        r = opt.optimize(soc=0.12, grid_price=1.0, load_kw=20)
        assert r.action == "idle"
        assert r.power_kw == 0.0

    def test_discharge_above_floor_discharges(self):
        """soc 高于放电下限 + 峰价 → 正常放电(回归)"""
        opt = StorageOptimizer()
        r = opt.optimize(soc=0.5, grid_price=1.0, load_kw=20)
        assert r.action == "discharge"
        assert r.power_kw < 0

    def test_discharge_floor_clamped_to_soc_min(self):
        """config 设 discharge_soc_floor=0.05 → 属性 clamp 到 SOC_MIN(0.10), 保证不低于绝对地板"""
        opt = StorageOptimizer(StorageOptimizerConfig(discharge_soc_floor=0.05))
        assert opt._discharge_soc_floor == 0.10

    def test_discharge_floor_respects_higher_config(self):
        """config 设 discharge_soc_floor=0.30 → 实际用 0.30(高于 SOC_MIN)"""
        opt = StorageOptimizer(StorageOptimizerConfig(discharge_soc_floor=0.30))
        assert opt._discharge_soc_floor == 0.30
        # soc=0.25 < 0.30 → 不放电
        r = opt.optimize(soc=0.25, grid_price=1.0, load_kw=20)
        assert r.action == "idle"

    def test_temp_high_low_soc_idles_not_discharge(self):
        """温度超限 + soc 低于放电下限 → idle(不能放电降温)"""
        opt = StorageOptimizer()
        r = opt.optimize(soc=0.12, temp_c=50, grid_price=1.0, load_kw=10)
        assert r.action == "idle"
