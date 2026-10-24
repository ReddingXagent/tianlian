"""
全局退款记录列表端点测试 (卡 34ec1d55)

覆盖 GET /api/v1/orders/refunds:
- 路由注册序: '/orders/refunds' 不被 '/orders/{order_id}/refunds' 捕获 (422 防回归)
- 分页翻页 / total
- status 过滤 (合法/非法)
- team scoping: 非 platform admin 仅见本 team (经 ChargingOrder.station→Station.team)
- order_no / station_name 扩展字段
"""
from decimal import Decimal

import pytest

from app.models.charging_order import (
    ChargingOrder, OrderPaymentStatus, OrderStatus, PaymentMethod, UserType,
)
from app.models.order_fee_item import RefundRecord, RefundStatus
from app.models.station import Station
from app.models.user import User, UserRole

# 非 admin 团队用户 — 直接调用 router 函数用 (绕过 write permission, 只验 scoping)
_TEAM1_USER = User(id=901, username="t1eng", role=UserRole.ENGINEER, status="active", team_id=1)
_ADMIN = User(id=1, username="admin", role=UserRole.ADMIN, status="active")


def _seed(session):
    """2 站 2 队 3 订单 4 退款"""
    stations = [
        Station(id=101, name="郑州一队站", code="GLR-S1", team_id=1),
        Station(id=102, name="广州二队站", code="GLR-S2", team_id=2),
    ]
    session.add_all(stations)
    orders = [
        ChargingOrder(
            order_no="GLR001", station_id=101, device_id=1, user_id=1,
            user_type=UserType.APP, total_amount=Decimal("100.00"), paid_amount=Decimal("100.00"),
            payment_status=OrderPaymentStatus.REFUNDING, order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.WECHAT,
        ),
        ChargingOrder(
            order_no="GLR002", station_id=101, device_id=2, user_id=2,
            user_type=UserType.APP, total_amount=Decimal("80.00"), paid_amount=Decimal("80.00"),
            payment_status=OrderPaymentStatus.REFUNDED, order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.WECHAT,
        ),
        ChargingOrder(
            order_no="GLR003", station_id=102, device_id=3, user_id=3,
            user_type=UserType.APP, total_amount=Decimal("60.00"), paid_amount=Decimal("60.00"),
            payment_status=OrderPaymentStatus.REFUNDING, order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.WECHAT,
        ),
    ]
    session.add_all(orders)
    session.flush()
    refunds = [
        RefundRecord(order_id=orders[0].id, user_id=1, refund_amount=Decimal("30.00"),
                     reason="充电中断", status=RefundStatus.PENDING),
        RefundRecord(order_id=orders[1].id, user_id=2, refund_amount=Decimal("20.00"),
                     reason="系统多扣", status=RefundStatus.REFUNDED),
        RefundRecord(order_id=orders[1].id, user_id=2, refund_amount=Decimal("10.00"),
                     reason="重复扣费", status=RefundStatus.REJECTED, reject_reason="不符合条件"),
        RefundRecord(order_id=orders[2].id, user_id=3, refund_amount=Decimal("50.00"),
                     reason="二队退款", status=RefundStatus.PENDING),
    ]
    session.add_all(refunds)
    session.commit()
    return orders, refunds


class TestRouteRegistration:
    """路由注册序 — /orders/refunds 必须先于 /orders/{order_id}/refunds"""

    def test_route_not_captured_as_order_id(self, client):
        """GET /api/v1/orders/refunds 返回 200 列表, 非 422 ('refunds' 被当 order_id)"""
        _seed(client._sesh)
        resp = client.get("/api/v1/orders/refunds")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total"] == 4
        nos = {i["order_no"] for i in data["items"]}
        assert nos == {"GLR001", "GLR002", "GLR003"}

    def test_items_include_order_no_and_station_name(self, client):
        """扩展字段: order_no + station_name"""
        _seed(client._sesh)
        data = client.get("/api/v1/orders/refunds").json()["data"]
        by_order = {i["order_no"]: i for i in data["items"]}
        assert by_order["GLR001"]["station_name"] == "郑州一队站"
        assert by_order["GLR003"]["station_name"] == "广州二队站"
        # _refund_to_dict 基础字段仍在
        assert by_order["GLR001"]["status"] == "pending"
        assert by_order["GLR001"]["refund_amount"] == 30.0


class TestPagination:
    """分页翻页"""

    def test_page2_returns_remaining(self, client):
        _seed(client._sesh)
        p1 = client.get("/api/v1/orders/refunds", params={"page": 1, "page_size": 2}).json()["data"]
        p2 = client.get("/api/v1/orders/refunds", params={"page": 2, "page_size": 2}).json()["data"]
        assert p1["total"] == 4 and len(p1["items"]) == 2
        assert p2["total"] == 4 and len(p2["items"]) == 2
        assert p1["page"] == 1 and p2["page"] == 2
        ids1 = {i["id"] for i in p1["items"]}
        ids2 = {i["id"] for i in p2["items"]}
        assert not (ids1 & ids2), "翻页不得重复"

    def test_page_size_over_100_rejected(self, client):
        _seed(client._sesh)
        resp = client.get("/api/v1/orders/refunds", params={"page_size": 101})
        assert resp.status_code == 422

    def test_page_zero_rejected(self, client):
        resp = client.get("/api/v1/orders/refunds", params={"page": 0})
        assert resp.status_code == 422


class TestStatusFilter:
    """status 过滤"""

    def test_filter_refunded(self, client):
        _seed(client._sesh)
        data = client.get("/api/v1/orders/refunds", params={"status": "refunded"}).json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["reason"] == "系统多扣"
        assert data["items"][0]["order_no"] == "GLR002"

    def test_filter_pending(self, client):
        _seed(client._sesh)
        data = client.get("/api/v1/orders/refunds", params={"status": "pending"}).json()["data"]
        assert data["total"] == 2

    def test_invalid_status_400(self, client):
        resp = client.get("/api/v1/orders/refunds", params={"status": "bogus"})
        assert resp.status_code == 400


class TestTeamScoping:
    """team scoping — 非 platform admin 仅见本 team 站点的订单退款"""

    def test_team1_user_sees_only_own_team(self, test_db):
        from app.api.v1.order_fees import list_all_refunds

        session = test_db["session"]
        _seed(session)
        resp = list_all_refunds(db=session, user=_TEAM1_USER)
        data = resp["data"]
        assert data["total"] == 3  # GLR001 x1 + GLR002 x2, 不含 GLR003(二队)
        nos = {i["order_no"] for i in data["items"]}
        assert nos == {"GLR001", "GLR002"}

    def test_team2_user_sees_only_own_team(self, test_db):
        from app.api.v1.order_fees import list_all_refunds

        session = test_db["session"]
        _seed(session)
        team2_user = User(id=902, username="t2eng", role=UserRole.ENGINEER, status="active", team_id=2)
        data = list_all_refunds(db=session, user=team2_user)["data"]
        assert data["total"] == 1
        assert data["items"][0]["order_no"] == "GLR003"

    def test_admin_sees_all(self, test_db):
        from app.api.v1.order_fees import list_all_refunds

        session = test_db["session"]
        _seed(session)
        data = list_all_refunds(db=session, user=_ADMIN)["data"]
        assert data["total"] == 4

    def test_team_scoping_status_filter_combined(self, test_db):
        from app.api.v1.order_fees import list_all_refunds

        session = test_db["session"]
        _seed(session)
        resp = list_all_refunds(status="pending", db=session, user=_TEAM1_USER)
        data = resp["data"]
        assert data["total"] == 1
        assert data["items"][0]["order_no"] == "GLR001"
