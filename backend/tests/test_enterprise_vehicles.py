"""
企业车辆管理 API 测试 - Phase43 车队管理

覆盖:
- GET    /api/v1/enterprises/{enterprise_id}/vehicles —— 列表 + 分页
- POST   /api/v1/enterprises/{enterprise_id}/vehicles —— 绑定车辆
- DELETE /api/v1/enterprises/{enterprise_id}/vehicles/{vehicle_id} —— 解绑车辆
- 参数校验(422) / 错误处理(404/400) / 企业隔离
"""
import pytest
from fastapi.testclient import TestClient


# ========== Fixtures ==========

_counter = [0]


def _unique_code(prefix: str = "ENT_V") -> str:
    _counter[0] += 1
    return f"{prefix}{_counter[0]}"


def _create_enterprise(test_db, name="测试车队企业"):
    from app.models.enterprise import Enterprise
    db = test_db["session"]
    ent = Enterprise(name=name, code=_unique_code(), balance=10000.00)
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


def _login(client):
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers(client):
    return {"Authorization": f"Bearer {_login(client)}"}


def _bind_vehicle(client, enterprise_id, **overrides):
    """绑定车辆辅助函数，默认成功"""
    payload = {
        "plate_number": "豫A99999",
        "vin": "LSJU26938VS000001",
    }
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/enterprises/{enterprise_id}/vehicles",
        json=payload,
        headers=_auth_headers(client),
    )
    assert resp.status_code == 200, f"绑定车辆失败: {resp.text}"
    return resp.json()["data"]


# ========== 列表 + 分页 ==========

class TestVehicleList:
    """车辆列表与分页测试"""

    def test_list_empty(self, client, enterprise_id):
        """空列表"""
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_list_with_data(self, client, enterprise_id):
        """有数据列表 + 字段完整"""
        _bind_vehicle(client, enterprise_id, plate_number="豫A11111", vin="LSJU26938VS000011")
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        item = data["items"][0]
        assert item["plate_number"] == "豫A11111"
        assert item["vin"] == "LSJU26938VS000011"
        assert item["enterprise_id"] == enterprise_id
        assert item["status"] == "active"
        for key in ("id", "created_at", "updated_at"):
            assert key in item

    def test_list_pagination(self, client, enterprise_id):
        """分页：创建 5 辆，按 page_size=2 取 3 页"""
        for i in range(5):
            _bind_vehicle(client, enterprise_id, plate_number=f"豫P{i:05d}", vin=f"LSJU26938VS00PG{i:02d}")
        # 第1页
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles?page=1&page_size=2",
            headers=_auth_headers(client),
        )
        data = resp.json()["data"]
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2
        # 第3页（剩余1条）
        resp3 = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles?page=3&page_size=2",
            headers=_auth_headers(client),
        )
        data3 = resp3.json()["data"]
        assert len(data3["items"]) == 1

    def test_list_invalid_page(self, client, enterprise_id):
        """page < 1 -> 422"""
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles?page=0",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_list_invalid_page_size(self, client, enterprise_id):
        """page_size > 100 -> 422"""
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles?page_size=200",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_list_enterprise_not_found(self, client):
        """企业不存在 -> 404"""
        resp = client.get(
            "/api/v1/enterprises/99999/vehicles",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404


# ========== 绑定车辆 ==========

class TestVehicleBind:
    """绑定车辆测试"""

    def test_bind_success(self, client, enterprise_id):
        """绑定成功 + 默认 active"""
        data = _bind_vehicle(
            client, enterprise_id,
            plate_number="豫B22222", vin="LSJU26938VS000021",
        )
        assert data["plate_number"] == "豫B22222"
        assert data["vin"] == "LSJU26938VS000021"
        assert data["status"] == "active"
        assert data["enterprise_id"] == enterprise_id
        assert data["driver_name"] is None
        assert data["driver_phone"] is None
        assert data["id"] > 0

    def test_bind_with_driver(self, client, enterprise_id):
        """带司机信息绑定"""
        data = _bind_vehicle(
            client, enterprise_id,
            plate_number="豫C33333", vin="LSJU26938VS000031",
            driver_name="王师傅", driver_phone="13800001234",
        )
        assert data["driver_name"] == "王师傅"
        assert data["driver_phone"] == "13800001234"

    def test_bind_duplicate_vin(self, client, enterprise_id):
        """VIN 重复 -> 400"""
        _bind_vehicle(client, enterprise_id, plate_number="豫D44444", vin="LSJU26938VS000041")
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            json={"plate_number": "豫D55555", "vin": "LSJU26938VS000041"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 400
        # HTTPException 被全局处理器包装为 {code, message, ...}
        assert "VIN" in resp.json()["message"]

    def test_bind_missing_required_field(self, client, enterprise_id):
        """缺少必填字段 vin -> 422"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            json={"plate_number": "豫E66666"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_bind_enterprise_not_found(self, client):
        """企业不存在 -> 404"""
        resp = client.post(
            "/api/v1/enterprises/99999/vehicles",
            json={"plate_number": "豫F77777", "vin": "LSJU26938VS000051"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404


# ========== 解绑车辆 ==========

class TestVehicleUnbind:
    """解绑车辆测试"""

    def test_unbind_success(self, client, enterprise_id):
        """解绑成功后列表中消失"""
        created = _bind_vehicle(client, enterprise_id, plate_number="豫G88888", vin="LSJU26938VS000061")
        resp = client.delete(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{created['id']}",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "车辆解绑成功"
        # 列表里应已无此车
        lst = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            headers=_auth_headers(client),
        )
        assert lst.json()["data"]["total"] == 0

    def test_unbind_not_found(self, client, enterprise_id):
        """车辆不存在 -> 404"""
        resp = client.delete(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/99999",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404

    def test_unbind_wrong_enterprise(self, client, test_db):
        """解绑别企业的车辆 -> 404（查询带 enterprise_id 约束）"""
        ent1 = _create_enterprise(test_db, name="企业甲")
        ent2 = _create_enterprise(test_db, name="企业乙")
        # 车辆挂在 ent1
        created = _bind_vehicle(client, ent1.id, plate_number="豫H99999", vin="LSJU26938VS000071")
        # 用 ent2 的 URL 解绑
        resp = client.delete(
            f"/api/v1/enterprises/{ent2.id}/vehicles/{created['id']}",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404

    def test_unbind_enterprise_not_found(self, client, enterprise_id):
        """企业不存在时解绑 -> 404"""
        resp = client.delete(
            f"/api/v1/enterprises/99999/vehicles/1",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404
