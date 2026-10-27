"""
DispatchPlan.plan_id 生成器单元测试 (services/vpp/test_dispatch_plan_id.py)

被测: app/services/vpp/dispatch_optimizer/optimizer._make_plan_id
      coordinator 经 `from .optimizer import _make_plan_id` 复用同一生成器。

背景 (卡 d62f6d93): 旧实现 f"{prefix}_{strftime('%Y%m%d%H%M%S')}" 仅秒级粒度,
同一秒内生成两个同前缀计划 → plan_id 完全相同, 污染 coordinator 日志追踪
(L268) 与上报 payload (L285)。触发路径:
- 降级链 safe→后续计划背靠背生成
- 削峰(ps_)与需求响应(dr_)同秒触发
- coordinator L50 与 optimizer L88 的 safe_ 异常降级双入口

本文件给出 RED→GREEN 证据:
- TestLegacyCollisionBaseline : 复刻旧逻辑, 冻结秒级时间戳后 100 次全碰撞 (对照基线)
- TestMakePlanIdUnique        : 新生成器冻结时钟后 100 次仍全唯一
- TestMakePlanIdPrefix        : 各前缀(safe_/eco_/ps_/dr_/coord_)正确, 格式 = 前缀+14位时间戳+6位hex
- TestSafeEntryNoCollision    : coordinator._safe_plan 与 optimizer._safe_default_plan
                                两个 safe_ 双入口同秒 plan_id 不同
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.services.vpp.dispatch_optimizer import (
    DispatchMode,
    MultiStationCoordinator,
    VPPOptimizer,
)
from app.services.vpp.dispatch_optimizer import optimizer as optimizer_module
from app.services.vpp.dispatch_optimizer.optimizer import _make_plan_id


# ─── 工具: 冻结 optimizer 模块的 datetime, 固定秒级时间戳 ───

class _FrozenDateTime:
    """假 datetime: now() 恒返回 fixed, 用于冻结 plan_id 的秒级时间戳部分。

    optimizer._make_plan_id 内部 `datetime.now().strftime('%Y%m%d%H%M%S')` 会恒定,
    使同秒生成的 plan_id 时间戳前缀完全相同 → 唯一性只能靠 uuid 后缀保证。
    """
    fixed = datetime(2026, 8, 6, 7, 5, 0)  # 冻结时刻 → 时间戳 20260806070500

    @classmethod
    def now(cls, tz=None):
        return cls.fixed


def _legacy_plan_id(prefix: str, now: datetime) -> str:
    """复刻旧实现: prefix(含尾下划线) + 秒级时间戳, 无 uuid 后缀。

    忠实复刻旧代码 f"eco_{strftime(...)}" 的拼接(prefix 自带下划线, 直接接时间戳)。
    """
    return f"{prefix}{now.strftime('%Y%m%d%H%M%S')}"


# ═══════════════════════════════════════════════════════════
# 对照基线: 旧实现同秒必碰撞
# ═══════════════════════════════════════════════════════════

class TestLegacyCollisionBaseline:
    """证明旧实现(秒级时间戳)冻结时钟后 100 次生成结果完全相同。

    这是 RED→GREEN 的对照证据: 旧逻辑天然无法区分同秒计划,
    100 次生成退化为 1 个唯一 id。
    """

    def test_legacy_same_second_all_collide(self):
        now = _FrozenDateTime.fixed
        ids = [_legacy_plan_id("eco_", now) for _ in range(100)]
        assert len(set(ids)) == 1  # 100 次全相同 → 旧实现必碰撞
        assert ids[0] == "eco_20260806070500"


# ═══════════════════════════════════════════════════════════
# 新生成器: 同秒唯一
# ═══════════════════════════════════════════════════════════

class TestMakePlanIdUnique:
    """_make_plan_id 冻结时钟后仍 100 个全唯一 (uuid 后缀消除碰撞)。"""

    def test_unique_100_within_same_second(self, monkeypatch):
        monkeypatch.setattr(optimizer_module, "datetime", _FrozenDateTime)
        ids = [_make_plan_id("eco_") for _ in range(100)]
        assert len(ids) == 100
        assert len(set(ids)) == 100  # 冻结时钟下全唯一 → uuid 后缀生效


# ═══════════════════════════════════════════════════════════
# 前缀与格式
# ═══════════════════════════════════════════════════════════

class TestMakePlanIdPrefix:
    """各调度入口前缀正确, 整体格式 = {prefix}_{14位时间戳}_{6位hex}。"""

    @pytest.mark.parametrize("prefix", ["safe_", "eco_", "ps_", "dr_", "coord_"])
    def test_prefix_correct(self, prefix):
        assert _make_plan_id(prefix).startswith(prefix)

    @pytest.mark.parametrize("prefix", ["safe_", "eco_", "ps_", "dr_", "coord_"])
    def test_format_timestamp_and_hex_suffix(self, prefix, monkeypatch):
        """冻结时钟: 去掉前缀后 = '20260806070500_<6位hex>'。"""
        monkeypatch.setattr(optimizer_module, "datetime", _FrozenDateTime)
        pid = _make_plan_id(prefix)
        body = pid[len(prefix):]                       # '20260806070500_ab12cd'
        ts, sep, hex_suffix = body.partition("_")
        assert sep == "_"
        assert ts == "20260806070500"                  # 14位秒级时间戳, 冻结后恒定
        assert len(hex_suffix) == 6                    # uuid4().hex[:6]
        assert all(c in "0123456789abcdef" for c in hex_suffix)


# ═══════════════════════════════════════════════════════════
# safe_ 异常降级双入口: coordinator 与 optimizer 同秒不碰撞
# ═══════════════════════════════════════════════════════════

class TestSafeEntryNoCollision:
    """coordinator._safe_plan (L50) 与 optimizer._safe_default_plan (L88) 同为
    safe_ 前缀的异常降级双入口: 冻结时钟后两者 plan_id 仍不同。

    旧实现下两者时间戳完全相同 → plan_id 相等 (本断言 RED)。
    """

    def test_safe_entries_distinct_same_second(self, monkeypatch):
        monkeypatch.setattr(optimizer_module, "datetime", _FrozenDateTime)
        opt_plan = VPPOptimizer()._safe_default_plan(DispatchMode.ECONOMIC, "经济调度")
        coord_plan = MultiStationCoordinator()._safe_plan(DispatchMode.ECONOMIC, "经济调度")
        assert opt_plan.plan_id.startswith("safe_")
        assert coord_plan.plan_id.startswith("safe_")
        assert opt_plan.plan_id != coord_plan.plan_id  # 旧实现相等 → RED, uuid 后缀使其不同
