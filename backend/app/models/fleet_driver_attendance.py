"""
司机考勤/工时模型 - fleet-platform-spec §4.3 规划表

包含:
- FleetDriverAttendance: 司机每日考勤(班次/工时/状态)
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Index

from app.core.database import Base


class FleetDriverAttendance(Base):
    """司机考勤表 - 班次(day/night/rest) + 工时 + 状态(normal/late/absent)"""
    __tablename__ = "fleet_driver_attendance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(Integer, ForeignKey("fleet_drivers.id"), nullable=False, comment="司机ID")
    date = Column(String(10), nullable=False, comment="考勤日期 YYYY-MM-DD")
    shift_type = Column(String(10), nullable=False, default="day", comment="班次: day/night/rest")
    hours = Column(Float, nullable=False, default=0.0, comment="工时(小时)")
    status = Column(String(10), nullable=False, default="normal", comment="状态: normal/late/absent")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_fatt_driver_date", "driver_id", "date", unique=True),
        Index("idx_fatt_date", "date"),
        Index("idx_fatt_status", "status"),
    )
