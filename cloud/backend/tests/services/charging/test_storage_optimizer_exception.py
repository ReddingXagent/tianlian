"""test_storage_optimizer_exception.py — StorageOptimizer.optimize 入口异常保护测试

被测卡片: d23b9a2d
同卡: templates.py (见 tests/services/runbook_engine/test_templates_exception.py)

设计: optimize() 为纯计算入口(无 DB 查询/写入), 故通过 monkeypatch 注入内部
运行时异常, 验证顶层 try/except 健壮性兜底:
1. 非校验类意外异常 → 不向调用方裸抛, 返回 idle 安全默认 StorageAction,
   记录 logger.exception (调用方 charging_strategy.py 直接解引用 action 字段,
   裸抛会致 HTTP 500)
2. 输入校验 ValueError(fail-fast 契约) → 仍向上传播, 不被吞(正常流程不受影响;
   现有 TestInputValidation 30+ 用例依赖此契约)
3. 合法输入 → 结果与未加保护时完全一致(回归保护)
"""
import logging

import pytest

from app.services.charging.storage_optimizer import (
    StorageAction,
    StorageOptimizer,
)

LOGGER_NAME = "app.services.charging.storage_optimizer"


def _patch_soc_floor_to_raise(monkeypatch):
    """注入内部异常: 把 _soc_floor property 替换为抛 RuntimeError。

    optimize() 在输入校验通过后第一个被访问的内部属性就是 _soc_floor
    (``safe = self._soc_floor <= soc <= self._soc_ceiling``), 让它抛可精确
    模拟“校验之后、计算过程中”的意外异常(如依赖数据获取失败)。
    """
    def _boom(self):
        raise RuntimeError("内部数据获取失败(模拟)")
    monkeypatch.setattr(StorageOptimizer, "_soc_floor", property(_boom))


# ─── 1. 内部意外异常 → 安全降级 idle ───

class TestOptimizeInternalExceptionSafety:
    def test_internal_exception_returns_idle_safe_default(self, monkeypatch):
        _patch_soc_floor_to_raise(monkeypatch)
        opt = StorageOptimizer()

        result = opt.optimize(soc=0.5)  # 不应抛

        assert isinstance(result, StorageAction)
        assert result.action == "idle"
        assert result.power_kw == 0.0

    def test_internal_exception_does_not_propagate(self, monkeypatch):
        _patch_soc_floor_to_raise(monkeypatch)
        opt = StorageOptimizer()
        # 多种合法入参均不应裸抛
        opt.optimize(soc=0.5, pv_surplus_kw=30, grid_price=0.3, load_kw=10, temp_c=25)

    def test_internal_exception_logs_error(self, monkeypatch, caplog):
        _patch_soc_floor_to_raise(monkeypatch)
        opt = StorageOptimizer()

        with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
            opt.optimize(soc=0.5)

        # logger.exception → ERROR 级 + 携带 exc_info
        assert any(r.levelno == logging.ERROR and r.exc_info for r in caplog.records)

    def test_internal_exception_target_soc_uses_input_when_given(self, monkeypatch):
        _patch_soc_floor_to_raise(monkeypatch)
        opt = StorageOptimizer()

        result = opt.optimize(soc=0.5, target_soc=0.7)

        assert result.target_soc == 0.7

    def test_internal_exception_target_soc_falls_back_to_default(self, monkeypatch):
        _patch_soc_floor_to_raise(monkeypatch)
        opt = StorageOptimizer()

        result = opt.optimize(soc=0.5)

        assert result.target_soc == StorageOptimizer.TARGET_SOC


# ─── 2. ValueError 输入校验(fail-fast) 必须保留向上传播 ───

class TestInputValidationPreserved:
    """输入校验是正常流程契约, 顶层异常保护不得吞掉。"""

    def setup_method(self):
        self.opt = StorageOptimizer()

    def test_invalid_soc_still_raises(self):
        with pytest.raises(ValueError):
            self.opt.optimize(soc=-0.1)

    def test_invalid_pv_still_raises(self):
        with pytest.raises(ValueError):
            self.opt.optimize(soc=0.5, pv_surplus_kw=-10)

    def test_invalid_target_soc_still_raises(self):
        with pytest.raises(ValueError):
            self.opt.optimize(soc=0.5, target_soc=1.5)

    def test_invalid_temp_still_raises(self):
        with pytest.raises(ValueError):
            self.opt.optimize(soc=0.5, temp_c=150)


# ─── 3. 正常流程结果不变(回归保护) ───

class TestNormalFlowUnchanged:
    def test_soc_low_forces_charge(self):
        r = StorageOptimizer().optimize(soc=0.05)
        assert r.action == "charge"
        assert r.power_kw == StorageOptimizer.DEFAULT_CHARGE_KW

    def test_pv_surplus_charges(self):
        r = StorageOptimizer().optimize(soc=0.5, pv_surplus_kw=30)
        assert r.action == "charge"
        assert r.power_kw == 30

    def test_peak_price_discharges(self):
        r = StorageOptimizer().optimize(soc=0.5, grid_price=1.0, load_kw=40)
        assert r.action == "discharge"
        assert r.power_kw < 0

    def test_idle_when_neutral(self):
        r = StorageOptimizer().optimize(soc=0.5)
        assert r.action == "idle"
        assert r.power_kw == 0.0
