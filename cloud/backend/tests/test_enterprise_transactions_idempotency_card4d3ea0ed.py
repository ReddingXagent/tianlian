"""
企业交易 order_id 幂等测试 - 卡 4d3ea0ed (资金安全)

覆盖:
- 同一 (enterprise_id, type, order_id) 重复 POST recharge/refund → 409, 只落一条流水, 余额只加一次
- order_id=NULL 不受幂等约束 (对齐 charging_order.transaction_id 的 NULL 语义)
- 同 order_id 不同 type / 不同 enterprise 互不冲突
"""
import pytest
from fastapi.testclient import TestClient


_counter = [0]


def _unique_code(prefix: str = "ENT_IDEM") -> str:
    _counter[0] += 1
    return f"{prefix}{_counter[0]}"


def _create_enterprise(test_db, balance=10000.00):
    from app.models.enterprise import Enterprise
    db = test_db["session"]
    ent = Enterprise(name="幂等测试企业", code=_unique_code(), balance=balance)
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


def _auth_headers(client):
    resp = client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


def _post_tx(client, enterprise_id, headers, **overrides):
    payload = {"type": "recharge", "amount": 100.00}
    payload.update(overrides)
    return client.post(
        f"/api/v1/enterprises/{enterprise_id}/transactions",
        json=payload,
        headers=headers,
    )


def _get_balance(test_db, enterprise_id):
    from app.models.enterprise import Enterprise
    db = test_db["session"]
    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    db.refresh(ent)
    return float(ent.balance)


class TestOrderIdIdempotency:
    """卡 4d3ea0ed: order_id 幂等去重"""

    def test_duplicate_recharge_same_order_id_rejected(self, client, test_db, enterprise_id):
        """同 order_id 重复 recharge: 第二次 409, 只落一条, 余额只加一次"""
        headers = _auth_headers(client)
        r1 = _post_tx(client, enterprise_id, headers, type="recharge", amount=500, order_id="ORD-IDEM-1")
        assert r1.status_code == 200
        r2 = _post_tx(client, enterprise_id, headers, type="recharge", amount=500, order_id="ORD-IDEM-1")
        assert r2.status_code == 409, f"重复 order_id 应被拒绝: {r2.status_code} {r2.text}"

        lst = client.get(
            f"/api/v1/enterprises/{enterprise_id}/transactions", headers=headers
        )
        assert lst.json()["data"]["total"] == 1
        assert _get_balance(test_db, enterprise_id) == 10500.0  # 10000 + 500 只加一次

    def test_duplicate_refund_same_order_id_rejected(self, client, test_db, enterprise_id):
        """同 order_id 重复 refund: 第二次 409, 余额只加一次"""
        headers = _auth_headers(client)
        r1 = _post_tx(client, enterprise_id, headers, type="refund", amount=200, order_id="ORD-IDEM-2")
        assert r1.status_code == 200
        r2 = _post_tx(client, enterprise_id, headers, type="refund", amount=200, order_id="ORD-IDEM-2")
        assert r2.status_code == 409

        lst = client.get(
            f"/api/v1/enterprises/{enterprise_id}/transactions", headers=headers
        )
        assert lst.json()["data"]["total"] == 1
        assert _get_balance(test_db, enterprise_id) == 10200.0

    def test_null_order_id_not_constrained(self, client, test_db, enterprise_id):
        """order_id=NULL 重复提交不受幂等约束(可落多条)"""
        headers = _auth_headers(client)
        r1 = _post_tx(client, enterprise_id, headers, type="recharge", amount=100)
        r2 = _post_tx(client, enterprise_id, headers, type="recharge", amount=100)
        assert r1.status_code == 200
        assert r2.status_code == 200, f"NULL order_id 不应被拒: {r2.status_code} {r2.text}"
        assert _get_balance(test_db, enterprise_id) == 10200.0

    def test_same_order_id_different_type_or_enterprise_ok(self, client, test_db, enterprise_id):
        """同 order_id 不同 type / 不同 enterprise 不冲突"""
        headers = _auth_headers(client)
        other = _create_enterprise(test_db)
        r1 = _post_tx(client, enterprise_id, headers, type="recharge", amount=100, order_id="ORD-IDEM-3")
        r2 = _post_tx(client, enterprise_id, headers, type="refund", amount=50, order_id="ORD-IDEM-3")
        r3 = _post_tx(client, other.id, headers, type="recharge", amount=30, order_id="ORD-IDEM-3")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 200
