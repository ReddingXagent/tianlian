"""
VPPLPOptimizer plan_id 同秒唯一性测试 (services/vpp/test_lp_plan_id.py)

被测: app/services/vpp/lp_optimizer.py 的两个 plan_id 生成点
  - _lp_result_to_plan LP 求解成功路径 (L411 附近, 前缀 'lp_')
  - _empty_plan 空资源降级路径 (L444, 前缀 'lp_empty_')

背景 (卡 235160b5; dispatch_optimizer 修复卡 8c15dea6f 自审遗留项):
  旧实现 f"lp_{strftime('%Y%m%d%H%M%S')}" / f"lp_empty_{...}" 仅秒级粒度,
  与 dispatch_optimizer 修复前同款缺陷 — 同秒并发产出两个同前缀 LP 计划 → plan_id 完全相同,
  污染日志与上报 payload 追踪。

  修复: 复用 dispatch_optimizer/optimizer._make_plan_id
        (格式 {prefix}{14位ts}_{6位hex uuid4}), 替换 lp_optimizer 全部裸生成点。

本文件给出 RED→GREEN 证据:
- TestLpLegacyCollisionBaseline : 复刻旧逻辑, 冻结秒级时间戳后 100 次全碰撞 (对照基线)
- TestLpPrefixUniqueSameSecond  : _make_plan_id 在 lp_/lp_empty_ 前缀下冻结时钟后 100 次仍全唯一
- TestLpEntriesUniqueSameSecond : 真集成 — VPPLPOptimizer.optimize_dispatch 两个入口
                                  (lp_ 成功路径 / lp_empty_ 空资源路径) 冻结时钟后各 100 次全唯一
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.vpp import lp_optimizer as lp_mod
from app.services.vpp.dispatch_optimizer import optimizer as optimizer_module
from app.services.vpp.dispatch_optimizer.optimizer import _make_plan_id
from app.services.vpp.dispatch_optimizer import (
    DispatchMode,
    DispatchPlan,
    ResourceType,
    ResourceCapability,
    StationStatus,
)
from app.services.vpp.lp_optimizer import VPPLPOptimizer


# ─── 工具: 冻结 optimizer 模块的 datetime, 固定秒级时间戳 ───

class _FrozenDateTime:
    """假 datetime: now() 恒返回 fixed, 用于冻结 plan_id 的秒级时间戳部分。

    _make_plan_id 内部 `datetime.now().strftime('%Y%m%d%H%M%S')` 会恒定,
    使同秒生成的 plan_id 时间戳前缀完全相同 → 唯一性只能靠 uuid 后缀保证。

    旧 lp_optimizer 裸实现读 lp_mod.datetime; 修复后读 optimizer_module.datetime;
    故集成测试同时冻结两个命名空间, 保证 RED(旧码)与 GREEN(新码)都确定可复现。
    """
    fixed = datetime(2026, 8, 6, 7, 5, 0)  # 冻结时刻 → 时间戳 20260806070500

    @classmethod
    def now(cls, tz=None):
        return cls.fixed


def _legacy_plan_id(prefix: str, now: datetime) -> str:
    """复刻旧实现: prefix(含尾下划线) + 秒级时间戳, 无 uuid 后缀。

    忠实复刻旧代码 f"lp_{strftime(...)}" 的拼接(prefix 自带下划线, 直接接时间戳)。
    """
    return f"{prefix}{now.strftime('%Y%m%d%H%M%S')}"


# ─── 工厂 (与 tests/services/vpp/test_lp_optimizer.py 对齐, 自包含) ───

def _resource(rid, rtype, *, station_id="ST-001", rated=100.0, current=0.0,
              available=100.0, soc=0.8, efficiency=0.95, ramp=100.0, priority=5):
    return ResourceCapability(
        resource_id=rid, resource_type=rtype, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        soc=soc, efficiency=efficiency, ramp_rate_kw_per_min=ramp, priority=priority,
    )


def _station(sid="ST-001", online=True):
    return StationStatus(
        station_id=sid, station_name="S-" + sid, total_pv_kw=200, total_battery_kwh=500,
        total_ev_chargers=10, current_load_kw=100, current_pv_output_kw=120,
        current_battery_soc=0.7, available_dispatch_kw=200, online=online,
    )


def _base_mock(price=0.9, valley=0.3):
    """固定电价/谷价 + SOC 阈值的 base_optimizer 替身 (不触 DB, 无 datetime 依赖)。"""
    m = MagicMock()
    m.get_current_price.return_value = price
    m.VALLEY_PRICE = valley
    m.BATTERY_SOC_MIN = 0.10
    m.BATTERY_DISCHARGE_SOC_FLOOR = 0.20
    m.BATTERY_SOC_MAX = 0.95
    m._battery_discharge_soc_floor = 0.20
    return m


def _lp_ok(x, message="optimal"):
    return SimpleNamespace(success=True, x=np.array(x, dtype=float), message=message)


# ═══════════════════════════════════════════════════════════
# 对照基线: 旧实现同秒必碰撞
# ═══════════════════════════════════════════════════════════

class TestLpLegacyCollisionBaseline:
    """旧实现(秒级时间戳)冻结时钟后 100 次生成结果完全相同。

    RED→GREEN 的对照证据: 旧逻辑天然无法区分同秒计划, 100 次退化为 1 个唯一 id。
    """

    @pytest.mark.parametrize("prefix", ["lp_", "lp_empty_"])
    def test_legacy_same_second_all_collide(self, prefix):
        now = _FrozenDateTime.fixed
        ids = [_legacy_plan_id(prefix, now) for _ in range(100)]
        assert len(set(ids)) == 1  # 100 次全相同 → 旧实现必碰撞
        assert ids[0] == f"{prefix}20260806070500"


# ═══════════════════════════════════════════════════════════
# 共享生成器: lp_ / lp_empty_ 前缀同秒唯一
# ═══════════════════════════════════════════════════════════

class TestLpPrefixUniqueSameSecond:
    """_make_plan_id 在 lp_/lp_empty_ 前缀下, 冻结时钟后 100 次仍全唯一 (uuid 后缀消除碰撞)。"""

    @pytest.mark.parametrize("prefix", ["lp_", "lp_empty_"])
    def test_unique_100_within_same_second(self, prefix, monkeypatch):
        monkeypatch.setattr(optimizer_module, "datetime", _FrozenDateTime)
        ids = [_make_plan_id(prefix) for _ in range(100)]
        assert len(ids) == 100
        assert len(set(ids)) == 100  # 冻结时钟下全唯一 → uuid 后缀生效

    @pytest.mark.parametrize("prefix", ["lp_", "lp_empty_"])
    def test_format_timestamp_and_hex_suffix(self, prefix, monkeypatch):
        """冻结时钟: 去掉前缀后 = '20260806070500_<6位hex>'。"""
        monkeypatch.setattr(optimizer_module, "datetime", _FrozenDateTime)
        pid = _make_plan_id(prefix)
        assert pid.startswith(prefix)
        body = pid[len(prefix):]                      # '20260806070500_ab12cd'
        ts, sep, hex_suffix = body.partition("_")
        assert sep == "_"
        assert ts == "20260806070500"                  # 14位秒级时间戳, 冻结后恒定
        assert len(hex_suffix) == 6                    # uuid4().hex[:6]
        assert all(c in "0123456789abcdef" for c in hex_suffix)


# ═══════════════════════════════════════════════════════════
# 真集成: VPPLPOptimizer 两个入口同秒 plan_id 全唯一
# ═══════════════════════════════════════════════════════════

class TestLpEntriesUniqueSameSecond:
    """optimize_dispatch 的两个 plan_id 入口冻结时钟后各 100 次全唯一。

    旧实现: lp_mod.datetime 被冻结 → 同秒 strftime 恒定 → 100 次全相同 (本断言 RED)。
    修复后: plan_id 经 _make_plan_id → uuid 后缀保证唯一 (GREEN)。
    """

    def test_lp_success_path_unique_same_second(self, monkeypatch):
        """LP 求解成功路径 (lp_ 前缀) 冻结时钟后 100 次全唯一。"""
        monkeypatch.setattr(optimizer_module, "datetime", _FrozenDateTime)
        monkeypatch.setattr(lp_mod, "datetime", _FrozenDateTime)  # 旧码 RED 必要

        opt = VPPLPOptimizer(base_optimizer=_base_mock(price=0.9))
        res = [_resource("BAT", ResourceType.BATTERY, station_id="ST-001",
                         soc=0.8, available=100, rated=100)]

        ids = []
        with patch("app.services.vpp.lp_optimizer.linprog", return_value=_lp_ok([80.0])):
            for _ in range(100):
                plan = opt.optimize_dispatch([], res, target_power_kw=80,
                                             duration_min=15, mode=DispatchMode.ECONOMIC)
                ids.append(plan.plan_id)

        assert all(pid.startswith("lp_") for pid in ids)
        assert not any(pid.startswith("lp_empty_") for pid in ids)
        assert len(set(ids)) == 100  # 旧码全相同 → RED; 修复后 uuid 后缀全唯一

    def test_lp_empty_path_unique_same_second(self, monkeypatch):
        """空资源降级路径 (lp_empty_ 前缀) 冻结时钟后 100 次全唯一。"""
        monkeypatch.setattr(optimizer_module, "datetime", _FrozenDateTime)
        monkeypatch.setattr(lp_mod, "datetime", _FrozenDateTime)  # 旧码 RED 必要

        opt = VPPLPOptimizer(base_optimizer=_base_mock(price=0.9))
        stations = [_station()]

        ids = []
        for _ in range(100):
            plan = opt.optimize_dispatch(stations, [], target_power_kw=50,
                                         mode=DispatchMode.ECONOMIC)
            ids.append(plan.plan_id)

        assert all(pid.startswith("lp_empty_") for pid in ids)
        assert len(set(ids)) == 100  # 旧码全相同 → RED; 修复后 uuid 后缀全唯一

    def test_lp_and_empty_distinct_same_second(self, monkeypatch):
        """同秒生成的 lp_ 计划与 lp_empty_ 计划 plan_id 互不相同 (跨入口不碰撞)。"""
        monkeypatch.setattr(optimizer_module, "datetime", _FrozenDateTime)
        monkeypatch.setattr(lp_mod, "datetime", _FrozenDateTime)

        opt = VPPLPOptimizer(base_optimizer=_base_mock(price=0.9))
        res = [_resource("BAT", ResourceType.BATTERY, soc=0.8, available=100, rated=100)]

        with patch("app.services.vpp.lp_optimizer.linprog", return_value=_lp_ok([80.0])):
            lp_plan = opt.optimize_dispatch([], res, target_power_kw=80,
                                            duration_min=15, mode=DispatchMode.ECONOMIC)
        empty_plan = opt.optimize_dispatch([_station()], [], target_power_kw=50,
                                           mode=DispatchMode.ECONOMIC)

        assert lp_plan.plan_id != empty_plan.plan_id  # 前缀已不同; 旧码下也必不同
        assert lp_plan.plan_id.startswith("lp_")
        assert empty_plan.plan_id.startswith("lp_empty_")
