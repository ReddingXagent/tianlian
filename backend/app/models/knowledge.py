"""
知识库模型
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

class KnowledgeArticle(Base):
    """知识文章表"""
    __tablename__ = "knowledge_articles"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    category = Column(String(50), index=True)  # 分类（字符串，向后兼容）
    category_id = Column(Integer, ForeignKey("knowledge_categories.id"), nullable=True, index=True)  # 分类ID（FK）
    content = Column(Text, nullable=False)  # 富文本内容
    tags = Column(String(500))  # 标签（逗号分隔）
    
    # 作者
    author_id = Column(Integer, ForeignKey("users.id"), index=True)

    # 统计
    view_count = Column(Integer, default=0)
    
    # 状态
    published = Column(Boolean, default=False)

    # 数据隔离: 0=平台共享(全平台可见), >0=企业专属(仅本企业可见)
    team_id = Column(Integer, default=0, index=True)

    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关联
    category_rel = relationship("KnowledgeCategory", backref="articles", foreign_keys=[category_id])


class KnowledgeCategory(Base):
    """知识库分类表"""
    __tablename__ = "knowledge_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)  # 分类名称
    icon = Column(String(50), default="")  # 图标（emoji或icon名称）
    sort_order = Column(Integer, default=0)  # 排序
    description = Column(String(500), default="")  # 描述
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class KnowledgeFAQ(Base):
    """知识库FAQ表"""
    __tablename__ = "knowledge_faq"
    
    id = Column(Integer, primary_key=True, index=True)
    question = Column(String(500), nullable=False, index=True)  # 问题
    answer = Column(Text, nullable=False)  # 答案
    category = Column(String(50), index=True)  # 分类：设备类/告警类/工单类/系统类
    tags = Column(String(500))  # 标签（逗号分隔）

    # 数据隔离: 0=平台共享(全平台可见), >0=企业专属(仅本企业可见)
    team_id = Column(Integer, default=0, index=True)

    # 统计
    views = Column(Integer, default=0)  # 浏览次数
    helpful_count = Column(Integer, default=0)  # 有用次数
    
    # 作者
    author_id = Column(Integer, ForeignKey("users.id"))
    
    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
