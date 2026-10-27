"""系统配置通用 helper 测试 (app/api/v1/system_config/common.py, 卡 96f676b3)

common.py 是无 router 端点的依赖层纯函数模块, 被各业务域子模块复用:
- _check_admin_or_permission(user, perm)  admin 直通, 否则查 RBAC 权限, 无 → 403
- _load_json_config(db, key, default)      从 system_configs 表读 JSON, merge default
- _save_json_config(db, key, value, type)  upsert JSON 到 system_configs 表
- list_system_configs_for_team(db, user)   按 team 隔罗列出配置 (ORM)

覆盖维度:
(a) _check_admin_or_permission: admin/super_admin 直通; viewer 有权限 → True; 无权限 → 403
(b) _load_json_config: 不存在 → default; 存在 → merge default(保留 db 覆盖); 坏 JSON → default
(c) _save_json_config: 新增 + 更新 (upsert)
(d) list_system_configs_for_team: 平台 admin 全量; team 用户仅本 team + 平台共享 (team_id NULL)
(e) _load/_save 与 ORM list 互不影响 (raw SQL vs ORM, 不同视图)

system_configs 表由 conftest._schema_template_db 用 raw SQL 创建 (config_value TEXT)。
SystemConfig ORM 模型的 config_value 为 JSON 类型 —— 两者映射同表但视图不同 (common.py docstring)。
铁律: 仅加测试, 不改业务代码。
"""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.system_config.common import (
    _check_admin_or_permission,
    _load_json_config,
    _save_json_config,
    list_system_configs_for_team,
)
from app.models.system_config import SystemConfig
from app.models.user import User, UserRole


# ─── helpers ───

def _user(role, team_id=None):
    """造一个内存 User 对象 (不入库, 仅供权限判断; _check 用 role.value)。"""
    return User(username=f"u-{role.value}", role=role, team_id=team_id, status="active")


# ═══════════════════════════════════════════════════════════════
# 1. _check_admin_or_permission
# ═══════════════════════════════════════════════════════════════

class TestCheckAdminOrPermission:
    def test_admin_always_passes(self):
        """admin 角色无需具体权限即直通。"""
        assert _check_admin_or_permission(_user(UserRole.ADMIN), "any:perm") is True

    def test_super_admin_passes(self):
        assert _check_admin_or_permission(_user(UserRole.SUPER_ADMIN), "any:perm") is True

    def test_viewer_with_held_permission_passes(self):
        """viewer 持有 device:view (ROLE_PERMISSIONS_MATRIX) → 直通。"""
        assert _check_admin_or_permission(_user(UserRole.VIEWER), "device:view") is True

    def test_viewer_without_permission_raises_403(self):
        """viewer 无 system:manage → 403。"""
        with pytest.raises(HTTPException) as exc:
            _check_admin_or_permission(_user(UserRole.VIEWER), "system:manage")
        assert exc.value.status_code == 403
        assert "权限不足" in exc.value.detail


# ═══════════════════════════════════════════════════════════════
# 2. _load_json_config
# ═══════════════════════════════════════════════════════════════

class TestLoadJsonConfig:
    def test_missing_key_returns_default(self, client):
        db = client._sesh
        out = _load_json_config(db, "nonexistent_key", {"a": 1, "b": 2})
        assert out == {"a": 1, "b": 2}

    def test_stored_value_merges_default(self, client):
        """已存值与 default 合并 (db 值覆盖同名键)。"""
        db = client._sesh
        _save_json_config(db, "k1", {"b": 99, "c": 3})
        db.commit()
        out = _load_json_config(db, "k1", {"a": 1, "b": 2})  # b 被覆盖
        assert out == {"a": 1, "b": 99, "c": 3}

    def test_corrupt_json_returns_default(self, client):
        """config_value 非合法 JSON → 回退 default。"""
        db = client._sesh
        db.execute(text("INSERT INTO system_configs (config_key, config_value, type) VALUES (:k, :v, 'global')"),
                   {"k": "bad", "v": "<<<not json>>>"})
        db.commit()
        out = _load_json_config(db, "bad", {"fallback": True})
        assert out == {"fallback": True}


# ═══════════════════════════════════════════════════════════════
# 3. _save_json_config (upsert)
# ═══════════════════════════════════════════════════════════════

class TestSaveJsonConfig:
    def test_insert_new(self, client):
        db = client._sesh
        _save_json_config(db, "new_key", {"x": 1}, "global")
        db.commit()
        row = db.execute(text("SELECT config_value FROM system_configs WHERE config_key='new_key'")).first()
        assert json.loads(row[0]) == {"x": 1}

    def test_update_existing(self, client):
        """同 key 二次保存 → UPDATE 而非新增。"""
        db = client._sesh
        _save_json_config(db, "up", {"v": 1})
        db.commit()
        _save_json_config(db, "up", {"v": 2})
        db.commit()
        rows = db.execute(text("SELECT config_value FROM system_configs WHERE config_key='up'")).all()
        assert len(rows) == 1  # 仅一行 (upsert)
        assert json.loads(rows[0][0]) == {"v": 2}

    def test_round_trip(self, client):
        """save 后 load 回原值 (merge default 保留)。"""
        db = client._sesh
        _save_json_config(db, "rt", {"name": "n", "val": 5})
        db.commit()
        loaded = _load_json_config(db, "rt", {"name": "", "val": 0, "extra": "e"})
        assert loaded == {"name": "n", "val": 5, "extra": "e"}


# ═══════════════════════════════════════════════════════════════
# 4. list_system_configs_for_team (team 隔离, ORM)
# ═══════════════════════════════════════════════════════════════

class TestListForTeam:
    def _seed_configs(self, session):
        """造 3 条 ORM 配置: 平台共享 + 本队 + 他队。"""
        session.add_all([
            SystemConfig(config_key="shared", config_value={"s": 1}, team_id=None),
            SystemConfig(config_key="team1_only", config_value={"t": 1}, team_id=1),
            SystemConfig(config_key="team2_only", config_value={"t": 2}, team_id=2),
        ])
        session.commit()

    def test_admin_sees_all(self, client):
        s = client._sesh
        self._seed_configs(s)
        rows = list_system_configs_for_team(s, _user(UserRole.ADMIN))
        keys = {r.config_key for r in rows}
        assert keys == {"shared", "team1_only", "team2_only"}

    def test_team_user_sees_shared_and_own(self, client):
        """team1 用户: 平台共享 + team1, 不见他队。"""
        s = client._sesh
        self._seed_configs(s)
        rows = list_system_configs_for_team(s, _user(UserRole.VIEWER, team_id=1))
        keys = {r.config_key for r in rows}
        assert keys == {"shared", "team1_only"}
        assert "team2_only" not in keys

    def test_no_team_user_sees_only_shared(self, client):
        """无 team 用户 (team_id=None): 仅平台共享。"""
        s = client._sesh
        self._seed_configs(s)
        rows = list_system_configs_for_team(s, _user(UserRole.VIEWER, team_id=None))
        keys = {r.config_key for r in rows}
        assert keys == {"shared"}


# ═══════════════════════════════════════════════════════════════
# 5. _load/_save 与 ORM list 互不影响 (raw SQL vs ORM 视图)
# ═══════════════════════════════════════════════════════════════

class TestRawSqlAndOrmIndependence:
    def test_raw_save_not_visible_to_orm_list_without_team_match(self, client):
        """_save (raw SQL, 无 team_id 列写入) → ORM list 仅当 user 为平台 admin 或 team 匹配可见。

        raw SQL INSERT 不写 team_id (默认 NULL=平台共享), 故 team 用户应可见 (team_id IS NULL)。
        """
        db = client._sesh
        _save_json_config(db, "raw_k", {"v": 1})
        db.commit()
        # team1 viewer: team_id NULL 属平台共享 → 可见
        rows = list_system_configs_for_team(db, _user(UserRole.VIEWER, team_id=1))
        assert any(r.config_key == "raw_k" for r in rows)
