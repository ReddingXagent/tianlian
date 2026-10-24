"""
营收统计 API - 按站点/时间维度的营收分析
GET /api/v1/operate/revenue/by-station — 按站点营收明细
GET /api/v1/operate/revenue/summary — 总营收概览
GET /api/v1/operate/revenue/daily-trend — 日趋势
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date

from app.core.database import get_db
from app.core.response import success_response
from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus
from app.models.station import Station
from app.models.order_fee_item import (
    OrderFeeItem, FeeType as OrderFeeType, RefundRecord, RefundStatus,
)
from app.models.coupon import Coupon, CouponUsage, CouponStatus
from app.models.pricing_v2 import TimeSlotDefinition
from app.models.spec_tables import RevenueDaily
from app.tasks.analytics_tasks import (
    build_revenue_daily,
    build_station_daily_metrics,
    _iter_target_dates,
)
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, require_platform_admin
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


# ── team scoping helper（任务卡 ab5c5f17）：营收统计全部源自充电订单/预聚合表，
#    经 station→team 归属。非 admin 仅统计本 team；admin 不过滤。──
def _scope_orders(q, user):
    if not is_platform_admin(user):
        return q.join(Station, ChargingOrder.station_id == Station.id) \
                .filter(Station.team_id == user.team_id)
    return q


def _scope_revenue_daily(q, user):
    if not is_platform_admin(user):
        return q.join(Station, RevenueDaily.station_id == Station.id) \
                .filter(Station.team_id == user.team_id)
    return q


def _scope_fee_items(q, user):
    if not is_platform_admin(user):
        return q.join(ChargingOrder, OrderFeeItem.order_id == ChargingOrder.id) \
                .join(Station, ChargingOrder.station_id == Station.id) \
                .filter(Station.team_id == user.team_id)
    return q


# ── 退款扣减口径（任务卡 a1e8299d）───
# 毛 paid 口径本端点原为 payment_status==PAID。真实退款流(order_fees.complete_refund)会把
# 全额退款订单置 REFUNDED、部分退款置 PARTIAL —— 若毛口径仍只算 PAID、再从毛里扣退款,
# 全额退款订单会被"既不算收入又扣一遍退款"双重扣减。故:
# 1. 毛 paid 口径扩为 PAID/PARTIAL/REFUNDING/REFUNDED(曾支付过的订单集合);
# 2. net_paid = gross_paid - ΣRefundRecord(status=REFUNDED).refund_amount;
# 3. 时间窗口: 退款按"关联订单 created_at"回溯过滤(而非 refunded_at) —— 营收按下单窗口
#    统计, 今日下单/次日退的退款归入下单窗口, 两侧口径才自洽对齐。
_PAID_LIKE = [
    OrderPaymentStatus.PAID, OrderPaymentStatus.PARTIAL,
    OrderPaymentStatus.REFUNDING, OrderPaymentStatus.REFUNDED,
]


def _refund_by_station(db, user, start_date, end_date):
    """当前 scope 内 [start,end) 下单窗口的按站点退款额(经关联订单回溯归属)。

    退款查询经 ChargingOrder→Station 走与营收相同的 _scope_orders team 过滤, 不串租户。
    """
    q = db.query(
        ChargingOrder.station_id,
        func.coalesce(func.sum(RefundRecord.refund_amount), 0).label("refund"),
    ).join(RefundRecord, RefundRecord.order_id == ChargingOrder.id).filter(
        RefundRecord.status == RefundStatus.REFUNDED,
        ChargingOrder.payment_status.in_(_PAID_LIKE),
    )
    q = _scope_orders(q, user)
    q = _range_filter(q, ChargingOrder.created_at, start_date, end_date)
    return {r.station_id: float(r.refund or 0) for r in q.group_by(ChargingOrder.station_id).all()}


@router.get("/revenue/summary", summary="营收概览")
def revenue_summary(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """营收统计总览 — 优先读 revenue_daily 预聚合表, 无覆盖时回退实时聚合。"""
    try:
        start_dt, end_dt = _range_datetimes(start_date, end_date)
        if _revenue_daily_covered(db, start_dt, end_dt):
            q = db.query(
                func.coalesce(func.sum(RevenueDaily.paid_revenue), 0).label("total_revenue"),
                func.coalesce(func.sum(RevenueDaily.energy_kwh), 0).label("total_kwh"),
                func.coalesce(func.sum(RevenueDaily.charge_fee), 0).label("total_electricity_fee"),
                func.coalesce(func.sum(RevenueDaily.service_fee), 0).label("total_service_fee"),
                func.coalesce(func.sum(RevenueDaily.parking_fee), 0).label("total_parking_fee"),
                func.coalesce(func.sum(RevenueDaily.reservation_fee), 0).label("total_reservation_fee"),
                func.coalesce(func.sum(RevenueDaily.orders_count), 0).label("total_orders"),
            )
            if start_dt:
                q = q.filter(RevenueDaily.record_date >= start_dt)
            if end_dt:
                q = q.filter(RevenueDaily.record_date < end_dt)
            q = _scope_revenue_daily(q, user)
            row = q.first()
            # 预聚合表无 discount/idle_penalty 列, 按同口径(COMPLETED+end_time)补查
            discount, idle = _supplemental_discount_idle(db, start_dt, end_dt, user)
            return success_response({
                "total_revenue": float(row.total_revenue or 0),
                "total_kwh": float(row.total_kwh or 0),
                "total_electricity_fee": float(row.total_electricity_fee or 0),
                "total_service_fee": float(row.total_service_fee or 0),
                "total_discount": discount,
                "total_parking_fee": float(row.total_parking_fee or 0),
                "total_idle_penalty": idle,
                "total_reservation_fee": float(row.total_reservation_fee or 0),
                "total_orders": row.total_orders or 0,
                "source": "pre_aggregated",
            })

        # 回退: 实时聚合(原口径 payment_status=PAID + created_at)
        # 口径提示: 预聚合路径基于 COMPLETED+end_time, 回退路径基于 PAID+created_at,
        # 时间基准与订单集合均不同 → 同参数在两路径下数值不可直接对比(如当日聚合 job 未跑)。
        logger.warning(
            "revenue_summary 走实时回退路径(PAID+created_at), 与预聚合口径(COMPLETED+end_time)不一致, "
            "区间内可能存在未聚合日, 跨日/跨路径对比请谨慎"
        )
        q = db.query(
            func.coalesce(func.sum(ChargingOrder.paid_amount), 0).label("total_revenue"),
            func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("total_kwh"),
            func.coalesce(func.sum(ChargingOrder.electricity_fee), 0).label("total_electricity_fee"),
            func.coalesce(func.sum(ChargingOrder.service_fee), 0).label("total_service_fee"),
            func.coalesce(func.sum(ChargingOrder.discount_amount), 0).label("total_discount"),
            func.count(ChargingOrder.id).label("total_orders"),
            func.coalesce(func.sum(ChargingOrder.parking_fee), 0).label("total_parking_fee"),
            func.coalesce(func.sum(ChargingOrder.idle_penalty), 0).label("total_idle_penalty"),
            func.coalesce(func.sum(ChargingOrder.reservation_fee), 0).label("total_reservation_fee"),
        ).filter(
            ChargingOrder.payment_status == OrderPaymentStatus.PAID,
        )
        q = _scope_orders(q, user)

        if start_date:
            q = q.filter(ChargingOrder.created_at >= start_date)
        if end_date:
            q = q.filter(ChargingOrder.created_at < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))

        row = q.first()
        return success_response({
            "total_revenue": float(row.total_revenue) if row else 0,
            "total_kwh": float(row.total_kwh) if row else 0,
            "total_electricity_fee": float(row.total_electricity_fee) if row else 0,
            "total_service_fee": float(row.total_service_fee) if row else 0,
            "total_discount": float(row.total_discount) if row else 0,
            "total_parking_fee": float(row.total_parking_fee) if row else 0,
            "total_idle_penalty": float(row.total_idle_penalty) if row else 0,
            "total_reservation_fee": float(row.total_reservation_fee) if row else 0,
            "total_orders": row.total_orders if row else 0,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("revenue_summary 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/revenue/by-station", summary="按站点营收明细")
def revenue_by_station(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按站点统计营收 - 参考易事特营收统计报表"""
    try:
        q = db.query(
            ChargingOrder.station_id,
            func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("total_kwh"),
            func.coalesce(func.sum(ChargingOrder.duration_minutes), 0).label("total_minutes"),
            func.coalesce(func.sum(ChargingOrder.electricity_fee), 0).label("total_electricity_fee"),
            func.coalesce(func.sum(ChargingOrder.service_fee), 0).label("total_service_fee"),
            func.coalesce(func.sum(ChargingOrder.discount_amount), 0).label("total_discount"),
            func.coalesce(func.sum(ChargingOrder.total_amount), 0).label("total_amount"),
            func.coalesce(func.sum(ChargingOrder.paid_amount), 0).label("total_paid"),
            func.count(ChargingOrder.id).label("order_count"),
            func.coalesce(func.sum(ChargingOrder.parking_fee), 0).label("total_parking_fee"),
            func.coalesce(func.sum(ChargingOrder.idle_penalty), 0).label("total_idle_penalty"),
        ).filter(
            # 卡 a1e8299d: 毛口径含曾支付订单(退款后订单离开 PAID 态), net_paid 在下方扣退款
            ChargingOrder.payment_status.in_(_PAID_LIKE),
        )
        q = _scope_orders(q, user)

        if start_date:
            q = q.filter(ChargingOrder.created_at >= start_date)
        if end_date:
            q = q.filter(ChargingOrder.created_at < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))

        rows = q.group_by(ChargingOrder.station_id).all()
        stations = {s.id: s for s in db.query(Station).all()}

        # 卡 a1e8299d: 同窗口/scope 退款额, net_paid = gross - refund
        refund_by_station = _refund_by_station(db, user, start_date, end_date)

        result = []
        for r in rows:
            station = stations.get(r.station_id)
            refund_amt = refund_by_station.get(r.station_id, 0.0)
            result.append({
                "station_id": r.station_id,
                "station_name": station.name if station else f"站点#{r.station_id}",
                "total_kwh": float(r.total_kwh),
                "total_hours": round(r.total_minutes / 60, 1) if r.total_minutes else 0,
                "total_electricity_fee": float(r.total_electricity_fee),
                "total_service_fee": float(r.total_service_fee),
                "total_discount": float(r.total_discount),
                "total_amount": float(r.total_amount),
                "total_paid": float(r.total_paid),
                "total_refund": round(refund_amt, 2),
                "net_paid": round(float(r.total_paid) - refund_amt, 2),
                "order_count": r.order_count,
                "total_parking_fee": float(r.total_parking_fee),
                "total_idle_penalty": float(r.total_idle_penalty),
            })

        return success_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("revenue_by_station 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/revenue/daily-trend", summary="日营收趋势")
def revenue_daily_trend(
    days: int = Query(30, ge=1, le=730, description="最近N天(边界1~730)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """最近N天的日营收趋势 — 优先读 revenue_daily 预聚合表(规避 cast(Date) 在 SQLite 的解析 bug)。"""
    try:
        start = datetime.now(timezone.utc) - timedelta(days=days)
        if _revenue_daily_covered(db, start, None):
            _q = (
                db.query(
                    RevenueDaily.record_date,
                    func.coalesce(func.sum(RevenueDaily.paid_revenue), 0).label("revenue"),
                    func.coalesce(func.sum(RevenueDaily.energy_kwh), 0).label("kwh"),
                    func.coalesce(func.sum(RevenueDaily.orders_count), 0).label("orders"),
                )
                .filter(RevenueDaily.record_date >= start)
            )
            _q = _scope_revenue_daily(_q, user)
            rows = _q.group_by(RevenueDaily.record_date).order_by(RevenueDaily.record_date).all()
            return success_response([
                {
                    "date": r.record_date.strftime("%Y-%m-%d"),
                    "revenue": float(r.revenue),
                    "kwh": float(r.kwh),
                    "orders": r.orders,
                }
                for r in rows
            ])

        # 回退: 实时聚合(端点 cast(Date) 在 SQLite 下 result-row 解析有 bug, 见 xfail 测试)
        _q = db.query(
            cast(ChargingOrder.created_at, Date).label("day"),
            func.coalesce(func.sum(ChargingOrder.paid_amount), 0).label("revenue"),
            func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("kwh"),
            func.count(ChargingOrder.id).label("orders"),
        ).filter(
            ChargingOrder.payment_status == OrderPaymentStatus.PAID,
            ChargingOrder.created_at >= start,
        )
        _q = _scope_orders(_q, user)
        rows = _q.group_by(cast(ChargingOrder.created_at, Date)).order_by("day").all()

        result = []
        for r in rows:
            result.append({
                "date": str(r.day),
                "revenue": float(r.revenue),
                "kwh": float(r.kwh),
                "orders": r.orders,
            })

        return success_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("revenue_daily_trend 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/revenue/export", summary="导出营收报表")
def revenue_export(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """导出营收统计报表（同by-station格式，方便导出为CSV/Excel）"""
    try:
        return revenue_by_station(start_date, end_date, db, user)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("revenue_export 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ================= 运营分析深化 (Phase43) =================
# 五项费用（聚合时排除 discount/coupon/points 等抵扣项）
_FEE_TYPES = [
    OrderFeeType.ELECTRICITY, OrderFeeType.SERVICE, OrderFeeType.PARKING,
    OrderFeeType.OCCUPANCY, OrderFeeType.RESERVATION,
]
_FEE_KEYS = ["electricity", "service", "parking", "occupancy", "reservation"]


def _range_filter(query, col, start_date: Optional[str], end_date: Optional[str]):
    """应用 [start_date, end_date+1天) 半开区间过滤，与现有端点口径一致。"""
    if start_date:
        query = query.filter(col >= start_date)
    if end_date:
        query = query.filter(col < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
    return query


# ================= 预聚合表优先读取 (revenue_daily) =================
def _range_datetimes(start_date: Optional[str], end_date: Optional[str]):
    """字符串日期 → (start_dt, end_dt) 半开区间上界; None 表示不限。"""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
    end_dt = (
        datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        if end_date else None
    )
    return start_dt, end_dt


def _revenue_daily_covered(db: Session, start_dt, end_dt) -> bool:
    """预聚合表在 [start_dt, end_dt) 是否有数据(决定是否走预聚合快路径)。"""
    q = db.query(func.count(RevenueDaily.id))
    if start_dt:
        q = q.filter(RevenueDaily.record_date >= start_dt)
    if end_dt:
        q = q.filter(RevenueDaily.record_date < end_dt)
    return (q.scalar() or 0) > 0


def _supplemental_discount_idle(db: Session, start_dt, end_dt, user):
    """预聚合表无 discount/idle_penalty 列, 按同口径(COMPLETED+PAID+end_time)补查, 返回 (discount, idle)。

    口径对齐: total_revenue 取自 revenue_daily.paid_revenue(实付口径, 仅含已支付金额),
    故 discount/idle 亦须限定 payment_status==PAID —— 否则已完成未支付订单的折扣/占桩费
    会混入"已收营收"同屏指标, 造成折扣虚高、报表不自洽。
    """
    q = db.query(
        func.coalesce(func.sum(ChargingOrder.discount_amount), 0).label("discount"),
        func.coalesce(func.sum(ChargingOrder.idle_penalty), 0).label("idle"),
    ).filter(
        ChargingOrder.order_status == OrderStatus.COMPLETED,
        ChargingOrder.payment_status == OrderPaymentStatus.PAID,
    )
    q = _scope_orders(q, user)
    if start_dt:
        q = q.filter(ChargingOrder.end_time >= start_dt)
    if end_dt:
        q = q.filter(ChargingOrder.end_time < end_dt)
    r = q.first()
    return float(r.discount or 0), float(r.idle or 0)


@router.get("/revenue/fee-breakdown", summary="费用占比分析(按月趋势)")
def revenue_fee_breakdown(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """五项费用(充电费/服务费/停车费/占桩费/预约费)占比与按月趋势。

    数据源: order_fee_items 按 fee_type 聚合。
    月度分组在 Python 层完成，规避 cast(Date) 在 SQLite 下的解析问题。
    """
    try:
        q = _range_filter(
            db.query(OrderFeeItem.created_at, OrderFeeItem.fee_type, OrderFeeItem.amount)
            .filter(OrderFeeItem.fee_type.in_(_FEE_TYPES)),
            OrderFeeItem.created_at, start_date, end_date,
        )
        q = _scope_fee_items(q, user)
        monthly = defaultdict(lambda: defaultdict(float))   # {month: {fee_key: amount}}
        summary = defaultdict(float)                        # {fee_key: amount}
        for created_at, fee_type, amount in q.all():
            month = created_at.strftime("%Y-%m")
            key = fee_type.value
            val = float(amount or 0)
            monthly[month][key] += val
            summary[key] += val

        total = sum(summary.values())
        trends = [
            {
                "month": m,
                "fees": {k: round(monthly[m].get(k, 0), 2) for k in _FEE_KEYS},
                "total": round(sum(monthly[m].values()), 2),
            }
            for m in sorted(monthly.keys())
        ]
        ratios = {k: round(summary[k] / total, 4) for k in _FEE_KEYS} if total else {k: 0 for k in _FEE_KEYS}
        return success_response({
            "trends": trends,
            "summary": {k: round(summary[k], 2) for k in _FEE_KEYS},
            "total": round(total, 2),
            "ratios": ratios,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("revenue_fee_breakdown 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/revenue/by-user-type", summary="用户类型收入分析")
def revenue_by_user_type(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """各用户类型(APP/卡/VIN/互联互通/企业)营收贡献、户均消费、复充率。

    数据源: charging_orders 按 user_type 聚合。
    按 user_type 实际值动态分组(不硬编码类型)，枚举扩展无需改代码。
    复充率 = 下单≥2次的去重用户数 / 该类型去重用户数。
    """
    try:
        orders = _scope_orders(
            _range_filter(
                db.query(ChargingOrder).filter(ChargingOrder.payment_status == OrderPaymentStatus.PAID),
                ChargingOrder.created_at, start_date, end_date,
            ),
            user,
        ).all()

        by_type = defaultdict(list)
        for o in orders:
            by_type[(o.user_type.value if o.user_type else "unknown")].append(o)

        result = []
        for ut, ords in by_type.items():
            revenue = sum(float(o.paid_amount or 0) for o in ords)
            order_cnt = defaultdict(int)
            for o in ords:
                if o.user_id is not None:
                    order_cnt[o.user_id] += 1
            users = len(order_cnt)
            repeat_users = sum(1 for c in order_cnt.values() if c >= 2)
            result.append({
                "user_type": ut,
                "revenue": round(revenue, 2),
                "kwh": round(sum(float(o.charged_kwh or 0) for o in ords), 2),
                "orders": len(ords),
                "users": users,
                "avg_per_user": round(revenue / users, 2) if users else 0,
                "repeat_rate": round(repeat_users / users, 4) if users else 0,
            })
        return success_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("revenue_by_user_type 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/revenue/by-time-period", summary="时段收益分析(尖/峰/平/谷)")
def revenue_by_time_period(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """尖/峰/平/谷各时段电量分布、电价贡献、服务费占比。

    时段电量取自 charging_orders 的分时电量字段(peak/flat/valley/trough)。
    注: order_fee_items 无时段字段、time_slot_definitions 仅是模板，
        故电量分布以订单分时字段为准；时段元信息(名称)取自 TimeSlotDefinition。
    """
    try:
        q = _range_filter(
            db.query(
                func.coalesce(func.sum(ChargingOrder.peak_energy), 0).label("peak"),
                func.coalesce(func.sum(ChargingOrder.flat_energy), 0).label("flat"),
                func.coalesce(func.sum(ChargingOrder.valley_energy), 0).label("valley"),
                func.coalesce(func.sum(ChargingOrder.trough_energy), 0).label("trough"),
                func.coalesce(func.sum(ChargingOrder.electricity_fee), 0).label("efee"),
                func.coalesce(func.sum(ChargingOrder.service_fee), 0).label("sfee"),
            ).filter(ChargingOrder.payment_status == OrderPaymentStatus.PAID),
            ChargingOrder.created_at, start_date, end_date,
        )
        q = _scope_orders(q, user)
        r = q.first()
        energy = {
            "peak": float(r.peak or 0), "shoulder": 0.0,      # 订单无独立峰段字段
            "flat": float(r.flat or 0), "valley": float(r.valley or 0),
            "trough": float(r.trough or 0),
        }
        efee, sfee = float(r.efee or 0), float(r.sfee or 0)
        total_energy = sum(energy.values())

        slot_label = {s.period_type.value: s.name for s in
                      db.query(TimeSlotDefinition).filter(TimeSlotDefinition.is_active.is_(True)).all()}
        labels = {"peak": "尖", "shoulder": "峰", "flat": "平", "valley": "谷", "trough": "深谷"}
        periods = [
            {
                "period": k,
                "label": slot_label.get(k, labels[k]),
                "energy": round(energy[k], 2),
                "ratio": round(energy[k] / total_energy, 4) if total_energy else 0,
            }
            for k in ["peak", "shoulder", "flat", "valley", "trough"]
        ]
        total_fee = efee + sfee
        return success_response({
            "periods": periods,
            "total_energy": round(total_energy, 2),
            "electricity_fee": round(efee, 2),
            "service_fee": round(sfee, 2),
            "service_fee_ratio": round(sfee / total_fee, 4) if total_fee else 0,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("revenue_by_time_period 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/revenue/coupon-effectiveness", summary="优惠券效果分析")
def revenue_coupon_effectiveness(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """券核销率、增量订单数、优惠成本 vs 营收增长、ROI。

    数据源: coupons + coupon_usages + charging_orders。
    - 核销率 = 已核销 / 已发放
    - 优惠成本 = 已核销券的抵扣金额合计
    - 增量订单数 = 已核销券关联的订单数(无对照组，以此为增量近似)
    - ROI = 关联订单实付营收 / 优惠成本
    """
    try:
        _uq = _range_filter(
            db.query(CouponUsage), CouponUsage.created_at, start_date, end_date,
        )
        # team scoping（任务卡 ab5c5f17）：券使用记录按领取用户归属过滤，非 admin 仅本 team 用户。
        if not is_platform_admin(user):
            _uq = _uq.join(User, CouponUsage.user_id == User.id).filter(User.team_id == user.team_id)
        usages = _uq.all()
        coupon_name = {c.id: c.name for c in db.query(Coupon).all()}

        # 过期派生（卡 ea373b3a）: 与 /coupon/usages 响应层口径对齐（卡 73d52e60）——
        # 多数过期券停在 DB ACTIVE（响应层派生不回写），按 DB EXPIRED 统计会系统性
        # 低估 expired、高估 active。Python 层派生而非 SQL CASE：usages 已全量在内存，
        # 且与 coupon_api 逐字共享"naive→UTC 补齐 + 严格小于"语义（== now 不算过期）。
        _now = datetime.now(timezone.utc)

        def _derived_status(u: CouponUsage) -> CouponStatus:
            if u.status == CouponStatus.ACTIVE:
                _exp = u.expires_at
                if _exp is not None and _exp.tzinfo is None:
                    _exp = _exp.replace(tzinfo=timezone.utc)
                if _exp is not None and _exp < _now:
                    return CouponStatus.EXPIRED
            return u.status

        by_coupon = defaultdict(list)
        for u in usages:
            by_coupon[u.coupon_id].append(u)

        coupons_out, tot_issued, tot_used, tot_cost, tot_rev = [], 0, 0, 0.0, 0.0
        for cid, items in by_coupon.items():
            used_items = [u for u in items if u.status == CouponStatus.USED]
            cost = sum(float(u.discount_amount or 0) for u in used_items)
            order_ids = [u.order_id for u in used_items if u.order_id]
            rev = float(db.query(func.coalesce(func.sum(ChargingOrder.paid_amount), 0))
                        .filter(ChargingOrder.id.in_(order_ids)).scalar() or 0) if order_ids else 0.0
            issued, used = len(items), len(used_items)
            tot_issued += issued
            tot_used += used
            tot_cost += cost
            tot_rev += rev
            derived = [_derived_status(u) for u in items]
            coupons_out.append({
                "coupon_id": cid,
                "name": coupon_name.get(cid, f"券#{cid}"),
                "issued": issued,
                "used": used,
                "expired": sum(1 for s in derived if s == CouponStatus.EXPIRED),
                "active": sum(1 for s in derived if s == CouponStatus.ACTIVE),
                "redemption_rate": round(used / issued, 4) if issued else 0,
                "discount_cost": round(cost, 2),
                "order_revenue": round(rev, 2),
                "incremental_orders": used,
                "roi": round(rev / cost, 4) if cost else 0,
            })
        return success_response({
            "coupons": coupons_out,
            "summary": {
                "total_issued": tot_issued,
                "total_used": tot_used,
                "overall_redemption_rate": round(tot_used / tot_issued, 4) if tot_issued else 0,
                "total_discount_cost": round(tot_cost, 2),
                "total_order_revenue": round(tot_rev, 2),
                "overall_roi": round(tot_rev / tot_cost, 4) if tot_cost else 0,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("revenue_coupon_effectiveness 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ================= 手动触发补算 (支持指定日期 / 区间) =================
@router.post("/revenue/aggregate", summary="手动触发营收日报聚合(支持区间补算)")
def trigger_revenue_aggregate(
    target_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD, 缺省=昨日"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD, 含当日"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    """同步执行 revenue_daily 聚合; 无 Celery worker 时也可手动补算。

    取 analytics_tasks._iter_target_dates 解析 [target_date, end_date] 闭区间。
    """
    try:
        dates = _iter_target_dates(target_date, end_date)
        if not dates:
            raise HTTPException(status_code=400, detail="日期格式错误或区间为空")
        results = [build_revenue_daily(db, d) for d in dates]
        db.commit()
        return success_response({
            "status": "completed",
            "dates": dates,
            "results": results,
            "orders": sum(r.get("orders", 0) for r in results),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("trigger_revenue_aggregate 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/station-metrics/aggregate", summary="手动触发站点日报聚合(支持区间补算)")
def trigger_station_metrics_aggregate(
    target_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD, 缺省=昨日"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD, 含当日"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    """同步执行 station_daily_metrics 聚合; 无 Celery worker 时也可手动补算。"""
    try:
        dates = _iter_target_dates(target_date, end_date)
        if not dates:
            raise HTTPException(status_code=400, detail="日期格式错误或区间为空")
        results = [build_station_daily_metrics(db, d) for d in dates]
        db.commit()
        return success_response({
            "status": "completed",
            "dates": dates,
            "results": results,
            "stations": sum(r.get("stations", 0) for r in results),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("trigger_station_metrics_aggregate 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
