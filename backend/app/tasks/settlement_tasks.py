"""
运营结算对账自动化定时任务

- settlement_daily: 每日凌晨1点，前一日已完成订单汇总 → daily_settlements
- settlement_reconcile: 每日凌晨1:30，支付对账比对 → payment_reconciliation
"""
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from celery import shared_task
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.order_fee_item import RefundRecord, RefundStatus
from app.models.ops_settlement.daily_settlement import DailySettlement, SettlementStatus
from app.models.ops_settlement.payment_reconciliation import PaymentReconciliation, ReconciliationStatus
from app.tasks._soft_timeout import SoftTimeLimitExceeded  # 卡 411936df
from app.tasks.tz_utils import biz_day_bounds_utc_naive, yesterday_in_biz_tz

logger = logging.getLogger(__name__)


def build_daily_settlement(db: Session, target_date: str) -> Dict[str, Any]:
    """
    汇总指定日期已完成订单 → daily_settlements
    幂等键: settlement_date + station_id (NULL=全平台)
    """
    try:
        target = date.fromisoformat(target_date)
    except (ValueError, TypeError):
        return {"status": "error", "error": f"日期格式错误: {target_date}"}

    # 卡 f7422bbc: 业务日边界换算为 UTC-naive 窗口 (与 naive-UTC 落库口径对齐),
    # 上海 00:00-08:00 结束的订单不再错归前一日。
    day_start, day_end = biz_day_bounds_utc_naive(target)

    # 聚合已完成订单
    row = (
        db.query(
            func.count(ChargingOrder.id).label("total_orders"),
            func.sum(ChargingOrder.charged_kwh).label("total_energy"),
            func.sum(ChargingOrder.electricity_fee).label("total_charge_fee"),
            func.sum(ChargingOrder.service_fee).label("total_service_fee"),
            func.sum(ChargingOrder.parking_fee).label("total_parking_fee"),
            func.sum(ChargingOrder.occupancy_fee).label("total_occupancy_fee"),
            func.sum(ChargingOrder.reservation_fee).label("total_reservation_fee"),
            func.sum(ChargingOrder.total_amount).label("total_amount"),
            func.sum(ChargingOrder.paid_amount).label("total_paid"),
            func.sum(ChargingOrder.discount_amount).label("total_discount"),
            func.sum(ChargingOrder.coupon_amount).label("total_coupon"),
            func.sum(ChargingOrder.points_amount).label("total_points"),
        )
        .filter(
            ChargingOrder.order_status == OrderStatus.COMPLETED,
            ChargingOrder.end_time >= day_start,
            ChargingOrder.end_time < day_end,
        )
        .one()
    )

    total_orders = row.total_orders or 0
    if total_orders == 0:
        return {"status": "completed", "message": "当日无已完成订单", "orders": 0}

    total_amount = Decimal(str(row.total_amount or 0))
    total_paid = Decimal(str(row.total_paid or 0))
    total_discount = Decimal(str(row.total_discount or 0))
    total_coupon = Decimal(str(row.total_coupon or 0))
    total_points = Decimal(str(row.total_points or 0))

    # 退款: 当日已到账退款 (status=REFUNDED 且 refunded_at 落在 [day_start, day_end))
    # 口径与 end_time 同为 naive-UTC 落库, 沿用同一业务日 UTC-naive 窗口
    refund_row = (
        db.query(func.coalesce(func.sum(RefundRecord.refund_amount), 0))
        .filter(
            RefundRecord.status == RefundStatus.REFUNDED,
            RefundRecord.refunded_at >= day_start,
            RefundRecord.refunded_at < day_end,
        )
        .one()
    )
    total_refund = Decimal(str(refund_row[0] or 0))

    # 幂等: 唯一约束 uq_ds_date_station (settlement_date, station_key) 支撑的
    # 原子 upsert (卡 97c83af9)。先查快路径, 插入撞约束则回查转覆盖, 消除
    # celery 并发 worker 下 check-then-act 竞态插重复行。
    def _fetch_existing() -> Optional[DailySettlement]:
        return (
            db.query(DailySettlement)
            .filter(
                DailySettlement.settlement_date == target,
                DailySettlement.station_id.is_(None),
            )
            .first()
        )

    existing = _fetch_existing()

    values = dict(
        total_orders=total_orders,
        total_energy_kwh=Decimal(str(row.total_energy or 0)),
        total_charge_fee=Decimal(str(row.total_charge_fee or 0)),
        total_service_fee=Decimal(str(row.total_service_fee or 0)),
        total_parking_fee=Decimal(str(row.total_parking_fee or 0)),
        total_occupancy_fee=Decimal(str(row.total_occupancy_fee or 0)),
        total_reservation_fee=Decimal(str(row.total_reservation_fee or 0)),
        total_amount=total_amount,
        total_paid=total_paid,
        total_discount=total_discount,
        total_coupon=total_coupon,
        total_points=total_points,
        total_refund=total_refund,
    )

    # 无差异自动确认: 应收 == 净实收(毛实付-已退) + 优惠
    # paid_amount 为毛实付(支付侧不核减), 退款从实收侧扣减, 否则有退款当日恒失衡折 PENDING
    expected = (total_paid - total_refund) + total_discount + total_coupon + total_points
    auto_confirm = abs(float(total_amount - expected)) < 0.01

    if existing:
        for k, v in values.items():
            setattr(existing, k, v)
        if auto_confirm and existing.status == SettlementStatus.PENDING:
            existing.status = SettlementStatus.CONFIRMED
            existing.confirmed_at = datetime.now(timezone.utc)
            existing.confirmed_by = "system_auto"
    else:
        settlement = DailySettlement(
            settlement_date=target,
            station_id=None,
            status=SettlementStatus.CONFIRMED if auto_confirm else SettlementStatus.PENDING,
            confirmed_at=datetime.now(timezone.utc) if auto_confirm else None,
            confirmed_by="system_auto" if auto_confirm else None,
            **values,
        )
        db.add(settlement)
        try:
            db.flush()
        except IntegrityError:
            # 并发 worker 已插入同 (date, station=NULL) 行 → 回退覆盖语义
            db.rollback()
            winner = _fetch_existing()
            for k, v in values.items():
                setattr(winner, k, v)
            if auto_confirm and winner.status == SettlementStatus.PENDING:
                winner.status = SettlementStatus.CONFIRMED
                winner.confirmed_at = datetime.now(timezone.utc)
                winner.confirmed_by = "system_auto"

    db.flush()
    logger.info("[settlement] 日结: date=%s orders=%d amount=%.2f auto_confirm=%s",
                target_date, total_orders, float(total_amount), auto_confirm)
    return {
        "status": "completed",
        "orders": total_orders,
        "total_amount": float(total_amount),
        "auto_confirmed": auto_confirm,
        "date": target_date,
    }


def reconcile_payments(db: Session, target_date: str) -> Dict[str, Any]:
    """
    支付对账: 按支付渠道比对平台订单 vs 渠道流水
    幂等键: settlement_date + payment_channel
    """
    try:
        target = date.fromisoformat(target_date)
    except (ValueError, TypeError):
        return {"status": "error", "error": f"日期格式错误: {target_date}"}

    # 卡 f7422bbc: 同 build_daily_settlement, 业务日 UTC-naive 窗口。
    day_start, day_end = biz_day_bounds_utc_naive(target)

    # 按支付渠道聚合
    rows = (
        db.query(
            ChargingOrder.payment_method,
            func.count(ChargingOrder.id).label("orders_count"),
            func.sum(ChargingOrder.paid_amount).label("total_paid"),
        )
        .filter(
            ChargingOrder.order_status == OrderStatus.COMPLETED,
            ChargingOrder.end_time >= day_start,
            ChargingOrder.end_time < day_end,
            ChargingOrder.payment_method.isnot(None),
        )
        .group_by(ChargingOrder.payment_method)
        .all()
    )

    reconciled_count = 0
    for row in rows:
        channel = row.payment_method.value if hasattr(row.payment_method, 'value') else str(row.payment_method)
        platform_count = row.orders_count or 0
        platform_amount = Decimal(str(row.total_paid or 0))

        # 当前无外部支付渠道API对接，模拟渠道数据=平台数据（差异为0）
        payment_count = platform_count
        payment_amount = platform_amount
        diff_count = 0
        diff_amount = Decimal("0")

        def _fetch_existing_recon() -> Optional[PaymentReconciliation]:
            return (
                db.query(PaymentReconciliation)
                .filter(
                    PaymentReconciliation.settlement_date == target,
                    PaymentReconciliation.payment_channel == channel,
                )
                .first()
            )

        existing = _fetch_existing_recon()

        values = dict(
            platform_orders_count=platform_count,
            platform_amount=platform_amount,
            payment_orders_count=payment_count,
            payment_amount=payment_amount,
            difference_count=diff_count,
            difference_amount=diff_amount,
            difference_detail=None if diff_count == 0 else f"差异{diff_count}笔/{diff_amount}元",
        )

        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            if diff_count == 0 and existing.status == ReconciliationStatus.PENDING:
                existing.status = ReconciliationStatus.RECONCILED
                existing.reconciled_at = datetime.now(timezone.utc)
                existing.reconciled_by = "system_auto"
        else:
            recon = PaymentReconciliation(
                settlement_date=target,
                payment_channel=channel,
                status=ReconciliationStatus.RECONCILED if diff_count == 0 else ReconciliationStatus.PENDING,
                reconciled_at=datetime.now(timezone.utc) if diff_count == 0 else None,
                reconciled_by="system_auto" if diff_count == 0 else None,
                **values,
            )
            db.add(recon)
            try:
                db.flush()
            except IntegrityError:
                # 并发 worker 已插入同 (date, channel) 行 → 回退覆盖语义
                db.rollback()
                winner = _fetch_existing_recon()
                for k, v in values.items():
                    setattr(winner, k, v)
                if diff_count == 0 and winner.status == ReconciliationStatus.PENDING:
                    winner.status = ReconciliationStatus.RECONCILED
                    winner.reconciled_at = datetime.now(timezone.utc)
                    winner.reconciled_by = "system_auto"
        reconciled_count += 1

    db.flush()
    logger.info("[settlement] 对账: date=%s channels=%d", target_date, reconciled_count)
    return {"status": "completed", "channels_reconciled": reconciled_count, "date": target_date}


@shared_task(name="settlement.daily", bind=True, max_retries=2, default_retry_delay=60)
def settlement_daily(self, target_date: Optional[str] = None) -> Dict[str, Any]:
    """每日结算任务"""
    if target_date is None:
        # 卡 c42ac99a: beat 按上海 01:00 触发 (= UTC 前日 17:00), date.today() 在 UTC
        # 容器取到前日 → 错算"上海前天"。改用业务时区昨日。
        target_date = yesterday_in_biz_tz().isoformat()
    logger.info("[settlement] 开始日结: %s", target_date)
    db = SessionLocal()
    try:
        result = build_daily_settlement(db, target_date)
        db.commit()
        return result
    except SoftTimeLimitExceeded:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error("[settlement] 日结失败: %s", e, exc_info=True)
        raise self.retry(exc=e)
    finally:
        db.close()


@shared_task(name="settlement.reconcile", bind=True, max_retries=2, default_retry_delay=60)
def settlement_reconcile(self, target_date: Optional[str] = None) -> Dict[str, Any]:
    """每日支付对账任务"""
    if target_date is None:
        # 卡 c42ac99a: 同 settlement_daily, 业务时区昨日 (见上方注释)。
        target_date = yesterday_in_biz_tz().isoformat()
    logger.info("[settlement] 开始对账: %s", target_date)
    db = SessionLocal()
    try:
        result = reconcile_payments(db, target_date)
        db.commit()
        return result
    except SoftTimeLimitExceeded:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error("[settlement] 对账失败: %s", e, exc_info=True)
        raise self.retry(exc=e)
    finally:
        db.close()
