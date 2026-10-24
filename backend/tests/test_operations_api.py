import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


class TestEnterprises:
    def test_list_enterprises_empty(self):
        token = _login()
        resp = client.get("/api/v1/enterprises", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["items"] == []

    def test_create_enterprise_success(self):
        token = _login()
        payload = {"name": "TestCorp", "code": "ENT001", "contact": "Zhang", "phone": "13800138000", "balance": 10000.0, "credit_limit": 50000.0, "status": "active"}
        resp = client.post("/api/v1/enterprises", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "TestCorp"
    def test_create_enterprise_duplicate_code(self):
        token = _login()
        payload = {"name": "A", "code": "ENT002"}
        r1 = client.post("/api/v1/enterprises", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert r1.status_code == 200
        r2 = client.post("/api/v1/enterprises", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 400

    def test_get_enterprise_detail(self):
        token = _login()
        cr = client.post("/api/v1/enterprises", json={"name": "Detail", "code": "ENT003"}, headers={"Authorization": f"Bearer {token}"})
        eid = cr.json()["data"]["id"]
        resp = client.get(f"/api/v1/enterprises/{eid}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_get_enterprise_not_found(self):
        token = _login()
        resp = client.get("/api/v1/enterprises/999999", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_update_enterprise(self):
        token = _login()
        cr = client.post("/api/v1/enterprises", json={"name": "Old", "code": "ENT004"}, headers={"Authorization": f"Bearer {token}"})
        eid = cr.json()["data"]["id"]
        resp = client.put(f"/api/v1/enterprises/{eid}", json={"name": "New", "contact": "Li"}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "New"

    def test_delete_enterprise(self):
        token = _login()
        cr = client.post("/api/v1/enterprises", json={"name": "Del", "code": "ENT005"}, headers={"Authorization": f"Bearer {token}"})
        eid = cr.json()["data"]["id"]
        resp = client.delete(f"/api/v1/enterprises/{eid}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        resp = client.get(f"/api/v1/enterprises/{eid}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_list_enterprises_with_filters(self):
        token = _login()
        client.post("/api/v1/enterprises", json={"name": "ActiveCorp", "code": "ENT_A1", "status": "active"}, headers={"Authorization": f"Bearer {token}"})
        client.post("/api/v1/enterprises", json={"name": "InactiveCorp", "code": "ENT_A2", "status": "inactive"}, headers={"Authorization": f"Bearer {token}"})
        resp = client.get("/api/v1/enterprises?status=active", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()["data"]["items"]) >= 1
        resp = client.get("/api/v1/enterprises?keyword=Inactive", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert any("Inactive" in i["name"] for i in resp.json()["data"]["items"])

class TestPricing:
    def test_list_pricing_empty(self):
        token = _login()
        resp = client.get("/api/v1/pricing", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_create_pricing_success(self):
        token = _login()
        payload = {"name": "PeakRate", "period_type": "peak", "start_time": "09:00", "end_time": "12:00", "electricity_price": 1.2, "service_fee_rate": 0.8, "parking_fee_per_hour": 5.0, "idle_penalty_per_min": 0.5, "is_active": True}
        resp = client.post("/api/v1/pricing", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["period_type"] == "peak"

    def test_create_pricing_invalid_period(self):
        token = _login()
        resp = client.post("/api/v1/pricing", json={"name": "Invalid", "period_type": "invalid", "start_time": "08:00", "end_time": "18:00"}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

    def test_get_pricing_detail(self):
        token = _login()
        cr = client.post("/api/v1/pricing", json={"name": "Valley", "period_type": "valley", "start_time": "23:00", "end_time": "07:00", "electricity_price": 0.3}, headers={"Authorization": f"Bearer {token}"})
        pid = cr.json()["data"]["id"]
        resp = client.get(f"/api/v1/pricing/{pid}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_update_pricing(self):
        token = _login()
        cr = client.post("/api/v1/pricing", json={"name": "Old", "period_type": "flat", "start_time": "08:00", "end_time": "20:00", "electricity_price": 0.8}, headers={"Authorization": f"Bearer {token}"})
        pid = cr.json()["data"]["id"]
        resp = client.put(f"/api/v1/pricing/{pid}", json={"electricity_price": 0.9}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["electricity_price"] == 0.9

    def test_delete_pricing(self):
        token = _login()
        cr = client.post("/api/v1/pricing", json={"name": "Del", "period_type": "shoulder", "start_time": "12:00", "end_time": "17:00"}, headers={"Authorization": f"Bearer {token}"})
        pid = cr.json()["data"]["id"]
        resp = client.delete(f"/api/v1/pricing/{pid}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        resp = client.get(f"/api/v1/pricing/{pid}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

class TestChargingOrders:
    def test_list_orders_empty(self):
        token = _login()
        resp = client.get("/api/v1/charging-orders", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["items"] == []

    def test_create_order_success(self):
        token = _login()
        payload = {"station_id": 1, "device_id": 10, "user_id": 100, "user_type": "app", "plate_number": "TEST001", "charged_kwh": 30.5, "duration_minutes": 45, "parking_duration_hours": 1.0, "idle_minutes": 0, "discount_amount": 2.0, "remark": "test"}
        resp = client.post("/api/v1/charging-orders", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["station_id"] == 1
        assert d["charged_kwh"] == 30.5
        assert d["total_amount"] > 0
        assert d["order_status"] == "pending"
        assert d["order_no"].startswith("CO")

    def test_create_order_with_pricing(self):
        token = _login()
        client.post("/api/v1/pricing", json={"name": "High", "period_type": "peak", "start_time": "08:00", "end_time": "22:00", "electricity_price": 1.5, "service_fee_rate": 0.8, "parking_fee_per_hour": 10.0, "idle_penalty_per_min": 1.0, "is_active": True}, headers={"Authorization": f"Bearer {token}"})
        payload = {"station_id": 2, "device_id": 20, "plate_number": "XYZ", "charged_kwh": 50.0, "duration_minutes": 60, "parking_duration_hours": 2.0, "idle_minutes": 10}
        resp = client.post("/api/v1/charging-orders", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["electricity_fee"] == 75.0
        assert d["service_fee"] == 40.0
        assert d["parking_fee"] == 20.0
        assert d["idle_penalty"] == 10.0
        assert d["total_amount"] == 145.0

    def test_get_order_detail(self):
        token = _login()
        cr = client.post("/api/v1/charging-orders", json={"station_id": 1, "device_id": 1, "charged_kwh": 10.0}, headers={"Authorization": f"Bearer {token}"})
        oid = cr.json()["data"]["id"]
        resp = client.get(f"/api/v1/charging-orders/{oid}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_get_order_not_found(self):
        token = _login()
        resp = client.get("/api/v1/charging-orders/999999", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_update_order_status(self):
        token = _login()
        cr = client.post("/api/v1/charging-orders", json={"station_id": 1, "device_id": 1, "charged_kwh": 20.0}, headers={"Authorization": f"Bearer {token}"})
        oid = cr.json()["data"]["id"]
        resp = client.put(f"/api/v1/charging-orders/{oid}/status", json={"status": "charging"}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["order_status"] == "charging"
        resp = client.put(f"/api/v1/charging-orders/{oid}/status", json={"status": "completed"}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["order_status"] == "completed"

    def test_update_order_status_invalid(self):
        token = _login()
        cr = client.post("/api/v1/charging-orders", json={"station_id": 1, "device_id": 1, "charged_kwh": 10.0}, headers={"Authorization": f"Bearer {token}"})
        oid = cr.json()["data"]["id"]
        resp = client.put(f"/api/v1/charging-orders/{oid}/status", json={"status": "invalid"}, headers={"Authorization": f"Bearer {token}"})
        # 卡 77a186b3：status 已收紧为 Literal，非法值在 Pydantic 层即被拒（422）
        assert resp.status_code == 422

    def test_list_orders_with_filters(self):
        token = _login()
        client.post("/api/v1/charging-orders", json={"station_id": 2, "device_id": 111, "charged_kwh": 30.0, "plate_number": "ABC"}, headers={"Authorization": f"Bearer {token}"})
        client.post("/api/v1/charging-orders", json={"station_id": 2, "device_id": 222, "charged_kwh": 40.0, "plate_number": "DEF"}, headers={"Authorization": f"Bearer {token}"})
        resp = client.get("/api/v1/charging-orders?station_id=2", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert all(i["station_id"] == 2 for i in resp.json()["data"]["items"])
        resp = client.get("/api/v1/charging-orders?order_status=pending", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert all(i["order_status"] == "pending" for i in resp.json()["data"]["items"])

    def test_orders_require_auth(self):
        # conftest autouse _auth_module_level_client 会给模块级 client 注入 admin
        # token；本测试验证「匿名拒绝」，须先清除默认 Authorization 头。
        client.headers.pop("Authorization", None)
        resp = client.get("/api/v1/charging-orders")
        assert resp.status_code in (401, 403)
        resp = client.post("/api/v1/charging-orders", json={"station_id": 1, "device_id": 1, "charged_kwh": 1.0})
        assert resp.status_code in (401, 403)

class TestAuth:
    def test_enterprises_require_auth(self):
        # 同 test_orders_require_auth：清除 autouse 注入的 token 后验证匿名拒绝。
        client.headers.pop("Authorization", None)
        resp = client.get("/api/v1/enterprises")
        assert resp.status_code in (401, 403)

    def test_pricing_require_auth(self):
        client.headers.pop("Authorization", None)
        resp = client.get("/api/v1/pricing")
        assert resp.status_code in (401, 403)
