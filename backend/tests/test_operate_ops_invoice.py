"""
运营-发票管理 API 测试 (SPEC §2.5)

覆盖 /api/v1/operate/invoices:
- 发票抬头 CRUD + 404
- 发票生命周期: 申请(pending) → 审核(reviewed/rejected) → 开具(issued) → 红冲(voided)
- 状态机校验: 非预期状态操作 → 400
- 详情/列表/待审核筛选
- 匿名拒绝 (401)
"""
from datetime import datetime, timezone
from decimal import Decimal

# 卡526e7c57: asyncio_mode=auto 下, pytest-asyncio 在前置 session 的 teardown
# 会 set_event_loop(None) 清空主线程 loop。本文件若在前置文件之后才首次触发
# `from app.api.v1 import api_router` (经 _session_app fixture), 其导入链
# app/api/v1/workorders/helpers.py → app.ws.routes → app.ws.__init__ →
# ws_manager = WebSocketManager() → asyncio.Lock() 在 py3.9 构造期即调用
# get_event_loop(), 此时主线程 loop 已被清空 → RuntimeError: There is no
# current event loop。此处于 collection 阶段(loop policy 仍为默认, get_event_loop
# 会自动 new_event_loop)预导入 app.ws 包, 触发 ws_manager 单例在 loop 存活期
# 构造并缓存进 sys.modules, 后续 fixture setup 命中模块缓存不再二次构造该 Lock。
import app.ws  # noqa: F401

from app.models.ops_settlement import (
    InvoiceTitle,
    TitleType,
    OpsInvoice,
    OpsInvoiceStatus,
    OpsInvoiceType,
)


# ─── seed helpers ───

def _seed_title(session, **overrides):
    t = InvoiceTitle(
        user_id=overrides.get("user_id"),
        title_type=overrides.get("title_type", TitleType.PERSONAL),
        title_name=overrides.get("title_name", "测试个人抬头"),
        tax_id=overrides.get("tax_id"),
        is_default=overrides.get("is_default", False),
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


def _seed_invoice(session, status=OpsInvoiceStatus.PENDING, **overrides):
    inv = OpsInvoice(
        applicant_name=overrides.get("applicant_name", "张三"),
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


# ==================== 发票抬头 CRUD ====================

class TestOpsInvoiceTitle:
    """发票抬头 CRUD"""

    def test_create_title(self, client):
        resp = client.post("/api/v1/operate/invoices/titles", json={
            "title_name": "深圳某科技公司",
            "title_type": "enterprise",
            "tax_id": "91440300MA5XXX",
            "bank_name": "招商银行",
            "bank_account": "622500xxxx",
            "is_default": True,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] > 0
        assert data["title_name"] == "深圳某科技公司"
        assert data["title_type"] == "enterprise"
        assert data["tax_id"] == "91440300MA5XXX"
        assert data["is_default"] is True

    def test_list_titles(self, client):
        _seed_title(client._sesh, title_name="抬头A")
        _seed_title(client._sesh, title_name="抬头B", title_type=TitleType.ENTERPRISE)
        resp = client.get("/api/v1/operate/invoices/titles")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 2
        names = {t["title_name"] for t in data["items"]}
        assert {"抬头A", "抬头B"} <= names

    def test_list_titles_filter_by_type(self, client):
        _seed_title(client._sesh, title_name="个人X", title_type=TitleType.PERSONAL)
        _seed_title(client._sesh, title_name="企业Y", title_type=TitleType.ENTERPRISE)
        resp = client.get("/api/v1/operate/invoices/titles?title_type=enterprise")
        items = resp.json()["data"]["items"]
        assert items and all(i["title_type"] == "enterprise" for i in items)

    def test_update_title(self, client):
        t = _seed_title(client._sesh, title_name="旧名")
        resp = client.put(f"/api/v1/operate/invoices/titles/{t.id}", json={
            "title_name": "新名", "tax_id": "T999",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title_name"] == "新名"
        assert data["tax_id"] == "T999"

    def test_update_title_not_found(self, client):
        resp = client.put("/api/v1/operate/invoices/titles/99999", json={"title_name": "x"})
        assert resp.status_code == 404

    def test_delete_title(self, client):
        t = _seed_title(client._sesh, title_name="待删抬头")
        resp = client.delete(f"/api/v1/operate/invoices/titles/{t.id}")
        assert resp.status_code == 200
        items = client.get("/api/v1/operate/invoices/titles").json()["data"]["items"]
        assert all(i["id"] != t.id for i in items)

    def test_delete_title_not_found(self, client):
        assert client.delete("/api/v1/operate/invoices/titles/99999").status_code == 404


# ==================== 发票生命周期 (状态机) ====================

class TestOpsInvoiceLifecycle:
    """发票申请 → 审核 → 开具 → 红冲"""

    def test_create_invoice(self, client):
        resp = client.post("/api/v1/operate/invoices", json={
            "applicant_name": "李四",
            "applicant_phone": "13800000000",
            "title_name": "李四抬头",
            "amount": 256.50,
            "invoice_type": "electronic",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title_name"] == "李四抬头"
        assert data["amount"] == 256.5
        assert data["status"] == "pending"

    def test_full_approved_lifecycle(self, client):
        """pending → reviewed → issued → voided"""
        inv = _seed_invoice(client._sesh, amount=Decimal("88.00"))

        r = client.put(f"/api/v1/operate/invoices/{inv.id}/review",
                       json={"approved": True, "remark": "审核通过"})
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "reviewed"
        assert r.json()["data"]["review_remark"] == "审核通过"

        r = client.put(f"/api/v1/operate/invoices/{inv.id}/issue", json={
            "invoice_no": "INV001", "invoice_code": "CODE1",
            "pdf_url": "https://x/a.pdf",
        })
        assert r.status_code == 200
        issued = r.json()["data"]
        assert issued["status"] == "issued"
        assert issued["invoice_no"] == "INV001"
        assert issued["pdf_url"] == "https://x/a.pdf"

        r = client.put(f"/api/v1/operate/invoices/{inv.id}/void", json={"reason": "红冲作废"})
        assert r.status_code == 200
        voided = r.json()["data"]
        assert voided["status"] == "voided"
        assert voided["void_reason"] == "红冲作废"

    def test_review_rejected(self, client):
        inv = _seed_invoice(client._sesh)
        r = client.put(f"/api/v1/operate/invoices/{inv.id}/review",
                       json={"approved": False, "remark": "信息不全"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "rejected"
        assert data["review_remark"] == "信息不全"

    def test_review_wrong_status_400(self, client):
        """已审核的发票不能再次审核 → 400"""
        inv = _seed_invoice(client._sesh, status=OpsInvoiceStatus.REVIEWED)
        r = client.put(f"/api/v1/operate/invoices/{inv.id}/review", json={"approved": True})
        assert r.status_code == 400

    def test_issue_wrong_status_400(self, client):
        """未审核(pending)的发票不能开具 → 400"""
        inv = _seed_invoice(client._sesh, status=OpsInvoiceStatus.PENDING)
        r = client.put(f"/api/v1/operate/invoices/{inv.id}/issue", json={"invoice_no": "X"})
        assert r.status_code == 400

    def test_void_wrong_status_400(self, client):
        """未开具(reviewed)的发票不能红冲 → 400"""
        inv = _seed_invoice(client._sesh, status=OpsInvoiceStatus.REVIEWED)
        r = client.put(f"/api/v1/operate/invoices/{inv.id}/void", json={"reason": "x"})
        assert r.status_code == 400


# ==================== 发票查询/详情/筛选 ====================

class TestOpsInvoiceQuery:
    """发票查询"""

    def test_get_invoice_detail(self, client):
        inv = _seed_invoice(client._sesh, title_name="详情抬头")
        r = client.get(f"/api/v1/operate/invoices/{inv.id}")
        assert r.status_code == 200
        assert r.json()["data"]["title_name"] == "详情抬头"

    def test_get_invoice_not_found(self, client):
        assert client.get("/api/v1/operate/invoices/99999").status_code == 404

    def test_review_invoice_not_found(self, client):
        r = client.put("/api/v1/operate/invoices/99999/review", json={"approved": True})
        assert r.status_code == 404

    def test_list_invoices_status_filter(self, client):
        _seed_invoice(client._sesh, status=OpsInvoiceStatus.PENDING, title_name="待审")
        _seed_invoice(client._sesh, status=OpsInvoiceStatus.ISSUED, title_name="已开")
        r = client.get("/api/v1/operate/invoices?status=pending")
        items = r.json()["data"]["items"]
        assert items and all(i["status"] == "pending" for i in items)

    def test_list_pending_only(self, client):
        _seed_invoice(client._sesh, status=OpsInvoiceStatus.PENDING, title_name="P1")
        _seed_invoice(client._sesh, status=OpsInvoiceStatus.ISSUED)
        r = client.get("/api/v1/operate/invoices/pending")
        items = r.json()["data"]["items"]
        assert items and all(i["status"] == "pending" for i in items)


# ==================== 鉴权 ====================

class TestOpsInvoiceAuth:
    """匿名拒绝"""

    def test_anon_list_titles_denied(self, anon_client):
        assert anon_client.get("/api/v1/operate/invoices/titles").status_code == 401

    def test_anon_create_invoice_denied(self, anon_client):
        r = anon_client.post("/api/v1/operate/invoices", json={
            "title_name": "x", "amount": 1,
        })
        assert r.status_code == 401
