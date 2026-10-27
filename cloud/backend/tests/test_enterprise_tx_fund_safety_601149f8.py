"""
企业交易资金安全测试 - 卡 601149f8 (P1 资金安全)

缺陷1 POST /api/v1/enterprises/{id}/transactions:
- 负数/零金额 → 400 且余额不变(consume 负数 = 凭空造钱, recharge 负数 = 抽干余额)
- consume 透支防线: new_balance < -(credit_limit) → 400
  (语义对齐 enterprise_balance_service.check_balance_available)
- 正常路径不回归: 合法 recharge/consume/refund 仍成功且 balance_after 正确

缺陷2 PUT /api/v1/operate/recharge/{id}/approve:
- 已 APPROVED 的申请再次 approve → 400(状态机兜底; PG 下行锁防并发双审批,
  SQLite no-op, 由该校验兜底)
"""
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient


# ========== Fixtures ==========

_counter = [0]


def _unique_code(prefix: str = "ENT_FS") -> str:
    _counter[0] += 1
    return f"{prefix}{_counter[0]}"


@pytest.fixture
def client(test_db):
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: test_db["session"]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _create_enterprise(test_db, balance=Decimal("10000.00"), credit_limit=Decimal("0.00")):
    from app.models.enterprise import Enterprise
    db = test_db["session"]
    ent = Enterprise(
        name="资金安全测试企业", code=_unique_code(),
        balance=balance, credit_limit=credit_limit,
    )
    db.add(ent)
    db.commit()
    db.refresh(ent)
    return ent


def _auth_headers(client):
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


def _post_tx(client, headers, enterprise_id, payload):
    return client.post(
        f"/api/v1/enterprises/{enterprise_id}/transactions",
        json=payload,
        headers=headers,
    )


def _db_balance(test_db, enterprise_id):
    from app.models.enterprise import Enterprise
    db = test_db["session"]
    db.expire_all()
    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    return Decimal(str(ent.balance))


# ========== 缺陷1: 金额校验 + 透支防线 ==========

class TestNegativeAmountGuard:
    """负数/零金额被拒且余额不变。

    343baf02f/716bd8614 后负数金额由 Pydantic 前置拦截(Literal type + amount ge=0)→422;
    零金额通过 ge=0, 由端点 amount<=0 校验→400。
    """

    @pytest.mark.parametrize("tx_type", ["consume", "recharge", "refund"])
    @pytest.mark.parametrize("amount", [-500, -0.01])
    def test_negative_amount_rejected_422(self, client, test_db, tx_type, amount):
        ent = _create_enterprise(test_db)
        headers = _auth_headers(client)
        resp = _post_tx(client, headers, ent.id, {"type": tx_type, "amount": amount})
        assert resp.status_code == 422
        # 余额不变(未被凭空增减)
        assert _db_balance(test_db, ent.id) == Decimal("10000.00")

    @pytest.mark.parametrize("tx_type", ["consume", "recharge", "refund"])
    def test_zero_amount_rejected_400(self, client, test_db, tx_type):
        ent = _create_enterprise(test_db)
        headers = _auth_headers(client)
        resp = _post_tx(client, headers, ent.id, {"type": tx_type, "amount": 0})
        assert resp.status_code == 400
        assert _db_balance(test_db, ent.id) == Decimal("10000.00")

    def test_consume_negative_was_money_minting(self, client, test_db):
        """原缺陷复现口径: consume -500 旧代码算出 10500(凭空+500), 修复后 422(Pydantic前置)"""
        ent = _create_enterprise(test_db)
        headers = _auth_headers(client)
        resp = _post_tx(client, headers, ent.id, {"type": "consume", "amount": -500})
        assert resp.status_code == 422
        assert _db_balance(test_db, ent.id) == Decimal("10000.00")


class TestOverdraftGuard:
    """consume 透支防线: new_balance >= -(credit_limit)"""

    def test_consume_beyond_credit_limit_rejected(self, client, test_db):
        """balance=0, credit_limit=100, consume 200 → new=-200 < -100 → 400"""
        ent = _create_enterprise(test_db, balance=Decimal("0.00"), credit_limit=Decimal("100.00"))
        headers = _auth_headers(client)
        resp = _post_tx(client, headers, ent.id, {"type": "consume", "amount": 200})
        assert resp.status_code == 400
        assert _db_balance(test_db, ent.id) == Decimal("0.00")

    def test_consume_within_credit_limit_allowed(self, client, test_db):
        """balance=0, credit_limit=100, consume 100 → new=-100 == -credit_limit, 放行"""
        ent = _create_enterprise(test_db, balance=Decimal("0.00"), credit_limit=Decimal("100.00"))
        headers = _auth_headers(client)
        resp = _post_tx(client, headers, ent.id, {"type": "consume", "amount": 100})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["balance_after"] == -100.0
        assert _db_balance(test_db, ent.id) == Decimal("-100.00")

    def test_consume_overdraw_no_credit_limit_rejected(self, client, test_db):
        """credit_limit=0(默认): 余额打负即拒"""
        ent = _create_enterprise(test_db, balance=Decimal("10.00"), credit_limit=Decimal("0.00"))
        headers = _auth_headers(client)
        resp = _post_tx(client, headers, ent.id, {"type": "consume", "amount": 11})
        assert resp.status_code == 400
        assert _db_balance(test_db, ent.id) == Decimal("10.00")


class TestHappyPathNoRegression:
    """正常路径不回归"""

    def test_recharge_consume_refund_still_work(self, client, test_db):
        ent = _create_enterprise(test_db)
        headers = _auth_headers(client)

        r = _post_tx(client, headers, ent.id, {"type": "recharge", "amount": 1000})
        assert r.status_code == 200
        assert r.json()["data"]["balance_after"] == 11000.0

        c = _post_tx(client, headers, ent.id, {"type": "consume", "amount": 200})
        assert c.status_code == 200
        assert c.json()["data"]["balance_after"] == 10800.0

        f = _post_tx(client, headers, ent.id, {"type": "refund", "amount": 50})
        assert f.status_code == 200
        assert f.json()["data"]["balance_after"] == 10850.0

        assert _db_balance(test_db, ent.id) == Decimal("10850.00")


# ========== 缺陷2: 充值审批 TOCTOU ==========

class TestRechargeApproveDoubleApproval:
    """已 APPROVED 的申请再次 approve → 400(状态机兜底)"""

    def test_reapprove_approved_application_rejected(self, client, test_db):
        from app.models.enterprise import Enterprise, EnterpriseStatus
        from app.models.enterprise_recharge import RechargeApplication, RechargeStatus
        from datetime import datetime, timezone

        db = test_db["session"]
        ent = Enterprise(
            name="充值审批测试企业", code=_unique_code("ENT_RC"),
            balance=Decimal("1000.00"), status=EnterpriseStatus.ACTIVE,
        )
        db.add(ent)
        db.commit()

        app_row = RechargeApplication(
            enterprise_id=ent.id, amount=Decimal("500.00"),
            status=RechargeStatus.PENDING, applicant="admin",
            created_at=datetime.now(timezone.utc),
        )
        db.add(app_row)
        db.commit()
        db.refresh(app_row)

        headers = _auth_headers(client)
        first = client.put(
            f"/api/v1/operate/recharge/{app_row.id}/approve",
            json={"reason": "首次审批"}, headers=headers,
        )
        assert first.status_code == 200

        # 并发双审批的 SQLite 兜底路径: 第二次 approve 同一申请 → 400, 不重复入账
        second = client.put(
            f"/api/v1/operate/recharge/{app_row.id}/approve",
            json={"reason": "重复审批"}, headers=headers,
        )
        assert second.status_code == 400

        # 余额只入账一次
        db.expire_all()
        db.refresh(ent)
        assert Decimal(str(ent.balance)) == Decimal("1500.00")
