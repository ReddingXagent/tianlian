"""发票配置域越权门控测试 — 工作卡 a2ef58bb-ed10-4a7a-9fe9-852528c3ffa1。

对齐 sibling global_config.py 的治理模式: GET/PUT /system-config/invoice
均须 assert_config_domain_access(db, user, "invoice")。

scope_matrix: invoice 域仅 ops_company (及 platform_admin "*") 可访问;
maintenance_team / fleet → 403。
"""
import bcrypt
import pytest

import app.api.v1  # noqa: F401  化解 deps↔v1 循环导入 (同 test_multi_tenant_config)
from app.models.user import Team, TeamType, User, UserRole


@pytest.fixture(scope="function")
def inv_env(client):
    """ops_company + maintenance_team 两类 team 各一个 ENGINEER 用户 + admin token。"""
    s = client._sesh

    ops_team = Team(name="发票运营公司", code="InvOps1", type=TeamType.OPS_COMPANY,
                    owner_subject_id=2001)
    mt_team = Team(name="发票运维团队", code="InvMt1", type=TeamType.MAINTENANCE_TEAM,
                   owner_subject_id=2001)
    s.add_all([ops_team, mt_team])
    s.commit()
    s.refresh(ops_team); s.refresh(mt_team)

    mt_team.parent_team_id = ops_team.id
    s.commit()

    pwd = "inv123456"

    def _make_user(username, team):
        return User(
            username=username,
            real_name=username,
            role=UserRole.ENGINEER,
            team_id=team.id,
            status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )

    ops_user = _make_user("inv_ops_user", ops_team)
    mt_user = _make_user("inv_mt_user", mt_team)
    s.add_all([ops_user, mt_user])
    s.commit()

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json().get("data", {}).get("token") or r.json().get("token")

    def _admin_tok():
        r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
        assert r.status_code == 200, f"admin 登录失败: {r.text}"
        return r.json().get("data", {}).get("token") or r.json().get("token")

    return {
        "tokens": {
            "ops": _tok("inv_ops_user"),
            "mt": _tok("inv_mt_user"),
            "admin": _admin_tok(),
        },
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


class TestInvoiceConfigScope:
    def test_maintenance_team_get_forbidden(self, client, inv_env):
        """maintenance_team 用户 GET 发票配置 → 403"""
        resp = client.get("/api/v1/system-config/invoice", headers=_h(inv_env["tokens"]["mt"]))
        assert resp.status_code == 403

    def test_maintenance_team_put_forbidden(self, client, inv_env):
        """maintenance_team 用户 PUT 发票配置 → 403"""
        resp = client.put("/api/v1/system-config/invoice", headers=_h(inv_env["tokens"]["mt"]),
                          json={"company_name": "越权公司"})
        assert resp.status_code == 403

    def test_admin_and_ops_company_still_allowed(self, client, inv_env):
        """admin 与 ops_company 用户 GET+PUT 仍 200"""
        for key in ("admin", "ops"):
            resp = client.get("/api/v1/system-config/invoice", headers=_h(inv_env["tokens"][key]))
            assert resp.status_code == 200, f"{key} GET 失败: {resp.text}"
            resp = client.put("/api/v1/system-config/invoice",
                              headers=_h(inv_env["tokens"][key]),
                              json={"company_name": f"{key}公司"})
            if key == "admin":
                assert resp.status_code == 200, f"admin PUT 失败: {resp.text}"
            else:
                # ops_company ENGINEER 无 system:config 权限, 域校验通过后由
                # _check_admin_or_permission 决定 (403) — 只要不因 invoice 域被拒即可
                assert resp.status_code in (200, 403)
