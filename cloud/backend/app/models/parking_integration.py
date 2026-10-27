"""
停车场系统对接集成配置 - 任务卡 309b4132

商户站点与外部停车场系统的对接凭证：每个站点一对 app_key/app_secret，
开放API（/open/parking/*）凭此独立鉴权（不走 user JWT）。
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SAEnum, Index, ForeignKey

from app.core.database import Base


class IntegrationMode(str, enum.Enum):
    """对接模式：A=查询+留痕 / B=仅留痕"""
    A = "A"
    B = "B"


class ParkingIntegrationConfig(Base):
    """停车对接集成配置表 - 每站点一对独立凭证"""
    __tablename__ = "parking_integration_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True, comment="商户站点ID")
    provider_name = Column(String(100), nullable=True, comment="停车场系统名称")
    app_key = Column(String(100), nullable=False, unique=True, index=True, comment="对接标识(app_key)")
    app_secret = Column(String(200), nullable=False, comment="对接密钥(app_secret)")
    integration_mode = Column(SAEnum(IntegrationMode), nullable=False, default=IntegrationMode.A,
                              comment="对接模式 A=查询+留痕/B=仅留痕")
    allow_query = Column(Boolean, nullable=False, default=True, comment="是否允许查询(关闭则403)")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否启用(关闭则401)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_pic_station", "station_id"),
        Index("idx_pic_active", "is_active"),
    )
