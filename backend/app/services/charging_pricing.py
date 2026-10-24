"""
充电计费接线服务 (d018e3dc)

把 pricing_v2 定价表数据组装成 billing_engine 纯函数的输入,
驱动 TOU 五项计费 + order_fee_items 明细写入。

billing_engine 此前是孤儿(零调用方), 本服务是其在
charging-session ingestion / 手工建单路径上的首个调用方, 闭合经营计费环。

定价数据流:
  TimeSlotDefinition + EnergyPrice   → compute_tou_energy_fee  (尖峰平谷电量拆分)
  ServiceFeePrice                    → compute_service_fee_multi
  ParkingPrice                       → compute_parking_fee_full
  OccupancyFeePrice                  → compute_occupancy_fee_full
  (预约费 ingestion 无数据源, 恒 0)
  → settle_order_fees  (写 ChargingOrder 5 项费用字段 + order_fee_items 明细)

兜底: 任一定价缺失 → 默认费率(电价 0.8/kWh, 服务费 0.5/kWh), 记 warning, 不崩。
全程 Decimal, 禁 float。
"""
from __future__ import annotations

import logging
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.services.billing_engine import (
    compute_tou_energy_fee,
    compute_service_fee_multi,
    compute_parking_fee_full,
    compute_occupancy_fee_full,
    settle_order_fees,
)
from app.models.charging_order import ChargingOrder
from app.models.pricing_v2 import (
    TimeSlotDefinition,
    EnergyPrice,
    ServiceFeePrice,
    ParkingPrice,
    OccupancyFeePrice,
    UserType as PricingUserType,
)
from app.tasks.tz_utils import today_in_biz_tz, to_aware_biz_tz

_logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")

# 默认兜底费率(无 pricing_v2 定价时), 与 charging_orders 手工建单默认一致
DEFAULT_ENERGY_PRICE = Decimal("0.8")   # 元/kWh
DEFAULT_SERVICE_FEE = Decimal("0.5")    # 元/kWh


def _today() -> date:
    """业务时区当前日期(缺陷2)。旧实现 ``date.today()`` 取容器本地日, 云端 UTC 部署
    时定价基准日整体错位(同卡 c42ac99a 时区缺陷族); 复用共享 ``today_in_biz_tz()``。"""
    return today_in_biz_tz()


def _biz_date(dt: datetime) -> date:
    """任意时刻 → 业务日(缺陷2)。

    aware → ``astimezone`` 转业务时区后取 date(跨午夜按业务日墙钟定日);
    naive → 按业务时区表面解释(贴 tz 不偏移)后取 date。供 settle 把充电开始时刻
    映射为定价基准日, 替代旧的 ``start_time.date()`` 裸取(aware UTC 时取到 UTC 当日)。
    """
    return to_aware_biz_tz(dt).date()


def _effective_filter(model_cls, today: date):
    """生效期过滤: effective_date <= today AND (expire_date IS NULL OR expire_date >= today)"""
    return (
        (model_cls.effective_date <= today)
        & or_(model_cls.expire_date.is_(None), model_cls.expire_date >= today)
    )


# ─────────────────────────────────────────────────────────
# 1. 电费: 尖峰平谷时段拆分
# ─────────────────────────────────────────────────────────

def _load_tou_energy(
    db: Session,
    station_id: int,
    charged_kwh: Decimal,
    start_time: datetime,
    end_time: datetime,
    charging_date: Optional[date] = None,
) -> Optional[Tuple[Decimal, List[dict]]]:
    """加载时段定义 + 站点电价 → compute_tou_energy_fee。

    Args:
        charging_date: 定价基准日(默认 None 回退 today)。跨午夜/延迟结算时应传充电日
            start_time.date(), 使生效期过滤基于充电日而非结算执行日, 调价日不错账。

    Returns:
        (energy_fee, energy_breakdown) 或 None(无可用定价, 调用方走默认兜底)
    """
    # DB查询/Decimal转换/billing_engine 任一异常 → 返回 None(等价"无可用定价"),
    # 由调用方走 DEFAULT_ENERGY_PRICE 兜底, 不让脏数据/库故障崩掉结算流程。
    try:
        today = charging_date or _today()
        slots = (
            db.query(TimeSlotDefinition)
            .filter(TimeSlotDefinition.is_active.is_(True))
            .all()
        )
        if not slots:
            return None

        ep_rows = (
            db.query(EnergyPrice)
            .filter(
                EnergyPrice.station_id == station_id,
                EnergyPrice.is_active.is_(True),
                EnergyPrice.effective_date <= today,
                or_(EnergyPrice.expire_date.is_(None), EnergyPrice.expire_date >= today),
            )
            # 缺陷1: 同 slot 重叠生效期取行须确定。按生效日降序, first-wins dict 取最新生效价。
            .order_by(EnergyPrice.effective_date.desc(), EnergyPrice.id.desc())
            .all()
        )
        if not ep_rows:
            return None

        # first-wins: 行已按生效日降序, 同 slot 首条即最新生效价(缺陷1)。
        # 旧 dict 推导 last-wins 按行序而非生效日, 重叠时取到旧行, 选取不确定。
        slot_prices: dict = {}
        for ep in ep_rows:
            if ep.slot_id not in slot_prices:
                slot_prices[ep.slot_id] = Decimal(str(ep.price_per_kwh))
        time_slots = [
            {
                "slot_id": s.id,
                "period_type": s.period_type.value,
                "start_time": s.start_time,
                "end_time": s.end_time,
            }
            for s in slots
            if s.id in slot_prices
        ]
        if not time_slots:
            return None

        result = compute_tou_energy_fee(start_time, end_time, charged_kwh, time_slots, slot_prices)
        breakdown = [
            {
                "period_name": f"{pt}段电费",
                "kwh": v["energy"],
                "price": v["price"],
                "fee": v["fee"],
                "unit": "kWh",
            }
            for pt, v in result["period_breakdown"].items()
        ]
        # 不变式核对(卡4671e993): 明细行金额之和必须 == 总电费(electricity_fee), 否则发票
        # 明细与订单总额不符。billing_engine 同 period_type 累加保证此式成立; 违反即
        # billing_engine 有 bug → 抛错, 由外层 except 兜底走默认电价, 不出错误明细。
        total_fee = result["total_fee"]
        bd_fee_sum = sum((Decimal(str(v["fee"])) for v in breakdown), Decimal("0.00"))
        if bd_fee_sum != total_fee:
            raise ValueError(
                f"TOU 明细金额之和 {bd_fee_sum} != 总电费 {total_fee}"
            )
        return total_fee, breakdown
    except Exception:
        _logger.exception(
            "charging_pricing _load_tou_energy 失败 station=%s, 走默认电价兜底", station_id
        )
        return None


# ─────────────────────────────────────────────────────────
# 2. 服务费
# ─────────────────────────────────────────────────────────

def _load_service_fee(
    db: Session,
    station_id: int,
    user_type_str: str,
    charged_kwh: Decimal,
    charging_date: Optional[date] = None,
) -> Optional[Decimal]:
    # DB查询/Decimal转换/billing_engine 任一异常 → 返回 None, 调用方走 DEFAULT_SERVICE_FEE 兜底。
    # charging_date: 定价基准日(默认 None 回退 today), 跨午夜/延迟结算传充电日。
    try:
        today = charging_date or _today()
        try:
            ptype = PricingUserType(user_type_str)
        except ValueError:
            ptype = PricingUserType.APP
        row = (
            db.query(ServiceFeePrice)
            .filter(
                ServiceFeePrice.station_id == station_id,
                ServiceFeePrice.user_type == ptype,
                ServiceFeePrice.is_active.is_(True),
                _effective_filter(ServiceFeePrice, today),
            )
            # 缺陷1: 同维度重叠生效期取行须确定, 取最新生效。
            .order_by(ServiceFeePrice.effective_date.desc(), ServiceFeePrice.id.desc())
            .first()
        )
        if not row:
            return None
        return compute_service_fee_multi(
            charged_kwh, row.fee_type.value, Decimal(str(row.fee_value))
        )
    except Exception:
        _logger.exception(
            "charging_pricing _load_service_fee 失败 station=%s user_type=%s, 走默认服务费兜底",
            station_id, user_type_str,
        )
        return None


# ─────────────────────────────────────────────────────────
# 3. 停车费
# ─────────────────────────────────────────────────────────

def _load_parking_fee(
    db: Session,
    station_id: int,
    parking_minutes: int,
    start_time: Optional[datetime],
    charging_date: Optional[date] = None,
) -> Decimal:
    if not parking_minutes or parking_minutes <= 0:
        return Decimal("0.00")
    # DB查询/Decimal转换/billing_engine 任一异常 → 返回 0(等价"无定价"), 不崩结算。
    # charging_date: 定价基准日(默认 None 回退 today), 跨午夜/延迟结算传充电日。
    try:
        today = charging_date or _today()
        row = (
            db.query(ParkingPrice)
            .filter(
                ParkingPrice.station_id == station_id,
                ParkingPrice.is_active.is_(True),
                _effective_filter(ParkingPrice, today),
            )
            # 缺陷1: 同维度重叠生效期取行须确定, 取最新生效。
            .order_by(ParkingPrice.effective_date.desc(), ParkingPrice.id.desc())
            .first()
        )
        if not row:
            return Decimal("0.00")
        rule = {
            "free_minutes": row.free_minutes or 0,
            "hourly_rate": Decimal(str(row.hourly_rate)),
            "daily_cap": Decimal(str(row.daily_cap)) if row.daily_cap is not None else None,
            "enable_night_rate": bool(row.enable_night_rate),
            "night_rate": Decimal(str(row.night_rate)) if row.night_rate is not None else None,
            "night_start": row.night_start,
            "night_end": row.night_end,
        }
        return compute_parking_fee_full(parking_minutes, rule, start_time=start_time)["total"]
    except Exception:
        _logger.exception(
            "charging_pricing _load_parking_fee 失败 station=%s, 停车费置 0", station_id
        )
        return Decimal("0.00")


# ─────────────────────────────────────────────────────────
# 4. 占桩费
# ─────────────────────────────────────────────────────────

def _load_occupancy_fee(
    db: Session,
    station_id: int,
    occupancy_minutes: int,
    charging_date: Optional[date] = None,
) -> Decimal:
    if not occupancy_minutes or occupancy_minutes <= 0:
        return Decimal("0.00")
    # DB查询/Decimal转换/billing_engine 任一异常 → 返回 0(等价"无定价"), 不崩结算。
    # charging_date: 定价基准日(默认 None 回退 today), 跨午夜/延迟结算传充电日。
    try:
        today = charging_date or _today()
        row = (
            db.query(OccupancyFeePrice)
            .filter(
                OccupancyFeePrice.station_id == station_id,
                OccupancyFeePrice.is_active.is_(True),
                _effective_filter(OccupancyFeePrice, today),
            )
            # 缺陷1: 同维度重叠生效期取行须确定, 取最新生效。
            .order_by(OccupancyFeePrice.effective_date.desc(), OccupancyFeePrice.id.desc())
            .first()
        )
        if not row:
            return Decimal("0.00")
        rule = {
            "grace_minutes": row.grace_minutes or 0,
            "rate_per_minute": Decimal(str(row.rate_per_minute)),
            "max_fee": Decimal(str(row.max_fee)) if row.max_fee is not None else None,
        }
        return compute_occupancy_fee_full(occupancy_minutes, rule)
    except Exception:
        _logger.exception(
            "charging_pricing _load_occupancy_fee 失败 station=%s, 占桩费置 0", station_id
        )
        return Decimal("0.00")


# ─────────────────────────────────────────────────────────
# 综合结算入口
# ─────────────────────────────────────────────────────────

def settle_charging_session(
    db: Session,
    order: ChargingOrder,
    start_time: datetime,
    end_time: datetime,
    charged_kwh: Decimal,
    user_type_str: str = "app",
    parking_minutes: int = 0,
    occupancy_minutes: int = 0,
) -> dict:
    """加载站点 pricing_v2 定价 → billing_engine 计费 → settle_order_fees 写入。

    无定价 → 默认费率兜底(记 warning), 不抛异常。
    调用方需先 commit 订单拿到 order.id, 再调本函数(本函数在 settle 后负责 commit)。

    Args:
        db: SQLAlchemy Session
        order: 已持久化的 ChargingOrder(含 station_id / order_no)
        start_time / end_time: 充电起止时间(TOU 拆分依据)
        charged_kwh: 充电电量(Decimal, kWh)
        user_type_str: pricing 维度用户类型(enterprise/vin/app/card/interconnect)
        parking_minutes / occupancy_minutes: 停车/占桩分钟(ingestion 一般为 0)

    Returns:
        fees dict(含 5 项费用 + 优惠三项 + used_default 标记)
    """
    station_id = order.station_id
    # 入站 start/end 可能 naive(手工建单/旧测试) 或 aware(ingestion 已转 aware biz-tz)。
    # billing_engine 纯函数按"业务时区墙钟"匹配 TOU 时段/夜间窗(槽位为时:分无 tz), 须喂
    # naive 墙钟: 统一经 to_aware_biz_tz 归一到业务时区后剥 tz。aware 直传会让墙钟 vs
    # naive 槽窗比较抛 TypeError。定价基准日取业务日(缺陷2), 跨午夜按业务日定日。
    start_wall = to_aware_biz_tz(start_time).replace(tzinfo=None) if start_time else None
    end_wall = to_aware_biz_tz(end_time).replace(tzinfo=None) if end_time else None
    charging_date = _biz_date(start_time) if start_time else None
    # 整体置于异常保护下: settle_order_fees 写库 / db.commit 任一失败 → rollback + 记日志 +
    # 返回错误信息 dict(不抛); 调用方(charging_sessions)据 dict.error 决定后续, 订单已建费用保持 0。
    try:
        used_default = False

        # 1. 电费 (TOU 拆分或默认兜底)
        tou = _load_tou_energy(db, station_id, charged_kwh, start_wall, end_wall,
                               charging_date=charging_date)
        if tou is not None:
            energy_fee, energy_breakdown = tou
        else:
            used_default = True
            energy_fee = (charged_kwh * DEFAULT_ENERGY_PRICE).quantize(TWO_PLACES)
            energy_breakdown = None

        # 2. 服务费
        sf = _load_service_fee(db, station_id, user_type_str, charged_kwh,
                               charging_date=charging_date)
        if sf is not None:
            service_fee = sf
        else:
            used_default = True
            service_fee = (charged_kwh * DEFAULT_SERVICE_FEE).quantize(TWO_PLACES)

        # 3. 停车费 / 4. 占桩费 (无定价 → 0, 不兜底)
        parking_fee = _load_parking_fee(db, station_id, parking_minutes, start_wall,
                                        charging_date=charging_date)
        occupancy_fee = _load_occupancy_fee(db, station_id, occupancy_minutes,
                                            charging_date=charging_date)

        # 5. 预约费 (ingestion 无预约语义 → 恒 0)
        reservation_fee = Decimal("0.00")

        if used_default:
            _logger.warning(
                "charging_session order=%s station=%s 部分定价缺失, 使用默认费率兜底"
                "(电价 %s/kWh, 服务费 %s/kWh)",
                order.order_no, station_id, DEFAULT_ENERGY_PRICE, DEFAULT_SERVICE_FEE,
            )

        fees = {
            "energy_fee": energy_fee,
            "service_fee": service_fee,
            "parking_fee": parking_fee,
            "occupancy_fee": occupancy_fee,
            "reservation_fee": reservation_fee,
            "discount_amount": Decimal("0"),
            "coupon_amount": Decimal("0"),
            "points_amount": Decimal("0"),
            "used_default": used_default,
        }
        settle_order_fees(order, fees, db, energy_breakdown=energy_breakdown)
        db.commit()  # settle_order_fees 不再内部 commit, 提交边界由本层控制
        return fees
    except Exception:
        db.rollback()
        _logger.exception(
            "charging_session 结算失败 order=%s station=%s, 费用未落库(订单已建, 费用保持 0)",
            getattr(order, "order_no", None), station_id,
        )
        return {
            "error": "charging_session settle failed",
            "order_no": getattr(order, "order_no", None),
        }
