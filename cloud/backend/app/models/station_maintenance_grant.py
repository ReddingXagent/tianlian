"""运维分离架构 — 场站运维授权表 (任务卡 00d7d49a)。

StationMaintenanceGrant: 运营公司 (OPS_COMPANY) 把某场站的运维工作授权给独立第三方
运维团队 (MAINTENANCE_TEAM), 实现「运营/运维」三权分离:

  - 模式① 自运维: 运营+运维同一团队 (Station.team_id = 运营公司 team), 无需 grant。
  - 模式② 委外运维: 运营公司仅运营, 经本表把运维权限授予第三方运维团队。

授权维度:
  - scope: full / monitoring_only / maintenance_only
      · full             — 监控 + 维护(控制/检修) 全权
      · monitoring_only  — 仅监控(只读设备状态/告警), 不可控制设备
      · maintenance_only — 仅维护(控制/检修/工单), 不含监控看板 (可叠加另一条 grant 补监控)
  - status: active / revoked / expired
      · active  — 当前有效
      · revoked — 被授权方主动撤销 (DELETE 软删除, 保留留痕)
      · expired — 超过 expires_at 自动失效 (查询时按墙钟判定)

设计同 EnterpriseDeviceGrant (卡 a1468299): 独立授权表, FK 引用完整性 +
表式建模表达权限关系。唯一索引 (station_id, maintenance_team_id) 杜绝重复授权。
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum, Index,
)
from sqlalchemy.sql import func

from app.core.database import Base


class GrantScope(str, enum.Enum):
    """授权范围。"""
    FULL = "full"                      # 监控 + 维护 全权
    MONITORING_ONLY = "monitoring_only"  # 仅监控(只读)
    MAINTENANCE_ONLY = "maintenance_only"  # 仅维护(控制/检修/工单)


class GrantStatus(str, enum.Enum):
    """授权状态。"""
    ACTIVE = "active"      # 当前有效
    REVOKED = "revoked"    # 已撤销 (软删除)
    EXPIRED = "expired"    # 已过期


# scope 白名单: 各 scope 允许的操作类别 (供 assert_maintenance_access 判定)。
#   action ∈ {"monitor", "control"}
#     · monitor — 只读访问(看设备状态/告警/工单详情)
#     · control — 写操作(控制设备/创建工单/处置告警)
# monitoring_only 不含 control → 控制类写操作被拒。
SCOPE_ALLOWED_ACTIONS: dict[GrantScope, set[str]] = {
    GrantScope.FULL: {"monitor", "control"},
    GrantScope.MONITORING_ONLY: {"monitor"},
    GrantScope.MAINTENANCE_ONLY: {"control"},
}


class StationMaintenanceGrant(Base):
    """场站运维授权表 — 运营公司 → 第三方运维团队。"""
    __tablename__ = "station_maintenance_grants"

    id = Column(Integer, primary_key=True, autoincrement=True)

    station_id = Column(
        Integer, ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="被授权的场站",
    )
    maintenance_team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="被授权的运维团队 (须为 maintenance_team)",
    )
    granted_by_team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="授权方运营公司 (须为 ops_company)",
    )

    scope = Column(
        SQLEnum(GrantScope, values_callable=lambda x: [m.value for m in x]),
        nullable=False, default=GrantScope.FULL, server_default="full",
        comment="授权范围: full/monitoring_only/maintenance_only",
    )
    status = Column(
        SQLEnum(GrantStatus, values_callable=lambda x: [m.value for m in x]),
        nullable=False, default=GrantStatus.ACTIVE, server_default="active",
        index=True, comment="授权状态: active/revoked/expired",
    )

    granted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False,
                        comment="授权时间")
    revoked_at = Column(DateTime(timezone=True), nullable=True, comment="撤销时间")
    expires_at = Column(DateTime(timezone=True), nullable=True, comment="过期时间(空=永久)")
    remark = Column(String(500), nullable=True, comment="授权备注")

    __table_args__ = (
        # 同场站对同运维团队唯一: 一条 active 授权, 撤销后可重新授权
        # (唯一索引不区分 status, 故撤销后重授权须用新行 + 旧行已改 revoked, 不冲突)
        Index("ix_smg_station_maint_team", "station_id", "maintenance_team_id", unique=True),
        Index("ix_smg_granted_by", "granted_by_team_id"),
    )
