"""
fleet/balance-warning team scope 测试 — 任务卡 5219a206

缺陷: fleet_balance_warning 端点仅 get_current_user，无 team scope，
get_low_balance_enterprises 全量返回所有 ACTIVE 企业的财务敏感清单
（企业名/余额/credit_limit/available_balance）→ 水平越权。

修复语义（对齐 team_scope）:
- 团队级用户 → 仅本 team（Enterprise.owner_team_id == user.team_id）；
- admin/super_admin → None 全量；
- 未登录 → 401。
"""
from decimal import Decimal

import bcrypt
import pytest

from app.models.enterprise import Enterprise, EnterpriseStatus
from app.services.enterprise_balance_service import get_low_balance_enterprises


@pytest.fixture
def warning_scope_seed(client, seed_users):
    """两团队 + 各一家低余额企业 + 一家无主企业 + 团队级用户 token。"""
    from app.models.user import User, UserRole, Team
    s = client._sesh

    ta = Team(name="余额预警团队A", code="BWTA")
    tb = Team(name="余额预警团队B", code="BWTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "bw123456"
    ua = User(
        username="bw_op_a", real_name="A运营", role=UserRole.OPERATOR,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add(ua)
    s.commit()

    ent_a = Enterprise(
        name="A队低余额企业", code="BW_A_LOW", balance=Decimal("50.00"),
        credit_limit=Decimal("200.00"), status=EnterpriseStatus.ACTIVE,
        owner_team_id=ta.id,
    )
    ent_b = Enterprise(
        name="B队低余额企业", code="BW_B_LOW", balance=Decimal("80.00"),
        credit_limit=Decimal("300.00"), status=EnterpriseStatus.ACTIVE,
        owner_team_id=tb.id,
    )
    ent_none = Enterprise(
        name="无主低余额企业", code="BW_N_LOW", balance=Decimal("10.00"),
        credit_limit=Decimal("100.00"), status=EnterpriseStatus.ACTIVE,
        owner_team_id=None,
    )
    s.add_all([ent_a, ent_b, ent_none])
    s.commit()

    def _tok(username, password):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "enterprises": {"a": ent_a, "b": ent_b, "none": ent_none},
        "op_a_token": _tok("bw_op_a", pwd),
        "admin_token": _tok("admin", "admin123"),
        "session": s,
    }


class TestServiceTeamScope:
    """get_low_balance_enterprises 服务层 team_id 过滤"""

    def test_team_id_filters_owner_team(self, warning_scope_seed):
        db = warning_scope_seed["session"]
        result = get_low_balance_enterprises(db, team_id=warning_scope_seed["teams"]["a"].id)
        codes = [r["code"] for r in result]
        assert codes == ["BW_A_LOW"]

    def test_none_team_id_returns_all(self, warning_scope_seed):
        db = warning_scope_seed["session"]
        result = get_low_balance_enterprises(db, team_id=None)
        codes = sorted(r["code"] for r in result)
        assert codes == ["BW_A_LOW", "BW_B_LOW", "BW_N_LOW"]

    def test_team_id_composes_with_threshold(self, warning_scope_seed):
        db = warning_scope_seed["session"]
        result = get_low_balance_enterprises(db, threshold=Decimal("60"), team_id=warning_scope_seed["teams"]["a"].id)
        codes = [r["code"] for r in result]
        # BW_A_LOW(50<60) 命中；他团队/无主行被 scope 排除
        assert "BW_A_LOW" in codes
        assert "BW_B_LOW" not in codes
        assert "BW_N_LOW" not in codes


class TestEndpointTeamScope:

    def test_team_user_sees_own_team_only(self, client, warning_scope_seed):
        """团队级用户只见本 team 企业，不见他团队/无主企业（水平越权封堵）"""
        headers = {"Authorization": f"Bearer {warning_scope_seed['op_a_token']}"}
        resp = client.get("/api/v1/fleet/balance-warning", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        codes = [item["code"] for item in body["items"]]
        assert codes == ["BW_A_LOW"]
        assert body["total"] == 1

    def test_admin_sees_all(self, client, warning_scope_seed):
        headers = {"Authorization": f"Bearer {warning_scope_seed['admin_token']}"}
        resp = client.get("/api/v1/fleet/balance-warning", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        codes = sorted(item["code"] for item in body["items"])
        assert codes == ["BW_A_LOW", "BW_B_LOW", "BW_N_LOW"]

    def test_anonymous_401(self, anon_client, warning_scope_seed):
        resp = anon_client.get("/api/v1/fleet/balance-warning")
        assert resp.status_code == 401
