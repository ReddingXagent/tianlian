#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财务管理 API 测试 (app/api/v1/operate/financial.py, 工作卡 65f59428)

覆盖 5 个只读端点 (前缀 /api/v1/operate):
- GET /financial/charges       电费明细 (PAID 订单 + station_id 过滤 + team scoping + 越权 404)
- GET /financial/parking       停车费 (parking_fee > 0)
- GET /financial/occupancy     占桩费 (idle_penalty > 0)
- GET /financial/reservations  预约费 (reservation_fee > 0)
- GET /financial/refunds       退款 (payment_status ∈ refunding/refunded/partial)

覆盖维度:
(a) 正常路径: 各费用类型字段正确 + 分页 + station_id 过滤
(b) team scoping: 非 admin 仅见本 team 站点; 越权 station_id → 404 (不泄露存在)
(c) admin 全量可见 (跨 team)
(d) 参数校验: page<1 / page_size 越界 → 422
(e) 空数据不报错 (返回空 items + total 0)
(f) 日期范围过滤 (start_date / end_date 半开区间)
(g) 权限门 (router-level get_current_user): 匿名 → 401

铁律: 仅加测试, 不改业务代码。
"""
import uuid

import bcrypt
from datetime import datetime, timezone
from decimal import Decimal

from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

from tests.api._helpers import login_as, login_admin

FIN = "/api/v1/operate/financial"


# ───────────────────────── seed helpers ─────────────────────────


def _station(session, name, code, team_id):
    s = Station(
        name=name, code=code, address="测试地址",
        status=StationStatus.NORMAL, team_id=team_id,
    )
    session.add(s)
    session.flush()
    return s


def _order(
    session, station_id, *,
    paid=Decimal("10.00"), kwh=Decimal("0"), efee=Decimal("0"),
    park=Decimal("0"), idle=Decimal("0"), reservation=Decimal("0"),
    total=None, created_at=None, plate="京A12345",
    payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
    payment_method=PaymentMethod.WECHAT, device_id=1, user_type=UserType.APP,
):
    """造一条 ChargingOrder (order_no 用 uuid 保证唯一)。"""
    o = ChargingOrder(
        order_no=f"FIN-{uuid.uuid4().hex[:12]}",
        station_id=station_id, device_id=device_id, user_type=user_type,
        plate_number=plate,
        charged_kwh=kwh, electricity_fee=efee,
        parking_fee=park, idle_penalty=idle, reservation_fee=reservation,
        total_amount=total if total is not None else paid,
        paid_amount=paid, payment_status=payment_status, order_status=order_status,
        payment_method=payment_method,
        created_at=created_at,
    )
    session.add(o)
    session.flush()
    return o


def _make_team_user(client, team_id, username, role=UserRole.VIEWER):
    """创建带 team_id 的非 admin 用户, 供 team scoping / 越权验证。"""
    s = client._sesh
    existing = s.query(User).filter(User.username == username).first()
    if existing:
        existing.team_id = team_id
        s.commit()
        return existing
    u = User(
        username=username,
        password_hash=bcrypt.hashpw(b"v123456", bcrypt.gensalt()).decode(),
        real_name=username, role=role, status="active", team_id=team_id,
    )
    s.add(u)
    s.commit()
    return u


# ═══════════════════════════════════════════════════════════════
# 1. 电费明细 charges
# ═══════════════════════════════════════════════════════════════

class TestCharges:
    """GET /financial/charges"""

    def test_charges_fields_and_paid_filter(self, client):
        """PAID 订单出现且字段正确; 非 PAID 被过滤。"""
        s = client._sesh
        sta = _station(s, "电费站", "FC001", team_id=None)
        _order(s, sta.id, paid=Decimal("12.50"), kwh=Decimal("30"),
               efee=Decimal("12.50"), plate="京P0001")
        # UNPAID 不应出现
        _order(s, sta.id, paid=Decimal("99.00"), kwh=Decimal("5"),
               payment_status=OrderPaymentStatus.UNPAID, plate="京P0002")
        s.commit()

        r = client.get(f"{FIN}/charges")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 1
        it = d["items"][0]
        assert it["charged_kwh"] == 30.0
        assert it["electricity_fee"] == 12.5
        assert it["total_amount"] == 12.5
        assert it["paid_amount"] == 12.5
        assert it["station_name"] == "电费站"
        assert it["plate_number"] == "京P0001"
        assert it["payment_method"] == "im_b"

    def test_charges_station_name_fallback(self, client):
        """站点已删除 (stations 查不到) → 回退 站点#{id}。"""
        s = client._sesh
        # 用一个不存在的 station_id 直接造订单 (不建 Station)
        o = ChargingOrder(
            order_no=f"FIN-{uuid.uuid4().hex[:12]}",
            station_id=777777, device_id=1, charged_kwh=Decimal("1"),
            electricity_fee=Decimal("1"), total_amount=Decimal("1"),
            paid_amount=Decimal("1"), payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED, payment_method=PaymentMethod.WECHAT,
        )
        s.add(o)
        s.commit()
        r = client.get(f"{FIN}/charges")
        assert r.status_code == 200
        it = r.json()["data"]["items"][0]
        assert it["station_name"] == "站点#777777"

    def test_charges_station_id_filter(self, client):
        s = client._sesh
        sa = _station(s, "站A", "FSA", team_id=None)
        sb = _station(s, "站B", "FSB", team_id=None)
        _order(s, sa.id, plate="A1")
        _order(s, sb.id, plate="B1")
        s.commit()
        r = client.get(f"{FIN}/charges", params={"station_id": sa.id})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 1
        assert d["items"][0]["plate_number"] == "A1"

    def test_charges_pagination(self, client):
        s = client._sesh
        sta = _station(s, "分页站", "FPG", team_id=None)
        for i in range(3):
            _order(s, sta.id, plate=f"P{i}")
        s.commit()
        r = client.get(f"{FIN}/charges", params={"page": 1, "page_size": 2})
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2

    def test_charges_invalid_page_422(self, client):
        r = client.get(f"{FIN}/charges", params={"page": 0})
        assert r.status_code == 422

    def test_charges_invalid_page_size_422(self, client):
        r = client.get(f"{FIN}/charges", params={"page_size": 0})
        assert r.status_code == 422

    def test_charges_date_range(self, client):
        """start_date / end_date 半开区间过滤 created_at。"""
        s = client._sesh
        sta = _station(s, "日期站", "FDT", team_id=None)
        _order(s, sta.id, created_at=datetime(2026, 6, 1, tzinfo=timezone.utc), plate="D1")
        _order(s, sta.id, created_at=datetime(2026, 7, 1, tzinfo=timezone.utc), plate="D2")
        s.commit()
        r = client.get(f"{FIN}/charges", params={
            "start_date": "2026-06-15", "end_date": "2026-07-15",
        })
        d = r.json()["data"]
        assert d["total"] == 1
        assert d["items"][0]["plate_number"] == "D2"


# ═══════════════════════════════════════════════════════════════
# 2. team scoping + 越权 404
# ═══════════════════════════════════════════════════════════════

class TestTeamScoping:
    """非 admin 仅见本 team; 越权 station_id → 404 (不泄露存在)。"""

    def test_admin_sees_all_teams(self, client):
        s = client._sesh
        sa = _station(s, "本队", "TMA", team_id=1)
        sb = _station(s, "他队", "TMB", team_id=2)
        _order(s, sa.id, plate="T1")
        _order(s, sb.id, plate="T2")
        s.commit()
        # admin 默认身份
        r = client.get(f"{FIN}/charges")
        assert r.json()["data"]["total"] == 2

    def test_team_viewer_scoped(self, client):
        s = client._sesh
        sa = _station(s, "本队站", "TV1", team_id=1)
        sb = _station(s, "他队站", "TV2", team_id=2)
        _order(s, sa.id, plate="M1")
        _order(s, sb.id, plate="O1")
        _make_team_user(client, team_id=1, username="fin_viewer1")
        s.commit()
        login_as(client, "fin_viewer1", "v123456")
        r = client.get(f"{FIN}/charges")
        d = r.json()["data"]
        assert d["total"] == 1
        assert d["items"][0]["plate_number"] == "M1"

    def test_team_viewer_cross_station_404(self, client):
        """非 admin 传他队 station_id → 404 (assert_station_team_access)。"""
        s = client._sesh
        sb = _station(s, "他队站", "XSS", team_id=2)
        _make_team_user(client, team_id=1, username="fin_viewer2")
        s.commit()
        login_as(client, "fin_viewer2", "v123456")
        r = client.get(f"{FIN}/charges", params={"station_id": sb.id})
        assert r.status_code == 404

    def test_team_viewer_own_station_ok(self, client):
        """非 admin 传本队 station_id → 正常返回。"""
        s = client._sesh
        sa = _station(s, "本队站", "OWS", team_id=1)
        _order(s, sa.id, plate="OK1")
        _make_team_user(client, team_id=1, username="fin_viewer3")
        s.commit()
        login_as(client, "fin_viewer3", "v123456")
        r = client.get(f"{FIN}/charges", params={"station_id": sa.id})
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1


# ═══════════════════════════════════════════════════════════════
# 3. 其他费用类型 (parking / occupancy / reservations / refunds)
# ═══════════════════════════════════════════════════════════════

class TestOtherFeeTypes:
    def test_parking_only_positive(self, client):
        s = client._sesh
        sta = _station(s, "停车站", "FPK", team_id=None)
        _order(s, sta.id, park=Decimal("5.00"), plate="PK1")
        _order(s, sta.id, park=Decimal("0"), plate="PK0")  # 被过滤
        s.commit()
        r = client.get(f"{FIN}/parking")
        d = r.json()["data"]
        assert d["total"] == 1
        assert d["items"][0]["parking_fee"] == 5.0
        assert d["items"][0]["plate_number"] == "PK1"

    def test_occupancy_only_positive(self, client):
        s = client._sesh
        sta = _station(s, "占桩站", "FOC", team_id=None)
        _order(s, sta.id, idle=Decimal("8.00"), plate="OC1")
        _order(s, sta.id, idle=Decimal("0"), plate="OC0")
        s.commit()
        r = client.get(f"{FIN}/occupancy")
        d = r.json()["data"]
        assert d["total"] == 1
        assert d["items"][0]["idle_penalty"] == 8.0

    def test_reservations_only_positive(self, client):
        s = client._sesh
        sta = _station(s, "预约站", "FRS", team_id=None)
        _order(s, sta.id, reservation=Decimal("3.00"), plate="RS1")
        _order(s, sta.id, reservation=Decimal("0"), plate="RS0")
        s.commit()
        r = client.get(f"{FIN}/reservations")
        d = r.json()["data"]
        assert d["total"] == 1
        assert d["items"][0]["reservation_fee"] == 3.0

    def test_refunds_status_filter(self, client):
        """退款列表含 refunding/refunded/partial, 不含 paid。"""
        s = client._sesh
        sta = _station(s, "退款站", "FRF", team_id=None)
        _order(s, sta.id, payment_status=OrderPaymentStatus.REFUNDING, plate="RF1")
        _order(s, sta.id, payment_status=OrderPaymentStatus.REFUNDED, plate="RF2")
        _order(s, sta.id, payment_status=OrderPaymentStatus.PARTIAL, plate="RF3")
        _order(s, sta.id, payment_status=OrderPaymentStatus.PAID, plate="RF4")  # 排除
        s.commit()
        r = client.get(f"{FIN}/refunds")
        d = r.json()["data"]
        assert d["total"] == 3
        statuses = {it["payment_status"] for it in d["items"]}
        assert statuses == {"refunding", "refunded", "partial"}

    def test_empty_all_endpoints(self, client):
        """空数据各端点不报错。"""
        for ep in ("charges", "parking", "occupancy", "reservations", "refunds"):
            r = client.get(f"{FIN}/{ep}")
            assert r.status_code == 200, ep
            d = r.json()["data"]
            assert d["total"] == 0
            assert d["items"] == []


# ═══════════════════════════════════════════════════════════════
# 4. 权限门 (router-level get_current_user)
# ═══════════════════════════════════════════════════════════════

class TestPermissionGate:
    def test_anonymous_401(self, anon_client):
        r = anon_client.get(f"{FIN}/charges")
        assert r.status_code == 401
