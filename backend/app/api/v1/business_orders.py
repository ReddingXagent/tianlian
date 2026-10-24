"""充电生命周期 API (用户端云端契约 §7, 卡 0a080df5)

挂 /business 前缀 (与 business.router / business_invoices.router 同前缀):
- POST /business/orders                   创建充电订单 (校验 connector 可用 + 无未完成订单 → 201)
- POST /business/orders/{order_id}/stop   停止充电 (OCPP StopTransaction mock → completed)
- GET  /business/orders/{order_id}/status 充电实时状态 (高频轮询)
- GET  /business/orders                   用户订单列表 (分页 + status/station/日期过滤)
- POST /business/orders/{order_id}/cancel 取消订单 (仅 pending)
- GET  /business/orders/{order_id}        完整明细 (§7.7, ?detail=full; 兼容 §2.3 轻量查询)

注意: GET /business/orders/{order_id} 同时承载 §2.3 轻量查询与 §7.7 完整明细 ——
该路由定义在 business.py (get_order), 由 ?detail=full 区分; 本模块不再重复定义,
避免 FastAPI 路由覆盖。本模块只实现 5 个新端点 + 1 个列表端点。

认证: C 端用户 token (get_current_user)。
响应: 用户端云端契约统一 code=0 (契约 §6); 业务错误 HTTP 200 + code!=0 + message=原因码。
金额: 模型存储元(Decimal), 响应里是分(整数); 时间存 UTC, 响应 ISO8601 +08:00。
OCPP: 当前阶段 RemoteStart/StopTransaction 用 mock (返回 accepted)。
"""
import logging
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError, IntegrityError as SAIntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
    PaymentMethod,
    UserType,
)
from app.models.device import Device, DeviceStatus
from app.models.enterprise import Enterprise
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.pricing_v2 import EnergyPrice, TimeSlotDefinition
from app.models.station import Station
from app.models.user import User
from app.services.enterprise_balance_service import (
    deduct_on_order_complete,
    InsufficientBalanceError,
    EnterpriseDeletedError,
)
from app.services import ocpp_dispatch
from app.services.order_cleanup_service import (
    cancel_stale_pending_for_connector,
    cancel_stale_pending_for_user,
)
from app.services.wx_pay import response as rsp
from app.services.wx_pay import payment as payment_svc

logger = logging.getLogger(__name__)
router = APIRouter()

# 东八区: 模型存 UTC, 响应转 +08:00 (契约示例 2026-08-08T14:30:00+08:00)
_CN_TZ = timezone(timedelta(hours=8))

# charging 状态: connector 被占用 / 用户有未完成订单
_ACTIVE_STATUSES = (OrderStatus.PENDING, OrderStatus.CHARGING)


# ========== Schemas ==========

class CreateOrderRequest(BaseModel):
    station_id: int = Field(..., ge=1, description="场站ID")
    device_id: int = Field(..., ge=1, description="充电设备ID")
    connector_id: int = Field(..., ge=1, description="枪号 (OCPP connectorId)")
    vehicle_id: Optional[int] = Field(None, description="车辆ID (已绑定车辆时传)")
    plate_number: Optional[str] = Field(None, max_length=20, description="车牌号")
    user_type: Literal["app", "card"] = Field("app", description="app=App用户 / card=刷卡用户")
    remark: Optional[str] = Field(None, max_length=500)


# ========== Helpers ==========

def _iso_cn(dt: Optional[datetime]) -> Optional[str]:
    """datetime(UTC) → ISO8601 +08:00 字符串; None 透传。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_CN_TZ).isoformat()


def _to_fen(amount) -> int:
    """元(Decimal/float) → 分(整数), 四舍五入。"""
    if amount is None:
        return 0
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1")))


def _to_num(v, default=None):
    """Decimal → float (响应数值字段); None 透传。"""
    if v is None:
        return default
    return float(v)


# 高频轮询接口 estimated_cost 无定价时的降级默认电价 (元/kWh)。
# 契约 §7.3: estimated_cost 基于已充电量 × 当前时段单价; 缺配置时用安全默认值兜底。
_DEFAULT_ENERGY_PRICE = Decimal("1.0")


def _current_slot_price(db: Session, station_id, now: datetime) -> Optional[Decimal]:
    """取站点当前生效时段的电价 (元/kWh)。

    查 station 当前生效(is_active + 日期窗口)的 EnergyPrice, 用对应 TimeSlotDefinition
    的窗口判断当前本地时刻落在哪个时段, 命中即返回其 price_per_kwh。

    Args:
        now: 带时区的当前时刻; 内部转东八区本地时钟与时段窗口对比 (时段定义是本地时钟)。

    Returns:
        命中时段的电价(Decimal); 无配置/未命中 → None (由调用方走降级默认费率)。
    """
    today = now.astimezone(_CN_TZ).date()
    rows = (
        db.query(EnergyPrice, TimeSlotDefinition)
        .join(TimeSlotDefinition, EnergyPrice.slot_id == TimeSlotDefinition.id)
        .filter(
            EnergyPrice.station_id == station_id,
            EnergyPrice.is_active.is_(True),
            TimeSlotDefinition.is_active.is_(True),
            EnergyPrice.effective_date <= today,
            (EnergyPrice.expire_date.is_(None)) | (EnergyPrice.expire_date >= today),
        )
        .all()
    )
    if not rows:
        return None

    # 当前本地时刻的 time, 用于和时段窗口比对。
    now_local = now.astimezone(_CN_TZ)
    today_local = now_local.date()
    for ep, slot in rows:
        window_start, window_end = _slot_window_local(today_local, slot.start_time, slot.end_time)
        if window_start <= now_local < window_end:
            return Decimal(str(ep.price_per_kwh))
    return None


def _slot_window_local(d: date, start_t: time, end_t: time):
    """时段在某天的本地窗口 [start, end), 处理跨午夜 (与 billing_engine._slot_window_on_date 同语义)。"""
    s = datetime.combine(d, start_t, tzinfo=_CN_TZ)
    if end_t > start_t:
        e = datetime.combine(d, end_t, tzinfo=_CN_TZ)
    elif end_t < start_t:
        e = datetime.combine(d + timedelta(days=1), end_t, tzinfo=_CN_TZ)
    else:  # start == end: 全天窗口
        e = datetime.combine(d + timedelta(days=1), start_t, tzinfo=_CN_TZ)
    return s, e


def _order_no_prefix() -> tuple[str, int]:
    """订单号前缀 + 起始序号: TL + YYYYMMDDHHmmss(14) + 3位序号。

    契约 §7.1 示例 TL20260808143000001。序号从 1 起, 同秒内预估递增;
    真正的唯一性由 order_no 唯一约束 + INSERT 重试兜底 (见 _persist_order)。
    """
    now = datetime.now(_CN_TZ)
    return f"TL{now.strftime('%Y%m%d%H%M%S')}", 1


def _own_order_biz_error() -> dict:
    """订单不存在/非本人的统一业务错误响应 (不泄露存在性)。

    卡 418a675a: 原为 raise HTTPException(404), 现按契约 §6 统一为
    biz_error —— stop/status/cancel/detail 四端点共用。
    """
    return rsp.biz_error(rsp.CODE_ORDER_NOT_FOUND)


def _get_own_order(db: Session, order_no: str, user: User) -> Optional[ChargingOrder]:
    """取本人订单; 不存在或非本人 → 返回 None (由调用方回 biz_error)。"""
    order = (
        db.query(ChargingOrder)
        .filter(ChargingOrder.order_no == order_no)
        .first()
    )
    if order is None or order.user_id != user.id:
        return None
    return order


def _station_name(db: Session, station_id: int) -> Optional[str]:
    st = db.query(Station).filter(Station.id == station_id).first()
    return st.name if st else None


def _resolve_enterprise_for_order(db: Session, order: ChargingOrder) -> Optional[Enterprise]:
    """经 vehicle_id / plate_number 关联查订单所属企业 (契约 §7.6)。

    C 端订单 payment_method 在停单时仍为 None, 无法凭支付方式判定企业用户;
    改由订单的车牌/车辆反查 enterprise_vehicles → Enterprise, 与运营端
    charging_orders.update_order_status 的关联口径一致。
    """
    enterprise = None
    if order.vehicle_id:
        ev = db.query(EnterpriseVehicle).filter(
            EnterpriseVehicle.id == order.vehicle_id
        ).first()
        if ev:
            enterprise = db.query(Enterprise).filter(
                Enterprise.id == ev.enterprise_id
            ).first()
    if not enterprise and order.plate_number:
        ev = db.query(EnterpriseVehicle).filter(
            EnterpriseVehicle.plate_number == order.plate_number
        ).first()
        if ev:
            enterprise = db.query(Enterprise).filter(
                Enterprise.id == ev.enterprise_id
            ).first()
    return enterprise


# 并发建单重试上限: 同一秒级前缀下序号 001..999, 5 次重试足以覆盖正常预估偏差;
# 超过即放弃 (回滚整笔事务) 由调用方决定 (此处为极小概率, 抛 500)。
_ORDER_NO_RETRY = 5

# OCPP 真下发失败码映射 (卡 87d6f7b9)。契约 §7.1 未规定 rejected/timeout 码,
# 沿用 rsp.biz_error(message=...) 大写助记符惯例。
_DISPATCH_ERROR_MESSAGES = {
    "rejected": "REJECTED",
    "offline": "OFFLINE",
    "timeout": "TIMEOUT",
}


def _persist_order(db: Session, build_order) -> ChargingOrder:
    """建单 + order_no 唯一约束竞态重试 (方案C)。

    build_order(order_no) -> ChargingOrder: 由调用方提供 (不含 order_no 之外的副作用)。
    流程: 预估起始序号 → INSERT flush → 撞唯一约束则 rollback 本次 INSERT
    → 序号+1 重试, 最多 5 次。

    并发场景两个请求同秒预估出同一序号, 第二个 INSERT 撞 idx_co_order_unique →
    重试拿到下一个序号成功; 避免了 count+1 模式的 check-then-act 竞态。

    用 db.rollback() 全回滚而非 savepoint: 调用前只有只读校验查询, 无未提交写操作,
    rollback 仅丢弃当前 pending INSERT, 安全; 且 SQLite + pysqlite 的 SAVEPOINT 在
    IntegrityError 后状态清理不可靠 (下一轮 begin_nested 会复抛旧错), 全回滚更稳。
    """
    prefix, start = _order_no_prefix()
    base_count = (
        db.query(ChargingOrder)
        .filter(ChargingOrder.order_no.like(f"{prefix}%"))
        .count()
    )
    for i in range(_ORDER_NO_RETRY):
        seq = base_count + start + i
        order_no = f"{prefix}{seq:03d}"
        order = build_order(order_no)
        db.add(order)
        try:
            db.flush()  # 触发 INSERT, 撞唯一约束在此抛 IntegrityError
        except IntegrityError as e:
            # 区分两类唯一约束冲突 (卡 d9bba836):
            # - order_no 冲突 (idx_co_order_no): 换序号重试即可。
            # - connector 活跃订单冲突 (uq_connector_active_order partial index): 不可重试,
            #   透传给 create_order 外层 catch 转 CONNECTOR_BUSY。否则会重试 5 次后误报 500。
            msg = str(getattr(e, "orig", e)).lower()
            if "order_no" in msg:
                db.rollback()  # 丢弃这条 pending INSERT → 下一轮换序号重试
                continue
            raise  # connector 竞态等不可重试冲突 → 上抛
        return order
    raise HTTPException(
        status_code=500,
        detail="订单号生成冲突, 请重试",
    )


# ─── OCPP 下发 (卡 87d6f7b9: 开关接线, 默认 mock) ───

def _ocpp_remote_start(device: Device, connector_id: int, user_id: Optional[int] = None) -> str:
    """OCPP RemoteStartTransaction 下发, 返回 DispatchResult。

    开关 OCPP_REMOTE_DISPATCH_ENABLED=false (默认): mock — 设备在线即 accepted,
    OFFLINE/FAULT → rejected (错误码沿用调用方映射, 与现状 OFFLINE/FAULT 前置
    校验互补)。开=true: 经 OCPPAdapter 真实下发, 真实结果。
    """
    if not ocpp_dispatch.dispatch_enabled():
        if device.status in (DeviceStatus.OFFLINE, DeviceStatus.FAULT):
            return "rejected"
        return "accepted"
    return ocpp_dispatch.remote_start(device, connector_id, str(user_id or ""))


def _ocpp_stop_transaction(order: ChargingOrder) -> str:
    """OCPP StopTransaction 下发, 返回 DispatchResult。mock 阶段始终 accepted。"""
    if not ocpp_dispatch.dispatch_enabled():
        return "accepted"
    return ocpp_dispatch.remote_stop(order)


# ========== 路由 ==========

def _create_order_impl(
    db: Session,
    *,
    user_id: int,
    user_type: UserType,
    station_id: int,
    device_id: int,
    connector_id: int,
    vehicle_id: Optional[int] = None,
    plate_number: Optional[str] = None,
    remark: Optional[str] = None,
):
    """创建充电订单核心逻辑 (设备校验 + 未完成订单守卫 + OCPP RemoteStart + 竞态建单),
    供 /business/orders 与 C端 POST /charging-orders/start-by-sn 复用 (卡 089b01b2)。

    归属用 user_id: 运营端点传 user.id, C端薄路由传 end_user.id
    (契约 §8.5 end_user_id ↔ ChargingOrder.user_id 映射)。
    返回 JSONResponse(201) / rsp.biz_error dict。
    """
    # 场站/设备存在性 (卡 418a675a: 统一 biz_error, 不再 404)
    station = db.query(Station).filter(Station.id == station_id).first()
    if station is None:
        return rsp.biz_error(rsp.CODE_STATION_NOT_FOUND)
    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.station_id == station_id)
        .first()
    )
    if device is None:
        return rsp.biz_error(rsp.CODE_DEVICE_NOT_FOUND)

    # 用户无未完成订单 (pending/charging)
    existing = (
        db.query(ChargingOrder)
        .filter(
            ChargingOrder.user_id == user_id,
            ChargingOrder.order_status.in_(_ACTIVE_STATUSES),
        )
        .first()
    )
    if existing is not None:
        # 防御: 若旧订单是 pending 且已超时 (charger 无 StartTransaction 确认的僵尸单,
        # 契约 §7.1), 自动取消后放行建新单; charging 状态是真实充电中, 绝不超时取消。
        if existing.order_status == OrderStatus.PENDING:
            cancel_stale_pending_for_user(db, user_id, timeout_minutes=10)
            db.refresh(existing)
            if existing.order_status == OrderStatus.CANCELLED:
                existing = None  # 旧单已清理, 放行
        if existing is not None:
            return rsp.biz_error(message="EXISTING_ORDER")

    # connector 可用性: 设备在线 (OFFLINE/FAULT 分别返回真实状态码,
    # 避免落进 _ocpp_remote_start 后误报 OFFLINE — 卡 a319f721 Bug1)
    if device.status == DeviceStatus.OFFLINE:
        return rsp.biz_error(message="OFFLINE")
    if device.status == DeviceStatus.FAULT:
        return rsp.biz_error(message="FAULT")
    # connector 占用: 同 device+connector 已有 active 订单
    busy = (
        db.query(ChargingOrder)
        .filter(
            ChargingOrder.device_id == device_id,
            ChargingOrder.connector_id == connector_id,
            ChargingOrder.order_status.in_(_ACTIVE_STATUSES),
        )
        .first()
    )
    if busy is not None:
        # 跨用户僵尸豁免 (卡 eb9f824b): 占桩若是他人超时 pending (RemoteStart 无
        # StartTransaction 确认), 即时清理后重查放行, 不等 5min beat 任务;
        # charging 是真实充电中, 清理函数只扫 pending, 绝不误伤。
        cancel_stale_pending_for_connector(
            db, device_id, connector_id, timeout_minutes=10
        )
        db.refresh(busy)
        if busy.order_status in _ACTIVE_STATUSES:
            return rsp.biz_error(message="CONNECTOR_BUSY")

    # OCPP RemoteStart 下发 (卡 87d6f7b9: 开关开启走适配器, rejected/offline/timeout 分码)
    result = _ocpp_remote_start(device, connector_id, user_id=user_id)
    if result != "accepted":
        return rsp.biz_error(message=_DISPATCH_ERROR_MESSAGES.get(result, "OFFLINE"))

    def _build(order_no: str) -> ChargingOrder:
        return ChargingOrder(
            order_no=order_no,
            station_id=station_id,
            device_id=device_id,
            user_id=user_id,
            user_type=user_type,
            vehicle_id=vehicle_id,
            plate_number=plate_number,
            connector_id=connector_id,
            payment_status=OrderPaymentStatus.UNPAID,
            order_status=OrderStatus.PENDING,
            remark=remark,
        )

    # DB 级竞态兜底 (卡 d9bba836): partial unique index uq_connector_active_order 在
    # PG READ COMMITTED 下抗真并发。_persist_order 透传 connector 冲突 IntegrityError →
    # 此处 catch 转 CONNECTOR_BUSY, 避免裸 500。
    try:
        order = _persist_order(db, _build)
    except SAIntegrityError:
        db.rollback()
        return rsp.biz_error(message="CONNECTOR_BUSY")
    # 并发二次检查: busy 查询与 INSERT 非原子, 两个并发请求可能在 check-then-act
    # 窗口同时通过首次 busy 查询。此处排除自身订单后再查一次, 命中则回滚拒绝。
    # (SQLite 单 writer 下该窗口虽窄, 仍以 fail-closed 语义兜底 — 卡 a319f721 Bug3)
    busy2 = (
        db.query(ChargingOrder)
        .filter(
            ChargingOrder.device_id == device_id,
            ChargingOrder.connector_id == connector_id,
            ChargingOrder.order_status.in_(_ACTIVE_STATUSES),
            ChargingOrder.id != order.id,
        )
        .first()
    )
    if busy2 is not None:
        db.rollback()
        return rsp.biz_error(message="CONNECTOR_BUSY")
    db.commit()
    db.refresh(order)

    return JSONResponse(
        status_code=201,
        content=rsp.ok({
            "order_id": order.order_no,
            "order_status": order.order_status.value,
            "payment_status": order.payment_status.value,
            "station_id": order.station_id,
            "station_name": _station_name(db, order.station_id),
            "device_id": order.device_id,
            "connector_id": order.connector_id,
            "created_at": _iso_cn(order.created_at),
        }),
    )


@router.post("/orders", summary="创建充电订单 (契约 §7.1)")
@limiter.limit("30/minute")
def create_order(
    request: Request,
    body: CreateOrderRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """扫码/选桩创建订单 + 下发 OCPP RemoteStart。

    校验: station/device 存在; connector 可用; 用户无未完成订单。成功 → 201 + pending。
    """
    try:
        ut = UserType(body.user_type)
    except ValueError:
        ut = UserType.APP
    return _create_order_impl(
        db,
        user_id=user.id,
        user_type=ut,
        station_id=body.station_id,
        device_id=body.device_id,
        connector_id=body.connector_id,
        vehicle_id=body.vehicle_id,
        plate_number=body.plate_number,
        remark=body.remark,
    )


def _stop_order_impl(db: Session, order: ChargingOrder):
    """停止充电核心逻辑 (OCPP StopTransaction → 计费 → completed + 企业扣款),
    供 /business/orders/{id}/stop 与 C端 POST /charging-orders/{id}/complete 复用 (卡 089b01b2)。

    归属校验由调用方完成: 运营端点用 _get_own_order(user.id),
    C端薄路由用 end_user.id (契约 §8.5 user_id 映射)。
    返回 rsp.ok / rsp.biz_error。
    """
    # 幂等: 终态订单直接返回当前状态 (不重复下发 StopTransaction)
    if order.order_status in (OrderStatus.COMPLETED, OrderStatus.FAILED, OrderStatus.CANCELLED):
        return rsp.ok({
            "order_id": order.order_no,
            "order_status": order.order_status.value,
            "charged_kwh": _to_num(order.charged_kwh, 0.0),
            "duration_minutes": order.duration_minutes or 0,
            "total_amount": _to_fen(order.total_amount),
            "stop_reason": order.stop_reason,
        })

    if order.order_status != OrderStatus.CHARGING:
        return rsp.biz_error(message="ORDER_NOT_CHARGING")

    # OCPP StopTransaction (卡 87d6f7b9: 开关开启走适配器, 失败保持 charging)
    result = _ocpp_stop_transaction(order)
    if result != "accepted":
        return rsp.biz_error(message=_DISPATCH_ERROR_MESSAGES.get(result, "REJECTED"))

    # 结算费用: 当前 mock 阶段订单费用由 ingestion/billing_engine 写入;
    # 此处补算 end_time/duration, 触发状态流转。费用明细字段保持已有值。
    now = datetime.now(timezone.utc)

    def _apply_completed(order):
        """end_time/duration/stop_reason/状态流转 (rollback 后可重放, 卡 84439ed8)。"""
        order.end_time = now
        if order.start_time:
            st = order.start_time
            if st.tzinfo is None:  # SQLite 不存 tzinfo, 视为 UTC
                st = st.replace(tzinfo=timezone.utc)
            delta = now - st
            order.duration_minutes = max(0, int(delta.total_seconds() // 60))
        order.stop_reason = "user_manual"
        order.order_status = OrderStatus.COMPLETED

    _apply_completed(order)

    # 契约 §7.6 企业/车队余额自动扣款 (卡 42ccb1a5):
    # 企业账户余额支付 → 余额扣减在服务端自动完成, 端侧不调 prepay,
    # payment_status 直接变 paid。检测当前订单是否关联企业 (经车牌/车辆反查),
    # 命中且未支付 → 原子扣款; 余额不足 → 保持 unpaid (用户可走IM-B支付)。
    if order.payment_status != OrderPaymentStatus.PAID:
        enterprise = _resolve_enterprise_for_order(db, order)
        if enterprise is not None:
            try:
                deduct_on_order_complete(db, order, enterprise)
                order.payment_method = PaymentMethod.ENTERPRISE
            except InsufficientBalanceError:
                # 余额不足: 订单照常完成, payment_status 保持 unpaid
                # (调用方统一 commit; deduct 内未产生落库写)。
                logger.info(
                    "企业 %s 余额不足, 订单 %s 保持 unpaid 待用户自付",
                    enterprise.id, order.order_no,
                )
            except EnterpriseDeletedError:
                # 删除竞态 (卡 84439ed8): 结算窗口内企业行被并发删除,
                # deduct 中断防白嫖。此时 OCPP stop 已 accepted, 订单绝不能
                # 卡 charging (重试 stop 会真 OCPP rejected → 永久卡死);
                # rollback 丢弃已暂存的 completed 变更 → 重放 → completed+unpaid,
                # 用户可走IM-B支付, 营收漏损留人工跟进。
                db.rollback()
                db.refresh(order)
                _apply_completed(order)
                logger.warning(
                    "企业 %s 结算时已被删除, 订单 %s 保持 unpaid 待人工跟进",
                    enterprise.id, order.order_no,
                )

    db.commit()
    db.refresh(order)

    return rsp.ok({
        "order_id": order.order_no,
        "order_status": order.order_status.value,
        "charged_kwh": _to_num(order.charged_kwh, 0.0),
        "duration_minutes": order.duration_minutes or 0,
        "total_amount": _to_fen(order.total_amount),
        "stop_reason": order.stop_reason,
    })


@router.post("/orders/{order_id}/stop", summary="停止充电 (契约 §7.2)")
@limiter.limit("30/minute")
def stop_order(
    request: Request,
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """用户主动停止: OCPP StopTransaction → 计算费用 → completed。

    幂等: 已 completed/failed/cancelled → 返回当前状态, 不重复下发。
    前置: 非 charging → code=1 ORDER_NOT_CHARGING。
    """
    order = _get_own_order(db, order_id, user)
    if order is None:
        return _own_order_biz_error()
    return _stop_order_impl(db, order)


@router.get("/orders/{order_id}/status", summary="充电实时状态 (契约 §7.3)")
@limiter.limit("60/minute")
def order_status(
    request: Request,
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """高频轮询: charged_kwh / SOC / power_kw / estimated_cost。"""
    order = _get_own_order(db, order_id, user)
    if order is None:
        return _own_order_biz_error()
    charging = order.order_status == OrderStatus.CHARGING

    # estimated_cost (分): 已充电量 × 当前时段单价 (契约 §7.3)
    # 取站点当前生效 TOU 电价; 无定价配置时降级默认费率 1.0 元/kWh + warning。
    estimated_cost = 0
    if order.charged_kwh:
        price = _current_slot_price(db, order.station_id, datetime.now(_CN_TZ))
        if price is None:
            logger.warning(
                "order %s station_id=%s 无生效 TOU 定价, estimated_cost 降级默认费率 %s 元/kWh",
                order.order_no, order.station_id, _DEFAULT_ENERGY_PRICE,
            )
            price = _DEFAULT_ENERGY_PRICE
        estimated_cost = _to_fen(Decimal(str(order.charged_kwh)) * price)

    # power_kw: 充电中取设备额定功率 (mock; 生产取实时遥测), 非充电中为 null
    power_kw = None
    if charging:
        dev = db.query(Device).filter(Device.id == order.device_id).first()
        power_kw = _to_num(dev.rated_power) if dev and dev.rated_power else None

    return rsp.ok({
        "order_id": order.order_no,
        "order_status": order.order_status.value,
        "charged_kwh": _to_num(order.charged_kwh, 0.0),
        "start_soc": _to_num(order.start_soc),
        # 充电中 end_soc 被遥测管线实时更新为当前SOC值; 订单完成后为最终SOC
        "current_soc": _to_num(order.end_soc),
        "duration_minutes": order.duration_minutes or 0,
        "power_kw": power_kw,
        "estimated_cost": estimated_cost,
        "start_time": _iso_cn(order.start_time),
        "updated_at": _iso_cn(order.updated_at),
    })


@router.get("/orders", summary="用户订单列表 (契约 §7.4)")
@limiter.limit("60/minute")
def list_orders(
    request: Request,
    status: Optional[str] = Query(None, description="pending/charging/completed/cancelled/failed"),
    station_id: Optional[int] = Query(None, description="场站过滤"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="截止日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前用户充电订单历史 (分页 + 多维过滤)。"""
    q = db.query(ChargingOrder).filter(ChargingOrder.user_id == user.id)

    if status:
        try:
            q = q.filter(ChargingOrder.order_status == OrderStatus(status))
        except ValueError:
            pass
    if station_id:
        q = q.filter(ChargingOrder.station_id == station_id)
    # 日期过滤 (按 UTC created_at; start/end 日期视为东八区当日边界)
    try:
        if start_date:
            d = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=_CN_TZ)
            q = q.filter(ChargingOrder.created_at >= d.astimezone(timezone.utc))
        if end_date:
            d = (datetime.strptime(end_date, "%Y-%m-%d")
                 + timedelta(days=1)).replace(tzinfo=_CN_TZ)
            q = q.filter(ChargingOrder.created_at < d.astimezone(timezone.utc))
    except ValueError:
        # 非法日期格式: 忽略过滤 (不报错, 与 status 一致)
        pass

    total = q.count()
    items = (
        q.order_by(ChargingOrder.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # 批量取 station_name
    station_ids = {o.station_id for o in items}
    name_map = {}
    if station_ids:
        for st in db.query(Station).filter(Station.id.in_(station_ids)).all():
            name_map[st.id] = st.name

    rows = []
    for o in items:
        rows.append({
            "order_id": o.order_no,
            "order_status": o.order_status.value,
            "payment_status": o.payment_status.value,
            "station_id": o.station_id,
            "station_name": name_map.get(o.station_id),
            "device_id": o.device_id,
            "connector_id": o.connector_id,
            "charged_kwh": _to_num(o.charged_kwh, 0.0),
            "total_amount": _to_fen(o.total_amount),
            "paid_amount": _to_fen(o.paid_amount),
            "start_time": _iso_cn(o.start_time),
            "end_time": _iso_cn(o.end_time),
            "duration_minutes": o.duration_minutes or 0,
            "created_at": _iso_cn(o.created_at),
        })

    return rsp.ok({"items": rows, "total": total, "page": page, "page_size": page_size})


@router.post("/orders/{order_id}/cancel", summary="取消订单 (契约 §7.5)")
@limiter.limit("30/minute")
def cancel_order(
    request: Request,
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """仅 pending 可取消 (充电未实际开始); 否则 code=1 CANNOT_CANCEL。"""
    order = _get_own_order(db, order_id, user)
    if order is None:
        return _own_order_biz_error()
    if order.order_status != OrderStatus.PENDING:
        return rsp.biz_error(message="CANNOT_CANCEL")

    order.order_status = OrderStatus.CANCELLED
    order.end_time = datetime.now(timezone.utc)
    # pending→cancelled: best-effort 撤销已 accepted 的 RemoteStart (卡 e18ce31e)。
    # pending 必经 create_order RemoteStart accepted (§7.1); 开关 false 时
    # remote_stop_best_effort 天然 no-op (零回归), 开关 true 走真下发, 失败仅记
    # 日志不阻塞取消、不回滚。下发走独立 adapter 不依赖本事务, 先于 commit 调用。
    ocpp_dispatch.remote_stop_best_effort(order)
    db.commit()
    db.refresh(order)
    return rsp.ok({
        "order_id": order.order_no,
        "order_status": order.order_status.value,
    })


def order_full_detail(db: Session, order: ChargingOrder) -> dict:
    """§7.7 完整明细 dict (充电 + 费用完整信息, 金额分)。供 business.get_order 复用。

    transaction_id/paid_at 与 §2.3 同语义 (卡 4b4a502a): IM-B交易号 + 支付完成时间,
    真相源是 PaymentOrder —— ChargingOrder.transaction_id 是 OCPP 事务号 (遥测
    幂等键), ChargingOrder 无 paid_at 列, 均不能直接进 C 端契约响应。无支付记录
    (如企业余额自动扣款) → 两者为 null。
    """
    po = payment_svc._pick_payment_row(db, order.order_no)
    return {
        "order_id": order.order_no,
        "order_status": order.order_status.value,
        "payment_status": order.payment_status.value,
        "station_id": order.station_id,
        "station_name": _station_name(db, order.station_id),
        "device_id": order.device_id,
        "connector_id": order.connector_id,
        "user_type": order.user_type.value if order.user_type else None,
        "plate_number": order.plate_number,
        "charged_kwh": _to_num(order.charged_kwh, 0.0),
        "electricity_fee": _to_fen(order.electricity_fee),
        "service_fee": _to_fen(order.service_fee),
        "parking_fee": _to_fen(order.parking_fee),
        "idle_penalty": _to_fen(order.idle_penalty),
        "total_amount": _to_fen(order.total_amount),
        "discount_amount": _to_fen(order.discount_amount),
        "paid_amount": _to_fen(order.paid_amount),
        "payment_method": order.payment_method.value if order.payment_method else None,
        "start_time": _iso_cn(order.start_time),
        "end_time": _iso_cn(order.end_time),
        "duration_minutes": order.duration_minutes or 0,
        "start_soc": _to_num(order.start_soc),
        "end_soc": _to_num(order.end_soc),
        "stop_reason": order.stop_reason,
        "transaction_id": po.wx_transaction_id if po else None,
        "paid_at": _iso_cn(po.paid_at) if po else None,
        "created_at": _iso_cn(order.created_at),
    }
