"""
系统配置-通知开关 API 测试
覆盖: GET/PUT /api/v1/system-config/notification-switches
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


class TestSystemConfigNotificationSwitches:
    """系统配置-通知开关 API 测试类"""

    def test_get_notification_switches_defaults(self):
        """测试获取默认通知开关（无需认证）"""
        response = client.get("/api/v1/system-config/notification-switches/defaults")
        assert response.status_code == 200
        data = response.json()
        # 解包后端响应格式
        switches = data.get("data", data)
        assert "sms_on" in switches
        assert "email_on" in switches
        assert "app_push_on" in switches
        assert switches["sms_on"] == False
        assert switches["email_on"] == False
        assert switches["app_push_on"] == False

    def test_get_notification_switches_authenticated(self, auth_token):
        """测试认证用户获取通知开关"""
        response = client.get("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        switches = data.get("data", data)
        assert "sms_on" in switches
        assert "email_on" in switches
        assert "app_push_on" in switches

    def test_get_notification_switches_unauthenticated(self):
        """测试未认证获取通知开关应返回401"""
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        response = client.get("/api/v1/system-config/notification-switches")
        assert response.status_code == 401

    def test_update_notification_switches_partial(self, auth_token):
        """测试部分更新通知开关"""
        # 先获取当前值
        get_resp = client.get("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert get_resp.status_code == 200

        # 部分更新：只开启短信
        response = client.put("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "sms_on": True
        })
        assert response.status_code == 200
        data = response.json()
        switches = data.get("data", data)
        assert switches.get("sms_on") == True
        # email_on 和 app_push_on 应保持原值（默认False）

    def test_update_notification_switches_all(self, auth_token):
        """测试全量更新通知开关"""
        response = client.put("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "sms_on": True,
            "email_on": True,
            "app_push_on": True
        })
        assert response.status_code == 200
        data = response.json()
        switches = data.get("data", data)
        assert switches.get("sms_on") == True
        assert switches.get("email_on") == True
        assert switches.get("app_push_on") == True

    def test_update_notification_switches_turn_off(self, auth_token):
        """测试关闭通知开关"""
        # 先开启所有
        client.put("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "sms_on": True,
            "email_on": True,
            "app_push_on": True
        })

        # 关闭短信
        response = client.put("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "sms_on": False
        })
        assert response.status_code == 200
        data = response.json()
        switches = data.get("data", data)
        assert switches.get("sms_on") == False
        # 其他保持开启
        assert switches.get("email_on") == True
        assert switches.get("app_push_on") == True

    def test_update_notification_switches_unauthenticated(self):
        """测试未认证更新通知开关应返回401"""
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        response = client.put("/api/v1/system-config/notification-switches", json={
            "sms_on": True
        })
        assert response.status_code == 401

    def test_notification_switches_persistence(self, auth_token):
        """测试通知开关持久化（多次获取一致性）"""
        # 设置为特定值
        client.put("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "sms_on": True,
            "email_on": False,
            "app_push_on": True
        })

        # 第一次获取
        resp1 = client.get("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        data1 = resp1.json().get("data", resp1.json())

        # 第二次获取
        resp2 = client.get("/api/v1/system-config/notification-switches", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        data2 = resp2.json().get("data", resp2.json())

        # 两次结果应一致
        assert data1["sms_on"] == data2["sms_on"]
        assert data1["email_on"] == data2["email_on"]
        assert data1["app_push_on"] == data2["app_push_on"]


class TestNotificationConfigsRouteOrder:
    """路由顺序回归：静态路径 /templates、/logs 不可被动态 /{config_id} 吞掉 [5627c6cb]"""

    def test_get_templates_route_returns_200(self):
        """GET /notification-configs/templates 必须命中 list_templates(200)，而非被 /{config_id} 当成 'templates' 走 int 解析(422)"""
        r = client.get("/api/v1/notification-configs/templates")
        assert r.status_code == 200

    def test_get_logs_route_returns_200(self):
        """GET /notification-configs/logs 同理不可被 /{config_id} 拦截成 422"""
        r = client.get("/api/v1/notification-configs/logs")
        assert r.status_code == 200

    def test_get_config_by_int_id_still_works(self):
        """回归：GET /notification-configs/{int_id} 动态路由仍正常工作"""
        created = client.post("/api/v1/notification-configs", json={
            "name": "route-order-test", "scope_type": "tenant",
        })
        assert created.status_code == 200
        cid = created.json()["data"]["id"]
        r = client.get(f"/api/v1/notification-configs/{cid}")
        assert r.status_code == 200
        assert r.json()["data"]["id"] == cid
