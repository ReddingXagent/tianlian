"""优惠券核销订单归属校验测试 — 卡 5f7fa7ba

安全缺口: redeem 路径 order_id 从请求体直接落库, 全程不查 charging_orders 表。
运营端可对任意整数 order_id 核销, 造成 CouponUsage.order_id 与真实订单脱钩,
后续对账/统计读到幻影订单号。

关键不变量是【订单归属持券人】而非当前用户 —— redeem 是 require_platform_admin
运营端点, admin 不持 C 端券, 按当前用户校验会全灭。校验:
    order.user_id == usage.user_id (持券人)
不存在/非本人 → 契约 §6: HTTP 200 + code=10004 (ORDER_NOT_FOUND, 防枚举)。

参考同构: business_orders.py _get_own_order。
"""
import uuid

from app.models.charging_order import ChargingOrder
from app.models.coupon import CouponStatus, CouponUsage


def _seed_order(session, *, user_id):
    """插一条最小 ChargingOrder, 返回订单 id (SQLite 测试库无 FK 强制)"""
    o = ChargingOrder(
        order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=1,
        device_id=1,
        user_id=user_id,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o.id


def _seed_usage(session, coupon_id, *, user_id=101, status=CouponStatus.ACTIVE,
                code="CPN-GUARD-000001", expires_delta_days=30):
    """插一条持券人为 user_id 的 CouponUsage (对齐 test_operate_coupon._seed_usage)"""
    from datetime import datetime, timedelta, timezone
    u = CouponUsage(
        coupon_id=coupon_id,
        user_id=user_id,
        user_type="app",
        coupon_code=code,
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_delta_days),
    )
    session.add(u)
    session.commit()
    return u


class TestRedeemOrderOwnership:
    """POST /coupon/redeem — 订单归属校验 (卡 5f7fa7ba)"""

    def test_redeem_own_order_succeeds(self, client):
        """正路径: 持券人自己的订单 → 核销成功"""
        from tests.api._helpers import create_coupon
        cid = create_coupon(client, face_value=10.0, min_order_amount=0)
        _seed_usage(client._sesh, cid, user_id=101, code="CPN-OWN-000001")
        oid = _seed_order(client._sesh, user_id=101)

        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "CPN-OWN-000001", "order_id": oid, "order_amount": 100,
        })
        assert r.status_code == 200
        assert r.json()["data"]["discount_amount"] == 10.0
        u = client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_code == "CPN-OWN-000001").first()
        assert u.status == CouponStatus.USED
        assert u.order_id == oid

    def test_redeem_others_order_rejected(self, client):
        """他人订单 (券属 user 101, 订单属 user 999) → 200 + code=10004, 券不动"""
        from tests.api._helpers import create_coupon
        cid = create_coupon(client, face_value=10.0, min_order_amount=0)
        _seed_usage(client._sesh, cid, user_id=101, code="CPN-OTH-000001")
        oid = _seed_order(client._sesh, user_id=999)

        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "CPN-OTH-000001", "order_id": oid, "order_amount": 100,
        })
        assert r.status_code == 200
        assert r.json()["code"] == 10004
        assert r.json()["message"] == "ORDER_NOT_FOUND"
        u = client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_code == "CPN-OTH-000001").first()
        assert u.status == CouponStatus.ACTIVE  # 未被核销
        assert u.order_id is None  # 幻影 order_id 未落库

    def test_redeem_nonexistent_order_rejected(self, client):
        """不存在的订单 (order_id=99999) → 200 + code=10004, 防枚举同响应"""
        from tests.api._helpers import create_coupon
        cid = create_coupon(client, face_value=10.0, min_order_amount=0)
        _seed_usage(client._sesh, cid, user_id=101, code="CPN-NIL-000001")

        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "CPN-NIL-000001", "order_id": 99999, "order_amount": 100,
        })
        assert r.status_code == 200
        assert r.json()["code"] == 10004
        assert r.json()["message"] == "ORDER_NOT_FOUND"
        u = client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_code == "CPN-NIL-000001").first()
        assert u.status == CouponStatus.ACTIVE
