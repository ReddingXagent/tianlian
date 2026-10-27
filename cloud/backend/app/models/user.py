"""
用户与组织架构模型 (重构编码生成)
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum, Float, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"  # 超级管理员(跨租户)
    ADMIN = "admin"              # 租户管理员
    DISPATCHER = "dispatcher"    # 调度员
    STATION_MASTER = "station_master"  # 站长
    ENGINEER = "engineer"        # 工程师
    OPERATOR = "operator"        # 运维操作员
    VIEWER = "viewer"            # 只读用户
    TECHNICIAN = "technician"  # 现场技术员
    AUDITOR = "auditor"          # 审计员

class EngineerLevel(str, enum.Enum):
    JUNIOR = "junior"    # 初级
    MIDDLE = "middle"    # 中级
    SENIOR = "senior"    # 高级

class TeamType(str, enum.Enum):
    """组织层级类型 (卡 cf614348): 平台 → 运营公司 → 运维团队/车队。

    存量 Team 默认 ops_company (Alembic 迁移回填)。同一公司实体可挂多个不同 type
    的 Team, 经 owner_subject_id 关联 (同主体多角色)。
    """
    OPS_COMPANY = "ops_company"                # 运营公司 (顶层运营主体)
    MAINTENANCE_TEAM = "maintenance_team"      # 运维团队 (挂在运营公司下)
    FLEET = "fleet"                            # 车队 (挂在运营公司下)

class Team(Base):
    """运维团队表"""
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    code = Column(String(20), unique=True, index=True, nullable=True)  # 新增编码字段
    leader_id = Column(Integer, ForeignKey("users.id"), index=True)
    description = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 多租户组织层级 (卡 cf614348):
    # - type: 本 team 在层级中的角色; 存量数据默认 ops_company。
    # - parent_team_id: fleet/maintenance_team 指向所属运营公司 Team (self-FK)。
    # - owner_subject_id: 同一公司主体可关联多个不同 type 的 Team (多角色), 平台级可为空。
    type = Column(
        SQLEnum(TeamType, values_callable=lambda x: [m.value for m in x]),
        nullable=False,
        default=TeamType.OPS_COMPANY,
        server_default="ops_company",
        index=True,
    )
    parent_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    owner_subject_id = Column(Integer, nullable=True, index=True)

    # 二次验证(2FA, 任务卡 78c7404b): 团队级开关。默认关闭, 开启后该团队成员密码
    # 登录需额外短信验证码(两步登录)。method 当前仅 'sms', 预留扩展位。
    # nullable=False + server_default 保证存量数据迁移后即 False, 不影响现有登录路径。
    second_factor_enabled = Column(Boolean, default=False, nullable=False, server_default="0")
    second_factor_method = Column(String(20), default="sms", nullable=False, server_default="sms")

    # 关系
    members = relationship("User", foreign_keys="User.team_id", back_populates="team")
    stations = relationship("Station", foreign_keys="Station.team_id", back_populates="team")

class User(Base):
    """用户表 - 支持多租户"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    real_name = Column(String(100))
    phone = Column(String(20), index=True)
    email = Column(String(120), index=True, nullable=True)
    role = Column(SQLEnum(UserRole, values_callable=lambda x: [m.value for m in x]), default=UserRole.ENGINEER)
    level = Column(SQLEnum(EngineerLevel, values_callable=lambda x: [m.value for m in x]), default=EngineerLevel.JUNIOR)  # 工程师等级
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    
    # 工程师扩展信息
    skills = Column(Text, default='[]')  # JSON: ["充电桩", "高压电工"]
    latitude = Column(Float, nullable=True)  # 当前纬度
    longitude = Column(Float, nullable=True)  # 当前经度
    last_location_time = Column(DateTime(timezone=True), nullable=True)  # 最后位置更新时间
    
    # 多租户支持
    # tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True, comment="所属租户")
    # is_tenant_admin = Column(Boolean, default=False, comment="是否租户管理员")
    
    last_login = Column(DateTime(timezone=True), nullable=True)  # 最后登录时间

    # 登录失败锁定 (D8 爆破防护, spec admin§2.1)
    login_fail_count = Column(Integer, default=0, nullable=False)  # 连续失败计数, 达5触发锁定
    last_login_ip = Column(String(45), nullable=True)  # 最近一次成功登录 IP (IPv6 长度)
    locked_until = Column(DateTime, nullable=True)  # 锁定截止时间, 过期自动解锁

    status = Column(String(20), default="active")  # active/inactive/suspended

    # 会话固定防护 (卡 5d6a978b): 密码重置时递增, 已签发 JWT 内嵌 tv claim,
    # 每请求鉴权比对不一致即 401 → 改密后旧 token 立即驱逐。存量用户/旧 token
    # 均为 0, 向后兼容零影响。
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    # tenant = relationship("Tenant", back_populates="users")
    
    # 关系
    team = relationship("Team", foreign_keys=[team_id], back_populates="members")
    assigned_roles = relationship("RoleTable", secondary="user_roles", back_populates="users")
    assigned_workorders = relationship("WorkOrder", foreign_keys="WorkOrder.assignee_id", back_populates="assignee")
    created_workorders = relationship("WorkOrder", foreign_keys="WorkOrder.creator_id", back_populates="creator")
    operated_stations = relationship("Station", foreign_keys="Station.operator_id", back_populates="operator")
    maintenance_records = relationship("MaintenanceRecord", foreign_keys="MaintenanceRecord.engineer_id", back_populates="engineer")