"""
设备通信协议管理 API 测试 (admin-platform-spec §2.4)
覆盖: list(鉴权/空/按 type 过滤)、create、update、delete
契约字段: name/code/type(ocpp/modbus/mqtt/http/custom)/version/protocol_definition/data_point_mappings/status
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    yield


@pytest.fixture
def auth_token(test_db):
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _payload(name="OCPP 1.6J", code="OCPP_16J", ptype="ocpp"):
    return {
        "name": name,
        "code": code,
        "type": ptype,
        "version": "1.6",
        "protocol_definition": {"transport": "websocket", "port": 9000},
        "data_point_mappings": [{"field": "energy_kwh", "source": "MeterValues"}],
    }


def _create(token, **overrides):
    body = _payload(**overrides)
    resp = client.post("/api/v1/device-protocols", json=body, headers=_h(token))
    assert resp.status_code == 200, f"创建失败: {resp.text}"
    return resp.json()["data"]


class TestDeviceProtocolsAPI:

    def test_list_requires_auth(self):
        """无 token → 401/403"""
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        assert client.get("/api/v1/device-protocols").status_code in (401, 403)

    def test_list_empty(self, auth_token):
        """空库查询 → items=[] total=0"""
        resp = client.get("/api/v1/device-protocols", headers=_h(auth_token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_protocol(self, auth_token):
        """创建协议 → 返回 id 与全部字段"""
        item = _create(auth_token)
        assert item["id"] > 0
        assert item["name"] == "OCPP 1.6J"
        assert item["code"] == "OCPP_16J"
        assert item["type"] == "ocpp"
        assert item["version"] == "1.6"
        assert item["protocol_definition"] == {"transport": "websocket", "port": 9000}
        assert item["data_point_mappings"] == [{"field": "energy_kwh", "source": "MeterValues"}]
        assert item["status"] == "active"

    def test_update_protocol(self, auth_token):
        """PUT 更新 → 字段变更"""
        created = _create(auth_token)
        resp = client.put(
            f"/api/v1/device-protocols/{created['id']}",
            json={"version": "2.0.1", "status": "inactive"},
            headers=_h(auth_token),
        )
        assert resp.status_code == 200
        detail = client.get(
            f"/api/v1/device-protocols/{created['id']}", headers=_h(auth_token)
        ).json()["data"]
        assert detail["version"] == "2.0.1"
        assert detail["status"] == "inactive"

    def test_delete_protocol(self, auth_token):
        """DELETE → 再次 GET detail 应 404"""
        created = _create(auth_token)
        resp = client.delete(f"/api/v1/device-protocols/{created['id']}", headers=_h(auth_token))
        assert resp.status_code == 200
        assert client.get(
            f"/api/v1/device-protocols/{created['id']}", headers=_h(auth_token)
        ).status_code == 404

    def test_filter_by_type(self, auth_token):
        """按 type 过滤列表"""
        _create(auth_token, name="OCPP", code="OCPP_1", ptype="ocpp")
        _create(auth_token, name="Modbus-RTU", code="MB_1", ptype="modbus")
        _create(auth_token, name="MQTT", code="MQ_1", ptype="mqtt")

        resp = client.get("/api/v1/device-protocols?type=modbus", headers=_h(auth_token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["type"] == "modbus"

    def test_detail_not_found(self, auth_token):
        """不存在的 id → 404"""
        resp = client.get("/api/v1/device-protocols/999999", headers=_h(auth_token))
        assert resp.status_code == 404


def _create_rule(token, protocol_id, direction="uplink", **overrides):
    body = {
        "protocol_id": protocol_id,
        "direction": direction,
        "message_type": overrides.get("message_type", "MeterValues"),
        "parse_rule": overrides.get("parse_rule", {"regex": "^\\d+$", "scale": 0.1}),
        "encode_rule": overrides.get("encode_rule"),
    }
    resp = client.post("/api/v1/protocol-rules", json=body, headers=_h(token))
    assert resp.status_code == 200, f"创建规则失败: {resp.text}"
    return resp.json()["data"]


class TestProtocolRulesAPI:
    """协议解析规则 CRUD (/api/v1/protocol-rules) — 补齐 device_protocols.py L208-303 覆盖"""

    def test_list_rules_requires_auth(self):
        """匿名访问规则列表 → 401/403"""
        client.headers.pop("Authorization", None)
        assert client.get("/api/v1/protocol-rules").status_code in (401, 403)

    def test_list_rules_empty(self, auth_token):
        """空库 → items=[] total=0"""
        resp = client.get("/api/v1/protocol-rules", headers=_h(auth_token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_rule(self, auth_token):
        """创建规则 → 返回全字段, status 默认 active"""
        proto = _create(auth_token)
        rule = _create_rule(auth_token, proto["id"])
        assert rule["id"] > 0
        assert rule["protocol_id"] == proto["id"]
        assert rule["direction"] == "uplink"
        assert rule["message_type"] == "MeterValues"
        assert rule["parse_rule"] == {"regex": "^\\d+$", "scale": 0.1}
        assert rule["status"] == "active"

    def test_create_rule_protocol_not_found(self, auth_token):
        """protocol_id 不存在 → 404"""
        resp = client.post(
            "/api/v1/protocol-rules",
            json={"protocol_id": 999999, "direction": "uplink"},
            headers=_h(auth_token),
        )
        assert resp.status_code == 404

    def test_list_rules_filter(self, auth_token):
        """按 protocol_id / direction 过滤"""
        proto = _create(auth_token)
        other = _create(auth_token, name="Modbus", code="MB_X", ptype="modbus")
        _create_rule(auth_token, proto["id"], direction="uplink")
        _create_rule(auth_token, proto["id"], direction="downlink", message_type="SetChargingProfile")
        _create_rule(auth_token, other["id"], direction="uplink")

        resp = client.get(
            f"/api/v1/protocol-rules?protocol_id={proto['id']}", headers=_h(auth_token)
        )
        assert resp.json()["data"]["total"] == 2

        resp = client.get(
            f"/api/v1/protocol-rules?protocol_id={proto['id']}&direction=downlink",
            headers=_h(auth_token),
        )
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["direction"] == "downlink"

    def test_update_rule(self, auth_token):
        """PUT 更新 → 字段变更"""
        proto = _create(auth_token)
        rule = _create_rule(auth_token, proto["id"])
        resp = client.put(
            f"/api/v1/protocol-rules/{rule['id']}",
            json={"message_type": "BootNotification", "status": "inactive"},
            headers=_h(auth_token),
        )
        assert resp.status_code == 200
        listed = client.get(
            f"/api/v1/protocol-rules?protocol_id={proto['id']}", headers=_h(auth_token)
        ).json()["data"]["items"]
        updated = next(r for r in listed if r["id"] == rule["id"])
        assert updated["message_type"] == "BootNotification"
        assert updated["status"] == "inactive"

    def test_update_rule_no_change(self, auth_token):
        """PUT 空 body → 200 无需更新"""
        proto = _create(auth_token)
        rule = _create_rule(auth_token, proto["id"])
        resp = client.put(
            f"/api/v1/protocol-rules/{rule['id']}", json={}, headers=_h(auth_token)
        )
        assert resp.status_code == 200
        assert "无需更新" in resp.text

    def test_update_rule_not_found(self, auth_token):
        """PUT 不存在规则 → 404"""
        resp = client.put(
            "/api/v1/protocol-rules/999999", json={"status": "inactive"}, headers=_h(auth_token)
        )
        assert resp.status_code == 404

    def test_delete_rule(self, auth_token):
        """DELETE → 列表中消失"""
        proto = _create(auth_token)
        rule = _create_rule(auth_token, proto["id"])
        resp = client.delete(f"/api/v1/protocol-rules/{rule['id']}", headers=_h(auth_token))
        assert resp.status_code == 200
        data = client.get(
            f"/api/v1/protocol-rules?protocol_id={proto['id']}", headers=_h(auth_token)
        ).json()["data"]
        assert data["total"] == 0

    def test_delete_rule_not_found(self, auth_token):
        """DELETE 不存在规则 → 404"""
        resp = client.delete("/api/v1/protocol-rules/999999", headers=_h(auth_token))
        assert resp.status_code == 404

    def test_protocol_delete_cascades_rules(self, auth_token):
        """删除协议 → 其规则级联删除"""
        proto = _create(auth_token)
        _create_rule(auth_token, proto["id"], direction="uplink")
        _create_rule(auth_token, proto["id"], direction="downlink")
        resp = client.delete(f"/api/v1/device-protocols/{proto['id']}", headers=_h(auth_token))
        assert resp.status_code == 200
        data = client.get(
            f"/api/v1/protocol-rules?protocol_id={proto['id']}", headers=_h(auth_token)
        ).json()["data"]
        assert data["total"] == 0
