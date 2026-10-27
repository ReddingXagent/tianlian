"""C端用户收藏场站模型 (用户端契约§8 P2 §8.7, 卡 36396f29).

(end_user_id, station_id) unique —— 一人一站一条, 端点层幂等语义见契约 §8.7.
"""

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.core.database import Base


class EndUserFavorite(Base):
    """C 端用户收藏的公开场站."""

    __tablename__ = "end_user_favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    end_user_id = Column(Integer, ForeignKey("end_users.id"), nullable=False, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("end_user_id", "station_id", name="uq_end_user_favorite_station"),
    )
