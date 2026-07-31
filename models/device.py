"""Device data models"""

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class DeviceStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    FAULT = "fault"
    CHARGING = "charging"
    IDLE = "idle"


class DeviceType(StrEnum):
    CHARGER = "charger"          # 充电桩
    INVERTER = "inverter"        # 逆变器
    BATTERY = "battery"          # 储能
    METER = "meter"              # 电表
    SENSOR = "sensor"            # 传感器


class ProtocolType(StrEnum):
    OCPP = "ocpp"
    MODBUS_TCP = "modbus_tcp"
    MODBUS_RTU = "modbus_rtu"
    MQTT = "mqtt"


@dataclass
class DeviceInfo:
    """Device information"""
    device_id: str
    name: str
    type: DeviceType
    protocol: ProtocolType
    station_id: str = ""
    model: str = ""
    status: DeviceStatus = DeviceStatus.OFFLINE
    address: str = ""           # IP or serial port
    port: int = 0
    unit_id: int = 1            # Modbus unit ID
    config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceInfo":
        return cls(**data)
