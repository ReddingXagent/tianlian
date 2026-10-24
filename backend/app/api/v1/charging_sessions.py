"""
充电交易 ingestion 端点 (d018e3dc)

POST /api/v1/charging-sessions
云端 OCPP 交易接收 → 自动建单(completed) + billing_engine TOU 计费
+ 企业车辆匹配余额扣减, 闭合经营环。

鉴权复用 telemetry.get_current_gateway_or_user (X-API-Key 网关 / Bearer 用户)。
charge_point_id → Device.sn 映射站点; transaction_id+device 幂等; Wh→kWh全程 Decimal。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response
from app.models.charging_order import (
    ChargingOrder,
    OrderStatus,
    OrderPaymentStatus,
    PaymentMethod,
    UserType,
)
from app.models.device import Device
from app.models.enterprise import Enterprise
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.spec_tables import VinUser
from app.api.v1.telemetry import get_current_gateway_or_user
from app.api.v1.charging_orders import _order_to_dict, _generate_order_no
from app.services.charging_pricing import settle_charging_session
from app.services.enterprise_balance_service import (
    deduct_on_order_complete,
    InsufficientBalanceError,
    EnterpriseDeletedError,
)
from app.services.fleet_grant_service import is_device_authorized
from app.tasks.tz_utils import to_aware_biz_tz

_logger = logging.getLogger(__name__)

router = APIRouter()

WH_PER_KWH = Decimal("1000")


class ChargingSessionReport(BaseModel):
    """OCPP 充电交易上报载荷"""
    charge_point_id: str = Field(..., description="充电桩标识(映射 Device.sn / code)")
    connector_id: Optional[int] = Field(None, description="枪号(OCPP connectorId)")
    transaction_id: str = Field(..., description="OCPP transactionId, 幂等键")
    id_tag: Optional[str] = Field(None, description="用户标识(优先按 VIN 匹配)")
    meter_start: Optional[int] = Field(None, ge=0, description="起始电表读数(Wh)")
    meter_stop: Optional[int] = Field(None, ge=0, description="结束电表读数(Wh)")
    timestamp_start: datetime = Field(..., description="充电开始时间")
    timestamp_stop: datetime = Field(..., description="充电结束时间")
    reason: Optional[str] = Field(None, description="停止原因")
    station_id: Optional[int] = Field(None, description="可选, 覆盖设备所属站点")


def _resolve_device(
    db: Session, charge_point_id: str, station_id_override: Optional[int]
) -> tuple[Device, int]:
    """charge_point_id → Device(sn 优先, 回退 code)。找不到 → 404。"""
    device = db.query(Device).filter(Device.sn == charge_point_id).first()
    if not device:
        device = db.query(Device).filter(Device.code == charge_point_id).first()
    if not device:
        raise HTTPException(
            status_code=404, detail=f"充电桩不存在: {charge_point_id}"
        )
    return device, station_id_override or device.station_id


def _resolve_user(db: Session, id_tag: Optional[str]) -> tuple:
    """id_tag → 用户识别。

    匹配优先级: EnterpriseVehicle.vin(企业车) > VinUser.vin(个人) > 散客。

    Returns:
        (user_type, user_id, vehicle_id, plate_number, enterprise, pricing_user_type)
        - 企业车: user_type=CARD, vehicle_id=ev.id, enterprise, pricing 维度 "enterprise"
        - 个人VIN: user_type=APP, user_id=vin_user.user_id, pricing 维度 "vin"
        - 散客/无id_tag: 全 None, pricing 维度 "app"
    """
    if not id_tag:
        return None, None, None, None, None, "app"

    ev = db.query(EnterpriseVehicle).filter(EnterpriseVehicle.vin == id_tag).first()
    if ev:
        enterprise = (
            db.query(Enterprise).filter(Enterprise.id == ev.enterprise_id).first()
        )
        return (
            UserType.CARD, None, ev.id, ev.plate_number, enterprise, "enterprise",
        )

    vu = db.query(VinUser).filter(VinUser.vin == id_tag).first()
    if vu:
        return UserType.APP, vu.user_id, None, vu.plate_number, None, "vin"

    return None, None, None, None, None, "app"


def _utc_naive(dt: datetime) -> datetime:
    """任意 datetime 归一为 UTC-naive (SQL 绑定/落库口径, 与 monitor.py 同名惯例)。"""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


_SIBLING_WINDOW_SEC = 600  # 与 pending 超时阈值同量级, 降低与历史 cancelled 单误判


def _find_cancelled_pending_sibling(
    db: Session, device_id: int, connector_id: Optional[int], ts_start: datetime
) -> Optional[ChargingOrder]:
    """识别"被取消的 pending 单" (卡 e18ce31e; 时间窗 SQL 下推 卡 c669ce66)。

    同 device+connector 上, StartTransaction 上报时刻已存在且被 cancelled 的订单
    (pending→cancelled 两路径: 用户主动取消 cancel_order / 超时清理 order_cleanup)。
    命中即视为"取消后桩仍物理启动"的遗留 session, 交由调用方丢弃, 避免归属悬空
    (cancelled 单 + 新 completed 单共存)。

    时间窗已下推 SQL 层 (卡 c669ce66): created_at ∈ [ts_start-600s, ts_start]
    (闭区间: "取消单先于 session 开始存在" + 与 pending 超时同量级降误判),
    order_by(created_at.desc()).first() 取最近一条。不再 .all() 拉该设备全部
    历史 CANCELLED 单进内存逐条 Python 比较 —— 本函数在 StartTransaction ingest
    路径每次上报都调用, 历史取消单无界累积时为 O(历史取消单数) DB IO + ORM
    实例化, 已消除。

    naive-UTC 口径: created_at 列经 SQLite 返回 naive-UTC, SQL 绑定参数必须
    同为 naive-UTC (ts_start 经 _utc_naive 归一), 禁止 aware datetime 直接
    参与 SQL 过滤。

    等价性: 原 Python 循环语义 "created_at <= ts 且 ts ∈ [created_at,
    created_at+600s]" 数学上 ⟺ "created_at ∈ [ts-600s, ts]" (同一闭区间),
    按 created_at desc 取首条命中者, 与原实现严格等价。
    """
    ts_naive = _utc_naive(ts_start)
    window = timedelta(seconds=_SIBLING_WINDOW_SEC)
    q = db.query(ChargingOrder).filter(
        ChargingOrder.device_id == device_id,
        ChargingOrder.order_status == OrderStatus.CANCELLED,
        ChargingOrder.created_at >= ts_naive - window,
        ChargingOrder.created_at <= ts_naive,
    )
    if connector_id is not None:
        q = q.filter(ChargingOrder.connector_id == connector_id)
    return q.order_by(ChargingOrder.created_at.desc()).first()


@router.post(
    "/charging-sessions",
    dependencies=[Depends(get_current_gateway_or_user)],
)
def report_charging_session(
    body: ChargingSessionReport,
    db: Session = Depends(get_db),
):
    """接收云端充电交易 → 自动建单 + TOU 计费 + 企业扣款(幂等)。"""
    device, station_id = _resolve_device(db, body.charge_point_id, body.station_id)

    # ── 幂等: transaction_id + device 命中既有订单则直接返回 ──
    existing = (
        db.query(ChargingOrder)
        .filter(
            ChargingOrder.transaction_id == body.transaction_id,
            ChargingOrder.device_id == device.id,
        )
        .first()
    )
    if existing:
        return success_response(
            _order_to_dict(existing), "充电会话已存在(幂等, 未重建)"
        )

    # ── 电量 Wh→kWh (Decimal, 禁 float) ──
    charged_kwh = Decimal("0")
    if body.meter_start is not None and body.meter_stop is not None:
        wh = Decimal(str(body.meter_stop)) - Decimal(str(body.meter_start))
        if wh < 0:
            raise HTTPException(
                status_code=400, detail="meter_stop 不能小于 meter_start"
            )
        charged_kwh = (wh / WH_PER_KWH).quantize(Decimal("0.01"))

    # ── 入站时间归一(缺陷3) ──
    # timestamp_start/stop 可能 aware/naive 混传(OCPP 上报来源不一), 直接做差会抛
    # "can't subtract offset-naive and offset-aware datetimes" → 500。统一按业务时区
    # 转 aware: aware→astimezone, naive→贴业务时区表面解释。后续时长/存库/定价基准日均
    # 用归一值, 口径一致。
    ts_start = to_aware_biz_tz(body.timestamp_start)
    ts_stop = to_aware_biz_tz(body.timestamp_stop)

    # ── 时长 ──
    duration_minutes = int((ts_stop - ts_start).total_seconds() // 60)
    if duration_minutes < 0:
        raise HTTPException(
            status_code=400, detail="timestamp_stop 不能早于 timestamp_start"
        )

    # ── 归属识别 (卡 e18ce31e): 桩物理启动后的 StartTransaction 上报, 若该桩枪上
    # 存在已 cancelled 的 pending 单 (用户取消/超时清理, RemoteStop 未及时撤销桩侧
    # 启动), 则丢弃本次 session 不建 completed 单, 避免 cancelled 单 + 新 completed
    # 单归属悬空。仅 warning 审计, 不转 charging。 ──
    sibling = _find_cancelled_pending_sibling(
        db, device.id, body.connector_id, ts_start
    )
    if sibling is not None:
        _logger.warning(
            "StartTransaction 丢弃: 订单 %s 已取消(reason=remote_stop_pending_cancel) "
            "charge_point_id=%s connector_id=%s transaction_id=%s",
            sibling.order_no, body.charge_point_id, body.connector_id,
            body.transaction_id,
        )
        return success_response(
            None,
            "StartTransaction 已丢弃: 对应订单已取消(remote_stop_pending_cancel), 不转 charging",
        )

    # ── 用户识别 ──
    (
        user_type, user_id, vehicle_id, plate_number,
        enterprise, pricing_user_type,
    ) = _resolve_user(db, body.id_tag)

    # ── 车队三级授权 scope 校验 (卡 a1468299) ──
    # 仅企业车受约束; 散客/无enterprise 跳过(向后兼容)
    if enterprise:
        allowed, reason = is_device_authorized(db, enterprise.id, device)
        if not allowed:
            raise HTTPException(status_code=403, detail=reason)

    # ── 建单 (completed, 计费前) ──
    # 卡 f7422bbc: start/end_time 落库统一 naive-UTC (与其余写入口径一致 —
    # charging_orders/business_orders/order_cleanup 全存 UTC naive)。ts_start/ts_stop
    # 保持 aware biz-tz 变量不变: 计费 settle_charging_session 依赖 aware 归一取业务日。
    ts_start_utc = ts_start.astimezone(timezone.utc).replace(tzinfo=None)
    ts_stop_utc = ts_stop.astimezone(timezone.utc).replace(tzinfo=None)
    order = ChargingOrder(
        order_no=_generate_order_no(db),
        station_id=station_id,
        device_id=device.id,
        user_id=user_id,
        user_type=user_type,
        vehicle_id=vehicle_id,
        plate_number=plate_number,
        transaction_id=body.transaction_id,
        connector_id=body.connector_id,
        start_time=ts_start_utc,
        end_time=ts_stop_utc,
        duration_minutes=duration_minutes,
        start_meter=Decimal(str(body.meter_start)) if body.meter_start is not None else None,
        end_meter=Decimal(str(body.meter_stop)) if body.meter_stop is not None else None,
        stop_reason=body.reason,
        charged_kwh=charged_kwh,
        payment_status=OrderPaymentStatus.UNPAID,
        order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.ENTERPRISE if enterprise else None,
    )
    db.add(order)
    try:
        db.commit()
    except IntegrityError:
        # 并发竞态: 同 transaction_id+device 两请求同时过前置查询,
        # 第二个 INSERT 撞唯一索引(idx_co_tx_device) → 回查既有单返回(幂等语义)。
        # 回查不到(如对手单被删)才 409, 禁裸抛 500。
        db.rollback()
        existing = (
            db.query(ChargingOrder)
            .filter(
                ChargingOrder.transaction_id == body.transaction_id,
                ChargingOrder.device_id == device.id,
            )
            .first()
        )
        if existing:
            return success_response(
                _order_to_dict(existing), "充电会话已存在(并发竞态, 复用既有单)"
            )
        raise HTTPException(
            status_code=409,
            detail="concurrent insert conflict, existing order not found",
        )
    db.refresh(order)

    # ── billing_engine TOU 计费 (有电量才计; 兜底不崩) ──
    if charged_kwh > 0:
        try:
            settle_charging_session(
                db, order,
                start_time=ts_start,
                end_time=ts_stop,
                charged_kwh=charged_kwh,
                user_type_str=pricing_user_type,
            )
        except Exception:
            _logger.exception(
                "charging_session settle 失败 order=%s(订单已建, 费用保持 0)",
                order.order_no,
            )
            db.rollback()
            db.refresh(order)
        else:
            # settle 不内部 commit (提交边界交由调用方), 此处先落库费用,
            # 防止后续企业扣款分支 rollback 把 pending 费用一并抹掉 (卡 8772b963)。
            db.commit()
            db.refresh(order)

    # ── 企业余额扣款 (completed + 匹配到企业) ──
    # 幂等守卫: 订单已 PAID(重复结算/重试/重复 webhook) → 跳过, 避免双扣
    # (deduct_on_order_complete 内亦有同款守卫, 此处提前避免无谓事务)
    deduction_msg = ""
    if (
        enterprise
        and order.paid_amount
        and order.paid_amount > 0
        and order.payment_status != OrderPaymentStatus.PAID
    ):
        try:
            tx = deduct_on_order_complete(db, order, enterprise)
            db.commit()
            db.refresh(order)
            if tx:
                deduction_msg = f", 企业余额扣减 {float(tx.amount):.2f} 元"
        except InsufficientBalanceError:
            # 余额不足 (卡 8772b963): 对齐 business_orders 语义 —
            # 订单照常 completed, 费用保留(已在 settle 后 commit),
            # payment_status 保持 unpaid, 会话 200, 不再 402。
            db.rollback()
            db.refresh(order)
            _logger.info(
                "企业 %s 余额不足, 订单 %s 保持 unpaid 待人工跟进",
                enterprise.id, order.order_no,
            )
        except EnterpriseDeletedError:
            # 删除竞态 (卡 84439ed8): 结算窗口内企业行被并发删除,
            # deduct 中断防白嫖。回滚后订单保持 completed+unpaid,
            # 会话照常 200, 营收漏损留人工跟进。
            db.rollback()
            db.refresh(order)
            _logger.warning(
                "企业 %s 结算时已被删除, 订单 %s 保持 unpaid 待人工跟进",
                enterprise.id, order.order_no,
            )

    msg = "充电会话已接收并结算"
    if not charged_kwh:
        msg = "充电会话已接收(零电量, 未计费)"
    return success_response(_order_to_dict(order), msg + deduction_msg)
