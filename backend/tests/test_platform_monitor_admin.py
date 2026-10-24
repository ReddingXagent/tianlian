"""
平台监控 admin-only 鉴权测试 (卡 820cf187)

/platform/topology 与 /platform/device-access-stats 是平台级基础设施视图,
非 admin (engineer/viewer/operator) → 403; admin → 200; 未登录 401。
"""
import bcrypt
from app.models.user import User, UserRole

PWD = "pltmon82"


class TestPlatformMonitorAdminOnly:

    def test_non_admin_topology_403(self, client, seed_users):
        # seed_users 里 engineer1 密码即其用户名同名密码? 不确定 → 直接建一个非 admin 用户
        s = client._sesh
        s.add(User(username="pm82_eng", real_name="非管理员", role=UserRole.ENGINEER,
                   status="active",
                   password_hash=bcrypt.hashpw(PWD.encode(), bcrypt.gensalt()).decode()))
        s.commit()
        r = client.post("/api/v1/auth/login", data={"username": "pm82_eng", "password": PWD})
        assert r.status_code == 200, r.text
        tok = r.json()["data"]["token"]
        resp = client.get("/api/v1/platform/topology",
                          headers={"Authorization": f"Bearer {tok}"})
        assert resp.status_code == 403, resp.text

    def test_non_admin_device_access_403(self, client):
        s = client._sesh
        s.add(User(username="pm82_eng2", real_name="非管理员2", role=UserRole.ENGINEER,
                   status="active",
                   password_hash=bcrypt.hashpw(PWD.encode(), bcrypt.gensalt()).decode()))
        s.commit()
        r = client.post("/api/v1/auth/login", data={"username": "pm82_eng2", "password": PWD})
        tok = r.json()["data"]["token"]
        resp = client.get("/api/v1/platform/device-access-stats",
                          headers={"Authorization": f"Bearer {tok}"})
        assert resp.status_code == 403, resp.text

    def test_admin_topology_200(self, client):
        resp = client.get("/api/v1/platform/topology")  # client 默认 admin token
        assert resp.status_code == 200, resp.text

    def test_admin_device_access_200(self, client):
        resp = client.get("/api/v1/platform/device-access-stats")
        assert resp.status_code == 200, resp.text

    def test_anon_topology_401(self, anon_client):
        resp = anon_client.get("/api/v1/platform/topology")
        assert resp.status_code in (401, 403)
