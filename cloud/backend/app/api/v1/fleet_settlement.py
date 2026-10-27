"""
车队对账结算 API

功能:
- POST /api/v1/fleet/settlement/bills/generate     —— 生成账单（按账期聚合）
- GET  /api/v1/fleet/settlement/bills               —— 账单列表
- GET  /api/v1/fleet/settlement/bills/{bill_id}      —— 账单详情
- POST /api/v1/fleet/settlement/bills/{bill_id}/confirm  —— 确认账单
- POST /api/v1/fleet/settlement/bills/{bill_id}/pay      —— 标记已付款
- GET  /api/v1/fleet/settlement/bills/{bill_id}/details  —— 账单明细列表
- POST /api/v1/fleet/settlement/bills/{bill_id}/invoice  —— 申请发票
- GET  /api/v1/fleet/settlement/invoices                 —— 发票申请列表
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import assert_enterprise_team_access, team_scope
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.enterprise import Enterprise
from app.models.settlement import (
    FleetSettlementBill, BillStatus,
    FleetSettlementDetail,
    FleetInvoiceRequest, InvoiceStatus, InvoiceType,
)
from app.models.user import User
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_write_permission("fleet:manage"))])


# ========== Schemas ==========

class BillGenerateRequest(BaseModel):
    enterprise_id: int
    bill_period: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="账期 YYYY-MM", examples=["2025-07"])


class BillConfirmRequest(BaseModel):
    remark: Optional[str] = None


class BillPayRequest(BaseModel):
    paid_amount: Decimal = Field(
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="实付金额(元)：非负，整数部分≤10位，精确到分(2位小数)，与 Numeric(12,2) 列语义对齐",
    )
    remark: Optional[str] = None


class InvoiceRequest(BaseModel):
    title: str = Field(..., description="发票抬头")
    tax_no: Optional[str] = Field(None, description="税号")
    invoice_type: str = Field("general", description="发票类型: general/special")
    email: Optional[str] = Field(None, description="接收邮箱")
    remark: Optional[str] = None


# ========== Helpers ==========

def _bill_to_dict(bill: FleetSettlementBill) -> dict:
    return {
        "id": bill.id,
        "bill_no": bill.bill_no,
        "enterprise_id": bill.enterprise_id,
        "bill_period": bill.bill_period,
        "total_orders": bill.total_orders,
        "total_energy_kwh": float(bill.total_energy_kwh) if bill.total_energy_kwh else 0,
        "total_charge_fee": float(bill.total_charge_fee) if bill.total_charge_fee else 0,
        "total_service_fee": float(bill.total_service_fee) if bill.total_service_fee else 0,
        "total_parking_fee": float(bill.total_parking_fee) if bill.total_parking_fee else 0,
        "total_discount": float(bill.total_discount) if bill.total_discount else 0,
        "total_amount": float(bill.total_amount) if bill.total_amount else 0,
        "paid_amount": float(bill.paid_amount) if bill.paid_amount else 0,
        "balance_amount": float(bill.balance_amount) if bill.balance_amount else 0,
        "status": bill.status.value if bill.status else "pending",
        "confirmed_at": bill.confirmed_at.isoformat() if bill.confirmed_at else None,
        "paid_at": bill.paid_at.isoformat() if bill.paid_at else None,
        "remark": bill.remark,
        "created_at": bill.created_at.isoformat() if bill.created_at else None,
        "updated_at": bill.updated_at.isoformat() if bill.updated_at else None,
    }


def _detail_to_dict(d: FleetSettlementDetail) -> dict:
    return {
        "id": d.id,
        "bill_id": d.bill_id,
        "order_id": d.order_id,
        "order_no": d.order_no,
        "vehicle_id": d.vehicle_id,
        "plate_number": d.plate_number,
        "driver_id": d.driver_id,
        "charging_time": d.charging_time.isoformat() if d.charging_time else None,
        "energy_kwh": float(d.energy_kwh) if d.energy_kwh else 0,
        "charge_fee": float(d.charge_fee) if d.charge_fee else 0,
        "service_fee": float(d.service_fee) if d.service_fee else 0,
        "parking_fee": float(d.parking_fee) if d.parking_fee else 0,
        "discount_amount": float(d.discount_amount) if d.discount_amount else 0,
        "total_amount": float(d.total_amount) if d.total_amount else 0,
    }


def _invoice_to_dict(inv: FleetInvoiceRequest) -> dict:
    return {
        "id": inv.id,
        "enterprise_id": inv.enterprise_id,
        "bill_id": inv.bill_id,
        "amount": float(inv.amount) if inv.amount else 0,
        "invoice_type": inv.invoice_type.value if inv.invoice_type else "general",
        "title": inv.title,
        "tax_no": inv.tax_no,
        "email": inv.email,
        "status": inv.status.value if inv.status else "pending",
        "remark": inv.remark,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


# ========== API Endpoints ==========

@router.post("/bills/generate", summary="生成对账账单")
def generate_bill(
    data: BillGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按账期聚合充电订单，生成对账账单"""
    try:
        assert_enterprise_team_access(db, data.enterprise_id, current_user)

        # 检查是否已有该账期的账单
        existing = db.query(FleetSettlementBill).filter(
            FleetSettlementBill.enterprise_id == data.enterprise_id,
            FleetSettlementBill.bill_period == data.bill_period,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"{data.bill_period} 账期账单已存在")

        # 查询该企业该账期所有已完成/已支付的充电订单
        period_start = f"{data.bill_period}-01 00:00:00"
        # 计算下一个月
        year, month = map(int, data.bill_period.split("-"))
        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1
        period_end = f"{next_year}-{next_month:02d}-01 00:00:00"

        orders = db.query(ChargingOrder).filter(
            ChargingOrder.start_time >= period_start,
            ChargingOrder.start_time < period_end,
            ChargingOrder.order_status.in_([OrderStatus.COMPLETED]),
        ).all()

        # 过滤属于该企业的订单: 严格按 EnterpriseVehicle 反查企业确权 (卡 3a8d4dc5)
        # 口径与 charging_orders 扣款侧一致: 先 vehicle_id 反查, 再 plate_number 反查,
        # 反查到的 enterprise_id == 当前企业才并入; 移除 payment_method==enterprise 无归属 OR 兜底,
        # 否则任何企业的 enterprise 支付订单都会被吞进当前账单 → 资金串账
        from app.models.enterprise_vehicle import EnterpriseVehicle
        vehicles_by_id = {
            v.id: v for v in
            db.query(EnterpriseVehicle).filter(EnterpriseVehicle.id.in_(
                [o.vehicle_id for o in orders if o.vehicle_id]
            )).all()
        }
        vehicles_by_plate = {
            v.plate_number: v for v in
            db.query(EnterpriseVehicle).filter(EnterpriseVehicle.plate_number.in_(
                [o.plate_number for o in orders if o.plate_number]
            )).all()
        }
        ent_orders = []
        for o in orders:
            vehicle = vehicles_by_id.get(o.vehicle_id) if o.vehicle_id else None
            if vehicle is None and o.plate_number:
                vehicle = vehicles_by_plate.get(o.plate_number)
            if vehicle is not None and vehicle.enterprise_id == data.enterprise_id:
                ent_orders.append(o)
            elif o.payment_method is not None and o.payment_method.value == "enterprise":
                # 无法确权归属到他企的 enterprise 支付订单: 不并入, 仅记录待人工对账
                logger.warning(
                    "generate_bill 跳过无法确权归属的企业支付订单 order_no=%s "
                    "(vehicle_id=%s, plate_number=%s 不属于企业 %s)",
                    o.order_no, o.vehicle_id, o.plate_number, data.enterprise_id,
                )

        if not ent_orders:
            # 仍然创建一个空账单，方便对账确认
            pass

        # 汇总金额
        total_orders = len(ent_orders)
        total_energy = sum((o.charged_kwh or Decimal("0")) for o in ent_orders)
        total_charge_fee = sum((o.electricity_fee or Decimal("0")) for o in ent_orders)
        total_service_fee = sum((o.service_fee or Decimal("0")) for o in ent_orders)
        total_parking_fee = sum((o.parking_fee or Decimal("0")) for o in ent_orders)
        total_discount = sum((o.discount_amount or Decimal("0")) + (o.coupon_amount or Decimal("0")) for o in ent_orders)
        total_amount = sum((o.total_amount or Decimal("0")) for o in ent_orders)
        paid_amount = sum((o.paid_amount or Decimal("0")) for o in ent_orders)
        balance = total_amount - paid_amount

        # 生成账单编号
        bill_no = f"FSB{data.bill_period.replace('-', '')}{data.enterprise_id:04d}"

        bill = FleetSettlementBill(
            bill_no=bill_no,
            enterprise_id=data.enterprise_id,
            bill_period=data.bill_period,
            total_orders=total_orders,
            total_energy_kwh=total_energy,
            total_charge_fee=total_charge_fee,
            total_service_fee=total_service_fee,
            total_parking_fee=total_parking_fee,
            total_discount=total_discount,
            total_amount=total_amount,
            paid_amount=paid_amount,
            balance_amount=balance,
            status=BillStatus.PENDING,
        )
        db.add(bill)
        db.flush()  # 获取 bill.id

        # 生成明细
        for o in ent_orders:
            detail = FleetSettlementDetail(
                bill_id=bill.id,
                order_id=o.id,
                order_no=o.order_no,
                vehicle_id=o.vehicle_id,
                plate_number=o.plate_number,
                driver_id=None,
                charging_time=o.start_time,
                energy_kwh=o.charged_kwh or Decimal("0"),
                charge_fee=o.electricity_fee or Decimal("0"),
                service_fee=o.service_fee or Decimal("0"),
                parking_fee=o.parking_fee or Decimal("0"),
                discount_amount=(o.discount_amount or Decimal("0")) + (o.coupon_amount or Decimal("0")),
                total_amount=o.total_amount or Decimal("0"),
            )
            db.add(detail)

        db.commit()
        db.refresh(bill)

        return success_response(_bill_to_dict(bill), message=f"账单 {bill.bill_no} 已生成，含 {total_orders} 笔订单")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_bill 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/bills", summary="获取账单列表")
def list_bills(
    enterprise_id: Optional[int] = Query(None),
    bill_period: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取对账账单列表 (卡 45166947: 缺省时 team 兜底过滤)"""
    try:
        if enterprise_id is not None:
            assert_enterprise_team_access(db, enterprise_id, current_user)
        query = db.query(FleetSettlementBill)
        scope = team_scope(current_user)
        if scope is not None:
            # 团队级用户缺省 enterprise_id 时按企业归属 team 兜底过滤, 杜绝全表裸查越权
            query = query.join(Enterprise, Enterprise.id == FleetSettlementBill.enterprise_id).filter(
                Enterprise.owner_team_id == scope
            )
        if enterprise_id is not None:
            query = query.filter(FleetSettlementBill.enterprise_id == enterprise_id)
        if bill_period:
            query = query.filter(FleetSettlementBill.bill_period == bill_period)
        if status:
            query = query.filter(FleetSettlementBill.status == status)

        total = query.count()
        items = query.order_by(FleetSettlementBill.id.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        return paginated_response(
            items=[_bill_to_dict(b) for b in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_bills 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/bills/{bill_id}", summary="获取账单详情")
def get_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单条账单详情"""
    try:
        bill = db.query(FleetSettlementBill).filter(FleetSettlementBill.id == bill_id).first()
        if not bill:
            raise HTTPException(status_code=404, detail="账单不存在")
        assert_enterprise_team_access(db, bill.enterprise_id, current_user)
        return success_response(_bill_to_dict(bill))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_bill 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/bills/{bill_id}/confirm", summary="确认账单")
def confirm_bill(
    bill_id: int,
    data: BillConfirmRequest = BillConfirmRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """确认对账账单 (pending → confirmed)"""
    try:
        bill = (
            db.query(FleetSettlementBill)
            .filter(FleetSettlementBill.id == bill_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if not bill:
            raise HTTPException(status_code=404, detail="账单不存在")
        assert_enterprise_team_access(db, bill.enterprise_id, current_user)
        if bill.status != BillStatus.PENDING:
            raise HTTPException(status_code=400, detail=f"账单当前状态 {bill.status.value}，无法确认")

        bill.status = BillStatus.CONFIRMED
        bill.confirmed_at = datetime.now(timezone.utc)
        if data.remark:
            bill.remark = data.remark
        db.commit()
        db.refresh(bill)

        return success_response(_bill_to_dict(bill), message="账单已确认")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("confirm_bill 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/bills/{bill_id}/pay", summary="标记账单已付款")
def pay_bill(
    bill_id: int,
    data: BillPayRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记账单已付款 (confirmed → paid)"""
    try:
        bill = (
            db.query(FleetSettlementBill)
            .filter(FleetSettlementBill.id == bill_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if not bill:
            raise HTTPException(status_code=404, detail="账单不存在")
        assert_enterprise_team_access(db, bill.enterprise_id, current_user)
        if bill.status != BillStatus.CONFIRMED:
            raise HTTPException(status_code=400, detail=f"账单当前状态 {bill.status.value}，需先确认后再付款")
        if data.paid_amount > (bill.total_amount or Decimal("0")):
            raise HTTPException(status_code=400, detail="实付金额不能超过账单总额")

        bill.status = BillStatus.PAID
        bill.paid_at = datetime.now(timezone.utc)
        bill.paid_amount = data.paid_amount
        bill.balance_amount = bill.total_amount - data.paid_amount
        if data.remark:
            bill.remark = data.remark
        db.commit()
        db.refresh(bill)

        return success_response(_bill_to_dict(bill), message="账单已标记付款")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("pay_bill 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/bills/{bill_id}/details", summary="获取账单明细")
def list_bill_details(
    bill_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取账单的订单明细列表"""
    try:
        bill = db.query(FleetSettlementBill).filter(FleetSettlementBill.id == bill_id).first()
        if not bill:
            raise HTTPException(status_code=404, detail="账单不存在")
        assert_enterprise_team_access(db, bill.enterprise_id, current_user)

        query = db.query(FleetSettlementDetail).filter(FleetSettlementDetail.bill_id == bill_id)
        total = query.count()
        items = query.order_by(FleetSettlementDetail.id.asc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        return paginated_response(
            items=[_detail_to_dict(d) for d in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_bill_details 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/bills/{bill_id}/invoice", summary="申请发票")
def request_invoice(
    bill_id: int,
    data: InvoiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """对指定账单申请开发票"""
    try:
        bill = db.query(FleetSettlementBill).filter(FleetSettlementBill.id == bill_id).first()
        if not bill:
            raise HTTPException(status_code=404, detail="账单不存在")
        assert_enterprise_team_access(db, bill.enterprise_id, current_user)

        inv_type = InvoiceType.GENERAL
        if data.invoice_type == "special":
            inv_type = InvoiceType.SPECIAL

        invoice = FleetInvoiceRequest(
            enterprise_id=bill.enterprise_id,
            bill_id=bill.id,
            amount=bill.total_amount or Decimal("0"),
            invoice_type=inv_type,
            title=data.title,
            tax_no=data.tax_no,
            email=data.email,
            status=InvoiceStatus.PENDING,
            remark=data.remark,
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        return success_response(_invoice_to_dict(invoice), message="发票申请已提交")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("request_invoice 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/invoices", summary="获取发票申请列表")
def list_invoices(
    enterprise_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取发票申请列表 (卡 45166947: 缺省时 team 兜底过滤)"""
    try:
        if enterprise_id is not None:
            assert_enterprise_team_access(db, enterprise_id, current_user)
        query = db.query(FleetInvoiceRequest)
        scope = team_scope(current_user)
        if scope is not None:
            # 团队级用户缺省 enterprise_id 时按企业归属 team 兜底过滤, 杜绝全表裸查越权
            query = query.join(Enterprise, Enterprise.id == FleetInvoiceRequest.enterprise_id).filter(
                Enterprise.owner_team_id == scope
            )
        if enterprise_id is not None:
            query = query.filter(FleetInvoiceRequest.enterprise_id == enterprise_id)
        if status:
            query = query.filter(FleetInvoiceRequest.status == status)

        total = query.count()
        items = query.order_by(FleetInvoiceRequest.id.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        return paginated_response(
            items=[_invoice_to_dict(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_invoices 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
