"""优惠券管理 API 测试 — app/api/v1/operate/coupon_api.py

补充 test_coupon.py 未覆盖端点：stats / usages / batches / distribute / redeem / update / delete
维度：正常路径 × 业务校验(404/400) × 三类券抵扣计算 × 库存联动 × team scoping × 权限(403) × 参数校验(422)

写端点（create/distribute/redeem/update/delete）经 require_platform_admin 收紧，
非 admin → 403；读端点（stats/usages/batches/list/get）仅认证即可。
"""
from datetime import datetime, timedelta, timezone
import uuid

import pytest

from tests.api._helpers import COUPON_URL, login_as, create_coupon
from app.models.charging_order import ChargingOrder
from app.models.coupon import CouponUsage, CouponStatus


def _distribute(client, coupon_id, quantity=1, user_ids="1"):
    r = client.post(f"{COUPON_URL}/distribute", json={
        "coupon_id": coupon_id, "quantity": quantity,
        "user_ids": user_ids, "batch_name": "测试发放",
    })
    assert r.status_code == 200, f"发放失败: {r.status_code} {r.text[:300]}"
    return r.json()["data"]


def _seed_order(client, user_id=1):
    """插一条最小 ChargingOrder (卡 5f7fa7ba 归属校验后 redeem 须真实订单)"""
    o = ChargingOrder(
        order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=1, device_id=1, user_id=user_id,
    )
    client._sesh.add(o)
    client._sesh.commit()
    client._sesh.refresh(o)
    return o.id


def _redeem(client, code, order_id=None, order_amount=100.0):
    """order_id 缺省时自动种一条 user_id=1 的订单 (与 _distribute 默认持券人一致)"""
    if order_id is None:
        order_id = _seed_order(client, user_id=1)
    return client.post(f"{COUPON_URL}/redeem", json={
        "coupon_code": code, "order_id": order_id, "order_amount": order_amount,
    })


def _make_usage(session, *, coupon_id, user_id, code, status=CouponStatus.ACTIVE,
                expires_in_days=30):
    from datetime import datetime
    u = CouponUsage(
        coupon_id=coupon_id, user_id=user_id, coupon_code=code,
        status=status, expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
    )
    session.add(u)
    session.commit()
    return u


class TestStats:
    def test_stats_empty(self, client):
        r = client.get(f"{COUPON_URL}/stats")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total_coupons"] == 0
        assert data["usage_rate"] == 0

    def test_stats_with_data(self, client):
        cid = create_coupon(client, total_stock=100)
        _distribute(client, cid, quantity=3, user_ids="1,2,3")
        r = client.get(f"{COUPON_URL}/stats")
        data = r.json()["data"]
        assert data["total_coupons"] == 1
        assert data["total_stock"] == 100
        assert data["total_distributed"] == 3


class TestUsages:
    def test_usages_empty(self, client):
        r = client.get(f"{COUPON_URL}/usages")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_usages_team_scoped(self, client, db_session, seed_users):
        """非 admin 仅见本 team 用户的领券记录"""
        cid = create_coupon(client)
        eng = seed_users["engineer1"]
        eng.team_id = 5
        viewer = seed_users["viewer1"]
        viewer.team_id = 999
        db_session.commit()
        _make_usage(db_session, coupon_id=cid, user_id=eng.id, code="CPN-TEAM-OWN")
        _make_usage(db_session, coupon_id=cid, user_id=viewer.id, code="CPN-TEAM-OTHER")
        login_as(client, "engineer1", "eng123")
        r = client.get(f"{COUPON_URL}/usages")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1  # 仅本 team

    def test_usages_filter_status(self, client, db_session):
        cid = create_coupon(client)
        _make_usage(db_session, coupon_id=cid, user_id=1, code="CPN-F1", status=CouponStatus.ACTIVE)
        _make_usage(db_session, coupon_id=cid, user_id=2, code="CPN-F2", status=CouponStatus.USED)
        r = client.get(f"{COUPON_URL}/usages", params={"status": "used"})
        assert r.json()["data"]["total"] == 1


class TestBatches:
    def test_batches_empty(self, client):
        r = client.get(f"{COUPON_URL}/batches")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_batches_after_distribute(self, client):
        cid = create_coupon(client)
        _distribute(client, cid, quantity=2, user_ids="1,2")
        r = client.get(f"{COUPON_URL}/batches")
        assert r.json()["data"]["total"] == 1

    def test_batches_filter_coupon_id(self, client):
        cid1 = create_coupon(client)
        cid2 = create_coupon(client, name="另一券")
        _distribute(client, cid1, quantity=1, user_ids="1")
        _distribute(client, cid2, quantity=1, user_ids="1")
        r = client.get(f"{COUPON_URL}/batches", params={"coupon_id": cid1})
        assert r.json()["data"]["total"] == 1


class TestDistribute:
    def test_distribute_ok(self, client):
        cid = create_coupon(client, total_stock=100)
        data = _distribute(client, cid, quantity=3, user_ids="1,2,3")
        assert data["count"] == 3
        assert len(data["codes"]) == 3
        # 库存已扣减
        from app.models.coupon import Coupon
        c = client._sesh.query(Coupon).filter(Coupon.id == cid).first()
        assert c.remaining_stock == 97

    def test_distribute_coupon_not_found(self, client):
        r = client.post(f"{COUPON_URL}/distribute", json={
            "coupon_id": 99999, "quantity": 1, "user_ids": "1",
        })
        assert r.status_code == 404

    def test_distribute_inactive(self, client):
        cid = create_coupon(client, is_active=False)
        r = client.post(f"{COUPON_URL}/distribute", json={
            "coupon_id": cid, "quantity": 1, "user_ids": "1",
        })
        assert r.status_code == 400
        assert "停用" in r.json()["detail"]

    def test_distribute_insufficient_stock(self, client):
        cid = create_coupon(client, total_stock=5)
        r = client.post(f"{COUPON_URL}/distribute", json={
            "coupon_id": cid, "quantity": 10, "user_ids": "1",
        })
        assert r.status_code == 400
        assert "库存不足" in r.json()["detail"]

    def test_distribute_invalid_quantity(self, client):
        """quantity < 1 → 422"""
        cid = create_coupon(client)
        r = client.post(f"{COUPON_URL}/distribute", json={
            "coupon_id": cid, "quantity": 0, "user_ids": "1",
        })
        assert r.status_code == 422

    def test_distribute_forbidden(self, client, seed_users):
        """非 admin 发放 → 403"""
        cid = create_coupon(client)
        seed_users
        login_as(client, "viewer1", "view123")
        r = client.post(f"{COUPON_URL}/distribute", json={
            "coupon_id": cid, "quantity": 1, "user_ids": "1",
        })
        assert r.status_code == 403


class TestRedeem:
    def test_redeem_fixed(self, client):
        """固定金额券 → discount = face_value"""
        cid = create_coupon(client, coupon_type="fixed", face_value=15.0)
        code = _distribute(client, cid)["codes"][0]
        r = _redeem(client, code, order_amount=100)
        assert r.status_code == 200
        assert r.json()["data"]["discount_amount"] == 15.0

    def test_redeem_percentage(self, client):
        """百分比券 → discount = order_amount * face_value"""
        cid = create_coupon(client, coupon_type="percentage", face_value=0.1)  # 10%
        code = _distribute(client, cid)["codes"][0]
        r = _redeem(client, code, order_amount=200)
        assert r.status_code == 200
        assert r.json()["data"]["discount_amount"] == 20.0

    def test_redeem_percentage_with_cap(self, client):
        """百分比券有上限 → cap 到 max_discount_amount"""
        cid = create_coupon(client, coupon_type="percentage", face_value=0.5,
                            max_discount_amount=50.0)
        code = _distribute(client, cid)["codes"][0]
        r = _redeem(client, code, order_amount=200)  # 0.5*200=100 → cap 50
        assert r.json()["data"]["discount_amount"] == 50.0

    def test_redeem_free_charge(self, client):
        """免单券 → discount = order_amount"""
        cid = create_coupon(client, coupon_type="free_charge", face_value=0)
        code = _distribute(client, cid)["codes"][0]
        r = _redeem(client, code, order_amount=88.5)
        assert r.json()["data"]["discount_amount"] == 88.5

    def test_redeem_below_min_order(self, client):
        """订单金额低于门槛 → 400"""
        cid = create_coupon(client, face_value=10.0, min_order_amount=50.0)
        code = _distribute(client, cid)["codes"][0]
        r = _redeem(client, code, order_amount=30)
        assert r.status_code == 400
        assert "最低消费" in r.json()["detail"]

    def test_redeem_code_not_found(self, client):
        r = _redeem(client, "CPN-NONEXIST")
        assert r.status_code == 404

    def test_redeem_already_used(self, client):
        cid = create_coupon(client, face_value=10.0)
        code = _distribute(client, cid)["codes"][0]
        assert _redeem(client, code).status_code == 200
        r = _redeem(client, code)  # 二次核销
        assert r.status_code == 400
        assert "状态" in r.json()["detail"]

    def test_redeem_expired(self, client):
        cid = create_coupon(client, face_value=10.0)
        code = _distribute(client, cid)["codes"][0]
        # 手动置过期
        from datetime import datetime
        u = client._sesh.query(CouponUsage).filter(CouponUsage.coupon_code == code).first()
        u.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        client._sesh.commit()
        r = _redeem(client, code)
        assert r.status_code == 400
        assert "过期" in r.json()["detail"]

    def test_redeem_forbidden(self, client, seed_users):
        cid = create_coupon(client, face_value=10.0)
        code = _distribute(client, cid)["codes"][0]
        seed_users
        login_as(client, "viewer1", "view123")
        r = _redeem(client, code)
        assert r.status_code == 403

    def test_redeem_missing_fields(self, client):
        """缺 coupon_code → 422"""
        r = client.post(f"{COUPON_URL}/redeem", json={"order_id": 1, "order_amount": 100})
        assert r.status_code == 422


class TestUpdateDelete:
    def test_update_ok(self, client):
        cid = create_coupon(client)
        r = client.put(f"{COUPON_URL}/{cid}", json={"name": "改名券", "is_active": False})
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "改名券"

    def test_update_not_found(self, client):
        r = client.put(f"{COUPON_URL}/99999", json={"name": "x"})
        assert r.status_code == 404

    def test_delete_ok(self, client):
        cid = create_coupon(client)
        r = client.delete(f"{COUPON_URL}/{cid}")
        assert r.status_code == 200
        assert client.get(f"{COUPON_URL}/{cid}").status_code == 404

    def test_delete_not_found(self, client):
        r = client.delete(f"{COUPON_URL}/99999")
        assert r.status_code == 404

    def test_update_forbidden(self, client, seed_users):
        cid = create_coupon(client)
        seed_users
        login_as(client, "viewer1", "view123")
        r = client.put(f"{COUPON_URL}/{cid}", json={"name": "x"})
        assert r.status_code == 403


class TestAuth:
    def test_anon_denied(self, anon_client):
        r = anon_client.get(f"{COUPON_URL}/stats")
        assert r.status_code == 401
