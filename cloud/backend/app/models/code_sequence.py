"""
编码序列号模型 - 用于维护编码序列
"""
from sqlalchemy import Column, String, BigInteger, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class CodeSequence(Base):
    """
    编码序列表
    
    存储各类型编码的当前序列值
    key格式:
      - seq:team:HN (团队序列，区域HN)
      - seq:station:GD (站点序列，区域GD)
      - seq:gateway:HN (网关序列，区域HN)
      - seq:device:HN:PV (设备序列，区域HN+类型PV)
    """
    __tablename__ = "code_sequences"
    
    key = Column(String(32), primary_key=True, index=True)  # 序列键
    current_value = Column(BigInteger, nullable=False, default=0)  # 当前值
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())