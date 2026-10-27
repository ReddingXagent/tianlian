"""
企业车辆状态变更 API 测试 - 车队管理

覆盖:
- PATCH /api/v1/enterprises/{enterprise_id}/vehicles/{vehicle_id} —— 变更车辆状态
- 正常变更(200) / 车辆不存在(404) / 跨企业(404) / 非法状态值(422)
"""
import pytest
from fastapi.testclient import TestClient


# ========== Fixtures (与 test_enterprise_vehicles.py 保持一致，保证可独立运行) ==========

_counter = [0]


def _unique_code(prefix: str = "ENT_VP") -> str:
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
        "vin": "LSJU26938VS100001",
    }
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/enterprises/{enterprise_id}/vehicles",
        json=payload,
        headers=_auth_headers(client),
    )
    assert resp.status_code == 200, f"绑定车辆失败: {resp.text}"
    return resp.json()["data"]


# ========== 状态变更 ==========

class TestVehicleStatusUpdate:
    """车辆状态变更测试"""

    def test_update_status_success(self, client, enterprise_id):
        """正常变更：active -> maintenance，返回200且状态已更新"""
        created = _bind_vehicle(
            client, enterprise_id,
            plate_number="豫P10001", vin="LSJU26938VP000001",
        )
        assert created["status"] == "active"

        resp = client.patch(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{created['id']}",
            json={"status": "maintenance"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == created["id"]
        assert data["status"] == "maintenance"
        assert data["enterprise_id"] == enterprise_id

    def test_update_status_all_values(self, client, enterprise_id):
        """枚举各合法值均可变更"""
        created = _bind_vehicle(
            client, enterprise_id,
            plate_number="豫P10002", vin="LSJU26938VP000002",
        )
        for new_status in ("inactive", "maintenance", "retired", "active"):
            resp = client.patch(
                f"/api/v1/enterprises/{enterprise_id}/vehicles/{created['id']}",
                json={"status": new_status},
                headers=_auth_headers(client),
            )
            assert resp.status_code == 200, f"变更 {new_status} 失败: {resp.text}"
            assert resp.json()["data"]["status"] == new_status

    def test_update_status_persists(self, client, enterprise_id):
        """变更后通过列表接口确认状态已持久化"""
        created = _bind_vehicle(
            client, enterprise_id,
            plate_number="豫P10003", vin="LSJU26938VP000003",
        )
        client.patch(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{created['id']}",
            json={"status": "retired"},
            headers=_auth_headers(client),
        )
        lst = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            headers=_auth_headers(client),
        )
        items = lst.json()["data"]["items"]
        assert items[0]["status"] == "retired"

    def test_update_status_vehicle_not_found(self, client, enterprise_id):
        """车辆不存在 -> 404"""
        resp = client.patch(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/99999",
            json={"status": "maintenance"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404

    def test_update_status_wrong_enterprise(self, client, test_db):
        """变更别企业的车辆 -> 404（查询带 enterprise_id 约束）"""
        ent1 = _create_enterprise(test_db, name="企业甲")
        ent2 = _create_enterprise(test_db, name="企业乙")
        # 车辆挂在 ent1
        created = _bind_vehicle(
            client, ent1.id, plate_number="豫P10004", vin="LSJU26938VP000004",
        )
        # 用 ent2 的 URL 变更状态
        resp = client.patch(
            f"/api/v1/enterprises/{ent2.id}/vehicles/{created['id']}",
            json={"status": "maintenance"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404

    def test_update_status_invalid_value(self, client, enterprise_id):
        """非法状态值 -> 422（Pydantic 枚举校验）"""
        created = _bind_vehicle(
            client, enterprise_id,
            plate_number="豫P10005", vin="LSJU26938VP000005",
        )
        resp = client.patch(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{created['id']}",
            json={"status": "flying"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422
        # 且不应改变原状态
        lst = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            headers=_auth_headers(client),
        )
        assert lst.json()["data"]["items"][0]["status"] == "active"

    def test_update_status_missing_field(self, client, enterprise_id):
        """缺少 status 字段 -> 422"""
        created = _bind_vehicle(
            client, enterprise_id,
            plate_number="豫P10006", vin="LSJU26938VP000006",
        )
        resp = client.patch(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{created['id']}",
            json={},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_update_status_enterprise_not_found(self, client):
        """企业不存在 -> 404"""
        resp = client.patch(
            "/api/v1/enterprises/99999/vehicles/1",
            json={"status": "maintenance"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404
