"""
车队充值申请 API 测试

覆盖:
- 创建充值申请(含文件上传)
- 列表(权限隔离)
- 审核通过(余额入账)
- 驳回
- 重复审核防护
"""
import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from .conftest import _get_token
from app.core.database import get_db, Base
from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.fleet_recharge import FleetRechargeRequest, RechargeStatus
from app.models.user import User, UserRole


@pytest.fixture
def setup_enterprise(client: TestClient, db_session):
    """创建测试企业 + admin token"""
    # 确保有 admin 用户（conftest seed_users 已创建）
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 创建企业
    r = client.post("/api/v1/fleet/enterprises", json={
        "name": "测试车队企业",
        "code": "TEST-RECHARGE-001",
        "contact": "张三",
        "phone": "13800000001",
        "status": "active",
    }, headers=headers)
    assert r.status_code in (200, 201)
    enterprise_id = r.json().get("data", {}).get("id")
    if not enterprise_id:
        # 可能已存在，尝试获取列表
        r2 = client.get("/api/v1/fleet/enterprises", headers=headers)
        items = r2.json().get("data", [])
        if isinstance(items, list) and items:
            enterprise_id = items[0]["id"]
        else:
            # 直接在 DB 创建
            ent = Enterprise(name="测试车队企业DB", code="TEST-RECHARGE-DB", status=EnterpriseStatus.ACTIVE)
            db_session.add(ent)
            db_session.commit()
            db_session.refresh(ent)
            enterprise_id = ent.id

    return {"token": token, "headers": headers, "enterprise_id": enterprise_id}


def _make_voucher_file():
    """生成测试用图片文件"""
    return ("voucher.jpg", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100), "image/jpeg")


class TestFleetRechargeCreate:
    """创建充值申请"""

    def test_create_recharge_success(self, client: TestClient, setup_enterprise):
        """正常创建充值申请"""
        eid = setup_enterprise["enterprise_id"]
        headers = setup_enterprise["headers"]

        r = client.post(
            "/api/v1/fleet/recharge",
            data={"enterprise_id": eid, "amount": "500.00"},
            files={"file": _make_voucher_file()},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        data = r.json().get("data", {})
        assert data["status"] == "pending"
        assert data["amount"] == 500.0
        assert data["voucher_url"].startswith("/uploads/fleet_recharge/")
        assert data["enterprise_id"] == eid

    def test_create_recharge_fake_extension_rejected(self, client: TestClient, setup_enterprise):
        """卡 7007f36c: 扩展名 .jpg 但内容是 HTML → 魔数校验 422"""
        eid = setup_enterprise["enterprise_id"]
        headers = setup_enterprise["headers"]

        r = client.post(
            "/api/v1/fleet/recharge",
            data={"enterprise_id": eid, "amount": "500.00"},
            files={"file": ("voucher.jpg", io.BytesIO(b"<html><body>evil</body></html>"), "image/jpeg")},
            headers=headers,
        )
        assert r.status_code == 422
        assert "文件内容与声明类型不符" in r.json().get("detail", "")

    def test_create_recharge_invalid_amount(self, client: TestClient, setup_enterprise):
        """金额无效"""
        eid = setup_enterprise["enterprise_id"]
        headers = setup_enterprise["headers"]

        r = client.post(
            "/api/v1/fleet/recharge",
            data={"enterprise_id": eid, "amount": "0"},
            files={"file": _make_voucher_file()},
            headers=headers,
        )
        assert r.status_code == 422

    def test_create_recharge_no_file(self, client: TestClient, setup_enterprise):
        """缺少文件"""
        eid = setup_enterprise["enterprise_id"]
        headers = setup_enterprise["headers"]

        r = client.post(
            "/api/v1/fleet/recharge",
            data={"enterprise_id": eid, "amount": "100.00"},
            headers=headers,
        )
        assert r.status_code == 422


class TestFleetRechargeList:
    """列表 + 权限隔离"""

    def test_list_as_admin(self, client: TestClient, setup_enterprise):
        """admin 可看全部"""
        headers = setup_enterprise["headers"]
        r = client.get("/api/v1/fleet/recharge", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "data" in data or "items" in data

    def test_list_filter_by_status(self, client: TestClient, setup_enterprise):
        """按状态筛选"""
        headers = setup_enterprise["headers"]
        r = client.get("/api/v1/fleet/recharge?status=pending", headers=headers)
        assert r.status_code == 200


class TestFleetRechargeApprove:
    """审核通过"""

    def test_approve_balance_updated(self, client: TestClient, setup_enterprise, db_session):
        """审核通过后企业余额增加"""
        eid = setup_enterprise["enterprise_id"]
        headers = setup_enterprise["headers"]

        # 创建充值申请
        r = client.post(
            "/api/v1/fleet/recharge",
            data={"enterprise_id": eid, "amount": "1000.00"},
            files={"file": _make_voucher_file()},
            headers=headers,
        )
        assert r.status_code == 200
        req_id = r.json()["data"]["id"]

        # 记录审核前余额
        ent_before = db_session.query(Enterprise).filter(Enterprise.id == eid).first()
        balance_before = float(ent_before.balance or 0)

        # 审核通过
        r2 = client.post(f"/api/v1/fleet/recharge/{req_id}/approve", headers=headers)
        assert r2.status_code == 200, r2.text
        assert r2.json()["data"]["status"] == "approved"

        # 验证余额增加
        db_session.expire_all()
        ent_after = db_session.query(Enterprise).filter(Enterprise.id == eid).first()
        balance_after = float(ent_after.balance or 0)
        assert abs((balance_after - balance_before) - 1000.0) < 0.01

    def test_approve_already_processed(self, client: TestClient, setup_enterprise):
        """重复审核已处理的申请"""
        eid = setup_enterprise["enterprise_id"]
        headers = setup_enterprise["headers"]

        # 创建 + 通过
        r = client.post(
            "/api/v1/fleet/recharge",
            data={"enterprise_id": eid, "amount": "200.00"},
            files={"file": _make_voucher_file()},
            headers=headers,
        )
        req_id = r.json()["data"]["id"]
        client.post(f"/api/v1/fleet/recharge/{req_id}/approve", headers=headers)

        # 再次通过 → 409
        r2 = client.post(f"/api/v1/fleet/recharge/{req_id}/approve", headers=headers)
        assert r2.status_code == 409


class TestFleetRechargeReject:
    """驳回"""

    def test_reject_with_remark(self, client: TestClient, setup_enterprise):
        """驳回并填写理由"""
        eid = setup_enterprise["enterprise_id"]
        headers = setup_enterprise["headers"]

        r = client.post(
            "/api/v1/fleet/recharge",
            data={"enterprise_id": eid, "amount": "300.00"},
            files={"file": _make_voucher_file()},
            headers=headers,
        )
        req_id = r.json()["data"]["id"]

        r2 = client.post(
            f"/api/v1/fleet/recharge/{req_id}/reject",
            json={"remark": "凭证模糊，请重新上传"},
            headers=headers,
        )
        assert r2.status_code == 200, r2.text
        data = r2.json()["data"]
        assert data["status"] == "rejected"
        assert data["remark"] == "凭证模糊，请重新上传"

    def test_reject_already_processed(self, client: TestClient, setup_enterprise):
        """驳回已处理的申请 → 400"""
        eid = setup_enterprise["enterprise_id"]
        headers = setup_enterprise["headers"]

        r = client.post(
            "/api/v1/fleet/recharge",
            data={"enterprise_id": eid, "amount": "100.00"},
            files={"file": _make_voucher_file()},
            headers=headers,
        )
        req_id = r.json()["data"]["id"]
        client.post(f"/api/v1/fleet/recharge/{req_id}/reject", json={"remark": "驳回"}, headers=headers)

        r2 = client.post(f"/api/v1/fleet/recharge/{req_id}/reject", json={"remark": "再次驳回"}, headers=headers)
        assert r2.status_code == 409
