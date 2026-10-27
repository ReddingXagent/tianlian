"""
fleet 充电策略 list 端点缺省 team 兜底过滤测试 — 任务卡 91848751

验证 GET /api/v1/fleet/policies 在 enterprise_id 缺省时:
- 团队 A 用户 → 只见本 team 企业策略, 看不到团队 B;
- admin 缺省 → 全量可见;
- 团队 A 用户传团队 B enterprise_id → 404。

fixture 构建思路照抄 test_fleet_default_scope_isolation.py(卡 45166947)。
"""
import bcrypt
import pytest

from app.models.fleet_charging_policy import FleetChargingPolicy


@pytest.fixture
def policy_scope_pair(client):
    """两团队 + 两 OPERATOR 用户 + 两企业(分属两团队) + 各一条充电策略 + token。"""
    from app.models.user import User, UserRole, Team
    from app.models.enterprise import Enterprise, EnterpriseStatus

    s = client._sesh
    out = {"teams": {}, "users": {}, "enterprises": {}, "tokens": {}}
    pwd = "policyscope123"

    for key, tname, tcode, uname in [
        ("a", "策略团队A", "PSCPA", "policy_op_a"),
        ("b", "策略团队B", "PSCPB", "policy_op_b"),
    ]:
        t = Team(name=tname, code=tcode)
        s.add(t)
        s.commit()
        s.refresh(t)
        out["teams"][key] = t

        u = User(
            username=uname, real_name=f"{key}运营", role=UserRole.OPERATOR,
            team_id=t.id, status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )
        s.add(u)
        s.commit()
        out["users"][key] = u

        ent = Enterprise(name=f"策略企业{key}", code=f"PSCPENT{key}",
                         status=EnterpriseStatus.ACTIVE, owner_team_id=t.id)
        s.add(ent)
        s.commit()
        s.refresh(ent)
        out["enterprises"][key] = ent

    ent_a, ent_b = out["enterprises"]["a"], out["enterprises"]["b"]
    for ent in [ent_a, ent_b]:
        s.add(FleetChargingPolicy(
            enterprise_id=ent.id, daily_kwh_limit=100.0, enable=True,
        ))
    s.commit()

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    out["tokens"] = {"a": _tok("policy_op_a"), "b": _tok("policy_op_b")}
    return out


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _admin_h(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _list(client, headers):
    r = client.get("/api/v1/fleet/policies", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    return body["items"] if isinstance(body, dict) and "items" in body else body


class TestListPoliciesDefaultScope:
    def test_team_a_only_sees_own(self, client, policy_scope_pair):
        items = _list(client, _h(policy_scope_pair["tokens"]["a"]))
        ent_a = policy_scope_pair["enterprises"]["a"].id
        ent_b = policy_scope_pair["enterprises"]["b"].id
        assert len(items) == 1
        assert all(p["enterprise_id"] == ent_a for p in items)
        assert not any(p["enterprise_id"] == ent_b for p in items)

    def test_admin_sees_all(self, client, policy_scope_pair):
        items = _list(client, _admin_h(client))
        assert len(items) >= 2

    def test_team_a_cross_enterprise_404(self, client, policy_scope_pair):
        ent_b = policy_scope_pair["enterprises"]["b"].id
        r = client.get("/api/v1/fleet/policies",
                       params={"enterprise_id": ent_b},
                       headers=_h(policy_scope_pair["tokens"]["a"]))
        assert r.status_code == 404, r.text
