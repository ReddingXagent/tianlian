"""
fleet 模块企业归属团队隔离测试 — 任务卡 708350b3

验证车队资源（司机 / V2G 计划）按 enterprise.owner_team_id 隔离：
- 团队级用户(operator)伪造 enterprise_id（query/body）→ 404；
- 跨团队访问他人司机（resource-by-id）→ 404；
- 同企业正常访问不受影响；admin/平台级豁免。

fleet_drivers / fleet_v2g 的 router 均 require_role("admin","operator")，
故团队级用户用 OPERATOR 角色（非平台级，受 team scoping 约束）。
"""
import bcrypt
import pytest


@pytest.fixture
def fleet_team_pair(client):
    """两团队 + 两 OPERATOR 用户 + 两企业(分属两团队) + token。"""
    from app.models.user import User, UserRole, Team
    from app.models.enterprise import Enterprise, EnterpriseStatus
    s = client._sesh

    ta = Team(name="车队团队A", code="FLTTA")
    tb = Team(name="车队团队B", code="FLTTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "fleet123456"
    ua = User(
        username="fleet_op_a", real_name="A运营", role=UserRole.OPERATOR,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="fleet_op_b", real_name="B运营", role=UserRole.OPERATOR,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([ua, ub])
    s.commit()

    ent_a = Enterprise(name="舰队企业A", code="FLTEA", status=EnterpriseStatus.ACTIVE, owner_team_id=ta.id)
    ent_b = Enterprise(name="舰队企业B", code="FLTEB", status=EnterpriseStatus.ACTIVE, owner_team_id=tb.id)
    s.add_all([ent_a, ent_b])
    s.commit()
    s.refresh(ent_a)
    s.refresh(ent_b)

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "enterprises": {"a": ent_a, "b": ent_b},
        "tokens": {"a": _tok("fleet_op_a"), "b": _tok("fleet_op_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _admin_h(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


# ==================== fleet_drivers 团队隔离 ====================

class TestFleetDriversTeamIsolation:
    """司机资源按企业归属团队隔离"""

    def test_list_forge_enterprise_404(self, client, fleet_team_pair):
        """A 运营伪造 ?enterprise_id=B → 404。"""
        ent_b = fleet_team_pair["enterprises"]["b"]
        r = client.get(
            f"/api/v1/fleet/drivers?enterprise_id={ent_b.id}",
            headers=_h(fleet_team_pair["tokens"]["a"]),
        )
        assert r.status_code == 404

    def test_list_own_enterprise_ok(self, client, fleet_team_pair):
        """A 运营查本人企业司机 → 200（空列表亦可）。"""
        ent_a = fleet_team_pair["enterprises"]["a"]
        r = client.get(
            f"/api/v1/fleet/drivers?enterprise_id={ent_a.id}",
            headers=_h(fleet_team_pair["tokens"]["a"]),
        )
        assert r.status_code == 200

    def test_create_forge_enterprise_404(self, client, fleet_team_pair):
        """A 运营伪造 body enterprise_id=B 创建司机 → 404。"""
        ent_b = fleet_team_pair["enterprises"]["b"]
        r = client.post(
            "/api/v1/fleet/drivers",
            json={
                "enterprise_id": ent_b.id, "name": "越权司机",
                "phone": "13800099999", "license_no": "FORGE_LICENSE_A1",
                "license_type": "B2",
            },
            headers=_h(fleet_team_pair["tokens"]["a"]),
        )
        assert r.status_code == 404

    def test_cross_team_driver_access_404(self, client, fleet_team_pair):
        """A 运营访问/改/删 B 企业司机 → 404。"""
        ent_b = fleet_team_pair["enterprises"]["b"]
        # B 运营先创建一名司机
        created = client.post(
            "/api/v1/fleet/drivers",
            json={
                "enterprise_id": ent_b.id, "name": "B司机",
                "phone": "13800088888", "license_no": "B_LICENSE_001",
                "license_type": "B2",
            },
            headers=_h(fleet_team_pair["tokens"]["b"]),
        )
        assert created.status_code == 200, created.text
        driver_b = created.json()["data"]["id"]

        ha = _h(fleet_team_pair["tokens"]["a"])
        assert client.get(f"/api/v1/fleet/drivers/{driver_b}", headers=ha).status_code == 404
        assert client.put(f"/api/v1/fleet/drivers/{driver_b}", json={"name": "篡改"}, headers=ha).status_code == 404
        assert client.delete(f"/api/v1/fleet/drivers/{driver_b}", headers=ha).status_code == 404

        # B 本人可访问
        assert client.get(
            f"/api/v1/fleet/drivers/{driver_b}",
            headers=_h(fleet_team_pair["tokens"]["b"]),
        ).status_code == 200

    def test_admin_sees_all(self, client, fleet_team_pair):
        """admin（平台级）可查任意企业司机列表。"""
        ent_a = fleet_team_pair["enterprises"]["a"]
        ent_b = fleet_team_pair["enterprises"]["b"]
        admin = _admin_h(client)
        assert client.get(f"/api/v1/fleet/drivers?enterprise_id={ent_a.id}", headers=admin).status_code == 200
        assert client.get(f"/api/v1/fleet/drivers?enterprise_id={ent_b.id}", headers=admin).status_code == 200


# ==================== fleet_v2g 团队隔离 ====================

class TestFleetV2gTeamIsolation:
    """V2G 计划/收益按企业归属团队隔离（enterprise_id 必填 query）"""

    def test_list_plans_forge_404(self, client, fleet_team_pair):
        """A 运营伪造 ?enterprise_id=B 查 V2G 计划 → 404。"""
        ent_b = fleet_team_pair["enterprises"]["b"]
        r = client.get(
            f"/api/v1/fleet/v2g/plans?enterprise_id={ent_b.id}",
            headers=_h(fleet_team_pair["tokens"]["a"]),
        )
        assert r.status_code == 404

    def test_list_revenue_forge_404(self, client, fleet_team_pair):
        """A 运营伪造 ?enterprise_id=B 查 V2G 收益 → 404。"""
        ent_b = fleet_team_pair["enterprises"]["b"]
        r = client.get(
            f"/api/v1/fleet/v2g/revenue?enterprise_id={ent_b.id}",
            headers=_h(fleet_team_pair["tokens"]["a"]),
        )
        assert r.status_code == 404

    def test_status_forge_404(self, client, fleet_team_pair):
        """A 运营伪造 ?enterprise_id=B 查 V2G 状态 → 404。"""
        ent_b = fleet_team_pair["enterprises"]["b"]
        r = client.get(
            f"/api/v1/fleet/v2g/status?enterprise_id={ent_b.id}",
            headers=_h(fleet_team_pair["tokens"]["a"]),
        )
        assert r.status_code == 404
