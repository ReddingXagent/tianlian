"""
无人值守占位费自动化 — 占位费 service 测试 (工作卡 f0db2036)

丁哥定调(不可违反):
- 平台收的是「占位费」(占用充电车位的费用, 尤其充满未挪车), 不是停车费
- 本地车牌识别系统是外部系统, 发来最终数据(车牌+起止时间), 平台不做识别
- 占位费复用 billing_engine.compute_parking_fee_full(免费时长/小时费率/封顶/充电期间免除)

覆盖:
① 占位时长来源优先级: 识别系统进出场 > 充电订单推算
② 占位费计费: 复用 compute_parking_fee_full(免费时段 + 充电期间免除)
③ 事件幂等: 同站同车牌未离场更新 / 同一离场事件重复上报只计一次
④ 订单合并: 有充电订单 → 占位费并入订单账单(order.parking_fee + total + 明细)
⑤ 独立账单: 纯占位(无充电订单) → event 自身承载(fee_status=BILLED)
⑥ 免费时长内 → EXEMPT

全程 Decimal; 断言落在真实费用数值, 禁弱断言。
"""
from datetime import datetime
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """注入 test_db(override SessionLocal + seed admin), 每测试独立 DB。"""
    pass


# ─── 种子 helpers ───

def _seed_station(session, code="STOCC01"):
    from app.models.station import Station, StationStatus
    st = Station(name="占位费测试站", code=code, address="测试地址",
                 status=StationStatus.NORMAL)
    session.add(st); session.commit(); session.refresh(st)
    return st


def _seed_parking_price(session, station_id, *, free_minutes=30, hourly_rate=6.0,
                        daily_cap=None, enable_night_rate=False, night_rate=None,
                        night_start=None, night_end=None):
    """站点占位费率(ParkingPrice, 丁哥定调: 现有 parking pricing 语义即占位费)。"""
    from datetime import date
    from app.models.pricing_v2 import ParkingPrice
    pp = ParkingPrice(
        station_id=station_id, free_minutes=free_minutes,
        hourly_rate=Decimal(str(hourly_rate)), daily_cap=(
            Decimal(str(daily_cap)) if daily_cap is not None else None),
        enable_night_rate=enable_night_rate,
        night_rate=(Decimal(str(night_rate)) if night_rate is not None else None),
        night_start=night_start, night_end=night_end,
        effective_date=date(2026, 1, 1), is_active=True,
    )
    session.add(pp); session.commit()
    return pp


def _seed_charging_order(session, station_id, plate="京A12345",
                         start=datetime(2026, 7, 28, 10, 0, 0),
                         end=datetime(2026, 7, 28, 12, 0, 0)):
    """一笔已结算的充电订单(parking_fee=0, 占位费联动前)。"""
    from app.models.charging_order import (
        ChargingOrder, OrderStatus, OrderPaymentStatus,
    )
    o = ChargingOrder(
        order_no="OCC-ORDER-001", station_id=station_id, device_id=1,
        plate_number=plate, start_time=start, end_time=end,
        duration_minutes=120, charged_kwh=Decimal("20.00"),
        electricity_fee=Decimal("16.00"), service_fee=Decimal("10.00"),
        parking_fee=Decimal("0.00"), occupancy_fee=Decimal("0.00"),
        reservation_fee=Decimal("0.00"), total_amount=Decimal("26.00"),
        paid_amount=Decimal("26.00"), order_status=OrderStatus.COMPLETED,
        payment_status=OrderPaymentStatus.UNPAID,
    )
    session.add(o); session.commit(); session.refresh(o)
    return o


# ═══════════════════════════════════════════════════════════════
# ① 占位时长来源优先级
# ═══════════════════════════════════════════════════════════════

def test_occupancy_minutes_prefers_alpr_record():
    """识别系统进出场记录优先: exit_at-enter_at, 即便有充电订单也以识别记录为准。

    充电期间(订单时间窗)与在场时间重叠部分计入 charging_exempt(免除占位费)。
    """
    from app.services.occupancy_fee_service import compute_occupancy_minutes

    enter = datetime(2026, 7, 28, 10, 0, 0)
    exit_ = datetime(2026, 7, 28, 13, 0, 0)  # 在场 180min

    class _Ord:
        start_time = datetime(2026, 7, 28, 10, 0, 0)
        end_time = datetime(2026, 7, 28, 12, 0, 0)  # 充电 120min

    occupancy, exempt = compute_occupancy_minutes(enter, exit_, _Ord())
    assert occupancy == 180                          # 识别记录: 10:00-13:00
    assert exempt == 120                             # 充电期间重叠 10:00-12:00


def test_occupancy_minutes_falls_back_to_charging_estimate():
    """无识别系统离场记录 → 用充电订单推算占位时长(全部视为充电期间, 免除)。"""
    from app.services.occupancy_fee_service import compute_occupancy_minutes

    enter = datetime(2026, 7, 28, 10, 0, 0)

    class _Ord:
        start_time = datetime(2026, 7, 28, 10, 0, 0)
        end_time = datetime(2026, 7, 28, 12, 0, 0)  # 推算 120min

    occupancy, exempt = compute_occupancy_minutes(enter, None, _Ord())
    assert occupancy == 120
    assert exempt == 120                             # 推算窗口 == 充电窗口, 全免除


def test_occupancy_minutes_no_data_returns_zero():
    """既无离场记录也无充电订单 → 无法计费。"""
    from app.services.occupancy_fee_service import compute_occupancy_minutes
    occupancy, exempt = compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0, 0), None, None)
    assert (occupancy, exempt) == (0, 0)


# ═══════════════════════════════════════════════════════════════
# ② 占位费计费 — 复用 compute_parking_fee_full(充满后未挪车核心场景)
# ═══════════════════════════════════════════════════════════════

def test_settle_merged_into_order(test_db):
    """有充电订单 → 占位费并入订单账单。

    在场 10:00-13:00(180min), 充电 10:00-12:00(120min), free=30min, rate=6/h。
    充满(12:00)后未挪车至 13:00 → billable = 180-30(free)-120(充电免除) = 30min。
    占位费 = 30/60 * 6 = 3.00 元 → 并入 order.parking_fee + total + PARKING 明细。
    """
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s)
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0)
    order = _seed_charging_order(s, st.id)  # 充电 10:00-12:00, total=26.00

    event = OccupancyEvent(
        plate_number="京A12345", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=datetime(2026, 7, 28, 13, 0, 0),
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["fee_status"] == "merged"
    assert result["fee_amount"] == Decimal("3.00")
    assert result["match_order_id"] == order.id
    assert result["occupancy_minutes"] == 180

    # 订单账单并入
    s.refresh(order)
    assert order.parking_fee == Decimal("3.00")
    assert order.total_amount == Decimal("29.00")     # 26 + 3
    assert event.fee_status == OccupancyFeeStatus.MERGED
    assert event.match_order_id == order.id
    assert event.fee_amount == Decimal("3.00")

    # PARKING 明细行
    from app.models.order_fee_item import OrderFeeItem, FeeType
    parking_items = [i for i in s.query(OrderFeeItem).filter(
        OrderFeeItem.order_id == order.id).all() if i.fee_type == FeeType.PARKING]
    assert len(parking_items) == 1
    assert parking_items[0].amount == Decimal("3.00")


def test_settle_standalone_billed(test_db):
    """纯占位(无充电订单) → 独立账单, event 自身承载 fee。

    在场 10:00-12:00(120min), 无订单, free=30min, rate=6/h。
    billable = 120-30 = 90min → fee = 90/60*6 = 9.00 元。fee_status=BILLED。
    """
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s)
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0)

    event = OccupancyEvent(
        plate_number="京B88888", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=datetime(2026, 7, 28, 12, 0, 0),
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["fee_status"] == "billed"
    assert result["fee_amount"] == Decimal("9.00")
    assert result["match_order_id"] is None
    assert event.fee_status == OccupancyFeeStatus.BILLED
    assert event.fee_amount == Decimal("9.00")


def test_settle_exempt_within_free_minutes(test_db):
    """免费时长内 → fee=0, fee_status=EXEMPT。在场 20min < free 30min。"""
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s)
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0)

    event = OccupancyEvent(
        plate_number="京C77777", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=datetime(2026, 7, 28, 10, 20, 0),  # 20min
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["fee_status"] == "exempt"
    assert result["fee_amount"] == Decimal("0.00")
    assert event.fee_status == OccupancyFeeStatus.EXEMPT


def test_settle_no_parking_price_no_crash(test_db):
    """站点未配占位费率 → 不崩, fee=0, 保持 PENDING(等运营配费率后重试)。

    复用现有 charging_pricing 兜底口径: 无定价 → 0, 不兜默认费率(占位费不默认收费)。
    """
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s)
    # 不 seed ParkingPrice

    event = OccupancyEvent(
        plate_number="京D66666", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=datetime(2026, 7, 28, 12, 0, 0),
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["fee_status"] == "pending"          # 无费率, 等配置
    assert result["fee_amount"] == Decimal("0.00")
    assert event.fee_status == OccupancyFeeStatus.PENDING


# ═══════════════════════════════════════════════════════════════
# ③ 事件幂等
# ═══════════════════════════════════════════════════════════════

def test_ingest_idempotent_open_then_exit(test_db):
    """同站同车牌: 先报进场(未离场) → 再报离场 → 更新同一事件, 不新建。"""
    s = test_db["session"]
    from app.services.occupancy_fee_service import ingest_parking_event
    from app.models.parking_event import OccupancyEvent

    st = _seed_station(s)
    _seed_parking_price(s, st.id)

    # 进场(未离场)
    ev1 = ingest_parking_event(
        s, plate_number="京A12345", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0), exit_at=None)
    assert ev1.exit_at is None

    # 离场(同车牌同站)
    ev2 = ingest_parking_event(
        s, plate_number="京A12345", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=datetime(2026, 7, 28, 13, 0, 0))
    assert ev2.id == ev1.id                            # 同一事件
    assert ev2.exit_at == datetime(2026, 7, 28, 13, 0, 0)

    count = s.query(OccupancyEvent).filter(
        OccupancyEvent.plate_number == "京A12345",
        OccupancyEvent.station_id == st.id,
    ).count()
    assert count == 1


def test_ingest_idempotent_duplicate_exit_settles_once(test_db):
    """同一离场事件重复上报 → 只计费一次(订单合并幂等, 不重复累加)。"""
    s = test_db["session"]
    from app.services.occupancy_fee_service import (
        ingest_parking_event, settle_occupancy_event,
    )

    st = _seed_station(s)
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0)
    order = _seed_charging_order(s, st.id)

    # 第一次离场 → settle 计费并入订单
    ev = ingest_parking_event(
        s, plate_number="京A12345", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=datetime(2026, 7, 28, 13, 0, 0))
    settle_occupancy_event(s, ev)
    s.refresh(order)
    first_total = order.total_amount

    # 重复上报同一离场 → 幂等更新, 再 settle 不重复计费
    ev2 = ingest_parking_event(
        s, plate_number="京A12345", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=datetime(2026, 7, 28, 13, 0, 0))
    assert ev2.id == ev.id
    settle_occupancy_event(s, ev2)
    s.refresh(order)
    assert order.total_amount == first_total           # 未重复累加


def test_ingest_different_plate_creates_separate(test_db):
    """不同车牌 → 各自独立事件。"""
    s = test_db["session"]
    from app.services.occupancy_fee_service import ingest_parking_event
    from app.models.parking_event import OccupancyEvent

    st = _seed_station(s)
    ingest_parking_event(s, plate_number="京A12345", station_id=st.id,
                         enter_at=datetime(2026, 7, 28, 10, 0, 0), exit_at=None)
    ingest_parking_event(s, plate_number="京B88888", station_id=st.id,
                         enter_at=datetime(2026, 7, 28, 10, 0, 0), exit_at=None)
    assert s.query(OccupancyEvent).filter(
        OccupancyEvent.station_id == st.id).count() == 2


# ═══════════════════════════════════════════════════════════════
# ④ 财务安全 edge case (卡 9cc6bdad)
#    TOCTOU 并发双扣 / naive-aware 混用 / 日期穿透 / 累加幂等
# ═══════════════════════════════════════════════════════════════

def test_settle_toctou_concurrent_no_double_charge(test_db, monkeypatch):
    """TOCTOU 并发双扣防御 (settle 层, BUG1 行锁重读)。

    场景: 两并发事务都对同一 PENDING event 调 settle, check-then-act 窗口被绕过
    (第二个事务的内存视图仍是 PENDING, 但 DB 行已被第一事务改成 MERGED)。修复后
    settle 入口加行锁 + populate_existing 重读权威状态 → 以 DB 状态为准(DB 已
    MERGED → 幂等返回), 不再进入计费分支, _merge_fee_into_order 仅被调用一次。

    SQLite FOR UPDATE no-op, populate_existing() 强制重读到 MERGED 驱动幂等返回
    (生产 PG 则由行锁阻塞并发)。BUG4 绝对值覆盖作应用层兜底, 由
    test_merge_fee_into_order_idempotent_overwrite 独立验证。
    """
    s = test_db["session"]
    from app.models.parking_event import (
        OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource,
    )
    from app.services import occupancy_fee_service as svc
    from app.services.occupancy_fee_service import settle_occupancy_event

    # spy _merge_fee_into_order 计次: 验证 BUG1 行锁重读阻断了第二次计费
    real_merge = svc._merge_fee_into_order
    merge_calls = {"n": 0}

    def _spy_merge(db, order, fee):
        merge_calls["n"] += 1
        return real_merge(db, order, fee)
    monkeypatch.setattr(svc, "_merge_fee_into_order", _spy_merge)

    st = _seed_station(s)
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0)
    order = _seed_charging_order(s, st.id)  # 充电 10:00-12:00, total=26.00

    event = OccupancyEvent(
        plate_number="京A12345", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=datetime(2026, 7, 28, 13, 0, 0),
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    # 第一次 settle: PENDING → MERGED, parking_fee = 3.00, _merge 调用 1 次
    r1 = settle_occupancy_event(s, event)
    assert r1["fee_amount"] == Decimal("3.00")
    assert merge_calls["n"] == 1
    s.refresh(order)
    assert order.parking_fee == Decimal("3.00")
    assert order.total_amount == Decimal("29.00")

    # 模拟并发窗口: 内存 event 仍是 PENDING(DB 行已 MERGED)
    event.fee_status = OccupancyFeeStatus.PENDING
    event.fee_amount = Decimal("0.00")
    event.match_order_id = None

    # 第二次 settle: 行锁重读权威状态 → DB 已 MERGED → 幂等返回, _merge 不再调用
    r2 = settle_occupancy_event(s, event)
    assert merge_calls["n"] == 1                       # BUG1 阻断, 仍只 1 次
    assert r2["fee_status"] == "merged"
    assert r2["fee_amount"] == Decimal("3.00")
    s.refresh(order)
    assert order.parking_fee == Decimal("3.00")        # 不翻倍
    assert order.total_amount == Decimal("29.00")      # 不翻倍


def test_match_charging_order_aware_naive_no_crash(test_db):
    """_match_charging_order 对 aware / naive datetime 均不崩且匹配正确。

    缺陷族 (BUG2): filter 直接用 event.exit_at / enter_at 与 naive DB 列比较。
      - PostgreSQL: aware vs naive 列 → TypeError
      - SQLite: aware datetime bind 只取墙钟字面量(丢 tz), 跨时区 aware(如 UTC,
        墙钟 02:00-05:00) 与业务时区 naive 列(墙钟 10:00-12:00) 错位 → 匹配丢失
    修复: query filter 前用 _wall() 归一化为业务时区 naive 墙钟。
    """
    s = test_db["session"]
    from datetime import timezone, timedelta
    from app.models.parking_event import (
        OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource,
    )
    from app.services.occupancy_fee_service import _match_charging_order

    tz = timezone(timedelta(hours=8))  # 业务时区 CST
    st = _seed_station(s)
    # 充电订单 naive-UTC 02:00-04:00 落库 (= 上海 10:00-12:00, 卡 f7422bbc 口径)
    _seed_charging_order(s, st.id, plate="京A12345",
                         start=datetime(2026, 7, 28, 2, 0, 0),
                         end=datetime(2026, 7, 28, 4, 0, 0))

    # UTC aware (同一绝对时刻 = 上海 10:00-13:00, 墙钟 02:00-05:00):
    # 修复后 _utc_naive 归一到 UTC 轴 → 与订单 UTC 列同轴命中 (卡 5a18d1ee)
    utc_event = OccupancyEvent(
        plate_number="京A12345", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 2, 0, 0, tzinfo=timezone.utc),
        exit_at=datetime(2026, 7, 28, 5, 0, 0, tzinfo=timezone.utc),
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    order = _match_charging_order(s, utc_event)
    assert order is not None
    assert order.plate_number == "京A12345"

    # 业务时区 aware (同一绝对时刻, UTC 02:00-05:00): _utc_naive 真换算 → 命中
    cst_event = OccupancyEvent(
        plate_number="京A12345", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0, tzinfo=tz),
        exit_at=datetime(2026, 7, 28, 13, 0, 0, tzinfo=tz),
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    assert _match_charging_order(s, cst_event) is not None

    # naive datetime (DB 读回即 UTC 轴, 卡 5a18d1ee): 原值参与 UTC 轴比较 → 命中
    naive_event = OccupancyEvent(
        plate_number="京A12345", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 2, 0, 0),
        exit_at=datetime(2026, 7, 28, 5, 0, 0),
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    order3 = _match_charging_order(s, naive_event)
    assert order3 is not None
    assert order3.id == order.id


def test_load_parking_rule_none_enter_at_returns_none(test_db):
    """enter_at=None 不穿透返回 ALL active rules (含未生效 future), 而是返回 None。

    缺陷 (BUG3): enter_at=None → today=None → 跳过日期过滤, 返回所有 active rules
    (含 effective_date 在未来的未生效费率) → 误用未生效费率计费。
    修复: today=None 时直接返回 None (无法判定业务日 → 不默认收费)。
    """
    s = test_db["session"]
    from datetime import date
    from app.models.pricing_v2 import ParkingPrice
    from app.services.occupancy_fee_service import _load_parking_rule

    st = _seed_station(s)
    # 仅一条未生效的 future 费率
    s.add(ParkingPrice(
        station_id=st.id, free_minutes=30, hourly_rate=Decimal("6.0"),
        daily_cap=None, enable_night_rate=False,
        effective_date=date(2099, 1, 1), is_active=True,
    )); s.commit()

    rule = _load_parking_rule(s, st.id, enter_at=None)
    assert rule is None                                # 不穿透返回 future rule


def test_merge_fee_into_order_idempotent_overwrite(test_db):
    """_merge_fee_into_order 绝对值覆盖: 重复调用同一 fee 不累加。

    缺陷 (BUG4): 旧实现 current_parking + fee 纯累加, 配合 TOCTOU 重复调用 →
    parking_fee 翻倍且 PARKING 明细 delete+recreate 丢历史。
    修复: 查现有 PARKING 明细金额, new_parking = current - existing + fee
    (绝对值覆盖语义), 重复调用同一 fee 幂等不翻倍。
    """
    s = test_db["session"]
    from app.services.occupancy_fee_service import _merge_fee_into_order
    from app.models.order_fee_item import OrderFeeItem, FeeType

    st = _seed_station(s)
    order = _seed_charging_order(s, st.id)  # parking_fee=0, total=26.00

    fee = Decimal("3.00")
    _merge_fee_into_order(s, order, fee)
    s.flush()
    assert order.parking_fee == Decimal("3.00")
    assert order.total_amount == Decimal("29.00")

    # 重复调用同一 fee (TOCTOU 漏过状态检查的兜底): 绝对值覆盖, 不翻倍
    _merge_fee_into_order(s, order, fee)
    s.flush()
    assert order.parking_fee == Decimal("3.00")        # 不翻倍
    assert order.total_amount == Decimal("29.00")

    # PARKING 明细仅一条, 金额 == fee
    items = [i for i in s.query(OrderFeeItem).filter(
        OrderFeeItem.order_id == order.id).all()
             if i.fee_type == FeeType.PARKING]
    assert len(items) == 1
    assert items[0].amount == Decimal("3.00")


# ═══════════════════════════════════════════════════════════════
# ⑤ 跨日 / 封顶 / 夜间费率切换 / 空时长 / 跨时段 (覆盖任务点名维度)
#    现有 14 测试均为单日内白天场景, 以下补跨日·封顶·峰谷平切换·除零空时长。
# ═══════════════════════════════════════════════════════════════

def test_settle_cross_midnight_billed(test_db):
    """跨日占位(在场跨午夜, 无充电订单) → 独立账单, 时长按墙钟差正确累计。

    在场 2026-07-28 23:00 → 次日 01:00 = 120min, free=0, rate=6/h, 无夜间。
    billable = 120 → day_fee = 120/60*6 = 12.00。验证 timedelta 跨日不被日历边界截断。
    """
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s, code="CROSS01")
    _seed_parking_price(s, st.id, free_minutes=0, hourly_rate=6.0)

    event = OccupancyEvent(
        plate_number="京E11111", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 23, 0, 0),
        exit_at=datetime(2026, 7, 29, 1, 0, 0),
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["occupancy_minutes"] == 120              # 跨日 timedelta 正常
    assert result["fee_amount"] == Decimal("12.00")
    assert result["fee_status"] == "billed"


def test_settle_daily_cap_caps_fee(test_db):
    """日封顶: 占位费超 daily_cap → 封顶到 cap, fee_status=BILLED。

    在场 600min(10h), free=0, rate=6/h → 未封顶 subtotal=60.00, daily_cap=40 → 封顶 40.00。
    """
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s, code="CAP01")
    _seed_parking_price(s, st.id, free_minutes=0, hourly_rate=6.0, daily_cap=40.0)

    event = OccupancyEvent(
        plate_number="京F22222", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=datetime(2026, 7, 28, 20, 0, 0),  # 600min
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["fee_amount"] == Decimal("40.00")        # 封顶
    assert result["fee_status"] == "billed"


def test_settle_night_rate_lower_than_day(test_db):
    """峰谷平费率切换: 夜间窗内占位按更低夜间费率计, 非 billing_engine 白天默认。

    在场上海 23:00→00:00 = 60min, free=0, day rate=6/h, night rate=2/h, 夜间窗 23:00-07:00。
    全部落夜间 → night_fee = 60/60*2 = 2.00 (非白天 6.00)。验证占位费走夜间低费率分支。
    DB 落库 naive-UTC (卡 5a18d1ee): 上海 23:00/00:00 = UTC 15:00 / 16:00。
    """
    from datetime import time
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s, code="NIGHT01")
    _seed_parking_price(
        s, st.id, free_minutes=0, hourly_rate=6.0,
        enable_night_rate=True, night_rate=2.0,
        night_start=time(23, 0), night_end=time(7, 0),
    )

    event = OccupancyEvent(
        plate_number="京G33333", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 15, 0, 0),  # UTC = 上海 23:00
        exit_at=datetime(2026, 7, 28, 16, 0, 0),   # UTC = 上海 7/29 00:00
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["fee_amount"] == Decimal("2.00")         # 夜间低费率, 非白天 6.00


def test_settle_day_window_uses_day_rate(test_db):
    """峰谷平费率切换(白天窗对照): 白天窗内占位按白天费率, 不走夜间。

    在场上海 22:00→23:00 = 60min(全白天, 23:00 才进夜间), day rate=6/h, night rate=2/h。
    全白天 → day_fee = 6.00 (非夜间 2.00)。与上一测试对照, 确认窗口边界正确切分。
    DB 落库 naive-UTC (卡 5a18d1ee): 上海 22:00/23:00 = UTC 14:00 / 15:00。
    """
    from datetime import time
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s, code="NIGHT02")
    _seed_parking_price(
        s, st.id, free_minutes=0, hourly_rate=6.0,
        enable_night_rate=True, night_rate=2.0,
        night_start=time(23, 0), night_end=time(7, 0),
    )

    event = OccupancyEvent(
        plate_number="京H44444", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 14, 0, 0),  # UTC = 上海 22:00
        exit_at=datetime(2026, 7, 28, 15, 0, 0),   # UTC = 上海 23:00
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["fee_amount"] == Decimal("6.00")         # 白天费率


def test_settle_zero_duration_exit_le_enter_pending(test_db):
    """空时长(exit <= enter, 异常数据) → occupancy=0 → 不计费, 保持 PENDING。

    compute_occupancy_minutes 用 max(0, int(...//60)) 兜底负/零时长 → 0,
    settle 见 occupancy<=0 分支返回 PENDING, 不崩不收费。
    """
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s, code="ZERO01")
    _seed_parking_price(s, st.id, free_minutes=0, hourly_rate=6.0)

    event = OccupancyEvent(
        plate_number="京I55555", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 12, 0, 0),
        exit_at=datetime(2026, 7, 28, 12, 0, 0),  # exit == enter
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["fee_status"] == "pending"
    assert result["fee_amount"] == Decimal("0.00")
    assert result["occupancy_minutes"] == 0


def test_settle_reversed_exit_before_enter_pending(test_db):
    """exit < enter(异常时序数据) → occupancy=0(max 兜底) → 不计费 PENDING, 不崩。"""
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s, code="REV01")
    _seed_parking_price(s, st.id, free_minutes=0, hourly_rate=6.0)

    event = OccupancyEvent(
        plate_number="京J66666", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 14, 0, 0),
        exit_at=datetime(2026, 7, 28, 10, 0, 0),  # exit < enter
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["fee_status"] == "pending"
    assert result["fee_amount"] == Decimal("0.00")
    assert result["occupancy_minutes"] == 0


# ── _overlap_minutes 边界 (compute_occupancy_minutes 的免除分钟核心) ──

def test_overlap_minutes_no_overlap():
    """两区间不相交 → 0。"""
    from app.services.occupancy_fee_service import _overlap_minutes as ov
    assert ov(datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 11, 0),
              datetime(2026, 7, 28, 12, 0), datetime(2026, 7, 28, 13, 0)) == 0


def test_overlap_minutes_partial():
    """部分重叠 → 重叠分钟数(向下取整)。10:00-11:00 与 10:30-11:30 → 30min。"""
    from app.services.occupancy_fee_service import _overlap_minutes as ov
    assert ov(datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 11, 0),
              datetime(2026, 7, 28, 10, 30), datetime(2026, 7, 28, 11, 30)) == 30


def test_overlap_minutes_contained():
    """一区间完全包含另一区间 → 较小区间全长。"""
    from app.services.occupancy_fee_service import _overlap_minutes as ov
    # 在场 10:00-13:00(180min), 充电 10:30-11:30(60min) → 重叠 60min
    assert ov(datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 13, 0),
              datetime(2026, 7, 28, 10, 30), datetime(2026, 7, 28, 11, 30)) == 60


def test_overlap_minutes_touch_boundary():
    """相邻不重叠(端点相切): [10,11) 与 [11,12) → 0(左闭右开)。"""
    from app.services.occupancy_fee_service import _overlap_minutes as ov
    assert ov(datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 11, 0),
              datetime(2026, 7, 28, 11, 0), datetime(2026, 7, 28, 12, 0)) == 0


# ── compute_occupancy_minutes 进阶边界 ──

def test_occupancy_minutes_exempt_capped_by_overlap():
    """免除分钟不超过在场时长: 充电窗超出在场时间, exempt 取重叠部分非全长。

    在场 10:00-11:00(60min), 充电 09:00-12:00(覆盖在场) → 重叠=在场=60min,
    exempt=60(非充电全长180)。
    """
    from app.services.occupancy_fee_service import compute_occupancy_minutes

    class _Ord:
        start_time = datetime(2026, 7, 28, 9, 0, 0)
        end_time = datetime(2026, 7, 28, 12, 0, 0)

    occ, exempt = compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0, 0), datetime(2026, 7, 28, 11, 0, 0), _Ord())
    assert occ == 60
    assert exempt == 60                                   # 仅重叠部分, 非充电 180min


def test_occupancy_minutes_none_enter_returns_zero():
    """enter_at=None → (0, 0) 防御(无法判定占位起点)。"""
    from app.services.occupancy_fee_service import compute_occupancy_minutes

    class _Ord:
        start_time = datetime(2026, 7, 28, 10, 0, 0)
        end_time = datetime(2026, 7, 28, 12, 0, 0)

    assert compute_occupancy_minutes(None, datetime(2026, 7, 28, 13, 0, 0), _Ord()) == (0, 0)


def test_occupancy_minutes_order_missing_window_no_exempt():
    """充电订单缺 start/end → has_order_window=False, 走识别记录, exempt=0。"""
    from app.services.occupancy_fee_service import compute_occupancy_minutes

    class _Ord:
        start_time = None
        end_time = datetime(2026, 7, 28, 12, 0, 0)

    occ, exempt = compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0, 0), datetime(2026, 7, 28, 13, 0, 0), _Ord())
    assert occ == 180                                      # 识别记录 10:00-13:00
    assert exempt == 0                                     # 无有效订单窗, 不免除


# ── ingest_parking_event 边界 ──

def test_ingest_invalid_source_falls_back_to_alpr(test_db):
    """非法 source 字符串 → 兜底 ALPR, 不崩(VehicleError 兜底, 事件正常入库)。"""
    s = test_db["session"]
    from app.services.occupancy_fee_service import ingest_parking_event
    from app.models.parking_event import OccupancyEventSource

    st = _seed_station(s, code="SRC01")
    ev = ingest_parking_event(
        s, plate_number="京K77777", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0), exit_at=None,
        source="totally-bogus-source",
    )
    assert ev.source == OccupancyEventSource.ALPR


def test_ingest_empty_source_defaults_alpr(test_db):
    """空 source → 默认 ALPR。"""
    s = test_db["session"]
    from app.services.occupancy_fee_service import ingest_parking_event
    from app.models.parking_event import OccupancyEventSource

    st = _seed_station(s, code="SRC02")
    ev = ingest_parking_event(
        s, plate_number="京L88888", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0), exit_at=None, source="",
    )
    assert ev.source == OccupancyEventSource.ALPR


def test_settle_terminal_state_idempotent_returns_current(test_db):
    """已终结状态(BILLED)再 settle → 幂等返回当前值, 不重算(防重复上报累加)。

    独立账单场景: 首次 settle → BILLED fee=9.00; 改 DB 模拟重复 settle,
    返回值与首次一致, 不进计费分支。
    """
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s, code="TERM01")
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0)

    event = OccupancyEvent(
        plate_number="京M99999", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=datetime(2026, 7, 28, 12, 0, 0),
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    r1 = settle_occupancy_event(s, event)
    assert r1["fee_status"] == "billed"
    first_fee = r1["fee_amount"]

    # 再次 settle: 已 BILLED(终结) → 幂等返回当前值
    r2 = settle_occupancy_event(s, event)
    assert r2["fee_status"] == "billed"
    assert r2["fee_amount"] == first_fee


def test_settle_not_exited_pending_zero_fee(test_db):
    """未离场(exit_at=None) → 不结算, PENDING fee=0(占位费在离场时结算)。"""
    s = test_db["session"]
    from app.models.parking_event import OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource
    from app.services.occupancy_fee_service import settle_occupancy_event

    st = _seed_station(s, code="PEND01")
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0)

    event = OccupancyEvent(
        plate_number="京N00000", station_id=st.id,
        enter_at=datetime(2026, 7, 28, 10, 0, 0),
        exit_at=None,  # 未离场
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    s.add(event); s.commit(); s.refresh(event)

    result = settle_occupancy_event(s, event)
    assert result["fee_status"] == "pending"
    assert result["fee_amount"] == Decimal("0.00")
