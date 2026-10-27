"""
auth 响应 team_type/team_id 回填测试 (卡 6c5d28fa)

背景: cf614348 建 Team.type(scope 矩阵) 后, /auth/me + /auth/login 响应未回填
team_type/team_id, 致前端 resolveTeamType 走兜底链, maintenance_team 工程师
被误判为 ops_company。本套测试驱动两个端点 + JWT claims 正确回填, 让前端
不再靠兜底猜。
"""
import bcrypt
from app.core.jwt_utils import decode_token
from app.models.user import User, UserRole, Team, TeamType


def _seed_team_user(session, username, team_name, team_type=TeamType.MAINTENANCE_TEAM):
    """seed 一个 team + 挂在其下的工程师, 返回 (team, user)。"""
    team = Team(name=team_name, type=team_type)
    session.add(team)
    session.commit()
    session.refresh(team)
    user = User(
        username=username,
        password_hash=bcrypt.hashpw(b"mt123", bcrypt.gensalt()).decode(),
        real_name=username,
        role=UserRole.ENGINEER,
        status="active",
        team_id=team.id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return team, user


class TestLoginTeamFields:
    """/auth/login 响应必须回填 team_type/team_id。"""

    def test_login_admin_team_null(self, client):
        """admin 无 team → team_type/team_id 为 null (前端不报错)。"""
        resp = client.post("/api/v1/auth/login", data={
            "username": "admin",
            "password": "admin123",
        })
        assert resp.status_code == 200, resp.text
        user = resp.json()["data"]["user"]
        assert "team_type" in user, "login 响应 user 缺 team_type"
        assert "team_id" in user, "login 响应 user 缺 team_id"
        assert user["team_type"] is None
        assert user["team_id"] is None

    def test_login_maintenance_team_user(self, client, db_session):
        """maintenance_team 工程师登录 → team_type/team_id 正确回填, 不走兜底。"""
        team, user = _seed_team_user(db_session, "mt_engineer", "运维一队")
        resp = client.post("/api/v1/auth/login", data={
            "username": "mt_engineer",
            "password": "mt123",
        })
        assert resp.status_code == 200, resp.text
        u = resp.json()["data"]["user"]
        assert u["team_type"] == "maintenance_team"
        assert u["team_id"] == team.id


class TestMeTeamFields:
    """/auth/me 响应必须回填 team_type/team_id。"""

    def test_me_admin_team_null(self, client):
        """admin /me → team_type/team_id 为 null。"""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        assert "team_type" in d, "/me 响应缺 team_type"
        assert "team_id" in d, "/me 响应缺 team_id"
        assert d["team_type"] is None
        assert d["team_id"] is None

    def test_me_maintenance_team_user(self, client, db_session):
        """maintenance_team 工程师 /me → team_type/team_id 正确回填。"""
        team, user = _seed_team_user(db_session, "mt_engineer2", "运维二队")
        # 该用户登录拿 token
        resp = client.post("/api/v1/auth/login", data={
            "username": "mt_engineer2",
            "password": "mt123",
        })
        assert resp.status_code == 200
        token = resp.json()["data"]["token"]

        resp2 = client.get("/api/v1/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp2.status_code == 200, resp2.text
        d = resp2.json()["data"]
        assert d["team_type"] == "maintenance_team"
        assert d["team_id"] == team.id


class TestLoginJwtClaims:
    """login 签发的 JWT claims 应含 team_type (前端可从 token 直接取, 免二次拉取)。"""

    def test_jwt_claims_team_type_present(self, client, db_session):
        team, user = _seed_team_user(db_session, "mt_engineer3", "运维三队")
        resp = client.post("/api/v1/auth/login", data={
            "username": "mt_engineer3",
            "password": "mt123",
        })
        assert resp.status_code == 200
        token = resp.json()["data"]["token"]
        payload = decode_token(token)
        assert payload.get("team_type") == "maintenance_team"

    def test_jwt_claims_team_type_null_for_admin(self, client):
        """admin 无 team → JWT claims team_type 为 null (不能缺席键)。"""
        resp = client.post("/api/v1/auth/login", data={
            "username": "admin",
            "password": "admin123",
        })
        token = resp.json()["data"]["token"]
        payload = decode_token(token)
        assert "team_type" in payload
        assert payload["team_type"] is None
