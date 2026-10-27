"""
status/category/type/source 族 API 输入 Literal 收紧验证 (卡 fbc05dc8)

非法枚举值 → 422 (Pydantic 前置拦截, 防碎片化 + 防灌 SQLEnum 触发 500);
合法值 → 通过校验层 (业务结果不影响断言主体)。

收紧范围/依据:
- enterprises.status        ← EnterpriseStatus enum: active/inactive/suspended
- device_library.status     ← 模型注释: active/inactive
- inspection Template.status ← 模型注释: active/inactive
- runbook_templates.status  ← 模型注释: active/inactive
- operate/users.status      ← users_api.VALID_STATUSES: active/inactive/suspended
- runbook_templates.category ← RunbookTemplate.TEMPLATES 种子集合: inverter/charger/pcs/bms/ems/ess/general
- fleet_drivers TransactionCreateRequest.type ← 端点逻辑仅允许 consume/refund (recharge 走专用接口)
- parking_events.source     ← OccupancyEventSource enum: alpr/charging_estimate

triage-out(不收紧, 自由文本):
- knowledge/articles.category — 前端用自由中文分类(维修指南/电气安全/故障诊断等), 无封闭集合
- knowledge/faq.category — 既有测试/业务大量使用自由值(operation/general/technical/maintenance/中文), 非封闭集合
- carbon_emission FactorCreate/Update.source — 数据来源说明性自由文本(如"生态环境部")
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库"""
    pass


BAD_STATUS = "zombie"
BAD_CATEGORY = "nope"
BAD_TYPE = "recharge_extra"
BAD_SOURCE = "guess"


def _admin_headers():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


# ── status 族 ──

class TestEnterpriseStatusLiteral:
    def test_create_invalid_status_422(self):
        resp = client.post("/api/v1/enterprises", json={
            "name": "坏状态企业", "code": "BAD_STATUS_ENT", "status": BAD_STATUS,
        }, headers=_admin_headers())
        assert resp.status_code == 422

    def test_create_valid_status_not_422(self):
        resp = client.post("/api/v1/enterprises", json={
            "name": "好状态企业", "code": "OK_STATUS_ENT", "status": "active",
        }, headers=_admin_headers())
        assert resp.status_code != 422

    def test_update_invalid_status_422(self):
        resp = client.put("/api/v1/enterprises/1", json={"status": BAD_STATUS},
                          headers=_admin_headers())
        assert resp.status_code == 422


class TestDeviceLibraryStatusLiteral:
    def test_update_invalid_status_422(self):
        resp = client.put("/api/v1/device-library/1", json={"status": BAD_STATUS},
                          headers=_admin_headers())
        assert resp.status_code == 422

    def test_update_valid_status_not_422(self):
        resp = client.put("/api/v1/device-library/1", json={"status": "inactive"},
                          headers=_admin_headers())
        assert resp.status_code != 422


class TestInspectionTemplateStatusLiteral:
    def test_create_invalid_status_422(self):
        resp = client.post("/api/v1/inspection/templates", json={
            "name": "坏状态模板", "status": BAD_STATUS,
        }, headers=_admin_headers())
        assert resp.status_code == 422

    def test_update_invalid_status_422(self):
        resp = client.put("/api/v1/inspection/templates/1", json={"status": BAD_STATUS},
                          headers=_admin_headers())
        assert resp.status_code == 422


class TestRunbookTemplateStatusLiteral:
    def test_create_invalid_status_422(self):
        resp = client.post("/api/v1/runbooks/templates", json={
            "name": "坏状态RB", "status": BAD_STATUS,
        }, headers=_admin_headers())
        assert resp.status_code == 422

    def test_update_invalid_status_422(self):
        resp = client.put("/api/v1/runbooks/templates/1", json={"status": BAD_STATUS},
                          headers=_admin_headers())
        assert resp.status_code == 422


class TestOperateUsersStatusLiteral:
    def test_update_invalid_status_422(self):
        resp = client.put("/api/v1/operate/users/1", json={"status": BAD_STATUS},
                          headers=_admin_headers())
        assert resp.status_code == 422

    def test_update_valid_status_not_422(self):
        resp = client.put("/api/v1/operate/users/1", json={"status": "active"},
                          headers=_admin_headers())
        assert resp.status_code != 422


# ── category 族 ──

class TestRunbookTemplateCategoryLiteral:
    def test_create_invalid_category_422(self):
        resp = client.post("/api/v1/runbooks/templates", json={
            "name": "坏类别RB", "category": BAD_CATEGORY,
        }, headers=_admin_headers())
        assert resp.status_code == 422

    def test_create_valid_category_not_422(self):
        resp = client.post("/api/v1/runbooks/templates", json={
            "name": "好类别RB", "category": "inverter",
        }, headers=_admin_headers())
        assert resp.status_code != 422

    def test_update_invalid_category_422(self):
        resp = client.put("/api/v1/runbooks/templates/1", json={"category": BAD_CATEGORY},
                          headers=_admin_headers())
        assert resp.status_code == 422


# ── type/source 族 ──

class TestFleetDriverTransactionTypeLiteral:
    def test_create_invalid_type_422(self):
        resp = client.post("/api/v1/fleet/drivers/1/transactions", json={
            "type": BAD_TYPE, "amount": 10,
        }, headers=_admin_headers())
        assert resp.status_code == 422

    def test_create_recharge_via_transactions_422(self):
        """recharge 必须走专用充值接口, 不允许从交易接口灌入"""
        resp = client.post("/api/v1/fleet/drivers/1/transactions", json={
            "type": "recharge", "amount": 10,
        }, headers=_admin_headers())
        assert resp.status_code == 422


class TestParkingEventSourceLiteral:
    def test_report_invalid_source_422(self):
        resp = client.post("/api/v1/parking/events", json={
            "plate_number": "京A12345", "station_id": 1,
            "enter_at": "2026-08-25T10:00:00", "source": BAD_SOURCE,
        }, headers=_admin_headers())
        assert resp.status_code == 422

    def test_batch_invalid_source_422(self):
        resp = client.post("/api/v1/parking/events/batch", json={
            "events": [{
                "plate_number": "京A12345", "station_id": 1,
                "enter_at": "2026-08-25T10:00:00", "source": BAD_SOURCE,
            }],
        }, headers=_admin_headers())
        assert resp.status_code == 422
