#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无人值守占位费服务 - 隔离单元测试 (MagicMock 隔离 DB)

被测: app/services/occupancy_fee_service.py
设计: 纯函数 (_wall/_overlap_minutes/compute_occupancy_minutes) 直测;
       DB 依赖 (Session) 用 MagicMock 自链式 query 隔离, 不触碰真实数据库;
       billing_engine.compute_parking_fee_full 在需要精确费用时 patch, 其余走真实
       纯函数逻辑(它本身也是纯函数, 测试其集成)。
       _merge_fee_into_order 用 SimpleNamespace 订单替身验证数值覆盖语义。

覆盖:
- _wall / _overlap_minutes (不相交/部分/包含/相切边界)
- compute_occupancy_minutes (识别优先/订单推算/无数据/None 入参/订单缺窗/exempt 上限)
- _load_parking_rule (enter_at=None→None/无行→None/有行→dict)
- _match_charging_order (有/无 exit 的 filter 分支/无匹配)
- _merge_fee_into_order (绝对值覆盖幂等不翻倍/fee=0 删明细不新建/total 重算)
- settle_occupancy_event (终结幂等/未离场/occupancy<=0/无费率/计费异常/EXEMPT/MERGED/BILLED)
- ingest_parking_event (open→update离场重置/dup幂等/新建/非法+空source兜底ALPR)
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.order_fee_item import FeeType
from app.models.parking_event import (
    OccupancyEventSource,
    OccupancyFeeStatus,
)
from app.services import occupancy_fee_service as svc


# ─────────────────────────────────────────────────────────
# 辅助: 自链式 query mock
# ─────────────────────────────────────────────────────────

def _chain_query(result=None):
    """filter/order_by/join/limit/offset/with_for_update/populate_existing 自链。

    with_for_update().populate_existing().first() (settle 行锁) 也自链 → result。
    """
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.join.return_value = q
    q.with_for_update.return_value = q
    q.populate_existing.return_value = q
    q.all.return_value = result or []
    q.first.return_value = result
    q.scalar.return_value = result
    q.count.return_value = result if isinstance(result, int) else 0
    q.delete.return_value = None
    return q


def _event(*, eid=1, plate="京A12345", station_id=10,
           enter_at=None, exit_at=None,
           fee_status=OccupancyFeeStatus.PENDING, fee_amount=Decimal("0.00"),
           match_order_id=None, occupancy_minutes=0):
    e = MagicMock()
    e.id = eid
    e.plate_number = plate
    e.station_id = station_id
    e.enter_at = enter_at or datetime(2026, 7, 28, 10, 0, 0)
    e.exit_at = exit_at
    e.fee_status = fee_status
    e.fee_amount = fee_amount
    e.match_order_id = match_order_id
    e.occupancy_minutes = occupancy_minutes
    return e


def _order(*, oid=100, parking_fee=Decimal("0.00"),
           electricity_fee=Decimal("16.00"), service_fee=Decimal("10.00"),
           occupancy_fee=Decimal("0.00"), reservation_fee=Decimal("0.00"),
           total_amount=Decimal("26.00"),
           start_time=datetime(2026, 7, 28, 10, 0),
           end_time=datetime(2026, 7, 28, 12, 0)):
    """用 SimpleNamespace 使数值字段可读可写 (_merge 会赋值)。

    start_time/end_time 供 compute_occupancy_minutes 读取订单时间窗。
    """
    return SimpleNamespace(
        id=oid, parking_fee=parking_fee, electricity_fee=electricity_fee,
        service_fee=service_fee, occupancy_fee=occupancy_fee,
        reservation_fee=reservation_fee, total_amount=total_amount,
        start_time=start_time, end_time=end_time,
    )


# ═══════════════════════════════════════════════════════════
# 1. _wall
# ═══════════════════════════════════════════════════════════

def test_wall_naive_keeps_wall_clock_strips_tz():
    """DB naive-UTC 读回 → 真换算业务时区墙钟 (卡 5a18d1ee: 不再表面解释)。

    naive-UTC 10:00 → 上海 18:00 (墙钟随真实偏移改变, 语义不变)。
    """
    naive = datetime(2026, 7, 28, 10, 0, 0)  # DB naive-UTC
    assert svc._wall(naive) == datetime(2026, 7, 28, 18, 0, 0)


def test_wall_aware_converts_to_biz_tz_then_strips():
    """aware UTC → 转业务时区(CST+8)墙钟, 再 strip tz。"""
    utc = datetime(2026, 7, 28, 2, 0, 0, tzinfo=timezone.utc)
    # CST 10:00 → strip → naive 10:00
    assert svc._wall(utc) == datetime(2026, 7, 28, 10, 0, 0)


# ═══════════════════════════════════════════════════════════
# 2. _overlap_minutes
# ═══════════════════════════════════════════════════════════

def test_overlap_no_intersection():
    assert svc._overlap_minutes(
        datetime(2026, 7, 28, 10), datetime(2026, 7, 28, 11),
        datetime(2026, 7, 28, 12), datetime(2026, 7, 28, 13)) == 0


def test_overlap_partial():
    assert svc._overlap_minutes(
        datetime(2026, 7, 28, 10), datetime(2026, 7, 28, 11),
        datetime(2026, 7, 28, 10, 30), datetime(2026, 7, 28, 11, 30)) == 30


def test_overlap_contained():
    assert svc._overlap_minutes(
        datetime(2026, 7, 28, 10), datetime(2026, 7, 28, 13),
        datetime(2026, 7, 28, 10, 30), datetime(2026, 7, 28, 11, 30)) == 60


def test_overlap_touching_boundary_is_zero():
    """[10,11) 与 [11,12) 端点相切 → 0。"""
    assert svc._overlap_minutes(
        datetime(2026, 7, 28, 10), datetime(2026, 7, 28, 11),
        datetime(2026, 7, 28, 11), datetime(2026, 7, 28, 12)) == 0


def test_overlap_negative_clamped_to_zero():
    """完全反向(b_start > a_end) → 0。"""
    assert svc._overlap_minutes(
        datetime(2026, 7, 28, 10), datetime(2026, 7, 28, 10, 10),
        datetime(2026, 7, 28, 12), datetime(2026, 7, 28, 13)) == 0


# ═══════════════════════════════════════════════════════════
# 3. compute_occupancy_minutes
# ═══════════════════════════════════════════════════════════

class _Ord:
    def __init__(self, start, end):
        self.start_time = start
        self.end_time = end


def test_compute_minutes_prefers_alpr_record():
    """识别系统进出场优先, 充电期间重叠计入 exempt。"""
    occ, exempt = svc.compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 13, 0),
        _Ord(datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 12, 0)))
    assert occ == 180
    assert exempt == 120


def test_compute_minutes_falls_back_to_order_estimate():
    """无 exit_at → 用订单推算, 全程免除。"""
    occ, exempt = svc.compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0), None,
        _Ord(datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 12, 0)))
    assert occ == 120
    assert exempt == 120


def test_compute_minutes_no_data_zero():
    occ, exempt = svc.compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0), None, None)
    assert (occ, exempt) == (0, 0)


def test_compute_minutes_none_enter_zero():
    occ, exempt = svc.compute_occupancy_minutes(
        None, datetime(2026, 7, 28, 13, 0),
        _Ord(datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 12, 0)))
    assert (occ, exempt) == (0, 0)


def test_compute_minutes_order_missing_window_no_exempt():
    """订单缺 start/end → has_order_window=False, 走识别记录, exempt=0。"""
    occ, exempt = svc.compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 13, 0),
        _Ord(None, datetime(2026, 7, 28, 12, 0)))
    assert occ == 180
    assert exempt == 0


def test_compute_minutes_exempt_capped_by_overlap():
    """充电窗超出在场时间 → exempt 取重叠部分, 非充电全长。"""
    occ, exempt = svc.compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0), datetime(2026, 7, 28, 11, 0),
        _Ord(datetime(2026, 7, 28, 9, 0), datetime(2026, 7, 28, 12, 0)))
    assert occ == 60
    assert exempt == 60


def test_compute_minutes_no_exit_no_order_window_zero():
    """无 exit + 无有效订单窗 → (0,0)。"""
    occ, exempt = svc.compute_occupancy_minutes(
        datetime(2026, 7, 28, 10, 0), None,
        _Ord(None, None))
    assert (occ, exempt) == (0, 0)


def test_compute_minutes_reversed_exit_zero():
    """exit < enter → occupancy 为 0(max 兜底, 向下取整)。"""
    occ, exempt = svc.compute_occupancy_minutes(
        datetime(2026, 7, 28, 14, 0), datetime(2026, 7, 28, 10, 0), None)
    assert occ == 0
    assert exempt == 0


# ═══════════════════════════════════════════════════════════
# 4. _load_parking_rule
# ═══════════════════════════════════════════════════════════

def _pp_row(*, free_minutes=30, hourly_rate=Decimal("6.00"), daily_cap=None,
            enable_night_rate=False, night_rate=None,
            night_start=None, night_end=None):
    return SimpleNamespace(
        free_minutes=free_minutes, hourly_rate=hourly_rate, daily_cap=daily_cap,
        enable_night_rate=enable_night_rate, night_rate=night_rate,
        night_start=night_start, night_end=night_end,
    )


def test_load_parking_rule_none_enter_returns_none():
    """enter_at=None → 直接 None, 不穿透返回 future rules(BUG3)。"""
    db = MagicMock()
    db.query.return_value = _chain_query(_pp_row())
    assert svc._load_parking_rule(db, 10, enter_at=None) is None
    db.query.assert_not_called()    # None 前置, 不查库


def test_load_parking_rule_no_row_returns_none():
    db = MagicMock()
    db.query.return_value = _chain_query(None)
    assert svc._load_parking_rule(db, 10, datetime(2026, 7, 28, 10, 0)) is None


def test_load_parking_rule_row_to_dict():
    db = MagicMock()
    db.query.return_value = _chain_query(_pp_row(
        free_minutes=15, hourly_rate=Decimal("3.50"),
        daily_cap=Decimal("40.00"), enable_night_rate=True,
        night_rate=Decimal("2.00"), night_start="23:00", night_end="07:00"))
    rule = svc._load_parking_rule(db, 10, datetime(2026, 7, 28, 10, 0))
    assert rule == {
        "free_minutes": 15,
        "hourly_rate": Decimal("3.50"),
        "daily_cap": Decimal("40.00"),
        "enable_night_rate": True,
        "night_rate": Decimal("2.00"),
        "night_start": "23:00",
        "night_end": "07:00",
    }


def test_load_parking_rule_null_free_minutes_defaults_zero():
    """free_minutes=None → 0 (or 守卫)。"""
    db = MagicMock()
    db.query.return_value = _chain_query(_pp_row(free_minutes=None))
    rule = svc._load_parking_rule(db, 10, datetime(2026, 7, 28, 10, 0))
    assert rule["free_minutes"] == 0


# ═══════════════════════════════════════════════════════════
# 5. _match_charging_order
# ═══════════════════════════════════════════════════════════

def test_match_order_with_exit_uses_window_intersect():
    """有 exit → 用时间窗相交 filter(start<=exit, end>=enter)。"""
    order = MagicMock(plate_number="京A12345", id=100)
    db = MagicMock()
    db.query.return_value = _chain_query(order)
    e = _event(exit_at=datetime(2026, 7, 28, 13, 0))
    got = svc._match_charging_order(db, e)
    assert got is order


def test_match_order_without_exit_uses_end_after_enter():
    """无 exit → filter(end_time >= enter)。"""
    order = MagicMock(plate_number="京A12345", id=100)
    db = MagicMock()
    db.query.return_value = _chain_query(order)
    e = _event(exit_at=None)
    got = svc._match_charging_order(db, e)
    assert got is order


def test_match_order_no_match_returns_none():
    db = MagicMock()
    db.query.return_value = _chain_query(None)
    e = _event(exit_at=datetime(2026, 7, 28, 13, 0))
    assert svc._match_charging_order(db, e) is None


# ═══════════════════════════════════════════════════════════
# 6. _merge_fee_into_order — 绝对值覆盖幂等
# ═══════════════════════════════════════════════════════════

def _merge_db(existing_items=()):
    """_merge 用的 db: query(OrderFeeItem)→链(.all/.delete 自链)。"""
    db = MagicMock()
    db.query.return_value = _chain_query(list(existing_items))
    db.add = MagicMock()
    db.flush = MagicMock()
    return db


def test_merge_fee_into_order_overwrites_parking_fee():
    order = _order(parking_fee=Decimal("0.00"), total_amount=Decimal("26.00"))
    db = _merge_db(existing_items=[])
    svc._merge_fee_into_order(db, order, Decimal("3.00"))
    assert order.parking_fee == Decimal("3.00")
    assert order.total_amount == Decimal("29.00")
    db.add.assert_called_once()
    db.flush.assert_called_once()


def test_merge_fee_into_order_idempotent_overwrite():
    """重复 merge 同一 fee → 绝对值覆盖不翻倍 (BUG4 兜底)。

    existing PARKING 明细贡献 = 3.00 (首次写入后);
    new_parking = (current_parking - existing + fee) = (3 - 3 + 3) = 3, 不累加。
    """
    order = _order(parking_fee=Decimal("3.00"), total_amount=Decimal("29.00"))
    # 模拟已有 PARKING 明细金额 3.00 (首次 merge 后的明细行)
    existing = [SimpleNamespace(amount=Decimal("3.00"))]
    db = _merge_db(existing_items=existing)
    svc._merge_fee_into_order(db, order, Decimal("3.00"))
    assert order.parking_fee == Decimal("3.00")    # 不翻倍
    assert order.total_amount == Decimal("29.00")


def test_merge_fee_into_order_new_fee_replaces_existing():
    """新 fee 替换旧 fee: existing=3, new=5 → new_parking=5。"""
    order = _order(parking_fee=Decimal("3.00"), total_amount=Decimal("29.00"))
    existing = [SimpleNamespace(amount=Decimal("3.00"))]
    db = _merge_db(existing_items=existing)
    svc._merge_fee_into_order(db, order, Decimal("5.00"))
    assert order.parking_fee == Decimal("5.00")
    assert order.total_amount == Decimal("31.00")


def test_merge_fee_into_order_zero_fee_deletes_no_new_item():
    """fee=0 → 删旧明细 + 不写新明细 (fee != 0 才 add)。

    绝对值覆盖: current_parking(3) - existing(3) + fee(0) = 0 → parking_fee 归零。
    """
    order = _order(parking_fee=Decimal("3.00"), total_amount=Decimal("29.00"))
    existing = [SimpleNamespace(amount=Decimal("3.00"))]
    db = _merge_db(existing_items=existing)
    svc._merge_fee_into_order(db, order, Decimal("0.00"))
    assert order.parking_fee == Decimal("0.00")
    assert order.total_amount == Decimal("26.00")
    db.add.assert_not_called()         # 不新建明细
    db.flush.assert_called_once()


def test_merge_fee_into_order_recomputes_total_all_components():
    """total = 电费+服务费+占位费+占桩费+预约费, 全分量参与。"""
    order = _order(parking_fee=Decimal("0.00"),
                   electricity_fee=Decimal("16.00"),
                   service_fee=Decimal("10.00"),
                   occupancy_fee=Decimal("2.00"),
                   reservation_fee=Decimal("1.00"),
                   total_amount=Decimal("29.00"))
    db = _merge_db(existing_items=[])
    svc._merge_fee_into_order(db, order, Decimal("4.50"))
    assert order.total_amount == Decimal("33.50")   # 16+10+4.5+2+1


# ═══════════════════════════════════════════════════════════
# 7. settle_occupancy_event — 状态机
# ═══════════════════════════════════════════════════════════

def _settle_db(*, locked=None, matched_order=None, parking_rule=None):
    """settle 用的 db: query 链按顺序:
    1) OccupancyEvent 行锁重读 → locked (or None → 用传入 event)
    2) ChargingOrder match → matched_order
    3) ParkingPrice rule → parking_rule (None=未配)
    多次 flush 调用对 db.flush 是同一个 mock。
    """
    db = MagicMock()
    calls = {"n": 0}
    locked_q = _chain_query(locked)
    order_q = _chain_query(matched_order)
    rule_q = _chain_query(parking_rule)
    queries = [locked_q, order_q, rule_q]

    def _query(_model=None, *a, **k):
        i = min(calls["n"], len(queries) - 1)
        calls["n"] += 1
        return queries[i]
    db.query.side_effect = _query
    db.flush = MagicMock()
    return db


def test_settle_terminal_state_idempotent_no_recompute():
    """终结状态(MERGED)再 settle → 幂等返回当前值, 不查订单/费率。"""
    e = _event(fee_status=OccupancyFeeStatus.MERGED,
               fee_amount=Decimal("3.00"), match_order_id=100,
               occupancy_minutes=180)
    db = _settle_db()
    res = svc.settle_occupancy_event(db, e)
    assert res == {
        "fee_status": "merged",
        "fee_amount": Decimal("3.00"),
        "match_order_id": 100,
        "occupancy_minutes": 180,
    }
    db.flush.assert_not_called()


@pytest.mark.parametrize("status", [
    OccupancyFeeStatus.BILLED, OccupancyFeeStatus.MERGED,
    OccupancyFeeStatus.EXEMPT,
])
def test_settle_all_terminal_states_idempotent(status):
    e = _event(fee_status=status, fee_amount=Decimal("5.00"),
               match_order_id=200, occupancy_minutes=90)
    db = _settle_db()
    res = svc.settle_occupancy_event(db, e)
    assert res["fee_status"] == status.value


def test_settle_not_exited_pending():
    """未离场 → PENDING fee=0。"""
    e = _event(exit_at=None)
    db = _settle_db()
    res = svc.settle_occupancy_event(db, e)
    assert res["fee_status"] == "pending"
    assert res["fee_amount"] == Decimal("0.00")
    assert res["occupancy_minutes"] == 0
    db.flush.assert_called_once()


def test_settle_occupancy_zero_pending():
    """exit<=enter → occupancy=0 → PENDING。"""
    e = _event(exit_at=datetime(2026, 7, 28, 10, 0))  # exit==enter
    db = _settle_db(matched_order=None)
    res = svc.settle_occupancy_event(db, e)
    assert res["fee_status"] == "pending"
    assert res["occupancy_minutes"] == 0


def test_settle_no_parking_rule_pending():
    """有 occupancy 但站点未配费率 → PENDING, occupancy 已写入。"""
    e = _event(exit_at=datetime(2026, 7, 28, 12, 0))
    db = _settle_db(matched_order=None, parking_rule=None)
    res = svc.settle_occupancy_event(db, e)
    assert res["fee_status"] == "pending"
    assert res["fee_amount"] == Decimal("0.00")
    assert res["occupancy_minutes"] == 120
    assert e.occupancy_minutes == 120


def test_settle_billing_exception_pending():
    """compute_parking_fee_full 抛异常 → 不崩, PENDING。"""
    e = _event(exit_at=datetime(2026, 7, 28, 12, 0))
    db = _settle_db(matched_order=None, parking_rule=_pp_row(free_minutes=30))
    with patch.object(svc, "compute_parking_fee_full",
                      side_effect=ValueError("boom")):
        res = svc.settle_occupancy_event(db, e)
    assert res["fee_status"] == "pending"
    assert res["fee_amount"] == Decimal("0.00")


def test_settle_exempt_when_fee_zero():
    """有费率但 fee<=0 (免费时段内/充电全覆盖) → EXEMPT。"""
    e = _event(exit_at=datetime(2026, 7, 28, 10, 20))  # 20min, free=30
    db = _settle_db(matched_order=None, parking_rule=_pp_row(free_minutes=30))
    res = svc.settle_occupancy_event(db, e)
    assert res["fee_status"] == "exempt"
    assert res["fee_amount"] == Decimal("0.00")
    assert e.fee_status == OccupancyFeeStatus.EXEMPT


def test_settle_merged_into_order():
    """有匹配订单 + fee>0 → MERGED, 调 _merge_fee_into_order。

    在场 10:00-13:00(180min), 充电 10:00-12:00(120min, exempt), free=0, rate=6/h。
    billable = 180-0-120 = 60min → fee=6.00 → MERGED。
    """
    order = _order()
    e = _event(exit_at=datetime(2026, 7, 28, 13, 0))
    db = _settle_db(matched_order=order,
                    parking_rule=_pp_row(free_minutes=0, hourly_rate=Decimal("6")))
    with patch.object(svc, "_merge_fee_into_order") as merge:
        res = svc.settle_occupancy_event(db, e)
    assert res["fee_status"] == "merged"
    assert res["match_order_id"] == order.id
    merge.assert_called_once()
    assert e.fee_status == OccupancyFeeStatus.MERGED


def test_settle_billed_standalone_no_order():
    """无匹配订单 + fee>0 → BILLED, fee 落 event。"""
    e = _event(exit_at=datetime(2026, 7, 28, 12, 0))
    db = _settle_db(matched_order=None,
                    parking_rule=_pp_row(free_minutes=0, hourly_rate=Decimal("6")))
    res = svc.settle_occupancy_event(db, e)
    assert res["fee_status"] == "billed"
    assert res["match_order_id"] is None
    assert e.fee_status == OccupancyFeeStatus.BILLED
    assert e.fee_amount == res["fee_amount"]


def test_settle_locked_event_replaces_argument():
    """行锁重读到 locked(非 None) → 用 locked 替换传入 event 计算。"""
    locked = _event(eid=1, fee_status=OccupancyFeeStatus.BILLED,
                    fee_amount=Decimal("9.00"), match_order_id=300,
                    occupancy_minutes=60)
    e_arg = _event(eid=1, fee_status=OccupancyFeeStatus.PENDING)
    db = _settle_db(locked=locked)
    res = svc.settle_occupancy_event(db, e_arg)
    # locked 是 BILLED(终结) → 幂等返回 locked 的值
    assert res["fee_amount"] == Decimal("9.00")
    assert res["match_order_id"] == 300


# ═══════════════════════════════════════════════════════════
# 8. ingest_parking_event — 幂等
# ═══════════════════════════════════════════════════════════

def _ingest_db(*, open_event=None, dup_event=None):
    db = MagicMock()
    calls = {"n": 0}
    open_q = _chain_query(open_event)
    dup_q = _chain_query(dup_event)
    queries = [open_q, dup_q]

    def _query(_model=None, *a, **k):
        i = min(calls["n"], len(queries) - 1)
        calls["n"] += 1
        return queries[i]
    db.query.side_effect = _query
    db.add = MagicMock()
    db.flush = MagicMock()
    return db


def test_ingest_open_event_then_exit_resets_status():
    """同站同车牌未离场事件 → 首次离场重置 fee_status/amount/match。"""
    open_ev = MagicMock()
    open_ev.exit_at = None
    open_ev.source = OccupancyEventSource.ALPR
    db = _ingest_db(open_event=open_ev)
    got = svc.ingest_parking_event(
        db, plate_number="京A12345", station_id=10,
        enter_at=datetime(2026, 7, 28, 10, 0),
        exit_at=datetime(2026, 7, 28, 13, 0))
    assert got is open_ev
    assert got.exit_at == datetime(2026, 7, 28, 13, 0)
    assert got.fee_status == OccupancyFeeStatus.PENDING
    assert got.fee_amount == Decimal("0.00")
    assert got.match_order_id is None
    db.add.assert_not_called()        # 更新既有, 不新建


def test_ingest_open_event_with_existing_exit_updates_exit():
    """既有事件已有 exit, 再次带 exit → 仅更新 exit_at(不重置状态)。"""
    open_ev = MagicMock()
    open_ev.exit_at = datetime(2026, 7, 28, 12, 0)  # 已离场(但匹配为 open query 结果)
    open_ev.fee_status = OccupancyFeeStatus.BILLED
    open_ev.source = OccupancyEventSource.ALPR
    db = _ingest_db(open_event=open_ev)
    got = svc.ingest_parking_event(
        db, plate_number="京A12345", station_id=10,
        enter_at=datetime(2026, 7, 28, 10, 0),
        exit_at=datetime(2026, 7, 28, 14, 0))
    # 走 elif exit_at is not None 分支: 仅赋 exit, 不重置 status
    assert got.exit_at == datetime(2026, 7, 28, 14, 0)
    assert got.fee_status == OccupancyFeeStatus.BILLED  # 未重置


def test_ingest_open_event_no_exit_keeps_open():
    """未离场事件 + 本次也无 exit → 仅更新 source。"""
    open_ev = MagicMock()
    open_ev.exit_at = None
    open_ev.source = OccupancyEventSource.ALPR
    db = _ingest_db(open_event=open_ev)
    got = svc.ingest_parking_event(
        db, plate_number="京A12345", station_id=10,
        enter_at=datetime(2026, 7, 28, 10, 0), exit_at=None,
        source="charging_estimate")
    assert got is open_ev
    assert got.source == OccupancyEventSource.CHARGING_ESTIMATE


def test_ingest_duplicate_full_event_idempotent():
    """完全相同(plate+station+enter+exit)已离场事件 → 幂等返回。"""
    dup = MagicMock(id=999)
    db = _ingest_db(open_event=None, dup_event=dup)
    got = svc.ingest_parking_event(
        db, plate_number="京A12345", station_id=10,
        enter_at=datetime(2026, 7, 28, 10, 0),
        exit_at=datetime(2026, 7, 28, 13, 0))
    assert got is dup
    db.add.assert_not_called()


def test_ingest_creates_new_event():
    """无 open/无 dup → 新建事件入库。"""
    created = []
    db = MagicMock()
    db.query.return_value = _chain_query(None)
    db.add.side_effect = lambda obj: created.append(obj)
    db.flush = MagicMock()
    got = svc.ingest_parking_event(
        db, plate_number="京B88888", station_id=20,
        enter_at=datetime(2026, 7, 28, 10, 0),
        exit_at=datetime(2026, 7, 28, 12, 0))
    assert got.plate_number == "京B88888"
    assert got.source == OccupancyEventSource.ALPR
    assert got.fee_status == OccupancyFeeStatus.PENDING
    db.add.assert_called_once()
    db.flush.assert_called_once()


def test_ingest_invalid_source_falls_back_to_alpr():
    """非法 source → 兜底 ALPR。"""
    db = MagicMock()
    db.query.return_value = _chain_query(None)
    db.add = MagicMock()
    db.flush = MagicMock()
    got = svc.ingest_parking_event(
        db, plate_number="京C", station_id=30,
        enter_at=datetime(2026, 7, 28, 10, 0),
        source="bogus-source")
    assert got.source == OccupancyEventSource.ALPR


def test_ingest_empty_source_defaults_alpr():
    db = MagicMock()
    db.query.return_value = _chain_query(None)
    db.add = MagicMock()
    db.flush = MagicMock()
    got = svc.ingest_parking_event(
        db, plate_number="京D", station_id=40,
        enter_at=datetime(2026, 7, 28, 10, 0), source="")
    assert got.source == OccupancyEventSource.ALPR


def test_ingest_valid_source_charging_estimate():
    db = MagicMock()
    db.query.return_value = _chain_query(None)
    db.add = MagicMock()
    db.flush = MagicMock()
    got = svc.ingest_parking_event(
        db, plate_number="京E", station_id=50,
        enter_at=datetime(2026, 7, 28, 10, 0),
        source="charging_estimate")
    assert got.source == OccupancyEventSource.CHARGING_ESTIMATE


# ═══════════════════════════════════════════════════════════
# 9. _TERMINAL_STATES 常量契约
# ═══════════════════════════════════════════════════════════

def test_terminal_states_constant():
    """终结状态集合 = BILLED/MERGED/EXEMPT (PENDING 非)。"""
    assert set(svc._TERMINAL_STATES) == {
        OccupancyFeeStatus.BILLED,
        OccupancyFeeStatus.MERGED,
        OccupancyFeeStatus.EXEMPT,
    }
    assert OccupancyFeeStatus.PENDING not in svc._TERMINAL_STATES
