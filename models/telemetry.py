"""Telemetry data models"""

import contextlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

UTC = timezone.utc  # Py3.10 compat
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
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    power: float = 0.0        # kW
    voltage: float = 0.0      # V
    current: float = 0.0      # A
    temperature: float = 0.0  # °C
    energy: float = 0.0       # kWh
    soc: float | None = None  # State of charge (%)
    status: str = "normal"    # normal | warning | fault

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_api_payload(self) -> dict:
        """Format for cloud V3 TelemetryReportLegacy schema

        Maps edge gateway fields to cloud V3 fields:
        - modbus-1 → grid_* fields (储能逆变器)
        - CHARGER-001 → charger_* fields (充电桩)
        """
        cloud_id = DEVICE_ID_MAP.get(self.device_id, self.device_id)
        with contextlib.suppress(ValueError, TypeError):
            cloud_id = int(cloud_id)

        # 通用基础字段
        payload = {"device_id": cloud_id}

        # 根据设备类型映射字段
        if self.device_id == "modbus-1":
            # 储能逆变器 → grid + battery + pv fields
            payload.update({
                "grid_voltage_a": self.voltage if self.voltage else None,
                "grid_power_a": self.power if self.power else None,
                "grid_power_total": self.power if self.power else None,
                "battery_voltage": self.voltage if self.voltage else None,
                "battery_temperature": self.temperature if self.temperature else None,
                "battery_soc": self.soc,
                "ambient_temperature": self.temperature if self.temperature else None,
            })
        elif self.device_id.startswith("CHARGER"):
            # 充电桩 → charger fields
            payload.update({
                "charger_voltage": self.voltage if self.voltage else None,
                "charger_current": self.current if self.current else None,
                "charger_power": self.power if self.power else None,
                "charger_soc": self.soc,
                "charger_kwh": self.energy if self.energy else None,
                "gun_temperature": self.temperature if self.temperature else None,
            })
        else:
            # 未知设备 → 通用power字段
            payload.update({
                "grid_power_total": self.power if self.power else None,
                "grid_voltage_a": self.voltage if self.voltage else None,
                "ambient_temperature": self.temperature if self.temperature else None,
            })

        # 清理 None 值
        return {k: v for k, v in payload.items() if v is not None}


@dataclass
class TelemetryBatch:
    """Batch of telemetry points"""
    gateway_id: str
    points: list[TelemetryPoint] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def add(self, point: TelemetryPoint) -> None:
        self.points.append(point)

    def to_api_payload(self) -> dict:
        return {
            "records": [p.to_api_payload() for p in self.points],
            "pod_id": self.gateway_id,
            "region_id": "default",
        }
