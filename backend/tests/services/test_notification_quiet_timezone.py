"""通知静默时段时区修复 单元测试 (卡 ac0a7aa7)

被测: app/services/notification_sender.py
  - 模块级 _get_notification_tz(config): 三级优先解析目标时区
  - NotificationSender._is_quiet_time(config, *, now=None): aware now 自动转目标时区

根因 (与电价卡 9912ba63 同根):
  旧 _is_quiet_time 用 datetime.now() 取 naive 本地时间读 .hour。NotificationConfig.quiet_start/
  quiet_end (如 22:00-08:00) 按用户本地时间定义。容器默认 UTC 部署时窗口整体错位 8h:
  上海 22:00 静默被当 UTC 22:00 = 上海 06:00, 静默窗口平移到错误的绝对时段。

修复:
  - NotificationConfig.timezone (模型早有 default='Asia/Shanghai', 但旧实现从未读, 是死字段)
    现作为 per-config 时区, 缺省回退 settings.NOTIFICATION_TIMEZONE (默认上海), 再兜底硬编码。
  - now= aware 时 astimezone(tz) 后取本地时分; naive 时按表面时分 (兼容简单确定性测试);
    None 时 datetime.now(tz) 取目标时区当前时刻。

五类用例:
  1. UTC 容器跨时区判定      — per-config timezone 直接改变静默判定
  2. 8h 错位回归证据          — 注入 UTC 绝对时刻, 验证转到目标时区后判定正确
  3. _get_notification_tz     — 三级优先 + 坏值兜底
  4. 边界 inclusive            — start/end 端点含等号
  5. naive now 兼容            — 注入 naive 仍按表面时分, 不抛
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.services.notification_sender import NotificationSender, _get_notification_tz


# ─── 工厂 ───

def make_config(*, quiet_start=None, quiet_end=None, tz=None):
    """内存 config: tz=None 表示不设 timezone 属性 (走兜底)。"""
    kw = dict(
        id=1, quiet_start=quiet_start, quiet_end=quiet_end,
    )
    if tz is not None:
        kw["timezone"] = tz
    return SimpleNamespace(**kw)


@pytest.fixture
def sender():
    # _is_quiet_time / _get_notification_tz 不触达 dispatcher, 无需 mock
    return NotificationSender()


SH = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc


# ═══════════════════════════════════════════════════════════
# 1. UTC 容器跨时区判定: per-config timezone 改变静默判定
# ═══════════════════════════════════════════════════════════

class TestTimezoneAwareness:
    def test_shanghai_window_uses_shanghai_local_hour(self, sender):
        # 上海 22:00-08:00; 注入上海 22:30 (aware) → 静默
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 22, 30, tzinfo=SH)
        assert sender._is_quiet_time(cfg, now=now) is True

    def test_shanghai_window_outside(self, sender):
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 14, 0, tzinfo=SH)  # 上海 14:00 窗口外
        assert sender._is_quiet_time(cfg, now=now) is False

    def test_utc_window_uses_utc_local_hour(self, sender):
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="UTC")
        now = datetime(2026, 1, 1, 23, 0, tzinfo=UTC)  # UTC 23:00 在窗口
        assert sender._is_quiet_time(cfg, now=now) is True

    def test_utc_window_outside(self, sender):
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="UTC")
        now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)  # UTC 10:00 窗口外
        assert sender._is_quiet_time(cfg, now=now) is False

    def test_same_utc_moment_different_tz_different_verdict(self, sender):
        """同一 UTC 绝对时刻, 仅 per-config timezone 不同 → 判定不同 (核心证据)。

        UTC 14:30 = 上海 22:30。窗口 22:00-23:00:
          - tz=Asia/Shanghai → 22:30 在窗口 → 静默
          - tz=UTC           → 14:30 不在窗口 → 不静默
        """
        now = datetime(2026, 1, 1, 14, 30, tzinfo=UTC)
        cfg_sh = make_config(quiet_start="22:00", quiet_end="23:00", tz="Asia/Shanghai")
        cfg_utc = make_config(quiet_start="22:00", quiet_end="23:00", tz="UTC")
        assert sender._is_quiet_time(cfg_sh, now=now) is True
        assert sender._is_quiet_time(cfg_utc, now=now) is False


# ═══════════════════════════════════════════════════════════
# 2. 8h 错位回归证据: 注入 UTC 时刻, 验证转到上海后判定正确
# ═══════════════════════════════════════════════════════════

class TestUtcContainerOffsetRegression:
    def test_shanghai_quiet_at_utc_equivalent(self, sender):
        """上海 22:00 静默: UTC 14:00 (=上海 22:00) 应静默。

        旧 bug: datetime.now() 在 UTC 容器返回 naive 14:00, .hour=14, 不在 22-08 窗口 → 不静默 (错)。
        修复: astimezone(Shanghai) → 22:00 → 静默 (对)。
        """
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 14, 0, tzinfo=UTC)  # = 上海 22:00
        assert sender._is_quiet_time(cfg, now=now) is True

    def test_shanghai_nonquiet_at_utc_equivalent(self, sender):
        """上海 10:00 窗口外: UTC 02:00 (=上海 10:00) 应不静默。

        窗口 22:00-08:00; 上海 10:00 在 08:00-22:00 外段 → 不静默。
        旧 bug: naive .hour=2 (UTC 02:00) → 2 <= 480(end) → 误判在 22-08 窗口 → 误静默 (错)。
        """
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)  # = 上海 10:00
        assert sender._is_quiet_time(cfg, now=now) is False

    def test_tokyo_offset(self, sender):
        # 东京 +9: UTC 00:00 = 东京 09:00; 窗口 09:00-10:00 → 静默
        cfg = make_config(quiet_start="09:00", quiet_end="10:00", tz="Asia/Tokyo")
        now = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        assert sender._is_quiet_time(cfg, now=now) is True

    def test_negative_offset_los_angeles(self, sender):
        # 洛杉矶 -8: UTC 06:00 = LA 前一天 22:00; 跨天窗口 22:00-08:00 → 静默
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="America/Los_Angeles")
        now = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)  # = LA 2025-12-31 22:00
        assert sender._is_quiet_time(cfg, now=now) is True


# ═══════════════════════════════════════════════════════════
# 3. _get_notification_tz: 三级优先 + 坏值兜底
# ═══════════════════════════════════════════════════════════

class TestGetNotificationTz:
    def test_uses_per_config_timezone(self):
        cfg = make_config(tz="Asia/Tokyo")
        assert _get_notification_tz(cfg) == ZoneInfo("Asia/Tokyo")

    def test_falls_back_to_settings_when_config_tz_none(self):
        # config.timezone=None → 回退 settings.NOTIFICATION_TIMEZONE (默认上海)
        cfg = make_config(tz=None)
        cfg.timezone = None
        assert _get_notification_tz(cfg) == ZoneInfo("Asia/Shanghai")

    def test_falls_back_when_no_timezone_attr(self):
        # config 无 timezone 属性 (getattr 默认) → 上海
        cfg = SimpleNamespace(id=1)
        assert _get_notification_tz(cfg) == ZoneInfo("Asia/Shanghai")

    def test_bad_iana_name_falls_back(self):
        # 合法 str 但非法 IANA 名 → ZoneInfo 抛错 → 兜底上海
        cfg = make_config(tz="Foo/Bar")
        assert _get_notification_tz(cfg) == ZoneInfo("Asia/Shanghai")

    def test_non_string_tz_falls_back(self):
        # config.timezone 非 str (如脏数据 int) → 走 settings 兜底上海
        cfg = SimpleNamespace(id=1, timezone=12345)
        assert _get_notification_tz(cfg) == ZoneInfo("Asia/Shanghai")

    def test_empty_string_tz_falls_back(self):
        cfg = make_config(tz="")
        assert _get_notification_tz(cfg) == ZoneInfo("Asia/Shanghai")

    def test_settings_override_used_when_config_tz_missing(self, monkeypatch):
        # config.timezone=None + settings.NOTIFICATION_TIMEZONE=UTC → 用 UTC
        monkeypatch.setattr(
            "app.core.config.settings.NOTIFICATION_TIMEZONE", "UTC"
        )
        cfg = SimpleNamespace(id=1, timezone=None)
        assert _get_notification_tz(cfg) == ZoneInfo("UTC")

    def test_utc_iana_resolves(self):
        cfg = make_config(tz="UTC")
        assert _get_notification_tz(cfg).utcoffset(datetime(2026, 1, 1)) == timezone.utc.utcoffset(None)


# ═══════════════════════════════════════════════════════════
# 4. 边界 inclusive (start/end 端点含等号)
# ═══════════════════════════════════════════════════════════

class TestBoundaryInclusive:
    def test_exactly_start_is_quiet(self, sender):
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 22, 0, tzinfo=SH)
        assert sender._is_quiet_time(cfg, now=now) is True

    def test_exactly_end_is_quiet(self, sender):
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 8, 0, tzinfo=SH)
        assert sender._is_quiet_time(cfg, now=now) is True

    def test_one_min_before_start_not_quiet(self, sender):
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 21, 59, tzinfo=SH)
        assert sender._is_quiet_time(cfg, now=now) is False

    def test_one_min_after_end_not_quiet(self, sender):
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 8, 1, tzinfo=SH)
        assert sender._is_quiet_time(cfg, now=now) is False

    def test_same_day_window_boundary_start(self, sender):
        cfg = make_config(quiet_start="10:00", quiet_end="12:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 10, 0, tzinfo=SH)
        assert sender._is_quiet_time(cfg, now=now) is True


# ═══════════════════════════════════════════════════════════
# 5. naive now 兼容 (按表面时分, 不抛)
# ═══════════════════════════════════════════════════════════

class TestNaiveNowCompat:
    def test_naive_now_uses_surface_hour_in_window(self, sender):
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 23, 30)  # naive, 表面 23:30
        assert sender._is_quiet_time(cfg, now=now) is True

    def test_naive_now_uses_surface_hour_outside(self, sender):
        cfg = make_config(quiet_start="22:00", quiet_end="08:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 12, 0)  # naive, 表面 12:00
        assert sender._is_quiet_time(cfg, now=now) is False

    def test_naive_now_same_day_window(self, sender):
        cfg = make_config(quiet_start="10:00", quiet_end="12:00", tz="Asia/Shanghai")
        now = datetime(2026, 1, 1, 11, 0)  # naive
        assert sender._is_quiet_time(cfg, now=now) is True


# ─── 辅助: 无窗口/坏格式仍短路 (回归保护) ───

class TestNoWindowAndBadFormat:
    def test_no_window_returns_false(self, sender):
        cfg = make_config(tz="Asia/Shanghai")
        assert sender._is_quiet_time(cfg, now=datetime(2026, 1, 1, 3, 0, tzinfo=SH)) is False

    def test_half_window_returns_false(self, sender):
        cfg = make_config(quiet_start="22:00", tz="Asia/Shanghai")
        assert sender._is_quiet_time(cfg, now=datetime(2026, 1, 1, 22, 30, tzinfo=SH)) is False

    def test_bad_format_returns_false(self, sender):
        cfg = make_config(quiet_start="bad", quiet_end="12:00", tz="Asia/Shanghai")
        assert sender._is_quiet_time(cfg, now=datetime(2026, 1, 1, 11, 0, tzinfo=SH)) is False
