"""忘记密码申请表 (卡 922b2fba)

POST /auth/forgot-password 匿名提交, 落库 pending, 由平台管理员在
GET /auth/forgot-password/requests 查看、POST .../resolve 线下处理后关闭。
不存任何令牌/哈希 — 重置动作本身仍走管理员 reset-password 端点。
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class PasswordResetRequest(Base):
    """忘记密码申请"""
    __tablename__ = "password_reset_requests"

    id = Column(Integer, primary_key=True, index=True)
    account = Column(String(100), nullable=False, index=True)  # 用户名/手机号原文
    status = Column(String(20), default="pending", nullable=False)  # pending/resolved
    handled_by = Column(Integer)  # 处理人 user_id
    created_at = Column(DateTime, server_default=func.now())
