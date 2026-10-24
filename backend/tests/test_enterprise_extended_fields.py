"""
Enterprise 字段扩展测试

覆盖新增字段:
- default_vehicle_config (JSON)
- address (str)
- description (str)
在 Create / Update / GET 中的读写
"""
import pytest


def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json().get("data", {}).get("token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


class TestEnterpriseExtendedFields:
    """Enterprise 新增字段读写测试"""

    def test_create_with_extended_fields(self, client, seed_users):
        """创建时携带新字段"""
        headers = _auth(client)
        config = {"battery_capacity_kwh": 75, "brand": "BYD", "model": "T3"}
        resp = client.post("/api/v1/enterprises", json={
            "name": "扩展字段企业",
            "code": "EXT001",
            "address": "深圳市南山区科技园",
            "description": "新能源车队运营企业",
            "default_vehicle_config": config,
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["address"] == "深圳市南山区科技园"
        assert data["description"] == "新能源车队运营企业"
        assert data["default_vehicle_config"] == config

    def test_get_returns_extended_fields(self, client, seed_users):
        """GET 详情返回新字段"""
        headers = _auth(client)
        # 创建
        create = client.post("/api/v1/enterprises", json={
            "name": "获取测试企业",
            "code": "EXT002",
            "address": "北京市海淀区",
            "description": "测试获取详情",
            "default_vehicle_config": {"max_speed": 120},
        }, headers=headers)
        ent_id = create.json()["data"]["id"]

        # 获取
        resp = client.get(f"/api/v1/enterprises/{ent_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["address"] == "北京市海淀区"
        assert data["description"] == "测试获取详情"
        assert data["default_vehicle_config"] == {"max_speed": 120}

    def test_update_extended_fields(self, client, seed_users):
        """PUT 更新新字段"""
        headers = _auth(client)
        # 先创建
        create = client.post("/api/v1/enterprises", json={
            "name": "更新前企业",
            "code": "EXT003",
        }, headers=headers)
        ent_id = create.json()["data"]["id"]

        # 更新
        resp = client.put(f"/api/v1/enterprises/{ent_id}", json={
            "address": "上海市浦东新区",
            "description": "更新后的描述",
            "default_vehicle_config": {"soc_min": 20, "soc_max": 80},
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["address"] == "上海市浦东新区"
        assert data["description"] == "更新后的描述"
        assert data["default_vehicle_config"]["soc_min"] == 20
        assert data["default_vehicle_config"]["soc_max"] == 80

    def test_extended_fields_default_none(self, client, seed_users):
        """不传新字段时默认为 None"""
        headers = _auth(client)
        resp = client.post("/api/v1/enterprises", json={
            "name": "默认值测试",
            "code": "EXT004",
        }, headers=headers)
        data = resp.json()["data"]
        assert data["address"] is None
        assert data["description"] is None
        assert data["default_vehicle_config"] is None

    def test_update_partial_extended_field(self, client, seed_users):
        """仅更新部分新字段"""
        headers = _auth(client)
        create = client.post("/api/v1/enterprises", json={
            "name": "部分更新企业",
            "code": "EXT005",
            "address": "广州市天河区",
            "description": "原始描述",
        }, headers=headers)
        ent_id = create.json()["data"]["id"]

        # 仅更新 address
        resp = client.put(f"/api/v1/enterprises/{ent_id}", json={
            "address": "广州市越秀区",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["address"] == "广州市越秀区"
        # description 不变
        assert data["description"] == "原始描述"
