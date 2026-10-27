"""
天链智能体记忆服务 (设计文档 §5.2)

为巡检任务 (agent_patrol) 和助手对话 (ai_chat) 提供:
- 巡检发现 / 诊断结论 / 经验的持久化与检索 (agent_memory)
- 对话历史的持久化与回放 (agent_conversation)

前期用 ILIKE 关键词搜索; 数据量大再加 pgvector (设计文档不做清单已明确)。

实现约定:
- 所有 datetime 用 UTC
- SessionLocal 在函数体内动态 import (避免 import-time 绑定到生产库,
  conftest test_db fixture override 模块级 SessionLocal 才能对服务层生效,
  参见 memory: service-sessionlocal-import-binding)
- team_id 强校验非空 (多租户隔离红线, 防跨租户记忆污染)
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import or_

from app.models.agent_memory import AgentMemory, AgentConversation

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    """当前 UTC 时间 (aware)"""
    return datetime.now(timezone.utc)


def _new_session():
    """取最新 SessionLocal (函数内 import, 兼容测试 override)"""
    from app.core.database import SessionLocal
    return SessionLocal()


def save_memory(
    team_id: int,
    board: str,
    category: str,
    title: str,
    content: str,
    *,
    source: Optional[str] = None,
    severity: str = "info",
    metadata: Optional[dict] = None,
    importance: float = 0.5,
    related_type: Optional[str] = None,
    related_id: Optional[str] = None,
    status: str = "open",
    expires_at: Optional[datetime] = None,
) -> AgentMemory:
    """写入一条智能体记忆 (巡检发现 / 诊断结论 / 经验)。

    Args:
        team_id: 租户 (隔离键, 必填)
        board: 板块 maintenance/operations/admin
        category: finding/diagnosis/decision/learning
        title: 标题
        content: 正文
        severity: info/warning/critical
        metadata: 结构化扩展信息 (映射到 DB 列 metadata, Python 属性 meta_info)
        related_type/related_id: 关联对象 (device/order/station/system)
    """
    if not team_id:
        # 多租户隔离红线: team_id 不可空, 否则记忆跨租户污染
        raise ValueError("save_memory: team_id 不能为空")

    mem = AgentMemory(
        team_id=team_id,
        board=board,
        category=category,
        source=source,
        title=title,
        content=content,
        severity=severity,
        meta_info=metadata or {},
        importance=importance,
        related_type=related_type,
        related_id=related_id,
        status=status,
        expires_at=expires_at,
    )
    session = _new_session()
    try:
        session.add(mem)
        session.commit()
        session.refresh(mem)
        return mem
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def save_conversation(
    team_id: int,
    board: str,
    role: str,
    content: str,
    *,
    user_id: Optional[int] = None,
    tool_calls: Optional[Any] = None,
) -> AgentConversation:
    """写入一条对话记录 (user/assistant/system)。

    tool_calls: function calling 调用记录, 序列化为 JSON 存储。
    """
    if not team_id:
        raise ValueError("save_conversation: team_id 不能为空")

    convo = AgentConversation(
        team_id=team_id,
        user_id=user_id,
        board=board,
        role=role,
        content=content,
        tool_calls=tool_calls,
    )
    session = _new_session()
    try:
        session.add(convo)
        session.commit()
        session.refresh(convo)
        return convo
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def search_memory(
    team_id: int,
    query: str,
    *,
    board: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
) -> list[AgentMemory]:
    """关键词搜索记忆 (ILIKE, 命中 title 或 content)。

    前期关键词搜索够用 (设计文档不做清单); 数据量大再加 pgvector 语义搜索。
    """
    if not team_id:
        raise ValueError("search_memory: team_id 不能为空")
    if not query or not query.strip():
        return []

    session = _new_session()
    try:
        pattern = f"%{query.strip()}%"
        q = (
            session.query(AgentMemory)
            .filter(AgentMemory.team_id == team_id)
            .filter(
                or_(
                    AgentMemory.title.ilike(pattern),
                    AgentMemory.content.ilike(pattern),
                )
            )
        )
        if board:
            q = q.filter(AgentMemory.board == board)
        if category:
            q = q.filter(AgentMemory.category == category)
        return (
            q.order_by(AgentMemory.created_at.desc(), AgentMemory.importance.desc())
            .limit(limit)
            .all()
        )
    finally:
        session.close()


def get_findings(
    team_id: int,
    *,
    board: Optional[str] = None,
    status: str = "open",
    limit: int = 50,
) -> list[AgentMemory]:
    """获取巡检发现列表 (默认查 open 状态, 按创建时间倒序)。"""
    if not team_id:
        raise ValueError("get_findings: team_id 不能为空")

    session = _new_session()
    try:
        q = (
            session.query(AgentMemory)
            .filter(AgentMemory.team_id == team_id)
            .filter(AgentMemory.category == "finding")
        )
        if board:
            q = q.filter(AgentMemory.board == board)
        if status:
            q = q.filter(AgentMemory.status == status)
        return q.order_by(AgentMemory.created_at.desc()).limit(limit).all()
    finally:
        session.close()


def update_finding_status(memory_id: int, status: str) -> AgentMemory:
    """更新记忆/发现状态 (open → acknowledged → resolved)。"""
    session = _new_session()
    try:
        mem = session.query(AgentMemory).filter(AgentMemory.id == memory_id).first()
        if not mem:
            raise ValueError(f"记忆 {memory_id} 不存在")
        mem.status = status
        mem.updated_at = _now_utc()
        session.commit()
        session.refresh(mem)
        return mem
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_conversation_history(
    team_id: int,
    board: str,
    *,
    user_id: Optional[int] = None,
    limit: int = 20,
) -> list[AgentConversation]:
    """获取对话历史 (按时间倒序, 最近在前)。"""
    if not team_id:
        raise ValueError("get_conversation_history: team_id 不能为空")

    session = _new_session()
    try:
        q = (
            session.query(AgentConversation)
            .filter(AgentConversation.team_id == team_id)
            .filter(AgentConversation.board == board)
        )
        if user_id:
            q = q.filter(AgentConversation.user_id == user_id)
        # created_at + id 双键倒序: 同事务内多条记录 created_at 可能完全相同
        # (SQLite server_default=func.now() 同值), 单按 created_at 倒序不稳定;
        # id 自增严格单调, 作为次序兜底保证对话插入顺序。
        return q.order_by(
            AgentConversation.created_at.desc(),
            AgentConversation.id.desc(),
        ).limit(limit).all()
    finally:
        session.close()
