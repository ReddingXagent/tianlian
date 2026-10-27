"""
租户用量统计模型 (admin-platform-spec)

- tenant_usage: 按日记录每个租户的资源用量快照（站点/设备/用户数、存储、API 调用）。
- 由定时任务或手动触发写入，供 GET /api/v1/tenants/{id}/usage 查询趋势。
- 实时用量（当前站点/设备/用户数）由 services.tenant_usage_service 聚合计算，
  不在此表落库。
"""
from sqlalchemy import Column, Integer, Float, Date, DateTime, ForeignKey, Index
from datetime import datetime, timezone
from app.core.database import Base


class TenantUsage(Base):
    """租户用量表 - 每租户每日一条用量快照"""
    __tablename__ = "tenant_usage"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, comment="租户ID")
    record_date = Column(Date, nullable=False, comment="记录日期")

    # 用量指标
    station_count = Column(Integer, default=0, comment="站点数")
    device_count = Column(Integer, default=0, comment="设备数")
    user_count = Column(Integer, default=0, comment="用户数")
    storage_used_gb = Column(Float, default=0.0, comment="存储用量(GB)")
    api_calls_today = Column(Integer, default=0, comment="当日API调用数")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # 每租户每日唯一，防止重复快照
        Index('idx_tenant_usage_tenant_date', 'tenant_id', 'record_date', unique=True),
    )
