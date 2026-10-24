"""
health 管道/网关遥测 admin-only 守卫测试 (卡 185e5a04)

/pipeline/health /pipeline/stats /gateway/health 是平台级基建遥测
(进程级全局单例指标, 无 team 维度), 团队级登录用户 → 403; admin → 200。
/live /ready /ping 等公共探针不在本测试范围 (保持公开)。
"""
import bcrypt
from app.models.user import User, UserRole

PWD = "hpg185"

ENDPOINTS = [
    "/api/v1/pipeline/health",
    "/api/v1/pipeline/stats",
    "/api/v1/gateway/health",
]


class TestPipelineTelemetryPlatformAdminGuard:

    def test_team_user_403(self, client):
        s = client._sesh
        s.add(User(username="hpg185_eng", real_name="团队级用户", role=UserRole.ENGINEER,
                   status="active",
                   password_hash=bcrypt.hashpw(PWD.encode(), bcrypt.gensalt()).decode()))
        s.commit()
        r = client.post("/api/v1/auth/login", data={"username": "hpg185_eng", "password": PWD})
        assert r.status_code == 200, r.text
        tok = r.json()["data"]["token"]
        for ep in ENDPOINTS:
            resp = client.get(ep, headers={"Authorization": f"Bearer {tok}"})
            assert resp.status_code == 403, f"{ep} -> {resp.status_code} {resp.text}"

    def test_admin_200(self, client):
        for ep in ENDPOINTS:  # client 默认 admin token
            resp = client.get(ep)
            assert resp.status_code == 200, f"{ep} -> {resp.status_code} {resp.text}"
