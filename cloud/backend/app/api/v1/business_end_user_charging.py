"""卡 089b01b2 — C端充电订单薄路由 (端侧 §7 路径, 无 /business 前缀).

端侧调用 (BASE_URL=/api/v1):
- POST /charging-orders/start-by-sn   扫码启动 (sn → 设备 → 建单 + OCPP RemoteStart)
- POST /charging-orders/{id}/pay      直接支付 (wx.requestPayment 五字段)
- POST /charging-orders/{id}/complete 完成充电 (StopTransaction → completed)

鉴权: get_current_end_user (aud=end_user); 运营 token / 匿名 → 401
      (enforce_auth 经 _END_USER_PATH_PREFIXES 放行, 端点级 end_user 依赖校验 aud).
复用: business_orders._create_order_impl / _stop_order_impl, business._prepay_impl
      (薄路由, 不重复造业务逻辑, 卡 089b01b2).
归属: ChargingOrder.user_id == end_user.id (契约 §8.5 end_user_id↔user_id 映射落地).
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.business import _prepay_impl
from app.api.v1.business_orders import _create_order_impl, _stop_order_impl
from app.api.v1.business_end_user_auth import get_current_end_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.charging_order import ChargingOrder, UserType
from app.models.device import Device
from app.models.end_user import EndUser
from app.services.wx_pay import response as rsp

router = APIRouter()


class StartBySnRequest(BaseModel):
    sn: str = Field(..., max_length=100, description="设备序列号 (扫码所得)")
    connector_id: Optional[int] = Field(1, ge=1, description="枪号, 默认 1")


class PayRequest(BaseModel):
    openid: str = Field(..., description="用户 openid")
    scene: Literal["miniprogram", "app"] = Field(
        "miniprogram", description="miniprogram=小程序 / app=移动应用"
    )


@router.post("/charging-orders/start-by-sn", summary="扫码启动充电 (端侧 §7.1)")
@limiter.limit("30/minute")
def start_by_sn(
    request: Request,
    body: StartBySnRequest,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    """扫码 → sn 查设备 → 建单 + OCPP RemoteStart (端侧简化: 仅 sn + 枪号).

    C端用户类型固定 APP (契约 §8.5). 设备不存在 → DEVICE_NOT_FOUND;
    其余建单约束 (connector 占用 / 僵尸清理 / 竞态) 复用 _create_order_impl.
    """
    device = db.query(Device).filter(Device.sn == body.sn).first()
    if device is None:
        return rsp.biz_error(rsp.CODE_DEVICE_NOT_FOUND)
    return _create_order_impl(
        db,
        user_id=end_user.id,
        user_type=UserType.APP,
        station_id=device.station_id,
        device_id=device.id,
        connector_id=body.connector_id,
    )


@router.post("/charging-orders/{order_id}/pay", summary="订单直接支付 (端侧 §2.1)")
@limiter.limit("30/minute")
def pay(
    request: Request,
    order_id: str,
    body: PayRequest,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    """统一下单 → wx.requestPayment 五字段 (复用 _prepay_impl).

    归属校验: 非本人订单 / 不存在 → ORDER_NOT_FOUND (不泄露存在性, 同 §7 口径).
    openid 唯一真相源: 已认证 EndUser.wx_openid, 禁止信任端侧 body.openid
    (契约 §8.5 / 卡 9bee42cc — 防伪造他人 openid 使支付主体脱钩).
    wx_openid 异常为空 → 受控 BIZ_ERROR, 不回退 body.openid.
    """
    order = (
        db.query(ChargingOrder)
        .filter(ChargingOrder.order_no == order_id)
        .first()
    )
    if order is None or order.user_id != end_user.id:
        return rsp.biz_error(rsp.CODE_ORDER_NOT_FOUND)
    if not end_user.wx_openid:
        return rsp.biz_error(rsp.CODE_BIZ_ERROR, "OPENID_MISSING")
    return _prepay_impl(db, order, end_user.wx_openid, body.scene)


@router.post("/charging-orders/{order_id}/complete", summary="完成充电 (端侧 §7.2)")
@limiter.limit("30/minute")
def complete(
    request: Request,
    order_id: str,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    """用户主动完成: OCPP StopTransaction → 计费 → completed (复用 _stop_order_impl).

    幂等: 终态订单返回当前状态; 非 charging → ORDER_NOT_CHARGING.
    """
    order = (
        db.query(ChargingOrder)
        .filter(ChargingOrder.order_no == order_id)
        .first()
    )
    if order is None or order.user_id != end_user.id:
        return rsp.biz_error(rsp.CODE_ORDER_NOT_FOUND)
    return _stop_order_impl(db, order)
