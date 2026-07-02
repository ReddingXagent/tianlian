"""Telemetry data models"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Optional
from datetime import datetime, timezone

# 设备名→云端ID映射（云端要求整数device_id）
DEVICE_ID_MAP = {
    "modbus-1": 1,
    "CHARGER-001": 2,
    "GW-001": 0,
}


@dataclass
class TelemetryPoint:
    """Single telemetry data point"""
    device_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    power: float = 0.0        # kW
    voltage: float = 0.0      # V
    current: float = 0.0      # A
    temperature: float = 0.0  # °C
    energy: float = 0.0       # kWh
    soc: Optional[float] = None  # State of charge (%)
    status: str = "normal"    # normal | warning | fault

    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_api_payload(self) -> Dict:
        """Format for cloud API (device_id mapped to integer)"""
        cloud_id = DEVICE_ID_MAP.get(self.device_id, self.device_id)
        try:
            cloud_id = int(cloud_id)
        except (ValueError, TypeError):
            pass  # keep as string if unmappable
        return {
            "device_id": cloud_id,
            "timestamp": self.timestamp,
            "metrics": {
                "power": self.power,
                "voltage": self.voltage,
                "current": self.current,
                "temperature": self.temperature,
                "energy": self.energy,
            }
        }


@dataclass
class TelemetryBatch:
    """Batch of telemetry points"""
    gateway_id: str
    points: list[TelemetryPoint] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add(self, point: TelemetryPoint) -> None:
        self.points.append(point)

    def to_api_payload(self) -> Dict:
        return {
            "gateway_id": self.gateway_id,
            "timestamp": self.timestamp,
            "telemetry": [p.to_api_payload() for p in self.points]
        }
