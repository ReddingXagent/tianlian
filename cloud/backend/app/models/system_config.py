"""
系统配置模型 - system_configs 表的 ORM 占位

⚠️ 当前 system_configs 表仍由 app/api/v1/system_config/common.py 通过 raw SQL(text()) 访问,
   本 model 仅作 ORM 占位注册, 供后续迁移把 raw SQL 收敛到 ORM 时使用 (D8 顺手补齐)。
   故列定义与现有 raw SQL 兼容:
   - config_type 显式映射到现有 DB 列 ``type`` (common.py INSERT/SELECT 均按 ``type`` 操作)
   - config_value 用 JSON 类型 (SQLite 下底层 TEXT, 与 common.py 存 JSON 字符串兼容)
   - description 为新增列, common.py 不涉及, 不破坏现有逻辑
"""
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.core.database import Base


class SystemConfig(Base):
    """系统配置表 (键值 JSON 配置存储)"""
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(100), unique=True, nullable=False, index=True)
    config_value = Column(JSON, nullable=False, default=dict)
    description = Column(String(255), nullable=True)
    # 映射现有 DB 列名 ``type`` (common.py raw SQL 使用), Python 属性用 config_type
    config_type = Column("type", String(50), nullable=False, default="global")
    # 多租户隔离 (卡 cf614348): NULL = 平台级配置 (全可见); 否则归属该 team。
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "config_key": self.config_key,
            "config_value": self.config_value or {},
            "description": self.description,
            "config_type": self.config_type,
            "team_id": self.team_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
