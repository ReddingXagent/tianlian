"""
运营-发票管理 API 边界测试 (SPEC §2.5)

与 tests/test_operate_ops_invoice.py 互补：后者覆盖基础 CRUD/生命周期/匿名401，
本文件聚焦**金额校验(Decimal 精度/负数/超额)**、**完整状态机非法流转矩阵**、
**非平台管理员 403**、**抬头 team scoping** 四类边界。

覆盖端点前缀: /api/v1/operate/invoices
"""
import bcrypt
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.models.ops_settlement import (
    InvoiceTitle,
    TitleType,
    OpsInvoice,
    OpsInvoiceStatus,
    OpsInvoiceType,
)
from app.models.user import User, UserRole, Team


# ─── seed helpers ───

def _seed_title(session, **overrides):
    t = InvoiceTitle(
        user_id=overrides.get("user_id"),
        title_type=overrides.get("title_type", TitleType.PERSONAL),
        title_name=overrides.get("title_name", "测试抬头"),
        tax_id=overrides.get("tax_id"),
        is_default=overrides.get("is_default", False),
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


def _seed_invoice(session, status=OpsInvoiceStatus.PENDING, **overrides):
    inv = OpsInvoice(
        applicant_name=overrides.get("applicant_name", "申请人"),
        title_name=overrides.get("title_name", "测试抬头"),
        amount=overrides.get("amount", Decimal("100.00")),
        invoice_type=overrides.get("invoice_type", OpsInvoiceType.ELECTRONIC),
        status=status,
        apply_time=datetime.now(timezone.utc),
    )
    session.add(inv)
    session.commit()
    session.refresh(inv)
    return inv


def _add_user(session, username, role, team_id=None, password="pw123456"):
    """创建并提交一个用户，返回 ORM（供 team scoping / 403 测试复用）。"""
    u = User(
        username=username,
        real_name=username,
        role=role,
        team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    return r.json().get("data", {}).get("token") or r.json().get("token")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ==================== 金额校验 (Decimal 精度 / 负数 / 超额) ====================

class TestOpsInvoiceAmountValidation:
    """开票金额校验。

    列定义为 Numeric(12,2)（整数≤10位，精确到分）。SQLite 的 NUMERIC 亲和性
    不强制精度/范围 —— 负数、超额、过多小数位均被静默存入；PostgreSQL 生产环境
    对超额会抛 numeric field overflow (500)。路由层 schema 必须在入库前拦断，
    与列语义对齐：gt=0（必须为正）+ max_digits=12 + decimal_places=2。
    """

    BASE = {"title_name": "抬头", "applicant_name": "张三"}

    @pytest.mark.parametrize("amount", [-100, -0.01, 0])
    def test_non_positive_amount_rejected(self, client, amount):
        """负数 / 零金额 → 422（财务输入校验缺陷）"""
        r = client.post("/api/v1/operate/invoices", json={**self.BASE, "amount": amount})
        assert r.status_code == 422

    def test_negative_amount_as_string_rejected(self, client):
        """字符串形式负数同样 → 422"""
        r = client.post("/api/v1/operate/invoices", json={**self.BASE, "amount": "-50"})
        assert r.status_code == 422

    @pytest.mark.parametrize("amount", [10000000000.00, "99999999999.99", "1e20"])
    def test_exceed_numeric_precision_rejected(self, client, amount):
        """超额（整数部分超过 10 位 / 总位数 > 12）→ 422，防 PG 生产 numeric overflow"""
        r = client.post("/api/v1/operate/invoices", json={**self.BASE, "amount": amount})
        assert r.status_code == 422

    @pytest.mark.parametrize("amount", [100.999, "0.001", "99.999"])
    def test_too_many_decimal_places_rejected(self, client, amount):
        """超过 2 位小数 → 422（精确到分，避免精度损失/库间不一致）"""
        r = client.post("/api/v1/operate/invoices", json={**self.BASE, "amount": amount})
        assert r.status_code == 422

    def test_invalid_amount_type_rejected(self, client):
        """非数字 amount → 422"""
        r = client.post("/api/v1/operate/invoices", json={**self.BASE, "amount": "abc"})
        assert r.status_code == 422

    def test_boundary_max_amount_accepted(self, client):
        """列精度上界 9999999999.99（整数10位+小数2位=12位）→ 200"""
        r = client.post("/api/v1/operate/invoices",
                        json={**self.BASE, "amount": "9999999999.99"})
        assert r.status_code == 200
        assert r.json()["data"]["amount"] == 9999999999.99

    def test_minimal_valid_amount_accepted(self, client):
        """最小有效金额 0.01 → 200"""
        r = client.post("/api/v1/operate/invoices", json={**self.BASE, "amount": "0.01"})
        assert r.status_code == 200
        assert r.json()["data"]["amount"] == 0.01

    def test_amount_decimal_roundtrip(self, client):
        """金额 Decimal 往返：写入 256.50 → 读回 float 256.5"""
        r = client.post("/api/v1/operate/invoices",
                        json={**self.BASE, "amount": "256.50"})
        assert r.status_code == 200
        inv_id = r.json()["data"]["id"]
        detail = client.get(f"/api/v1/operate/invoices/{inv_id}").json()["data"]
        assert detail["amount"] == 256.5

    def test_missing_amount_rejected(self, client):
        """缺省 amount → 422（必填字段）"""
        r = client.post("/api/v1/operate/invoices",
                        json={"title_name": "抬头", "applicant_name": "张三"})
        assert r.status_code == 422


# ==================== 状态机非法流转矩阵 ====================

class TestOpsInvoiceStateMachine:
    """完整状态机契约：每个操作的合法前置状态唯一，非法流转一律 400 且状态不变。

    合法流转:
      PENDING  --review(approved)-->  REVIEWED
      PENDING  --review(rejected)-->  REJECTED  (终态)
      REVIEWED --issue-->            ISSUED
      ISSUED   --void-->             VOIDED     (终态)
    """

    PAYLOADS = {
        "review": {"approved": True, "remark": "通过"},
        "issue": {"invoice_no": "INV-X", "invoice_code": "C"},
        "void": {"reason": "红冲"},
    }

    @pytest.mark.parametrize("initial, action", [
        # REJECTED 为终态，三种操作均非法
        (OpsInvoiceStatus.REJECTED, "review"),
        (OpsInvoiceStatus.REJECTED, "issue"),
        (OpsInvoiceStatus.REJECTED, "void"),
        # ISSUED 后：不能重复开具 / 不能回退审核
        (OpsInvoiceStatus.ISSUED, "issue"),
        (OpsInvoiceStatus.ISSUED, "review"),
        # VOIDED 为终态，三种操作均非法
        (OpsInvoiceStatus.VOIDED, "review"),
        (OpsInvoiceStatus.VOIDED, "issue"),
        (OpsInvoiceStatus.VOIDED, "void"),
        # PENDING：未审核不能直接开具 / 红冲
        (OpsInvoiceStatus.PENDING, "void"),
        # REVIEWED：已审核不能再审核 / 未开具不能红冲
        (OpsInvoiceStatus.REVIEWED, "review"),
    ])
    def test_illegal_transition_blocked(self, client, initial, action):
        inv = _seed_invoice(client._sesh, status=initial)
        r = client.put(f"/api/v1/operate/invoices/{inv.id}/{action}",
                       json=self.PAYLOADS[action])
        assert r.status_code == 400, f"{initial.value}+{action} 应被拒绝, 实际 {r.status_code}: {r.text}"
        # 状态保持不变（非法操作不产生副作用）
        detail = client.get(f"/api/v1/operate/invoices/{inv.id}").json()["data"]
        assert detail["status"] == initial.value

    def test_voided_is_terminal_all_actions_blocked(self, client):
        """红冲后发票为终态：review/issue/void 全部 400"""
        inv = _seed_invoice(client._sesh, status=OpsInvoiceStatus.VOIDED)
        for action, payload in self.PAYLOADS.items():
            r = client.put(f"/api/v1/operate/invoices/{inv.id}/{action}", json=payload)
            assert r.status_code == 400, f"终态+{action} 应 400, 实际 {r.status_code}"

    def test_issue_then_reissue_blocked(self, client):
        """已开具发票不能重复开具 → 400，且发票号不变"""
        inv = _seed_invoice(client._sesh, status=OpsInvoiceStatus.ISSUED,
                            **{"amount": Decimal("88.00")})
        # 直接置入发票号（模拟已开具结果）
        client._sesh.query(OpsInvoice).filter(OpsInvoice.id == inv.id).update(
            {"invoice_no": "ORIG"})
        client._sesh.commit()
        r = client.put(f"/api/v1/operate/invoices/{inv.id}/issue",
                       json={"invoice_no": "NEW"})
        assert r.status_code == 400
        detail = client.get(f"/api/v1/operate/invoices/{inv.id}").json()["data"]
        assert detail["invoice_no"] == "ORIG"  # 未被覆盖


# ==================== 非平台管理员鉴权 (403) ====================

class TestOpsInvoicePlatformAdminOnly:
    """写端点 + 发票查询端点均 require_platform_admin；team 级角色 → 403。

    GET /invoices/titles 例外：仅需认证，按 team 过滤（见 TestOpsInvoiceTitleTeamScoping）。
    """

    @pytest.fixture
    def engineer_token(self, client):
        _add_user(client._sesh, "inv_eng", UserRole.ENGINEER)
        return _login_token(client, "inv_eng")

    def test_engineer_create_title_forbidden(self, client, engineer_token):
        r = client.post("/api/v1/operate/invoices/titles",
                        json={"title_name": "x"}, headers=_auth(engineer_token))
        assert r.status_code == 403

    def test_engineer_create_invoice_forbidden(self, client, engineer_token):
        r = client.post("/api/v1/operate/invoices",
                        json={"title_name": "x", "amount": "1"},
                        headers=_auth(engineer_token))
        assert r.status_code == 403

    def test_engineer_review_forbidden(self, client, engineer_token):
        inv = _seed_invoice(client._sesh)
        r = client.put(f"/api/v1/operate/invoices/{inv.id}/review",
                       json={"approved": True}, headers=_auth(engineer_token))
        assert r.status_code == 403

    def test_engineer_issue_forbidden(self, client, engineer_token):
        inv = _seed_invoice(client._sesh, status=OpsInvoiceStatus.REVIEWED)
        r = client.put(f"/api/v1/operate/invoices/{inv.id}/issue",
                       json={"invoice_no": "X"}, headers=_auth(engineer_token))
        assert r.status_code == 403

    def test_engineer_void_forbidden(self, client, engineer_token):
        inv = _seed_invoice(client._sesh, status=OpsInvoiceStatus.ISSUED)
        r = client.put(f"/api/v1/operate/invoices/{inv.id}/void",
                       json={"reason": "x"}, headers=_auth(engineer_token))
        assert r.status_code == 403

    def test_engineer_list_invoices_forbidden(self, client, engineer_token):
        """GET /invoices 同样平台级 → 403"""
        r = client.get("/api/v1/operate/invoices", headers=_auth(engineer_token))
        assert r.status_code == 403

    def test_engineer_list_pending_forbidden(self, client, engineer_token):
        r = client.get("/api/v1/operate/invoices/pending", headers=_auth(engineer_token))
        assert r.status_code == 403

    def test_engineer_get_detail_forbidden(self, client, engineer_token):
        inv = _seed_invoice(client._sesh)
        r = client.get(f"/api/v1/operate/invoices/{inv.id}", headers=_auth(engineer_token))
        assert r.status_code == 403


# ==================== 抬头 team scoping ====================

class TestOpsInvoiceTitleTeamScoping:
    """GET /invoices/titles：非 admin 仅返回本 team 用户的抬头（经 user→team）。

    归属经 InvoiceTitle.user_id → User.team_id 间接判定；user_id 为 NULL 的运营
    公用抬头经 inner join 对 team 级用户不可见。
    """

    @pytest.fixture
    def two_team_setup(self, client):
        s = client._sesh
        ta = Team(name="INV团队A", code="INVA1")
        tb = Team(name="INV团队B", code="INVB1")
        s.add_all([ta, tb]); s.commit(); s.refresh(ta); s.refresh(tb)

        ua = _add_user(s, "inv_u_a", UserRole.VIEWER, team_id=ta.id)
        ub = _add_user(s, "inv_u_b", UserRole.VIEWER, team_id=tb.id)

        # team A 工程师（查询人）
        eng_a = _add_user(s, "inv_eng_a", UserRole.ENGINEER, team_id=ta.id)

        ta_title = _seed_title(s, user_id=ua.id, title_name="A队抬头")
        tb_title = _seed_title(s, user_id=ub.id, title_name="B队抬头")
        # user_id=NULL 的运营公用抬头
        _seed_title(s, user_id=None, title_name="公用抬头")

        return {
            "teams": {"a": ta, "b": tb},
            "eng_a_token": _login_token(client, "inv_eng_a"),
        }

    def test_engineer_sees_only_own_team_titles(self, client, two_team_setup):
        """team A 工程师只看到本 team 用户的抬头"""
        r = client.get("/api/v1/operate/invoices/titles",
                       headers=_auth(two_team_setup["eng_a_token"]))
        assert r.status_code == 200
        names = {i["title_name"] for i in r.json()["data"]["items"]}
        assert "A队抬头" in names
        assert "B队抬头" not in names  # 跨 team 不可见
        assert "公用抬头" not in names  # user_id=NULL 经 inner join 不可见

    def test_admin_sees_all_titles(self, client, two_team_setup):
        """admin（client 默认头）跨 team 全可见，含公用抬头"""
        r = client.get("/api/v1/operate/invoices/titles")
        assert r.status_code == 200
        names = {i["title_name"] for i in r.json()["data"]["items"]}
        assert {"A队抬头", "B队抬头", "公用抬头"} <= names

    def test_engineer_cannot_create_title_under_other_team(self, client, two_team_setup):
        """team 级用户无权创建抬头（require_platform_admin）→ 403，
        不存在跨 team 越权写入的路径"""
        r = client.post("/api/v1/operate/invoices/titles",
                        json={"title_name": "x"},
                        headers=_auth(two_team_setup["eng_a_token"]))
        assert r.status_code == 403


# ==================== 抬头更新字段语义 ====================

class TestOpsInvoiceTitleUpdateSemantics:
    """更新抬头：model_dump(exclude_unset=True) 只改传入字段，其余保持原值。"""

    def test_update_partial_keeps_other_fields(self, client):
        t = _seed_title(client._sesh, title_name="原名", tax_id="T1",
                        title_type=TitleType.ENTERPRISE, is_default=True)
        # 仅改 title_name
        r = client.put(f"/api/v1/operate/invoices/titles/{t.id}",
                       json={"title_name": "新名"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["title_name"] == "新名"
        assert d["tax_id"] == "T1"          # 未传 → 保持
        assert d["title_type"] == "enterprise"
        assert d["is_default"] is True

    def test_update_title_type(self, client):
        t = _seed_title(client._sesh, title_type=TitleType.PERSONAL)
        r = client.put(f"/api/v1/operate/invoices/titles/{t.id}",
                       json={"title_type": "enterprise"})
        assert r.status_code == 200
        assert r.json()["data"]["title_type"] == "enterprise"

    def test_update_empty_body_noop(self, client):
        """空 body 不报错，字段全部保持"""
        t = _seed_title(client._sesh, title_name="保持名")
        r = client.put(f"/api/v1/operate/invoices/titles/{t.id}", json={})
        assert r.status_code == 200
        assert r.json()["data"]["title_name"] == "保持名"


# ==================== 红冲字段固化 ====================

class TestOpsInvoiceVoidFields:
    """红冲后详情含 void_reason / void_time，且原开票信息保留。"""

    def test_void_records_reason_and_time(self, client):
        inv = _seed_invoice(client._sesh, status=OpsInvoiceStatus.ISSUED,
                            **{"amount": Decimal("200.00")})
        # 补全开票信息（模拟已开具）
        client._sesh.query(OpsInvoice).filter(OpsInvoice.id == inv.id).update(
            {"invoice_no": "INV1", "issued_by": "开票员"})
        client._sesh.commit()

        r = client.put(f"/api/v1/operate/invoices/{inv.id}/void",
                       json={"reason": "客户退款"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] == "voided"
        assert d["void_reason"] == "客户退款"
        assert d["void_time"] is not None
        # 原开票信息保留（红冲不抹除开票记录）
        assert d["invoice_no"] == "INV1"
        assert d["issued_by"] == "开票员"

    def test_void_default_reason(self, client):
        """红冲未传 reason → 默认 "红冲作废" """
        inv = _seed_invoice(client._sesh, status=OpsInvoiceStatus.ISSUED)
        r = client.put(f"/api/v1/operate/invoices/{inv.id}/void", json={})
        assert r.status_code == 200
        assert r.json()["data"]["void_reason"] == "红冲作废"


# ==================== 列表分页 ====================

class TestOpsInvoicePagination:
    """发票列表分页参数。"""

    def test_list_invoices_pagination(self, client):
        for i in range(3):
            _seed_invoice(client._sesh, title_name=f"页发票{i}")
        r = client.get("/api/v1/operate/invoices?page=1&page_size=2")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] >= 3
        assert len(d["items"]) == 2
        assert d["page"] == 1
        assert d["page_size"] == 2

    def test_list_titles_pagination(self, client):
        for i in range(3):
            _seed_title(client._sesh, title_name=f"页抬头{i}")
        r = client.get("/api/v1/operate/invoices/titles?page_size=2")
        assert r.status_code == 200
        d = r.json()["data"]
        assert len(d["items"]) == 2
        assert d["page_size"] == 2
