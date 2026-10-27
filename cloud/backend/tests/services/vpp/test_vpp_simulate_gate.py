"""
VPP_SIMULATE 生产模式门控测试 (卡 1b2f4cc4 step3)

被测文件: app/services/vpp/dispatch_optimizer/__init__.py get_vpp_coordinator()
验证点:
- settings.VPP_SIMULATE == "0" → coordinator 不加载模拟站点数据 (生产模式)
- settings.VPP_SIMULATE != "0" (默认 "1") → coordinator 加载 5 个模拟站点
- 单例重置: 每个测试 monkeypatch.setattr(dispatch_optimizer, "_coordinator", None),
  避免跨测试共享已初始化单例造成互相污染
"""
from __future__ import annotations

from app.core.config import settings
from app.services.vpp import dispatch_optimizer


def _station_count(coordinator) -> int:
    return len(list(coordinator.stations.values()))


def test_prod_mode_no_simulated_stations(monkeypatch):
    """VPP_SIMULATE='0' 时 get_vpp_coordinator 不加载模拟站点数据"""
    monkeypatch.setattr(dispatch_optimizer, "_coordinator", None)
    monkeypatch.setattr(settings, "VPP_SIMULATE", "0")
    coord = dispatch_optimizer.get_vpp_coordinator()
    assert _station_count(coord) == 0


def test_dev_mode_loads_simulated_stations(monkeypatch):
    """VPP_SIMULATE='1' (开发模式) 时 coordinator 加载 5 个模拟站点"""
    monkeypatch.setattr(dispatch_optimizer, "_coordinator", None)
    monkeypatch.setattr(settings, "VPP_SIMULATE", "1")
    coord = dispatch_optimizer.get_vpp_coordinator()
    assert _station_count(coord) == 5


def test_dev_mode_default_value(monkeypatch):
    """配置默认 VPP_SIMULATE='1' (非 '0' 即开) → 加载模拟数据"""
    monkeypatch.setattr(dispatch_optimizer, "_coordinator", None)
    monkeypatch.setattr(settings, "VPP_SIMULATE", "true")
    coord = dispatch_optimizer.get_vpp_coordinator()
    assert _station_count(coord) == 5


def test_singleton_reset_between_modes(monkeypatch):
    """重置单例后重新初始化, 门控按新配置生效 (不残留上一个模式的站点)"""
    # 先以生产模式初始化
    monkeypatch.setattr(dispatch_optimizer, "_coordinator", None)
    monkeypatch.setattr(settings, "VPP_SIMULATE", "0")
    prod = dispatch_optimizer.get_vpp_coordinator()
    assert _station_count(prod) == 0
    # 重置单例切开发模式: 必须重新加载, 且不与旧实例共享状态
    monkeypatch.setattr(dispatch_optimizer, "_coordinator", None)
    monkeypatch.setattr(settings, "VPP_SIMULATE", "1")
    dev = dispatch_optimizer.get_vpp_coordinator()
    assert dev is not prod
    assert _station_count(dev) == 5
