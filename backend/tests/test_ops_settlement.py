"""
运营结算对账 + 发票管理 后端测试

覆盖:
- 模型: DailySettlement, PaymentReconciliation, InterconnectSettlement, InvoiceTitle, OpsInvoice
- API: 日结/对账/互联互通/发票抬头/发票全生命周期
- 业务逻辑: 状态流转, 分成计算, 审核流转
"""
import bcrypt
import pytest
from datetime import date, datetime
from decimal import Decimal


def _h(token):
    """Bearer 认证头（与 test_team_scoping.py 同构）。"""
    return {"Authorization": f"Bearer {token}"}


class TestDailySettlement:
    """日结汇总模型 + API"""

    def test_create_daily_settlement(self, client):
        """创建日结记录"""
        resp = client.post("/api/v1/operate/settlement/daily/generate", json={
            "settlement_date": "2026-07-20",
            "station_id": 1,
            "total_orders": 50,
            "total_charge_fee": 1200.50,
            "total_service_fee": 300.00,
            "total_amount": 1500.50,
            "total_paid": 1500.50,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["settlement_date"] == "2026-07-20"
        assert data["total_orders"] == 50
        assert data["status"] == "pending"

    def test_list_daily_settlements(self, client):
        """列表查询"""
        client.post("/api/v1/operate/settlement/daily/generate", json={
            "settlement_date": "2026-07-18", "total_orders": 10, "total_amount": 500,
        })
        client.post("/api/v1/operate/settlement/daily/generate", json={
            "settlement_date": "2026-07-19", "total_orders": 20, "total_amount": 800,
        })

        resp = client.get("/api/v1/operate/settlement/daily")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 2

    def test_confirm_daily_settlement(self, client):
        """确认日结"""
        r = client.post("/api/v1/operate/settlement/daily/generate", json={
            "settlement_date": "2026-07-21", "total_orders": 5,
        })
        sid = r.json()["data"]["id"]

        resp = client.put(f"/api/v1/operate/settlement/daily/{sid}/confirm")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "confirmed"
        assert resp.json()["data"]["confirmed_at"] is not None

    def test_duplicate_date_rejected(self, client):
        """同日期重复生成"""
        client.post("/api/v1/operate/settlement/daily/generate", json={
            "settlement_date": "2026-07-22", "total_orders": 1,
        })
        resp = client.post("/api/v1/operate/settlement/daily/generate", json={
            "settlement_date": "2026-07-22", "total_orders": 2,
        })
        assert resp.status_code == 400

    def test_get_daily_detail(self, client):
        """获取详情"""
        r = client.post("/api/v1/operate/settlement/daily/generate", json={
            "settlement_date": "2026-07-23", "total_orders": 3, "remark": "test",
        })
        sid = r.json()["data"]["id"]
        resp = client.get(f"/api/v1/operate/settlement/daily/{sid}")
        assert resp.status_code == 200
        assert resp.json()["data"]["remark"] == "test"


class TestPaymentReconciliation:
    """支付对账模型 + API"""

    def test_create_reconciliation(self, client):
        resp = client.post("/api/v1/operate/settlement/reconciliation", json={
            "settlement_date": "2026-07-20",
            "payment_channel": "im_b",
            "platform_orders_count": 100,
            "platform_amount": 5000.00,
            "payment_orders_count": 99,
            "payment_amount": 4950.00,
            "difference_count": 1,
            "difference_amount": 50.00,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["payment_channel"] == "im_b"
        assert data["status"] == "pending"
        assert data["difference_count"] == 1

    def test_list_reconciliations(self, client):
        client.post("/api/v1/operate/settlement/reconciliation", json={
            "settlement_date": "2026-07-19",
            "payment_channel": "alipay",
            "platform_amount": 1000, "payment_amount": 1000,
        })
        resp = client.get("/api/v1/operate/settlement/reconciliation?payment_channel=alipay")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    def test_reconcile_record(self, client):
        r = client.post("/api/v1/operate/settlement/reconciliation", json={
            "settlement_date": "2026-07-18",
            "payment_channel": "unionpay",
            "platform_amount": 2000, "payment_amount": 2000,
        })
        rid = r.json()["data"]["id"]
        resp = client.put(f"/api/v1/operate/settlement/reconciliation/{rid}/reconcile", json={
            "operator": "财务张三"
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "reconciled"
        assert resp.json()["data"]["reconciled_by"] == "财务张三"


class TestInterconnectSettlement:
    """互联互通结算模型 + API"""

    def test_create_interconnect(self, client):
        resp = client.post("/api/v1/operate/settlement/interconnect", json={
            "platform_id": "eidp_platform_001",
            "platform_name": "e充宝",
            "start_date": "2026-07-01",
            "end_date": "2026-07-15",
            "total_orders": 200,
            "total_amount": 8000.00,
            "revenue_share_ratio": "0.7000",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["our_revenue"] == 5600.0
        assert data["partner_revenue"] == 2400.0
        assert data["status"] == "pending"

    def test_list_interconnect(self, client):
        client.post("/api/v1/operate/settlement/interconnect", json={
            "platform_id": "test_plat",
            "start_date": "2026-07-01",
            "end_date": "2026-07-07",
            "total_amount": 1000,
            "revenue_share_ratio": "0.5000",
        })
        resp = client.get("/api/v1/operate/settlement/interconnect")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    def test_settle_interconnect(self, client):
        r = client.post("/api/v1/operate/settlement/interconnect", json={
            "platform_id": "plat_settle",
            "start_date": "2026-07-10",
            "end_date": "2026-07-20",
            "total_amount": 5000,
            "revenue_share_ratio": "0.6000",
        })
        sid = r.json()["data"]["id"]
        resp = client.put(f"/api/v1/operate/settlement/interconnect/{sid}/settle", json={
            "operator": "运营李四"
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "settled"
        assert resp.json()["data"]["settled_by"] == "运营李四"


class TestInvoiceTitle:
    """发票抬头模型 + API"""

    def test_create_title(self, client):
        resp = client.post("/api/v1/operate/invoices/titles", json={
            "title_type": "enterprise",
            "title_name": "北京新能源科技有限公司",
            "tax_id": "91110100MA01ABCDEF",
            "register_address": "北京市海淀区中关村大街1号",
            "register_phone": "010-12345678",
            "bank_name": "中国银行北京分行",
            "bank_account": "1234567890123456",
            "email": "finance@example.com",
            "is_default": True,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title_name"] == "北京新能源科技有限公司"
        assert data["title_type"] == "enterprise"
        assert data["is_default"] is True

    def test_list_titles(self, client):
        client.post("/api/v1/operate/invoices/titles", json={
            "title_type": "personal",
            "title_name": "张三",
        })
        resp = client.get("/api/v1/operate/invoices/titles?title_type=personal")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    def test_update_title(self, client):
        r = client.post("/api/v1/operate/invoices/titles", json={
            "title_name": "旧名称", "title_type": "personal",
        })
        tid = r.json()["data"]["id"]
        resp = client.put(f"/api/v1/operate/invoices/titles/{tid}", json={
            "title_name": "新名称",
            "is_default": True,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["title_name"] == "新名称"

    def test_delete_title(self, client):
        r = client.post("/api/v1/operate/invoices/titles", json={
            "title_name": "要删除的抬头",
        })
        tid = r.json()["data"]["id"]
        resp = client.delete(f"/api/v1/operate/invoices/titles/{tid}")
        assert resp.status_code == 200
        # 确认已删除
        resp2 = client.get(f"/api/v1/operate/invoices/titles")
        items = resp2.json()["data"]["items"]
        assert all(i["id"] != tid for i in items)


class TestOpsInvoice:
    """发票申请/审核/开具/红冲 全生命周期"""

    def test_full_invoice_lifecycle(self, client):
        """完整流转: 申请 → 审核 → 开具 → 红冲"""
        # 1. 创建申请
        r = client.post("/api/v1/operate/invoices", json={
            "applicant_name": "客户王五",
            "title_name": "北京新能源科技有限公司",
            "tax_id": "91110100MA01ABCDEF",
            "amount": 3000.00,
            "invoice_type": "electronic",
        })
        assert r.status_code == 200
        inv_id = r.json()["data"]["id"]
        assert r.json()["data"]["status"] == "pending"

        # 2. 审核
        r2 = client.put(f"/api/v1/operate/invoices/{inv_id}/review", json={
            "approved": True, "reviewer_id": 1, "remark": "审核通过",
        })
        assert r2.status_code == 200
        assert r2.json()["data"]["status"] == "reviewed"

        # 3. 开具
        r3 = client.put(f"/api/v1/operate/invoices/{inv_id}/issue", json={
            "invoice_no": "INV20260720001",
            "invoice_code": "CODE001",
            "pdf_url": "https://example.com/inv/001.pdf",
        })
        assert r3.status_code == 200
        assert r3.json()["data"]["status"] == "issued"
        assert r3.json()["data"]["invoice_no"] == "INV20260720001"

        # 4. 红冲
        r4 = client.put(f"/api/v1/operate/invoices/{inv_id}/void", json={
            "reason": "客户要求重开",
        })
        assert r4.status_code == 200
        assert r4.json()["data"]["status"] == "voided"

    def test_pending_invoices_list(self, client):
        """待审核列表"""
        client.post("/api/v1/operate/invoices", json={
            "title_name": "测试公司", "amount": 500,
        })
        resp = client.get("/api/v1/operate/invoices/pending")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1
        for item in resp.json()["data"]["items"]:
            assert item["status"] == "pending"

    def test_reject_invoice(self, client):
        """驳回"""
        r = client.post("/api/v1/operate/invoices", json={
            "title_name": "被驳回公司", "amount": 100,
        })
        inv_id = r.json()["data"]["id"]
        resp = client.put(f"/api/v1/operate/invoices/{inv_id}/review", json={
            "approved": False, "remark": "金额不符",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "rejected"

    def test_all_invoices_list(self, client):
        """全部发票列表"""
        client.post("/api/v1/operate/invoices", json={
            "title_name": "列表测试", "amount": 200,
        })
        resp = client.get("/api/v1/operate/invoices")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    def test_invoice_detail(self, client):
        """发票详情"""
        r = client.post("/api/v1/operate/invoices", json={
            "title_name": "详情测试", "amount": 800,
        })
        inv_id = r.json()["data"]["id"]
        resp = client.get(f"/api/v1/operate/invoices/{inv_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == inv_id

    def test_issue_without_review_fails(self, client):
        """未审核直接开票应失败"""
        r = client.post("/api/v1/operate/invoices", json={
            "title_name": "跳过审核", "amount": 300,
        })
        inv_id = r.json()["data"]["id"]
        resp = client.put(f"/api/v1/operate/invoices/{inv_id}/issue", json={
            "invoice_no": "TEST",
        })
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════
# 任务卡 abf3d756：授权缺口（对账/互联互通列表补 require_platform_admin）
# + 分账比例边界校验 + 负金额 schema 约束。
# 对账/互联互通为平台级财务记录（无 team 维度），读写对称 → 仅 admin 可见。
# 日结/企业结算有 team 维度 → 走 team scoping（既有 ab5c5f17 模式，回归锁定）。
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture(scope="function")
def ops_team_setup(client):
    """两 team + 两 engineer + 两 station(各属一 team) + 两 enterprise(各属一 team)
    + 各站一日结 + 各企业一账单，供 ops_settlement 授权/team scoping 回归用。

    返回:
        teams:       {a, b}   Team ORM
        stations:    {a, b}   Station ORM（team_id 已绑定）
        enterprises: {a, b}   Enterprise ORM（owner_team_id 已绑定）
        daily:       {a, b}   DailySettlement ORM（分别挂 a/b 站）
        bills:       {a, b}   FleetSettlementBill ORM（分别属 a/b 企业）
        tokens:      {a, b, admin}
    """
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.enterprise import Enterprise
    from app.models.ops_settlement import DailySettlement, SettlementStatus
    from app.models.settlement import FleetSettlementBill

    s = client._sesh
    ta = Team(name="OS团队A", code="OSA1")
    tb = Team(name="OS团队B", code="OSB1")
    s.add_all([ta, tb]); s.commit(); s.refresh(ta); s.refresh(tb)

    pwd = "os123456"
    ua = User(username="os_eng_a", real_name="A工程师", role=UserRole.ENGINEER,
              team_id=ta.id, status="active",
              password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode())
    ub = User(username="os_eng_b", real_name="B工程师", role=UserRole.ENGINEER,
              team_id=tb.id, status="active",
              password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode())
    s.add_all([ua, ub]); s.commit()

    sa = Station(name="OS-A站", code="OSSA1", team_id=ta.id, status=StationStatus.NORMAL)
    sb = Station(name="OS-B站", code="OSSB1", team_id=tb.id, status=StationStatus.NORMAL)
    s.add_all([sa, sb]); s.commit(); s.refresh(sa); s.refresh(sb)

    ea = Enterprise(name="OS企业A", code="OSEAQ1", owner_team_id=ta.id)
    eb = Enterprise(name="OS企业B", code="OSEBQ1", owner_team_id=tb.id)
    s.add_all([ea, eb]); s.commit(); s.refresh(ea); s.refresh(eb)

    dsa = DailySettlement(settlement_date=date(2026, 7, 1), station_id=sa.id,
                          status=SettlementStatus.PENDING)
    dsb = DailySettlement(settlement_date=date(2026, 7, 1), station_id=sb.id,
                          status=SettlementStatus.PENDING)
    s.add_all([dsa, dsb]); s.commit(); s.refresh(dsa); s.refresh(dsb)

    ba = FleetSettlementBill(bill_no="OS-BILL-A-1", enterprise_id=ea.id, bill_period="2026-07")
    bb = FleetSettlementBill(bill_no="OS-BILL-B-1", enterprise_id=eb.id, bill_period="2026-07")
    s.add_all([ba, bb]); s.commit(); s.refresh(ba); s.refresh(bb)

    def _tok(username, password):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        j = r.json()
        return j.get("data", {}).get("token") or j.get("token")

    return {
        "teams": {"a": ta, "b": tb},
        "stations": {"a": sa, "b": sb},
        "enterprises": {"a": ea, "b": eb},
        "daily": {"a": dsa, "b": dsb},
        "bills": {"a": ba, "b": bb},
        "tokens": {
            "a": _tok("os_eng_a", pwd),
            "b": _tok("os_eng_b", pwd),
            "admin": _tok("admin", "admin123"),
        },
    }


class TestOpsSettlementAuthorization:
    """对账/互联互通列表为平台级财务记录（无 team 维度），读写对称 → 仅 admin 可见。

    同文件写端点已全部 require_platform_admin；补齐读端点，杜绝普通 team 用户
    读取无权写入的敏感财务数据。任务卡 abf3d756。
    """

    def test_reconciliation_list_requires_admin(self, client, ops_team_setup):
        """team 级 engineer 读对账列表 → 403。"""
        r = client.get("/api/v1/operate/settlement/reconciliation",
                       headers=_h(ops_team_setup["tokens"]["a"]))
        assert r.status_code == 403

    def test_interconnect_list_requires_admin(self, client, ops_team_setup):
        """team 级 engineer 读互联互通结算列表 → 403。"""
        r = client.get("/api/v1/operate/settlement/interconnect",
                       headers=_h(ops_team_setup["tokens"]["a"]))
        assert r.status_code == 403

    def test_reconciliation_list_admin_ok(self, client, ops_team_setup):
        """admin 读对账列表 → 200。"""
        r = client.get("/api/v1/operate/settlement/reconciliation",
                       headers=_h(ops_team_setup["tokens"]["admin"]))
        assert r.status_code == 200

    def test_interconnect_list_admin_ok(self, client, ops_team_setup):
        """admin 读互联互通结算列表 → 200。"""
        r = client.get("/api/v1/operate/settlement/interconnect",
                       headers=_h(ops_team_setup["tokens"]["admin"]))
        assert r.status_code == 200


class TestOpsSettlementTeamScoping:
    """日结（经 station→team）/ 企业结算（经 enterprise→owner_team）有 team 维度，
    非 admin 仅返回本 team；admin 全见。既有 ab5c5f17 模式，回归锁定。"""

    def test_daily_settlement_scoped_by_team(self, client, ops_team_setup):
        """A 只见本 team 站点日结，不见 B 站。"""
        t = ops_team_setup
        r = client.get("/api/v1/operate/settlement/daily", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["daily"]["a"].id in ids
        assert t["daily"]["b"].id not in ids

    def test_daily_settlement_admin_sees_all(self, client, ops_team_setup):
        """admin 跨 team 全见。"""
        t = ops_team_setup
        r = client.get("/api/v1/operate/settlement/daily", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["daily"]["a"].id in ids
        assert t["daily"]["b"].id in ids

    def test_enterprise_settlement_scoped_by_team(self, client, ops_team_setup):
        """A 的企业结算列表只见本 team 企业账单（1 条），不见 B 企业的。"""
        t = ops_team_setup
        r = client.get("/api/v1/operate/settlement/enterprise", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["bills"]["a"].id in ids
        assert t["bills"]["b"].id not in ids


class TestOpsSettlementBoundary:
    """分账比例边界校验（资金安全）+ 负金额 schema 约束。任务卡 abf3d756。

    ratio 链式比较 Decimal("0") <= ratio <= Decimal("1")：负数/>1 → 400；
    NaN 参与比较恒 False → not False → 一并 raise → 400。0/1 边界放行。
    """

    def test_interconnect_ratio_negative_rejected(self, client):
        """ratio=-0.1 → 400。"""
        r = client.post("/api/v1/operate/settlement/interconnect", json={
            "platform_id": "p_neg", "start_date": "2026-07-01", "end_date": "2026-07-07",
            "total_amount": 1000, "revenue_share_ratio": "-0.1",
        })
        assert r.status_code == 400

    def test_interconnect_ratio_over_one_rejected(self, client):
        """ratio=1.5 → 400。"""
        r = client.post("/api/v1/operate/settlement/interconnect", json={
            "platform_id": "p_over", "start_date": "2026-07-01", "end_date": "2026-07-07",
            "total_amount": 1000, "revenue_share_ratio": "1.5",
        })
        assert r.status_code == 400

    def test_interconnect_ratio_boundary_ok(self, client):
        """ratio=0/1 边界值放行 → 200。"""
        for ratio in ("0", "1"):
            r = client.post("/api/v1/operate/settlement/interconnect", json={
                "platform_id": f"p_ok_{ratio}", "start_date": "2026-07-01",
                "end_date": "2026-07-07", "total_amount": 1000,
                "revenue_share_ratio": ratio,
            })
            assert r.status_code == 200, f"ratio={ratio} 边界应放行"

    def test_daily_negative_amount_rejected(self, client):
        """日结 total_amount 负值 → 422（Field ge=0 schema 约束）。"""
        r = client.post("/api/v1/operate/settlement/daily/generate", json={
            "settlement_date": "2026-07-30", "total_amount": -100,
        })
        assert r.status_code == 422
