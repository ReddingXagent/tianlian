"""企业注册申请单 (卡 c8f7be6f)

企业提交注册申请 → 平台 admin 审批 → approve 建 Subject + ops_company Team + 企业
admin User(apply_scope 含 maintenance 时同主体再建 maintenance_team Team)。

status 流转: pending → approved / rejected。approve 幂等: 重复 approve 返回已创建
结果, 不重复建 Subject/Team/User。
"""
import enum

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Enum as SQLEnum
from sqlalchemy.sql import func

from app.core.database import Base


class ApplyScope(str, enum.Enum):
    """企业申请开通的业务范围"""
    OPS = "ops"            # 仅运营
    MAINTENANCE = "maintenance"  # 仅运维
    BOTH = "both"          # 运营 + 运维


class RegistrationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RegistrationApplication(Base):
    """企业注册申请单"""
    __tablename__ = "registration_applications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    company_name = Column(String(200), nullable=False, comment="企业名称")
    credit_code = Column(String(18), nullable=False, index=True, comment="统一社会信用代码(18位)")
    license_file_path = Column(String(500), nullable=True, comment="营业执照文件路径")
    legal_person = Column(String(100), nullable=True, comment="法人代表")
    contact_name = Column(String(100), nullable=False, comment="联系人姓名")
    contact_phone = Column(String(20), nullable=False, index=True, comment="联系电话")
    contact_email = Column(String(120), nullable=True, comment="联系邮箱")
    password_hash = Column(String(255), nullable=False, comment="初始账户密码 hash")

    apply_scope = Column(
        SQLEnum(ApplyScope, values_callable=lambda x: [m.value for m in x]),
        nullable=False,
        default=ApplyScope.BOTH,
        comment="申请开通范围",
    )
    status = Column(
        SQLEnum(RegistrationStatus, values_callable=lambda x: [m.value for m in x]),
        nullable=False,
        default=RegistrationStatus.PENDING,
        server_default="pending",
        index=True,
        comment="审批状态",
    )

    # 协议同意留痕 (任务卡: 必须 agreed_to_terms=true + 记录 agreement_version)
    agreed_to_terms = Column(Boolean, default=False, nullable=False, comment="是否同意平台协议")
    agreement_version = Column(String(50), nullable=True, comment="同意的协议版本")

    # 审批信息
    reviewer_id = Column(Integer, nullable=True, comment="审批人 user id")
    review_remark = Column(Text, nullable=True, comment="审批备注/拒绝理由")
    subject_id = Column(Integer, nullable=True, index=True, comment="审批通过后创建的主体 id(回链)")

    applied_at = Column(DateTime(timezone=True), server_default=func.now(), comment="申请时间")
    reviewed_at = Column(DateTime(timezone=True), nullable=True, comment="审批时间")
