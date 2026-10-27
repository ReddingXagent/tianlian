"""
电价时段时区与整点边界测试 (卡 9912ba63)

被测:
- app.services.vpp.dispatch_optimizer.optimizer._pricing_hour
- VPPOptimizer.get_current_price(now=...) 端到端

修复的两个缺陷:
1. 双 now() 整点毛刺 — 旧 `datetime.now().hour + datetime.now().minute/60.0` 两次独立
   now() 之间可能跨整点 (10:59:59.999 → 11:00:00.001), 使 hour 与 minute 来自不同
   分钟, 峰谷切换边界产出错误 hour (10.0 而非 10.983)。修复: 单次 now(tz) 取值。
2. naive 时间电价窗口错位 — 旧 datetime.now() 返回 naive 本地时间, 容器默认 UTC
   部署时 "尖峰10-12点" 被当成 UTC10-12 点 (实为上海18-20点), 整体错位 8h。
   修复: 显式电价时区 settings.PRICING_TIMEZONE (默认 Asia/Shanghai)。

纯逻辑测试: 注入 aware 时刻 (不依赖运行时钟), 跨时区场景确定性可复现。
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.vpp.dispatch_optimizer.optimizer import _pricing_hour
from app.services.vpp.dispatch_optimizer import VPPOptimizer

CST = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc


# ═══════════════════════════════════════════════════════════
# 峰谷切换边界 hour 浮点计算 (单次取值, 无双 now 毛刺)
# ═══════════════════════════════════════════════════════════

class TestPricingHourBoundary:
    """各时段切换边界的 _pricing_hour 浮点值, 验证单次取值不产生整点毛刺。"""

    def test_peak_window_start(self):
        """上海 10:00:00 整点 = 尖峰起点, hour=10.0 (非 9.983 毛刺)。"""
        assert _pricing_hour(datetime(2026, 8, 6, 10, 0, 0, tzinfo=CST)) == 10.0

    def test_just_before_peak_start_no_glitch(self):
        """上海 09:59:59.999999 仍属高峰段, hour≈9.9833 — 旧双 now 毛刺会得 10.0。"""
        h = _pricing_hour(datetime(2026, 8, 6, 9, 59, 59, 999999, tzinfo=CST))
        assert h == pytest.approx(9 + 59 / 60, abs=1e-6)
        assert h < 10.0

    def test_peak_window_end(self):
        """上海 12:00:00 = 尖峰结束进入平段, hour=12.0。"""
        assert _pricing_hour(datetime(2026, 8, 6, 12, 0, 0, tzinfo=CST)) == 12.0

    def test_valley_wraparound(self):
        """上海 03:00 落在跨午夜低谷段 (23-06), hour=3.0。"""
        assert _pricing_hour(datetime(2026, 8, 6, 3, 0, 0, tzinfo=CST)) == 3.0

    def test_high_window_start_evening(self):
        """上海 18:00:00 = 晚高峰起点, hour=18.0。"""
        assert _pricing_hour(datetime(2026, 8, 6, 18, 0, 0, tzinfo=CST)) == 18.0

    def test_just_before_high_evening_no_glitch(self):
        """上海 17:59:59.999999 仍属平段, hour≈17.9833 — 旧双 now 毛刺会得 18.0。"""
        h = _pricing_hour(datetime(2026, 8, 6, 17, 59, 59, 999999, tzinfo=CST))
        assert h == pytest.approx(17 + 59 / 60, abs=1e-6)
        assert h < 18.0


# ═══════════════════════════════════════════════════════════
# 单次 now(tz) 取值 — 整点边界 hour/minute 同源
# ═══════════════════════════════════════════════════════════

class TestSingleNowNoGlitch:
    """验证 _pricing_hour() 真实路径只调用一次 datetime.now(tz), 消除双 now 毛刺根因。"""

    def test_now_invoked_exactly_once(self, monkeypatch):
        """整点前夜 10:59:59.999999, 单次 now 取值 → hour≈9.983, 且 now 仅被调用 1 次。"""
        import app.services.vpp.dispatch_optimizer.optimizer as opt_mod

        calls: list = []
        fixed = datetime(2026, 8, 6, 9, 59, 59, 999999, tzinfo=CST)

        class _FakeDateTime:
            """替身: 仅实现 _pricing_hour 用到的 datetime.now(tz) 并计数。
            C 类型 datetime.now 不可 setattr, 故整体替换模块级 datetime 引用。"""

            @classmethod
            def now(cls, tz=None):
                calls.append(tz)
                return fixed if tz is None else fixed.astimezone(tz)

        monkeypatch.setattr(opt_mod, "datetime", _FakeDateTime)
        h = _pricing_hour()
        assert len(calls) == 1, "必须单次 now 取值, 旧双 now 是整点毛刺根因"
        assert calls[0] is not None, "必须传入显式电价时区 (非 naive now)"
        assert h == pytest.approx(9 + 59 / 60, abs=1e-6)


# ═══════════════════════════════════════════════════════════
# 跨时区部署 — 进程 TZ=UTC 仍按 Asia/Shanghai 电价窗口判定
# ═══════════════════════════════════════════════════════════

class TestCrossTimezoneDeployment:
    """容器默认 UTC 部署: 电价窗口必须锁定上海时区, 不随进程 TZ 漂移。"""

    def test_utc_2am_maps_to_cst_peak(self):
        """物理时刻 UTC 02:00 = 上海 10:00 尖峰; 旧 naive 在 UTC 容器会判 hour=2→低谷。"""
        utc_2am = datetime(2026, 8, 6, 2, 0, 0, tzinfo=UTC)
        assert _pricing_hour(utc_2am) == 10.0

    def test_utc_15_maps_to_cst_valley(self):
        """物理时刻 UTC 15:00 = 上海 23:00 低谷; 旧 naive 在 UTC 容器会判 hour=15→平段。"""
        utc_15 = datetime(2026, 8, 6, 15, 0, 0, tzinfo=UTC)
        assert _pricing_hour(utc_15) == 23.0

    def test_process_tz_utc_still_selects_cst_window(self):
        """进程 TZ=UTC 环境下, aware 上海时刻注入仍选中上海电价窗口 (尖峰)。"""
        prev_tz = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        try:
            time.tzset()  # Unix/macOS; Windows 无此调用, 显式 tz 注入路径不依赖进程 TZ
        except AttributeError:
            pass
        try:
            cst_peak = datetime(2026, 8, 6, 10, 30, tzinfo=CST)
            assert _pricing_hour(cst_peak) == 10.5
            assert VPPOptimizer().get_current_price(now=cst_peak) == pytest.approx(
                VPPOptimizer.PEAK_PRICE
            )
        finally:
            if prev_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = prev_tz
            try:
                time.tzset()
            except AttributeError:
                pass


# ═══════════════════════════════════════════════════════════
# get_current_price 端到端 (now 参数注入)
# ═══════════════════════════════════════════════════════════

class TestGetCurrentPriceWithNow:
    """get_current_price(now=...) 跨时区端到端: aware 时刻 → 上海窗口 → 正确电价。"""

    def test_utc_peak_time_yields_peak_price(self):
        """UTC 02:00 (上海10:00) → get_current_price 返回尖峰价, 不受 hour 位置参数干扰。"""
        opt = VPPOptimizer()
        utc_2am = datetime(2026, 8, 6, 2, 0, 0, tzinfo=UTC)
        assert opt.get_current_price(now=utc_2am) == pytest.approx(opt.PEAK_PRICE)

    def test_utc_valley_time_yields_valley_price(self):
        """UTC 15:00 (上海23:00) → get_current_price 返回低谷价。"""
        opt = VPPOptimizer()
        utc_15 = datetime(2026, 8, 6, 15, 0, 0, tzinfo=UTC)
        assert opt.get_current_price(now=utc_15) == pytest.approx(opt.VALLEY_PRICE)

    def test_explicit_hour_param_takes_precedence(self):
        """显式 hour 位置参数优先, now 仅在 hour 缺省时使用 (向后兼容)。"""
        opt = VPPOptimizer()
        utc_2am = datetime(2026, 8, 6, 2, 0, 0, tzinfo=UTC)
        # 传 hour=3.0 (低谷) 应胜过 now 注入的上海尖峰判定
        assert opt.get_current_price(3.0, now=utc_2am) == pytest.approx(opt.VALLEY_PRICE)


# ═══════════════════════════════════════════════════════════
# naive 旧公式回归证据 — 锁定缺陷行为, 防回退
# ═══════════════════════════════════════════════════════════

class TestNaiveRegressionEvidence:
    """证明旧 naive 公式在 UTC 容器会错判, 新实现修正之。"""

    def test_old_naive_formula_misjudges_under_utc(self):
        """回归对比: 旧 naive 公式把上海尖峰物理时刻判成低谷, 新 aware 实现判对尖峰。"""
        opt = VPPOptimizer()
        # 模拟旧实现: TZ=UTC 容器的 naive datetime.now() 在该物理时刻得 02:00 naive
        naive_utc_2am = datetime(2026, 8, 6, 2, 0, 0)  # naive, 无 tzinfo
        old_hour = naive_utc_2am.hour + naive_utc_2am.minute / 60.0
        assert old_hour == 2.0
        # 旧公式 hour=2.0 → 低谷 (错误: 物理时刻实为上海 10:00 尖峰)
        assert opt.get_current_price(old_hour) == pytest.approx(opt.VALLEY_PRICE)
        # 新实现: 同一物理时刻 aware UTC → 上海窗口 → 尖峰
        assert opt.get_current_price(
            now=datetime(2026, 8, 6, 2, 0, 0, tzinfo=UTC)
        ) == pytest.approx(opt.PEAK_PRICE)
