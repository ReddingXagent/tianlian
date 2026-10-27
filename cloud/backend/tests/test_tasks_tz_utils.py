"""
业务时区共享 helper 单元测试 (卡 c42ac99a, 时区缺陷族第4弹)

确定性证明日批"业务日"在容器 UTC 部署 + 业务时区上海双场景下取值正确:
  - 上海凌晨 beat 触发时刻 (= UTC 前日 17:00~19:00) 仍取"上海昨天/上月"
  - 旧 date.today() 公式在该时刻产出错误业务日 (回归对照证据)
  - monthly 月初边界: 上海1号03:00 (= UTC 上月末19:00) 汇总上月而非上上月
  - parse_dt_in_biz_tz: naive 串按业务时区解释成 aware (修复 naive vs aware TypeError)
  - get_biz_tz 坏值逐级回退上海永不抛
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.tasks import tz_utils
from app.tasks.tz_utils import (
    get_biz_tz,
    now_in_biz_tz,
    parse_dt_in_biz_tz,
    today_in_biz_tz,
    yesterday_in_biz_tz,
)

UTC = timezone.utc
SH = ZoneInfo("Asia/Shanghai")
SHANGHAI = "Asia/Shanghai"


# ═══════════════════════════════════════════════════════════════════
# 日批"补前一天"边界 (卡 c42ac99a 核心)
# ═══════════════════════════════════════════════════════════════════

class TestDailyYesterdayBoundary:
    """settlement/carbon/analytics 日批凌晨触发: 上海昨天语义。"""

    def test_yesterday_at_shanghai_0100_utc_container(self):
        """上海 01:00 (= UTC 前日 17:00) beat 触发 → 业务昨日 = 上海昨天。

        场景: 2026-08-07 01:00 上海 = 2026-08-06 17:00 UTC。
        旧 date.today() 在 UTC 容器取到 2026-08-06, -1d = 2026-08-05 (上海前天, 错)。
        helper 取业务时区昨日 = 2026-08-06 (上海昨天, 对)。
        """
        fire_moment = datetime(2026, 8, 6, 17, 0, tzinfo=UTC)  # 上海 08-07 01:00
        assert yesterday_in_biz_tz(fire_moment) == date(2026, 8, 6)

        # 回归对照: 旧公式在此时刻产出错误业务日
        old_naive_yesterday = fire_moment.astimezone(UTC).date() - timedelta(days=1)
        assert old_naive_yesterday == date(2026, 8, 5)  # 旧实现错算"上海前天"

    def test_today_at_shanghai_0100_utc_container(self):
        """同一时刻业务时区"今天" = 上海今天 (跨午夜边界)。"""
        fire_moment = datetime(2026, 8, 6, 17, 0, tzinfo=UTC)
        assert today_in_biz_tz(fire_moment) == date(2026, 8, 7)

    def test_yesterday_midday_utc_unaffected(self):
        """UTC 中午 (上海晚上) 无跨日歧义, helper 与朴素计算一致。"""
        noon_utc = datetime(2026, 8, 7, 6, 0, tzinfo=UTC)  # 上海 08-07 14:00
        assert yesterday_in_biz_tz(noon_utc) == date(2026, 8, 6)

    def test_settlement_beat_window_all_hours_pick_shanghai_yesterday(self):
        """settlement/revenue beat 窗口 (上海 00:00~02:40) 全段都取上海昨天。

        构造上海墙钟 beat 时刻再转 UTC (模拟容器 UTC now), 业务昨日恒为 08-06。
        """
        for sh_hour, sh_minute in [(0, 0), (1, 0), (2, 30), (2, 40)]:
            sh_dt = datetime(2026, 8, 7, sh_hour, sh_minute, tzinfo=SH)  # 上海 beat 时刻
            utc_dt = sh_dt.astimezone(UTC)  # 容器看到的 UTC now
            assert yesterday_in_biz_tz(utc_dt) == date(2026, 8, 6), (
                f"上海 {sh_hour:02d}:{sh_minute:02d} beat 业务昨日应恒为 08-06")


# ═══════════════════════════════════════════════════════════════════
# monthly 月初边界 (carbon_monthly_summary)
# ═══════════════════════════════════════════════════════════════════

def _resolve_target_month(today):
    """复刻 carbon_monthly_summary 的 year/month 默认解析逻辑。"""
    last_month = today.replace(day=1) - timedelta(days=1)
    return last_month.year, last_month.month


class TestMonthlyBoundary:
    """carbon_monthly_summary 月初 beat: 汇总上月而非上上月。"""

    def test_month_first_at_shanghai_0300_utc_container(self):
        """上海每月1号 03:00 (= UTC 上月末 19:00) → 汇总上月。

        场景: 2026-08-01 03:00 上海 = 2026-07-31 19:00 UTC。
        旧 date.today() 在 UTC 容器取到 2026-07-31 → replace(day=1)-1d = 06-30
        → 汇总 6 月 (上上月, 每月固定错)。
        helper 业务时区 today = 08-01 → 汇总 7 月 (上月, 对)。
        """
        fire_moment = datetime(2026, 7, 31, 19, 0, tzinfo=UTC)  # 上海 08-01 03:00

        new_today = today_in_biz_tz(fire_moment)
        assert new_today == date(2026, 8, 1)
        assert _resolve_target_month(new_today) == (2026, 7)

        # 回归对照: 旧公式在此时刻汇总上上月
        old_today = fire_moment.astimezone(UTC).date()  # date.today() 在 UTC 容器
        assert _resolve_target_month(old_today) == (2026, 6)  # 旧实现每月固定错

    def test_month_first_at_shanghai_noon_safe(self):
        """上海 1 号白天 (无 UTC 跨月歧义) 也汇总上月。"""
        fire_moment = datetime(2026, 8, 1, 4, 0, tzinfo=UTC)  # 上海 08-01 12:00
        new_today = today_in_biz_tz(fire_moment)
        assert _resolve_target_month(new_today) == (2026, 7)

    def test_year_rollover_january(self):
        """1月初 beat 汇总上年12月 (年份回滚)。"""
        # 上海 2026-01-01 03:00 = UTC 2025-12-31 19:00
        fire_moment = datetime(2025, 12, 31, 19, 0, tzinfo=UTC)
        new_today = today_in_biz_tz(fire_moment)
        assert _resolve_target_month(new_today) == (2025, 12)


# ═══════════════════════════════════════════════════════════════════
# parse_dt_in_biz_tz (analyze_efficiency_task naive vs aware TypeError 修复)
# ═══════════════════════════════════════════════════════════════════

class TestParseDtInBizTz:
    """naive isoformat 串按业务时区解释成 aware, 与默认分支 aware 比较不再 TypeError。"""

    def test_naive_interpreted_as_biz_tz(self):
        dt = parse_dt_in_biz_tz("2026-07-15T10:00:00")
        assert dt.tzinfo is not None
        # 上海墙钟 10:00 → UTC 02:00
        assert dt.astimezone(UTC) == datetime(2026, 7, 15, 2, 0, tzinfo=UTC)

    def test_aware_input_preserved(self):
        dt = parse_dt_in_biz_tz("2026-07-15T10:00:00+05:00")
        assert dt.utcoffset() == timedelta(hours=5)
        assert dt.astimezone(UTC) == datetime(2026, 7, 15, 5, 0, tzinfo=UTC)

    def test_naive_start_comparable_with_utc_now(self):
        """复刻 analyze_efficiency_task 比较场景: naive start 与 aware end 不再崩。"""
        start = parse_dt_in_biz_tz("2026-07-15T10:00:00")
        end = datetime.now(UTC)  # 默认分支
        # 旧实现 start=naive vs end=aware 此处抛 TypeError
        assert start <= end  # 不抛即通过


# ═══════════════════════════════════════════════════════════════════
# get_biz_tz 坏值兜底
# ═══════════════════════════════════════════════════════════════════

class TestGetBizTzFallback:
    """BUSINESS_TIMEZONE 坏值逐级回退上海, 永不抛。"""

    def test_default_is_shanghai(self):
        from zoneinfo import ZoneInfo
        assert get_biz_tz() == ZoneInfo(SHANGHAI)

    def test_valid_override(self, monkeypatch):
        monkeypatch.setattr(tz_utils, "_global_business_timezone_name", lambda: "America/New_York")
        assert get_biz_tz() == ZoneInfo("America/New_York")

    def test_invalid_iana_falls_back(self, monkeypatch):
        """非法 IANA 名 (含斜杠路径式坏值) → 回退上海。"""
        monkeypatch.setattr(tz_utils, "_global_business_timezone_name", lambda: "Not/A/Zone")
        assert str(get_biz_tz()) == SHANGHAI

    def test_none_or_empty_falls_back(self, monkeypatch):
        for bad in (None, "", "   "):
            monkeypatch.setattr(tz_utils, "_global_business_timezone_name", lambda b=bad: b)
            assert str(get_biz_tz()) == SHANGHAI

    def test_now_injection_naive_uses_biz_tz(self):
        """naive now 注入按业务时区表面解释 (仅测试路径, 不抛 aware/naive 错误)。"""
        naive = datetime(2026, 8, 6, 17, 0)  # 无 tzinfo
        result = now_in_biz_tz(naive)
        assert result.tzinfo is not None
        assert result.date() == date(2026, 8, 6)
