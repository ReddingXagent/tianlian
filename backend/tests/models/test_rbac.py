#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RBAC 模型测试 — SQLAlchemy RoleTable/PermissionTable
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.models.rbac import (
    RoleTable, PermissionTable, role_permission_table, user_role_table,
    Role, Permission, ROLE_PERMISSIONS_MATRIX, seed_roles_and_permissions,
)
from app.models.user import User, UserRole
from app.middleware.permission import get_user_permissions


@pytest.fixture(scope="function")
def db_session():
    """每个测试独立的 SQLite 内存数据库"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


class TestRBACModel:
    def test_role_columns(self, db_session):
        cols = [c.name for c in RoleTable.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "display_name" in cols
        assert "description" in cols
        assert "is_system" in cols

    def test_permission_columns(self, db_session):
        cols = [c.name for c in PermissionTable.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "resource" in cols
        assert "action" in cols
        assert "description" in cols

    def test_role_relationships(self, db_session):
        assert hasattr(RoleTable, "users")
        assert hasattr(RoleTable, "permissions")
        assert hasattr(PermissionTable, "roles")

    def test_name_uniqueness(self, db_session):
        assert RoleTable.__table__.columns["name"].unique
        assert PermissionTable.__table__.columns["name"].unique

    def test_seed_creates_5_roles(self, db_session):
        seed_roles_and_permissions(db_session)
        roles = db_session.query(RoleTable).all()
        assert len(roles) == 5
        names = [r.name for r in roles]
        assert "super_admin" in names
        assert "admin" in names
        assert "operator" in names
        assert "viewer" in names
        assert "auditor" in names

    def test_seed_creates_38_permissions(self, db_session):
        seed_roles_and_permissions(db_session)
        perms = db_session.query(PermissionTable).all()
        assert len(perms) == 38

    def test_admin_has_all_permissions(self, db_session):
        seed_roles_and_permissions(db_session)
        admin_role = db_session.query(RoleTable).filter(RoleTable.name == "admin").first()
        assert len(admin_role.permissions) == 38

    def test_operator_permissions(self, db_session):
        seed_roles_and_permissions(db_session)
        op_role = db_session.query(RoleTable).filter(RoleTable.name == "operator").first()
        perm_names = [p.name for p in op_role.permissions]
        assert "device:create" in perm_names
        assert "device:control" in perm_names
        assert "workorder:assign" in perm_names
        assert "system:role" not in perm_names

    def test_viewer_permissions(self, db_session):
        seed_roles_and_permissions(db_session)
        v_role = db_session.query(RoleTable).filter(RoleTable.name == "viewer").first()
        perm_names = [p.name for p in v_role.permissions]
        assert "device:view" in perm_names
        assert "device:create" not in perm_names
        assert len(perm_names) == 6

    def test_auditor_permissions(self, db_session):
        seed_roles_and_permissions(db_session)
        a_role = db_session.query(RoleTable).filter(RoleTable.name == "auditor").first()
        perm_names = [p.name for p in a_role.permissions]
        assert "audit:view" in perm_names
        assert "audit:export" in perm_names
        assert "device:create" not in perm_names

    def test_matrix_consistency(self):
        """验证矩阵与枚举一致性"""
        matrix_admin = ROLE_PERMISSIONS_MATRIX["admin"]
        matrix_auditor = ROLE_PERMISSIONS_MATRIX["auditor"]
        assert "audit:view" in matrix_auditor
        assert "audit:export" in matrix_auditor
        assert len(matrix_admin) == 38

    def test_user_permission_resolution(self, db_session):
        """验证 get_user_permissions"""
        seed_roles_and_permissions(db_session)
        user = User(username="viewer_user", password_hash="x", role=UserRole.VIEWER)
        db_session.add(user)
        db_session.flush()

        perms = get_user_permissions(user)
        assert "device:view" in perms
        assert "device:create" not in perms
        assert len(perms) == 6

    def test_admin_user_permission_resolution(self, db_session):
        seed_roles_and_permissions(db_session)
        user = User(username="admin_user", password_hash="x", role=UserRole.ADMIN)
        db_session.add(user)
        db_session.flush()

        perms = get_user_permissions(user)
        assert len(perms) == 38
        assert "system:role" in perms

    # ── P2 (卡 1bd3b6e2): 现场运营角色补全 + 新增 8 manage 权限 ──

    def test_field_roles_have_operational_perms(self):
        """engineer/dispatcher/station_master/technician 矩阵补全 (operator 等价)。

        P2 之前矩阵漏建模这 4 个 UserRole, get_user_permissions 返回 [] → require_permission
        误挡; 它们在 23 个测试文件做写操作。补全后应持 operator 等价写权限。
        """
        for role in ("engineer", "dispatcher", "station_master", "technician"):
            perms = ROLE_PERMISSIONS_MATRIX[role]
            assert "device:edit" in perms, f"{role} 应可写设备"
            assert "workorder:edit" in perms, f"{role} 应可写工单"
            assert "charging:manage" in perms, f"{role} 应有 charging:manage"
            assert "system:role" not in perms, f"{role} 不应持 admin 专属权限"

    def test_operator_has_p2_manage_perms(self):
        """operator 持全部 8 个新 manage 权限 (业务写), 含 notification:manage + engineer:manage。"""
        op = ROLE_PERMISSIONS_MATRIX["operator"]
        for p in ("charging:manage", "fleet:manage", "healing:manage",
                  "notification:manage", "analytics:manage",
                  "knowledge:manage", "report:manage", "engineer:manage"):
            assert p in op, f"operator 应持 {p}"

    def test_readonly_roles_lack_write_perms(self):
        """viewer/auditor 不持任何写权限 (含 8 新 manage), 确保写端点 403。"""
        for role in ("viewer", "auditor"):
            perms = ROLE_PERMISSIONS_MATRIX[role]
            for p in ("device:edit", "charging:manage", "fleet:manage",
                      "notification:manage", "engineer:manage", "workorder:create"):
                assert p not in perms, f"{role} 不应持写权限 {p}"