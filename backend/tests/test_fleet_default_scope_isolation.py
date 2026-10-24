"""
fleet list 端点缺省 team 兜底过滤测试 — 任务卡 45166947

验证 enterprise_id 查询参数缺省时, 团队级用户(OPERATOR)不得全表裸查:
- 团队 A 用户不传 enterprise_id → 只见本团队数据(跨团队数据被过滤);
- admin(平台级)缺省 → 全量可见。

覆盖端点:
- GET /api/v1/fleet/drivers
- GET /api/v1/fleet/settlement/bills
- GET /api/v1/fleet/settlement/invoices
- GET /api/v1/fleet/funds
- GET /api/v1/fleet/carbon/certificates

范式参考 test_fleet_team_isolation.py(团队用户造+登录)。
"""
import bcrypt
import pytest

from app.models.fleet_carbon_certificate import (
    FleetCarbonCertificate, CertificateStatus,
)
from app.models.settlement import (
    FleetSettlementBill, BillStatus, FleetInvoiceRequest, InvoiceStatus, InvoiceType,
)


@pytest.fixture
def scope_team_pair(client):
    """两团队 + 两 OPERATOR 用户 + 两企业(分属两团队) + 各端点种子数据 + token。"""
    from app.models.user import User, UserRole, Team
    from app.models.enterprise import Enterprise, EnterpriseStatus
    from app.models.fleet_driver import (
        FleetDriver, FleetDriverAccount, DriverStatus, LicenseType, AccountStatus,
    )
    from app.models.fund_pool import (
        FundPool, FundAccountStatus, FundPoolTransaction,
        FundTransactionType, FundTransactionStatus,
    )
    s = client._sesh

    out = {"teams": {}, "users": {}, "enterprises": {}, "tokens": {}}
    pwd = "scope123456"
    for key, tname, tcode, uname in [
        ("a", "兜底团队A", "DFTA", "scope_op_a"),
        ("b", "兜底团队B", "DFTB", "scope_op_b"),
    ]:
        t = Team(name=tname, code=tcode)
        s.add(t)
        s.commit()
        s.refresh(t)
        out["teams"][key] = t

        u = User(
            username=uname, real_name=f"{key}运营", role=UserRole.OPERATOR,
            team_id=t.id, status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )
        s.add(u)
        s.commit()
        out["users"][key] = u

        ent = Enterprise(name=f"兜底企业{key}", code=f"DFTENT{key}",
                         status=EnterpriseStatus.ACTIVE, owner_team_id=t.id)
        s.add(ent)
        s.commit()
        s.refresh(ent)
        out["enterprises"][key] = ent

    ent_a, ent_b = out["enterprises"]["a"], out["enterprises"]["b"]

    # 种子: 各企业各造 1 条司机/账单/发票/资金账户/碳核证
    for i, ent in enumerate([ent_a, ent_b]):
        drv = FleetDriver(
            enterprise_id=ent.id, name=f"兜底司机{i}", phone=f"1390000000{i}",
            license_no=f"DFT_LIC_{i}", license_type=LicenseType.C1,
            status=DriverStatus.ACTIVE,
        )
        s.add(drv)
        s.commit()
        s.refresh(drv)
        s.add(FleetDriverAccount(driver_id=drv.id, status=AccountStatus.ACTIVE))

        bill = FleetSettlementBill(
            bill_no=f"DFTBILL-{i}", enterprise_id=ent.id, bill_period="2026-08",
            status=BillStatus.PENDING,
        )
        s.add(bill)
        s.add(FleetInvoiceRequest(
            enterprise_id=ent.id, bill_id=None, title=f"兜底发票{i}", amount=100,
            invoice_type=InvoiceType.GENERAL, status=InvoiceStatus.PENDING,
        ))

        fund = FundPool(
            enterprise_id=ent.id, enterprise_name=ent.name, account_name=f"兜底账户{i}",
            status=FundAccountStatus.ACTIVE,
        )
        s.add(fund)
        s.commit()
        s.refresh(fund)
        s.add(FundPoolTransaction(
            fund_pool_id=fund.id, transaction_type=FundTransactionType.RECHARGE,
            amount=100, balance_before=0, balance_after=100,
            status=FundTransactionStatus.SUCCESS,
        ))

        s.add(FleetCarbonCertificate(
            enterprise_id=ent.id, summary_id=10000 + i, certificate_no=f"DFTCC-{i}",
            status=CertificateStatus.PENDING,
        ))
    s.commit()

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    out["tokens"] = {"a": _tok("scope_op_a"), "b": _tok("scope_op_b")}
    return out


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _admin_h(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _list(client, headers, url):
    r = client.get(url, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    return body["items"] if isinstance(body, dict) and "items" in body else body


# ==================== drivers ====================

class TestListDriversDefaultScope:
    def test_team_a_only_sees_own(self, client, scope_team_pair):
        items = _list(client, _h(scope_team_pair["tokens"]["a"]), "/api/v1/fleet/drivers")
        ent_a = scope_team_pair["enterprises"]["a"].id
        assert len(items) == 1 and items[0]["enterprise_id"] == ent_a
        assert all(d["enterprise_id"] == ent_a for d in items)

    def test_admin_sees_all(self, client, scope_team_pair):
        items = _list(client, _admin_h(client), "/api/v1/fleet/drivers")
        assert len(items) >= 2


# ==================== settlement bills ====================

class TestListBillsDefaultScope:
    def test_team_a_only_sees_own(self, client, scope_team_pair):
        items = _list(client, _h(scope_team_pair["tokens"]["a"]),
                      "/api/v1/fleet/settlement/bills")
        ent_a = scope_team_pair["enterprises"]["a"].id
        assert len(items) == 1 and items[0]["enterprise_id"] == ent_a

    def test_admin_sees_all(self, client, scope_team_pair):
        items = _list(client, _admin_h(client), "/api/v1/fleet/settlement/bills")
        assert len(items) >= 2


# ==================== settlement invoices ====================

class TestListInvoicesDefaultScope:
    def test_team_a_only_sees_own(self, client, scope_team_pair):
        items = _list(client, _h(scope_team_pair["tokens"]["a"]),
                      "/api/v1/fleet/settlement/invoices")
        ent_a = scope_team_pair["enterprises"]["a"].id
        assert len(items) == 1 and items[0]["enterprise_id"] == ent_a

    def test_admin_sees_all(self, client, scope_team_pair):
        items = _list(client, _admin_h(client), "/api/v1/fleet/settlement/invoices")
        assert len(items) >= 2


# ==================== funds ====================

class TestListFundsDefaultScope:
    def test_team_a_only_sees_own(self, client, scope_team_pair):
        items = _list(client, _h(scope_team_pair["tokens"]["a"]), "/api/v1/fleet/funds")
        ent_a = scope_team_pair["enterprises"]["a"].id
        assert len(items) == 1 and items[0]["enterprise_id"] == ent_a

    def test_admin_sees_all(self, client, scope_team_pair):
        items = _list(client, _admin_h(client), "/api/v1/fleet/funds")
        assert len(items) >= 2


# ==================== carbon certificates ====================

class TestListCertificatesDefaultScope:
    def test_team_a_only_sees_own(self, client, scope_team_pair):
        items = _list(client, _h(scope_team_pair["tokens"]["a"]),
                      "/api/v1/fleet/carbon/certificates")
        ent_a = scope_team_pair["enterprises"]["a"].id
        assert len(items) == 1 and items[0]["enterprise_id"] == ent_a

    def test_admin_sees_all(self, client, scope_team_pair):
        items = _list(client, _admin_h(client), "/api/v1/fleet/carbon/certificates")
        assert len(items) >= 2
