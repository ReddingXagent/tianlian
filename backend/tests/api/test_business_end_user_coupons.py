"""卡 089b01b2 — C端优惠券 (GET /coupons, POST /coupons/claim).

端侧路径 (无 /business): GET /coupons 可用券列表; POST /coupons/claim {coupon_id} 领取。
鉴权: get_current_end_user; 运营 token / 匿名 → 401。
领取: 创建 CouponUsage (user_id=end_user.id), 扣库存 (CAS), per_user_limit 校验。
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.coupon import Coupon, CouponStatus, CouponType, CouponUsage
from app.models.end_user import EndUser

AUTH_URL = "/api/v1/business/auth/wx-login"
BASE = "/api/v1/coupons"


def _login(client, code):
    r = client.post(AUTH_URL, json={"code": code})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _end_user(client, code):
    openid = "mock_" + __import__("hashlib").sha1(code.encode()).hexdigest()[:16]
    return client._sesh.query(EndUser).filter(EndUser.wx_openid == openid).one()


def _seed_coupon(session, *, name="新人券", face_value=10.0, total_stock=100,
                 per_user_limit=1, valid_days=30, is_active=True,
                 start_offset=-1, end_offset=+30, coupon_type=CouponType.FIXED):
    now = datetime.now(timezone.utc)
    c = Coupon(
        name=name,
        coupon_type=coupon_type,
        face_value=Decimal(str(face_value)),
        min_order_amount=Decimal("0"),
        total_stock=total_stock,
        remaining_stock=total_stock,
        per_user_limit=per_user_limit,
        valid_days=valid_days,
        start_time=now + timedelta(days=start_offset),
        end_time=now + timedelta(days=end_offset),
        is_active=is_active,
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


# =====================================================================
# GET /coupons
# =====================================================================

class TestListCoupons:
    def test_list_only_active_in_window_with_stock(self, client):
        _seed_coupon(client._sesh, name="可用券")
        _seed_coupon(client._sesh, name="停用券", is_active=False)
        _seed_coupon(client._sesh, name="未开始", start_offset=+1, end_offset=+30)
        _seed_coupon(client._sesh, name="已结束", start_offset=-30, end_offset=-1)
        _seed_coupon(client._sesh, name="无库存", total_stock=0)
        token = _login(client, "cpn-list")
        r = client.get(BASE, headers=_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        names = [i["name"] for i in body["data"]["items"]]
        assert "可用券" in names
        assert "停用券" not in names
        assert "未开始" not in names
        assert "已结束" not in names
        assert "无库存" not in names

    def test_list_pagination(self, client):
        """多券分页: 默认 page=1/page_size=20; total 正确; 上限 le=100。"""
        for i in range(25):
            _seed_coupon(client._sesh, name=f"分页券{i}")
        token = _login(client, "cpn-page")
        r = client.get(BASE, headers=_headers(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total"] == 25
        assert len(data["items"]) == 20
        r2 = client.get(f"{BASE}?page=2", headers=_headers(token))
        data2 = r2.json()["data"]
        assert len(data2["items"]) == 5
        assert data2["total"] == 25
        # page_size 上限
        assert client.get(
            f"{BASE}?page_size=101", headers=_headers(token)
        ).status_code == 422
        # page_size 自定义
        r4 = client.get(f"{BASE}?page_size=5&page=2", headers=_headers(token))
        data4 = r4.json()["data"]
        assert data4["page_size"] == 5
        assert len(data4["items"]) == 5

    def test_list_anonymous_401(self, anon_client):
        assert anon_client.get(BASE).status_code == 401


# =====================================================================
# POST /coupons/claim
# =====================================================================

class TestClaim:
    def test_claim_ok(self, client):
        c = _seed_coupon(client._sesh, total_stock=10)
        token = _login(client, "cpn-claim-1")
        r = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                        headers=_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["coupon_id"] == c.id
        assert data["coupon_code"].startswith("CPN-")
        assert data["expires_at"]
        # 库存原子扣减
        client._sesh.refresh(c)
        assert c.remaining_stock == 9
        # CouponUsage 落库, 归属 end_user
        eu = _end_user(client, "cpn-claim-1")
        usage = (
            client._sesh.query(CouponUsage)
            .filter(CouponUsage.coupon_id == c.id)
            .one()
        )
        assert usage.coupon_code == data["coupon_code"]
        assert usage.status == CouponStatus.ACTIVE
        assert usage.user_id == eu.id

    def test_claim_not_found(self, client):
        token = _login(client, "cpn-claim-nf")
        r = client.post(f"{BASE}/claim", json={"coupon_id": 999999},
                        headers=_headers(token))
        assert r.status_code == 404
        assert r.json()["detail"] == "COUPON_NOT_FOUND"

    def test_claim_per_user_limit_409(self, client):
        c = _seed_coupon(client._sesh, total_stock=10, per_user_limit=1)
        token = _login(client, "cpn-limit")
        r1 = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                         headers=_headers(token))
        assert r1.status_code == 200
        r2 = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                         headers=_headers(token))
        assert r2.status_code == 409
        assert r2.json()["detail"] == "COUPON_LIMIT_REACHED"

    def test_claim_out_of_stock_409(self, client):
        c = _seed_coupon(client._sesh, total_stock=0)
        token = _login(client, "cpn-stock")
        r = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                        headers=_headers(token))
        assert r.status_code == 409
        assert r.json()["detail"] == "COUPON_OUT_OF_STOCK"

    def test_claim_inactive_409(self, client):
        c = _seed_coupon(client._sesh, is_active=False)
        token = _login(client, "cpn-inactive")
        r = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                        headers=_headers(token))
        assert r.status_code == 409
        assert r.json()["detail"] == "COUPON_NOT_AVAILABLE"

    def test_claim_anonymous_401(self, anon_client, client):
        c = _seed_coupon(client._sesh)
        r = anon_client.post(f"{BASE}/claim", json={"coupon_id": c.id})
        assert r.status_code == 401
