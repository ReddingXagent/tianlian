"""卡 089b01b2 — C端积分 (GET /points).

端侧路径 (无 /business): GET /points 当前用户积分余额 + 最近记录。
鉴权: get_current_end_user; 运营 token / 匿名 → 401。
余额: 最新 PointsRecord.balance_after (无记录 → 0); 记录按时间倒序。
"""
import hashlib

import pytest

from app.models.end_user import EndUser
from app.models.points import PointsRecord, PointsRecordType

AUTH_URL = "/api/v1/business/auth/wx-login"
BASE = "/api/v1/points"


def _login(client, code):
    r = client.post(AUTH_URL, json={"code": code})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _end_user(client, code):
    openid = "mock_" + hashlib.sha1(code.encode()).hexdigest()[:16]
    return client._sesh.query(EndUser).filter(EndUser.wx_openid == openid).one()


def _seed_record(session, *, end_user_id, points, balance_after,
                 record_type=PointsRecordType.EARN, description="充电积分"):
    r = PointsRecord(
        user_id=end_user_id,
        record_type=record_type,
        points=points,
        balance_before=balance_after - points,
        balance_after=balance_after,
        description=description,
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


class TestPoints:
    def test_points_balance_and_records(self, client):
        token = _login(client, "pts-1")
        eu = _end_user(client, "pts-1")
        _seed_record(client._sesh, end_user_id=eu.id, points=100,
                     balance_after=100)
        _seed_record(client._sesh, end_user_id=eu.id, points=50,
                     balance_after=150)
        r = client.get(BASE, headers=_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["balance"] == 150
        assert len(data["records"]) == 2
        # 最近在前 (created_at 倒序)
        assert data["records"][0]["points"] == 50
        assert data["records"][1]["points"] == 100

    def test_points_pagination(self, client):
        """多记录分页: 默认 page=1/page_size=20; page_size 上限 100。"""
        token = _login(client, "pts-page")
        eu = _end_user(client, "pts-page")
        for i in range(1, 26):  # 25 条
            _seed_record(client._sesh, end_user_id=eu.id, points=1,
                         balance_after=i)
        r = client.get(BASE, headers=_headers(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total"] == 25
        assert len(data["records"]) == 20
        # 翻页
        r2 = client.get(f"{BASE}?page=2", headers=_headers(token))
        data2 = r2.json()["data"]
        assert len(data2["records"]) == 5
        assert data2["total"] == 25
        # page_size 上限 le=100
        r3 = client.get(f"{BASE}?page_size=101", headers=_headers(token))
        assert r3.status_code == 422
        # page_size 自定义生效
        r4 = client.get(f"{BASE}?page_size=5&page=2", headers=_headers(token))
        data4 = r4.json()["data"]
        assert data4["page_size"] == 5
        assert len(data4["records"]) == 5

    def test_points_isolated_between_users(self, client):
        """他人积分不可见 (契约 §8 隔离): 仅返回本人记录。"""
        a = _login(client, "pts-iso-a")
        b = _login(client, "pts-iso-b")
        eu_a = _end_user(client, "pts-iso-a")
        _seed_record(client._sesh, end_user_id=eu_a.id, points=200,
                     balance_after=200)
        # b 用户查 → 不含 a 的记录
        r = client.get(BASE, headers=_headers(b))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["balance"] == 0
        assert data["records"] == []

    def test_points_no_records_balance_zero(self, client):
        token = _login(client, "pts-empty")
        r = client.get(BASE, headers=_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["balance"] == 0
        assert body["data"]["records"] == []

    def test_points_anonymous_401(self, anon_client):
        assert anon_client.get(BASE).status_code == 401

    def test_points_operate_token_401(self, client):
        """运营 token 调 C端积分端点必须 401。"""
        r = client.post("/api/v1/auth/login",
                        data={"username": "admin", "password": "admin123"})
        admin_token = r.json()["data"]["token"]
        assert client.get(BASE, headers=_headers(admin_token)).status_code == 401
