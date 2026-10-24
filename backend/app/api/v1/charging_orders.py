"""
充电订单管理 API - Phase42 运营管理

提供充电订单的查询和创建操作:
- GET    /api/v1/charging-orders        列表（支持多维度筛选和分页）
- GET    /api/v1/charging-orders/{id}   详情
- POST   /api/v1/charging-orders        创建（自动调用 billing 计算费用）
- PUT    /api/v1/charging-orders/{id}/status  更新订单状态
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Literal, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from decimal import Decimal

from app.core.database import get_db
from app.core.iso_utils import parse_iso8601_or_400
from app.core.response import success_response, paginated_response
from app.models.charging_order import ChargingOrder, OrderPaymentStatus, OrderStatus, PaymentMethod, UserType
from app.models.station import Station
from app.models.user import User
from app.services.billing import calculate_total_order
from app.services.enterprise_balance_service import (
    deduct_on_order_complete,
    InsufficientBalanceError,
    EnterpriseDeletedError,
)
from app.models.enterprise import Enterprise
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, assert_station_team_access
from app.middleware.permission import require_write_permission

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_write_permission("charging:manage"))])


# ─── Pydantic 模型 ───

class ChargingOrderCreate(BaseModel):
    station_id: int = Field(..., description="电站ID")
    device_id: int = Field(..., description="充电设备ID")
    user_id: Optional[int] = Field(None, description="用户ID")
    user_type: Optional[str] = Field(None, description="用户类型: app/card")
    vehicle_id: Optional[int] = Field(None, description="车辆ID")
    plate_number: Optional[str] = Field(None, max_length=20, description="车牌号")
    start_time: Optional[str] = Field(None, description="充电开始时间 (ISO格式)")
    start_soc: Optional[float] = Field(None, description="起始电量(%)")
    end_soc: Optional[float] = Field(None, description="结束电量(%)")
    start_meter: Optional[float] = Field(None, description="起始电表读数")
    end_meter: Optional[float] = Field(None, description="结束电表读数")
    stop_reason: Optional[str] = Field(None, max_length=50, description="停止原因: full/active/fault/balance_low")
    charged_kwh: float = Field(0.0, ge=0, description="充电电量(kWh)")
    duration_minutes: int = Field(0, description="充电时长(分钟)")
    parking_duration_hours: float = Field(0.0, description="停车时长(小时)")
    idle_minutes: int = Field(0, description="超时分钟数")
    discount_amount: float = Field(0.0, ge=0, le=100000, description="折扣金额(元)")
    remark: Optional[str] = Field(None, max_length=500, description="备注")


class OrderStatusUpdate(BaseModel):
    status: Literal["pending", "charging", "completed", "cancelled", "failed"] = Field(
        ..., description="目标状态: pending/charging/completed/cancelled/failed"
    )


# ─── Helper ───

def _order_to_dict(order: ChargingOrder) -> dict:
    return {
        "id": order.id,
        "order_no": order.order_no,
        "station_id": order.station_id,
        "device_id": order.device_id,
        "user_id": order.user_id,
        "user_type": order.user_type.value if order.user_type else None,
        "vehicle_id": order.vehicle_id,
        "plate_number": order.plate_number,
        "start_time": order.start_time.isoformat() if order.start_time else None,
        "end_time": order.end_time.isoformat() if order.end_time else None,
        "duration_minutes": order.duration_minutes,
        "start_soc": float(order.start_soc) if order.start_soc else None,
        "end_soc": float(order.end_soc) if order.end_soc else None,
        "start_meter": float(order.start_meter) if order.start_meter else None,
        "end_meter": float(order.end_meter) if order.end_meter else None,
        "stop_reason": order.stop_reason,
        "charged_kwh": float(order.charged_kwh) if order.charged_kwh else 0.0,
        "electricity_fee": float(order.electricity_fee) if order.electricity_fee else 0.0,
        "service_fee": float(order.service_fee) if order.service_fee else 0.0,
        "parking_fee": float(order.parking_fee) if order.parking_fee else 0.0,
        "idle_penalty": float(order.idle_penalty) if order.idle_penalty else 0.0,
        "reservation_fee": float(order.reservation_fee) if order.reservation_fee else 0.0,
        "total_amount": float(order.total_amount) if order.total_amount else 0.0,
        "discount_amount": float(order.discount_amount) if order.discount_amount else 0.0,
        "paid_amount": float(order.paid_amount) if order.paid_amount else 0.0,
        "payment_status": order.payment_status.value if order.payment_status else None,
        "order_status": order.order_status.value if order.order_status else None,
        "payment_method": order.payment_method.value if order.payment_method else None,
        "remark": order.remark,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }


def _generate_order_no(db: Session) -> str:
    """生成订单编号: CO + YYYYMMDD + 4位序号"""
    from datetime import datetime, timezone
    prefix = f"CO{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    count = db.query(ChargingOrder).filter(
        ChargingOrder.order_no.like(f"{prefix}%")
    ).count()
    return f"{prefix}{count + 1:04d}"


# 订单经 station 间接归属 team（自身无 team_id 列）。
# admin/super_admin 平台级豁免；跨团队一律 404（不泄露存在）。

def _order_team_id(db: Session, order_id: int):
    """order → station.team_id（经 join）；订单/站点不存在 → None。"""
    return (
        db.query(Station.team_id)
        .join(ChargingOrder, ChargingOrder.station_id == Station.id)
        .filter(ChargingOrder.id == order_id)
        .scalar()
    )


def _assert_order_team_access(db: Session, order_id: int, user: User):
    """详情/写端点归属校验：admin 豁免；非 admin 仅本 team 订单，否则 404。"""
    if is_platform_admin(user):
        return
    tid = _order_team_id(db, order_id)
    if tid is None or user.team_id is None or tid != user.team_id:
        raise HTTPException(status_code=404, detail="充电订单不存在")


# ─── API 端点 ───

@router.get("/charging-orders")
def list_charging_orders(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    station_id: Optional[int] = Query(None, description="电站ID筛选"),
    device_id: Optional[int] = Query(None, description="设备ID筛选"),
    user_id: Optional[int] = Query(None, description="用户ID筛选"),
    order_status: Optional[str] = Query(None, description="订单状态筛选: pending/charging/completed/cancelled/failed"),
    payment_status: Optional[str] = Query(None, description="支付状态筛选: unpaid/paid/refunding/refunded/partial"),
    plate_number: Optional[str] = Query(None, description="车牌号筛选"),
    keyword: Optional[str] = Query(None, description="订单编号搜索"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """充电订单列表（支持多维度筛选）"""
    q = db.query(ChargingOrder)

    # team scoping（任务卡 b640bdd9）：非 admin 仅返回本 team 站点的订单（经 station→team）。
    if not is_platform_admin(user):
        q = q.join(Station, ChargingOrder.station_id == Station.id) \
             .filter(Station.team_id == user.team_id)
    if station_id:
        # 非 admin 校验 station 归属本 team，越权站点 → 404（不泄露存在）。
        if not is_platform_admin(user):
            assert_station_team_access(db, station_id, user)
        q = q.filter(ChargingOrder.station_id == station_id)
    if device_id:
        q = q.filter(ChargingOrder.device_id == device_id)
    if user_id:
        q = q.filter(ChargingOrder.user_id == user_id)
    if order_status:
        try:
            os = OrderStatus(order_status)
            q = q.filter(ChargingOrder.order_status == os)
        except ValueError:
            pass
    if payment_status:
        try:
            ps = OrderPaymentStatus(payment_status)
            q = q.filter(ChargingOrder.payment_status == ps)
        except ValueError:
            pass
    if plate_number:
        q = q.filter(ChargingOrder.plate_number == plate_number)
    if keyword:
        q = q.filter(ChargingOrder.order_no.ilike(f"%{keyword}%"))

    total = q.count()
    items = q.order_by(ChargingOrder.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()

    return paginated_response(
        items=[_order_to_dict(o) for o in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/charging-orders/{order_id}")
def get_charging_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """充电订单详情"""
    order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="充电订单不存在")
    _assert_order_team_access(db, order_id, user)
    return success_response(_order_to_dict(order))


@router.post("/charging-orders")
def create_charging_order(body: ChargingOrderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """创建充电订单（自动调用 billing 计算费用）

    从 active 的定价规则中取第一条的电价和服务费率来计算费用。
    """
    # team scoping（任务卡 b640bdd9）：非 admin 仅可在本 team 站点建单，越权 → 404；
    # admin 显式豁免（保留原可跨站建单语义）。
    if not is_platform_admin(user):
        assert_station_team_access(db, body.station_id, user)

    from app.models.pricing_rule import PricingRule

    # 获取活跃的定价规则（取第一条）
    pr = db.query(PricingRule).filter(PricingRule.is_active == True).first()
    if pr:
        electricity_price = Decimal(str(pr.electricity_price))
        service_fee_rate = Decimal(str(pr.service_fee_rate))
        parking_fee_per_hour = Decimal(str(pr.parking_fee_per_hour))
        idle_penalty_per_min = Decimal(str(pr.idle_penalty_per_min))
    else:
        # 默认费率
        electricity_price = Decimal("0.8")
        service_fee_rate = Decimal("0.5")
        parking_fee_per_hour = Decimal("0")
        idle_penalty_per_min = Decimal("0")

    # 调用 billing 计算费用
    charged_kwh = Decimal(str(body.charged_kwh))
    parking_hours = Decimal(str(body.parking_duration_hours))
    billing_result = calculate_total_order(
        charged_kwh=charged_kwh,
        electricity_price=electricity_price,
        service_fee_rate=service_fee_rate,
        duration_hours=parking_hours,
        parking_fee_per_hour=parking_fee_per_hour,
        idle_minutes=body.idle_minutes,
        idle_penalty_per_min=idle_penalty_per_min,
        discount_amount=Decimal(str(body.discount_amount)),
    )

    order_no = _generate_order_no(db)
    start_dt = parse_iso8601_or_400(body.start_time, "start_time 格式无效，需 ISO 8601") if body.start_time else None

    order = ChargingOrder(
        order_no=order_no,
        station_id=body.station_id,
        device_id=body.device_id,
        user_id=body.user_id,
        user_type=UserType(body.user_type) if body.user_type else None,
        vehicle_id=body.vehicle_id,
        plate_number=body.plate_number,
        start_time=start_dt,
        duration_minutes=body.duration_minutes,
        start_soc=body.start_soc,
        end_soc=body.end_soc,
        start_meter=body.start_meter,
        end_meter=body.end_meter,
        stop_reason=body.stop_reason,
        charged_kwh=charged_kwh,
        payment_status=OrderPaymentStatus.UNPAID,
        order_status=OrderStatus.PENDING,
        remark=body.remark,
    )
    db.add(order)
    db.flush()  # 仅分配 order.id 供费用明细FK; 订单与费用同一事务边界 (b8895972)

    # billing_engine 写 5 项费用字段 + order_fee_items 明细 (d018e3dc)
    # 计算仍走 calculate_total_order(旧 billing.py 向后兼容), 数值不变, 仅切换写入路径
    from app.services.billing_engine import settle_order_fees
    fees = {
        "energy_fee": billing_result["electricity_fee"],
        "service_fee": billing_result["service_fee"],
        "parking_fee": billing_result["parking_fee"],
        "occupancy_fee": billing_result["idle_penalty"],
        "reservation_fee": billing_result["reservation_fee"],
        "discount_amount": billing_result["discount_amount"],
    }
    settle_order_fees(order, fees, db)
    db.commit()  # settle_order_fees 不再内部 commit, 提交边界由调用方控制
    db.refresh(order)
    return success_response(_order_to_dict(order), "充电订单创建成功")


@router.put("/charging-orders/{order_id}/status")
def update_order_status(order_id: int, body: OrderStatusUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新充电订单状态

    当订单状态变为 completed 且支付方式为 enterprise 时，
    自动扣减企业余额并写入交易流水（预储值消耗闭环）。
    """
    order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="充电订单不存在")
    _assert_order_team_access(db, order_id, user)

    try:
        new_status = OrderStatus(body.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效的订单状态: {body.status}，请使用 pending/charging/completed/cancelled/failed"
        )

    order.order_status = new_status
    if new_status == OrderStatus.COMPLETED:
        from datetime import datetime, timezone
        order.end_time = datetime.now(timezone.utc)

        # ─── 预储值消耗闭环: 企业账户扣费 ───
        # 当支付方式为企业账户时，扣减余额并写流水
        if order.payment_method == PaymentMethod.ENTERPRISE:
            # 通过 vehicle_id 或 plate_number 找到关联企业
            enterprise = None
            if order.vehicle_id:
                from app.models.enterprise_vehicle import EnterpriseVehicle
                ev = db.query(EnterpriseVehicle).filter(
                    EnterpriseVehicle.id == order.vehicle_id
                ).first()
                if ev:
                    enterprise = db.query(Enterprise).filter(
                        Enterprise.id == ev.enterprise_id
                    ).first()

            if not enterprise and order.plate_number:
                from app.models.enterprise_vehicle import EnterpriseVehicle
                ev = db.query(EnterpriseVehicle).filter(
                    EnterpriseVehicle.plate_number == order.plate_number
                ).first()
                if ev:
                    enterprise = db.query(Enterprise).filter(
                        Enterprise.id == ev.enterprise_id
                    ).first()

            # 幂等守卫: 订单已 PAID(重复结算) → 跳过扣款, 仅完成订单
            # (deduct_on_order_complete 内亦有同款守卫, 此处提前避免无谓事务)
            if enterprise and order.payment_status != OrderPaymentStatus.PAID:
                try:
                    tx = deduct_on_order_complete(db, order, enterprise)
                    db.commit()
                    db.refresh(order)
                    msg = f"订单状态已更新为 {body.status}"
                    if tx:
                        msg += f"，企业余额扣减 {float(tx.amount):.2f} 元（余额 {float(tx.balance_after):.2f} 元）"
                    return success_response(_order_to_dict(order), msg)
                except InsufficientBalanceError as e:
                    # 余额不足 (卡 8772b963): 对齐 business_orders 语义 —
                    # rollback 丢弃 deduct 变更, 重放订单状态 → completed+unpaid,
                    # 费用在创建时已 commit (b8895972), 不受影响; 不再 402。
                    db.rollback()
                    db.refresh(order)
                    order.order_status = new_status
                    order.end_time = datetime.now(timezone.utc)
                    logger.info(
                        "企业 %s 余额不足, 订单 %s 保持 unpaid 待人工跟进",
                        enterprise.id, order.order_no,
                    )
                    db.commit()
                    db.refresh(order)
                    return success_response(
                        _order_to_dict(order),
                        f"订单状态已更新为 {body.status}，企业余额不足待人工跟进",
                    )
                except EnterpriseDeletedError:
                    # 删除竞态 (卡 84439ed8): 结算窗口内企业行被并发删除,
                    # deduct 中断防白嫖。重放订单状态变更 → completed+unpaid,
                    # 订单照常完成, 营收漏损留人工跟进。
                    db.rollback()
                    db.refresh(order)
                    order.order_status = new_status
                    order.end_time = datetime.now(timezone.utc)
                    logger.warning(
                        "企业 %s 结算时已被删除, 订单 %s 保持 unpaid 待人工跟进",
                        enterprise.id, order.order_no,
                    )
                    db.commit()
                    db.refresh(order)
                    return success_response(
                        _order_to_dict(order),
                        "订单状态已更新为 completed，企业账户异常待人工跟进",
                    )
            else:
                # 找不到关联企业 或 订单已结算(幂等跳过) → 仅完成订单
                db.commit()
                db.refresh(order)
                return success_response(_order_to_dict(order), f"订单状态已更新为 {body.status}")

    elif new_status == OrderStatus.CANCELLED:
        from datetime import datetime, timezone
        order.end_time = datetime.now(timezone.utc)

    db.commit()
    db.refresh(order)
    return success_response(_order_to_dict(order), f"订单状态已更新为 {body.status}")
