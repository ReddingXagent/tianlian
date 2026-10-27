"""
订单管理 API - 各类订单查询
GET /api/v1/operate/orders — 订单列表
GET /api/v1/operate/orders/enterprise — 企业充电订单
GET /api/v1/operate/orders/vehicle — 车辆充电订单
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response
from app.models.charging_order import ChargingOrder, OrderStatus, PaymentMethod
from app.models.order_fee_item import OrderFeeItem
from app.api.v1.order_fees import _fee_item_to_dict  # 复用明细行序列化,保持与 /orders/{id}/fee-items 一致
from app.models.spec_tables import OrderChargeCurve
from app.models.station import Station
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import (
    is_platform_admin,
    assert_station_team_access,
    assert_enterprise_team_access,
    assert_order_team_access,
)
from app.middleware.permission import require_write_permission
from app.services.charging_pricing import settle_charging_session

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/orders", summary="订单列表")
def list_orders(
    status: Optional[str] = Query(None),
    payment_status: Optional[str] = Query(None),
    station_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None, description="订单号/车牌号搜索"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """通用订单列表"""
    try:
        q = db.query(ChargingOrder)
        # team scoping（任务卡 ab5c5f17）：非 admin 仅返回本 team 站点的订单（经 station→team）。
        if not is_platform_admin(user):
            q = q.join(Station, ChargingOrder.station_id == Station.id) \
                 .filter(Station.team_id == user.team_id)
        if status:
            q = q.filter(ChargingOrder.order_status == status)
        if payment_status:
            q = q.filter(ChargingOrder.payment_status == payment_status)
        if station_id:
            # 非 admin 校验 station 归属本 team，越权站点 → 404（不泄露存在）。
            if not is_platform_admin(user):
                assert_station_team_access(db, station_id, user)
            q = q.filter(ChargingOrder.station_id == station_id)
        if keyword:
            q = q.filter(
                (ChargingOrder.order_no.ilike(f"%{keyword}%")) |
                (ChargingOrder.plate_number.ilike(f"%{keyword}%"))
            )
        if start_date:
            q = q.filter(ChargingOrder.created_at >= start_date)
        if end_date:
            q = q.filter(ChargingOrder.created_at < end_date)

        total = q.count()
        rows = q.order_by(ChargingOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        stations = {s.id: s.name for s in db.query(Station).all()}
        items = []
        for r in rows:
            items.append({
                "id": r.id,
                "order_no": r.order_no,
                "station_name": stations.get(r.station_id, f"站点#{r.station_id}"),
                "plate_number": r.plate_number,
                "user_type": r.user_type.value if r.user_type else None,
                "charged_kwh": float(r.charged_kwh) if r.charged_kwh else 0,
                "total_amount": float(r.total_amount) if r.total_amount else 0,
                "paid_amount": float(r.paid_amount) if r.paid_amount else 0,
                "discount_amount": float(r.discount_amount) if r.discount_amount else 0,
                "order_status": r.order_status.value if r.order_status else None,
                "payment_status": r.payment_status.value if r.payment_status else None,
                "payment_method": r.payment_method.value if r.payment_method else None,
                "duration_minutes": r.duration_minutes or 0,
                # 卡 f730f63c: 异常订单已处理标记(非空=已处理), 供前端列表显隐操作列。
                "abnormal_handle_type": r.abnormal_handle_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        return success_response({"items": items, "total": total, "page": page, "page_size": page_size})
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询订单列表失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/orders/enterprise", summary="企业充电订单")
def list_enterprise_orders(
    enterprise_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """企业维度充电订单"""
    try:
        # 企业订单 = 企业账户挂账支付 (payment_method=ENTERPRISE)。
        # 历史误用 user_type=='enterprise' 过滤, 但 UserType 枚举仅 app/card,
        # 'enterprise' 非其合法值 —— 脏数据写入该列会令 SAEnum 反序列化抛 LookupError → 500 (卡 6c7e252c)。
        # 真正标识"企业订单"的是支付方式而非用户身份载体。
        q = db.query(ChargingOrder).filter(ChargingOrder.payment_method == PaymentMethod.ENTERPRISE)
        # team scoping（任务卡 ab5c5f17）：非 admin 仅返回本 team 站点的订单（经 station→team）。
        if not is_platform_admin(user):
            q = q.join(Station, ChargingOrder.station_id == Station.id) \
                 .filter(Station.team_id == user.team_id)
        if enterprise_id:
            # 非 admin 校验企业归属本 team，越权 → 404（不泄露存在）。
            if not is_platform_admin(user):
                assert_enterprise_team_access(db, enterprise_id, user)
            q = q.filter(ChargingOrder.user_id == enterprise_id)

        total = q.count()
        rows = q.order_by(ChargingOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        items = []
        for r in rows:
            items.append({
                "id": r.id,
                "order_no": r.order_no,
                "plate_number": r.plate_number,
                "charged_kwh": float(r.charged_kwh) if r.charged_kwh else 0,
                "total_amount": float(r.total_amount) if r.total_amount else 0,
                "paid_amount": float(r.paid_amount) if r.paid_amount else 0,
                "electricity_fee": float(r.electricity_fee) if r.electricity_fee else 0,
                "service_fee": float(r.service_fee) if r.service_fee else 0,
                "order_status": r.order_status.value if r.order_status else None,
                "duration_minutes": r.duration_minutes or 0,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        return success_response({"items": items, "total": total, "page": page, "page_size": page_size})
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询企业充电订单失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/orders/vehicle", summary="车辆充电订单")
def list_vehicle_orders(
    plate_number: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按车辆查询充电订单"""
    try:
        q = db.query(ChargingOrder)
        # team scoping（任务卡 ab5c5f17）：非 admin 仅返回本 team 站点的订单（经 station→team）。
        if not is_platform_admin(user):
            q = q.join(Station, ChargingOrder.station_id == Station.id) \
                 .filter(Station.team_id == user.team_id)
        if plate_number:
            q = q.filter(ChargingOrder.plate_number.ilike(f"%{plate_number}%"))

        total = q.count()
        rows = q.order_by(ChargingOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        items = []
        for r in rows:
            items.append({
                "id": r.id,
                "order_no": r.order_no,
                "plate_number": r.plate_number,
                "charged_kwh": float(r.charged_kwh) if r.charged_kwh else 0,
                "total_amount": float(r.total_amount) if r.total_amount else 0,
                "paid_amount": float(r.paid_amount) if r.paid_amount else 0,
                "order_status": r.order_status.value if r.order_status else None,
                "duration_minutes": r.duration_minutes or 0,
                "start_time": r.start_time.isoformat() if r.start_time else None,
                "end_time": r.end_time.isoformat() if r.end_time else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        return success_response({"items": items, "total": total, "page": page, "page_size": page_size})
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询车辆充电订单失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/orders/{order_id}/charge-curve", summary="订单充电曲线")
def get_order_charge_curve(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """订单充电曲线 - 按分钟记录的功率/电压/电流/SOC 时间序列

    按 record_time 升序返回, 供前端绘制充电过程曲线图。
    订单无曲线数据时返回空 items (与订单列表风格一致, 不抛 404)。
    """
    try:
        # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 订单曲线；越权/不存在 → 404。
        assert_order_team_access(db, order_id, user)
        rows = (
            db.query(OrderChargeCurve)
            .filter(OrderChargeCurve.order_id == order_id)
            .order_by(OrderChargeCurve.record_time.asc())
            .all()
        )
        items = [
            {
                "record_time": r.record_time.isoformat() if r.record_time else None,
                "current_power": float(r.current_power) if r.current_power is not None else None,
                "energy_this_minute": float(r.energy_this_minute) if r.energy_this_minute is not None else None,
                "voltage": float(r.voltage) if r.voltage is not None else None,
                "current": float(r.current) if r.current is not None else None,
                "soc": float(r.soc) if r.soc is not None else None,
            }
            for r in rows
        ]
        return success_response({"order_id": order_id, "items": items, "total": len(items)})
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询订单充电曲线失败 order_id=%s", order_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


def _num(v) -> float:
    """Decimal/Numeric → float, None → 0(未结算订单各项费用为 0)。"""
    return float(v) if v is not None else 0


@router.get("/orders/{order_id}", summary="订单详情")
def get_order_detail(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """订单详情 — SPEC §2.2 计费明细(5项费用拆解)

    返回:
    - 订单基本信息(订单号/站点/用户/SOC/电表/电量/停止原因/状态)
    - fees: 5项费用结构化拆解(充电费/服务费/停车费/占桩费/预约费) + 优惠三项 + 总费用 + 实收金额
    - fee_items: 费用明细行(含分时电费/优惠行)

    路径校验: 必须位于 /orders/enterprise /orders/vehicle 之后,避免 {order_id} 捕获字面量子路径。
    """
    try:
        order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="充电订单不存在")
        # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 订单；越权 → 404（不泄露存在）。
        assert_order_team_access(db, order_id, user)

        items = db.query(OrderFeeItem).filter(OrderFeeItem.order_id == order_id).all()

        return success_response({
            # 基本信息
            "id": order.id,
            "order_no": order.order_no,
            "station_id": order.station_id,
            "device_id": order.device_id,
            "user_id": order.user_id,
            "user_type": order.user_type.value if order.user_type else None,
            "plate_number": order.plate_number,
            "charged_kwh": _num(order.charged_kwh),
            "start_soc": _num(order.start_soc),
            "end_soc": _num(order.end_soc),
            "start_meter": _num(order.start_meter),
            "end_meter": _num(order.end_meter),
            "duration_minutes": order.duration_minutes or 0,
            "stop_reason": order.stop_reason,
            "order_status": order.order_status.value if order.order_status else None,
            "payment_status": order.payment_status.value if order.payment_status else None,
            "payment_method": order.payment_method.value if order.payment_method else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            # 5项费用拆解 + 优惠 + 总费用 + 实收
            "fees": {
                "charge_fee": _num(order.electricity_fee),       # 充电费(电费)
                "service_fee": _num(order.service_fee),
                "parking_fee": _num(order.parking_fee),
                "occupancy_fee": _num(order.occupancy_fee),
                "reservation_fee": _num(order.reservation_fee),
                "total_amount": _num(order.total_amount),
                "paid_amount": _num(order.paid_amount),
                "discount_amount": _num(order.discount_amount),
                "coupon_amount": _num(order.coupon_amount),
                "points_amount": _num(order.points_amount),
            },
            # 费用明细行
            "fee_items": [_fee_item_to_dict(i) for i in items],
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询订单详情失败 order_id=%s", order_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


# ─── 异常订单操作闭环 (卡 f730f63c) ───

class ResolveRequest(BaseModel):
    """异常订单标记处理请求。

    handle_type 语义:
    - refunded     已走退款(联动 refunds 模块)
    - written_off  核销(费用无法追回, 账面抹平)
    - false_alarm  误报(经核查非异常, 仅留痕)
    """
    handle_type: Literal["refunded", "written_off", "false_alarm"]
    remark: Optional[str] = Field(None, max_length=500, description="处理备注")


@router.post(
    "/orders/{order_id}/resolve",
    summary="标记异常订单已处理",
    dependencies=[Depends(require_write_permission("charging:manage"))],
)
def resolve_abnormal_order(
    order_id: int,
    body: ResolveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """标记 failed/cancelled 异常订单的处理结果。

    幂等: 重复 resolve 覆盖更新 abnormal_handle_*, 不报错(同订单再次标记以最新为准)。
    """
    try:
        assert_order_team_access(db, order_id, user)
        order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="充电订单不存在")

        order.abnormal_handle_type = body.handle_type
        order.abnormal_handle_remark = body.remark
        order.abnormal_handled_at = datetime.now(timezone.utc)
        order.abnormal_handled_by = user.id
        db.commit()
        db.refresh(order)

        return success_response({
            "id": order.id,
            "order_no": order.order_no,
            "abnormal_handle_type": order.abnormal_handle_type,
            "abnormal_handle_remark": order.abnormal_handle_remark,
            "abnormal_handled_at": order.abnormal_handled_at.isoformat() if order.abnormal_handled_at else None,
            "abnormal_handled_by": order.abnormal_handled_by,
        }, "已标记处理")
    except HTTPException:
        raise
    except Exception:
        logger.exception("resolve_abnormal_order 异常 order_id=%s", order_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.post(
    "/orders/{order_id}/retry-charge",
    summary="重试计费(仅故障中断订单)",
    dependencies=[Depends(require_write_permission("charging:manage"))],
)
def retry_charge_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """对 failed 订单重跑费用计算, 生成/补全账单明细。

    复用 charging_pricing.settle_charging_session: 加载站点定价 → billing_engine 计算
    → settle_order_fees 写入(清旧明细重写, 幂等)。无定价走默认费率兜底, 不抛异常。

    状态机: 仅 FAILED 订单可重试(故障中断后补算账单); 非 FAILED → 409。
    """
    try:
        assert_order_team_access(db, order_id, user)
        order = db.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="充电订单不存在")

        if order.order_status != OrderStatus.FAILED:
            cur = order.order_status.value if order.order_status else None
            raise HTTPException(
                status_code=409,
                detail=f"仅故障中断(failed)订单可重试计费, 当前状态: {cur}",
            )

        # 时间兜底: failed 订单可能缺 end_time(中途中断), 用 created_at 保证 settle 不因 None 失败。
        start_time = order.start_time or order.created_at
        end_time = order.end_time or order.created_at
        charged_kwh = order.charged_kwh or Decimal("0")
        user_type_str = order.user_type.value if order.user_type else "app"

        result = settle_charging_session(
            db, order, start_time, end_time, charged_kwh,
            user_type_str=user_type_str,
        )
        # settle_charging_session 内部已 commit 成功; 仅当其自身异常兜底返回 error dict 时视为失败。
        if "error" in result:
            logger.warning("retry-charge 结算失败 order_id=%s: %s", order_id, result.get("error"))
            raise HTTPException(status_code=500, detail="重试计费失败, 请稍后重试")

        db.refresh(order)
        return success_response({
            "order_id": order_id,
            "energy_fee": float(result.get("energy_fee") or 0),
            "service_fee": float(result.get("service_fee") or 0),
            "parking_fee": float(result.get("parking_fee") or 0),
            "occupancy_fee": float(result.get("occupancy_fee") or 0),
            "reservation_fee": float(result.get("reservation_fee") or 0),
            "total_amount": float(order.total_amount or 0),
            "paid_amount": float(order.paid_amount or 0),
            "used_default": bool(result.get("used_default")),
        }, "重试计费成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("retry_charge_order 异常 order_id=%s", order_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")
