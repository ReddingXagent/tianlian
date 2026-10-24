"""
teams.py 越权收紧回归测试 (卡 85deafc4 / 审计 #3)

修复前: router 级 require_role("admin","operator") 导致 operator 可
创建/改/删任意团队(含级联删除)、把任意用户移入任意团队、枚举任意团队 PII。

修复后契约:
  - 团队写操作 (创建/更新/删除/成员添加/成员移除) → platform admin only,
    operator → 403
  - 团队列表/详情/成员列表 → operator 仅可见本队 (team_id 匹配),
    跨队 → 404 (assert_team_access 既有约定, 不泄露存在)
  - platform admin (admin) 全通
"""
import bcrypt
import pytest

from app.models.user import User, UserRole, Team


@pytest.fixture
def teams_env(client):
    """seed 两个团队 + 本队 operator + 他队成员 + 独立 admin 账号"""
    s = client._sesh

    team_a = Team(name="卡85deafc4_A队", type="ops_company")
    team_b = Team(name="卡85deafc4_B队", type="ops_company")
    s.add_all([team_a, team_b])
    s.flush()

    op = User(
        username="iso_op_85deafc4",
        password_hash=bcrypt.hashpw(b"op123456", bcrypt.gensalt()).decode(),
        real_name="本队operator",
        role=UserRole.OPERATOR,
        team_id=team_a.id,
        status="active",
        phone="13800000001",
    )
    other = User(
        username="iso_other_85deafc4",
        password_hash=bcrypt.hashpw(b"other123", bcrypt.gensalt()).decode(),
        real_name="他队成员",
        role=UserRole.ENGINEER,
        team_id=team_b.id,
        status="active",
        phone="13800000002",
    )
    s.add_all([op, other])
    s.commit()
    yield client, team_a.id, team_b.id, op.id, other.id


def _login(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["data"]["token"]


def _hdr(client, username="admin", password="admin123"):
    return {"Authorization": f"Bearer {_login(client, username, password)}"}


OP_USER = ("iso_op_85deafc4", "op123456")


# ===== operator 写操作 → 403 =====

def test_operator_cannot_create_team(teams_env):
    client, _, _, _, _ = teams_env
    r = client.post("/api/v1/teams", json={"name": "op新建队"},
                    headers=_hdr(client, *OP_USER))
    assert r.status_code == 403, f"operator 建团队未拒: {r.status_code} {r.text}"


def test_operator_cannot_update_other_team(teams_env):
    client, _, tb, _, _ = teams_env
    r = client.put(f"/api/v1/teams/{tb}", json={"name": "op改队"},
                   headers=_hdr(client, *OP_USER))
    assert r.status_code == 403, f"operator 改他队未拒: {r.status_code} {r.text}"


def test_operator_cannot_delete_other_team(teams_env):
    client, _, tb, _, _ = teams_env
    r = client.delete(f"/api/v1/teams/{tb}", headers=_hdr(client, *OP_USER))
    assert r.status_code == 403, f"operator 删他队未拒: {r.status_code} {r.text}"


def test_operator_cannot_move_admin_user_into_team(teams_env):
    client, ta, _, _, _ = teams_env
    r = client.post(f"/api/v1/teams/{ta}/members", json={"user_id": 1},
                    headers=_hdr(client, *OP_USER))
    assert r.status_code == 403, f"operator 移动用户未拒: {r.status_code} {r.text}"


def test_operator_cannot_remove_member(teams_env):
    client, tb, _, _, other_id = teams_env
    r = client.delete(f"/api/v1/teams/{tb}/members/{other_id}",
                      headers=_hdr(client, *OP_USER))
    assert r.status_code == 403, f"operator 移除成员未拒: {r.status_code} {r.text}"


# ===== operator 读: 本队 200 / 跨队 404 =====

def test_operator_reads_own_team_members(teams_env):
    client, ta, _, _, _ = teams_env
    r = client.get(f"/api/v1/teams/{ta}/members", headers=_hdr(client, *OP_USER))
    assert r.status_code == 200, r.text


def test_operator_reads_own_team_detail(teams_env):
    client, ta, _, _, _ = teams_env
    r = client.get(f"/api/v1/teams/{ta}", headers=_hdr(client, *OP_USER))
    assert r.status_code == 200, r.text


def test_operator_cannot_read_other_team_members_pii(teams_env):
    client, _, tb, _, _ = teams_env
    r = client.get(f"/api/v1/teams/{tb}/members", headers=_hdr(client, *OP_USER))
    assert r.status_code == 404, f"跨队成员 PII 枚举未拒: {r.status_code} {r.text}"


def test_operator_cannot_read_other_team_detail(teams_env):
    client, _, tb, _, _ = teams_env
    r = client.get(f"/api/v1/teams/{tb}", headers=_hdr(client, *OP_USER))
    assert r.status_code == 404, f"跨队详情未拒: {r.status_code} {r.text}"


def test_operator_team_list_scoped_to_own_team(teams_env):
    client, ta, tb, _, _ = teams_env
    r = client.get("/api/v1/teams?page_size=100", headers=_hdr(client, *OP_USER))
    assert r.status_code == 200, r.text
    ids = [t["id"] for t in r.json()["data"]["items"]]
    assert ta in ids, "本队应可见"
    assert tb not in ids, f"operator 列表不应见他队: {ids}"


# ===== platform admin 全通 =====

def test_admin_full_access(teams_env):
    client, ta, tb, _, other_id = teams_env
    h = _hdr(client)
    # 建
    r = client.post("/api/v1/teams", json={"name": "卡85deafc4_admin建"}, headers=h)
    assert r.status_code == 200, r.text
    new_id = r.json()["data"]["id"]
    # 改
    assert client.put(f"/api/v1/teams/{new_id}", json={"name": "卡85deafc4_admin改"}, headers=h).status_code == 200
    # 读他队
    assert client.get(f"/api/v1/teams/{tb}/members", headers=h).status_code == 200
    # 成员移入/移出
    assert client.post(f"/api/v1/teams/{ta}/members", json={"user_id": other_id}, headers=h).status_code == 200
    assert client.delete(f"/api/v1/teams/{ta}/members/{other_id}", headers=h).status_code == 200
    # 删
    assert client.delete(f"/api/v1/teams/{new_id}", headers=h).status_code == 200
