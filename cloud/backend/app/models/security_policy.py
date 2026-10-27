"""
安全策略模型 - admin-platform-spec §2.7 安全管理

security_policies 表存放各类安全策略的 JSON 配置:
- password: 密码强度/过期
- login:   登录失败锁定
- session: 会话超时/并发
- ip:      IP 白/黑名单
"""
from typing import Any, Dict, Optional

from sqlalchemy import Column, DateTime, Integer, JSON, String
from sqlalchemy.sql import func

from app.core.database import Base


# 允许的策略类型
VALID_POLICY_KEYS = {"password", "login", "session", "ip"}
# 允许的策略状态
VALID_POLICY_STATUS = {"active", "disabled"}


class SecurityPolicy(Base):
    """安全策略表"""
    __tablename__ = "security_policies"

    id = Column(Integer, primary_key=True)  # PK 自带唯一索引, 无需冗余 index=True (消除 schema 漂移告警)
    policy_key = Column(String(50), unique=True, nullable=False, index=True)
    policy_config = Column(JSON, nullable=False, default=dict)
    description = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="active")  # active / disabled

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "policy_key": self.policy_key,
            "policy_config": self.policy_config or {},
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def default_security_policies() -> list:
    """默认安全策略种子数据 (供 alembic 迁移与初始化复用)。"""
    return [
        {
            "policy_key": "password",
            "policy_config": {
                "min_length": 8,
                "require_upper": True,
                "require_digit": True,
                "expire_days": 90,
            },
            "description": "密码强度与过期策略",
            "status": "active",
        },
        {
            "policy_key": "login",
            "policy_config": {
                "fail_lock_count": 5,
                "lock_duration_minutes": 30,
            },
            "description": "登录失败锁定策略",
            "status": "active",
        },
        {
            "policy_key": "session",
            "policy_config": {
                "session_timeout_minutes": 480,
                "concurrent_session_limit": 3,
            },
            "description": "会话超时与并发限制策略",
            "status": "active",
        },
        {
            "policy_key": "ip",
            "policy_config": {
                "whitelist": [],
                "blacklist": [],
                "enable_ip_restrict": False,
            },
            "description": "IP 访问控制策略",
            "status": "active",
        },
    ]


def seed_security_policies(session) -> Optional[int]:
    """向给定 session 插入默认安全策略 (已存在的 policy_key 跳过)。
    返回新增行数。供初始化/迁移 Python 路径复用。"""
    inserted = 0
    existing = {row.policy_key for row in session.query(SecurityPolicy).all()}
    for item in default_security_policies():
        if item["policy_key"] in existing:
            continue
        session.add(SecurityPolicy(**item))
        inserted += 1
    if inserted:
        session.commit()
    return inserted
