"""
运营侧发票模型 - SPEC §2.5 + §4

发票申请 → 审核 → 开具 → (红冲作废)
状态流转: pending → reviewed → issued → voided / rejected
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Enum as SAEnum, Index, Text
import enum

from app.core.database import Base


class OpsInvoiceStatus(str, enum.Enum):
    """发票状态: pending(待审核) → reviewed(审核通过) → issued(已开具) → voided(已红冲)"""
    PENDING = "pending"
    REVIEWED = "reviewed"
    ISSUED = "issued"
    VOIDED = "voided"
    REJECTED = "rejected"


class OpsInvoiceType(str, enum.Enum):
    """发票类型: electronic(电子发票) / paper(纸质发票)"""
    ELECTRONIC = "electronic"
    PAPER = "paper"


class OpsInvoice(Base):
    """运营侧发票表"""
    __tablename__ = "ops_invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 申请信息
    applicant_name = Column(String(100), nullable=True, comment="申请人姓名")
    applicant_phone = Column(String(20), nullable=True, comment="申请人手机")
    apply_source = Column(String(20), default="admin", comment="申请来源(app/admin)")
    # 开票内容
    order_ids = Column(Text, nullable=True, comment="关联订单ID列表(JSON)")
    invoice_title_id = Column(Integer, nullable=True, comment="关联抬头ID")
    title_name = Column(String(200), nullable=False, comment="发票抬头(冗余)")
    tax_id = Column(String(50), nullable=True, comment="税号(冗余)")
    amount = Column(Numeric(12, 2), nullable=False, comment="开票金额(元)")
    invoice_type = Column(SAEnum(OpsInvoiceType), default=OpsInvoiceType.ELECTRONIC, comment="发票类型")
    # 开票结果
    invoice_no = Column(String(50), nullable=True, comment="发票号码")
    invoice_code = Column(String(50), nullable=True, comment="发票代码")
    pdf_url = Column(String(500), nullable=True, comment="发票PDF链接")
    # 状态流转
    status = Column(SAEnum(OpsInvoiceStatus), default=OpsInvoiceStatus.PENDING, comment="发票状态")
    # 审核信息
    reviewer_id = Column(Integer, nullable=True, comment="审核人ID")
    review_time = Column(DateTime, nullable=True, comment="审核时间")
    review_remark = Column(String(500), nullable=True, comment="审核备注")
    # 开票信息
    issue_time = Column(DateTime, nullable=True, comment="开票时间")
    issued_by = Column(String(100), nullable=True, comment="开票人")
    # 红冲信息
    void_reason = Column(String(500), nullable=True, comment="红冲原因")
    void_time = Column(DateTime, nullable=True, comment="红冲时间")
    # 时间
    apply_time = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="申请时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_oi_status", "status"),
        Index("idx_oi_title", "title_name"),
        Index("idx_oi_apply_time", "apply_time"),
    )
