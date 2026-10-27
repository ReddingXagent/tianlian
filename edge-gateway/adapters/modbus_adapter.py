"""Modbus TCP/RTU adapter for inverter/battery communication

Supports both real pymodbus reading and simulated fallback mode.
Real mode: reads holding registers via AsyncModbusTcpClient.
Simulated mode: generates realistic telemetry without hardware.
"""

import asyncio
import contextlib
import logging
import random
from collections.abc import Callable
from typing import Any, ClassVar

from config import ModbusConfig
from models import TelemetryPoint

logger = logging.getLogger(__name__)


class ModbusAdapter:
    """Modbus protocol adapter - polls devices and emits telemetry.

    Config-driven: set `use_real_modbus=True` for real pymodbus reading,
    or keep default for simulation mode. Falls back to simulation on
    connection failure after configured retries.
    """

    # Register mapping: register index → (field_name, unit, scale_factor)
    REGISTER_MAP: ClassVar[dict[int, tuple[str, str, float]]] = {
        0: ("voltage", "V", 1.0),        # register[0] → voltage (V)
        1: ("current", "A", 1.0),         # register[1] → current (A)
        2: ("power", "kW", 1.0),          # register[2] → power (kW)
        3: ("temperature", "°C", 1.0),    # register[3] → temperature (°C)
        4: ("energy", "kWh", 1.0),        # register[4] → energy (kWh)
        5: ("status", "", 1.0),           # register[5] → status code
    }

    STATUS_MAP: ClassVar[dict[int, str]] = {
        0: "normal",
        1: "warning",
        2: "fault",
        3: "charging",
        4: "idle",
        5: "offline",
    }

    def __init__(self, config: ModbusConfig):
        self.config = config
        self._running = False
        self._task: asyncio.Task | None = None
        self._on_telemetry: Callable[[TelemetryPoint], None] | None = None
        self._on_alarm: Callable[[str, str, str], None] | None = None
        self._client = None
        self._connected = False
        self._sim_energy: float = 0.0  # cumulative energy for simulation

    def on_telemetry(self, callback: Callable[[TelemetryPoint], None]) -> None:
        """Register telemetry callback"""
        self._on_telemetry = callback

    def on_alarm(self, callback: Callable[[str, str, str], None]) -> None:
        """Register alarm callback: callback(device_id, alarm_type, message)"""
        self._on_alarm = callback

    async def start(self) -> None:
        """Start polling Modbus devices"""
        self._running = True

        if self.config.use_real_modbus:
            connected = await self._connect_modbus()
            if not connected:
                logger.warning(
                    "Modbus connection failed after %d retries, falling back to simulation",
                    self.config.retry_count,
                )
                self.config.use_real_modbus = False

        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Modbus adapter started (host=%s:%d, mode=%s)",
            self.config.host, self.config.port,
            "real" if self.config.use_real_modbus else "simulated",
        )

    async def stop(self) -> None:
        """Stop polling and disconnect"""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        if self._client:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None
            self._connected = False

        logger.info("Modbus adapter stopped")

    # ── Real Modbus Connection ────────────────────────────────────────

    async def _connect_modbus(self) -> bool:
        """Connect to Modbus TCP device with retry logic.

        Returns True if connected, False if all retries exhausted.
        """
        for attempt in range(1, self.config.retry_count + 1):
            try:
                from pymodbus.client import AsyncModbusTcpClient

                self._client = AsyncModbusTcpClient(
                    host=self.config.host,
                    port=self.config.port,
                    timeout=self.config.timeout,
                )
                connected = await self._client.connect()
                if connected:
                    self._connected = True
                    logger.info(
                        "Modbus connected to %s:%d (attempt %d/%d)",
                        self.config.host, self.config.port,
                        attempt, self.config.retry_count,
                    )
                    return True
                else:
                    logger.warning(
                        "Modbus connection refused %s:%d (attempt %d/%d)",
                        self.config.host, self.config.port,
                        attempt, self.config.retry_count,
                    )
            except ImportError:
                logger.error("pymodbus not installed, cannot use real Modbus mode")
                return False
            except Exception as e:
                logger.warning(
                    "Modbus connection error %s:%d (attempt %d/%d): %s",
                    self.config.host, self.config.port,
                    attempt, self.config.retry_count, e,
                )

            if attempt < self.config.retry_count:
                await asyncio.sleep(self.config.retry_delay)

        return False

    # ── Poll Loop ─────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Main polling loop"""
        while self._running:
            try:
                if self.config.use_real_modbus and self._connected:
                    await self._poll_real_device()
                else:
                    await self._poll_simulated_device()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Modbus poll failed: %s", e)
                # If real mode fails, try to reconnect
                if self.config.use_real_modbus:
                    self._connected = False
                    logger.info("Attempting Modbus reconnection...")
                    self._connected = await self._connect_modbus()
                    if not self._connected:
                        logger.warning("Modbus reconnection failed, falling back to simulation")
                        self.config.use_real_modbus = False

            await asyncio.sleep(self.config.poll_interval)

    async def _poll_real_device(self) -> None:
        """Read holding registers from real Modbus device"""
        try:
            # Read holding registers
            result = await self._client.read_holding_registers(
                address=self.config.registers[0],
                count=len(self.config.registers),
                slave=self.config.unit_id,
            )

            if result.isError():
                logger.warning("Modbus read error: %s", result)
                return

            registers = result.registers
            if not registers or len(registers) < len(self.config.registers):
                logger.warning(
                    "Modbus read returned %d registers, expected %d",
                    len(registers) if registers else 0,
                    len(self.config.registers),
                )
                return

            # Map registers to telemetry fields
            values = {}
            for idx, reg_idx in enumerate(self.config.registers):
                if reg_idx in self.REGISTER_MAP:
                    field_name, _unit, scale = self.REGISTER_MAP[reg_idx]
                    raw_value = registers[idx]
                    values[field_name] = raw_value * scale

            # Build telemetry point
            voltage = values.get("voltage", 0.0)
            current = values.get("current", 0.0)
            power = values.get("power", 0.0)
            temperature = values.get("temperature", 0.0)
            energy = values.get("energy", 0.0)
            status_code = int(values.get("status", 0))
            status = self.STATUS_MAP.get(status_code, "unknown")

            point = TelemetryPoint(
                device_id=f"modbus-{self.config.unit_id}",
                power=power,
                voltage=voltage,
                current=current,
                temperature=temperature,
                energy=energy,
                status=status,
            )

            if self._on_telemetry:
                self._on_telemetry(point)

            logger.debug(
                "Modbus real poll: power=%.1fkW voltage=%.1fV current=%.1fA temp=%.1f°C energy=%.1fkWh status=%s",
                power, voltage, current, temperature, energy, status,
            )

            # Check for alarm conditions
            if status_code == 2:  # fault
                self._emit_alarm("device_fault", f"Modbus device {self.config.unit_id} reported fault status")
            elif temperature > 60.0:
                self._emit_alarm(
                    "high_temperature",
                    f"Modbus device {self.config.unit_id} temperature high: {temperature}°C",
                )

        except Exception as e:
            logger.error("Modbus real poll error: %s", e)
            raise

    async def _poll_simulated_device(self) -> None:
        """Generate simulated Modbus telemetry"""
        # Simulate realistic values with slight random variation
        voltage = round(random.uniform(370.0, 390.0), 1)
        current = round(random.uniform(0.0, 20.0), 1)
        power = round(voltage * current / 1000, 1)
        temperature = round(random.uniform(25.0, 45.0), 1)
        energy_delta = power * (self.config.poll_interval / 3600)
        self._sim_energy += energy_delta

        # Random status changes
        if random.random() < 0.05:
            status = random.choice(["normal", "warning", "charging"])
        else:
            status = "normal"

        point = TelemetryPoint(
            device_id=f"modbus-{self.config.unit_id}",
            power=power,
            voltage=voltage,
            current=current,
            temperature=temperature,
            energy=round(self._sim_energy, 3),
            status=status,
        )

        if self._on_telemetry:
            self._on_telemetry(point)

        logger.debug(
            "Modbus simulated poll: power=%.1fkW voltage=%.1fV current=%.1fA temp=%.1f°C energy=%.3fkWh status=%s",
            power, voltage, current, temperature, self._sim_energy, status,
        )

        # Occasionally simulate alarms
        if status == "warning" and random.random() < 0.2:
            self._emit_alarm("device_warning", f"Modbus device {self.config.unit_id} warning status")
        if temperature > 55.0 and random.random() < 0.1:
            self._emit_alarm(
                "high_temperature",
                f"Modbus device {self.config.unit_id} temperature high: {temperature}°C",
            )

    # ── Manual injection (for debug API) ──────────────────────────────

    def inject_telemetry(
        self,
        power: float = 0.0,
        voltage: float = 380.0,
        current: float = 0.0,
        temperature: float = 25.0,
        energy: float | None = None,
        status: str = "normal",
    ) -> TelemetryPoint:
        """Manually inject a telemetry point (for debug/simulation API).

        Returns the created TelemetryPoint.
        """
        if energy is not None:
            self._sim_energy = energy

        point = TelemetryPoint(
            device_id=f"modbus-{self.config.unit_id}",
            power=power,
            voltage=voltage,
            current=current,
            temperature=temperature,
            energy=round(self._sim_energy, 3),
            status=status,
        )

        if self._on_telemetry:
            self._on_telemetry(point)

        logger.info(
            "Modbus injected telemetry: power=%.1fkW voltage=%.1fV current=%.1fA temp=%.1f°C status=%s",
            power, voltage, current, temperature, status,
        )

        return point

    def inject_alarm(self, alarm_type: str, message: str) -> None:
        """Manually trigger an alarm (for debug/simulation API)."""
        self._emit_alarm(alarm_type, message)

    # ── Helpers ───────────────────────────────────────────────────────

    # ── Parameter Deploy/Verify (参数下发/校验) ─────────────────────
    # 参数寄存器区: address 100+（与遥测区 0-5 隔离）
    PARAM_REGISTER_MAP: ClassVar[dict[str, int]] = {
        "voltage_limit": 100,        # V, ×10
        "current_limit": 101,        # A, ×10
        "max_power": 102,            # kW, ×10
        "charge_mode": 103,          # enum: 0=standard 1=fast 2=trickle
        "overload_protection": 104,  # 0/1
    }
    _PARAM_SCALE: ClassVar[dict[str, int]] = {"voltage_limit": 10, "current_limit": 10, "max_power": 10}
    _CHARGE_MODE_ENUM: ClassVar[dict[str, int]] = {"standard": 0, "fast": 1, "trickle": 2}
    _CHARGE_MODE_NAMES: ClassVar[dict[int, str]] = {0: "standard", 1: "fast", 2: "trickle"}

    def _encode_param(self, key: str, value) -> int:
        """参数值 → 寄存器原始值"""
        if key == "charge_mode":
            if isinstance(value, str):
                if value not in self._CHARGE_MODE_ENUM:
                    raise ValueError(f"charge_mode 非法: {value}")
                return self._CHARGE_MODE_ENUM[value]
            return int(value)
        if key == "overload_protection":
            return 1 if value else 0
        return int(float(value) * self._PARAM_SCALE.get(key, 1))

    def _decode_param(self, key: str, raw: int):
        """寄存器原始值 → 参数值"""
        if key == "charge_mode":
            return self._CHARGE_MODE_NAMES.get(raw, str(raw))
        if key == "overload_protection":
            return bool(raw)
        return raw / self._PARAM_SCALE.get(key, 1)

    def _ensure_param_shadow(self) -> dict[int, int]:
        if not hasattr(self, "_param_shadow"):
            self._param_shadow: dict[int, int] = {}
        return self._param_shadow

    async def write_params(self, values: dict) -> dict:
        """参数下发: 写保持寄存器。真实模式走 pymodbus, 未连接/模拟模式写影子寄存器。

        Returns: {"simulated": bool, "written": {key: address}, "raw": {key: int}}
        """
        unknown = [k for k in values if k not in self.PARAM_REGISTER_MAP]
        if unknown:
            raise ValueError(f"未知参数: {unknown}（支持: {list(self.PARAM_REGISTER_MAP)}）")
        raw_values = {k: self._encode_param(k, v) for k, v in values.items()}
        shadow = self._ensure_param_shadow()

        if not self._connected or self._client is None:
            shadow.update({self.PARAM_REGISTER_MAP[k]: v for k, v in raw_values.items()})
            return {
                "simulated": True,
                "written": {k: self.PARAM_REGISTER_MAP[k] for k in raw_values},
                "raw": raw_values,
            }

        for key, raw in raw_values.items():
            rr = await self._client.write_register(self.PARAM_REGISTER_MAP[key], raw)
            if rr.isError():
                raise RuntimeError(f"写入寄存器失败 {key}@{self.PARAM_REGISTER_MAP[key]}: {rr}")
            shadow[self.PARAM_REGISTER_MAP[key]] = raw
        return {
            "simulated": False,
            "written": {k: self.PARAM_REGISTER_MAP[k] for k in raw_values},
            "raw": raw_values,
        }

    async def read_params(self, keys: list[str] | None = None) -> dict:
        """参数读回: 读保持寄存器并解码（用于校验）。模拟模式从影子寄存器读。"""
        keys = keys or list(self.PARAM_REGISTER_MAP)
        unknown = [k for k in keys if k not in self.PARAM_REGISTER_MAP]
        if unknown:
            raise ValueError(f"未知参数: {unknown}")
        shadow = self._ensure_param_shadow()

        result: dict[str, Any] = {}
        if not self._connected or self._client is None:
            for k in keys:
                addr = self.PARAM_REGISTER_MAP[k]
                raw = shadow.get(addr)
                result[k] = {"value": self._decode_param(k, raw) if raw is not None else None,
                             "raw": raw, "simulated": True}
            return result

        for k in keys:
            addr = self.PARAM_REGISTER_MAP[k]
            rr = await self._client.read_holding_registers(addr, 1)
            if rr.isError():
                raise RuntimeError(f"读取寄存器失败 {k}@{addr}: {rr}")
            raw = int(rr.registers[0])
            result[k] = {"value": self._decode_param(k, raw), "raw": raw, "simulated": False}
        return result

    def _emit_alarm(self, alarm_type: str, message: str) -> None:
        """Emit an alarm through the registered callback"""
        if self._on_alarm:
            self._on_alarm(f"modbus-{self.config.unit_id}", alarm_type, message)

        logger.warning(
            "Modbus alarm: device=%s type=%s message=%s",
            f"modbus-{self.config.unit_id}", alarm_type, message,
        )
