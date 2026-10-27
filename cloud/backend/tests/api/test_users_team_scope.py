"""tests/api/test_users_team_scope.py — 用户列表/详情 team scope 越权 (卡 2d34e5c1)

缺陷 (修复前): users.py 中
- get_users 全量查询, 无 team 过滤 → 团队级用户可枚举所有团队用户
- get_user 按主键直查 → 团队级用户可看任意团队用户详情 (水平越权)

修复契约:
- 团队级用户: 列表仅本团队 (query team_id 被忽略); 跨团队详情 404
- admin/平台级: 保持全量, 可传 team_id 筛选
"""
import uuid

import bcrypt

from app.models.user import User, UserRole, EngineerLevel, Team
from tests.api._helpers import login_admin, login_as

PASS = "pass123"


def _uname(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:8]}"


def _make_team(s, name: str) -> Team:
    t = Team(name=name)
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def _add_user(s, username, *, team_id=None, role=UserRole.ENGINEER) -> User:
    u = User(
        username=username,
        password_hash=bcrypt.hashpw(PASS.encode(), bcrypt.gensalt()).decode(),
        real_name=username,
        role=role,
        level=EngineerLevel.JUNIOR,
        status="active",
        team_id=team_id,
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def _list_usernames(client, query: str = "") -> list:
    r = client.get(f"/api/v1/users{query}")
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    data = r.json()["data"]
    items = data.get("items", data) if isinstance(data, dict) else data
    return [u["username"] for u in items]


def test_team_user_list_only_own_team(client):
    """团队级用户: 列表仅本团队用户, 他团队用户不可见。"""
    s = client._sesh
    team_a, team_b = _make_team(s, "usr-scope-a"), _make_team(s, "usr-scope-b")
    mine = _add_user(s, _uname("mine"), team_id=team_a.id)
    other = _add_user(s, _uname("other"), team_id=team_b.id)
    me = _add_user(s, _uname("me"), team_id=team_a.id, role=UserRole.DISPATCHER)

    login_as(client, me.username, PASS)
    names = _list_usernames(client)
    assert mine.username in names
    assert me.username in names
    assert other.username not in names
    login_admin(client)


def test_team_user_list_ignores_team_id_param(client):
    """团队级用户: query 传他团队 team_id 被忽略, 仍仅本团队。"""
    s = client._sesh
    team_a, team_b = _make_team(s, "usr-scope-c"), _make_team(s, "usr-scope-d")
    other = _add_user(s, _uname("other"), team_id=team_b.id)
    me = _add_user(s, _uname("me"), team_id=team_a.id, role=UserRole.DISPATCHER)

    login_as(client, me.username, PASS)
    names = _list_usernames(client, f"?team_id={team_b.id}")
    assert other.username not in names
    assert me.username in names
    login_admin(client)


def test_admin_list_full_and_filterable(client):
    """admin/平台级: 全量可见, team_id 筛选生效 (现状不回归)。"""
    s = client._sesh
    team_a, team_b = _make_team(s, "usr-scope-e"), _make_team(s, "usr-scope-f")
    mine = _add_user(s, _uname("mine"), team_id=team_a.id)
    other = _add_user(s, _uname("other"), team_id=team_b.id)

    names = _list_usernames(client)
    assert mine.username in names
    assert other.username in names

    filtered = _list_usernames(client, f"?team_id={team_b.id}")
    assert other.username in filtered
    assert mine.username not in filtered


def test_team_user_cross_team_detail_404(client):
    """团队级用户: 跨团队用户详情 → 404 (不泄露存在)。"""
    s = client._sesh
    team_a, team_b = _make_team(s, "usr-scope-g"), _make_team(s, "usr-scope-h")
    other = _add_user(s, _uname("other"), team_id=team_b.id)
    me = _add_user(s, _uname("me"), team_id=team_a.id, role=UserRole.DISPATCHER)

    login_as(client, me.username, PASS)
    r = client.get(f"/api/v1/users/{other.id}")
    assert r.status_code == 404, f"跨团队详情应 404, 实际 {r.status_code}"
    login_admin(client)


def test_team_user_own_team_detail_200(client):
    """团队级用户: 本团队用户详情正常 200。"""
    s = client._sesh
    team_a = _make_team(s, "usr-scope-i")
    mine = _add_user(s, _uname("mine"), team_id=team_a.id)
    me = _add_user(s, _uname("me"), team_id=team_a.id, role=UserRole.DISPATCHER)

    login_as(client, me.username, PASS)
    r = client.get(f"/api/v1/users/{mine.id}")
    assert r.status_code == 200
    assert r.json()["data"]["username"] == mine.username
    login_admin(client)


def test_admin_cross_team_detail_200(client):
    """admin: 跨团队用户详情正常 200 (现状不回归)。"""
    s = client._sesh
    team_b = _make_team(s, "usr-scope-j")
    other = _add_user(s, _uname("other"), team_id=team_b.id)

    r = client.get(f"/api/v1/users/{other.id}")
    assert r.status_code == 200
    assert r.json()["data"]["username"] == other.username
