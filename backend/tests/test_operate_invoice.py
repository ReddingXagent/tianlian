"""
运营-发票管理 API 测试

覆盖 /api/v1/operate/invoices (ops_invoice.py):
- 发票抬头: 创建/列表/类型过滤/更新/删除
- 发票申请: 提交申请/列表/status 过滤/待审核子端点/详情
- 状态流转: PENDING -> REVIEWED(approved) -> ISSUED(issue) -> VOIDED(void)
- 驳回分支: PENDING -> REJECTED(approved=False)
- 状态守卫: 非法状态下 review/issue/void 返回 400
- 404: 不存在的发票
"""
from app.models.ops_settlement.invoice_title import InvoiceTitle, TitleType
from app.models.ops_settlement.ops_invoice import (
    OpsInvoice, OpsInvoiceStatus, OpsInvoiceType,
)


def _seed_titles(session):
    """2 个抬头: 1 个人 + 1 企业"""
    session.add_all([
        InvoiceTitle(
            user_id=101, title_type=TitleType.PERSONAL,
            title_name="张三", tax_id="123456789012345678",
            email="zs@example.com", is_default=True,
        ),
        InvoiceTitle(
            user_id=102, title_type=TitleType.ENTERPRISE,
            title_name="天链科技有限公司", tax_id="91110000MA00ABCD",
            register_address="北京市朝阳区", bank_name="工行", bank_account="6222000011112222",
        ),
    ])
    session.commit()


def _seed_invoices(session):
    """3 张不同状态发票: pending / reviewed / issued"""
    session.add_all([
        OpsInvoice(
            applicant_name="李四", applicant_phone="13800000001",
            apply_source="app", title_name="天链科技有限公司", tax_id="91110000MA00ABCD",
            amount="100.00", invoice_type=OpsInvoiceType.ELECTRONIC,
            status=OpsInvoiceStatus.PENDING,
        ),
        OpsInvoice(
            applicant_name="王五", applicant_phone="13800000002",
            apply_source="admin", title_name="张三",
            amount="256.80", invoice_type=OpsInvoiceType.ELECTRONIC,
            status=OpsInvoiceStatus.REVIEWED, reviewer_id=1,
        ),
        OpsInvoice(
            applicant_name="赵六", applicant_phone="13800000003",
            apply_source="admin", title_name="天链科技有限公司",
            amount="999.00", invoice_type=OpsInvoiceType.PAPER,
            status=OpsInvoiceStatus.ISSUED, reviewer_id=1, issued_by="admin",
            invoice_no="INV20260721001",
        ),
    ])
    session.commit()


class TestOperateInvoiceTitles:
    """发票抬头 CRUD"""

    def test_title_create_list_and_type_filter(self, client):
        """创建 2 个抬头 + 列表 + title_type 过滤命中"""
        _seed_titles(client._sesh)

        data = client.get("/api/v1/operate/invoices/titles").json()["data"]
        assert data["total"] == 2
        assert {t["title_name"] for t in data["items"]} == {"张三", "天链科技有限公司"}

        ent = client.get("/api/v1/operate/invoices/titles?title_type=enterprise").json()["data"]
        assert ent["total"] == 1
        assert ent["items"][0]["title_name"] == "天链科技有限公司"
        assert ent["items"][0]["title_type"] == "enterprise"

    def test_title_update_and_delete(self, client):
        """更新抬头字段 + 删除后数量减少"""
        _seed_titles(client._sesh)
        s = client._sesh
        target = s.query(InvoiceTitle).filter(InvoiceTitle.title_name == "张三").one()

        r = client.put(
            f"/api/v1/operate/invoices/titles/{target.id}",
            json={"title_name": "张三丰", "is_default": False},
        )
        assert r.status_code == 200
        assert r.json()["data"]["title_name"] == "张三丰"
        assert r.json()["data"]["is_default"] is False

        d = client.delete(f"/api/v1/operate/invoices/titles/{target.id}")
        assert d.status_code == 200
        assert client.get("/api/v1/operate/invoices/titles").json()["data"]["total"] == 1

    def test_title_update_404(self, client):
        """更新不存在的抬头 -> 404"""
        r = client.put("/api/v1/operate/invoices/titles/99999", json={"title_name": "x"})
        assert r.status_code == 404


class TestOperateInvoiceLifecycle:
    """发票申请 + 状态流转全链路"""

    def test_list_invoices_status_filter_and_pending(self, client):
        """列表 + status 过滤 + pending 子端点只返回待审核"""
        _seed_invoices(client._sesh)

        data = client.get("/api/v1/operate/invoices").json()["data"]
        assert data["total"] == 3

        pending = client.get("/api/v1/operate/invoices?status=pending").json()["data"]
        assert pending["total"] == 1
        assert pending["items"][0]["applicant_name"] == "李四"

        only_pending = client.get("/api/v1/operate/invoices/pending").json()["data"]
        assert only_pending["total"] == 1
        assert only_pending["items"][0]["status"] == "pending"

    def test_full_approve_flow(self, client):
        """完整通过流: 申请(PENDING) -> 审核(REVIEWED) -> 开具(ISSUED)"""
        r = client.post("/api/v1/operate/invoices", json={
            "applicant_name": "钱七", "applicant_phone": "13900000000",
            "apply_source": "app", "title_name": "天链科技有限公司",
            "tax_id": "91110000MA00ABCD", "amount": "88.88",
            "invoice_type": "electronic",
        })
        assert r.status_code == 200
        inv_id = r.json()["data"]["id"]
        assert r.json()["data"]["status"] == "pending"

        # 审核通过 -> reviewed
        rev = client.put(f"/api/v1/operate/invoices/{inv_id}/review",
                         json={"approved": True, "reviewer_id": 1, "remark": "ok"})
        assert rev.status_code == 200
        assert rev.json()["data"]["status"] == "reviewed"

        # 开具 -> issued, 落地发票号
        iss = client.put(f"/api/v1/operate/invoices/{inv_id}/issue",
                         json={"invoice_no": "INV001", "invoice_code": "CODE001",
                               "pdf_url": "https://example.com/x.pdf", "issued_by": "admin"})
        assert iss.status_code == 200
        body = iss.json()["data"]
        assert body["status"] == "issued"
        assert body["invoice_no"] == "INV001"

        # 详情回读校验
        detail = client.get(f"/api/v1/operate/invoices/{inv_id}").json()["data"]
        assert detail["amount"] == 88.88
        assert detail["status"] == "issued"

    def test_reject_and_void_flows(self, client):
        """驳回分支 + 红冲分支: 各走一张已 seed 的发票"""
        s = client._sesh
        _seed_invoices(s)

        pending = s.query(OpsInvoice).filter(OpsInvoice.status == OpsInvoiceStatus.PENDING).one()
        rej = client.put(f"/api/v1/operate/invoices/{pending.id}/review",
                         json={"approved": False, "remark": "金额不符"})
        assert rej.status_code == 200
        assert rej.json()["data"]["status"] == "rejected"

        issued = s.query(OpsInvoice).filter(OpsInvoice.status == OpsInvoiceStatus.ISSUED).one()
        void = client.put(f"/api/v1/operate/invoices/{issued.id}/void",
                          json={"reason": "开票有误"})
        assert void.status_code == 200
        assert void.json()["data"]["status"] == "voided"
        assert void.json()["data"]["void_reason"] == "开票有误"

    def test_state_guards_return_400(self, client):
        """状态守卫: PENDING 不能直接 issue/void; REVIEWED 不能再 review"""
        r = client.post("/api/v1/operate/invoices", json={
            "title_name": "张三", "amount": "10.00",
        })
        inv_id = r.json()["data"]["id"]

        # PENDING 直接开票 -> 400
        assert client.put(f"/api/v1/operate/invoices/{inv_id}/issue",
                          json={"invoice_no": "X"}).status_code == 400
        # PENDING 直接红冲 -> 400
        assert client.put(f"/api/v1/operate/invoices/{inv_id}/void",
                          json={"reason": "x"}).status_code == 400

        # 推进到 REVIEWED 后再 review -> 400 (只有 PENDING 可审核)
        client.put(f"/api/v1/operate/invoices/{inv_id}/review", json={"approved": True})
        second = client.put(f"/api/v1/operate/invoices/{inv_id}/review", json={"approved": True})
        assert second.status_code == 400

    def test_missing_invoice_404(self, client):
        """不存在 -> review/issue/void/detail 均 404"""
        for path in ["review", "issue", "void"]:
            r = client.put(f"/api/v1/operate/invoices/99999/{path}", json={})
            assert r.status_code == 404
        assert client.get("/api/v1/operate/invoices/99999").status_code == 404
