"""
初始化测试数据 - 创建站点和设备用于扫码报修测试
"""
from app.core.database import SessionLocal
from app.models.station import Station
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.device_qrcode import DeviceQRCode
import uuid

db = SessionLocal()

# 创建测试站点
station = Station(
    id=1,
    name="浦东充电站",
    code="ST-001",
    address="上海市浦东新区陆家嘴环路1000号",
    lat=31.23,
    lon=121.47,
    status="active",
    capacity=20,
)
db.add(station)

# 创建测试设备
devices_data = [
    {
        "sn": "SN001-2026",
        "code": "TL-DEV001",
        "name": "直流充电桩-01",
        "type": DeviceType.CHARGER_DC,
        "station_id": 1,
        "rated_power": 120.0,
        "gun_count": 2,
        "status": DeviceStatus.ONLINE,
        "health_score": 85.0,
    },
    {
        "sn": "SN002-2026",
        "code": "TL-DEV002",
        "name": "交流充电桩-01",
        "type": DeviceType.CHARGER_AC,
        "station_id": 1,
        "rated_power": 7.0,
        "gun_count": 1,
        "status": DeviceStatus.ONLINE,
        "health_score": 90.0,
    },
    {
        "sn": "SN003-2026",
        "code": "TL-DEV003",
        "name": "光伏逆变器-01",
        "type": DeviceType.PV_INVERTER,
        "station_id": 1,
        "rated_power": 50.0,
        "status": DeviceStatus.ONLINE,
        "health_score": 92.0,
    },
]

for data in devices_data:
    device = Device(**data)
    db.add(device)

db.commit()

# 刷新获取设备ID
db.refresh(station)
for data in devices_data:
    db.query(Device).filter(Device.code == data["code"]).first()

# 创建二维码
for device_data in devices_data:
    device = db.query(Device).filter(Device.code == device_data["code"]).first()
    qr_code = f"TL-{device.code}-{uuid.uuid4().hex[:8]}"
    qrcode_record = DeviceQRCode(
        device_id=device.id,
        qr_code=qr_code,
        is_active=True,
        notes="测试二维码",
    )
    db.add(qrcode_record)

db.commit()

print("✅ 测试数据创建完成:")
print(f"  - 站点: {station.name}")
for device_data in devices_data:
    device = db.query(Device).filter(Device.code == device_data["code"]).first()
    qrcode = db.query(DeviceQRCode).filter(DeviceQRCode.device_id == device.id).first()
    print(f"  - 设备: {device.name} ({device.code})")
    print(f"    二维码: {qrcode.qr_code}")

db.close()