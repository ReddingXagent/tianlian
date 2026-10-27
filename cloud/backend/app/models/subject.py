"""企业主体模型 (卡 c8f7be6f)

注册审批通过后, 为每家企业创建一个主体(Subject), 作为 Team.owner_subject_id 的指向
目标, 把同一公司下不同 type 的 Team(ops_company / maintenance_team / fleet) 关联为
同一主体的多角色。Team.owner_subject_id 是逻辑外键(无 FK 约束, 平台级可空), 指向
本表 id —— 与卡 cf614348 的「同主体多角色」设计一致。

Subject 独立于 Enterprise: Enterprise 是车队/运营企业账户(带余额/编码/owner_team_id
反向引用), 语义不符「公司主体」; Subject 是组织层级里串起多 Team 的轻量逻辑根。
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Subject(Base):
    """企业主体 — 同一公司实体的逻辑根, 串起其下多个不同 type 的 Team。"""
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    company_name = Column(String(200), nullable=False, index=True, comment="企业名称")
    credit_code = Column(String(18), nullable=True, index=True, comment="统一社会信用代码")
    status = Column(String(20), default="active", nullable=False, comment="主体状态")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
