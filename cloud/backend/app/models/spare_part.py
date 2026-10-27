"""
备件库存模型 — maint-platform-spec §2.2

work_order_spare_parts 只记录工单领用的备件，本表为独立库存台账：
- total_quantity:      累计入库总量（只增，随入库增加）
- available_quantity:  当前可用量（入库增、出库/工单领用减）

工单申请备件时按 (part_name, part_model) 匹配本表并扣减 available_quantity。
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class SparePartInventory(Base):
    """备件库存表"""
    __tablename__ = "spare_parts_inventory"

    id = Column(Integer, primary_key=True, index=True)
    part_name = Column(String(100), nullable=False)            # 备件名称
    part_model = Column(String(100))                            # 备件型号
    total_quantity = Column(Integer, nullable=False, default=0)     # 累计入库量
    available_quantity = Column(Integer, nullable=False, default=0)  # 可用量
    warehouse = Column(String(100))                             # 仓库
    created_at = Column(DateTime(timezone=True), server_default=func.now())
