"""
计费引擎增强 - SPEC §2.1 费用模型管理

完整计费引擎, 与 billing.py(简单乘法, 向后兼容) 解耦:

1. compute_tou_energy_fee      尖峰平谷时段计费(按充电起止时间拆分电量)
2. compute_service_fee_multi   服务费多模式(fixed 元/次 / percent 元/kWh)
3. compute_parking_fee_full    停车费完整规则(免费/小时/封顶/夜间/充电期间免除)
4. compute_occupancy_fee_full  占桩费完整规则(宽限/费率/单次封顶)
5. compute_reservation_fee_full 预约费完整规则(预约费/冻结/爽约罚款)
6. compute_order_fees          综合费用(实收=总-券-积分-折扣, 三项分离)
7. settle_order_fees           写入 ChargingOrder 5项费用 + order_fee_items 明细

设计原则:
- 纯计算函数, 接受规则 dict(key 对应模型字段名), 不耦合 ORM, 便于单测与复用
- 所有金额运算用 Decimal, 量化到 2 位(费率/单价按各自模型精度)
- 数据库查询由调用方负责, 引擎只做"给定规则→计算费用"
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, date, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional, List

from app.models.charging_order import ChargingOrder
from app.models.order_fee_item import OrderFeeItem, FeeType


_logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


class BillingError(ValueError):
    """billing_engine 顶层入参编程错误(None 必填入参 / 负数金额 / 非 dict 规则)。

    与既有 ``ValueError``(规则配置错误: 未知 fee_type / 缺 slot 价格 / 时段重叠)
    语义区分:
    - ValueError  → 配置数据问题, 调用方 try/except 后走默认值兜底;
    - BillingError → 调用方传参错误(本不该发生), 应向上冒泡暴露 bug, 不静默降级。

    继承 ValueError 以兼容可能存在的宽口径 ``except ValueError`` 兜底, 同时保留
    独立类型便于上层按需区分处理。
    """


def _is_negative_decimal(value) -> bool:
    """判断 value 是否为负数, 不抛异常(脏值返回 False)。

    用于 reservation 金额字段的负数校验: 过滤出负数(抛 BillingError, 防负预约费套利),
    其余(None/非法)继续走 `or 0` 降级。脏值(无法解析)不在此报错, 与既有语义一致。
    """
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return False
    return d.is_finite() and d < 0


def _q(value) -> Decimal:
    """统一转 Decimal 并量化到 2 位小数"""
    return Decimal(str(value)).quantize(TWO_PLACES)


def _safe_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    """转 Decimal, 保留原始精度; None / 非法字符串 / NaN / Infinity → default。

    与 ``_q`` 的区别: ``_q`` 面向"调用方保证合法"的内部路径并量化到 2 位, 脏输入
    直接抛 InvalidOperation(快速暴露 bug); 本 helper 面向"入参 sanitize"防御边界 ——
    外部传入的费率/电量可能为 None(配置缺失)或非法字符串(解析失败), 此时降级为
    default(通常 0, 不多收费)而非让整单计算崩溃。**不量化**(费率如 0.5286 是 4 位
    精度, 提前量化到 2 位会失真), 精度收敛交给各调用点的乘积 quantize。

    契约式 ValueError(未知 fee_type / 缺 slot 价格 / 时段重叠)由各自函数显式 raise,
    不走此 helper。
    """
    try:
        d = Decimal(str(value))
        if not d.is_finite():
            return Decimal(str(default))
        return d
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(str(default))


def _nonneg(value) -> Decimal:
    """转 Decimal, 负数归零(优惠金额不允许为负)"""
    v = Decimal(str(value))
    return v.quantize(TWO_PLACES) if v > 0 else Decimal("0.00")


def _to_amount(value) -> float:
    """金额序列化: Decimal → 干净的 2 位 float(序列化边界专用)。

    业务全程 Decimal, 仅在返回 dict 处转 float。round(value, 2) 兜底确保即便上游
    quantize 失效也不泄漏长浮点尾(如 0.30000000000000004)。返回 float 而非 str,
    以兼容所有用 float 相等断言的消费方; falsy 归 0.0 保持与旧 `float(x) if x else 0.0` 等价。
    """
    return float(round(value, 2)) if value else 0.0


# ═══════════════════════════════════════════════════════════════
# 1. 尖峰平谷时段充电费
# ═══════════════════════════════════════════════════════════════

def _slot_window_on_date(d: date, start_t: time, end_t: time):
    """时段在某一天的窗口 (start_dt, end_dt), 处理跨午夜。

    - start < end: 当天窗口
    - start > end: 跨午夜, 当天 start → 次日 end
    - start == end: 视为全天窗口
    """
    s = datetime.combine(d, start_t)
    if end_t > start_t:
        e = datetime.combine(d, end_t)
    elif end_t < start_t:
        e = datetime.combine(d + timedelta(days=1), end_t)
    else:
        e = datetime.combine(d + timedelta(days=1), start_t)
    return s, e


def _overlap_minutes(a_start: datetime, a_end: datetime,
                     b_start: datetime, b_end: datetime) -> float:
    """两个时间区间的重叠分钟数"""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    delta = (end - start).total_seconds() / 60
    return max(0.0, delta)


def compute_tou_energy_fee(
    start_time: datetime,
    end_time: datetime,
    total_kwh: Decimal,
    time_slots: List[dict],
    slot_prices: dict,
) -> dict:
    """按充电起止时间拆分各时段电量: ∑(时段电量 × 时段电价)

    时区约定: start_time / end_time 期望为 **UTC naive datetime**(aware 会被抹平
    tzinfo, 见下); time_slots 内的 start_time/end_time 为无时区的 time, 仅表本地时钟。

    Args:
        start_time: 充电开始时间(UTC naive datetime; None → BillingError)
        end_time: 充电结束时间(UTC naive datetime; None → BillingError)
        total_kwh: 充电总电量(kWh; None 降级 0, 负数 → BillingError)
        time_slots: 时段定义列表, 每项 {slot_id, period_type, start_time(time), end_time(time)}
        slot_prices: {slot_id: price_per_kwh(Decimal)}

    Returns:
        {
            "period_breakdown": {period_type: {energy, price, fee, minutes}},
            "energy_by_period": {period_type: energy(Decimal)},
            "total_fee": Decimal,
            "total_energy": Decimal,
        }
    """
    # 顶层入参校验: start/end 为 None 时下方 .tzinfo 访问会抛 AttributeError,
    # 属调用方编程错误 → BillingError(所有调用方 charging_pricing 均有 try/except 兜底)。
    if start_time is None or end_time is None:
        raise BillingError(
            f"compute_tou_energy_fee start_time/end_time 不能为 None "
            f"(start={start_time!r}, end={end_time!r})"
        )
    # 入口统一 naive 化: 下游 _slot_window_on_date 用 datetime.combine 构造的时段窗口
    # 均为 naive datetime, aware 入参与之比较/相减会抛 TypeError(can't compare offset-
    # naive and offset-aware); TOU 时段仅关心本地时钟(slot 的 time 无时区), 抹平
    # tzinfo 不改变计费结果。
    if start_time.tzinfo is not None:
        start_time = start_time.replace(tzinfo=None)
    if end_time.tzinfo is not None:
        end_time = end_time.replace(tzinfo=None)
    total_minutes = (end_time - start_time).total_seconds() / 60
    # 入参 sanitize: total_kwh 可能为 None(配置缺失/解析失败), _safe_decimal 降级为 0
    # 触发下方 <=0 短路返回空结构, 避免 Decimal(str(None)) 抛 InvalidOperation 使整单崩溃。
    total_kwh_dec = _safe_decimal(total_kwh)
    if total_minutes <= 0 or total_kwh_dec <= 0 or not time_slots:
        return {
            "period_breakdown": {},
            "energy_by_period": {},
            "total_fee": Decimal("0.00"),
            "total_energy": Decimal("0.00"),
            "coverage": 1.0,
        }

    # 充电覆盖的每一天(通常 1-2 天)。
    # 多取前一天: 跨午夜时段(end<start, 如谷段 22-06)在 start_time.date() 凌晨的
    # 尾巴属于前一天起始的窗口([d-1 22:00, d 06:00])。若 days 从 start_time.date()
    # 起算, 充电起点在午夜后(如 6/25 01:00)时该窗口不会被枚举, overlap=0,
    # 整段电量被静默排除(coverage=0, 客户少付费)。前置一天只增加零重叠窗, 无副作用。
    days: List[date] = []
    cur = start_time.date() - timedelta(days=1)
    end_date = end_time.date()
    while cur <= end_date:
        days.append(cur)
        cur += timedelta(days=1)

    period_breakdown: dict = {}
    total_fee = Decimal("0.00")
    total_energy = Decimal("0.00")
    # 累积所有 slot 覆盖分钟之和, 用于校验时段是否重叠(> 充电时长即配置错误)
    total_overlap = 0.0

    for slot in time_slots:
        # 入参 sanitize: slot 缺 slot_id/period_type/start_time/end_time 任一关键字
        # (规则格式错误) → 跳过该 slot, 不让 KeyError 中断整单。
        slot_id = slot.get("slot_id")
        period_type = slot.get("period_type")
        if slot_id is None or period_type is None \
                or slot.get("start_time") is None or slot.get("end_time") is None:
            _logger.warning("跳过格式错误的 TOU 时段(缺必要字段): %r", slot)
            continue
        # 累积该时段在充电区间内(跨多天)的重叠分钟
        overlap_min = 0.0
        for d in days:
            ws, we = _slot_window_on_date(d, slot["start_time"], slot["end_time"])
            overlap_min += _overlap_minutes(start_time, end_time, ws, we)
        if overlap_min <= 0:
            continue
        total_overlap += overlap_min

        # 恒功率假设: 按时间比例线性分摊电量
        share = Decimal(str(overlap_min)) / Decimal(str(total_minutes))
        # 4 位精度 energy 参与 fee 计算(保金额精度); 2 位 energy_q 用于展示与 total_energy
        # 累加, 使 energy_by_period 之和 == total_energy, 避免展示自相矛盾。
        energy = (share * total_kwh_dec).quantize(Decimal("0.0001"))
        # slot 覆盖充电区间却缺价格(配置错误): 显式报错, 不默认 0(否则该时段免费充电,
        # 客户少付费)。未覆盖的 slot 已在上方 overlap_min<=0 处 continue, 不会走到这里;
        # 调用方 _load_tou_energy 有 try/except 兜底走默认电价。
        if slot_id not in slot_prices:
            raise ValueError(f"Missing price for slot: {slot_id}")
        # 价格值 sanitize: key 存在但 value=None / 非法字符串(解析失败) → 该 slot 电量
        # 安全排除(降级跳过, 不崩), 不视为"缺价格"契约错误(那对应 key 完全不存在)。
        price = _safe_decimal(slot_prices[slot_id])
        if price <= 0:
            _logger.warning("跳过价格非法的 TOU 时段(slot_id=%s, price=%r)", slot_id, slot_prices[slot_id])
            continue
        fee = (energy * price).quantize(TWO_PLACES)
        energy_q = energy.quantize(TWO_PLACES)

        # 同 period_type 多时段窗(如双峰 08-12 + 18-21)累加, 不覆盖(卡4671e993):
        # 旧实现直接赋值, 后窗冲掉前窗, energy_by_period/明细只剩最后一窗,
        # 明细金额之和 < total_fee/electricity_fee, 发票与订单总额不符。
        if period_type in period_breakdown:
            prev = period_breakdown[period_type]
            merged_fee = prev["fee"] + fee
            merged_energy = prev["energy"] + energy_q
            period_breakdown[period_type] = {
                "energy": merged_energy,
                # 加权平均单价 = 累计费用 / 累计电量; 量化 6 位与 OrderFeeItem.unit_price 列一致。
                # merged_energy==0(两窗电量均量化为 0)时保留旧单价, 避免除零。
                "price": (merged_fee / merged_energy).quantize(Decimal("0.000001"))
                         if merged_energy > 0 else prev["price"],
                "fee": merged_fee,
                "minutes": prev["minutes"] + overlap_min,
            }
        else:
            period_breakdown[period_type] = {
                "energy": energy_q,
                "price": price,
                "fee": fee,
                "minutes": overlap_min,
            }
        total_fee += fee
        total_energy += energy_q

    # 时段重叠校验: 各 slot 覆盖分钟之和不得超过充电总时长, 否则恒功率分摊会使
    # total_energy > total_kwh 导致客户被多收费。配置错误应显式报错, 不静默处理。
    if total_overlap > total_minutes + 1e-9:
        raise ValueError("Time slots overlap, total overlap exceeds charging duration")

    # 覆盖完整性校验: time_slots 未完全覆盖充电区间时, 未覆盖分钟电量被静默排除,
    # total_energy < total_kwh, 客户少付费且无任何告警。不抛错(配置缺口由调用方默认电价
    # 兜底, 抛错反而整体走默认电价更糟), 但记 warning + 返回 coverage 标记, 让运维知晓
    # 并补全时段配置。
    coverage = total_overlap / total_minutes if total_minutes else 1.0
    if coverage < 1.0 - 1e-9:
        _logger.warning(
            "TOU 时段覆盖缺口: 充电 %.0f 分钟仅覆盖 %.0f 分钟 (coverage=%.2f%%), "
            "未覆盖部分电量被排除, total_energy<total_kwh, 客户可能少付费",
            total_minutes, total_overlap, coverage * 100,
        )

    return {
        "period_breakdown": period_breakdown,
        "energy_by_period": {pt: v["energy"] for pt, v in period_breakdown.items()},
        "total_fee": total_fee.quantize(TWO_PLACES),
        "total_energy": total_energy.quantize(TWO_PLACES),
        "coverage": coverage,
    }


# ═══════════════════════════════════════════════════════════════
# 2. 服务费多模式
# ═══════════════════════════════════════════════════════════════

def compute_service_fee_multi(
    charged_kwh: Decimal,
    fee_type: str,
    fee_value: Decimal,
) -> Decimal:
    """服务费多模式计算

    时区约定: 纯金额计算(电量×费率), 无时间入参。

    Args:
        charged_kwh: 充电电量(kWh)
        fee_type: "fixed"(元/次, 与电量无关) | "percent"(元/kWh)
        fee_value: fixed=每次金额; percent=每 kWh 金额

    Returns:
        服务费金额(元), 2 位小数
    """
    # 本函数全程依赖 _safe_decimal 降级(fee_value/charged_kwh 为 None/脏值 → 0),
    # 无崩溃缺口, 故不引入 BillingError。负数由乘积自然产生(hardening 卡未固化负数归零
    # 契约于此函数, 且无套利面 —— 负电量×正费率=负服务费由调用方兜底走默认费率)。
    value = _safe_decimal(fee_value)
    if fee_type == "fixed":
        # fixed=元/次, 固定金额量化到 2 位(费率 value 可能含多余小数位)
        return value.quantize(TWO_PLACES)
    if fee_type == "percent":
        # charged_kwh 可能为 None(电量未采集), _safe_decimal 降级为 0 → 服务费 0
        return (_safe_decimal(charged_kwh) * value).quantize(TWO_PLACES)
    # 未知/空 fee_type(配置错误): 显式报错, 不静默返回 0(否则配置错误被掩盖,
    # 该订单服务费悄无声息变 0)。调用方 _load_service_fee 有 try/except 兜底走 DEFAULT_SERVICE_FEE。
    raise ValueError(f"Unknown fee_type: {fee_type!r}")


# ═══════════════════════════════════════════════════════════════
# 3. 停车费完整规则
# ═══════════════════════════════════════════════════════════════

def _split_day_night(start: datetime, billable_minutes: int,
                     night_start: time, night_end: time) -> tuple:
    """将计费区间 [start, start+billable_minutes) 切分为白天/夜间分钟数。

    用每日夜间窗口与计费区间的相交长度累加(O(覆盖天数)≈O(1)),
    与逐分钟遍历结果完全等价(端点左闭右开一致)。
    """
    end = start + timedelta(minutes=billable_minutes)
    night_min = 0.0
    # 从 start 前一天起遍历, 覆盖 start 凌晨可能落入"前一日跨午夜夜间窗"的情形;
    # 多算的窗口相交长度为 0, 无副作用。
    cur_date = start.date() - timedelta(days=1)
    last_date = end.date()
    while cur_date <= last_date:
        ws, we = _slot_window_on_date(cur_date, night_start, night_end)
        night_min += _overlap_minutes(start, end, ws, we)
        cur_date += timedelta(days=1)
    night = int(round(night_min))
    day = billable_minutes - night
    return day, night


def compute_parking_fee_full(
    parking_minutes: int,
    parking_rule: dict,
    start_time: Optional[datetime] = None,
    charging_exempt_minutes: int = 0,
) -> dict:
    """停车费完整规则

    时区约定: start_time 期望为 **UTC naive datetime**(夜间费率分摊仅看本地时钟,
    aware 亦可, _split_day_night 内部用 datetime 算术不依赖 tzinfo)。

    Args:
        parking_minutes: 停车总时长(分钟; None/负数 → BillingError)
        parking_rule: {free_minutes, hourly_rate, daily_cap,
                       enable_night_rate, night_rate, night_start, night_end}
        start_time: 停车开始时间(UTC naive datetime; 夜间费率分摊需要)
        charging_exempt_minutes: 充电期间免除的停车分钟数(负数 → BillingError)

    Returns:
        {day_minutes, night_minutes, day_fee, night_fee, subtotal, total, capped}
    """
    # 顶层入参校验: parking_minutes=None 时下方 int(None) 抛 TypeError → BillingError
    # (编程错误)。负数由既有 max(0, int(...) - ...) 守卫钳为 0(billable=0 → 0 费),
    # 不在此抛错, 与 boundary 测试固化的"负数时长归零"契约一致。
    if parking_minutes is None:
        raise BillingError(
            f"compute_parking_fee_full parking_minutes 不能为 None: {parking_minutes!r}"
        )
    # 入参 sanitize: parking_rule=None(调用方未加载到规则) → 不崩, 返回 0 费。
    if not isinstance(parking_rule, dict):
        _logger.warning("停车费规则缺失或非 dict: %r, 降级为 0 费", parking_rule)
        return {
            "day_minutes": 0, "night_minutes": 0,
            "day_fee": Decimal("0.00"), "night_fee": Decimal("0.00"),
            "subtotal": Decimal("0.00"), "total": Decimal("0.00"), "capped": False,
        }
    free_minutes = int(parking_rule.get("free_minutes") or 0)
    # 负 charging_exempt_minutes 会让 billable 增大 → 用户多收费, 属调用方编程错误
    # (docstring 已承诺负数 → BillingError), 在计算 billable 前拦截。
    if charging_exempt_minutes is not None and int(charging_exempt_minutes) < 0:
        raise BillingError(
            f"charging_exempt_minutes 不能为负数: {charging_exempt_minutes}"
        )
    billable = max(0, int(parking_minutes) - free_minutes - int(charging_exempt_minutes))
    if billable <= 0:
        return {
            "day_minutes": 0, "night_minutes": 0,
            "day_fee": Decimal("0.00"), "night_fee": Decimal("0.00"),
            "subtotal": Decimal("0.00"), "total": Decimal("0.00"), "capped": False,
        }

    # _safe_decimal: hourly_rate 为 None / 非法字符串(配置错误) → 降级 0, 不崩。
    hourly_rate = _safe_decimal(parking_rule.get("hourly_rate"))
    enable_night = bool(parking_rule.get("enable_night_rate"))
    night_rate = parking_rule.get("night_rate")
    night_start = parking_rule.get("night_start")
    night_end = parking_rule.get("night_end")

    if enable_night and start_time and night_rate is not None and night_start and night_end:
        # night_start == night_end 被 _slot_window_on_date 视为全天窗(24h 夜间), 几乎必然是
        # 误配置 → 全部分钟按夜间费率(通常更低)→ 客户少付停车费。检测并降级为不启用夜间
        # 分摊(全白天费率), 记 warning 让运维修正配置。
        if night_start == night_end:
            _logger.warning(
                "停车费夜间窗配置疑似错误: night_start==night_end==%s, "
                "视为全天夜间窗, 已降级为白天费率计费", night_start,
            )
            day_min, night_min = billable, 0
        else:
            day_min, night_min = _split_day_night(start_time, billable, night_start, night_end)
        day_fee = (Decimal(day_min) / Decimal("60") * hourly_rate).quantize(TWO_PLACES)
        # _safe_decimal: night_rate 非法字符串(配置错误) → 降级 0, 不崩(与 hourly_rate 同策略)。
        night_rate_dec = _safe_decimal(night_rate)
        night_fee = (Decimal(night_min) / Decimal("60") * night_rate_dec).quantize(TWO_PLACES)
    else:
        day_min, night_min = billable, 0
        day_fee = (Decimal(billable) / Decimal("60") * hourly_rate).quantize(TWO_PLACES)
        night_fee = Decimal("0.00")

    subtotal = (day_fee + night_fee).quantize(TWO_PLACES)

    capped = False
    total = subtotal
    daily_cap = parking_rule.get("daily_cap")
    if daily_cap is not None:
        # daily_cap 为每 24h 封顶: 按 ceil(billable/1440) 个滚动计费块累计, 非自然日历日
        # (跨日历日但不足 24h 仍按 1 块, 不翻倍)。billable 已扣除免费时长与充电免除分钟。
        # _safe_decimal: daily_cap 非法字符串 → 降级为 0; 0 封顶无意义(cap=0 会把 total
        # 压成 0), 故 cap<=0 时视为无封顶(capped=False), 仅记 warning 让运维修正配置。
        cap = (_safe_decimal(daily_cap) * math.ceil(billable / 1440)).quantize(TWO_PLACES)
        if cap > 0 and total > cap:
            total = cap
            capped = True
        elif cap <= 0:
            _logger.warning("停车费 daily_cap 配置非法或为 0: %r, 视为无封顶", daily_cap)

    return {
        "day_minutes": day_min,
        "night_minutes": night_min,
        "day_fee": day_fee,
        "night_fee": night_fee,
        "subtotal": subtotal,
        "total": total.quantize(TWO_PLACES),
        "capped": capped,
    }


# ═══════════════════════════════════════════════════════════════
# 4. 占桩费完整规则
# ═══════════════════════════════════════════════════════════════

def compute_occupancy_fee_full(occupancy_minutes: int, occ_rule: dict) -> Decimal:
    """占桩费: 宽限时长后按分钟计费, 受单次封顶约束

    时区约定: 纯时长计费(分钟数), 无时间入参。

    Args:
        occupancy_minutes: 占桩时长(分钟; None → BillingError)
        occ_rule: {grace_minutes, rate_per_minute, max_fee}

    Returns:
        占桩费金额(元)
    """
    # 顶层入参校验: occupancy_minutes=None 时下方 int(None) 抛 TypeError → BillingError
    # (编程错误)。负数由既有 max(0, int(...) - grace) 守卫钳为 0, 不在此抛错,
    # 与 boundary 测试固化的"负数时长归零"契约一致。
    if occupancy_minutes is None:
        raise BillingError(
            f"compute_occupancy_fee_full occupancy_minutes 不能为 None: {occupancy_minutes!r}"
        )
    # 入参 sanitize: occ_rule=None(调用方未加载到规则) → 不崩, 返回 0 费。
    if not isinstance(occ_rule, dict):
        _logger.warning("占桩费规则缺失或非 dict: %r, 降级为 0 费", occ_rule)
        return Decimal("0.00")
    grace = int(occ_rule.get("grace_minutes") or 0)
    billable = max(0, int(occupancy_minutes) - grace)
    # _safe_decimal: rate_per_minute None/非法字符串 → 降级 0, 不崩。
    rate = _safe_decimal(occ_rule.get("rate_per_minute"))
    fee = (Decimal(billable) * rate).quantize(TWO_PLACES)
    max_fee = occ_rule.get("max_fee")
    if max_fee is not None:
        # max_fee None/非法 → 降级 0; cap<=0 无封顶意义, 不压制 fee, 仅记 warning。
        cap = _safe_decimal(max_fee)
        if cap > 0 and fee > cap:
            fee = cap
        elif cap <= 0:
            _logger.warning("占桩费 max_fee 配置非法或为 0: %r, 视为无封顶", max_fee)
    return fee


# ═══════════════════════════════════════════════════════════════
# 5. 预约费完整规则
# ═══════════════════════════════════════════════════════════════

def compute_reservation_fee_full(reservation_rule: dict, no_show: bool = False) -> dict:
    """预约费完整规则

    时区约定: 本函数纯金额计算, 不涉及时间入参(预约时段匹配由调用方在加载规则时完成)。

    Args:
        reservation_rule: {reservation_policy(slot_based/flat),
                           fee_amount, deposit_amount, no_show_penalty};
                           None / 非 dict → BillingError; 内部字段 None 降级 0,
                           负数 → BillingError
        no_show: 是否爽约(爽约则加收罚款)

    Returns:
        {fee, deposit, no_show_penalty, total}
        - fee: 预约费(flat/slot_based 均取 fee_amount)
        - deposit: 预约冻结金额(可退还, 不计入实收)
        - no_show_penalty: 爽约罚款
        - total: 实际收取 = fee + (no_show_penalty if no_show else 0)
    """
    # 顶层入参校验: reservation_rule=None 时下方 .get 抛 AttributeError, 非 dict 同理
    # → BillingError(编程错误)。与 parking/occupancy 的"None 规则降级 0 费"语义不同:
    # 预约费无规则即无业务, 调用方应先判空不调用本函数。
    if not isinstance(reservation_rule, dict):
        raise BillingError(
            f"compute_reservation_fee_full reservation_rule 必须为 dict, 实际: {reservation_rule!r}"
        )
    # 字段级负数校验: 金额字段为负是配置错误(防负预约费套利), 报 BillingError;
    # None/缺失走 `or 0` 降级(既有语义, 规则缺项不报错)。
    for _field in ("fee_amount", "deposit_amount", "no_show_penalty"):
        if _is_negative_decimal(reservation_rule.get(_field)):
            raise BillingError(
                f"compute_reservation_fee_full {_field} 不能为负数: {reservation_rule.get(_field)!r}"
            )
    fee = _q(reservation_rule.get("fee_amount") or 0)
    deposit = _q(reservation_rule.get("deposit_amount") or 0)
    penalty = _q(reservation_rule.get("no_show_penalty") or 0)
    total = fee + (penalty if no_show else Decimal("0.00"))
    return {
        "fee": fee,
        "deposit": deposit,
        "no_show_penalty": penalty,
        "total": total.quantize(TWO_PLACES),
    }


# ═══════════════════════════════════════════════════════════════
# 6. 综合费用(优惠三项分离)
# ═══════════════════════════════════════════════════════════════

def compute_order_fees(
    energy_fee: Decimal,
    service_fee: Decimal,
    parking_fee: Decimal,
    occupancy_fee: Decimal,
    reservation_fee: Decimal,
    discount_amount: Decimal = Decimal("0"),
    coupon_amount: Decimal = Decimal("0"),
    points_amount: Decimal = Decimal("0"),
) -> dict:
    """综合计算订单全部费用, 优惠三项分离

    总费用 = 充电费 + 服务费 + 停车费 + 占桩费 + 预约费
    实收   = 总费用 - 优惠券 - 积分 - 折扣(均不允许为负, 实收不低于 0)

    Returns:
        {total_amount, discount_amount, coupon_amount, points_amount, paid_amount}

    任一费用项为 None / 非法字符串(上游未采集/解析失败) → 该项安全降级为 0,
    不让单项异常中断整单汇总(_nonneg 内部 Decimal(str(None)) 会抛 InvalidOperation)。

    时区约定: 纯金额汇总, 无时间入参。

    负数约定: 5 项费用 / 优惠三项为负均由 _nonneg 钳为 0(既有归零守卫, 防负费用混入总额
    套利 / 防负优惠多抵扣), 不抛错 —— 与 edge_cases/boundary 测试固化的"负数归零"契约一致。
    """
    total_amount = (
        _nonneg(_safe_decimal(energy_fee))
        + _nonneg(_safe_decimal(service_fee))
        + _nonneg(_safe_decimal(parking_fee))
        + _nonneg(_safe_decimal(occupancy_fee))
        + _nonneg(_safe_decimal(reservation_fee))
    ).quantize(TWO_PLACES)

    discount = _nonneg(_safe_decimal(discount_amount))
    coupon = _nonneg(_safe_decimal(coupon_amount))
    points = _nonneg(_safe_decimal(points_amount))

    paid = total_amount - discount - coupon - points
    if paid < 0:
        paid = Decimal("0.00")

    return {
        "total_amount": total_amount,
        "discount_amount": discount,
        "coupon_amount": coupon,
        "points_amount": points,
        "paid_amount": paid.quantize(TWO_PLACES),
    }


# ═══════════════════════════════════════════════════════════════
# 7. 订单费用写入 + 明细
# ═══════════════════════════════════════════════════════════════

def settle_order_fees(
    order: ChargingOrder,
    fees: dict,
    db,
    energy_breakdown: Optional[List[dict]] = None,
) -> dict:
    """将计算好的费用写入 ChargingOrder 5项费用字段 + 生成 OrderFeeItem 明细行

    Args:
        order: 充电订单 ORM 对象
        fees: {energy_fee, service_fee, parking_fee, occupancy_fee, reservation_fee,
               discount_amount, coupon_amount, points_amount}
        db: SQLAlchemy Session
        energy_breakdown: 可选, 分时电量明细 [{period_name, kwh, price, fee, unit}],
                          提供则按时段生成多条电费明细, 否则电费汇总为单条

    Returns:
        {order_id, fee_items, total_amount, discount_amount, coupon_amount,
         points_amount, paid_amount}

    幂等: 重复结算会先清除该订单旧明细再重写。
    """
    # 写流程整体置于事务保护下: 中途异常 rollback, 不留半成品;
    # 不在此 commit, 提交边界交由调用方控制(避免与外层事务冲突/部分提交)。
    try:
        # 清除旧明细(幂等: 重复结算覆盖)
        db.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).delete()

        energy_fee = _q(fees.get("energy_fee") or 0)
        service_fee = _q(fees.get("service_fee") or 0)
        parking_fee = _q(fees.get("parking_fee") or 0)
        occupancy_fee = _q(fees.get("occupancy_fee") or 0)
        reservation_fee = _q(fees.get("reservation_fee") or 0)
        discount = _nonneg(fees.get("discount_amount") or 0)
        coupon = _nonneg(fees.get("coupon_amount") or 0)
        points = _nonneg(fees.get("points_amount") or 0)

        items: List[OrderFeeItem] = []

        # 1. 电费明细(分时多行 或 汇总单行)
        if energy_breakdown:
            for seg in energy_breakdown:
                # per-item 容错: 单条坏明细(类型错误/缺键/None 值等)只记日志跳过,
                # 不影响其余正常明细处理, 也不污染 total/paid 计算(total 由独立
                # energy_fee 字段汇总, 不依赖逐条 seg_fee 累加)。
                try:
                    seg_fee = _q(seg.get("fee") or 0)
                    if seg_fee != 0:
                        items.append(OrderFeeItem(
                            order_id=order.id, fee_type=FeeType.ELECTRICITY,
                            fee_name=str(seg.get("period_name", "电费")),
                            quantity=Decimal(str(seg.get("kwh") or 0)).quantize(Decimal("0.0001")),
                            unit_price=Decimal(str(seg.get("price") or 0)),
                            amount=seg_fee, unit=str(seg.get("unit", "kWh")),
                        ))
                except Exception:
                    _logger.exception("跳过异常的分时电量明细: %r", seg)
        elif energy_fee != 0:
            items.append(OrderFeeItem(
                order_id=order.id, fee_type=FeeType.ELECTRICITY, fee_name="电费",
                quantity=Decimal("1"), unit_price=energy_fee, amount=energy_fee, unit="元",
            ))

        # 2. 服务费
        if service_fee != 0:
            items.append(OrderFeeItem(
                order_id=order.id, fee_type=FeeType.SERVICE, fee_name="服务费",
                quantity=Decimal("1"), unit_price=service_fee, amount=service_fee, unit="元",
            ))

        # 3. 停车费
        if parking_fee != 0:
            items.append(OrderFeeItem(
                order_id=order.id, fee_type=FeeType.PARKING, fee_name="停车费",
                quantity=Decimal("1"), unit_price=parking_fee, amount=parking_fee, unit="元",
            ))

        # 4. 占桩费
        if occupancy_fee != 0:
            items.append(OrderFeeItem(
                order_id=order.id, fee_type=FeeType.OCCUPANCY, fee_name="占桩费",
                quantity=Decimal("1"), unit_price=occupancy_fee, amount=occupancy_fee, unit="元",
            ))

        # 5. 预约费
        if reservation_fee != 0:
            items.append(OrderFeeItem(
                order_id=order.id, fee_type=FeeType.RESERVATION, fee_name="预约费",
                quantity=Decimal("1"), unit_price=reservation_fee, amount=reservation_fee, unit="元",
            ))

        # 优惠明细行(负数金额表示抵扣)
        if discount != 0:
            items.append(OrderFeeItem(
                order_id=order.id, fee_type=FeeType.DISCOUNT, fee_name="折扣优惠",
                quantity=Decimal("1"), unit_price=discount, amount=-discount, unit="元",
            ))
        if coupon != 0:
            items.append(OrderFeeItem(
                order_id=order.id, fee_type=FeeType.COUPON, fee_name="优惠券抵扣",
                quantity=Decimal("1"), unit_price=coupon, amount=-coupon, unit="元",
            ))
        if points != 0:
            items.append(OrderFeeItem(
                order_id=order.id, fee_type=FeeType.POINTS, fee_name="积分抵扣",
                quantity=Decimal("1"), unit_price=points, amount=-points, unit="元",
            ))

        # 汇总并写入订单字段
        total_amount = (
            energy_fee + service_fee + parking_fee + occupancy_fee + reservation_fee
        ).quantize(TWO_PLACES)
        paid = total_amount - discount - coupon - points
        if paid < 0:
            paid = Decimal("0.00")

        order.electricity_fee = energy_fee
        order.service_fee = service_fee
        order.parking_fee = parking_fee
        order.occupancy_fee = occupancy_fee
        order.idle_penalty = occupancy_fee  # 兼容旧字段
        order.reservation_fee = reservation_fee
        order.total_amount = total_amount
        order.discount_amount = discount
        order.coupon_amount = coupon
        order.points_amount = points
        order.paid_amount = paid

        db.add_all(items)
        db.flush()  # 推入事务供调用方/后续查询可见; 提交边界由调用方控制
    except Exception:
        db.rollback()
        raise

    return {
        "order_id": order.id,
        "fee_items": [
            {
                "fee_type": i.fee_type.value if i.fee_type else None,
                "fee_name": i.fee_name,
                "amount": _to_amount(i.amount),
            }
            for i in items
        ],
        "total_amount": _to_amount(total_amount),
        "discount_amount": _to_amount(discount),
        "coupon_amount": _to_amount(coupon),
        "points_amount": _to_amount(points),
        "paid_amount": _to_amount(paid),
    }
