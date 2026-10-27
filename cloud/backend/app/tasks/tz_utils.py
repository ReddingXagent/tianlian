"""
业务时区共享工具 (卡 c42ac99a, 时区缺陷族第4弹)

背景:
  celery_app.conf timezone="Asia/Shanghai" + enable_utc=True → beat 按上海墙钟
  触发日批任务 (settlement 01:00 / carbon 02:00 / revenue 02:30 / station 02:40 /
  carbon-monthly 每月1号 03:00), 但任务体曾用 ``date.today()`` 取容器本地日期。
  云端 UTC 部署时业务日整体错位 8h: 上海 01:00 = UTC 前日 17:00, ``date.today()``
  取到 UTC 前日 → 结算/聚合"上海前天"而非"上海昨天"; 月初 03:00 (UTC 上月末 19:00)
  则把上月汇总成上上月。

集中提供业务时区日期/时刻 helper, 替换各任务内的 ``date.today()``, 避免第4份复制
(前3份 per-config ``_get_X_tz`` 分散在电价/通知/排班模块, 各读不同 settings)。
坏值 (None/空串/非 str/非法 IANA 名) 逐级回退上海, 永不抛 —— 日批调度是 best-effort,
时区解析失败不应让结算任务整体崩溃。
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# 最后防线时区, 模块加载时构造一次 (settings 不可用 / 非法 IANA 名时兜底)。
_FALLBACK_BIZ_TZ = ZoneInfo("Asia/Shanghai")


def _global_business_timezone_name() -> str:
    """读 ``settings.BUSINESS_TIMEZONE``, 取不到回退上海。

    settings 懒导入 (函数内) 规避模块加载时序耦合 —— 日批任务每天才触发一次,
    每次 import 开销可忽略 (sys.modules 缓存命中)。
    """
    try:
        from app.core.config import settings
        name = getattr(settings, "BUSINESS_TIMEZONE", None)
        if isinstance(name, str) and name.strip():
            return name
    except Exception:
        pass
    return "Asia/Shanghai"


def get_biz_tz() -> ZoneInfo:
    """解析业务时区。坏值回退上海, 永不抛。"""
    try:
        return ZoneInfo(_global_business_timezone_name())
    except Exception:
        return _FALLBACK_BIZ_TZ


def now_in_biz_tz(now: Optional[datetime] = None) -> datetime:
    """业务时区当前 aware datetime。

    Args:
        now: 测试注入的固定时刻 (任意 tz 的 aware datetime); None 取真实当前时刻,
            经 ``astimezone`` 转为业务时区。返回值必为 aware。
    """
    if now is None:
        return datetime.now(get_biz_tz())
    # 注入的 aware 时刻归一到业务时区 (保证 .date() 取业务日, 与生产路径同语义);
    # naive 注入按业务时区表面解释 (仅用于测试, 避免抛 aware/naive 错误)。
    if now.tzinfo is None:
        return now.replace(tzinfo=get_biz_tz())
    return now.astimezone(get_biz_tz())


def today_in_biz_tz(now: Optional[datetime] = None) -> date:
    """业务时区当前日期 (日批"今天/上月"语义基准)。"""
    return now_in_biz_tz(now).date()


def yesterday_in_biz_tz(now: Optional[datetime] = None) -> date:
    """业务时区的昨日 (凌晨日批"补前一天数据"的语义基准)。"""
    return today_in_biz_tz(now) - timedelta(days=1)


def parse_dt_in_biz_tz(dt_str: str) -> datetime:
    """按业务时区解释 naive isoformat 串 → aware datetime; aware 输入原样尊重。

    用于 analyze_efficiency_task 的 start_date/end_date: 旧实现
    ``datetime.fromisoformat(...)`` 产 naive, 与默认分支 ``datetime.now(timezone.utc)``
    aware 比较时 ``start <= timestamp <= end`` 直接 TypeError 崩任务。
    """
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_biz_tz())
    return dt


def biz_day_bounds_utc_naive(target: date) -> tuple[datetime, datetime]:
    """业务时区"日"边界换算成 UTC-naive [day_start, day_end) 半开区间 (卡 f7422bbc)。

    落库口径统一 naive-UTC 后, 日批(结算/营收/站点指标/碳排/对账)不能再用裸
    ``datetime.combine(target, ...)`` 当窗口 —— 那是"UTC 日的 00:00-24:00", 会把
    上海 00:00-08:00 结束的订单/到账的退款错归前一日。此 helper 把业务日的
    [00:00, 24:00) 墙钟窗换算为对应 UTC-naive 区间, 与 ChargingOrder.end_time /
    RefundRecord.refunded_at 的统一落库口径对齐。
    """
    tz = get_biz_tz()
    start_aware = datetime.combine(target, datetime.min.time(), tzinfo=tz)
    end_aware = datetime.combine(target + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    return (
        start_aware.astimezone(timezone.utc).replace(tzinfo=None),
        end_aware.astimezone(timezone.utc).replace(tzinfo=None),
    )


def naive_utc_to_biz_wall(dt: datetime) -> datetime:
    """DB 读回的 naive-UTC 墙钟 → 业务时区 naive 墙钟 (卡 5a18d1ee, 时区缺陷族)。

    落库口径统一 naive-UTC 后 (charging_sessions/卡 f7422bbc, parking_event 列注释
    明示 UTC), service 层读回这些 naive 列做 TOU 峰谷/夜间窗判定或时间窗匹配时,
    不能用 ``to_aware_biz_tz`` 的"表面解释为业务时区"(``replace`` 不改墙钟数字) —
    那会把 UTC 墙钟当上海墙钟, 整体错位 8h。本 helper 先补 UTC tz 再 ``astimezone``
    真换算到业务时区, 最后 strip tz 得 naive 墙钟, 供 billing_engine 纯函数比较。

    aware 输入直接 ``astimezone`` 归一(语义一致); naive 输入按 UTC 解释。
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_biz_tz()).replace(tzinfo=None)


def to_aware_biz_tz(dt: datetime) -> datetime:
    """任意 datetime 归一到业务时区 aware datetime (卡 a311a5b0, 时区缺陷族第6弹)。

    - aware → ``astimezone`` 转业务时区(墙钟值随真实偏移改变, 语义不变)
    - naive → 按业务时区"表面解释"(``replace(tzinfo=...)``, 不改墙钟数字)

    用于充电交易 ingestion 入站时间归一与定价基准日计算: 上报载荷
    ``timestamp_start/stop`` 可能 aware/naive 混传, 直接 ``(stop-start)`` 会抛
    ``TypeError: can't subtract offset-naive and offset-aware datetimes`` → 500;
    先各自归一为 aware biz-tz, 时长差与 ``.date()`` 取业务日均安全且口径一致。
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=get_biz_tz())
    return dt.astimezone(get_biz_tz())
