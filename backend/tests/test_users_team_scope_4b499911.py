"""
PUT /users/{user_id} team scoping 回归 (卡 4b499911)

复刻 engineers.py 卡 708350b3 模式:
- 非 platform admin 跨团队编辑用户 → 404 (不泄露存在)
- 非 platform admin 传 team_id → 静默弹出, team_id 不入库, 其余字段正常更新
- platform_admin 改 team_id → 200 成功
"""
import bcrypt

from app.models.user import User, UserRole, Team
from app.models.rbac import RoleTable, PermissionTable, user_role_table, role_permission_table


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _make_team(session, name):
    t = Team(name=name)
    session.add(t)
    session.flush()
    return t


def _make_user(session, username, role=UserRole.ENGINEER, team=None):
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


class TestUpdateUserTeamScope:
    def test_non_admin_cross_team_edit_returns_404(self, client):
        team_a = _make_team(client._sesh, "scope-team-a")
        team_b = _make_team(client._sesh, "scope-team-b")
        editor = _make_user(client._sesh, "scope-editor1", team=team_a)
        _grant(client._sesh, editor, ["user:edit"])
        target = _make_user(client._sesh, "scope-target1", role=UserRole.VIEWER, team=team_b)
        token = _login(client, "scope-editor1")
        r = client.put(
            f"/api/v1/users/{target.id}",
            json={"real_name": "越权修改"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_non_admin_team_id_dropped_other_fields_applied(self, client):
        team_a = _make_team(client._sesh, "scope-team-c")
        team_b = _make_team(client._sesh, "scope-team-d")
        editor = _make_user(client._sesh, "scope-editor2", team=team_a)
        _grant(client._sesh, editor, ["user:edit"])
        target = _make_user(client._sesh, "scope-target2", role=UserRole.VIEWER, team=team_a)
        token = _login(client, "scope-editor2")
        r = client.put(
            f"/api/v1/users/{target.id}",
            json={"team_id": team_b.id, "real_name": "合法改名"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["team_id"] == team_a.id
        assert r.json()["data"]["real_name"] == "合法改名"

    def test_platform_admin_can_change_team_id(self, client):
        team_a = _make_team(client._sesh, "scope-team-e")
        team_b = _make_team(client._sesh, "scope-team-f")
        target = _make_user(client._sesh, "scope-target3", role=UserRole.VIEWER, team=team_a)
        # client 默认 admin token (platform admin)
        r = client.put(f"/api/v1/users/{target.id}", json={"team_id": team_b.id})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["team_id"] == team_b.id
