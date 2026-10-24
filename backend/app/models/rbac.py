"""
RBAC 权限模型 — SQLAlchemy 表 + 枚举 + 权限矩阵

设计:
- 4 级角色: admin / operator / viewer / auditor
- 权限矩阵按模块 (device/workorder/alarm/station/user/audit/system) 的 CRUD 划分
- 用户通过 User.role 主角色 + user_roles 关联表获得权限
- 支持系统内置角色和自定义角色
"""
from __future__ import annotations

from enum import Enum as PyEnum

from sqlalchemy import (
    Column, Integer, String, Text, Table, ForeignKey, DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


# ═══════════════════════════════════════════════
# 角色枚举 (代码层使用)
# ═══════════════════════════════════════════════

class Role(str, PyEnum):
    """角色枚举"""
    SUPER_ADMIN = "super_admin"  # 超级管理员 — 全部权限 (含跨租户)
    ADMIN = "admin"              # 管理员 — 系统全部权限
    OPERATOR = "operator"        # 运维操作员 — 日常运维读写
    VIEWER = "viewer"            # 只读用户 — 仅查看
    AUDITOR = "auditor"          # 审计员 — 审计日志+只读


class Permission(str, PyEnum):
    """权限枚举 (name 与 PermissionTable.name 保持一致)"""
    # ── 设备管理 ──
    DEVICE_VIEW = "device:view"
    DEVICE_CREATE = "device:create"
    DEVICE_EDIT = "device:edit"
    DEVICE_DELETE = "device:delete"
    DEVICE_CONTROL = "device:control"
    # ── 工单管理 ──
    WORKORDER_VIEW = "workorder:view"
    WORKORDER_CREATE = "workorder:create"
    WORKORDER_EDIT = "workorder:edit"
    WORKORDER_DELETE = "workorder:delete"
    WORKORDER_ASSIGN = "workorder:assign"
    # ── 告警管理 ──
    ALARM_VIEW = "alarm:view"
    ALARM_PROCESS = "alarm:process"
    ALARM_DELETE = "alarm:delete"
    # ── 站点管理 ──
    STATION_VIEW = "station:view"
    STATION_CREATE = "station:create"
    STATION_EDIT = "station:edit"
    STATION_DELETE = "station:delete"
    # ── 用户管理 ──
    USER_VIEW = "user:view"
    USER_CREATE = "user:create"
    USER_EDIT = "user:edit"
    USER_DELETE = "user:delete"
    USER_ROLE = "user:role"
    # ── 报表 ──
    REPORT_VIEW = "report:view"
    REPORT_EXPORT = "report:export"
    # ── 审计日志 ──
    AUDIT_VIEW = "audit:view"
    AUDIT_EXPORT = "audit:export"
    # ── 系统管理 ──
    SYSTEM_CONFIG = "system:config"
    SYSTEM_ROLE = "system:role"
    # ── 运营管理面 (任务卡 b9d16fae) ──
    OPERATE_MANAGE = "operate:manage"
    # ── API Key 管理 (任务卡 b9d16fae) ──
    API_KEY_MANAGE = "api_key:manage"
    # ── P2 业务模块写操作 (任务卡 1bd3b6e2) ──
    # 粗粒度 module:manage, 对应业务域全部写端点 (路由级 require_write_permission 守卫);
    # viewer/auditor 不持有 → 写端点 403; operator/现场角色持有 → 放行; admin 全量。
    CHARGING_MANAGE = "charging:manage"          # 充电域: 订单/队列/调度/策略/费用
    FLEET_MANAGE = "fleet:manage"                # 车队域: 企业/车辆/资金/碳证/白名单/对账
    HEALING_MANAGE = "healing:manage"            # 自愈/诊断域: healing/runbook/diagnosis/log_analysis
    NOTIFICATION_MANAGE = "notification:manage"  # 通知域: 配置/规则/模板/webhook (操作级)
    ANALYTICS_MANAGE = "analytics:manage"        # 分析/计算/异步任务域
    KNOWLEDGE_MANAGE = "knowledge:manage"        # 知识库管理
    REPORT_MANAGE = "report:manage"              # 报告管理
    ENGINEER_MANAGE = "engineer:manage"          # 工程师档案管理 (团队 owner-scoped)


# ═══════════════════════════════════════════════
# 角色 ⇔ 权限映射矩阵 (Python 静态定义)
# ═══════════════════════════════════════════════

# ── 权限集常量 (P2, 卡 1bd3b6e2) ──
# 全部权限值 — super_admin / admin 持有 (自动含未来新增权限)
_ALL_PERM_VALUES: list[str] = [p.value for p in Permission]

# 运维操作级权限集 — operator 与现场运营角色 (engineer/dispatcher/station_master/
# technician) 共享。这些角色执行日常业务写; viewer/auditor 只读。
# ⚠️ P2 之前矩阵只建模 5 角色, engineer/dispatcher/station_master/technician 未建模,
#    get_user_permissions 对它们返回 [] → require_permission 会误挡成 403; 而它们在
#    23 个测试文件里做写操作 (如 test_team_scoping 用 ENGINEER 跨团队 DELETE 期望 404;
#    test_notification_configs_coverage 用 ENGINEER 管理本团队通知配置)。
#    故 P2 补全: 现场运营角色授 operator 等价权限, 既不回归 (它们本就能写) 又让
#    viewer/auditor 被正确拦截。8 个新 module:manage 全部纳入操作级 (业务写)。
_OPERATIONAL_PERM_VALUES: list[str] = [
    Permission.DEVICE_VIEW.value, Permission.DEVICE_CREATE.value,
    Permission.DEVICE_EDIT.value, Permission.DEVICE_CONTROL.value,
    Permission.WORKORDER_VIEW.value, Permission.WORKORDER_CREATE.value,
    Permission.WORKORDER_EDIT.value, Permission.WORKORDER_ASSIGN.value,
    Permission.ALARM_VIEW.value, Permission.ALARM_PROCESS.value,
    Permission.STATION_VIEW.value, Permission.STATION_CREATE.value,
    Permission.STATION_EDIT.value,
    Permission.USER_VIEW.value,
    Permission.REPORT_VIEW.value, Permission.REPORT_EXPORT.value,
    Permission.OPERATE_MANAGE.value, Permission.API_KEY_MANAGE.value,
    Permission.CHARGING_MANAGE.value, Permission.FLEET_MANAGE.value,
    Permission.HEALING_MANAGE.value, Permission.NOTIFICATION_MANAGE.value,
    Permission.ANALYTICS_MANAGE.value, Permission.KNOWLEDGE_MANAGE.value,
    Permission.REPORT_MANAGE.value, Permission.ENGINEER_MANAGE.value,
]

ROLE_PERMISSIONS_MATRIX: dict[str, list[str]] = {
    Role.SUPER_ADMIN.value: list(_ALL_PERM_VALUES),  # 超级管理员 — 全部权限 (含跨租户)
    Role.ADMIN.value: list(_ALL_PERM_VALUES),        # 管理员 — 全部权限
    Role.OPERATOR.value: list(_OPERATIONAL_PERM_VALUES),  # 运维操作员 — 日常业务读写
    Role.VIEWER.value: [                              # 只读用户
        Permission.DEVICE_VIEW.value,
        Permission.WORKORDER_VIEW.value,
        Permission.ALARM_VIEW.value,
        Permission.STATION_VIEW.value,
        Permission.USER_VIEW.value,
        Permission.REPORT_VIEW.value,
    ],
    Role.AUDITOR.value: [                              # 审计员 — 只读 + 审计日志
        Permission.DEVICE_VIEW.value,
        Permission.WORKORDER_VIEW.value,
        Permission.ALARM_VIEW.value,
        Permission.STATION_VIEW.value,
        Permission.USER_VIEW.value,
        Permission.REPORT_VIEW.value,
        Permission.AUDIT_VIEW.value,
        Permission.AUDIT_EXPORT.value,
    ],
    # 现场运营角色 (UserRole 定义但矩阵原未建模; P2 补全, 授 operator 等价写权限)
    "engineer": list(_OPERATIONAL_PERM_VALUES),
    "dispatcher": list(_OPERATIONAL_PERM_VALUES),
    "station_master": list(_OPERATIONAL_PERM_VALUES),
    "technician": list(_OPERATIONAL_PERM_VALUES),
}


# ═══════════════════════════════════════════════
# 兼容旧版 ROLE_PERMISSIONS 字典 (其他模块使用)
# ═══════════════════════════════════════════════

ROLE_PERMISSIONS: dict[str, list[Permission]] = {
    Role.SUPER_ADMIN: list(Permission),
    Role.ADMIN: list(Permission),
    Role.OPERATOR: [Permission(p) for p in _OPERATIONAL_PERM_VALUES],
    Role.VIEWER: [
        Permission.DEVICE_VIEW,
        Permission.WORKORDER_VIEW,
        Permission.ALARM_VIEW,
        Permission.STATION_VIEW,
        Permission.USER_VIEW,
        Permission.REPORT_VIEW,
    ],
    Role.AUDITOR: [
        Permission.DEVICE_VIEW,
        Permission.WORKORDER_VIEW,
        Permission.ALARM_VIEW,
        Permission.STATION_VIEW,
        Permission.USER_VIEW,
        Permission.REPORT_VIEW,
        Permission.AUDIT_VIEW,
        Permission.AUDIT_EXPORT,
    ],
    # 现场运营角色 (P2 补全, 同 operator; 字符串键避免循环 import)
    "engineer": [Permission(p) for p in _OPERATIONAL_PERM_VALUES],
    "dispatcher": [Permission(p) for p in _OPERATIONAL_PERM_VALUES],
    "station_master": [Permission(p) for p in _OPERATIONAL_PERM_VALUES],
    "technician": [Permission(p) for p in _OPERATIONAL_PERM_VALUES],
}


# ═══════════════════════════════════════════════
# SQLAlchemy 关联表
# ═══════════════════════════════════════════════

role_permission_table = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

user_role_table = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


# ═══════════════════════════════════════════════
# SQLAlchemy 表模型
# ═══════════════════════════════════════════════

class RoleTable(Base):
    """角色表"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)  # Integer兼容SQLite自增
    name = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    is_system = Column(Integer, default=1)  # 1=系统内置不可删除, 0=自定义
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    permissions = relationship("PermissionTable", secondary=role_permission_table, back_populates="roles")
    users = relationship("User", secondary=user_role_table, back_populates="assigned_roles")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "is_system": bool(self.is_system),
            "permissions": sorted(set(p.name for p in self.permissions)),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PermissionTable(Base):
    """权限表"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)  # Integer兼容SQLite自增
    name = Column(String(100), unique=True, nullable=False, index=True)
    resource = Column(String(50), nullable=False)
    action = Column(String(20), nullable=False)
    description = Column(String(200), default="")

    roles = relationship("RoleTable", secondary=role_permission_table, back_populates="permissions")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "resource": self.resource,
            "action": self.action,
            "description": self.description,
        }


# ═══════════════════════════════════════════════
# 种子数据
# ═══════════════════════════════════════════════

def seed_roles_and_permissions(db_session):
    """向 roles / permissions 表写入默认种子数据"""
    from sqlalchemy import select

    # 检查是否已初始化
    existing = db_session.execute(select(RoleTable).limit(1)).scalar()
    if existing:
        return

    # 1. 创建权限
    permission_defs = [
        # (name, resource, action, description)
        ("device:view", "device", "view", "查看设备"),
        ("device:create", "device", "create", "创建设备"),
        ("device:edit", "device", "edit", "编辑设备"),
        ("device:delete", "device", "delete", "删除设备"),
        ("device:control", "device", "control", "控制设备"),
        ("workorder:view", "workorder", "view", "查看工单"),
        ("workorder:create", "workorder", "create", "创建工单"),
        ("workorder:edit", "workorder", "edit", "编辑工单"),
        ("workorder:delete", "workorder", "delete", "删除工单"),
        ("workorder:assign", "workorder", "assign", "分配工单"),
        ("alarm:view", "alarm", "view", "查看告警"),
        ("alarm:process", "alarm", "process", "处理告警"),
        ("alarm:delete", "alarm", "delete", "删除告警"),
        ("station:view", "station", "view", "查看站点"),
        ("station:create", "station", "create", "创建站点"),
        ("station:edit", "station", "edit", "编辑站点"),
        ("station:delete", "station", "delete", "删除站点"),
        ("user:view", "user", "view", "查看用户"),
        ("user:create", "user", "create", "创建用户"),
        ("user:edit", "user", "edit", "编辑用户"),
        ("user:delete", "user", "delete", "删除用户"),
        ("user:role", "user", "role", "用户角色管理"),
        ("report:view", "report", "view", "查看报表"),
        ("report:export", "report", "export", "导出报表"),
        ("audit:view", "audit", "view", "查看审计日志"),
        ("audit:export", "audit", "export", "导出审计日志"),
        ("system:config", "system", "config", "系统配置"),
        ("system:role", "system", "role", "角色管理"),
        ("operate:manage", "operate", "manage", "运营管理面写操作"),
        ("api_key:manage", "api_key", "manage", "API Key 管理"),
        # P2 业务模块写操作 (卡 1bd3b6e2)
        ("charging:manage", "charging", "manage", "充电域写操作 (订单/队列/调度/策略/费用)"),
        ("fleet:manage", "fleet", "manage", "车队域写操作 (企业/车辆/资金/碳证/白名单/对账)"),
        ("healing:manage", "healing", "manage", "自愈/诊断域写操作 (healing/runbook/diagnosis/log_analysis)"),
        ("notification:manage", "notification", "manage", "通知域写操作 (配置/规则/模板/webhook)"),
        ("analytics:manage", "analytics", "manage", "分析/计算/异步任务写操作"),
        ("knowledge:manage", "knowledge", "manage", "知识库写操作"),
        ("report:manage", "report", "manage", "报告管理写操作"),
        ("engineer:manage", "engineer", "manage", "工程师档案写操作 (团队 owner-scoped)"),
    ]

    perm_objects = {}
    for name, resource, action, desc in permission_defs:
        p = PermissionTable(name=name, resource=resource, action=action, description=desc)
        db_session.add(p)
        perm_objects[name] = p
    db_session.flush()

    # 2. 创建角色
    role_defs = [
        ("super_admin", "超级管理员", "超级管理员，拥有全部权限（含跨租户管理）。", ROLE_PERMISSIONS_MATRIX["super_admin"]),
        ("admin", "管理员", "系统管理员，拥有全部权限。可管理用户、角色和系统配置。", ROLE_PERMISSIONS_MATRIX["admin"]),
        ("operator", "运维操作员", "日常运维操作员，可管理设备、工单、告警等运维模块。", ROLE_PERMISSIONS_MATRIX["operator"]),
        ("viewer", "只读用户", "只读用户，仅可查看设备、工单、告警等信息。", ROLE_PERMISSIONS_MATRIX["viewer"]),
        ("auditor", "审计员", "审计员，可查看全部资源及审计日志。", ROLE_PERMISSIONS_MATRIX["auditor"]),
    ]

    for name, display_name, desc, perms in role_defs:
        r = RoleTable(name=name, display_name=display_name, description=desc, is_system=1)
        for perm_name in perms:
            if perm_name in perm_objects:
                r.permissions.append(perm_objects[perm_name])
        db_session.add(r)

    db_session.commit()


def get_role_permission_names(role_name: str) -> list[str]:
    """根据角色名获取权限字符串列表"""
    return ROLE_PERMISSIONS_MATRIX.get(role_name, [])