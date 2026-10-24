"""
运营分析 6 大报表聚合 API

1. GET /analytics/revenue          — 营收总览(总营收/充电量/订单数/客单价 + 趋势序列)
2. GET /analytics/fee-breakdown    — 5项费用占比 + 趋势
3. GET /analytics/user-revenue     — 按用户类型营收贡献/户均消费/复充率
4. GET /analytics/station-rank     — 站点营收/充电量/利用率/收益每桩 排行
5. GET /analytics/time-slot        — 尖峰平谷时段电量/电价贡献/服务费占比
6. GET /analytics/coupon-effect    — 券核销率/增量订单/优惠成本vs营收增长/ROI

数据来源: charging_orders + order_fee_items + coupons/coupon_usages

team scoping（任务卡 1c19b59a）：6 大报表均按 ChargingOrder.station_id→Station.team_id
过滤；coupon-effect 的券统计按 CouponUsage.user_id→User.team_id 过滤。admin/super_admin
平台级豁免（不过滤，见全平台数据）。
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case, String

from app.core.database import get_db
from app.core.response import success_response
from app.models.charging_order import ChargingOrder, OrderPaymentStatus
from app.models.order_fee_item import OrderFeeItem, FeeType, RefundRecord, RefundStatus
from app.models.coupon import Coupon, CouponUsage, CouponStatus
from app.models.station import Station
from app.models.user import User
from app.api.deps import is_platform_admin
from app.api.v1.auth import get_current_user
from fastapi import HTTPException
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── team scoping 辅助（任务卡 1c19b59a）───

def _team_tid(user) -> Optional[int]:
    """admin/super_admin 返回 None（不过滤，平台级全可见）；团队级返回 user.team_id。"""
    if is_platform_admin(user):
        return None
    return user.team_id


def _scope_orders(q, user):
    """ChargingOrder 查询叠加 team 过滤（经 station_id→Station.team_id）。"""
    tid = _team_tid(user)
    if tid is None:
        return q
    return q.outerjoin(Station, Station.id == ChargingOrder.station_id).filter(Station.team_id == tid)


def _scope_coupon_usage(q, user):
    """CouponUsage 查询叠加 team 过滤（经领取人 user_id→User.team_id）。"""
    tid = _team_tid(user)
    if tid is None:
        return q
    return q.join(User, User.id == CouponUsage.user_id).filter(User.team_id == tid)


# ─── 退款扣减口径（任务卡 a1e8299d）───
# 毛营收(revenue 口径)本端点原为 payment_status==PAID。真实退款流(order_fees.complete_refund)
# 会把全额退款订单置 REFUNDED、部分退款置 PARTIAL —— 若毛口径仍只算 PAID、再从毛里扣退款,
# 全额退款订单会被"既不算收入又扣一遍退款"双重扣减。故:
# 1. 毛口径扩为 PAID/PARTIAL/REFUNDING/REFUNDED(曾支付过的订单集合), 保持 PAID 语义不变兼容;
# 2. net = gross - ΣRefundRecord(status=REFUNDED).refund_amount;
# 3. 时间窗口: 退款按"关联订单 created_at"回溯过滤(而非 refunded_at) — 营收按下单窗口统计,
#    今日下单/次日退的退款必须归入下单窗口, 两侧口径才自洽对齐(结算日结用 refunded_at 是
#    现金流口径, 本报表是订单归属口径, 二者刻意不同)。
_PAID_LIKE = [
    OrderPaymentStatus.PAID, OrderPaymentStatus.PARTIAL,
    OrderPaymentStatus.REFUNDING, OrderPaymentStatus.REFUNDED,
]


def _refund_subquery(db, user, start, end):
    """当前 scope 内 [start,end) 下单窗口的退款子查询(经关联订单回溯归属)。

    返回 ChargingOrder.id → 已到账退款额 的映射, 供趋势分组与汇总共用。
    """
    q = db.query(
        RefundRecord.order_id,
        func.coalesce(func.sum(RefundRecord.refund_amount), 0).label("refund"),
    ).join(ChargingOrder, ChargingOrder.id == RefundRecord.order_id).filter(
        RefundRecord.status == RefundStatus.REFUNDED,
        ChargingOrder.created_at >= start,
        ChargingOrder.created_at < end,
    )
    q = _scope_orders(q, user)
    return {r.order_id: Decimal(str(r.refund or 0)) for r in q.group_by(RefundRecord.order_id).all()}


# ─── 辅助函数 ───

def _parse_range(range_str: str) -> tuple[datetime, datetime, str, str]:
    """解析时间范围参数, 返回 (start, end, sqlite_fmt, pg_fmt)

    两套格式串分别对应 SQLite func.strftime 与 PostgreSQL func.to_char:
    SQLite 用 C89 strftime 占位符(%Y-%m-%d 等), PG 用自己的模板(YYYY-MM-DD 等)。
    生产 PG 上 func.strftime 不存在, 必须走 to_char。
    """
    now = datetime.now(timezone.utc)
    if range_str == "day":
        start = now - timedelta(days=30)
        sqlite_fmt, pg_fmt = "%Y-%m-%d", "YYYY-MM-DD"
    elif range_str == "week":
        start = now - timedelta(weeks=12)
        # SQLite %W = 周一为起点的年中周数; PG 用 ISO 周 IW + ISO 年 IYYY 对齐
        sqlite_fmt, pg_fmt = "%Y-W%W", 'IYYY-"W"IW'
    elif range_str == "month":
        start = now - timedelta(days=365)
        sqlite_fmt, pg_fmt = "%Y-%m", "YYYY-MM"
    elif range_str == "year":
        start = now - timedelta(days=365 * 3)
        sqlite_fmt, pg_fmt = "%Y", "YYYY"
    else:
        start = now - timedelta(days=30)
        sqlite_fmt, pg_fmt = "%Y-%m-%d", "YYYY-MM-DD"
    return start, now, sqlite_fmt, pg_fmt


def _build_period_expr(dialect_name: str, col, sqlite_fmt: str, pg_fmt: str):
    """按数据库方言返回时间截断列表达式(label='period')

    - SQLite: func.strftime(sqlite_fmt, col)
    - PostgreSQL(及其它): func.to_char(col, pg_fmt)

    func.strftime 是 SQLite 专有函数, PG 上会抛 UndefinedFunction; 反之 to_char
    在 SQLite 上不存在, 故必须按 dialect 分支。dialect_name 取自 db.bind.dialect.name。
    """
    if dialect_name == "sqlite":
        return func.strftime(sqlite_fmt, col).label("period")
    return func.to_char(col, pg_fmt).label("period")


# ─── 1. 营收总览 ───

@router.get("/analytics/revenue", summary="营收总览 — 总营收/充电量/订单数/客单价 + 趋势")
def analytics_revenue(
    range: str = Query("day", pattern="^(day|week|month|year)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        start, end, sqlite_fmt, pg_fmt = _parse_range(range)
        dialect_name = db.bind.dialect.name if db.bind else "sqlite"

        # 卡 a1e8299d: 毛/净/退款三口径。毛口径含曾支付订单(PAID/PARTIAL/REFUNDING/REFUNDED),
        # 退款子查询按订单 created_at 窗口回溯, 详见 _PAID_LIKE 注释。
        refund_map = _refund_subquery(db, current_user, start, end)
        total_refund = sum(refund_map.values(), Decimal("0"))

        total_revenue = _scope_orders(
            db.query(func.coalesce(func.sum(ChargingOrder.paid_amount), 0)), current_user
        ).filter(
            ChargingOrder.payment_status.in_(_PAID_LIKE),
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        ).scalar() or Decimal("0")

        total_kwh = _scope_orders(
            db.query(func.coalesce(func.sum(ChargingOrder.charged_kwh), 0)), current_user
        ).filter(
            ChargingOrder.payment_status.in_(_PAID_LIKE),
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        ).scalar() or Decimal("0")

        total_orders = _scope_orders(
            db.query(func.count(ChargingOrder.id)), current_user
        ).filter(
            ChargingOrder.payment_status.in_(_PAID_LIKE),
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        ).scalar() or 0

        avg_per_order = float(total_revenue) / total_orders if total_orders > 0 else 0.0

        # 趋势序列 — 按时间粒度分组(退款按订单归期, 在 Python 层按 period 合并)
        period_label = _build_period_expr(dialect_name, ChargingOrder.created_at, sqlite_fmt, pg_fmt)
        trend_q = _scope_orders(
            db.query(
                period_label,
                func.coalesce(func.sum(ChargingOrder.paid_amount), 0).label("revenue"),
                func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("kwh"),
                func.count(ChargingOrder.id).label("orders"),
            ), current_user
        ).filter(
            ChargingOrder.payment_status.in_(_PAID_LIKE),
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        ).group_by(period_label).order_by(period_label).all()

        # 订单 created_at → 所属期标签, 用于把 refund_map 归到各期
        order_periods = {
            row.id: row.period
            for row in _scope_orders(
                db.query(ChargingOrder.id, period_label), current_user
            ).filter(
                ChargingOrder.created_at >= start,
                ChargingOrder.created_at < end,
                ChargingOrder.id.in_(refund_map.keys()) if refund_map else False,
            ).all()
        }
        refund_by_period = defaultdict(Decimal)
        for oid, amt in refund_map.items():
            refund_by_period[order_periods.get(oid)] += amt

        trend = [
            {
                "period": row.period,
                "revenue": float(row.revenue),
                "refund": float(refund_by_period.get(row.period, 0)),
                "net_revenue": float(row.revenue) - float(refund_by_period.get(row.period, 0)),
                "kwh": float(row.kwh),
                "orders": row.orders,
            }
            for row in trend_q
        ]

        return success_response({
            "summary": {
                "total_revenue": float(total_revenue),
                "total_refund": float(total_refund),
                "net_revenue": float(total_revenue) - float(total_refund),
                "total_kwh": float(total_kwh),
                "total_orders": total_orders,
                "avg_per_order": round(avg_per_order, 2),
            },
            "trend": trend,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("analytics_revenue 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── 2. 费用占比分析 ───

@router.get("/analytics/fee-breakdown", summary="费用占比分析 — 5项费用占比 + 趋势")
def analytics_fee_breakdown(
    range: str = Query("day", pattern="^(day|week|month|year)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        start, end, sqlite_fmt, pg_fmt = _parse_range(range)
        dialect_name = db.bind.dialect.name if db.bind else "sqlite"

        # 从 order_fee_items 聚合各费用类型
        fee_q = _scope_orders(
            db.query(
                OrderFeeItem.fee_type,
                func.coalesce(func.sum(OrderFeeItem.amount), 0).label("total"),
            ).join(ChargingOrder, ChargingOrder.id == OrderFeeItem.order_id),
            current_user,
        ).filter(
            ChargingOrder.payment_status == OrderPaymentStatus.PAID,
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
            OrderFeeItem.fee_type.in_([
                FeeType.ELECTRICITY, FeeType.SERVICE,
                FeeType.PARKING, FeeType.OCCUPANCY, FeeType.RESERVATION,
            ]),
        ).group_by(OrderFeeItem.fee_type).all()

        fee_map = {row.fee_type.value: float(row.total) for row in fee_q}
        total_fees = sum(fee_map.values()) if fee_map else 0.0

        breakdown = []
        fee_labels = {
            "electricity": "充电费",
            "service": "服务费",
            "parking": "停车费",
            "occupancy": "占桩费",
            "reservation": "预约费",
        }
        for ftype, label in fee_labels.items():
            val = fee_map.get(ftype, 0.0)
            breakdown.append({
                "fee_type": ftype,
                "fee_name": label,
                "amount": round(val, 2),
                "percentage": round(val / total_fees * 100, 2) if total_fees > 0 else 0.0,
            })

        # 趋势 — 充电费+服务费按时间序列
        period_label = _build_period_expr(dialect_name, ChargingOrder.created_at, sqlite_fmt, pg_fmt)
        trend_q = _scope_orders(
            db.query(
                period_label,
                func.coalesce(func.sum(case(
                    (OrderFeeItem.fee_type == FeeType.ELECTRICITY, OrderFeeItem.amount),
                    else_=0,
                )), 0).label("electricity"),
                func.coalesce(func.sum(case(
                    (OrderFeeItem.fee_type == FeeType.SERVICE, OrderFeeItem.amount),
                    else_=0,
                )), 0).label("service"),
                func.coalesce(func.sum(case(
                    (OrderFeeItem.fee_type == FeeType.PARKING, OrderFeeItem.amount),
                    else_=0,
                )), 0).label("parking"),
                func.coalesce(func.sum(case(
                    (OrderFeeItem.fee_type == FeeType.OCCUPANCY, OrderFeeItem.amount),
                    else_=0,
                )), 0).label("occupancy"),
                func.coalesce(func.sum(case(
                    (OrderFeeItem.fee_type == FeeType.RESERVATION, OrderFeeItem.amount),
                    else_=0,
                )), 0).label("reservation"),
            ).join(ChargingOrder, ChargingOrder.id == OrderFeeItem.order_id),
            current_user,
        ).filter(
            ChargingOrder.payment_status == OrderPaymentStatus.PAID,
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        ).group_by(period_label).order_by(period_label).all()

        trend = [
            {
                "period": row.period,
                "electricity": float(row.electricity),
                "service": float(row.service),
                "parking": float(row.parking),
                "occupancy": float(row.occupancy),
                "reservation": float(row.reservation),
            }
            for row in trend_q
        ]

        return success_response({
            "breakdown": breakdown,
            "total": round(total_fees, 2),
            "trend": trend,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("analytics_fee_breakdown 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── 3. 用户收入分析 ───

@router.get("/analytics/user-revenue", summary="用户收入分析 — 按用户类型营收贡献/户均消费/复充率")
def analytics_user_revenue(
    range: str = Query("day", pattern="^(day|week|month|year)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        start, end, *_ = _parse_range(range)

        # user_type 是 SAEnum(UserType)(仅 app/card); 与 vin/interconnect/enterprise 字面量直接比较
        # 会触发 PG enum 强校验 InvalidTextRepresentation → 500(SQLite 容忍故测试不暴露)。
        # cast(String) 后按文本比较, 绕开 enum 取值域校验。修复 [35aad373]。
        user_type_label = case(
            (ChargingOrder.user_type.cast(String) == "app", "APP用户"),
            (ChargingOrder.user_type.cast(String) == "card", "卡用户"),
            (ChargingOrder.user_type.cast(String) == "vin", "VIN用户"),
            (ChargingOrder.user_type.cast(String) == "interconnect", "互联互通"),
            (ChargingOrder.user_type.cast(String) == "enterprise", "企业用户"),
            else_="其他",
        )

        q = _scope_orders(
            db.query(
                ChargingOrder.user_type,
                user_type_label.label("type_label"),
                func.coalesce(func.sum(ChargingOrder.paid_amount), 0).label("revenue"),
                func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("kwh"),
                func.count(ChargingOrder.id).label("orders"),
                func.count(func.distinct(ChargingOrder.user_id)).label("unique_users"),
            ), current_user
        ).filter(
            ChargingOrder.payment_status == OrderPaymentStatus.PAID,
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        ).group_by(ChargingOrder.user_type, user_type_label).all()

        result = []
        for row in q:
            unique_users = row.unique_users or 1
            orders = row.orders or 0
            revenue = float(row.revenue)
            result.append({
                "user_type": row.user_type.value if row.user_type else "unknown",
                "type_label": row.type_label,
                "revenue": round(revenue, 2),
                "kwh": round(float(row.kwh), 2),
                "orders": orders,
                "unique_users": row.unique_users,
                "avg_per_user": round(revenue / unique_users, 2),
                "orders_per_user": round(orders / unique_users, 2),
                # 复充率: 有2笔以上订单的用户占比(近似用 orders/users 估算)
                "recharge_rate": round(min(orders / unique_users, 1.0) * 100, 1) if unique_users > 0 else 0.0,
            })

        return success_response({"breakdown": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("analytics_user_revenue 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── 4. 站点收益排行 ───

@router.get("/analytics/station-rank", summary="站点收益排行 — 营收/充电量/利用率/收益每桩")
def analytics_station_rank(
    range: str = Query("day", pattern="^(day|week|month|year)$"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        start, end, *_ = _parse_range(range)

        tid = _team_tid(current_user)
        q = db.query(
            ChargingOrder.station_id,
            Station.name.label("station_name"),
            Station.code.label("station_code"),
            func.coalesce(func.sum(ChargingOrder.paid_amount), 0).label("revenue"),
            func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("kwh"),
            func.count(ChargingOrder.id).label("orders"),
            func.coalesce(func.sum(ChargingOrder.duration_minutes), 0).label("total_minutes"),
        ).outerjoin(
            Station, Station.id == ChargingOrder.station_id
        ).filter(
            ChargingOrder.payment_status == OrderPaymentStatus.PAID,
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        )
        # team scoping（任务卡 1c19b59a）：复用已 outerjoin 的 Station，非 admin 限定本 team 站点。
        if tid is not None:
            q = q.filter(Station.team_id == tid)
        q = q.group_by(
            ChargingOrder.station_id, Station.name, Station.code
        ).order_by(
            func.coalesce(func.sum(ChargingOrder.paid_amount), 0).desc()
        ).limit(limit).all()

        # 时间跨度天数
        days_span = max((end - start).days, 1)

        result = []
        for row in q:
            total_minutes = float(row.total_minutes or 0)
            # 利用率: 充电时长 / (天数 * 24 * 60) 近似单桩利用率
            utilization = round(min(total_minutes / (days_span * 24 * 60) * 100, 100), 2)
            # 收益每桩 = 总营收 / (天数 * 假设站点桩数=orders/10+1)
            estimated_piles = max(row.orders // 50 + 1, 1)
            revenue_per_pile = round(float(row.revenue) / estimated_piles, 2)

            result.append({
                "station_id": row.station_id,
                "station_name": row.station_name or f"站点{row.station_id}",
                "station_code": row.station_code or "",
                "revenue": round(float(row.revenue), 2),
                "kwh": round(float(row.kwh), 2),
                "orders": row.orders,
                "utilization_rate": utilization,
                "revenue_per_pile": revenue_per_pile,
                "avg_revenue_per_order": round(float(row.revenue) / row.orders, 2) if row.orders else 0,
            })

        return success_response({"ranking": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("analytics_station_rank 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── 5. 时段收益分析 ───

@router.get("/analytics/time-slot", summary="时段收益分析 — 尖峰平谷电量/电价/服务费")
def analytics_time_slot(
    range: str = Query("day", pattern="^(day|week|month|year)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        start, end, *_ = _parse_range(range)

        q = _scope_orders(
            db.query(
                func.coalesce(func.sum(ChargingOrder.peak_energy), 0).label("peak_kwh"),
                func.coalesce(func.sum(ChargingOrder.flat_energy), 0).label("flat_kwh"),
                func.coalesce(func.sum(ChargingOrder.valley_energy), 0).label("valley_kwh"),
                func.coalesce(func.sum(ChargingOrder.trough_energy), 0).label("trough_kwh"),
                func.coalesce(func.sum(ChargingOrder.electricity_fee), 0).label("total_elec_fee"),
                func.coalesce(func.sum(ChargingOrder.service_fee), 0).label("total_service_fee"),
                func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("total_kwh"),
                func.count(ChargingOrder.id).label("total_orders"),
            ), current_user
        ).filter(
            ChargingOrder.payment_status == OrderPaymentStatus.PAID,
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        ).first()

        total_kwh = float(q.total_kwh or 0)
        total_elec = float(q.total_elec_fee or 0)
        total_svc = float(q.total_service_fee or 0)
        total_fee = total_elec + total_svc

        slots = [
            {
                "slot_name": "尖峰",
                "slot_key": "peak",
                "kwh": float(q.peak_kwh or 0),
                "kwh_percentage": round(float(q.peak_kwh or 0) / total_kwh * 100, 2) if total_kwh > 0 else 0,
            },
            {
                "slot_name": "平段",
                "slot_key": "flat",
                "kwh": float(q.flat_kwh or 0),
                "kwh_percentage": round(float(q.flat_kwh or 0) / total_kwh * 100, 2) if total_kwh > 0 else 0,
            },
            {
                "slot_name": "谷段",
                "slot_key": "valley",
                "kwh": float(q.valley_kwh or 0),
                "kwh_percentage": round(float(q.valley_kwh or 0) / total_kwh * 100, 2) if total_kwh > 0 else 0,
            },
            {
                "slot_name": "深谷",
                "slot_key": "trough",
                "kwh": float(q.trough_kwh or 0),
                "kwh_percentage": round(float(q.trough_kwh or 0) / total_kwh * 100, 2) if total_kwh > 0 else 0,
            },
        ]

        return success_response({
            "slots": slots,
            "summary": {
                "total_kwh": round(total_kwh, 2),
                "total_electricity_fee": round(total_elec, 2),
                "total_service_fee": round(total_svc, 2),
                "electricity_fee_ratio": round(total_elec / total_fee * 100, 2) if total_fee > 0 else 0,
                "service_fee_ratio": round(total_svc / total_fee * 100, 2) if total_fee > 0 else 0,
                "total_orders": q.total_orders or 0,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("analytics_time_slot 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── 6. 优惠效果分析 ───

@router.get("/analytics/coupon-effect", summary="优惠效果分析 — 券核销率/增量订单/优惠成本/ROI")
def analytics_coupon_effect(
    range: str = Query("day", pattern="^(day|week|month|year)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        start, end, *_ = _parse_range(range)

        # 券统计（team scoping：经领取人 user_id→User.team_id）
        total_coupons = _scope_coupon_usage(
            db.query(func.count(CouponUsage.id)), current_user
        ).filter(
            CouponUsage.received_at >= start,
            CouponUsage.received_at < end,
        ).scalar() or 0

        used_coupons = _scope_coupon_usage(
            db.query(func.count(CouponUsage.id)), current_user
        ).filter(
            CouponUsage.received_at >= start,
            CouponUsage.received_at < end,
            CouponUsage.status == CouponStatus.USED,
        ).scalar() or 0

        expired_coupons = _scope_coupon_usage(
            db.query(func.count(CouponUsage.id)), current_user
        ).filter(
            CouponUsage.received_at >= start,
            CouponUsage.received_at < end,
            CouponUsage.status == CouponStatus.EXPIRED,
        ).scalar() or 0

        # 优惠成本 = 已用券的 discount_amount 总和 + 订单中 coupon_amount
        coupon_cost = _scope_coupon_usage(
            db.query(func.coalesce(func.sum(CouponUsage.discount_amount), 0)), current_user
        ).filter(
            CouponUsage.received_at >= start,
            CouponUsage.received_at < end,
            CouponUsage.status == CouponStatus.USED,
        ).scalar() or Decimal("0")

        order_coupon_amount = _scope_orders(
            db.query(func.coalesce(func.sum(ChargingOrder.coupon_amount), 0)), current_user
        ).filter(
            ChargingOrder.payment_status == OrderPaymentStatus.PAID,
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        ).scalar() or Decimal("0")

        total_discount_cost = float(coupon_cost) + float(order_coupon_amount)

        # 使用了券的订单数
        coupon_orders = _scope_coupon_usage(
            db.query(func.count(func.distinct(CouponUsage.order_id))), current_user
        ).filter(
            CouponUsage.received_at >= start,
            CouponUsage.received_at < end,
            CouponUsage.status == CouponStatus.USED,
            CouponUsage.order_id.isnot(None),
        ).scalar() or 0

        # 同期总订单和总营收
        total_orders = _scope_orders(
            db.query(func.count(ChargingOrder.id)), current_user
        ).filter(
            ChargingOrder.payment_status == OrderPaymentStatus.PAID,
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        ).scalar() or 0

        total_revenue = _scope_orders(
            db.query(func.coalesce(func.sum(ChargingOrder.paid_amount), 0)), current_user
        ).filter(
            ChargingOrder.payment_status == OrderPaymentStatus.PAID,
            ChargingOrder.created_at >= start,
            ChargingOrder.created_at < end,
        ).scalar() or Decimal("0")

        # ROI = (总营收 - 优惠成本) / 优惠成本
        roi = round((float(total_revenue) - total_discount_cost) / total_discount_cost, 2) if total_discount_cost > 0 else 0.0

        # 核销率
        redemption_rate = round(used_coupons / total_coupons * 100, 2) if total_coupons > 0 else 0.0

        # 按券类型分组
        type_q = _scope_coupon_usage(
            db.query(
                Coupon.coupon_type,
                func.count(CouponUsage.id).label("total"),
                func.coalesce(func.sum(CouponUsage.discount_amount), 0).label("cost"),
            ).join(
                Coupon, Coupon.id == CouponUsage.coupon_id
            ), current_user
        ).filter(
            CouponUsage.received_at >= start,
            CouponUsage.received_at < end,
            CouponUsage.status == CouponStatus.USED,
        ).group_by(Coupon.coupon_type).all()

        type_labels = {
            "fixed": "固定金额券",
            "percentage": "百分比折扣券",
            "free_charge": "免单券",
            "service_free": "免服务费券",
        }
        by_type = [
            {
                "coupon_type": row.coupon_type.value if row.coupon_type else "unknown",
                "type_name": type_labels.get(row.coupon_type.value if row.coupon_type else "", "其他"),
                "used_count": row.total,
                "total_cost": round(float(row.cost), 2),
            }
            for row in type_q
        ]

        return success_response({
            "summary": {
                "total_coupons_issued": total_coupons,
                "used_coupons": used_coupons,
                "expired_coupons": expired_coupons,
                "redemption_rate": redemption_rate,
                "coupon_orders": coupon_orders,
                "total_discount_cost": round(total_discount_cost, 2),
                "total_revenue": round(float(total_revenue), 2),
                "total_orders": total_orders,
                "roi": roi,
            },
            "by_type": by_type,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("analytics_coupon_effect 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
