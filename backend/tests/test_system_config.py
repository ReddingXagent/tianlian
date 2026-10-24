"""
系统配置 API 测试
覆盖: 权限配置、通知配置、日志审计
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta


def _get_token(client, username="admin", password="admin123"):
    """获取认证 token；测试环境 login 应稳定可用，失败直接 fail 以暴露真实问题。"""
    resp = client.post("/api/v1/auth/login", data={
        "username": username,
        "password": password,
    })
    assert resp.status_code == 200, f"login 失败 status={resp.status_code} body={resp.text}"
    data = resp.json()
    token = (data.get("data", {}).get("token") or data.get("token")
             or data.get("data", {}).get("access_token") or data.get("access_token"))
    assert token, f"login 响应未含 token: {data}"
    return token


class TestPermissionConfig:
    """权限配置测试"""

    def test_get_permission_tree(self, client, seed_users):
        """测试获取权限树形结构"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/permissions/tree", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        tree = data["data"]["tree"]
        assert isinstance(tree, list)
        # 验证树结构包含预期资源
        resources = [item["resource"] for item in tree]
        assert "device" in resources
        assert "workorder" in resources
        assert "alarm" in resources
        assert "station" in resources
        assert "user" in resources
        assert "report" in resources
        assert "audit" in resources
        assert "system" in resources

    def test_list_permissions(self, client, seed_users):
        """测试获取权限平铺列表"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/permissions/list", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        items = data["data"]["items"]
        assert isinstance(items, list)
        assert len(items) > 0
        # 验证每个权限有必要字段
        for item in items:
            assert "name" in item
            assert "resource" in item
            assert "action" in item
            assert "label" in item

    def test_list_roles(self, client, seed_users):
        """测试获取角色列表"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/roles", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        items = data["data"]["items"]
        assert isinstance(items, list)
        assert len(items) >= 5  # 至少5个系统内置角色

    def test_get_role_detail(self, client, seed_users):
        """测试获取角色详情"""
        token = _get_token(client)
        # 先获取角色列表找到一个角色ID
        list_resp = client.get("/api/v1/system-config/roles", headers={
            "Authorization": f"Bearer {token}"
        })
        roles = list_resp.json()["data"]["items"]
        assert roles, "种子 roles 缺失"
        role_id = roles[0]["id"]
        response = client.get(f"/api/v1/system-config/roles/{role_id}", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        role = data["data"]
        assert role["id"] == role_id
        assert "permissions" in role

    def test_create_role(self, client, seed_users):
        """测试创建自定义角色"""
        token = _get_token(client)
        response = client.post("/api/v1/system-config/roles", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "name": "test_role_custom",
            "display_name": "测试自定义角色",
            "description": "测试用自定义角色",
            "permissions": ["device:view", "workorder:view"]
        })
        assert response.status_code in (200, 201)
        data = response.json()
        assert "data" in data
        assert data["data"]["name"] == "test_role_custom"

    def test_update_role(self, client, seed_users):
        """测试更新角色"""
        token = _get_token(client)
        # 先创建一个角色
        create_resp = client.post("/api/v1/system-config/roles", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "name": "test_role_update",
            "display_name": "待更新角色",
            "description": "测试更新",
            "permissions": ["device:view"]
        })
        assert create_resp.status_code in (200, 201)
        role_id = create_resp.json()["data"]["id"]

        # 更新角色
        response = client.put(f"/api/v1/system-config/roles/{role_id}", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "display_name": "已更新角色",
            "permissions": ["device:view", "device:create"]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["display_name"] == "已更新角色"
        assert "device:create" in data["data"]["permissions"]

    def test_delete_role(self, client, seed_users):
        """测试删除角色"""
        token = _get_token(client)
        # 先创建一个角色
        create_resp = client.post("/api/v1/system-config/roles", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "name": "test_role_delete",
            "display_name": "待删除角色",
            "description": "测试删除",
            "permissions": ["device:view"]
        })
        assert create_resp.status_code in (200, 201)
        role_id = create_resp.json()["data"]["id"]

        # 删除角色
        response = client.delete(f"/api/v1/system-config/roles/{role_id}", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200

    def test_delete_system_role_fails(self, client, seed_users):
        """测试删除系统内置角色应失败"""
        token = _get_token(client)
        # 获取系统角色
        list_resp = client.get("/api/v1/system-config/roles", headers={
            "Authorization": f"Bearer {token}"
        })
        roles = list_resp.json()["data"]["items"]
        system_role = next((r for r in roles if r["is_system"]), None)
        assert system_role, "系统角色缺失"
        response = client.delete(f"/api/v1/system-config/roles/{system_role['id']}", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 400

    def test_list_users_with_roles(self, client, seed_users):
        """测试获取用户列表（含角色权限）"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/users", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        items = data["data"]["items"]
        assert isinstance(items, list)
        assert len(items) > 0
        for item in items:
            assert "username" in item
            assert "role" in item
            assert "permissions" in item

    def test_list_users_pagination(self, client, seed_users):
        """测试用户列表分页（卡51923d3c）：页大小生效、total=全量、跨页不重复"""
        from app.models.user import User
        s = client._sesh
        page_size = 3
        extra = [
            User(username=f"pguser_{i}", password_hash="x",
                 real_name=f"分页用户{i}", role="viewer", status="active")
            for i in range(5)
        ]
        s.add_all(extra)
        s.commit()

        token = _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        p1 = client.get("/api/v1/system-config/users",
                        headers=headers, params={"page": 1, "page_size": page_size})
        p2 = client.get("/api/v1/system-config/users",
                        headers=headers, params={"page": 2, "page_size": page_size})
        assert p1.status_code == 200
        assert p2.status_code == 200
        d1, d2 = p1.json()["data"], p2.json()["data"]

        expected_total = s.query(User).count()
        assert d1["total"] == expected_total
        assert d2["total"] == expected_total
        assert d1["page"] == 1 and d1["page_size"] == page_size
        assert d2["page"] == 2 and d2["page_size"] == page_size
        assert len(d1["items"]) == page_size
        # 全量超过一页时，第二页必须有内容且与第一页不重复
        assert expected_total > page_size
        assert len(d2["items"]) > 0
        ids1 = {u["id"] for u in d1["items"]}
        ids2 = {u["id"] for u in d2["items"]}
        assert not (ids1 & ids2), "第1页与第2页出现重复用户"

    def test_update_user_role(self, client, seed_users):
        """测试更新用户角色"""
        token = _get_token(client)
        # 获取一个非admin用户
        list_resp = client.get("/api/v1/system-config/users", headers={
            "Authorization": f"Bearer {token}"
        })
        users = list_resp.json()["data"]["items"]
        test_user = next((u for u in users if u["username"] != "admin"), None)
        assert test_user, "测试用户缺失"
        user_id = test_user["id"]
        original_role = test_user["role"]

        # 更新角色
        response = client.put(f"/api/v1/system-config/users/{user_id}/role", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "role": "operator" if original_role != "operator" else "viewer"
        })
        assert response.status_code == 200

    def test_check_permission(self, client, seed_users):
        """测试检查权限"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/check/device:view", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "permission" in data["data"]
        assert "allowed" in data["data"]
        assert "user_permissions" in data["data"]


class TestNotificationConfig:
    """通知配置测试"""

    def test_get_notification_switches(self, client, seed_users):
        """测试获取通知开关"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/notification/switches", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        switches = data["data"]
        assert "sms_on" in switches
        assert "email_on" in switches
        assert "app_push_on" in switches
        assert "im_b_on" in switches
        assert "im_on" in switches

    def test_update_notification_switches(self, client, seed_users):
        """测试更新通知开关"""
        token = _get_token(client)
        response = client.put("/api/v1/system-config/notification/switches", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "sms_on": True,
            "email_on": True,
            "app_push_on": False,
            "im_b_on": False,
            "im_on": False
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        switches = data["data"]
        assert switches["sms_on"] == True
        assert switches["email_on"] == True

    def test_update_notification_switches_partial(self, client, seed_users):
        """测试部分更新通知开关"""
        token = _get_token(client)
        # 先全部开启
        client.put("/api/v1/system-config/notification/switches", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "sms_on": True,
            "email_on": True,
            "app_push_on": True,
            "im_b_on": True,
            "im_on": True
        })
        # 只关闭短信
        response = client.put("/api/v1/system-config/notification/switches", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "sms_on": False
        })
        assert response.status_code == 200
        data = response.json()
        switches = data["data"]
        assert switches["sms_on"] == False
        # 其他应保持开启
        assert switches["email_on"] == True
        assert switches["app_push_on"] == True

    def test_get_default_notification_switches(self, client):
        """测试获取默认通知开关（无需认证）"""
        response = client.get("/api/v1/system-config/notification/switches/defaults")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        switches = data["data"]
        assert switches["sms_on"] == False
        assert switches["email_on"] == False
        assert switches["app_push_on"] == False

    def test_list_notification_templates(self, client, seed_users):
        """测试获取通知模板列表"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/notification/templates", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "items" in data["data"]
        assert "total" in data["data"]

    def test_create_notification_template(self, client, seed_users):
        """测试创建通知模板"""
        token = _get_token(client)
        response = client.post("/api/v1/system-config/notification/templates", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "name": "测试短信模板",
            "code": "test_sms_template",
            "channel": "sms",
            "event_type": "test_event",
            "subject": "测试主题",
            "content": "这是测试内容：{variable}",
            "variables": [{"name": "variable", "desc": "测试变量", "example": "test"}],
            "is_system": False
        })
        assert response.status_code in (200, 201)
        data = response.json()
        assert "data" in data
        assert data["data"]["name"] == "测试短信模板"

    def test_list_notification_rules(self, client, seed_users):
        """测试获取通知规则列表"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/notification/rules", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "items" in data["data"]
        assert "total" in data["data"]

    def test_create_notification_rule(self, client, seed_users):
        """测试创建通知规则"""
        token = _get_token(client)
        response = client.post("/api/v1/system-config/notification/rules", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "name": "测试通知规则",
            "scope_type": "tenant",
            "scope_id": 1,
            "channels": ["sms", "email"],
            "receivers": ["user1"],
            "receiver_roles": ["admin", "operator"],
            "trigger_events": ["workorder_dispatch", "alarm_trigger"],
            "quiet_start": "22:00",
            "quiet_end": "08:00",
            "timezone": "Asia/Shanghai",
            "rate_limit_per_hour": 10,
            "rate_limit_per_day": 50,
            "enabled": True,
            "priority": 5
        })
        assert response.status_code in (200, 201)
        data = response.json()
        assert "data" in data
        assert data["data"]["name"] == "测试通知规则"


class TestAuditLog:
    """日志审计测试"""

    def test_list_audit_logs(self, client, seed_users):
        """测试获取审计日志列表"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/audit/logs", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "items" in data["data"]
        assert "total" in data["data"]
        assert "page" in data["data"]
        assert "page_size" in data["data"]

    def test_list_audit_logs_with_filters(self, client, seed_users):
        """测试带过滤条件获取审计日志"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/audit/logs", headers={
            "Authorization": f"Bearer {token}"
        }, params={
            "action": "login",
            "module": "auth",
            "result": "success",
            "page": 1,
            "page_size": 10
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_get_audit_log_stats(self, client, seed_users):
        """测试获取审计日志统计"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/audit/logs/stats", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        stats = data["data"]
        assert "total_logs" in stats
        assert "today_logs" in stats
        assert "failed_logs" in stats
        assert "by_action" in stats
        assert "by_module" in stats

    def test_export_audit_logs_json(self, client, seed_users):
        """测试导出审计日志（JSON格式）"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/audit/logs/export", headers={
            "Authorization": f"Bearer {token}"
        }, params={"format": "json"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        export_data = data["data"]
        assert "content" in export_data
        assert "filename" in export_data
        assert export_data["filename"].endswith(".json")

    def test_export_audit_logs_csv(self, client, seed_users):
        """测试导出审计日志（CSV格式）"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/audit/logs/export", headers={
            "Authorization": f"Bearer {token}"
        }, params={"format": "csv"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        export_data = data["data"]
        assert "content" in export_data
        assert "filename" in export_data
        assert export_data["filename"].endswith(".csv")
        assert export_data["content_type"] == "text/csv"

    def test_get_audit_actions(self, client, seed_users):
        """测试获取审计动作列表"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/audit/actions", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        actions = data["data"]["actions"]
        assert isinstance(actions, list)
        assert "login" in actions
        assert "create" in actions
        assert "update" in actions
        assert "delete" in actions

    def test_get_audit_modules(self, client, seed_users):
        """测试获取审计模块列表"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/audit/modules", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        modules = data["data"]["modules"]
        assert isinstance(modules, list)
        assert "auth" in modules
        assert "devices" in modules
        assert "workorders" in modules


class TestBackwardCompatibility:
    """向后兼容性测试"""

    def test_old_notification_switches_get(self, client, seed_users):
        """测试旧版获取通知开关接口"""
        token = _get_token(client)
        response = client.get("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        switches = data["data"]
        assert "sms_on" in switches
        assert "email_on" in switches
        assert "app_push_on" in switches

    def test_old_notification_switches_put(self, client, seed_users):
        """测试旧版更新通知开关接口"""
        token = _get_token(client)
        response = client.put("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "sms_on": True,
            "email_on": False,
            "app_push_on": True
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_old_notification_switches_defaults(self, client):
        """测试旧版获取默认通知开关接口"""
        response = client.get("/api/v1/system-config/notification-switches/defaults")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data


# ═══════════════════════════════════════════════════════════
# 全局配置 / 支付通道 / 发票配置测试 (admin spec §2.3)
# ═══════════════════════════════════════════════════════════

class TestGlobalConfig:
    """全局配置测试"""

    def test_get_global_config(self, client, seed_users):
        """测试获取全局配置（默认值）"""
        token = _get_token(client)
        resp = client.get("/api/v1/system-config/global", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "system_name" in data
        assert "logo_url" in data
        assert "copyright" in data
        assert "login_bg_url" in data
        assert "language" in data

    def test_update_global_config(self, client, seed_users):
        """测试更新全局配置"""
        token = _get_token(client)
        resp = client.put("/api/v1/system-config/global", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "system_name": "测试平台",
            "language": "en-US",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["system_name"] == "测试平台"
        assert data["language"] == "en-US"

    def test_update_global_config_partial(self, client, seed_users):
        """测试部分更新全局配置"""
        token = _get_token(client)
        # 先更新一次
        client.put("/api/v1/system-config/global", headers={
            "Authorization": f"Bearer {token}"
        }, json={"system_name": "A", "copyright": "C"})
        # 再部分更新
        resp = client.put("/api/v1/system-config/global", headers={
            "Authorization": f"Bearer {token}"
        }, json={"system_name": "B"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["system_name"] == "B"
        # copyright 应该保持上次更新的值
        assert data["copyright"] == "C"

    def test_get_global_config_after_update(self, client, seed_users):
        """测试更新后重新获取全局配置"""
        token = _get_token(client)
        client.put("/api/v1/system-config/global", headers={
            "Authorization": f"Bearer {token}"
        }, json={"logo_url": "https://example.com/logo.png"})
        resp = client.get("/api/v1/system-config/global", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["logo_url"] == "https://example.com/logo.png"


class TestPaymentChannels:
    """支付通道配置测试"""

    def test_list_empty_channels(self, client, seed_users):
        """测试获取空支付通道列表"""
        token = _get_token(client)
        resp = client.get("/api/v1/system-config/payment-channels", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert isinstance(data["items"], list)

    def test_create_payment_channel(self, client, seed_users):
        """测试创建支付通道"""
        token = _get_token(client)
        resp = client.post("/api/v1/system-config/payment-channels", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "name": "IM-B支付",
            "channel_type": "im_b",
            "config": {"mch_id": "1234567890"},
            "api_key": "wx_key",
            "api_secret": "wx_secret",
            "enabled": True,
            "sort_order": 1,
        })
        assert resp.status_code in (200, 201)
        data = resp.json()["data"]
        assert data["name"] == "IM-B支付"
        assert data["channel_type"] == "im_b"
        assert data["id"] > 0

    def test_list_after_create(self, client, seed_users):
        """测试创建后获取列表"""
        token = _get_token(client)
        client.post("/api/v1/system-config/payment-channels", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "name": "支付宝",
            "channel_type": "alipay",
            "enabled": True,
        })
        resp = client.get("/api/v1/system-config/payment-channels", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1

    def test_update_payment_channel(self, client, seed_users):
        """测试更新支付通道"""
        token = _get_token(client)
        # 创建
        create_resp = client.post("/api/v1/system-config/payment-channels", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "name": "银联",
            "channel_type": "unionpay",
            "enabled": True,
        })
        ch_id = create_resp.json()["data"]["id"]
        # 更新
        resp = client.put(f"/api/v1/system-config/payment-channels/{ch_id}", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "name": "银联支付",
            "enabled": False,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "银联支付"
        assert data["enabled"] == False

    def test_delete_payment_channel(self, client, seed_users):
        """测试删除支付通道"""
        token = _get_token(client)
        # 创建
        create_resp = client.post("/api/v1/system-config/payment-channels", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "name": "对公转账",
            "channel_type": "bank_transfer",
            "enabled": True,
        })
        ch_id = create_resp.json()["data"]["id"]
        # 删除
        resp = client.delete(f"/api/v1/system-config/payment-channels/{ch_id}", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        # 验证已删除
        list_resp = client.get("/api/v1/system-config/payment-channels", headers={
            "Authorization": f"Bearer {token}"
        })
        items = list_resp.json()["data"]["items"]
        assert all(c["id"] != ch_id for c in items)

    def test_update_nonexistent_channel(self, client, seed_users):
        """测试更新不存在的支付通道"""
        token = _get_token(client)
        resp = client.put("/api/v1/system-config/payment-channels/99999", headers={
            "Authorization": f"Bearer {token}"
        }, json={"name": "test"})
        assert resp.status_code == 404

    def test_delete_nonexistent_channel(self, client, seed_users):
        """测试删除不存在的支付通道"""
        token = _get_token(client)
        resp = client.delete("/api/v1/system-config/payment-channels/99999", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 404


class TestInvoiceConfig:
    """发票配置测试"""

    def test_get_invoice_config(self, client, seed_users):
        """测试获取发票配置（默认值）"""
        token = _get_token(client)
        resp = client.get("/api/v1/system-config/invoice", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "provider" in data
        assert "tax_rate" in data
        assert "company_name" in data
        assert "tax_number" in data

    def test_update_invoice_config(self, client, seed_users):
        """测试更新发票配置"""
        token = _get_token(client)
        resp = client.put("/api/v1/system-config/invoice", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "provider": "航天信息",
            "tax_rate": 13,
            "company_name": "测试科技有限公司",
            "tax_number": "91110000TEST12345",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["provider"] == "航天信息"
        assert data["tax_rate"] == 13
        assert data["company_name"] == "测试科技有限公司"

    def test_update_invoice_config_partial(self, client, seed_users):
        """测试部分更新发票配置"""
        token = _get_token(client)
        # 先更新一次
        client.put("/api/v1/system-config/invoice", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "company_name": "公司A",
            "bank_name": "银行A",
        })
        # 再部分更新
        resp = client.put("/api/v1/system-config/invoice", headers={
            "Authorization": f"Bearer {token}"
        }, json={"company_name": "公司B"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["company_name"] == "公司B"
        # bank_name 应保持上次更新的值
        assert data["bank_name"] == "银行A"

    def test_invoice_config_persistence(self, client, seed_users):
        """测试发票配置持久化"""
        token = _get_token(client)
        client.put("/api/v1/system-config/invoice", headers={
            "Authorization": f"Bearer {token}"
        }, json={
            "reviewer": "张三",
            "payer": "李四",
        })
        resp = client.get("/api/v1/system-config/invoice", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["reviewer"] == "张三"
        assert data["payer"] == "李四"