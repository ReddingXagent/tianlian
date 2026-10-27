"""
企业充值申请模型 - 运营管理
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Enum as SAEnum, Index
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base


class RechargeStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RechargeApplication(Base):
    """企业充值申请表"""
    __tablename__ = "enterprise_recharge_applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, comment="企业ID")
    amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="申请金额(元)")
    proof_image = Column(String(500), nullable=True, comment="转账证明图片URL")
    status = Column(SAEnum(RechargeStatus), default=RechargeStatus.PENDING, comment="状态: pending/approved/rejected")
    remark = Column(String(500), nullable=True, comment="备注")
    applicant = Column(String(100), nullable=True, comment="申请人")
    approver = Column(String(100), nullable=True, comment="审批人")
    approve_reason = Column(String(500), nullable=True, comment="审批通过理由")
    reject_reason = Column(String(500), nullable=True, comment="拒绝原因")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    enterprise = relationship("Enterprise", backref="recharge_applications")

    __table_args__ = (
        Index("idx_era_enterprise", "enterprise_id"),
        Index("idx_era_status", "status"),
    )

    def to_dict(self):
        """序列化为可直接 JSON 化的 dict。

        避免 ORM 对象直接进响应：FastAPI jsonable_encoder 对未知对象走 __dict__ 隐式
        回退，行为随依赖版本漂移（历史曾非空 500），且会泄漏 _sa_instance_state 等内部
        状态、字段名与契约脱钩。任务卡 2fb8594a。
        """
        return {
            "id": self.id,
            "enterprise_id": self.enterprise_id,
            "amount": float(self.amount) if self.amount is not None else None,
            "proof_image": self.proof_image,
            "status": self.status.value if self.status else None,
            "remark": self.remark,
            "applicant": self.applicant,
            "approver": self.approver,
            "approve_reason": self.approve_reason,
            "reject_reason": self.reject_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }