"""
订单费用明细 & 退款 API - 运营五项费用扩展

提供:
- POST   /api/v1/orders/{order_id}/settle          结算并生成 fee_items 明细
- GET    /api/v1/orders/{order_id}/fee-items        查看费用明细
- POST   /api/v1/orders/{order_id}/refund           发起退款申请
- GET    /api/v1/orders/{order_id}/refunds           查看退款记录
- POST   /api/v1/orders/{order_id}/refunds/{refund_id}/approve   审批退款
- POST   /api/v1/orders/{order_id}/refunds/{refund_id}/reject    拒绝退款
- POST   /api/v1/orders/{order_id}/refunds/{refund_id}/complete  标记已退款

退款链路财务边界 (卡 aa88371f):
- 缺陷1: complete 按 累计退款 vs 实付 判定 REFUNDED(≥) / PARTIAL(<), 不再无条件 REFUNDED。
- 缺陷2: reject 恢复 create_refund 快照的 prev_payment_status, 不再硬编码 REFUNDING→PAID。
- 缺陷3: approve/reject 的 reviewer_id 取 token(user.id), body.reviewer_id 废弃。
- 缺陷4: approve/reject 走 WHERE status=PENDING 条件 UPDATE 乐观锁(败者 409);
         complete 走 SELECT...FOR UPDATE 悲观锁(防并发重复调渠道)。
- 缺陷5: complete 经 app.services.wx_pay.refund 发起渠道退款, 落 channel_refund_no。

累计退款额度 (卡 75134a82):
- 剩余可退 = paid_amount − Σ(状态为 PENDING+APPROVED+REFUNDED 的 refund_amount);
  REJECTED 已释放不占用。create/approve/complete 三层校验, 防跨笔累计超退渠道金额
  (修复前每笔仅校验单笔 ≤ paid, paid 不随退款衰减 → 多笔可累计超退)。
"""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

from app.core.database import get_db
from app.core.response import success_response
from app.models.charging_order import ChargingOrder, OrderPaymentStatus
from app.models.order_fee_item import OrderFeeItem, RefundRecord, FeeType, RefundStatus
from app.api.deps import assert_order_team_access, is_platform_admin
from app.models.station import Station
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.models.user import User
from app.services.wx_pay import refund as wx_refund_service
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_write_permission("charging:manage"))])


# ─── Pydantic 请求模型 ───

class SettleRequest(BaseModel):
    """结算请求 — 可选传入分时电量和优惠"""
    peak_energy: float = Field(0.0, description="尖峰电量(kWh)")
    flat_energy: float = Field(0.0, description="平段电量(kWh)")
    valley_energy: float = Field(0.0, description="谷段电量(kWh)")
    trough_energy: float = Field(0.0, description="深谷电量(kWh)")
    peak_price: float = Field(0.0, ge=0, description="尖峰电价(元/kWh)")
    flat_price: float = Field(0.0, ge=0, description="平段电价(元/kWh)")
    valley_price: float = Field(0.0, ge=0, description="谷段电价(元/kWh)")
    trough_price: float = Field(0.0, ge=0, description="深谷电价(元/kWh)")
    service_fee_rate: float = Field(0.0, ge=0, description="服务费率(元/kWh)")
    parking_hours: float = Field(0.0, description="停车时长(小时)")
    parking_rate: float = Field(0.0, ge=0, description="停车费率(元/小时)")
    occupancy_minutes: int = Field(0, description="占桩时长(分钟)")
    occupancy_rate: float = Field(0.0, ge=0, description="占桩费率(元/分钟)")
    reservation_minutes: int = Field(0, description="预约时长(分钟)")
    reservation_rate: float = Field(0.0, ge=0, description="预约费率(元/分钟)")
    discount_amount: float = Field(0.0, ge=0, le=100000, description="折扣金额(元)")
    coupon_amount: float = Field(0.0, ge=0, le=100000, description="优惠券抵扣(元)")
    points_amount: float = Field(0.0, ge=0, le=100000, description="积分抵扣(元)")


class RefundRequest(BaseModel):
    """退款申请"""
    refund_amount: float = Field(..., gt=0, description="退款金额(元)")
    reason: str = Field(..., min_length=1, max_length=500, description="退款原因")


class RefundReview(BaseModel):
    """退款审批 — reviewer_id 已废弃(卡 aa88371f 缺陷3), 服务端取 token user.id"""
    reviewer_id: Optional[int] = Field(None, description="已废弃: 审核人ID, 服务端取 token")
    reject_reason: Optional[str] = Field(None, max_length=500, description="拒绝原因")


# ─── 辅助函数 ───

def _fee_item_to_dict(item: OrderFeeItem) -> dict:
    return {
        "id": item.id,
        "order_id": item.order_id,
        "fee_type": item.fee_type.value if item.fee_type else None,
        "fee_name": item.fee_name,
        "quantity": float(item.quantity) if item.quantity else 0.0,
        "unit_price": float(item.unit_price) if item.unit_price else 0.0,
        "amount": float(item.amount) if item.amount else 0.0,
        "unit": item.unit,
        "remark": item.remark,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _refund_to_dict(refund: RefundRecord) -> dict:
    return {
        "id": refund.id,
        "order_id": refund.order_id,
        "user_id": refund.user_id,
        "refund_amount": float(refund.refund_amount) if refund.refund_amount else 0.0,
        "reason": refund.reason,
        "status": refund.status.value if refund.status else None,
        "reviewer_id": refund.reviewer_id,
        "reviewed_at": refund.reviewed_at.isoformat() if refund.reviewed_at else None,
        "refunded_at": refund.refunded_at.isoformat() if refund.refunded_at else None,
        "reject_reason": refund.reject_reason,
        # 卡 aa88371f: 渠道退款号(缺陷5) + 退款前状态快照(缺陷2)
        "channel_refund_no": refund.channel_refund_no,
        "prev_payment_status": refund.prev_payment_status,
        "created_at": refund.created_at.isoformat() if refund.created_at else None,
        "updated_at": refund.updated_at.isoformat() if refund.updated_at else None,
    }


# 卡 75134a82: 占用额度的状态集合 — PENDING/APPROVED/REFUNDED 均占剩余可退, REJECTED 已释放。
_REFUND_OCCUPYING_STATUSES = (
    RefundStatus.PENDING,
    RefundStatus.APPROVED,
    RefundStatus.REFUNDED,
)


def _occupied_refund_amount(db: Session, order_id: int, exclude_id: Optional[int] = None) -> Decimal:
    """订单当前被占用的退款额度: Σ(在途+已批+已退) 的 refund_amount。

    exclude_id: 复核某笔自身时排除它自己 (approve/complete 场景, 该笔仍在占用集合内
    但校验口径是「排除自身后, 自身金额 ≤ paid − 其余占用」)。
    """
    q = db.query(func.coalesce(func.sum(RefundRecord.refund_amount), 0)).filter(
        RefundRecord.order_id == order_id,
        RefundRecord.status.in_(_REFUND_OCCUPYING_STATUSES),
    )
    if exclude_id is not None:
        q = q.filter(RefundRecord.id != exclude_id)
    return Decimal(str(q.scalar() or 0))


def _remaining_refundable(order: ChargingOrder, occupied: Decimal) -> Decimal:
    """剩余可退 = 实付 − 已占用 (下限 0 防负)。"""
    return max(Decimal(str(order.paid_amount)) - occupied, Decimal("0"))


# ─── API 端点 ───

@router.post("/orders/{order_id}/settle")
def settle_order(order_id: int, body: SettleRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """结算订单 — 生成 fee_items 明细行并更新订单总额"""
    # team scoping（任务卡 1c19b59a）：订单归属校验前置，跨团队 → 404。
    try:
        assert_order_team_access(db, order_id, user)
        order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="充电订单不存在")

        # 清除旧明细（幂等：重复结算覆盖）
        db.query(OrderFeeItem).filter(OrderFeeItem.order_id == order_id).delete()

        fee_items: List[OrderFeeItem] = []
        total_amount = Decimal("0.00")

        # 1. 分时电费明细
        tou_pairs = [
            (FeeType.ELECTRICITY, "尖峰电费", body.peak_energy, body.peak_price, "kWh"),
            (FeeType.ELECTRICITY, "平段电费", body.flat_energy, body.flat_price, "kWh"),
            (FeeType.ELECTRICITY, "谷段电费", body.valley_energy, body.valley_price, "kWh"),
            (FeeType.ELECTRICITY, "深谷电费", body.trough_energy, body.trough_price, "kWh"),
        ]
        electricity_total = Decimal("0.00")
        energy_total = Decimal("0.00")
        for fee_type, name, kwh, price, unit in tou_pairs:
            if kwh > 0:
                amt = (Decimal(str(kwh)) * Decimal(str(price))).quantize(Decimal("0.01"))
                item = OrderFeeItem(
                    order_id=order_id, fee_type=fee_type, fee_name=name,
                    quantity=Decimal(str(kwh)), unit_price=Decimal(str(price)),
                    amount=amt, unit=unit,
                )
                fee_items.append(item)
                electricity_total += amt
                energy_total += Decimal(str(kwh))
        order.electricity_fee = electricity_total
        order.charged_kwh = energy_total

        # 2. 服务费
        if body.service_fee_rate > 0 and energy_total > 0:
            svc_amt = (energy_total * Decimal(str(body.service_fee_rate))).quantize(Decimal("0.01"))
            fee_items.append(OrderFeeItem(
                order_id=order_id, fee_type=FeeType.SERVICE, fee_name="服务费",
                quantity=energy_total, unit_price=Decimal(str(body.service_fee_rate)),
                amount=svc_amt, unit="kWh",
            ))
            total_amount += svc_amt
            order.service_fee = svc_amt
        else:
            order.service_fee = Decimal("0.00")

        total_amount += electricity_total

        # 3. 停车费
        if body.parking_hours > 0 and body.parking_rate > 0:
            pk_amt = (Decimal(str(body.parking_hours)) * Decimal(str(body.parking_rate))).quantize(Decimal("0.01"))
            fee_items.append(OrderFeeItem(
                order_id=order_id, fee_type=FeeType.PARKING, fee_name="停车费",
                quantity=Decimal(str(body.parking_hours)), unit_price=Decimal(str(body.parking_rate)),
                amount=pk_amt, unit="小时",
            ))
            total_amount += pk_amt
            order.parking_fee = pk_amt
        else:
            order.parking_fee = Decimal("0.00")

        # 4. 占桩费
        if body.occupancy_minutes > 0 and body.occupancy_rate > 0:
            oc_amt = (Decimal(str(body.occupancy_minutes)) * Decimal(str(body.occupancy_rate))).quantize(Decimal("0.01"))
            fee_items.append(OrderFeeItem(
                order_id=order_id, fee_type=FeeType.OCCUPANCY, fee_name="占桩费",
                quantity=Decimal(str(body.occupancy_minutes)), unit_price=Decimal(str(body.occupancy_rate)),
                amount=oc_amt, unit="分钟",
            ))
            total_amount += oc_amt
            order.occupancy_fee = oc_amt
            order.idle_penalty = oc_amt  # 兼容旧字段
        else:
            order.occupancy_fee = Decimal("0.00")

        # 5. 预约费
        if body.reservation_minutes > 0 and body.reservation_rate > 0:
            rv_amt = (Decimal(str(body.reservation_minutes)) * Decimal(str(body.reservation_rate))).quantize(Decimal("0.01"))
            fee_items.append(OrderFeeItem(
                order_id=order_id, fee_type=FeeType.RESERVATION, fee_name="预约费",
                quantity=Decimal(str(body.reservation_minutes)), unit_price=Decimal(str(body.reservation_rate)),
                amount=rv_amt, unit="分钟",
            ))
            total_amount += rv_amt
            order.reservation_fee = rv_amt
        else:
            order.reservation_fee = Decimal("0.00")

        # 分时电量写入
        order.peak_energy = Decimal(str(body.peak_energy))
        order.flat_energy = Decimal(str(body.flat_energy))
        order.valley_energy = Decimal(str(body.valley_energy))
        order.trough_energy = Decimal(str(body.trough_energy))

        # 优惠
        discount = Decimal(str(body.discount_amount)).quantize(Decimal("0.01"))
        coupon = Decimal(str(body.coupon_amount)).quantize(Decimal("0.01"))
        points = Decimal(str(body.points_amount)).quantize(Decimal("0.01"))

        order.total_amount = total_amount.quantize(Decimal("0.01"))
        order.discount_amount = discount
        order.coupon_amount = coupon
        order.points_amount = points

        paid = total_amount - discount - coupon - points
        order.paid_amount = paid if paid > 0 else Decimal("0.00")

        # 优惠明细行
        if discount > 0:
            fee_items.append(OrderFeeItem(
                order_id=order_id, fee_type=FeeType.DISCOUNT, fee_name="折扣优惠",
                quantity=Decimal("1"), unit_price=discount, amount=-discount, unit="元",
            ))
        if coupon > 0:
            fee_items.append(OrderFeeItem(
                order_id=order_id, fee_type=FeeType.COUPON, fee_name="优惠券抵扣",
                quantity=Decimal("1"), unit_price=coupon, amount=-coupon, unit="元",
            ))
        if points > 0:
            fee_items.append(OrderFeeItem(
                order_id=order_id, fee_type=FeeType.POINTS, fee_name="积分抵扣",
                quantity=Decimal("1"), unit_price=points, amount=-points, unit="元",
            ))

        db.add_all(fee_items)
        db.commit()
        db.refresh(order)

        return success_response({
            "order_id": order_id,
            "fee_items": [_fee_item_to_dict(i) for i in fee_items],
            "total_amount": float(order.total_amount),
            "discount_amount": float(order.discount_amount),
            "coupon_amount": float(order.coupon_amount),
            "points_amount": float(order.points_amount),
            "paid_amount": float(order.paid_amount),
        }, "结算成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("settle_order 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/orders/{order_id}/fee-items")
def list_fee_items(order_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """查看订单费用明细"""
    # team scoping（任务卡 1c19b59a）：订单归属校验前置，跨团队 → 404。
    try:
        assert_order_team_access(db, order_id, user)
        order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="充电订单不存在")
        items = db.query(OrderFeeItem).filter(OrderFeeItem.order_id == order_id).all()
        return success_response([_fee_item_to_dict(i) for i in items])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_fee_items 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/orders/{order_id}/refund")
def create_refund(order_id: int, body: RefundRequest, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """发起退款申请"""
    # team scoping（任务卡 1c19b59a）：订单归属校验前置，跨团队 → 404。
    try:
        assert_order_team_access(db, order_id, user)
        order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="充电订单不存在")

        if order.payment_status not in (OrderPaymentStatus.PAID, OrderPaymentStatus.PARTIAL):
            raise HTTPException(status_code=400, detail="订单未支付，无法退款")

        refund_amt = Decimal(str(body.refund_amount)).quantize(Decimal("0.01"))
        # 卡 75134a82: 校验剩余可退 (paid − 在途/已批/已退占用), 防跨笔累计超退。
        # 剩余可退 ≤ paid, 单笔超实付场景天然被覆盖。
        occupied = _occupied_refund_amount(db, order_id)
        remaining = _remaining_refundable(order, occupied)
        if refund_amt > remaining:
            raise HTTPException(
                status_code=400,
                detail=f"退款金额超过剩余可退金额 {remaining:.2f} 元（已扣除在途及已退款项）",
            )

        refund = RefundRecord(
            order_id=order_id,
            user_id=order.user_id,
            refund_amount=refund_amt,
            reason=body.reason,
            status=RefundStatus.PENDING,
            # 卡 aa88371f 缺陷2: 快照退款前支付状态, reject 时恢复 (PAID/PARTIAL 各归其位)
            prev_payment_status=order.payment_status.value if order.payment_status else None,
        )
        db.add(refund)

        # 更新订单支付状态为退款中
        order.payment_status = OrderPaymentStatus.REFUNDING

        db.commit()
        db.refresh(refund)
        return success_response(_refund_to_dict(refund), "退款申请已提交")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_refund 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/orders/refunds")
def list_all_refunds(
    status: Optional[str] = Query(None, description="退款状态过滤: pending/approved/refunded/rejected"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """全局退款记录列表 (卡 34ec1d55) — RefundRecord 审批记录跨订单分页视图。

    供前端退款历史页一次分页拉全量, 替代旧「先拉全部订单再逐单 GET /orders/{id}/refunds」
    的 N+1 千请求轰炸。注意: 本路由必须注册在 /orders/{order_id}/refunds 之前,
    否则 'refunds' 会被路径参数捕获为 order_id → 422。

    team scoping 对齐 financial.py 范式: 非 platform admin 经
    ChargingOrder.station_id → Station.team_id 过滤, 只见本队。
    """
    # 直接函数调用时默认值是 Query(...) 对象而非实际值, 先归一
    status_val = status if isinstance(status, str) else None
    page_val = page if isinstance(page, int) else 1
    page_size_val = page_size if isinstance(page_size, int) else 20
    if status_val is not None:
        try:
            status_enum = RefundStatus(status_val)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"非法退款状态: {status_val}")

    q = (
        db.query(RefundRecord, ChargingOrder, Station)
        .join(ChargingOrder, RefundRecord.order_id == ChargingOrder.id)
        .outerjoin(Station, ChargingOrder.station_id == Station.id)
    )
    if not is_platform_admin(user):
        q = q.filter(Station.team_id == user.team_id)
    if status_val is not None:
        q = q.filter(RefundRecord.status == status_enum)

    try:
        total = q.count()
        rows = (
            q.order_by(RefundRecord.created_at.desc(), RefundRecord.id.desc())
            .offset((page_val - 1) * page_size_val)
            .limit(page_size_val)
            .all()
        )
    except Exception:
        logger.exception("全局退款记录查询失败 user=%s", user.id)
        raise HTTPException(status_code=500, detail="查询失败")

    items = [
        {
            **_refund_to_dict(r),
            "order_no": o.order_no,
            "station_name": s.name if s else None,
        }
        for r, o, s in rows
    ]
    return success_response({"items": items, "total": total, "page": page_val, "page_size": page_size_val})


@router.get("/orders/{order_id}/refunds")
def list_refunds(order_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """查看订单退款记录"""
    # team scoping（任务卡 1c19b59a）：订单归属校验前置，跨团队 → 404。
    try:
        assert_order_team_access(db, order_id, user)
        order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="充电订单不存在")
        refunds = db.query(RefundRecord).filter(RefundRecord.order_id == order_id).all()
        return success_response([_refund_to_dict(r) for r in refunds])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_refunds 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/orders/{order_id}/refunds/{refund_id}/approve")
def approve_refund(order_id: int, refund_id: int, body: RefundReview, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """审批通过退款"""
    # team scoping（任务卡 1c19b59a）：订单归属校验前置（先于退款记录查找），跨团队 → 404。
    try:
        assert_order_team_access(db, order_id, user)
        now = datetime.now(timezone.utc)
        # 卡 75134a82: 审批前复核累计额度 — PENDING→APPROVED 间隙其它退款可能已消耗额度
        # (并发 create 竞态双 PENDING / 期间另一笔先完成)。口径含全部在途 PENDING 合计,
        # 对称拦截: 合计超 paid 时先审的一笔也不放行 (后审者无处可退)。
        target = db.query(RefundRecord).filter(
            RefundRecord.id == refund_id,
            RefundRecord.order_id == order_id,
        ).first()
        if not target:
            raise HTTPException(status_code=404, detail="退款记录不存在")
        if target.status != RefundStatus.PENDING:
            raise HTTPException(status_code=409, detail="退款状态已变更，无法审批（可能已被并发处理）")
        order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
        if order:
            occupied_by_others = _occupied_refund_amount(db, order_id, exclude_id=refund_id)
            remaining = _remaining_refundable(order, occupied_by_others)
            if Decimal(str(target.refund_amount)) > remaining:
                raise HTTPException(
                    status_code=400,
                    detail=f"退款金额超过剩余可退金额 {remaining:.2f} 元（已扣除在途及已退款项），无法审批",
                )
        # 卡 aa88371f 缺陷3+4: reviewer_id 取 token(user.id); 乐观锁 WHERE status=PENDING
        # 原子推进, 败者(记录不存在 / 状态已被并发改动) → 404 / 409。
        updated = db.query(RefundRecord).filter(
            RefundRecord.id == refund_id,
            RefundRecord.order_id == order_id,
            RefundRecord.status == RefundStatus.PENDING,
        ).update(
            {
                RefundRecord.status: RefundStatus.APPROVED,
                RefundRecord.reviewer_id: user.id,
                RefundRecord.reviewed_at: now,
            },
            synchronize_session=False,
        )
        if not updated:
            exists = db.query(RefundRecord.id).filter(
                RefundRecord.id == refund_id,
                RefundRecord.order_id == order_id,
            ).first()
            if not exists:
                raise HTTPException(status_code=404, detail="退款记录不存在")
            raise HTTPException(status_code=409, detail="退款状态已变更，无法审批（可能已被并发处理）")

        db.commit()
        refund = db.query(RefundRecord).filter(RefundRecord.id == refund_id).first()
        return success_response(_refund_to_dict(refund), "退款已批准")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("approve_refund 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/orders/{order_id}/refunds/{refund_id}/reject")
def reject_refund(order_id: int, refund_id: int, body: RefundReview, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """拒绝退款"""
    # team scoping（任务卡 1c19b59a）：订单归属校验前置，跨团队 → 404。
    try:
        assert_order_team_access(db, order_id, user)
        now = datetime.now(timezone.utc)
        # 卡 aa88371f 缺陷3+4: reviewer_id 取 token; 乐观锁 WHERE status=PENDING 原子推进。
        updated = db.query(RefundRecord).filter(
            RefundRecord.id == refund_id,
            RefundRecord.order_id == order_id,
            RefundRecord.status == RefundStatus.PENDING,
        ).update(
            {
                RefundRecord.status: RefundStatus.REJECTED,
                RefundRecord.reviewer_id: user.id,
                RefundRecord.reviewed_at: now,
                RefundRecord.reject_reason: body.reject_reason or "",
            },
            synchronize_session=False,
        )
        if not updated:
            exists = db.query(RefundRecord.id).filter(
                RefundRecord.id == refund_id,
                RefundRecord.order_id == order_id,
            ).first()
            if not exists:
                raise HTTPException(status_code=404, detail="退款记录不存在")
            raise HTTPException(status_code=409, detail="退款状态已变更，无法拒绝（可能已被并发处理）")

        db.commit()

        # 卡 aa88371f 缺陷2: 恢复退款前 payment_status 快照 (不再硬编码 REFUNDING→PAID)。
        # 仅当订单仍处退款中才恢复, 避免覆盖期间其它状态变更。
        refund = db.query(RefundRecord).filter(RefundRecord.id == refund_id).first()
        order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
        if order and order.payment_status == OrderPaymentStatus.REFUNDING:
            prev = refund.prev_payment_status
            if prev:
                try:
                    order.payment_status = OrderPaymentStatus(prev)
                except ValueError:
                    # 防御: 快照值非法时降级 PAID
                    order.payment_status = OrderPaymentStatus.PAID
            else:
                # 兼容无快照的历史数据: 降级 PAID
                order.payment_status = OrderPaymentStatus.PAID
            db.commit()

        return success_response(_refund_to_dict(refund), "退款已拒绝")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("reject_refund 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/orders/{order_id}/refunds/{refund_id}/complete")
def complete_refund(order_id: int, refund_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """标记退款已完成（到账）"""
    # team scoping（任务卡 1c19b59a）：订单归属校验前置，跨团队 → 404。
    try:
        assert_order_team_access(db, order_id, user)
        # 卡 aa88371f 缺陷4: SELECT...FOR UPDATE 行锁 — PG 防并发 complete 重复调渠道;
        # SQLite FOR UPDATE 为 no-op, 由 status 校验兜底(REFUNDED 后再次 complete → 409)。
        refund = db.query(RefundRecord).filter(
            RefundRecord.id == refund_id,
            RefundRecord.order_id == order_id,
        ).with_for_update().first()
        if not refund:
            raise HTTPException(status_code=404, detail="退款记录不存在")
        if refund.status != RefundStatus.APPROVED:
            raise HTTPException(
                status_code=409,
                detail=f"当前状态 {refund.status.value}，仅 approved 状态可完成退款",
            )

        order = db.query(ChargingOrder).filter(
            ChargingOrder.id == order_id
        ).with_for_update().first()

        # 卡 75134a82: 渠道打款前最后防线 — APPROVED 期间其它退款可能已先完成消耗额度,
        # 不足则拒绝且不调渠道, 状态保持 APPROVED 可人工处理 (改额/拒批)。
        if order:
            occupied_by_others = _occupied_refund_amount(db, order_id, exclude_id=refund_id)
            remaining = _remaining_refundable(order, occupied_by_others)
            if Decimal(str(refund.refund_amount)) > remaining:
                raise HTTPException(
                    status_code=400,
                    detail=f"退款金额超过剩余可退金额 {remaining:.2f} 元（已扣除在途及已退款项），无法完成退款",
                )

        # 卡 aa88371f 缺陷5: 先调IM-B退款(mock)拿渠道退款号 — 先于状态推进, 渠道失败则不完成。
        # 卡 692b3df7: process_refund 渠道异常返回结构化错误 dict (不裸抛), 据此映射 502
        # 并保持退款状态不变 (仍 APPROVED, 可重试), 不推进为 REFUNDED。
        # 卡 69fe6381: process_refund 已把幂等键 out_refund_no 写进 refund 对象
        # (复用已持久化号防重复打款); 失败路径抛 502 前先 commit 落库, 保证重试复用同号。
        channel_refund_no = wx_refund_service.process_refund(db, order=order, refund=refund)
        if isinstance(channel_refund_no, dict):
            if refund.out_refund_no:
                db.commit()
            raise HTTPException(
                status_code=502,
                detail=f"IM-B渠道退款失败: {channel_refund_no.get('error', '未知错误')}",
            )

        refund.status = RefundStatus.REFUNDED
        refund.refunded_at = datetime.now(timezone.utc)
        refund.channel_refund_no = channel_refund_no

        # 卡 aa88371f 缺陷1: 按 累计退款 vs 实付 判定 REFUNDED(≥) / PARTIAL(<),
        # 不再无条件置 REFUNDED。本次已置 REFUNDED, 显式 flush 后计入累计
        # (不依赖 autoflush — 部分 session/中间件 autoflush=False 会漏算本次)。
        if order:
            db.flush()
            total_refunded = db.query(
                func.coalesce(func.sum(RefundRecord.refund_amount), 0)
            ).filter(
                RefundRecord.order_id == order_id,
                RefundRecord.status == RefundStatus.REFUNDED,
            ).scalar() or Decimal("0")
            if Decimal(str(total_refunded)) >= Decimal(str(order.paid_amount)):
                order.payment_status = OrderPaymentStatus.REFUNDED
            else:
                order.payment_status = OrderPaymentStatus.PARTIAL

        db.commit()
        db.refresh(refund)
        return success_response(_refund_to_dict(refund), "退款已完成")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("complete_refund 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
