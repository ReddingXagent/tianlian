"""配置多租户化回归测试 — 工作卡 cf614348-a76e-4819-a2ff-ce00d4288881。

组织层级: 平台 → 运营公司(ops_company) → 运维团队(maintenance_team)/车队(fleet)。
本卡把配置域访问按 Team.type 收口, 并给 SystemConfig / NotificationConfig 补 team_id
隔离列, 杜绝「甲公司读到乙公司配置」。

覆盖:
1. Team 模型扩展: TeamType 枚举 + type/parent_team_id/owner_subject_id, 存量默认 ops_company
2. scope_matrix 三矩阵 + get_team_config_scope
3. assert_config_domain_access: 越权配置域 → 403
4. /system-config/global 4 类账户访问矩阵 (domain="system")
5. SystemConfig.team_id 隔离 (list_system_configs_for_team)
6. NotificationConfig.team_id 隔离 (API list/get)
7. fleet 经 parent_team 不可越权到 ops_company 域
"""
import bcrypt
import pytest
from fastapi import HTTPException

from app.core.scope_matrix import (
    CONFIG_SCOPE_MATRIX,
    LOG_SCOPE_MATRIX,
    NOTIFY_EVENT_SCOPE_MATRIX,
    get_team_config_scope,
)
from app.models.user import Team, TeamType, User, UserRole

# 先触发 app.api.v1 包完整初始化, 化解 deps↔v1 循环导入 (见 tests/api/test_deps_team_scoping.py):
# deps 顶层 `from app.api.v1.auth import get_current_user` 触发 v1/__init__, 其中
# charging_queue 又 import deps —— 若 deps 首个被导入会 partially-initialized。先 import v1 解环。
import app.api.v1  # noqa: F401
from app.api.deps import assert_config_domain_access, resolve_team_type


# ─── 多租户脚手架 ───────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def mt_env(client):
    """构造三层组织 + 四类账户:

    - ops_team   (ops_company, 顶层运营公司)
      ├─ mt_team    (maintenance_team, parent=ops_team)
      └─ fleet_team (fleet, parent=ops_team)

    用户均为 ENGINEER 角色 (含 notification:manage 权限, 且非 platform_admin),
    归属不同 type 的 team, 用以验证「同角色不同 team.type → 不同配置域」。

    返回 dict: teams/users/tokens + admin token。
    """
    s = client._sesh

    ops_team = Team(name="MT运营公司", code="MTOps1", type=TeamType.OPS_COMPANY,
                    owner_subject_id=1001)
    mt_team = Team(name="MT运维团队", code="MTMt1", type=TeamType.MAINTENANCE_TEAM,
                   owner_subject_id=1001)
    fleet_team = Team(name="MT车队", code="MTFlt1", type=TeamType.FLEET,
                      owner_subject_id=1001)
    s.add_all([ops_team, mt_team, fleet_team])
    s.commit()
    s.refresh(ops_team); s.refresh(mt_team); s.refresh(fleet_team)

    # 层级: maintenance_team / fleet 指向所属运营公司
    mt_team.parent_team_id = ops_team.id
    fleet_team.parent_team_id = ops_team.id
    s.commit()

    pwd = "mt123456"

    def _make_user(username, team):
        return User(
            username=username,
            real_name=username,
            role=UserRole.ENGINEER,
            team_id=team.id,
            status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )

    ops_user = _make_user("mt_ops_user", ops_team)
    mt_user = _make_user("mt_mt_user", mt_team)
    fleet_user = _make_user("mt_fleet_user", fleet_team)
    s.add_all([ops_user, mt_user, fleet_user])
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
        "teams": {"ops": ops_team, "mt": mt_team, "fleet": fleet_team},
        "users": {"ops": ops_user, "mt": mt_user, "fleet": fleet_user},
        "tokens": {
            "ops": _tok("mt_ops_user"),
            "mt": _tok("mt_mt_user"),
            "fleet": _tok("mt_fleet_user"),
            "admin": _admin_tok(),
        },
        "pwd": pwd,
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ─── 1. Team 模型扩展 ───────────────────────────────────────────────────────

class TestTeamModelExtension:
    def test_teamtype_enum_values(self):
        assert TeamType.OPS_COMPANY.value == "ops_company"
        assert TeamType.MAINTENANCE_TEAM.value == "maintenance_team"
        assert TeamType.FLEET.value == "fleet"

    def test_team_default_type_is_ops_company(self, client):
        """存量 Team 不显式指定 type → 默认 ops_company (存量迁移契约)。"""
        s = client._sesh
        legacy = Team(name="存量团队", code="MTLegacy1")
        s.add(legacy); s.commit(); s.refresh(legacy)
        assert legacy.type == TeamType.OPS_COMPANY

    def test_team_parent_and_owner_subject(self, mt_env):
        teams = mt_env["teams"]
        assert teams["mt"].parent_team_id == teams["ops"].id
        assert teams["fleet"].parent_team_id == teams["ops"].id
        # 同主体多 team (多角色): ops/mt/fleet 共享 owner_subject_id
        assert teams["ops"].owner_subject_id == teams["mt"].owner_subject_id == 1001


# ─── 2. scope_matrix 矩阵 + helper ─────────────────────────────────────────

class TestScopeMatrix:
    def test_config_scope_matrix_shape(self):
        assert CONFIG_SCOPE_MATRIX["platform_admin"] == "*"
        assert "system" in CONFIG_SCOPE_MATRIX["ops_company"]
        assert "payment" in CONFIG_SCOPE_MATRIX["ops_company"]
        assert "alarm" in CONFIG_SCOPE_MATRIX["maintenance_team"]
        assert "workorder" in CONFIG_SCOPE_MATRIX["maintenance_team"]
        assert CONFIG_SCOPE_MATRIX["fleet"] == ["notification_basic"]

    def test_log_and_notify_matrix_present(self):
        assert LOG_SCOPE_MATRIX["platform_admin"] == "*"
        assert "order" in LOG_SCOPE_MATRIX["ops_company"]
        assert "device" in LOG_SCOPE_MATRIX["maintenance_team"]
        assert "charging" in LOG_SCOPE_MATRIX["fleet"]
        assert NOTIFY_EVENT_SCOPE_MATRIX["platform_admin"] == "*"
        assert "device_down" in NOTIFY_EVENT_SCOPE_MATRIX["ops_company"]
        assert "fault" in NOTIFY_EVENT_SCOPE_MATRIX["maintenance_team"]
        assert "charging_complete" in NOTIFY_EVENT_SCOPE_MATRIX["fleet"]

    def test_get_team_config_scope(self):
        assert get_team_config_scope("platform_admin") == "*"
        assert get_team_config_scope("ops_company") == CONFIG_SCOPE_MATRIX["ops_company"]
        assert get_team_config_scope("fleet") == ["notification_basic"]

    def test_get_team_config_scope_unknown_type_empty(self):
        """未知/无 team_type → 空白名单 (最小权限)。"""
        assert get_team_config_scope("unknown") == []
        assert get_team_config_scope(None) == []


# ─── 3. assert_config_domain_access (越权 → 403) ────────────────────────────

class TestAssertConfigDomainAccess:
    def test_platform_admin_all_domains(self, mt_env, db_session):
        admin = mt_env["users"]["ops"]  # 占位, 真正测 admin 角色
        from app.models.user import User as U
        # 取 conftest seed 的 admin (平台级)
        admin_user = db_session.query(U).filter(U.username == "admin").first()
        for domain in ["system", "payment", "invoice", "notification", "alarm", "workorder"]:
            assert_config_domain_access(db_session, admin_user, domain)  # 不抛

    def test_ops_company_allowed_denied(self, mt_env, db_session):
        ops_user = mt_env["users"]["ops"]
        # 允许域
        assert_config_domain_access(db_session, ops_user, "system")
        assert_config_domain_access(db_session, ops_user, "payment")
        # 越权域 (alarm/workorder 属 maintenance_team)
        with pytest.raises(HTTPException) as exc:
            assert_config_domain_access(db_session, ops_user, "alarm")
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException):
            assert_config_domain_access(db_session, ops_user, "workorder")

    def test_maintenance_team_scope(self, mt_env, db_session):
        mt_user = mt_env["users"]["mt"]
        assert_config_domain_access(db_session, mt_user, "notification")
        assert_config_domain_access(db_session, mt_user, "workorder")
        with pytest.raises(HTTPException) as exc:
            assert_config_domain_access(db_session, mt_user, "system")
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException):
            assert_config_domain_access(db_session, mt_user, "payment")

    def test_fleet_only_notification_basic(self, mt_env, db_session):
        fleet_user = mt_env["users"]["fleet"]
        assert_config_domain_access(db_session, fleet_user, "notification_basic")
        # fleet 不能碰 ops_company 域, 也不能碰完整 notification
        for dom in ["system", "payment", "invoice", "tariff", "energy", "notification", "alarm"]:
            with pytest.raises(HTTPException) as exc:
                assert_config_domain_access(db_session, fleet_user, dom)
            assert exc.value.status_code == 403

    def test_resolve_team_type(self, mt_env, db_session):
        from app.models.user import User as U
        admin = db_session.query(U).filter(U.username == "admin").first()
        assert resolve_team_type(db_session, admin) == "platform_admin"
        assert resolve_team_type(db_session, mt_env["users"]["ops"]) == "ops_company"
        assert resolve_team_type(db_session, mt_env["users"]["mt"]) == "maintenance_team"
        assert resolve_team_type(db_session, mt_env["users"]["fleet"]) == "fleet"


# ─── 4. /system-config/global 4 类账户访问矩阵 ─────────────────────────────

class TestGlobalConfigDomainGate:
    """GET /system-config/global 属 system 域: 仅 platform_admin + ops_company 可读,
    maintenance_team / fleet 越权 → 403。真正发请求的 4×矩阵。"""

    def test_matrix(self, client, mt_env):
        tok = mt_env["tokens"]
        cases = [
            ("admin", 200),
            ("ops", 200),
            ("mt", 403),
            ("fleet", 403),
        ]
        for who, expect in cases:
            r = client.get("/api/v1/system-config/global", headers=_h(tok[who]))
            assert r.status_code == expect, (
                f"{who} 期望 {expect}, 实际 {r.status_code}: {r.text}"
            )

    def test_fleet_cannot_escalate_via_parent(self, client, mt_env):
        """fleet.parent_team=ops_company, 但仍不能访问 system 域 (fleet 白名单独立)。"""
        assert mt_env["teams"]["fleet"].parent_team_id == mt_env["teams"]["ops"].id
        r = client.get("/api/v1/system-config/global", headers=_h(mt_env["tokens"]["fleet"]))
        assert r.status_code == 403


# ─── 5. SystemConfig.team_id 隔离 ──────────────────────────────────────────

class TestSystemConfigTeamIsolation:
    """list_system_configs_for_team: 团队级仅见 本team + 平台(NULL); 平台管理员全见。"""

    @pytest.fixture(scope="function")
    def seeded_configs(self, client, mt_env):
        from app.models.system_config import SystemConfig
        s = client._sesh
        ops_id = mt_env["teams"]["ops"].id
        mt_id = mt_env["teams"]["mt"].id
        rows = [
            SystemConfig(config_key="mt_cfg_platform", config_value={"k": "plat"},
                         config_type="global", team_id=None),
            SystemConfig(config_key="mt_cfg_ops", config_value={"k": "ops"},
                         config_type="global", team_id=ops_id),
            SystemConfig(config_key="mt_cfg_mt", config_value={"k": "mt"},
                         config_type="global", team_id=mt_id),
        ]
        s.add_all(rows); s.commit()
        for r in rows:
            s.refresh(r)
        return {r.config_key: r for r in rows}

    def test_ops_user_sees_own_and_platform_only(self, client, mt_env, seeded_configs):
        from app.api.v1.system_config.common import list_system_configs_for_team
        s = client._sesh
        rows = list_system_configs_for_team(s, mt_env["users"]["ops"])
        keys = {r.config_key for r in rows}
        assert "mt_cfg_platform" in keys   # 平台共享
        assert "mt_cfg_ops" in keys        # 本 team
        assert "mt_cfg_mt" not in keys     # 乙公司不可见

    def test_mt_user_sees_own_and_platform_only(self, client, mt_env, seeded_configs):
        from app.api.v1.system_config.common import list_system_configs_for_team
        s = client._sesh
        rows = list_system_configs_for_team(s, mt_env["users"]["mt"])
        keys = {r.config_key for r in rows}
        assert "mt_cfg_platform" in keys
        assert "mt_cfg_mt" in keys
        assert "mt_cfg_ops" not in keys

    def test_platform_admin_sees_all(self, client, mt_env, seeded_configs):
        from app.api.v1.system_config.common import list_system_configs_for_team
        from app.models.user import User as U
        s = client._sesh
        admin = s.query(U).filter(U.username == "admin").first()
        rows = list_system_configs_for_team(s, admin)
        keys = {r.config_key for r in rows}
        assert {"mt_cfg_platform", "mt_cfg_ops", "mt_cfg_mt"} <= keys


# ─── 6. NotificationConfig.team_id 隔离 ────────────────────────────────────

class TestNotificationConfigTeamIsolation:
    """NotificationConfig 显式 team_id 列: team_id 非空时硬隔离, NULL 走原 scope 兼容。"""

    @pytest.fixture(scope="function")
    def seeded_notifs(self, client, mt_env):
        from app.models.notification_config import NotificationConfig
        s = client._sesh
        ops_id = mt_env["teams"]["ops"].id
        mt_id = mt_env["teams"]["mt"].id
        ca = NotificationConfig(name="MT-Ops通知", scope_type="tenant", team_id=ops_id)
        cb = NotificationConfig(name="MT-Mt通知", scope_type="tenant", team_id=mt_id)
        s.add_all([ca, cb]); s.commit(); s.refresh(ca); s.refresh(cb)
        return {"ops": ca.id, "mt": cb.id}

    def test_list_filters_by_team_id(self, client, mt_env, seeded_notifs):
        r = client.get("/api/v1/notification-configs", headers=_h(mt_env["tokens"]["ops"]))
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["data"]]
        assert seeded_notifs["ops"] in ids
        assert seeded_notifs["mt"] not in ids   # 乙公司不可见

    def test_get_other_team_config_404(self, client, mt_env, seeded_notifs):
        r = client.get(
            f"/api/v1/notification-configs/{seeded_notifs['mt']}",
            headers=_h(mt_env["tokens"]["ops"]),
        )
        assert r.status_code == 404

    def test_get_own_team_config_200(self, client, mt_env, seeded_notifs):
        r = client.get(
            f"/api/v1/notification-configs/{seeded_notifs['ops']}",
            headers=_h(mt_env["tokens"]["ops"]),
        )
        assert r.status_code == 200

    def test_admin_sees_all(self, client, mt_env, seeded_notifs):
        r = client.get("/api/v1/notification-configs", headers=_h(mt_env["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["data"]]
        assert seeded_notifs["ops"] in ids
        assert seeded_notifs["mt"] in ids

    def test_delete_other_team_config_404(self, client, mt_env, seeded_notifs):
        r = client.delete(
            f"/api/v1/notification-configs/{seeded_notifs['mt']}",
            headers=_h(mt_env["tokens"]["ops"]),
        )
        assert r.status_code == 404
