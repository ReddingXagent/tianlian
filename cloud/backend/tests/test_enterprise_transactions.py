"""
企业资金池交易 API 测试 - Phase43 车队管理

覆盖:
- GET  /api/v1/enterprises/{enterprise_id}/transactions —— 列表 + 分页
- POST /api/v1/enterprises/{enterprise_id}/transactions —— 充值/消费/退款(联动企业余额)
- 参数校验(422) / 错误处理(404/400) / 余额累计联动
"""
import pytest
from fastapi.testclient import TestClient


# ========== Fixtures ==========

_counter = [0]


def _unique_code(prefix: str = "ENT_T") -> str:
    _counter[0] += 1
    return f"{prefix}{_counter[0]}"


def _create_enterprise(test_db, name="测试车队企业", balance=10000.00):
    from app.models.enterprise import Enterprise
    db = test_db["session"]
    ent = Enterprise(name=name, code=_unique_code(), balance=balance)
    db.add(ent)
    db.commit()
    db.refresh(ent)
    return ent


@pytest.fixture
def enterprise_id(test_db):
    return _create_enterprise(test_db).id


@pytest.fixture
def client(test_db):
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: test_db["session"]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client):
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers(client):
    return {"Authorization": f"Bearer {_login(client)}"}


def _create_tx(client, enterprise_id, **overrides):
    """创建交易辅助函数，默认成功"""
    payload = {"type": "recharge", "amount": 100.00}
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/enterprises/{enterprise_id}/transactions",
        json=payload,
        headers=_auth_headers(client),
    )
    assert resp.status_code == 200, f"创建交易失败: {resp.text}"
    return resp.json()["data"]


# ========== 列表 + 分页 ==========

class TestTransactionList:
    """交易列表与分页测试"""

    def test_list_empty(self, client, enterprise_id):
        """空列表"""
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/transactions",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_with_data(self, client, enterprise_id):
        """有数据列表 + 字段完整"""
        _create_tx(client, enterprise_id, type="recharge", amount=500, remark="首次充值")
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/transactions",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        item = data["items"][0]
        assert item["type"] == "recharge"
        assert item["amount"] == 500.0
        assert item["balance_after"] == 10500.0  # 10000 + 500
        assert item["remark"] == "首次充值"
        assert item["enterprise_id"] == enterprise_id
        for key in ("id", "vehicle_id", "order_id", "created_at"):
            assert key in item

    def test_list_pagination(self, client, enterprise_id):
        """分页：创建 5 条，page_size=2"""
        for i in range(5):
            _create_tx(client, enterprise_id, type="recharge", amount=10)
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/transactions?page=1&page_size=2",
            headers=_auth_headers(client),
        )
        data = resp.json()["data"]
        assert data["total"] == 5
        assert len(data["items"]) == 2
        # 按 id 降序
        ids = [t["id"] for t in data["items"]]
        assert ids == sorted(ids, reverse=True)

    def test_list_invalid_page(self, client, enterprise_id):
        """page < 1 -> 422"""
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/transactions?page=0",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_list_enterprise_not_found(self, client):
        """企业不存在 -> 404"""
        resp = client.get(
            "/api/v1/enterprises/99999/transactions",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404


# ========== 创建交易 ==========

class TestTransactionCreate:
    """创建交易(充值/消费/退款) + 余额联动测试"""

    def test_create_recharge(self, client, enterprise_id):
        """充值：余额增加"""
        data = _create_tx(client, enterprise_id, type="recharge", amount=1000)
        assert data["type"] == "recharge"
        assert data["amount"] == 1000.0
        assert data["balance_after"] == 11000.0  # 10000 + 1000

    def test_create_consume(self, client, enterprise_id):
        """消费：余额减少"""
        data = _create_tx(client, enterprise_id, type="consume", amount=200)
        assert data["type"] == "consume"
        assert data["amount"] == 200.0
        assert data["balance_after"] == 9800.0  # 10000 - 200

    def test_create_refund(self, client, enterprise_id):
        """退款：余额增加"""
        data = _create_tx(client, enterprise_id, type="refund", amount=50)
        assert data["type"] == "refund"
        assert data["amount"] == 50.0
        assert data["balance_after"] == 10050.0  # 10000 + 50

    def test_create_invalid_type(self, client, enterprise_id):
        """无效交易类型 -> 422 (Literal 前置, 卡 6031add1)"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/transactions",
            json={"type": "invalid_type", "amount": 100},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_create_enterprise_not_found(self, client):
        """企业不存在 -> 404"""
        resp = client.post(
            "/api/v1/enterprises/99999/transactions",
            json={"type": "recharge", "amount": 100},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404

    def test_create_missing_required_field(self, client, enterprise_id):
        """缺少必填字段 amount -> 422"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/transactions",
            json={"type": "recharge"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_create_balance_cascades(self, client, test_db, enterprise_id):
        """连续多笔交易：balance_after 逐步联动，且企业余额同步更新"""
        # 初始 balance=10000
        r = _create_tx(client, enterprise_id, type="recharge", amount=1000)
        assert r["balance_after"] == 11000.0
        c = _create_tx(client, enterprise_id, type="consume", amount=200)
        assert c["balance_after"] == 10800.0
        f = _create_tx(client, enterprise_id, type="refund", amount=50)
        assert f["balance_after"] == 10850.0

        # 直接查 DB 验证企业余额已联动
        from app.models.enterprise import Enterprise
        db = test_db["session"]
        ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
        assert float(ent.balance) == 10850.0

        # 列表里应有3条
        lst = client.get(
            f"/api/v1/enterprises/{enterprise_id}/transactions",
            headers=_auth_headers(client),
        )
        assert lst.json()["data"]["total"] == 3
