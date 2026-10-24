#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
占位费时区错位回归 (工作卡 5a18d1ee, 时区缺陷族 AK-1弹)

缺陷: parking_event.enter_at/exit_at 与 charging_order.start_time/end_time 均
naive-UTC 落库, 但 occupancy_fee_service._wall 用 to_aware_biz_tz 对 naive
"表面解释为上海墙钟"(不改数字) → UTC 墙钟被当上海墙钟:
- TOU 峰谷/夜间窗判定错位 8h → 金额错
- _match_charging_order 事件(上海墙钟) vs 订单(UTC) 单侧比较 → 窗口匹配错位 8h
- parking_events ingest 直接落 body.enter_at → naive 上海墙钟混入 UTC 列

修复后契约:
- DB naive-UTC 列读回经 naive_utc_to_biz_wall 真换算取业务墙钟/业务日
- 窗口匹配两侧统一 UTC 轴(_utc_naive)
- ingest 上报 aware/naive 均归一 naive-UTC 落库
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import occupancy_fee_service as svc
from app.tasks.tz_utils import get_biz_tz, naive_utc_to_biz_wall

client = TestClient(app)

UTC = timezone.utc
BIZ = get_biz_tz()  # Asia/Shanghai


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """注入 test_db(override SessionLocal + seed admin), 每测试独立 DB。"""
    pass


def _auth_headers():
    resp = client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json().get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


def _seed_station(session, code="STTZ01"):
    from app.models.station import Station, StationStatus
    st = Station(name="占位时区测试站", code=code, address="测试地址",
                 status=StationStatus.NORMAL)
    session.add(st); session.commit(); session.refresh(st)
    return st


def _seed_parking_price(session, station_id, *, free_minutes=30, hourly_rate=6.0,
                        night_rate=None, night_start=None, night_end=None):
    from app.models.pricing_v2 import ParkingPrice
    session.add(ParkingPrice(
        station_id=station_id, free_minutes=free_minutes,
        hourly_rate=Decimal(str(hourly_rate)),
        enable_night_rate=night_rate is not None,
        night_rate=Decimal(str(night_rate)) if night_rate is not None else None,
        night_start=time.fromisoformat(night_start) if night_start else None,
        night_end=time.fromisoformat(night_end) if night_end else None,
        effective_date=date(2026, 1, 1), is_active=True,
    )); session.commit()


def _seed_order(session, station_id, plate, start_utc_naive, end_utc_naive):
    """充电订单, start/end_time 按真实写入口径 naive-UTC (卡 f7422bbc)。"""
    from app.models.charging_order import ChargingOrder, OrderStatus, UserType
    from app.models.device import Device, DeviceType
    dev = session.query(Device).filter(Device.station_id == station_id).first()
    if dev is None:
        dev = Device(sn=f"TZDEV{station_id}", name="tz-dev",
                     type=DeviceType.CHARGER_AC, station_id=station_id)
        session.add(dev); session.flush()
    o = ChargingOrder(
        order_no=f"TZ{start_utc_naive.strftime('%m%d%H%M')}{plate[-2:]}",
        station_id=station_id, plate_number=plate, device_id=dev.id,
        user_type=UserType.APP,
        order_status=OrderStatus.COMPLETED,
        start_time=start_utc_naive, end_time=end_utc_naive,
        electricity_fee=Decimal("0"), service_fee=Decimal("0"),
        total_amount=Decimal("0"),
    )
    session.add(o); session.commit(); session.refresh(o)
    return o


# ═══════════════════════════════════════════════════════════════
# 0. helper 直测: naive-UTC 真换算, 不再表面解释
# ═══════════════════════════════════════════════════════════════

def test_naive_utc_to_biz_wall_converts():
    """naive-UTC 16:00 → 上海次日 00:00 (旧 _wall 会原样返回 16:00)。"""
    assert naive_utc_to_biz_wall(datetime(2026, 7, 28, 16, 0)) == \
        datetime(2026, 7, 29, 0, 0)


def test_wall_on_db_naive_utc_converts():
    assert svc._wall(datetime(2026, 7, 28, 16, 0)) == datetime(2026, 7, 29, 0, 0)


def test_utc_naive_aware_converts_and_naive_passthrough():
    aware = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)
    assert svc._utc_naive(aware) == datetime(2026, 7, 28, 10, 0)
    naive = datetime(2026, 7, 28, 2, 0)
    assert svc._utc_naive(naive) is naive  # DB 读回即 UTC, 原值


# ═══════════════════════════════════════════════════════════════
# a) UTC 16:00 前夜订单 → 上海 00:00 起夜间窗, 不按日间计费
# ═══════════════════════════════════════════════════════════════

def test_night_window_before_utc_16_billed_as_night(test_db):
    """上海 00:00-06:00 (UTC 前日 16:00-22:00) 夜间率 1 元/h, 日间 6 元/h。

    在场 UTC 15:30-17:30 = 上海 23:30-01:30, 夜窗 23:00-07:00 全覆盖 →
    billable 120min(free=0) 按夜间 1 元/h → fee 2.00。
    旧缺陷: UTC 墙钟 15:30-17:30 被当上海日间 → 按日间 6 元/h 计 12.00。
    """
    s = test_db["session"]
    st = _seed_station(s)
    _seed_parking_price(s, st.id, free_minutes=0, hourly_rate=6.0,
                        night_rate=1.0, night_start="23:00", night_end="07:00")
    resp = client.post("/api/v1/parking/events", json={
        "plate_number": "沪N0001", "station_id": st.id,
        # naive 上报 = 上海墙钟 23:30-01:30(跨日)
        "enter_at": "2026-07-28T23:30:00",
        "exit_at": "2026-07-29T01:30:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["fee_status"] == "billed"
    assert data["occupancy_minutes"] == 120
    assert data["fee_amount"] == 2.0, \
        f"夜间窗被当日间计费: {data['fee_amount']} (期望 2.0, 旧缺陷值 12.0)"


# ═══════════════════════════════════════════════════════════════
# b) 上海白天停车 → 订单窗口能匹配 (旧缺陷错位 8h 丢匹配)
# ═══════════════════════════════════════════════════════════════

def test_daytime_parking_matches_order_window(test_db):
    """上海 10:00-13:00 在场, 充电订单 UTC 02:30-04:30 = 上海 10:30-12:30。

    落库后事件 enter/exit = UTC 02:00-05:00。旧缺陷: 事件被换上海墙钟 10:00-13:00
    与订单 UTC 02:30-04:30 比较 → 相交(02:30<13:00 且 04:30<10:00 end<enter)
    匹配丢失 → 误走独立账单 BILLED。修复后同轴 UTC 匹配成功 → MERGED。
    """
    s = test_db["session"]
    st = _seed_station(s)
    _seed_parking_price(s, st.id, free_minutes=0, hourly_rate=6.0)
    _seed_order(s, st.id, "沪M0002",
                datetime(2026, 7, 28, 2, 30),   # UTC = 上海 10:30
                datetime(2026, 7, 28, 4, 30))   # UTC = 上海 12:30
    resp = client.post("/api/v1/parking/events", json={
        "plate_number": "沪M0002", "station_id": st.id,
        "enter_at": "2026-07-28T10:00:00",      # 上海
        "exit_at": "2026-07-28T13:00:00",       # 上海
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["fee_status"] == "merged", f"订单匹配丢失: {data}"
    assert data["match_order_id"] is not None
    # 180min 在场 − 120min 充电免除 = 60min × 6 元/h = 6.00
    assert data["fee_amount"] == 6.0


# ═══════════════════════════════════════════════════════════════
# c) 跨午夜进出场 → 业务日归属正确 (费率按进场业务日选取)
# ═══════════════════════════════════════════════════════════════

def test_cross_midnight_event_uses_enter_business_day_rule(test_db):
    """进场上海 7/28 23:00, 离场 7/29 01:00。

    费率版本按进场业务日 7/28 选取: 当日有效费率 6 元/h, 次日起才换成 3 元/h。
    旧缺陷: UTC 15:00 表面解释 7/28 与真换算同为 7/28 不暴露 — 用 7/29 起生效
    费率 + 进场 UTC 16:00(上海 7/29 00:00) 场景: 表面解释取 UTC 日 7/28 误选旧费率。
    """
    from app.models.parking_event import OccupancyEvent
    s = test_db["session"]
    st = _seed_station(s)
    # 旧费率 7/28 前有效; 新费率 7/29 起生效 3 元/h
    _seed_parking_price(s, st.id, free_minutes=0, hourly_rate=9.9)
    from app.models.pricing_v2 import ParkingPrice
    old = s.query(ParkingPrice).filter(
        ParkingPrice.station_id == st.id).first()
    old.expire_date = date(2026, 7, 28); s.commit()
    s.add(ParkingPrice(
        station_id=st.id, free_minutes=0, hourly_rate=Decimal("3.0"),
        enable_night_rate=False,
        effective_date=date(2026, 7, 29), is_active=True)); s.commit()

    resp = client.post("/api/v1/parking/events", json={
        "plate_number": "沪X0003", "station_id": st.id,
        "enter_at": "2026-07-29T01:00:00",   # 上海 7/29 01:00 = UTC 7/28 17:00
        "exit_at": "2026-07-29T03:00:00",    # 上海 03:00
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["fee_status"] == "billed"
    assert data["occupancy_minutes"] == 120
    # 业务日 7/29 → 3 元/h → 6.00 (旧缺陷取 UTC 日 7/28 → 9.9 元/h → 19.8)
    assert data["fee_amount"] == 6.0


# ═══════════════════════════════════════════════════════════════
# d) ingest aware / naive 上报均归一 naive-UTC 落库
# ═══════════════════════════════════════════════════════════════

def test_ingest_naive_report_stored_as_utc(test_db):
    """naive 上海 10:00 上报 → 落库 UTC 02:00。"""
    from app.models.parking_event import OccupancyEvent
    s = test_db["session"]
    st = _seed_station(s)
    resp = client.post("/api/v1/parking/events", json={
        "plate_number": "沪A0004", "station_id": st.id,
        "enter_at": "2026-07-28T10:00:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    ev = s.query(OccupancyEvent).filter(
        OccupancyEvent.plate_number == "沪A0004").one()
    assert ev.enter_at == datetime(2026, 7, 28, 2, 0)  # naive-UTC


def test_ingest_aware_report_stored_as_utc(test_db):
    """aware UTC+8 墙钟 10:00 上报 → 真换算落库 UTC 02:00 (与 naive 同值)。"""
    from app.models.parking_event import OccupancyEvent
    s = test_db["session"]
    st = _seed_station(s)
    resp = client.post("/api/v1/parking/events", json={
        "plate_number": "沪B0005", "station_id": st.id,
        "enter_at": "2026-07-28T10:00:00+08:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    ev = s.query(OccupancyEvent).filter(
        OccupancyEvent.plate_number == "沪B0005").one()
    assert ev.enter_at == datetime(2026, 7, 28, 2, 0)  # naive-UTC
