"""
垂直越权守卫测试 (卡 a3750a42)

覆盖 /api/v1/users 两个端点的角色升级缺口:
- create_user: 非平台管理员创建 admin/super_admin → 403; 平台管理员 → 200
- update_user: 无 user:role 权限改 role → 403; 普通字段编辑 → 200
- update_user: 平台管理员改 role=admin → 200
- update_user: 禁止自我提权 (即使持 user:role)
"""
import bcrypt

from app.models.user import User, UserRole, Team
from app.models.rbac import RoleTable, PermissionTable, user_role_table, role_permission_table


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _shared_team(session):
    # 卡 4b499911 后 update_user 有 team scoping (无 team 一律 404),
    # 编辑者与目标须同 team 才能触达 role 守卫逻辑
    t = session.query(Team).filter(Team.name == "a3750a42-team").first()
    if t is None:
        t = Team(name="a3750a42-team")
        session.add(t)
        session.flush()
    return t


def _make_user(session, username, role=UserRole.ENGINEER, team=None):
    if team is None:
        team = _shared_team(session)
    u = User(
        username=username,
        password_hash=_hash("pwd123456"),
        role=role,
        status="active",
        team_id=team.id if team else None,
    )
    session.add(u)
    session.flush()
    return u


def _grant(session, user, perm_names):
    """附加角色授予权限 (走 user_roles 关联, get_user_permissions 会合并)"""
    r = RoleTable(name=f"role_{user.username}", display_name=user.username, is_system=0)
    session.add(r)
    session.flush()
    for name in perm_names:
        p = session.query(PermissionTable).filter(PermissionTable.name == name).first()
        if p is None:
            p = PermissionTable(name=name, resource=name.split(":")[0], action=name.split(":")[1])
            session.add(p)
            session.flush()
        session.execute(
            role_permission_table.insert().values(role_id=r.id, permission_id=p.id)
        )
    session.execute(user_role_table.insert().values(user_id=user.id, role_id=r.id))
    session.commit()


def _login(client, username, password="pwd123456"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


class TestCreateUserRoleGuard:
    def test_non_admin_cannot_create_admin(self, client):
        u = _make_user(client._sesh, "escalator1")
        _grant(client._sesh, u, ["user:create"])
        token = _login(client, "escalator1")
        r = client.post(
            "/api/v1/users",
            json={"username": "pawn1", "password": "pwd123456", "role": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        assert "仅平台管理员" in r.json()["detail"]

    def test_non_admin_can_create_normal_role(self, client):
        u = _make_user(client._sesh, "escalator2")
        _grant(client._sesh, u, ["user:create"])
        token = _login(client, "escalator2")
        r = client.post(
            "/api/v1/users",
            json={"username": "pawn2", "password": "pwd123456", "role": "viewer"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["role"] == "viewer"

    def test_platform_admin_can_create_admin(self, client):
        # client 默认 admin token
        r = client.post(
            "/api/v1/users",
            json={"username": "newadmin", "password": "pwd123456", "role": "admin"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["role"] == "admin"


class TestUpdateUserRoleGuard:
    def test_user_edit_without_user_role_cannot_change_role(self, client):
        u = _make_user(client._sesh, "editor1")
        _grant(client._sesh, u, ["user:edit"])
        target = _make_user(client._sesh, "target1", role=UserRole.VIEWER)
        token = _login(client, "editor1")
        r = client.put(
            f"/api/v1/users/{target.id}",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_non_admin_cannot_change_role_without_user_edit_perm(self, client):
        # 有 user:edit 才进得了端点; 无 user:edit → 403 (require_permission)
        _make_user(client._sesh, "plain1")
        target = _make_user(client._sesh, "target2", role=UserRole.VIEWER)
        token = _login(client, "plain1")
        r = client.put(
            f"/api/v1/users/{target.id}",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_plain_field_edit_still_works(self, client):
        u = _make_user(client._sesh, "editor2")
        _grant(client._sesh, u, ["user:edit"])
        target = _make_user(client._sesh, "target3", role=UserRole.VIEWER)
        token = _login(client, "editor2")
        r = client.put(
            f"/api/v1/users/{target.id}",
            json={"real_name": "新名字", "phone": "13800000000"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["real_name"] == "新名字"

    def test_platform_admin_can_change_role_to_admin(self, client):
        target = _make_user(client._sesh, "target4", role=UserRole.VIEWER)
        r = client.put(f"/api/v1/users/{target.id}", json={"role": "admin"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["role"] == "admin"

    def test_user_role_holder_cannot_elevate_self(self, client):
        u = _make_user(client._sesh, "editor3", role=UserRole.ENGINEER)
        _grant(client._sesh, u, ["user:edit", "user:role"])
        token = _login(client, "editor3")
        r = client.put(
            f"/api/v1/users/{u.id}",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_user_role_holder_can_change_others_role(self, client):
        u = _make_user(client._sesh, "editor4", role=UserRole.ENGINEER)
        _grant(client._sesh, u, ["user:edit", "user:role"])
        target = _make_user(client._sesh, "target5", role=UserRole.VIEWER)
        token = _login(client, "editor4")
        r = client.put(
            f"/api/v1/users/{target.id}",
            json={"role": "dispatcher"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["role"] == "dispatcher"
