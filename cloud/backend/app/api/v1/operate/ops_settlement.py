"""
运营结算对账 API - SPEC §2.7

日结汇总 / 支付对账 / 互联互通结算
统一挂载在 /api/v1/operate/settlement 前缀下
"""
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response
from app.models.ops_settlement import (
    DailySettlement, SettlementStatus,
    PaymentReconciliation, ReconciliationStatus,
    InterconnectSettlement, InterconnectSettlementStatus,
)
from app.models.station import Station
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, require_platform_admin, assert_station_team_access
from app.middleware.permission import require_permission
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


# ========== Schemas ==========


class DailySettlementGenerate(BaseModel):
    settlement_date: date
    station_id: Optional[int] = None
    total_orders: int = 0
    total_energy_kwh: Decimal = Field(default=Decimal("0"), ge=0)
    total_charge_fee: Decimal = Field(default=Decimal("0"), ge=0)
    total_service_fee: Decimal = Field(default=Decimal("0"), ge=0)
    total_parking_fee: Decimal = Field(default=Decimal("0"), ge=0)
    total_occupancy_fee: Decimal = Field(default=Decimal("0"), ge=0)
    total_reservation_fee: Decimal = Field(default=Decimal("0"), ge=0)
    total_amount: Decimal = Field(default=Decimal("0"), ge=0)
    total_paid: Decimal = Field(default=Decimal("0"), ge=0)
    total_discount: Decimal = Field(default=Decimal("0"), ge=0)
    total_coupon: Decimal = Field(default=Decimal("0"), ge=0)
    total_points: Decimal = Field(default=Decimal("0"), ge=0)
    total_refund: Decimal = Field(default=Decimal("0"), ge=0)
    remark: Optional[str] = None


class ReconciliationCreate(BaseModel):
    settlement_date: date
    payment_channel: str = Field(..., max_length=50)
    platform_orders_count: int = 0
    platform_amount: Decimal = Field(Decimal("0"), ge=0)
    payment_orders_count: int = Field(0, ge=0)
    payment_amount: Decimal = Field(Decimal("0"), ge=0)
    difference_count: int = 0
    difference_amount: Decimal = Field(Decimal("0"))
    difference_detail: Optional[str] = None
    remark: Optional[str] = None


class ReconcileRecord(BaseModel):
    operator: str = "admin"
    difference_detail: Optional[str] = None


class InterconnectSettlementCreate(BaseModel):
    platform_id: str = Field(..., max_length=100)
    platform_name: Optional[str] = None
    start_date: date
    end_date: date
    total_orders: int = 0
    total_energy_kwh: Decimal = Field(Decimal("0"), ge=0)
    total_amount: Decimal = Field(Decimal("0"), ge=0)
    revenue_share_ratio: Decimal = Decimal("0.7")
    remark: Optional[str] = None


class InterconnectSettle(BaseModel):
    operator: str = "admin"


# ==================== 日结汇总 ====================

@router.get("/settlement/daily", summary="日结汇总列表")
def list_daily_settlements(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    station_id: Optional[int] = Query(None, description="站点ID"),
    status: Optional[str] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取日结汇总列表"""
    try:
        q = db.query(DailySettlement)
        # team scoping（任务卡 ab5c5f17）：日结经 station→team，非 admin 仅返回本 team 站点的日结（NULL station 的平台级记录不含）。
        if not is_platform_admin(user):
            q = q.join(Station, DailySettlement.station_id == Station.id).filter(Station.team_id == user.team_id)
        if start_date:
            q = q.filter(DailySettlement.settlement_date >= start_date)
        if end_date:
            q = q.filter(DailySettlement.settlement_date <= end_date)
        if station_id:
            q = q.filter(DailySettlement.station_id == station_id)
        if status:
            q = q.filter(DailySettlement.status == status)

        total = q.count()
        items = q.order_by(DailySettlement.settlement_date.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()

        return success_response({
            "items": [_ds_to_dict(s) for s in items],
            "total": total, "page": page, "page_size": page_size,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_daily_settlements 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/settlement/daily/{settlement_id}", summary="日结汇总详情")
def get_daily_settlement(settlement_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        s = db.query(DailySettlement).filter(DailySettlement.id == settlement_id).first()
        if not s:
            raise HTTPException(status_code=404, detail="日结记录不存在")
        # team scoping（任务卡 ab5c5f17）：日结经 station→team；station_id 缺失视为平台级记录，仅 admin 可见。
        if s.station_id is not None:
            assert_station_team_access(db, s.station_id, user)
        elif not is_platform_admin(user):
            raise HTTPException(status_code=404, detail="日结记录不存在")
        return success_response(_ds_to_dict(s))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_daily_settlement 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/settlement/daily/generate", summary="生成日结汇总")
def generate_daily_settlement(
    body: DailySettlementGenerate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    """手动生成日结汇总记录"""
    try:
        settlement_date = body.settlement_date
        station_id = body.station_id

        existing = db.query(DailySettlement).filter(
            DailySettlement.settlement_date == settlement_date,
            DailySettlement.station_id == station_id if station_id else DailySettlement.station_id.is_(None)
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="该日期的日结记录已存在")

        record = DailySettlement(
            settlement_date=settlement_date,
            station_id=station_id,
            total_orders=body.total_orders,
            total_energy_kwh=body.total_energy_kwh,
            total_charge_fee=body.total_charge_fee,
            total_service_fee=body.total_service_fee,
            total_parking_fee=body.total_parking_fee,
            total_occupancy_fee=body.total_occupancy_fee,
            total_reservation_fee=body.total_reservation_fee,
            total_amount=body.total_amount,
            total_paid=body.total_paid,
            total_discount=body.total_discount,
            total_coupon=body.total_coupon,
            total_points=body.total_points,
            total_refund=body.total_refund,
            status=SettlementStatus.PENDING,
            remark=body.remark,
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            # 卡 97c83af9: 唯一约束兜底, 并发生成撞 uq_ds_date_station → 400 而非 500
            db.rollback()
            raise HTTPException(status_code=400, detail="该日期的日结记录已存在")
        db.refresh(record)
        return success_response(_ds_to_dict(record), "日结记录已生成")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_daily_settlement 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/settlement/daily/{settlement_id}/confirm", summary="确认日结")
def confirm_daily_settlement(
    settlement_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _=Depends(require_permission("operate:manage")),
):
    try:
        s = db.query(DailySettlement).filter(DailySettlement.id == settlement_id).first()
        if not s:
            raise HTTPException(status_code=404, detail="日结记录不存在")
        # team scoping（任务卡 ab5c5f17）：日结经 station→team；station_id 缺失视为平台级记录，仅 admin 可操作。
        if s.station_id is not None:
            assert_station_team_access(db, s.station_id, user)
        elif not is_platform_admin(user):
            raise HTTPException(status_code=404, detail="日结记录不存在")
        if s.status != SettlementStatus.PENDING:
            raise HTTPException(status_code=400, detail=f"只有待确认状态可确认, 当前: {s.status.value}")
        s.status = SettlementStatus.CONFIRMED
        s.confirmed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(s)
        return success_response(_ds_to_dict(s), "日结已确认")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("confirm_daily_settlement 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ==================== 支付对账 ====================

@router.get("/settlement/reconciliation", summary="支付对账列表")
def list_reconciliations(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    payment_channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    try:
        q = db.query(PaymentReconciliation)
        if start_date:
            q = q.filter(PaymentReconciliation.settlement_date >= start_date)
        if end_date:
            q = q.filter(PaymentReconciliation.settlement_date <= end_date)
        if payment_channel:
            q = q.filter(PaymentReconciliation.payment_channel == payment_channel)
        if status:
            q = q.filter(PaymentReconciliation.status == status)

        total = q.count()
        items = q.order_by(PaymentReconciliation.settlement_date.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()

        return success_response({
            "items": [_pr_to_dict(r) for r in items],
            "total": total, "page": page, "page_size": page_size,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_reconciliations 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/settlement/reconciliation", summary="创建对账记录")
def create_reconciliation(body: ReconciliationCreate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        record = PaymentReconciliation(
            settlement_date=body.settlement_date,
            payment_channel=body.payment_channel,
            platform_orders_count=body.platform_orders_count,
            platform_amount=body.platform_amount,
            payment_orders_count=body.payment_orders_count,
            payment_amount=body.payment_amount,
            difference_count=body.difference_count,
            difference_amount=body.difference_amount,
            difference_detail=body.difference_detail,
            remark=body.remark,
            status=ReconciliationStatus.PENDING,
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            # 卡 97c83af9: 并发创建撞 uq_pr_date_channel → 400 而非 500
            db.rollback()
            raise HTTPException(status_code=400, detail="该日期+渠道的对账记录已存在")
        db.refresh(record)
        return success_response(_pr_to_dict(record), "对账记录已创建")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_reconciliation 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/settlement/reconciliation/{rec_id}/reconcile", summary="完成对账")
def reconcile_record(rec_id: int, body: ReconcileRecord, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        r = db.query(PaymentReconciliation).filter(PaymentReconciliation.id == rec_id).first()
        if not r:
            raise HTTPException(status_code=404, detail="对账记录不存在")
        if r.status != ReconciliationStatus.PENDING:
            raise HTTPException(status_code=400, detail="该记录已对账")
        r.status = ReconciliationStatus.RECONCILED
        r.reconciled_at = datetime.now(timezone.utc)
        r.reconciled_by = body.operator
        if body.difference_detail is not None:
            r.difference_detail = body.difference_detail
        db.commit()
        db.refresh(r)
        return success_response(_pr_to_dict(r), "对账已完成")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("reconcile_record 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ==================== 互联互通结算 ====================

@router.get("/settlement/interconnect", summary="互联互通结算列表")
def list_interconnect_settlements(
    platform_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    try:
        q = db.query(InterconnectSettlement)
        if platform_id:
            q = q.filter(InterconnectSettlement.platform_id == platform_id)
        if status:
            q = q.filter(InterconnectSettlement.status == status)

        total = q.count()
        items = q.order_by(InterconnectSettlement.created_at.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()

        return success_response({
            "items": [_ic_to_dict(s) for s in items],
            "total": total, "page": page, "page_size": page_size,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_interconnect_settlements 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/settlement/interconnect", summary="创建互联互通结算")
def create_interconnect_settlement(body: InterconnectSettlementCreate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        ratio = body.revenue_share_ratio
        # 任务卡 abf3d756：分账比例边界校验（资金安全）。链式比较一并拦截
        # 负数 / >1 / NaN（NaN 参与比较恒 False → not False → raise → 400）。
        if not (Decimal("0") <= ratio <= Decimal("1")):
            raise HTTPException(status_code=400, detail="revenue_share_ratio 必须在 0~1 之间")
        total_amount = body.total_amount
        our_rev = (total_amount * ratio).quantize(Decimal("0.01"))
        partner_rev = total_amount - our_rev

        record = InterconnectSettlement(
            platform_id=body.platform_id,
            platform_name=body.platform_name,
            start_date=body.start_date,
            end_date=body.end_date,
            total_orders=body.total_orders,
            total_energy_kwh=body.total_energy_kwh,
            total_amount=total_amount,
            revenue_share_ratio=ratio,
            our_revenue=our_rev,
            partner_revenue=partner_rev,
            settlement_amount=our_rev,
            status=InterconnectSettlementStatus.PENDING,
            remark=body.remark,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return success_response(_ic_to_dict(record), "互联互通结算记录已创建")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_interconnect_settlement 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/settlement/interconnect/{settlement_id}/settle", summary="完成互联互通结算")
def settle_interconnect(settlement_id: int, body: InterconnectSettle, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        s = db.query(InterconnectSettlement).filter(InterconnectSettlement.id == settlement_id).first()
        if not s:
            raise HTTPException(status_code=404, detail="结算记录不存在")
        if s.status != InterconnectSettlementStatus.PENDING:
            raise HTTPException(status_code=400, detail="该记录已结算")
        s.status = InterconnectSettlementStatus.SETTLED
        s.settled_at = datetime.now(timezone.utc)
        s.settled_by = body.operator
        db.commit()
        db.refresh(s)
        return success_response(_ic_to_dict(s), "结算已完成")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("settle_interconnect 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ==================== 企业结算（复用日结数据，按企业维度聚合） ====================

@router.get("/settlement/enterprise", summary="企业结算列表")
def list_enterprise_settlements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """企业结算（从 fleet_settlement_bills 聚合，运营视角）"""
    try:
        from app.models.settlement import FleetSettlementBill
        from app.models.enterprise import Enterprise
        q = db.query(FleetSettlementBill)
        # team scoping（任务卡 ab5c5f17）：企业结算经 enterprise→owner_team，非 admin 仅返回本 team 企业的账单。
        if not is_platform_admin(user):
            q = q.join(Enterprise, FleetSettlementBill.enterprise_id == Enterprise.id).filter(Enterprise.owner_team_id == user.team_id)
        total = q.count()
        items = q.order_by(FleetSettlementBill.created_at.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()

        return success_response({
            "items": [{
                "id": b.id,
                "bill_no": b.bill_no,
                "enterprise_id": b.enterprise_id,
                "bill_period": b.bill_period,
                "total_orders": b.total_orders,
                "total_amount": float(b.total_amount) if b.total_amount else 0,
                "paid_amount": float(b.paid_amount) if b.paid_amount else 0,
                "balance_amount": float(b.balance_amount) if b.balance_amount else 0,
                "status": b.status.value if hasattr(b.status, 'value') else str(b.status),
                "created_at": b.created_at.isoformat() if b.created_at else None,
            } for b in items],
            "total": total, "page": page, "page_size": page_size,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_enterprise_settlements 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ==================== 辅助函数 ====================

def _ds_to_dict(s: DailySettlement) -> dict:
    return {
        "id": s.id,
        "settlement_date": s.settlement_date.isoformat() if s.settlement_date else None,
        "station_id": s.station_id,
        "total_orders": s.total_orders,
        "total_energy_kwh": float(s.total_energy_kwh) if s.total_energy_kwh else 0,
        "total_charge_fee": float(s.total_charge_fee) if s.total_charge_fee else 0,
        "total_service_fee": float(s.total_service_fee) if s.total_service_fee else 0,
        "total_parking_fee": float(s.total_parking_fee) if s.total_parking_fee else 0,
        "total_occupancy_fee": float(s.total_occupancy_fee) if s.total_occupancy_fee else 0,
        "total_reservation_fee": float(s.total_reservation_fee) if s.total_reservation_fee else 0,
        "total_amount": float(s.total_amount) if s.total_amount else 0,
        "total_paid": float(s.total_paid) if s.total_paid else 0,
        "total_discount": float(s.total_discount) if s.total_discount else 0,
        "total_coupon": float(s.total_coupon) if s.total_coupon else 0,
        "total_points": float(s.total_points) if s.total_points else 0,
        "total_refund": float(s.total_refund) if s.total_refund else 0,
        "status": s.status.value if hasattr(s.status, 'value') else str(s.status),
        "confirmed_at": s.confirmed_at.isoformat() if s.confirmed_at else None,
        "confirmed_by": s.confirmed_by,
        "remark": s.remark,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _pr_to_dict(r: PaymentReconciliation) -> dict:
    return {
        "id": r.id,
        "settlement_date": r.settlement_date.isoformat() if r.settlement_date else None,
        "payment_channel": r.payment_channel,
        "platform_orders_count": r.platform_orders_count,
        "platform_amount": float(r.platform_amount) if r.platform_amount else 0,
        "payment_orders_count": r.payment_orders_count,
        "payment_amount": float(r.payment_amount) if r.payment_amount else 0,
        "difference_count": r.difference_count,
        "difference_amount": float(r.difference_amount) if r.difference_amount else 0,
        "difference_detail": r.difference_detail,
        "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
        "reconciled_at": r.reconciled_at.isoformat() if r.reconciled_at else None,
        "reconciled_by": r.reconciled_by,
        "remark": r.remark,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _ic_to_dict(s: InterconnectSettlement) -> dict:
    return {
        "id": s.id,
        "platform_id": s.platform_id,
        "platform_name": s.platform_name,
        "start_date": s.start_date.isoformat() if s.start_date else None,
        "end_date": s.end_date.isoformat() if s.end_date else None,
        "total_orders": s.total_orders,
        "total_energy_kwh": float(s.total_energy_kwh) if s.total_energy_kwh else 0,
        "total_amount": float(s.total_amount) if s.total_amount else 0,
        "revenue_share_ratio": float(s.revenue_share_ratio) if s.revenue_share_ratio else 0,
        "our_revenue": float(s.our_revenue) if s.our_revenue else 0,
        "partner_revenue": float(s.partner_revenue) if s.partner_revenue else 0,
        "settlement_amount": float(s.settlement_amount) if s.settlement_amount else 0,
        "invoice_id": s.invoice_id,
        "status": s.status.value if hasattr(s.status, 'value') else str(s.status),
        "settled_at": s.settled_at.isoformat() if s.settled_at else None,
        "settled_by": s.settled_by,
        "remark": s.remark,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
