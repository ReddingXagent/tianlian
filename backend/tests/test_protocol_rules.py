"""
协议解析规则 API 测试 (admin-platform-spec §2.4)
覆盖: list(鉴权/按 protocol_id 过滤)、create、update、delete、级联删除
契约字段: protocol_id/direction(uplink/downlink)/message_type/parse_rule/encode_rule/status
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


def _create_protocol(token, code="PROTO_RULE_1"):
    resp = client.post(
        "/api/v1/device-protocols",
        json={"name": "规则测试协议", "code": code, "type": "ocpp", "version": "1.6"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _create_rule(token, protocol_id, direction="uplink", message_type="MeterValues"):
    resp = client.post(
        "/api/v1/protocol-rules",
        json={
            "protocol_id": protocol_id,
            "direction": direction,
            "message_type": message_type,
            "parse_rule": {"path": "$.meterValue", "scale": 0.001},
            "encode_rule": None,
        },
        headers=_h(token),
    )
    assert resp.status_code == 200, f"创建规则失败: {resp.text}"
    return resp.json()["data"]


class TestProtocolRulesAPI:

    def test_list_rules_requires_auth(self):
        """无 token → 401/403"""
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        assert client.get("/api/v1/protocol-rules").status_code in (401, 403)

    def test_create_rule(self, auth_token):
        """创建解析规则 → 字段回显"""
        proto = _create_protocol(auth_token)
        rule = _create_rule(auth_token, proto["id"])
        assert rule["id"] > 0
        assert rule["protocol_id"] == proto["id"]
        assert rule["direction"] == "uplink"
        assert rule["message_type"] == "MeterValues"
        assert rule["parse_rule"] == {"path": "$.meterValue", "scale": 0.001}
        assert rule["status"] == "active"

    def test_list_rules_by_protocol(self, auth_token):
        """按 protocol_id 过滤 — 只返回该协议的规则"""
        p1 = _create_protocol(auth_token, code="PROTO_A")
        p2 = _create_protocol(auth_token, code="PROTO_B")
        _create_rule(auth_token, p1["id"], message_type="BootNotification")
        _create_rule(auth_token, p1["id"], message_type="MeterValues")
        _create_rule(auth_token, p2["id"], message_type="StatusNotification")

        resp = client.get(
            f"/api/v1/protocol-rules?protocol_id={p1['id']}", headers=_h(auth_token)
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert all(it["protocol_id"] == p1["id"] for it in data["items"])

    def test_update_rule(self, auth_token):
        """PUT 更新规则字段"""
        proto = _create_protocol(auth_token)
        rule = _create_rule(auth_token, proto["id"])
        resp = client.put(
            f"/api/v1/protocol-rules/{rule['id']}",
            json={"direction": "downlink", "encode_rule": {"cmd": "Reset"}},
            headers=_h(auth_token),
        )
        assert resp.status_code == 200
        # 列表确认落库
        listing = client.get(
            f"/api/v1/protocol-rules?protocol_id={proto['id']}", headers=_h(auth_token)
        ).json()["data"]
        updated = listing["items"][0]
        assert updated["direction"] == "downlink"
        assert updated["encode_rule"] == {"cmd": "Reset"}

    def test_delete_rule(self, auth_token):
        """DELETE 规则 → 列表中消失"""
        proto = _create_protocol(auth_token)
        rule = _create_rule(auth_token, proto["id"])
        resp = client.delete(f"/api/v1/protocol-rules/{rule['id']}", headers=_h(auth_token))
        assert resp.status_code == 200
        listing = client.get(
            f"/api/v1/protocol-rules?protocol_id={proto['id']}", headers=_h(auth_token)
        ).json()["data"]
        assert listing["total"] == 0

    def test_delete_protocol_cascades_rules(self, auth_token):
        """删协议 → 关联规则一并清除（ORM cascade）"""
        proto = _create_protocol(auth_token, code="CASCADE_1")
        _create_rule(auth_token, proto["id"])
        _create_rule(auth_token, proto["id"], message_type="Heartbeat")

        resp = client.delete(
            f"/api/v1/device-protocols/{proto['id']}", headers=_h(auth_token)
        )
        assert resp.status_code == 200
        # 规则应随协议级联删除
        listing = client.get(
            f"/api/v1/protocol-rules?protocol_id={proto['id']}", headers=_h(auth_token)
        ).json()["data"]
        assert listing["total"] == 0

    def test_create_rule_protocol_not_found(self, auth_token):
        """不存在的 protocol_id → 404"""
        resp = client.post(
            "/api/v1/protocol-rules",
            json={"protocol_id": 999999, "direction": "uplink", "message_type": "X"},
            headers=_h(auth_token),
        )
        assert resp.status_code == 404
