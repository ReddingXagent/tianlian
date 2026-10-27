"""
无人值守占位费 service (工作卡 f0db2036)

丁哥定调:
- 平台收「占位费」(占用充电车位的费用, 充满未挪车是核心场景), 不收停车费
- 占位费复用 billing_engine.compute_parking_fee_full(免费时长/小时费率/封顶/充电期间免除)
- 站点占位费率 = ParkingPrice(现有 parking pricing, 命名沿用避免破坏面)

职责:
1. compute_occupancy_minutes — 占位时长来源优先级(识别系统进出场 > 充电订单推算)
2. settle_occupancy_event    — 占位费计费联动(订单合并 / 独立账单 / 免费免除), 幂等
3. ingest_parking_event      — 事件 ingestion 入口(HTTP 端点 / 未来 MQTT handler 共用),
                               同站同车牌未离场幂等更新

占位费 = 占位时长 − 免费时段(免费时长 + 充电期间免除), 按站点费率计:
    compute_parking_fee_full(occupancy, rule, start, charging_exempt_minutes)["total"]
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.parking_event import (
    OccupancyEvent, OccupancyEventSource, OccupancyFeeStatus,
)
from app.models.charging_order import ChargingOrder
from app.models.order_fee_item import OrderFeeItem, FeeType
from app.models.pricing_v2 import ParkingPrice
from app.services.billing_engine import compute_parking_fee_full
from app.tasks.tz_utils import naive_utc_to_biz_wall

_logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


def _safe_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    """转 Decimal; None / 非法字符串 / NaN / Infinity → default(通常 0, 不多收费)。

    防御 DB 脏数据(直写/迁移残留致 Numeric 列为 None 或非法值): 旧实现
    Decimal(str(value)) 遇 None → Decimal('None') 抛 InvalidOperation, 穿透
    整单结算。与 billing_engine._safe_decimal 同语义, 本地拷贝避免跨 service
    反向依赖(occupancy 依赖 billing_engine 的纯函数, 不应再耦合其内部 helper)。
    负数原值透传(费率符号是配置语义, 由上层 fee<=0 判定处理, 不在此篡改)。
    """
    try:
        d = Decimal(str(value))
        if not d.is_finite():
            return Decimal(str(default))
        return d
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(str(default))

# 已终结的占位费状态(再 settle 即幂等返回, 不重算)
_TERMINAL_STATES = (
    OccupancyFeeStatus.BILLED, OccupancyFeeStatus.MERGED, OccupancyFeeStatus.EXEMPT,
)


def _wall(dt: datetime) -> datetime:
    """DB 读回的 naive-UTC 时间 → 业务时区 naive 墙钟 (卡 5a18d1ee)。

    本服务读的时间(parking_event.enter_at/exit_at, charging_order.start_time/end_time)
    落库口径均为 naive-UTC(列注释明示 / 卡 f7422bbc), billing_engine 纯函数按
    "业务时区墙钟"匹配 TOU 时段/夜间窗, 须先真换算到业务时区再 strip tz。
    旧实现 naive 直接"表面解释为上海墙钟"(墙钟数字不变) → UTC 墙钟被当上海墙钟,
    TOU 峰谷/夜间窗判定与订单窗口匹配整体错位 8h。
    aware 入参(测试/新调用方)同样经 naive_utc_to_biz_wall 归一(astimezone 语义一致)。
    """
    return naive_utc_to_biz_wall(dt)


def _utc_naive(dt: datetime) -> datetime:
    """任意 datetime → naive-UTC (与 DB 两表落库轴一致, 卡 5a18d1ee)。

    parking_event.enter_at/exit_at 与 charging_order.start_time/end_time 均
    naive-UTC 落库, 两者做 SQL 窗口相交比较必须同在 UTC 轴 — 旧实现把事件时间
    单侧换成上海墙钟再与 UTC 订单列比较, 匹配窗口错位 8h。
    naive 入参按 UTC 表面解释(读回即 UTC); aware 入参 astimezone 真换算。
    """
    from datetime import timezone as _tz
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(_tz.utc).replace(tzinfo=None)


def _overlap_minutes(a_start: datetime, a_end: datetime,
                     b_start: datetime, b_end: datetime) -> int:
    """两区间重叠分钟数(调用方保证已归一为同口径墙钟)。"""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    delta = (end - start).total_seconds() / 60
    return max(0, int(delta))


# ─────────────────────────────────────────────────────────
# 1. 占位时长来源优先级
# ─────────────────────────────────────────────────────────

def compute_occupancy_minutes(
    enter_at: datetime,
    exit_at: Optional[datetime],
    charging_order: Optional[ChargingOrder],
) -> Tuple[int, int]:
    """占位时长来源优先级 → (occupancy_minutes, charging_exempt_minutes)。

    ① exit_at 存在(识别系统进出场记录, 丁哥首选): occupancy = exit_at - enter_at
    ② 无 exit_at 有充电订单(推算): occupancy = order.end_time - order.start_time
    ③ 都无: (0, 0) 无法计费

    charging_exempt = 在场时间与充电订单时间窗重叠分钟(有订单时);
    充电期间免除占位费(车在充电, 理应免费占位)。

    返回的 occupancy/exempt 均为分钟整数(向下取整, 与 charging_sessions 时长口径一致)。
    """
    if enter_at is None:
        return 0, 0
    enter_w = _wall(enter_at)

    has_order_window = (
        charging_order is not None
        and charging_order.start_time is not None
        and charging_order.end_time is not None
    )

    # 占位时长: 识别记录优先, 回退充电订单推算
    if exit_at is not None:
        occ_enter, occ_exit = enter_w, _wall(exit_at)
    elif has_order_window:
        occ_enter = _wall(charging_order.start_time)
        occ_exit = _wall(charging_order.end_time)
    else:
        return 0, 0

    occupancy = max(0, int((occ_exit - occ_enter).total_seconds() // 60))

    # 免除: 充电期间与在场时间重叠
    charging_exempt = 0
    if has_order_window:
        charging_exempt = _overlap_minutes(
            occ_enter, occ_exit,
            _wall(charging_order.start_time), _wall(charging_order.end_time),
        )
    return occupancy, charging_exempt


# ─────────────────────────────────────────────────────────
# 2. 站点占位费率加载 + 充电订单匹配
# ─────────────────────────────────────────────────────────

def _load_parking_rule(db: Session, station_id: int,
                       enter_at: datetime) -> Optional[dict]:
    """加载站点占位费率(ParkingPrice, 丁哥: parking pricing 语义即占位费)。

    取进场业务日生效的最新一条(同 charging_pricing._load_parking_fee 选取口径:
    生效日降序 first-wins)。无可用费率 → None(调用方走"待配置"分支, 不默认收费)。

    enter_at=None → 无法判定业务日, 直接返回 None(BUG3 卡 9cc6bdad)。否则会跳过
    日期过滤, 穿透返回 ALL active rules(含 effective_date 在未来的未生效费率),
    误用未生效费率计费。
    """
    if enter_at is None:
        return None
    today = naive_utc_to_biz_wall(enter_at).date()  # naive-UTC 列真换算取业务日(卡 5a18d1ee)
    q = db.query(ParkingPrice).filter(
        ParkingPrice.station_id == station_id,
        ParkingPrice.is_active.is_(True),
        ParkingPrice.effective_date <= today,
        or_(ParkingPrice.expire_date.is_(None), ParkingPrice.expire_date >= today),
    )
    row = q.order_by(ParkingPrice.effective_date.desc(), ParkingPrice.id.desc()).first()
    if not row:
        return None
    return {
        "free_minutes": row.free_minutes or 0,
        # _safe_decimal: hourly_rate 为 None / 非法脏数据(直写绕过 NOT NULL) →
        # 降级 0, 不崩(旧实现 Decimal(str(None)) 抛 InvalidOperation 穿透结算)。
        "hourly_rate": _safe_decimal(row.hourly_rate),
        "daily_cap": _safe_decimal(row.daily_cap) if row.daily_cap is not None else None,
        "enable_night_rate": bool(row.enable_night_rate),
        "night_rate": _safe_decimal(row.night_rate) if row.night_rate is not None else None,
        "night_start": row.night_start,
        "night_end": row.night_end,
    }


def _match_charging_order(db: Session, event: OccupancyEvent) -> Optional[ChargingOrder]:
    """按 plate_number + station_id + 时间窗重叠匹配充电订单。

    匹配条件: 同站同车牌, 订单时间窗 [start, end] 与在场 [enter, exit) 相交
    (车在场期间发生充电)。取最近完成的一笔(end_time 最晚)。

    纯占位(无匹配订单) → 返回 None, 调用方走独立账单分支。

    时间归一化(BUG2 卡 9cc6bdad + 时区错位卡 5a18d1ee): filter 前对 enter_at/exit_at
    调 _utc_naive() 归一到 UTC 轴 — 事件列与订单列同为 naive-UTC 落库, 窗口
    相交比较必须同轴。旧实现换上海墙钟单侧比较 → 匹配窗口错位 8h。
    """
    enter_w = _utc_naive(event.enter_at) if event.enter_at else None
    exit_w = _utc_naive(event.exit_at) if event.exit_at else None
    q = db.query(ChargingOrder).filter(
        ChargingOrder.station_id == event.station_id,
        ChargingOrder.plate_number == event.plate_number,
        ChargingOrder.start_time.isnot(None),
        ChargingOrder.end_time.isnot(None),
    )
    if exit_w is not None:
        # 时间窗相交: order.start <= exit AND order.end >= enter
        q = q.filter(
            ChargingOrder.start_time <= exit_w,
            ChargingOrder.end_time >= enter_w,
        )
    else:
        # 未离场: 订单在进场后完成(车进场后充的电)
        q = q.filter(ChargingOrder.end_time >= enter_w)
    return q.order_by(ChargingOrder.end_time.desc()).first()


# ─────────────────────────────────────────────────────────
# 3. 占位费计费联动
# ─────────────────────────────────────────────────────────

def _merge_fee_into_order(db: Session, order: ChargingOrder, fee: Decimal) -> None:
    """占位费并入充电订单账单(绝对值覆盖语义, 幂等)。

    - 占位费按"绝对值覆盖": 查现有 PARKING 明细金额 existing,
      new_parking = (order.parking_fee - existing) + fee。
      → 同一笔事件重复 merge(TOCTOU 漏过状态检查, BUG4 卡 9cc6bdad) 仍为 fee,
        不累加翻倍; 正常单次调用 existing=0, 行为与旧累加语义一致。
    - order.total_amount 重算(= 电费 + 服务费 + 占位费 + 占桩费 + 预约费)
    - OrderFeeItem PARKING 明细: 删旧 + 写新(金额 == fee, 保证明细 == 本次事件占位费)
    - 不动 order.paid_amount(已收金额涉及支付渠道, 占位费并入后产生"应收 vs 已收"
      差额, 由后续补扣/对账处理, 不在此伪造已收)

    DB 写入路径异常保护: db.add/delete/flush 抛异常 → db.rollback() 回滚脏写 +
    re-raise(让上层端点决定响应, 但 session 已干净)。Decimal 转换用 _safe_decimal
    防订单/明细金额脏数据(None/非法字符串)不崩。
    """
    try:
        fee = _safe_decimal(fee).quantize(TWO_PLACES)

        # 查现有 PARKING 明细金额(绝对值覆盖的扣除基准)
        existing_rows = db.query(OrderFeeItem).filter(
            OrderFeeItem.order_id == order.id,
            OrderFeeItem.fee_type == FeeType.PARKING,
        ).all()
        existing_parking = sum(
            (_safe_decimal(i.amount) for i in existing_rows), Decimal("0"),
        )

        current_parking = _safe_decimal(order.parking_fee)
        # 扣除现有 PARKING 明细贡献, 换成新 fee(绝对值覆盖 → 重复调用幂等不翻倍)
        new_parking = (current_parking - existing_parking + fee).quantize(TWO_PLACES)
        order.parking_fee = new_parking

        total = (
            _safe_decimal(order.electricity_fee)
            + _safe_decimal(order.service_fee)
            + new_parking
            + _safe_decimal(order.occupancy_fee)
            + _safe_decimal(order.reservation_fee)
        ).quantize(TWO_PLACES)
        order.total_amount = total

        # PARKING 明细: 删旧 + 写新(金额 == fee, 保证明细 == 本次事件占位费绝对值)
        db.query(OrderFeeItem).filter(
            OrderFeeItem.order_id == order.id,
            OrderFeeItem.fee_type == FeeType.PARKING,
        ).delete()
        if fee != 0:
            db.add(OrderFeeItem(
                order_id=order.id, fee_type=FeeType.PARKING, fee_name="占位费",
                quantity=Decimal("1"), unit_price=fee, amount=fee, unit="元",
            ))
        db.flush()
    except Exception:
        # DB 写入异常(约束冲突/连接断/脏数据) → 回滚已 staged 的脏写, 保持 session 干净,
        # re-raise 让上层端点处理(占位费并入失败 → 端点 500, 但订单账单不被半改污染)。
        _logger.exception(
            "_merge_fee_into_order 失败 order=%s fee=%s, 已 rollback",
            getattr(order, "id", None), fee,
        )
        db.rollback()
        raise


def settle_occupancy_event(db: Session, event: OccupancyEvent) -> dict:
    """占位费计费联动(幂等)。

    状态机: PENDING → (BILLED | MERGED | EXEMPT)
        BILLED  纯占位独立账单(无充电订单, fee 落 event.fee_amount)
        MERGED  占位费并入充电订单账单(有匹配订单, 写 order.parking_fee + total + 明细)
        EXEMPT  免费时长内/充电期间全覆盖, fee=0
        PENDING 保持未计费(未离场 / 站点未配占位费率)

    幂等: 已终结状态(BILLED/MERGED/EXEMPT)再 settle 直接返回当前值, 不重算
    (防止重复上报/重复联动累加费用)。

    Returns:
        {fee_status, fee_amount, match_order_id, occupancy_minutes}
    """
    # TOCTOU 防御(BUG1 卡 9cc6bdad): 加行锁并重读权威状态, 防 check-then-act 双扣
    # (两并发事务都见 PENDING → 都进 _merge_fee_into_order → parking_fee 翻倍)。
    # 生产 PG with_for_update 阻塞并发事务直到本事务提交; SQLite FOR UPDATE no-op,
    # 但 populate_existing() 强制从 DB 重读, 以 DB 状态为准(另一事务已改 MERGED 则
    # 本次幂等返回)。SQLite 下并发由 BUG4 绝对值覆盖作应用层兜底。
    locked = (
        db.query(OccupancyEvent)
        .filter(OccupancyEvent.id == event.id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if locked is not None:
        event = locked

    # 幂等: 终结状态不重算
    if event.fee_status in _TERMINAL_STATES:
        return {
            "fee_status": event.fee_status.value,
            "fee_amount": Decimal(str(event.fee_amount or 0)),
            "match_order_id": event.match_order_id,
            "occupancy_minutes": event.occupancy_minutes or 0,
        }

    # 未离场 → 不结算(占位费在离场时结算; 丁哥: 识别系统发来起止时间)
    if event.exit_at is None:
        db.flush()
        return {
            "fee_status": OccupancyFeeStatus.PENDING.value,
            "fee_amount": Decimal("0.00"),
            "match_order_id": None,
            "occupancy_minutes": 0,
        }

    order = _match_charging_order(db, event)
    occupancy, charging_exempt = compute_occupancy_minutes(
        event.enter_at, event.exit_at, order)
    event.occupancy_minutes = occupancy

    if occupancy <= 0:
        # exit <= enter 异常数据 → 不计费
        db.flush()
        return {
            "fee_status": OccupancyFeeStatus.PENDING.value,
            "fee_amount": Decimal("0.00"),
            "match_order_id": order.id if order else None,
            "occupancy_minutes": 0,
        }

    rule = _load_parking_rule(db, event.station_id, event.enter_at)
    if rule is None:
        # 站点未配占位费率 → 不崩, 保持 PENDING(等运营配费率后重试)
        # 复用 charging_pricing 兜底口径: 占位费无定价 → 不默认收费(不兜默认费率)
        db.flush()
        return {
            "fee_status": OccupancyFeeStatus.PENDING.value,
            "fee_amount": Decimal("0.00"),
            "match_order_id": order.id if order else None,
            "occupancy_minutes": occupancy,
        }

    # 占位费 = 占位时长 − 免费时段(免费时长 + 充电期间免除), 按站点费率计
    try:
        fee = compute_parking_fee_full(
            occupancy, rule, start_time=_wall(event.enter_at),
            charging_exempt_minutes=charging_exempt,
        )["total"]
    except Exception:
        # billing_engine 异常 → 不崩结算, 保持 PENDING(与 charging_pricing 兜底同源)
        _logger.exception(
            "occupancy_fee 计费失败 event=%s station=%s, 保持 PENDING",
            event.id, event.station_id,
        )
        db.flush()
        return {
            "fee_status": OccupancyFeeStatus.PENDING.value,
            "fee_amount": Decimal("0.00"),
            "match_order_id": order.id if order else None,
            "occupancy_minutes": occupancy,
        }

    # 状态机写入段(DB 写入路径)异常保护: _merge_fee_into_order / db.flush 抛异常 →
    # rollback 脏写 + re-raise(订单账单与事件状态不被半改污染)。
    # 注: 上方 compute_parking_fee_full 的 try/except 是计费异常兜底(吞掉返回 PENDING),
    #     本段是 DB 写入异常兜底(re-raise), 两者职责不同, 不重叠。
    try:
        if fee <= 0:
            event.fee_status = OccupancyFeeStatus.EXEMPT
            event.fee_amount = Decimal("0.00")
        elif order is not None:
            _merge_fee_into_order(db, order, fee)
            event.fee_status = OccupancyFeeStatus.MERGED
            event.match_order_id = order.id
            event.fee_amount = fee
        else:
            event.fee_status = OccupancyFeeStatus.BILLED
            event.fee_amount = fee

        db.flush()
    except Exception:
        _logger.exception(
            "settle_occupancy_event 写入失败 event=%s station=%s, 已 rollback",
            getattr(event, "id", None), getattr(event, "station_id", None),
        )
        db.rollback()
        raise

    return {
        "fee_status": event.fee_status.value,
        "fee_amount": _safe_decimal(event.fee_amount).quantize(TWO_PLACES),
        "match_order_id": event.match_order_id,
        "occupancy_minutes": occupancy,
    }


# ─────────────────────────────────────────────────────────
# 4. 事件 ingestion 入口(HTTP / MQTT 共用)
# ─────────────────────────────────────────────────────────

def ingest_parking_event(
    db: Session,
    *,
    plate_number: str,
    station_id: int,
    enter_at: datetime,
    exit_at: Optional[datetime] = None,
    source: str = "alpr",
) -> OccupancyEvent:
    """占位事件 ingestion 入口。HTTP 端点与未来 MQTT handler 共用本函数
    (丁哥: MQTT 复用 gateway 设备接入; 现.gateway/mqtt.py 为出站适配器抽象,
    无 broker 订阅, 故当前主路径为 HTTP; 接 broker 后 handler 直接调本函数)。

    幂等:
    - 同站同车牌未离场(exit_at IS NULL)既有事件 → 更新它(首次离场重置状态触发计费)
    - 同站同车牌同进出场时间已离场事件 → 幂等返回(重复上报不新建)
    - 否则新建

    本函数只建/更新事件, 不计费(计费由调用方按 exit_at 非空调 settle_occupancy_event)。
    """
    try:
        src = OccupancyEventSource(source) if source else OccupancyEventSource.ALPR
    except ValueError:
        src = OccupancyEventSource.ALPR

    # DB 写入路径异常保护: query/add/flush 抛异常 → rollback 脏写 + re-raise
    # (事件半建/半更新不残留, session 干净, 上层端点决定响应)。
    try:
        # 1) 同站同车牌未离场事件 → 更新
        open_event = (
            db.query(OccupancyEvent)
            .filter(
                OccupancyEvent.plate_number == plate_number,
                OccupancyEvent.station_id == station_id,
                OccupancyEvent.exit_at.is_(None),
            )
            .order_by(OccupancyEvent.enter_at.desc())
            .first()
        )
        if open_event is not None:
            if exit_at is not None and open_event.exit_at is None:
                # 首次离场: 重置状态以触发计费
                open_event.exit_at = exit_at
                open_event.fee_status = OccupancyFeeStatus.PENDING
                open_event.fee_amount = Decimal("0.00")
                open_event.match_order_id = None
            elif exit_at is not None:
                open_event.exit_at = exit_at
            open_event.source = src
            db.flush()
            return open_event

        # 2) 完全相同的已离场事件(plate+station+enter+exit) → 幂等返回(重复上报)
        if exit_at is not None:
            dup = (
                db.query(OccupancyEvent)
                .filter(
                    OccupancyEvent.plate_number == plate_number,
                    OccupancyEvent.station_id == station_id,
                    OccupancyEvent.enter_at == enter_at,
                    OccupancyEvent.exit_at == exit_at,
                )
                .first()
            )
            if dup is not None:
                return dup

        # 3) 新建
        event = OccupancyEvent(
            plate_number=plate_number,
            station_id=station_id,
            enter_at=enter_at,
            exit_at=exit_at,
            source=src,
            fee_status=OccupancyFeeStatus.PENDING,
        )
        db.add(event)
        db.flush()
        return event
    except Exception:
        _logger.exception(
            "ingest_parking_event 失败 plate=%s station=%s, 已 rollback",
            plate_number, station_id,
        )
        db.rollback()
        raise
