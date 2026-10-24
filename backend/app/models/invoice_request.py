"""
手动开票申请模型 - 用户端云端契约 §5 (工作卡 a09f8a21)

用户对已支付充电订单提交开票申请 → 运营商手动开票(上传发票文件) → ISSUED 推送通知;
或拒绝 REJECTED (用户可对同一订单重新申请, 新建一条 InvoiceRequest)。

状态机:
    PENDING ──upload──▶ ISSUED   (运营上传发票文件)
    PENDING ──reject──▶ REJECTED (用户可重新申请: 新建 InvoiceRequest)

⚠️ 金额单位: amount 为「分」整数 (契约 §6 通用约定: 金额分为单位整数)。
与 OpsInvoice.amount(元 Numeric) 不同 —— 本表面向 C 端用户端契约, 全程分。
汇总时由 service 层 sum(paid_amount[元]) → int(round(sum * 100)) 落库。
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    DateTime,
    Enum as SAEnum,
    Index,
    Text,
    ForeignKey,
)
import enum

from app.core.database import Base


class InvoiceRequestStatus(str, enum.Enum):
    """开票申请状态: pending → issued/rejected (rejected 后用户可重申, 新建一条)。"""
    PENDING = "pending"
    ISSUED = "issued"
    REJECTED = "rejected"


class InvoiceMode(str, enum.Enum):
    """开票通道: manual(线下手动) / auto(电子发票API, 将来启用)。当前全 manual。"""
    MANUAL = "manual"
    AUTO = "auto"


class InvoiceTitleType(str, enum.Enum):
    """抬头类型: personal(个人) / company(企业)。"""
    PERSONAL = "personal"
    COMPANY = "company"


class InvoiceFileType(str, enum.Enum):
    """发票文件类型: pdf / ofd / image(jpg/png)。"""
    PDF = "pdf"
    OFD = "ofd"
    IMAGE = "image"


class InvoiceRequest(Base):
    """开票申请表 (C 端用户提交, 运营 /ops/invoice-requests 处理)。"""
    __tablename__ = "invoice_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 关联订单 (order_no 列表, JSON 数组字符串; 一条申请可合并多单)
    order_ids = Column(Text, nullable=False, comment="关联订单号列表(JSON 数组)")
    user_id = Column(Integer, nullable=True, index=True, comment="申请人用户ID")
    # team 隔离: 创建时由订单 station→team 捕获, 供 /ops 列表按 team 过滤
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True, comment="归属团队(订单站点team)")
    # 抬头信息
    title_type = Column(
        SAEnum(InvoiceTitleType),
        nullable=False,
        default=InvoiceTitleType.PERSONAL,
        comment="抬头类型",
    )
    title_name = Column(String(200), nullable=False, comment="发票抬头名称")
    tax_number = Column(String(50), nullable=True, comment="税号(company 必填)")
    email = Column(String(120), nullable=True, comment="收票邮箱(选填, 填了则开票后自动发邮件)")
    remark = Column(String(500), nullable=True, comment="申请备注")
    # 金额(分整数, 契约 §6)
    amount = Column(Integer, nullable=False, default=0, comment="开票金额(分)")
    # 开票通道
    invoice_mode = Column(
        SAEnum(InvoiceMode),
        nullable=False,
        default=InvoiceMode.MANUAL,
        comment="开票通道 manual/auto",
    )
    # 状态
    status = Column(
        SAEnum(InvoiceRequestStatus),
        nullable=False,
        default=InvoiceRequestStatus.PENDING,
        comment="申请状态",
    )
    # 发票文件(运营上传)
    invoice_file_path = Column(String(500), nullable=True, comment="发票文件磁盘相对路径")
    invoice_file_name = Column(String(255), nullable=True, comment="发票文件原始名")
    invoice_file_type = Column(
        SAEnum(InvoiceFileType),
        nullable=True,
        comment="发票文件类型 pdf/ofd/image",
    )
    # 审核信息(reviewed_by/at 在 ISSUED 或 REJECTED 时写入)
    reviewed_by = Column(Integer, nullable=True, comment="处理人(运营)用户ID")
    reviewed_at = Column(DateTime, nullable=True, comment="处理时间(UTC)")
    reject_reason = Column(String(500), nullable=True, comment="拒绝原因(REJECTED 时)")
    # 红冲标记 (Phase2-B2, 卡 f42bdf5a; R1 方案b: status 三态不变, 红冲只打标)
    voided = Column(Boolean, nullable=False, default=False, server_default="0",
                    comment="已红冲(仅 ISSUED 发票可红冲)")
    void_reason = Column(String(500), nullable=True, comment="红冲原因")
    voided_by = Column(Integer, nullable=True, comment="红冲操作人(运营)用户ID")
    voided_at = Column(DateTime, nullable=True, comment="红冲时间(UTC)")
    # 时间
    applied_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment="申请时间(UTC)",
    )
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment="创建时间(UTC)",
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="更新时间(UTC)",
    )

    __table_args__ = (
        Index("ix_invoice_requests_user", "user_id"),
        Index("ix_invoice_requests_team", "team_id"),
        Index("ix_invoice_requests_status", "status"),
        Index("ix_invoice_requests_applied", "applied_at"),
    )
