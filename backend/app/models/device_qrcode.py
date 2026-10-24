"""
设备二维码模型 — 工作卡 c7523ad8

云快充协议 V1.6：
- 桩编号 14 位纯数字（6 位国标行政区划码 + 8 位桩序号）；
- 枪号 = 桩编号 + 2 位枪号 = 16 位；
- 二维码按枪粒度生成，单枪桩 1 张码（尾缀 01），双枪桩 2 张（01/02）。

因此 qr_code 存放 16 位枪号（扫码即得完整枪号），同一设备可有多行（每枪一行）：
- device_id 不再列级唯一（保留 index）；
- gun_no 标识枪号（default=1）；
- (device_id, gun_no) 复合唯一 — 一桩内每枪唯一。
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

class DeviceQRCode(Base):
    """设备二维码表（按枪粒度，一桩多枪一行一枪）"""
    __tablename__ = "device_qrcodes"
    __table_args__ = (
        # 一桩内每枪唯一（单枪桩 gun_no=1；双枪桩 01/02）
        Index("uq_device_qrcode_device_gun", "device_id", "gun_no", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)

    # 关联设备（不再列级唯一 — 一桩多枪对应多行）
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    # 枪号（1 起始；与 device_id 组合唯一；查询均与 device_id 配对，由复合唯一索引覆盖）
    gun_no = Column(Integer, nullable=False, default=1, server_default="1")

    # 二维码内容 = 16 位枪号（14 位桩编号 + 2 位枪号尾缀）
    qr_code = Column(String(200), unique=True, nullable=False, index=True)  # 二维码唯一标识

    # 二维码图片路径 (可选)
    qr_image_path = Column(String(500))  # 存储生成的二维码图片路径

    # 状态
    is_active = Column(Boolean, default=True)  # 是否有效

    # 打印信息
    print_count = Column(Integer, default=0)  # 打印次数
    last_print_time = Column(DateTime(timezone=True))

    # 扫码统计
    scan_count = Column(Integer, default=0)  # 扫码次数
    last_scan_time = Column(DateTime(timezone=True))

    # 备注
    notes = Column(Text)

    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    device = relationship("Device", backref="qrcode")
