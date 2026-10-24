"""
天链智能体记忆模型 (设计文档 §5.2)

两张表:
- agent_memory: 巡检发现 / 诊断结论 / 经验积累, 是智能体的"长期记忆"
- agent_conversation: 三板块助手对话历史, 是智能体的"短期对话上下文"

注意: 列名 `metadata` 是 SQLAlchemy 声明类的保留属性, 不能直接用作 Python
属性名; 这里用 Python 属性 `meta_info` 映射到 DB 列 `metadata`
(Column("metadata", ...))。读写统一用 obj.meta_info。
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Index,
)
from sqlalchemy.sql import func

from app.core.database import Base


class AgentMemory(Base):
    """智能体记忆 — 巡检发现 / 诊断结论 / 经验积累

    board: maintenance / operations / admin 三板块
    category: finding(发现) / diagnosis(诊断) / decision(决策) / learning(经验)
    status: open(待处理) / acknowledged(已确认) / resolved(已解决)
    severity: info / warning / critical
    """
    __tablename__ = "agent_memory"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    board = Column(String(20), nullable=False, comment="板块: maintenance/operations/admin")
    category = Column(String(50), nullable=False, comment="类别: finding/diagnosis/decision/learning")
    source = Column(String(100), nullable=True, comment="来源标识, 如 patrol:device_offline")

    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)

    severity = Column(String(20), default="info", comment="info/warning/critical")
    # 注意: SQLAlchemy 声明类保留 `metadata`, 此处 Python 属性用 meta_info,
    # 映射到 DB 列 metadata (与设计文档 §5.2 列名一致)。
    # 显式 key="meta_info": Python 属性名; 第一个位置参数 "metadata": DB 列名。
    meta_info = Column("metadata", JSON, key="meta_info", default=dict, comment="结构化扩展信息")
    importance = Column(Float, default=0.5, comment="重要度 0-1")

    related_type = Column(String(50), nullable=True, comment="关联对象类型: device/order/station/system")
    related_id = Column(String(100), nullable=True, comment="关联对象 ID")

    status = Column(String(20), default="open", comment="open/acknowledged/resolved")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_memory_team_board", "team_id", "board", created_at.desc()),
        Index("idx_memory_team_status", "team_id", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "team_id": self.team_id,
            "board": self.board,
            "category": self.category,
            "source": self.source,
            "title": self.title,
            "content": self.content,
            "severity": self.severity,
            "metadata": self.meta_info,
            "importance": self.importance,
            "related_type": self.related_type,
            "related_id": self.related_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class AgentConversation(Base):
    """智能体对话历史 — 三板块助手的上下文记忆

    role: user / assistant / system
    tool_calls: function calling 调用记录 (JSON)
    """
    __tablename__ = "agent_conversation"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    board = Column(String(20), nullable=False, comment="板块: maintenance/operations/admin")
    role = Column(String(20), nullable=False, comment="user/assistant/system")

    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True, comment="function calling 调用记录")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_convo_team_board", "team_id", "board", created_at.desc()),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "team_id": self.team_id,
            "user_id": self.user_id,
            "board": self.board,
            "role": self.role,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
