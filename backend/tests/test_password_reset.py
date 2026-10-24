"""管理员重置密码 + 忘记密码申请 API 测试 (卡 922b2fba)

覆盖: 临时密码生成/一次性返回 / 显式密码策略(72字节) / 旧会话驱逐 /
租户归属校验 / 忘记密码不泄露账号存在性 / 申请列表与处理权限。
"""
from app.models.user import UserRole
from tests.conftest import _get_token
from tests._test_helpers import _fast_hash


def _seed_team_user(client, username="reset_eng", team_code="RESET_TEAM"):
    from app.models.user import Team, User
    from app.models.tenant import Tenant
    s = client._sesh
    tenant = s.query(Tenant).filter(Tenant.code == team_code).first()
    if not tenant:
        tenant = Tenant(name="重置租户", code=team_code)
        s.add(tenant)
        s.commit()
    team = s.query(Team).filter(Team.code == team_code).first()
    if not team:
        team = Team(name="重置团队", code=team_code)
        s.add(team)
        s.commit()
    user = s.query(User).filter(User.username == username).first()
    if not user:
        user = User(username=username, password_hash=_fast_hash("oldpass123"),
                    real_name="被重置用户", role=UserRole.ENGINEER, status="active",
                    team_id=team.id)
        s.add(user)
        s.commit()
    return user, team, tenant


# ─── 管理员重置密码 ───

def test_reset_password_generates_temporary(client):
    user, _, _ = _seed_team_user(client)
    r = client.post(f"/api/v1/users/{user.id}/reset-password", json={})
    assert r.status_code == 200
    temp = r.json()["data"]["temporary_password"]
    assert isinstance(temp, str) and len(temp) == 12
    # 旧密码失效, 临时密码可登录
    assert _get_token(client, user.username, "oldpass123") == ""
    assert _get_token(client, user.username, temp) != ""


def test_reset_password_explicit(client):
    user, _, _ = _seed_team_user(client)
    r = client.post(f"/api/v1/users/{user.id}/reset-password",
                    json={"new_password": "NewPass123456"})
    assert r.status_code == 200
    assert "temporary_password" not in r.json()["data"]
    assert _get_token(client, user.username, "NewPass123456") != ""
    assert _get_token(client, user.username, "oldpass123") == ""


def test_reset_password_rejects_over_72_bytes(client):
    user, _, _ = _seed_team_user(client)
    r = client.post(f"/api/v1/users/{user.id}/reset-password",
                    json={"new_password": "x" * 73})
    assert r.status_code == 400


def test_reset_password_non_admin_403(client):
    user, _, _ = _seed_team_user(client)
    client.post("/api/v1/users", json={
        "username": "plain_eng", "password": "eng123456",
        "role": "engineer",
    })
    token = _get_token(client, "plain_eng", "eng123456")
    assert token
    r = client.post(f"/api/v1/users/{user.id}/reset-password", json={},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_reset_password_user_not_found(client):
    r = client.post("/api/v1/users/999999/reset-password", json={})
    assert r.status_code == 404


def test_reset_password_revokes_old_token(client):
    user, _, _ = _seed_team_user(client)
    old_token = _get_token(client, user.username, "oldpass123")
    assert old_token
    r = client.post(f"/api/v1/users/{user.id}/reset-password", json={})
    assert r.status_code == 200
    # 改密后旧 access token 立即失效 (token_version 驱逐)
    r = client.get(f"/api/v1/users/{user.id}",
                   headers={"Authorization": f"Bearer {old_token}"})
    assert r.status_code == 401


def test_tenant_reset_password_ok(client):
    user, team, tenant = _seed_team_user(client)
    r = client.post(f"/api/v1/tenants/{tenant.id}/users/{user.id}/reset-password", json={})
    assert r.status_code == 200
    assert len(r.json()["data"]["temporary_password"]) == 12


def test_tenant_reset_password_wrong_tenant_404(client):
    from app.models.tenant import Tenant
    user, _, tenant = _seed_team_user(client)
    other = Tenant(name="其它租户", code="OTHER_RESET")
    client._sesh.add(other)
    client._sesh.commit()
    r = client.post(f"/api/v1/tenants/{other.id}/users/{user.id}/reset-password", json={})
    assert r.status_code == 404


# ─── 忘记密码 ───

def test_forgot_password_uniform_response(anon_client):
    r1 = anon_client.post("/api/v1/auth/forgot-password", json={"account": "admin"})
    r2 = anon_client.post("/api/v1/auth/forgot-password", json={"account": "no_such_user_xyz"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["message"] == r2.json()["data"]["message"]
    # 申请已落库
    from app.models.password_reset_request import PasswordResetRequest
    rows = anon_client._sesh.query(PasswordResetRequest).filter(
        PasswordResetRequest.account == "no_such_user_xyz").all()
    assert len(rows) == 1
    assert rows[0].status == "pending"


def test_forgot_password_requests_admin_list_and_resolve(client):
    from app.models.password_reset_request import PasswordResetRequest
    s = client._sesh
    s.add(PasswordResetRequest(account="someuser"))
    s.commit()
    req_id = s.query(PasswordResetRequest).first().id

    # 非 admin 403
    client.post("/api/v1/users", json={
        "username": "plain_eng2", "password": "eng123456", "role": "engineer"})
    token = _get_token(client, "plain_eng2", "eng123456")
    r = client.get("/api/v1/auth/forgot-password/requests",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403

    # admin 列表 + 处理
    r = client.get("/api/v1/auth/forgot-password/requests")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert any(i["account"] == "someuser" for i in items)

    r = client.post(f"/api/v1/auth/forgot-password/requests/{req_id}/resolve")
    assert r.status_code == 200
    s.expire_all()
    row = s.query(PasswordResetRequest).filter(PasswordResetRequest.id == req_id).first()
    assert row.status == "resolved"
    assert row.handled_by is not None


def test_forgot_password_requests_anonymous_401(anon_client):
    r = anon_client.get("/api/v1/auth/forgot-password/requests")
    assert r.status_code == 401
