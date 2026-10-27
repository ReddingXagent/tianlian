"""
occupancy_fee_service 防御性加固边界测试 (卡 f1ca4ba3)

针对生产风险点补 edge case:
- DB 写入路径异常必须 rollback(不残留脏数据)
- Decimal/数值转换对 None / 非法字符串 / 负数脏数据降级, 不崩
- None 值边界全覆盖(enter_at/exit_at/start_time/end_time)
- 空重叠区间 / 负数费率

不改变现有正向逻辑: 已有 try/except 与契约 raise 保留, 现有测试全通过。
"""
from datetime import datetime, date, time
from decimal import Decimal, InvalidOperation

import pytest


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """注入 test_db(override SessionLocal + seed admin), 每测试独立 DB。"""
    pass


# ─── 种子 helpers(与 test_occupancy_fee_service.py 同口径, 独立拷贝避免跨文件耦合) ───

def _seed_station(session, code="HARD01"):
    from app.models.station import Station, StationStatus
    st = Station(name="占位费加固测试站", code=code, address="测试地址",
                 status=StationStatus.NORMAL)
    session.add(st); session.commit(); session.refresh(st)
    return st


def _seed_parking_price(session, station_id, *, free_minutes=30, hourly_rate=6.0,
                        daily_cap=None, enable_night_rate=False, night_rate=None,
                        night_start=None, night_end=None):
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
    from app.models.charging_order import (
        ChargingOrder, OrderStatus, OrderPaymentStatus,
    )
    o = ChargingOrder(
        order_no="HARD-ORDER-001", station_id=station_id, device_id=1,
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


def _make_event(session, station_id, *, enter, exit_=None, plate="京Z00001"):
    from app.models.parking_event import (
        OccupancyEvent, OccupancyFeeStatus, OccupancyEventSource,
    )
    ev = OccupancyEvent(
        plate_number=plate, station_id=station_id,
        enter_at=enter, exit_at=exit_,
        source=OccupancyEventSource.ALPR, fee_status=OccupancyFeeStatus.PENDING,
    )
    session.add(ev); session.commit(); session.refresh(ev)
    return ev


# ═══════════════════════════════════════════════════════════════
# A. Decimal 脏数据 — _load_parking_rule 降级不崩
#    ParkingPrice.hourly_rate 为 Numeric 列, 脏数据(直写/迁移残留)可能为
#    None 或非法字符串; 旧实现裸 Decimal(str(row.hourly_rate)) 会抛
#    InvalidOperation 穿透到 settle, 整单结算崩溃。
# ═══════════════════════════════════════════════════════════════

def test_load_parking_rule_hourly_rate_none_no_crash(test_db):
    """hourly_rate=None 脏数据(直写绕过 NOT NULL) → _load_parking_rule 不崩。

    降级口径: None 视为 0(不多收费), rule 仍返回(billing_engine 进一步 sanitize)。
    """
    from app.models.pricing_v2 import ParkingPrice
    from app.services.occupancy_fee_service import _load_parking_rule
    s = test_db["session"]
    st = _seed_station(s, code="DEC01")
    pp = ParkingPrice(
        station_id=st.id, free_minutes=30, hourly_rate=None,  # 脏数据
        daily_cap=None, enable_night_rate=False,
        effective_date=date(2026, 1, 1), is_active=True,
    )
    s.add(pp); s.commit()
    rule = _load_parking_rule(s, st.id, datetime(2026, 7, 28, 10, 0, 0))
    assert rule is not None                      # 不崩, 降级返回
    assert rule["hourly_rate"] == Decimal("0")   # None → 0


def test_load_parking_rule_daily_cap_none_no_crash(test_db):
    """daily_cap=None → 降级 None(无封顶), 不崩。"""
    from app.services.occupancy_fee_service import _load_parking_rule
    s = test_db["session"]
    st = _seed_station(s, code="DEC02")
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0, daily_cap=None)
    rule = _load_parking_rule(s, st.id, datetime(2026, 7, 28, 10, 0, 0))
    assert rule is not None
    assert rule["daily_cap"] is None             # None 直传(billing_engine 视为无封顶)


def test_load_parking_rule_night_rate_none_no_crash(test_db):
    """enable_night_rate=True 但 night_rate=None(配置半成品) → 降级 None, 不崩。

    Decimal(str(None)) 旧实现会抛 InvalidOperation; 修复后 None 直传,
    billing_engine 见 night_rate is None → 不启用夜间分摊。
    """
    from datetime import time as dtime
    from app.services.occupancy_fee_service import _load_parking_rule
    s = test_db["session"]
    st = _seed_station(s, code="DEC02B")
    _seed_parking_price(
        s, st.id, free_minutes=0, hourly_rate=6.0,
        enable_night_rate=True, night_rate=None,
        night_start=dtime(23, 0), night_end=dtime(7, 0),
    )
    rule = _load_parking_rule(s, st.id, datetime(2026, 7, 28, 23, 0, 0))
    assert rule is not None
    assert rule["night_rate"] is None            # None 直传不崩


def test_load_parking_rule_negative_hourly_rate_not_crash(test_db):
    """hourly_rate < 0(误配置/负费率脏数据) → _load_parking_rule 不崩, 原值透传。

    负费率本身是配置错误, 但 service 层不应在加载阶段崩; billing_engine
    会算出负费用, settle 的 fee<=0 分支判 EXEMPT(负费用不计费)。
    """
    from app.models.pricing_v2 import ParkingPrice
    from app.services.occupancy_fee_service import _load_parking_rule
    s = test_db["session"]
    st = _seed_station(s, code="DEC03")
    s.add(ParkingPrice(
        station_id=st.id, free_minutes=0, hourly_rate=Decimal("-6.00"),
        daily_cap=None, enable_night_rate=False,
        effective_date=date(2026, 1, 1), is_active=True,
    ))
    s.commit()
    rule = _load_parking_rule(s, st.id, datetime(2026, 7, 28, 10, 0, 0))
    assert rule is not None
    assert rule["hourly_rate"] == Decimal("-6.00")  # 原值透传, 不在加载层篡改


def test_settle_negative_rate_exempt_not_negative_fee(test_db):
    """负数费率端到端: settle 不产生负费用, fee<=0 → EXEMPT(负费率不计费不倒贴)。"""
    from app.services.occupancy_fee_service import settle_occupancy_event
    s = test_db["session"]
    st = _seed_station(s, code="DEC04")
    _seed_parking_price(s, st.id, free_minutes=0, hourly_rate=-6.0)
    ev = _make_event(s, st.id, plate="京Z00002",
                     enter=datetime(2026, 7, 28, 10, 0, 0),
                     exit_=datetime(2026, 7, 28, 11, 0, 0))  # 60min
    result = settle_occupancy_event(s, ev)
    # 费率 -6 → fee = 60/60 * -6 = -6.00; fee<=0 分支 → EXEMPT, fee=0
    assert result["fee_amount"] == Decimal("0.00")
    assert result["fee_status"] in ("exempt", "pending")  # 不产生负费用


# ═══════════════════════════════════════════════════════════════
# B. DB 写入异常 rollback — _merge_fee_into_order / settle / ingest
# ═══════════════════════════════════════════════════════════════

def test_merge_fee_into_order_db_exception_rolls_back(test_db, monkeypatch):
    """_merge_fee_into_order 内 db 操作抛异常 → 主动 rollback + re-raise。

    场景: db.flush 抛异常(模拟约束冲突/连接断)。修复后函数 catch + db.rollback()
    + re-raise(让上层端点决定 HTTP 响应, 但 session 已干净)。
    用 spy 计数 db.rollback() 调用次数验证 service 主动回滚。
    """
    from app.services import occupancy_fee_service as svc
    s = test_db["session"]
    st = _seed_station(s, code="RB01")
    order = _seed_charging_order(s, st.id)

    real_rollback = s.rollback
    rb = {"n": 0}

    def _spy_rollback(*a, **kw):
        rb["n"] += 1
        return real_rollback(*a, **kw)

    def _boom_flush(*a, **kw):
        raise RuntimeError("simulated db failure")
    monkeypatch.setattr(s, "flush", _boom_flush)
    monkeypatch.setattr(s, "rollback", _spy_rollback)

    with pytest.raises(RuntimeError):
        svc._merge_fee_into_order(s, order, Decimal("3.00"))

    assert rb["n"] >= 1                            # service 主动调 rollback


def test_settle_merge_exception_rolls_back_no_partial_write(test_db, monkeypatch):
    """settle_occupancy_event 中 _merge_fee_into_order 异常 → 主动 rollback + re-raise。

    场景: 有匹配订单, merge 时 DB 异常。修复前异常穿透, session 残留脏状态
    (occupancy_minutes 已赋值/部分 flush)。修复后 settle catch + rollback + re-raise,
    session 干净。用 spy 验证 rollback 被调用。
    """
    from app.services import occupancy_fee_service as svc
    from app.services.occupancy_fee_service import settle_occupancy_event
    s = test_db["session"]
    st = _seed_station(s, code="RB02")
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0)
    # order 与 event 同车牌同站, 时间窗重叠 → _match_charging_order 命中
    _seed_charging_order(s, st.id, plate="京Z00003")
    ev = _make_event(s, st.id, plate="京Z00003",
                     enter=datetime(2026, 7, 28, 10, 0, 0),
                     exit_=datetime(2026, 7, 28, 13, 0, 0))

    real_rollback = s.rollback
    rb = {"n": 0}

    def _spy_rollback(*a, **kw):
        rb["n"] += 1
        return real_rollback(*a, **kw)

    def _boom(db, o, fee):
        raise RuntimeError("merge failed")
    monkeypatch.setattr(svc, "_merge_fee_into_order", _boom)
    monkeypatch.setattr(s, "rollback", _spy_rollback)

    with pytest.raises(RuntimeError):
        settle_occupancy_event(s, ev)

    assert rb["n"] >= 1                            # settle 主动 rollback


def test_ingest_parking_event_db_exception_rolls_back(test_db, monkeypatch):
    """ingest_parking_event 新建事件时 db 异常 → 主动 rollback + re-raise。

    场景: db.add + flush 抛异常。修复后 catch + rollback + re-raise。
    用 spy 验证 rollback 被调用。
    """
    from app.services.occupancy_fee_service import ingest_parking_event
    s = test_db["session"]
    st = _seed_station(s, code="RB03")

    real_rollback = s.rollback
    rb = {"n": 0}

    def _spy_rollback(*a, **kw):
        rb["n"] += 1
        return real_rollback(*a, **kw)

    def _boom_flush(*a, **kw):
        raise RuntimeError("ingest db failure")
    monkeypatch.setattr(s, "flush", _boom_flush)
    monkeypatch.setattr(s, "rollback", _spy_rollback)

    with pytest.raises(RuntimeError):
        ingest_parking_event(
            s, plate_number="京Z00004", station_id=st.id,
            enter_at=datetime(2026, 7, 28, 10, 0, 0), exit_at=None)

    assert rb["n"] >= 1                            # ingest 主动 rollback


# ═══════════════════════════════════════════════════════════════
# C. None 值边界 — _match_charging_order / compute_occupancy_minutes
# ═══════════════════════════════════════════════════════════════

def test_compute_occupancy_minutes_none_exit_with_order_window():
    """exit_at=None 且订单有完整时间窗 → 用订单窗推算(回退路径), 不崩。"""
    from app.services.occupancy_fee_service import compute_occupancy_minutes

    class _Ord:
        start_time = datetime(2026, 7, 28, 10, 0, 0)
        end_time = datetime(2026, 7, 28, 12, 0, 0)

    occ, exempt = compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0, 0), None, _Ord())
    assert occ == 120
    assert exempt == 120


def test_compute_occupancy_minutes_none_exit_none_order_window():
    """exit_at=None 且订单 start_time=None → 无可用窗口 → (0,0), 不崩。"""
    from app.services.occupancy_fee_service import compute_occupancy_minutes

    class _Ord:
        start_time = None
        end_time = datetime(2026, 7, 28, 12, 0, 0)

    occ, exempt = compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0, 0), None, _Ord())
    assert (occ, exempt) == (0, 0)


def test_overlap_minutes_zero_overlap_returns_zero():
    """_overlap_minutes 零重叠(完全不相交) → 0(防御负数)。"""
    from app.services.occupancy_fee_service import _overlap_minutes as ov
    # 在场 10:00-11:00, 充电 11:30-12:30 → 不相交 → 0
    assert ov(datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 11, 0),
              datetime(2026, 7, 28, 11, 30), datetime(2026, 7, 28, 12, 30)) == 0


def test_overlap_minutes_reversed_window_zero():
    """_overlap_minutes 充电窗完全在场之前(反向) → 0, max(0,...) 兜底负值。"""
    from app.services.occupancy_fee_service import _overlap_minutes as ov
    # 在场 12:00-13:00, 充电 10:00-11:00 → delta 负 → max(0) → 0
    assert ov(datetime(2026, 7, 28, 12, 0), datetime(2026, 7, 28, 13, 0),
              datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 11, 0)) == 0


# ═══════════════════════════════════════════════════════════════
# D. _merge_fee_into_order Decimal 脏数据(订单侧脏值)
# ═══════════════════════════════════════════════════════════════

def test_merge_fee_into_order_dirty_amount_none_no_crash(test_db):
    """OrderFeeItem.amount 为 None 脏数据 → _merge_fee_into_order 不崩。

    场景: 历史 PARKING 明细 amount 为 NULL(脏数据)。`Decimal(str(i.amount or 0))`
    的 `or 0` 守卫已防 None(→ Decimal('0')); 本测试回归保护该守卫不被移除,
    并验证 None 明细不影响 existing_parking 累计。
    """
    from sqlalchemy import text
    from app.services.occupancy_fee_service import _merge_fee_into_order
    s = test_db["session"]
    st = _seed_station(s, code="DEC05")
    order = _seed_charging_order(s, st.id)

    # 先正常 merge 一笔, 写入 PARKING 明细
    _merge_fee_into_order(s, order, Decimal("3.00"))
    s.commit()

    # 把明细 amount 脏写成 NULL
    s.execute(text(
        "UPDATE order_fee_items SET amount = NULL "
        "WHERE order_id = :oid"), {"oid": order.id})
    s.commit()
    s.expire_all()
    s.refresh(order)
    order.parking_fee = Decimal("5.00")  # 模拟 order 侧已有值

    # 再次 merge: 现有明细 amount=NULL, `or 0` 降级, 不崩
    _merge_fee_into_order(s, order, Decimal("3.00"))
    s.commit()
    s.refresh(order)
    # NULL existing → 0: new_parking = 5.00 - 0 + 3.00 = 8.00
    assert order.parking_fee == Decimal("8.00")
