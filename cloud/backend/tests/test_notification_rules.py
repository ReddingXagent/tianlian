"""
通知规则配置 API 测试
覆盖: CRUD + toggle切换
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


@pytest.fixture
def auth_token(test_db):
    """获取认证token"""
    response = client.post("/api/v1/auth/login", data={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return token


class TestNotificationRulesAPI:
    """通知规则配置 API 测试类"""

    # ========== CRUD ==========

    def test_list_rules_success(self, auth_token):
        """测试获取通知规则列表成功"""
        response = client.get("/api/v1/notification-rules", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        # 规则列表可能是空数组或包裹格式
        assert "data" in data

    def test_create_rule_success(self, auth_token):
        """测试创建通知规则成功"""
        response = client.post("/api/v1/notification-rules", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "name": "严重告警通知",
            "level": "critical",
            "channels": ["sms", "email", "im_b"],
            "receivers": ["admin", "ops_team"],
            "enabled": True
        })
        assert response.status_code == 200
        data = response.json()
        rule_data = data.get("data", data)
        assert rule_data.get("name") == "严重告警通知"
        assert rule_data.get("level") == "critical"

    def test_create_rule_minimal(self, auth_token):
        """测试创建通知规则最小字段"""
        response = client.post("/api/v1/notification-rules", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "name": "简单规则",
            "level": "warning"
        })
        assert response.status_code == 200
        data = response.json()
        rule_data = data.get("data", data)
        assert rule_data.get("name") == "简单规则"

    def test_get_rule_success(self, auth_token):
        """测试获取通知规则详情成功"""
        # 先创建规则
        create_resp = client.post("/api/v1/notification-rules", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "name": "测试规则详情",
            "level": "info"
        })
        rule_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        # 获取详情
        response = client.get(f"/api/v1/notification-rules/{rule_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        rule_data = data.get("data", data)
        assert rule_data.get("id") == rule_id

    def test_get_rule_not_found(self, auth_token):
        """测试获取通知规则不存在"""
        response = client.get("/api/v1/notification-rules/99999", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    def test_update_rule_success(self, auth_token):
        """测试更新通知规则成功"""
        # 先创建规则
        create_resp = client.post("/api/v1/notification-rules", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "name": "待更新规则",
            "level": "warning"
        })
        rule_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        # 更新
        response = client.put(f"/api/v1/notification-rules/{rule_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "name": "已更新规则",
            "level": "critical",
            "channels": ["sms"],
            "enabled": False
        })
        assert response.status_code == 200
        data = response.json()
        rule_data = data.get("data", data)
        assert rule_data.get("name") == "已更新规则"
        assert rule_data.get("level") == "critical"

    def test_update_rule_partial(self, auth_token):
        """测试部分更新通知规则"""
        # 先创建规则
        create_resp = client.post("/api/v1/notification-rules", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "name": "部分更新规则",
            "level": "info",
            "channels": ["email"]
        })
        rule_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        # 只更新channels
        response = client.put(f"/api/v1/notification-rules/{rule_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "channels": ["sms", "im_b"]
        })
        assert response.status_code == 200
        data = response.json()
        rule_data = data.get("data", data)
        assert rule_data.get("channels") == ["sms", "im_b"]
        # name和level保持不变
        assert rule_data.get("name") == "部分更新规则"

    def test_update_rule_not_found(self, auth_token):
        """测试更新通知规则不存在"""
        response = client.put("/api/v1/notification-rules/99999", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "name": "不存在"
        })
        assert response.status_code == 404

    def test_delete_rule_success(self, auth_token):
        """测试删除通知规则成功"""
        # 先创建规则
        create_resp = client.post("/api/v1/notification-rules", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "name": "待删除规则",
            "level": "info"
        })
        rule_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        # 删除
        response = client.delete(f"/api/v1/notification-rules/{rule_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_delete_rule_not_found(self, auth_token):
        """测试删除通知规则不存在"""
        response = client.delete("/api/v1/notification-rules/99999", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    # ========== Toggle切换 ==========

    def test_toggle_rule_success(self, auth_token):
        """测试切换规则启用状态"""
        # 先创建规则
        create_resp = client.post("/api/v1/notification-rules", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "name": "待切换规则",
            "level": "warning",
            "enabled": True
        })
        rule_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        # 切换
        response = client.put(f"/api/v1/notification-rules/{rule_id}/toggle", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        rule_data = data.get("data", data)
        # 原来是True，切换后应该是False
        assert rule_data.get("enabled") == False

        # 再切换一次
        response = client.put(f"/api/v1/notification-rules/{rule_id}/toggle", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        rule_data = data.get("data", data)
        assert rule_data.get("enabled") == True

    def test_toggle_rule_not_found(self, auth_token):
        """测试切换不存在规则的状态"""
        response = client.put("/api/v1/notification-rules/99999/toggle", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    # ========== 列表过滤 ==========

    def test_list_rules_after_create(self, auth_token):
        """测试创建后列表包含新规则"""
        # 创建多条规则
        for level in ["critical", "warning", "info"]:
            client.post("/api/v1/notification-rules", headers={
                "Authorization": f"Bearer {auth_token}"
            }, json={
                "name": f"{level}_rule",
                "level": level
            })

        # 获取列表
        response = client.get("/api/v1/notification-rules", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        rules = data.get("data", [])
        # 列表应该包含创建的规则
        assert len(rules) >= 3

# ========== 审计归属 (卡 3c751d01) ==========

class TestAuditAttributionCard3c751d01:
    """规则 CRUD 审计记录归属真实操作用户"""

    def _admin(self, s):
        from app.models.user import User
        return s.query(User).filter(User.username == "admin").first()

    def test_rule_audit_records_real_operator(self, auth_token):
        from app.models.audit_log import AuditLog
        import app.core.database as _dbmod
        s = _dbmod.SessionLocal()
        admin = self._admin(s)
        assert admin is not None and admin.id != 0

        resp = client.post("/api/v1/notification-rules", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"name": "审计归属规则", "level": "info", "channels": ["app_push"]})
        assert resp.status_code == 200
        rule_id = resp.json()["data"]["id"]

        log = (s.query(AuditLog)
               .filter(AuditLog.module == "notification_rules", AuditLog.action == "create",
                       AuditLog.target_id == str(rule_id))
               .order_by(AuditLog.id.desc()).first())
        assert log is not None, "规则创建应产生审计记录"
        assert log.user_id == admin.id
        assert log.username == admin.username

        resp = client.delete(f"/api/v1/notification-rules/{rule_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200
        log = (s.query(AuditLog)
               .filter(AuditLog.module == "notification_rules", AuditLog.action == "delete",
                       AuditLog.target_id == str(rule_id))
               .order_by(AuditLog.id.desc()).first())
        assert log is not None, "规则删除应产生审计记录"
        assert log.user_id == admin.id
        assert log.username == admin.username
