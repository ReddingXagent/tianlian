"""
role/level 族 API 输入 Literal 收紧验证 (卡 e4b484b8)

非法 role/level → 422 (Pydantic 前置拦截, 不再灌 SQLEnum 触发 500);
合法值 → 请求通过校验层 (业务结果不影响断言主体)。
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库"""
    pass


BAD_ROLE = "king"
BAD_LEVEL = "archmage"
BAD_ALARM_LEVEL = "apocalyptic"


def _admin_headers():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


# ── role 族 ──

class TestRoleLiteral:
    def test_register_invalid_role_422(self):
        resp = client.post("/api/v1/auth/register", json={
            "username": "badrole_lit", "password": "test123", "real_name": "坏角色", "role": BAD_ROLE,
        })
        assert resp.status_code == 422

    def test_register_valid_role_passes_validation(self):
        # 卡 19c0ee73: register 白名单 viewer/technician, engineer 等后台角色须 422
        for role in ("technician", "viewer"):
            resp = client.post("/api/v1/auth/register", json={
                "username": f"goodrole_{role}", "password": "test123", "real_name": "好角色", "role": role,
            })
            assert resp.status_code != 422

    def test_users_create_invalid_role_422(self):
        resp = client.post("/api/v1/users", json={"username": "u1", "password": "x123456", "role": BAD_ROLE},
                           headers=_admin_headers())
        assert resp.status_code == 422

    def test_users_update_invalid_role_422(self):
        resp = client.put("/api/v1/users/1", json={"role": BAD_ROLE}, headers=_admin_headers())
        assert resp.status_code == 422

    def test_users_update_valid_role_not_422(self):
        resp = client.put("/api/v1/users/1", json={"role": "viewer"}, headers=_admin_headers())
        assert resp.status_code != 422

    def test_rbac_user_role_invalid_422(self):
        resp = client.put("/api/v1/rbac/users/1/role", json={"role": BAD_ROLE},
                          headers=_admin_headers())
        assert resp.status_code == 422

    def test_system_config_user_role_invalid_422(self):
        resp = client.put("/api/v1/system-config/users/1/role", json={"role": BAD_ROLE},
                          headers=_admin_headers())
        assert resp.status_code == 422

    def test_teams_member_add_invalid_role_422(self):
        resp = client.post("/api/v1/teams/1/members", json={"user_id": 1, "role": BAD_ROLE},
                           headers=_admin_headers())
        assert resp.status_code == 422

    def test_teams_member_add_valid_role_not_422(self):
        resp = client.post("/api/v1/teams/1/members", json={"user_id": 1, "role": "engineer"},
                           headers=_admin_headers())
        assert resp.status_code != 422


# ── engineer level 族 ──

class TestEngineerLevelLiteral:
    def test_create_invalid_level_422(self):
        resp = client.post("/api/v1/engineers",
                           json={"name": "无效", "phone": "13800009999", "password": "test123456", "level": BAD_LEVEL},
                           headers=_admin_headers())
        assert resp.status_code == 422

    def test_update_invalid_level_422(self):
        resp = client.put("/api/v1/engineers/1", json={"level": "invalid"}, headers=_admin_headers())
        assert resp.status_code == 422

    def test_update_valid_level_not_422(self):
        resp = client.put("/api/v1/engineers/1", json={"level": "senior"}, headers=_admin_headers())
        assert resp.status_code != 422


# ── alarm level 族 ──

class TestAlarmLevelLiteral:
    def test_alarm_create_invalid_level_422(self):
        resp = client.post("/api/v1/alarms",
                           json={"device_id": 1, "alarm_type": "overtemp", "content": "x", "level": BAD_ALARM_LEVEL},
                           headers=_admin_headers())
        assert resp.status_code == 422

    def test_alarm_rule_create_invalid_level_422(self):
        resp = client.post("/api/v1/alarms/rules",
                           json={"name": "r", "metric": "temp", "operator": ">", "threshold": 1.0, "level": BAD_ALARM_LEVEL},
                           headers=_admin_headers())
        assert resp.status_code == 422

    def test_alarm_rules_module_invalid_level_422(self):
        resp = client.post("/api/v1/alarm-rules",
                           json={"name": "r", "metric": "temp", "operator": ">", "threshold": 1.0, "level": BAD_ALARM_LEVEL},
                           headers=_admin_headers())
        assert resp.status_code == 422

    def test_alarm_rule_update_invalid_level_422(self):
        resp = client.put("/api/v1/alarm-rules/1", json={"level": BAD_ALARM_LEVEL},
                          headers=_admin_headers())
        assert resp.status_code == 422

    def test_alarm_create_valid_level_not_422(self):
        resp = client.post("/api/v1/alarms",
                           json={"device_id": 1, "alarm_type": "overtemp", "content": "x", "level": "fatal"},
                           headers=_admin_headers())
        assert resp.status_code != 422


# ── notification rule level 族 ──

class TestNotificationRuleLevelLiteral:
    def test_rule_create_invalid_level_422(self):
        resp = client.post("/api/v1/notification-rules", json={"name": "n", "level": BAD_ALARM_LEVEL},
                           headers=_admin_headers())
        assert resp.status_code == 422

    def test_rule_update_invalid_level_422(self):
        resp = client.put("/api/v1/notification-rules/1", json={"level": BAD_ALARM_LEVEL},
                          headers=_admin_headers())
        assert resp.status_code == 422

    def test_rule_update_valid_level_not_422(self):
        resp = client.put("/api/v1/notification-rules/1", json={"level": "daily"},
                          headers=_admin_headers())
        assert resp.status_code != 422
