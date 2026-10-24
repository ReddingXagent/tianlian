"""
GatewaySN 持久化测试 (卡 3681a8c6)

POST /api/v1/gateways/sn/generate 端点内 db.add 后未 commit，
get_db() 关闭 session 时隐式回滚 → 跨请求读不到行。
此处用独立新连接（模拟真实跨请求）断言持久化，避免 dependency_overrides
共用同一 session 造成假绿。
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


@pytest.fixture
def auth_token(test_db):
    response = client.post("/api/v1/auth/login", data={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.json()
    return data.get("token") or data.get("data", {}).get("token")


def _fresh_rows(test_db, batch_no):
    """独立新连接查询 —— 模拟真实跨请求读，绕开测试 session 缓存。"""
    from app.models.gateway import GatewaySN
    session = test_db["SessionLocal"]()
    try:
        return session.query(GatewaySN).filter(GatewaySN.batch_no == batch_no).all()
    finally:
        session.close()


class TestGatewaySNPersistence:
    def test_generate_persists_across_requests(self, test_db, auth_token):
        """generate 返回 200 后，独立连接按 batch_no 查询必须恰好 3 行"""
        batch_no = f"PERSIST-{uuid.uuid4().hex[:8]}"
        resp = client.post("/api/v1/gateways/sn/generate", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"count": 3, "model": "TL-GW-100", "batch_no": batch_no})
        assert resp.status_code == 200
        items = resp.json().get("data", {}).get("items", [])
        assert len(items) == 3

        rows = _fresh_rows(test_db, batch_no)
        assert len(rows) == 3, (
            f"SN 行未持久化: 独立连接仅查到 {len(rows)} 行 (期望3), "
            "generate 端点缺 commit"
        )

    def test_generated_sn_visible_in_list_and_writable(self, test_db, auth_token):
        """生成的 SN 在新请求列表中可见，且 write 不得因 SN 不存在而 404"""
        batch_no = f"PERSIST-{uuid.uuid4().hex[:8]}"
        resp = client.post("/api/v1/gateways/sn/generate", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"count": 1, "model": "TL-GW-100", "batch_no": batch_no})
        assert resp.status_code == 200
        items = resp.json().get("data", {}).get("items", [])
        assert len(items) == 1
        sn_id = items[0]["id"]

        # 新请求列表可见
        list_resp = client.get(f"/api/v1/gateways/sn?batch_no={batch_no}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        listed = list_data.get("data", {}).get("items", list_data.get("data", []))
        assert len(listed) == 1, f"列表新请求只看到 {len(listed)} 行, SN 未持久化"

        # write: gateway_id 不存在允许 400/404（网关维度），但 detail 不得是"SN码不存在"
        write_resp = client.post(f"/api/v1/gateways/sn/{sn_id}/write", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"gateway_id": 999999})
        assert write_resp.status_code in (200, 400, 404), write_resp.text
        assert "SN码不存在" not in write_resp.text, "write 因 SN 不存在而 404 — 持久化丢失"
