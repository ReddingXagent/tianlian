"""
设备型号库管理 API 测试 (admin-platform-spec §2.4)
覆盖: list(鉴权/空/搜索)、create、detail、update、delete
契约字段: brand/model/device_type/rated_power_kw/params_template/supported_protocols/spec_url/status
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库 + seed admin"""
    yield


@pytest.fixture
def auth_token(test_db):
    """登录获取 token"""
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _payload(brand="华为", model="SUN2000-30KTL", device_type="pv"):
    return {
        "brand": brand,
        "model": model,
        "device_type": device_type,
        "rated_power_kw": 30.0,
        "params_template": {"mppt_num": 2, "voc": 1000},
        "supported_protocols": ["modbus", "mqtt"],
        "spec_url": "https://example.com/spec.pdf",
    }


def _create(token, **overrides):
    body = _payload(**overrides)
    resp = client.post("/api/v1/device-library", json=body, headers=_h(token))
    assert resp.status_code == 200, f"创建失败: {resp.text}"
    return resp.json()["data"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


class TestDeviceLibraryAPI:

    def test_list_requires_auth(self):
        """无 token → 401/403"""
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        assert client.get("/api/v1/device-library").status_code in (401, 403)

    def test_list_empty(self, auth_token):
        """空库查询 → items=[] total=0"""
        resp = client.get("/api/v1/device-library", headers=_h(auth_token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_device_library(self, auth_token):
        """创建设备型号 → 返回 id 与全部字段"""
        item = _create(auth_token)
        assert item["id"] > 0
        assert item["brand"] == "华为"
        assert item["model"] == "SUN2000-30KTL"
        assert item["device_type"] == "pv"
        assert item["rated_power_kw"] == 30.0
        assert item["params_template"] == {"mppt_num": 2, "voc": 1000}
        assert item["supported_protocols"] == ["modbus", "mqtt"]
        assert item["status"] == "active"

    def test_get_device_library_detail(self, auth_token):
        """GET /{id} → 返回单条详情"""
        created = _create(auth_token)
        resp = client.get(f"/api/v1/device-library/{created['id']}", headers=_h(auth_token))
        assert resp.status_code == 200
        item = resp.json()["data"]
        assert item["id"] == created["id"]
        assert item["brand"] == "华为"
        assert item["spec_url"] == "https://example.com/spec.pdf"

    def test_get_device_library_not_found(self, auth_token):
        """不存在的 id → 404"""
        resp = client.get("/api/v1/device-library/999999", headers=_h(auth_token))
        assert resp.status_code == 404

    def test_update_device_library(self, auth_token):
        """PUT 更新 → 字段变更"""
        created = _create(auth_token)
        resp = client.put(
            f"/api/v1/device-library/{created['id']}",
            json={"rated_power_kw": 50.0, "status": "inactive"},
            headers=_h(auth_token),
        )
        assert resp.status_code == 200
        # 详情确认已落库
        detail = client.get(
            f"/api/v1/device-library/{created['id']}", headers=_h(auth_token)
        ).json()["data"]
        assert detail["rated_power_kw"] == 50.0
        assert detail["status"] == "inactive"

    def test_delete_device_library(self, auth_token):
        """DELETE → 再次查询应 404"""
        created = _create(auth_token)
        resp = client.delete(f"/api/v1/device-library/{created['id']}", headers=_h(auth_token))
        assert resp.status_code == 200
        assert client.get(
            f"/api/v1/device-library/{created['id']}", headers=_h(auth_token)
        ).status_code == 404

    def test_search_device_library(self, auth_token):
        """keyword 搜索 → 按 brand/model 匹配"""
        _create(auth_token, brand="华为", model="SUN2000-30KTL")
        _create(auth_token, brand="阳光电源", model="SG110CX")
        # 搜 "华为"
        resp = client.get("/api/v1/device-library?keyword=华为", headers=_h(auth_token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["brand"] == "华为"
        # device_type 过滤
        _create(auth_token, brand="宁德", model="CN-100", device_type="battery")
        resp2 = client.get("/api/v1/device-library?device_type=battery", headers=_h(auth_token))
        assert resp2.json()["data"]["total"] == 1
