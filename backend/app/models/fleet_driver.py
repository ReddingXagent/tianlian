"""
车队司机管理模型 - Phase44 司机管理

包含:
- FleetDriver: 车队司机
- FleetDriverAccount: 司机个人账户
- FleetDriverTransaction: 司机账户交易流水
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Enum as SAEnum, Index
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class DriverStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class LicenseType(str, enum.Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class DriverTransactionType(str, enum.Enum):
    RECHARGE = "recharge"
    CONSUME = "consume"
    REFUND = "refund"


class FleetDriver(Base):
    """车队司机表 - 企业下属司机信息"""
    __tablename__ = "fleet_drivers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, comment="所属企业ID")
    name = Column(String(100), nullable=False, comment="司机姓名")
    phone = Column(String(20), nullable=False, comment="手机号")
    license_no = Column(String(50), nullable=False, comment="驾驶证号")
    license_type = Column(SAEnum(LicenseType), nullable=False, default=LicenseType.C1, comment="准驾车型")
    assigned_vehicle_id = Column(Integer, ForeignKey("enterprise_vehicles.id"), nullable=True, index=True, comment="分配车辆ID")
    hire_date = Column(DateTime, nullable=True, comment="入职日期")
    status = Column(SAEnum(DriverStatus), default=DriverStatus.ACTIVE, comment="状态")
    total_charge_kwh = Column(Numeric(12, 2), default=Decimal("0.00"), comment="累计充电量(kWh)")
    total_spent = Column(Numeric(12, 2), default=Decimal("0.00"), comment="累计消费(元)")
    rating = Column(Numeric(3, 1), default=Decimal("5.0"), comment="评分(1-5)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    enterprise = relationship("Enterprise", backref="drivers")
    assigned_vehicle = relationship("EnterpriseVehicle", backref="assigned_drivers")
    account = relationship("FleetDriverAccount", uselist=False, back_populates="driver", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_fd_enterprise", "enterprise_id"),
        Index("idx_fd_phone", "phone"),
        Index("idx_fd_license", "license_no"),
        Index("idx_fd_status", "status"),
    )


class FleetDriverAccount(Base):
    """司机个人账户表 - 充值余额/密码/状态"""
    __tablename__ = "fleet_driver_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(Integer, ForeignKey("fleet_drivers.id", ondelete="CASCADE"), nullable=False, unique=True, comment="司机ID")
    balance = Column(Numeric(12, 2), default=Decimal("0.00"), comment="账户余额(元)")
    pay_password = Column(String(255), nullable=True, comment="支付密码hash")
    status = Column(SAEnum(AccountStatus), default=AccountStatus.ACTIVE, comment="账户状态")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    driver = relationship("FleetDriver", back_populates="account")
    transactions = relationship("FleetDriverTransaction", back_populates="account", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_fda_driver", "driver_id"),
        Index("idx_fda_status", "status"),
    )


class FleetDriverTransaction(Base):
    """司机账户交易记录表 - 充值/消费/退款流水"""
    __tablename__ = "fleet_driver_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("fleet_driver_accounts.id", ondelete="CASCADE"), nullable=False, comment="账户ID")
    type = Column(SAEnum(DriverTransactionType), nullable=False, comment="交易类型: recharge/consume/refund")
    amount = Column(Numeric(12, 2), nullable=False, comment="交易金额(元)")
    balance_after = Column(Numeric(12, 2), nullable=False, comment="交易后余额(元)")
    related_order_id = Column(String(64), nullable=True, comment="关联订单号")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    # 关系
    account = relationship("FleetDriverAccount", back_populates="transactions")

    __table_args__ = (
        Index("idx_fdt_account", "account_id"),
        Index("idx_fdt_type", "type"),
        Index("idx_fdt_created", "created_at"),
        Index("idx_fdt_order", "related_order_id"),
    )
