"""OCPP 1.6J adapter for EV charger communication

Supports both real OCPP WebSocket connection and simulated mode.
Real mode: connects as a ChargePoint to a CSMS via WebSocket.
Simulated mode: generates realistic telemetry without hardware.

OCPP 1.6J ChargePoint operations:
  - BootNotification → sends charger vendor/model/serial
  - Heartbeat → periodic heartbeat with currentTime
  - Authorize → RFID/tag authorization before charging
  - StartTransaction → begin charging session with meter start
  - StopTransaction → end charging session with meter stop + reason
  - MeterValues → periodic sampled values (V/A/W/Wh/°C)
  - StatusNotification → connector status changes with error codes
"""

import asyncio
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from config import OCPPConfig
from models import TelemetryPoint

UTC = timezone.utc  # Py3.10 compat
logger = logging.getLogger(__name__)


# ── OCPP 1.6J Message Types ──────────────────────────────────────────


class RegistrationStatus(str, Enum):
    """BootNotification response status"""
    ACCEPTED = "Accepted"
    PENDING = "Pending"
    REJECTED = "Rejected"


class ChargePointStatus(str, Enum):
    """StatusNotification status values"""
    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    SUSPENDED_EVSE = "SuspendedEVSE"
    SUSPENDED_EV = "SuspendedEV"
    FINISHING = "Finishing"
    RESERVED = "Reserved"
    UNAVAILABLE = "Unavailable"
    FAULTED = "Faulted"


class ChargePointErrorCode(str, Enum):
    """StatusNotification error codes"""
    NO_ERROR = "NoError"
    CONNECTOR_LOCK_FAILURE = "ConnectorLockFailure"
    EV_COMMUNICATION_ERROR = "EVCommunicationError"
    GROUND_FAILURE = "GroundFailure"
    HIGH_TEMPERATURE = "HighTemperature"
    INTERNAL_ERROR = "InternalError"
    LOCAL_LIST_CONFLICT = "LocalListConflict"
    OTHER_ERROR = "OtherError"
    OVER_CURRENT_FAILURE = "OverCurrentFailure"
    OVER_VOLTAGE = "OverVoltage"
    POWER_METER_FAILURE = "PowerMeterFailure"
    POWER_SWITCH_FAILURE = "PowerSwitchFailure"
    READER_FAILURE = "ReaderFailure"
    RESET_FAILURE = "ResetFailure"
    UNDER_VOLTAGE = "UnderVoltage"
    WEAK_SIGNAL = "WeakSignal"


class AuthorizationStatus(str, Enum):
    """Authorize response status"""
    ACCEPTED = "Accepted"
    BLOCKED = "Blocked"
    INVALID = "Invalid"
    CONCURRENT_TX = "ConcurrentTx"
    EXPIRED = "Expired"


class StopReason(str, Enum):
    """StopTransaction reason codes"""
    EMERGENCY_STOP = "EmergencyStop"
    EV_DISCONNECTED = "EVDisconnected"
    HARD_RESET = "HardReset"
    LOCAL = "Local"
    OTHER = "Other"
    POWER_LOSS = "PowerLoss"
    REBOOT = "Reboot"
    REMOTE = "Remote"
    SOFT_RESET = "SoftReset"
    UNLOCK_COMMAND = "UnlockCommand"
    DE_AUTHORIZED = "DeAuthorized"


class Measurand(str, Enum):
    """MeterValues measurand types"""
    VOLTAGE = "Voltage"
    CURRENT_IMPORT = "Current.Import"
    CURRENT_EXPORT = "Current.Export"
    POWER_ACTIVE_IMPORT = "Power.Active.Import"
    POWER_ACTIVE_EXPORT = "Power.Active.Export"
    ENERGY_ACTIVE_IMPORT_REGISTER = "Energy.Active.Import.Register"
    ENERGY_ACTIVE_EXPORT_REGISTER = "Energy.Active.Export.Register"
    TEMPERATURE = "Temperature"
    SOC = "SoC"
    FREQUENCY = "Frequency"


class UnitOfMeasure(str, Enum):
    """MeterValues unit types"""
    V = "V"
    A = "A"
    W = "W"
    WH = "Wh"
    KWH = "kWh"
    VAR = "var"
    VARH = "varh"
    CELSIUS = "Celsius"
    PERCENT = "Percent"
    HZ = "Hz"


class ReadingContext(str, Enum):
    """MeterValues reading context"""
    INTERRUPTION_BEGIN = "Interruption.Begin"
    INTERRUPTION_END = "Interruption.End"
    SAMPLE_CLOCK = "Sample.Clock"
    SAMPLE_PERIODIC = "Sample.Periodic"
    TRANSACTION_BEGIN = "Transaction.Begin"
    TRANSACTION_END = "Transaction.End"
    TRIGGER = "Trigger"
    OTHER = "Other"


# ── OCPP Message Dataclasses ─────────────────────────────────────────


@dataclass
class BootNotificationRequest:
    """OCPP BootNotification.req"""
    charge_point_vendor: str
    charge_point_model: str
    charge_point_serial_number: str = ""
    charge_box_serial_number: str = ""
    firmware_version: str = ""
    iccid: str = ""
    imsi: str = ""
    meter_type: str = ""
    meter_serial_number: str = ""


@dataclass
class BootNotificationResponse:
    """OCPP BootNotification.conf"""
    status: RegistrationStatus
    current_time: str = ""
    interval: int = 0


@dataclass
class HeartbeatRequest:
    """OCPP Heartbeat.req (empty payload)"""


@dataclass
class HeartbeatResponse:
    """OCPP Heartbeat.conf"""
    current_time: str


@dataclass
class AuthorizeRequest:
    """OCPP Authorize.req"""
    id_tag: str


@dataclass
class AuthorizeResponse:
    """OCPP Authorize.conf"""
    id_tag_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class StartTransactionRequest:
    """OCPP StartTransaction.req"""
    connector_id: int
    id_tag: str
    meter_start: int  # Wh
    timestamp: str = ""
    reservation_id: int | None = None


@dataclass
class StartTransactionResponse:
    """OCPP StartTransaction.conf"""
    transaction_id: int
    id_tag_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class StopTransactionRequest:
    """OCPP StopTransaction.req"""
    transaction_id: int
    meter_stop: int  # Wh
    timestamp: str = ""
    reason: StopReason = StopReason.EV_DISCONNECTED
    id_tag: str | None = None
    transaction_data: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class StopTransactionResponse:
    """OCPP StopTransaction.conf"""
    id_tag_info: dict[str, Any] | None = None


@dataclass
class SampledValue:
    """Single sampled value in MeterValues"""
    value: str
    measurand: Measurand = Measurand.ENERGY_ACTIVE_IMPORT_REGISTER
    unit: UnitOfMeasure = UnitOfMeasure.WH
    context: ReadingContext = ReadingContext.SAMPLE_PERIODIC
    format: str = "Raw"
    location: str = "Outlet"
    phase: str | None = None


@dataclass
class MeterValue:
    """Single meter value with timestamp and sampled values"""
    timestamp: str
    sampled_value: list[SampledValue] = field(default_factory=list)


@dataclass
class MeterValuesRequest:
    """OCPP MeterValues.req"""
    connector_id: int
    meter_value: list[MeterValue] = field(default_factory=list)
    transaction_id: int | None = None


@dataclass
class MeterValuesResponse:
    """OCPP MeterValues.conf (empty)"""


@dataclass
class StatusNotificationRequest:
    """OCPP StatusNotification.req"""
    connector_id: int
    error_code: ChargePointErrorCode
    status: ChargePointStatus
    timestamp: str = ""
    info: str = ""
    vendor_id: str = ""
    vendor_error_code: str = ""


@dataclass
class StatusNotificationResponse:
    """OCPP StatusNotification.conf (empty)"""


@dataclass
class OCPPMessageLog:
    """Record of an OCPP message exchange"""
    direction: str  # "req" or "conf"
    action: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── OCPP ChargePoint (protocol-level) ────────────────────────────────


class OCPPChargePointProtocol:
    """Pure protocol handler for OCPP 1.6J ChargePoint operations.

    This class handles the OCPP protocol logic without any I/O.
    It can be used both with real WebSocket connections and in tests.
    """

    def __init__(self, charger_id: str):
        self.charger_id = charger_id
        self._message_log: list[OCPPMessageLog] = []
        self._boot_status: RegistrationStatus | None = None
        self._last_heartbeat_time: str | None = None
        self._authorized_tags: dict[str, bool] = {}
        self._last_authorized_tag: str = ""
        self._active_transactions: dict[int, dict[str, Any]] = {}

    # ── Message Log ──────────────────────────────────────────────

    @property
    def message_log(self) -> list[OCPPMessageLog]:
        return list(self._message_log)

    @property
    def boot_status(self) -> RegistrationStatus | None:
        return self._boot_status

    @property
    def last_heartbeat_time(self) -> str | None:
        return self._last_heartbeat_time

    def clear_log(self) -> None:
        self._message_log.clear()

    def _log_message(self, direction: str, action: str, payload: dict[str, Any]) -> None:
        self._message_log.append(OCPPMessageLog(
            direction=direction,
            action=action,
            payload=payload,
        ))

    # ── BootNotification ─────────────────────────────────────────

    def build_boot_notification(self, req: BootNotificationRequest) -> dict[str, Any]:
        """Build BootNotification.req payload"""
        payload = {
            "chargePointVendor": req.charge_point_vendor,
            "chargePointModel": req.charge_point_model,
        }
        if req.charge_point_serial_number:
            payload["chargePointSerialNumber"] = req.charge_point_serial_number
        if req.charge_box_serial_number:
            payload["chargeBoxSerialNumber"] = req.charge_box_serial_number
        if req.firmware_version:
            payload["firmwareVersion"] = req.firmware_version
        if req.iccid:
            payload["iccid"] = req.iccid
        if req.imsi:
            payload["imsi"] = req.imsi
        if req.meter_type:
            payload["meterType"] = req.meter_type
        if req.meter_serial_number:
            payload["meterSerialNumber"] = req.meter_serial_number

        self._log_message("req", "BootNotification", payload)
        return payload

    def handle_boot_notification_response(self, response: dict[str, Any]) -> BootNotificationResponse:
        """Parse BootNotification.conf"""
        status = RegistrationStatus(response.get("status", "Rejected"))
        self._boot_status = status
        result = BootNotificationResponse(
            status=status,
            current_time=response.get("currentTime", ""),
            interval=int(response.get("interval", 0)),
        )
        self._log_message("conf", "BootNotification", response)
        return result

    # ── Heartbeat ────────────────────────────────────────────────

    def build_heartbeat(self) -> dict[str, Any]:
        """Build Heartbeat.req payload (empty)"""
        payload: dict[str, Any] = {}
        self._log_message("req", "Heartbeat", payload)
        return payload

    def handle_heartbeat_response(self, response: dict[str, Any]) -> HeartbeatResponse:
        """Parse Heartbeat.conf"""
        self._last_heartbeat_time = response.get("currentTime", "")
        result = HeartbeatResponse(current_time=self._last_heartbeat_time)
        self._log_message("conf", "Heartbeat", response)
        return result

    # ── Authorize ────────────────────────────────────────────────

    def build_authorize(self, req: AuthorizeRequest) -> dict[str, Any]:
        """Build Authorize.req payload"""
        payload = {"idTag": req.id_tag}
        self._log_message("req", "Authorize", payload)
        # Store the id_tag so we can correlate with the response
        self._last_authorized_tag = req.id_tag
        return payload

    def handle_authorize_response(self, response: dict[str, Any]) -> AuthorizeResponse:
        """Parse Authorize.conf"""
        id_tag_info = response.get("idTagInfo", {})
        status = id_tag_info.get("status", "Invalid")
        # Use the id_tag from the request, not the response
        tag = getattr(self, "_last_authorized_tag", "")
        if tag:
            self._authorized_tags[tag] = (status == "Accepted")
        result = AuthorizeResponse(id_tag_info=id_tag_info)
        self._log_message("conf", "Authorize", response)
        return result

    def is_tag_authorized(self, id_tag: str) -> bool:
        """Check if an idTag was previously authorized"""
        return self._authorized_tags.get(id_tag, False)

    # ── StartTransaction ─────────────────────────────────────────

    def build_start_transaction(self, req: StartTransactionRequest) -> dict[str, Any]:
        """Build StartTransaction.req payload"""
        payload: dict[str, Any] = {
            "connectorId": req.connector_id,
            "idTag": req.id_tag,
            "meterStart": req.meter_start,
            "timestamp": req.timestamp or datetime.now(UTC).isoformat(),
        }
        if req.reservation_id is not None:
            payload["reservationId"] = req.reservation_id

        self._log_message("req", "StartTransaction", payload)
        return payload

    def handle_start_transaction_response(self, response: dict[str, Any]) -> StartTransactionResponse:
        """Parse StartTransaction.conf"""
        transaction_id = int(response.get("transactionId", 0))
        id_tag_info = response.get("idTagInfo", {})
        self._active_transactions[transaction_id] = {
            "id_tag_info": id_tag_info,
            "started_at": datetime.now(UTC).isoformat(),
        }
        result = StartTransactionResponse(
            transaction_id=transaction_id,
            id_tag_info=id_tag_info,
        )
        self._log_message("conf", "StartTransaction", response)
        return result

    # ── StopTransaction ──────────────────────────────────────────

    def build_stop_transaction(self, req: StopTransactionRequest) -> dict[str, Any]:
        """Build StopTransaction.req payload"""
        payload: dict[str, Any] = {
            "transactionId": req.transaction_id,
            "meterStop": req.meter_stop,
            "timestamp": req.timestamp or datetime.now(UTC).isoformat(),
            "reason": req.reason.value if isinstance(req.reason, StopReason) else req.reason,
        }
        if req.id_tag:
            payload["idTag"] = req.id_tag
        if req.transaction_data:
            payload["transactionData"] = req.transaction_data

        self._log_message("req", "StopTransaction", payload)
        return payload

    def handle_stop_transaction_response(self, response: dict[str, Any]) -> StopTransactionResponse:
        """Parse StopTransaction.conf"""
        id_tag_info = response.get("idTagInfo")
        result = StopTransactionResponse(id_tag_info=id_tag_info)
        self._log_message("conf", "StopTransaction", response)
        # Clean up active transaction
        # (transaction_id is not in response, so we clean up via caller)
        return result

    def remove_transaction(self, transaction_id: int) -> None:
        """Remove a completed transaction from active tracking"""
        self._active_transactions.pop(transaction_id, None)

    # ── MeterValues ──────────────────────────────────────────────

    def build_meter_values(self, req: MeterValuesRequest) -> dict[str, Any]:
        """Build MeterValues.req payload"""
        meter_value_list = []
        for mv in req.meter_value:
            sv_list = []
            for sv in mv.sampled_value:
                sv_dict: dict[str, Any] = {
                    "value": sv.value,
                    "measurand": sv.measurand.value if isinstance(sv.measurand, Measurand) else sv.measurand,
                    "unit": sv.unit.value if isinstance(sv.unit, UnitOfMeasure) else sv.unit,
                    "context": sv.context.value if isinstance(sv.context, ReadingContext) else sv.context,
                }
                if sv.format:
                    sv_dict["format"] = sv.format
                if sv.location:
                    sv_dict["location"] = sv.location
                if sv.phase:
                    sv_dict["phase"] = sv.phase
                sv_list.append(sv_dict)

            meter_value_list.append({
                "timestamp": mv.timestamp,
                "sampledValue": sv_list,
            })

        payload: dict[str, Any] = {
            "connectorId": req.connector_id,
            "meterValue": meter_value_list,
        }
        if req.transaction_id is not None:
            payload["transactionId"] = req.transaction_id

        self._log_message("req", "MeterValues", payload)
        return payload

    def handle_meter_values_response(self, response: dict[str, Any]) -> MeterValuesResponse:
        """Parse MeterValues.conf (empty)"""
        self._log_message("conf", "MeterValues", response)
        return MeterValuesResponse()

    # ── StatusNotification ───────────────────────────────────────

    def build_status_notification(self, req: StatusNotificationRequest) -> dict[str, Any]:
        """Build StatusNotification.req payload"""
        payload: dict[str, Any] = {
            "connectorId": req.connector_id,
            "errorCode": req.error_code.value if isinstance(req.error_code, ChargePointErrorCode) else req.error_code,
            "status": req.status.value if isinstance(req.status, ChargePointStatus) else req.status,
            "timestamp": req.timestamp or datetime.now(UTC).isoformat(),
        }
        if req.info:
            payload["info"] = req.info
        if req.vendor_id:
            payload["vendorId"] = req.vendor_id
        if req.vendor_error_code:
            payload["vendorErrorCode"] = req.vendor_error_code

        self._log_message("req", "StatusNotification", payload)
        return payload

    def handle_status_notification_response(self, response: dict[str, Any]) -> StatusNotificationResponse:
        """Parse StatusNotification.conf (empty)"""
        self._log_message("conf", "StatusNotification", response)
        return StatusNotificationResponse()


# ── OCPP Adapter ──────────────────────────────────────────────────────


# ── Conditional imports for real OCPP mode ───────────────────────

try:
    from ocpp.v16 import call as _ocpp_call
    from ocpp.v16 import call_result as _ocpp_call_result
    _HAS_OCPP = True
except ImportError:
    _HAS_OCPP = False
    _ocpp_call = None  # type: ignore
    _ocpp_call_result = None  # type: ignore


class OCPPAdapter:
    """OCPP protocol adapter - connects to EV chargers and emits telemetry.

    Supports OCPP 1.6J ChargePoint operations:
      - BootNotification → sends charger vendor/model
      - Heartbeat → periodic heartbeat
      - MeterValues → periodic meter data (voltage/current/power/energy)
      - StatusNotification → status change notifications
      - StartTransaction / StopTransaction → charging transactions
      - Authorize → authorization verification

    Config-driven: set `use_real_charger=True` for real WebSocket connection,
    or keep default for simulation mode.
    """

    def __init__(self, config: OCPPConfig):
        self.config = config
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._on_telemetry: Callable[[TelemetryPoint], None] | None = None
        self._on_alarm: Callable[[str, str, str], None] | None = None

        # Runtime state
        self._meter_value: float = 0.0  # cumulative energy (kWh)
        self._status: str = "Available"
        self._transaction_id: int = 0
        self._is_charging: bool = False
        self._connector_id: int = 1
        self._reconnect_count: int = 0
        self._max_reconnects: int = 5  # max reconnect attempts before fallback

        # Real charger state
        self._ws_connected: bool = False
        self._last_power: float = 0.0
        self._last_voltage: float = 0.0
        self._last_current: float = 0.0
        self._last_temperature: float = 25.0

        # Simulated state
        self._sim_power: float = 0.0
        self._sim_voltage: float = 380.0
        self._sim_current: float = 0.0
        self._sim_temperature: float = 25.0

        # Protocol handler (used in both modes)
        self._protocol = OCPPChargePointProtocol(self.config.charger_id)

    @property
    def protocol(self) -> OCPPChargePointProtocol:
        """Access the protocol handler for testing"""
        return self._protocol

    @property
    def message_log(self) -> list[OCPPMessageLog]:
        """Access message log for testing"""
        return self._protocol.message_log

    def on_telemetry(self, callback: Callable[[TelemetryPoint], None]) -> None:
        """Register telemetry callback (same pattern as ModbusAdapter)"""
        self._on_telemetry = callback

    def on_alarm(self, callback: Callable[[str, str, str], None]) -> None:
        """Register alarm callback: callback(device_id, alarm_type, message)"""
        self._on_alarm = callback

    async def start(self) -> None:
        """Start OCPP adapter"""
        self._running = True

        if self.config.use_real_charger:
            self._tasks.append(asyncio.create_task(self._run_real_charger()))
        else:
            self._tasks.append(asyncio.create_task(self._run_simulated_charger()))

        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
        self._tasks.append(asyncio.create_task(self._meter_loop()))

        logger.info(
            "OCPP adapter started (charger=%s, mode=%s)",
            self.config.charger_id,
            "real" if self.config.use_real_charger else "simulated",
        )

    async def stop(self) -> None:
        """Stop OCPP adapter"""
        self._running = False
        for task in self._tasks:
            task.cancel()
        results = await asyncio.gather(*self._tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError):
                logger.warning("OCPP task error during shutdown: %s", r)
        self._tasks.clear()
        logger.info("OCPP adapter stopped")

    # ── Simulated charger (no real charger needed) ──────────────────────

    async def _run_simulated_charger(self) -> None:
        """Simulate OCPP charger behavior with full protocol emulation"""
        # Simulate BootNotification
        await asyncio.sleep(1)
        boot_req = BootNotificationRequest(
            charge_point_vendor=self.config.charger_vendor,
            charge_point_model=self.config.charger_model,
            charge_point_serial_number=self.config.charger_id,
            charge_box_serial_number=f"CB-{self.config.charger_id}",
            firmware_version="1.0.0",
            meter_type="Tianlian SmartMeter",
            meter_serial_number=f"MTR-{self.config.charger_id}",
        )
        self._protocol.build_boot_notification(boot_req)
        self._protocol.handle_boot_notification_response({
            "status": "Accepted",
            "currentTime": datetime.now(UTC).isoformat(),
            "interval": self.config.heartbeat_interval,
        })
        logger.info(
            "OCPP simulated BootNotification: charger=%s vendor=%s model=%s",
            self.config.charger_id,
            self.config.charger_vendor,
            self.config.charger_model,
        )
        self._emit_telemetry(
            power=0.0,
            voltage=380.0,
            current=0.0,
            temperature=25.0,
            status="Available",
        )

        # Simulate StatusNotification: Available
        await asyncio.sleep(0.5)
        self._protocol.build_status_notification(StatusNotificationRequest(
            connector_id=self._connector_id,
            error_code=ChargePointErrorCode.NO_ERROR,
            status=ChargePointStatus.AVAILABLE,
        ))
        self._protocol.handle_status_notification_response({})
        logger.info("OCPP simulated StatusNotification: status=Available connector=%d", self._connector_id)

        # Main simulation loop
        while self._running:
            try:
                if random.random() < 0.3:
                    await self._simulate_charging_session()
                else:
                    await self._simulate_idle_period()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("OCPP simulation error: %s", e)
                await asyncio.sleep(5)

    async def _simulate_charging_session(self) -> None:
        """Simulate a full charging session with StartTransaction/StopTransaction"""
        # Authorize
        id_tag = f"RFID-{random.randint(10000, 99999)}"
        self._protocol.build_authorize(AuthorizeRequest(id_tag=id_tag))
        self._protocol.handle_authorize_response({
            "idTagInfo": {"status": "Accepted", "expiryDate": "2099-12-31T23:59:59Z"},
        })
        logger.info("OCPP simulated Authorize: idTag=%s → Accepted", id_tag)

        # StartTransaction
        self._transaction_id = random.randint(1000, 9999)
        self._is_charging = True
        meter_start = int(self._meter_value * 1000)  # kWh → Wh
        self._protocol.build_start_transaction(StartTransactionRequest(
            connector_id=self._connector_id,
            id_tag=id_tag,
            meter_start=meter_start,
        ))
        self._protocol.handle_start_transaction_response({
            "transactionId": self._transaction_id,
            "idTagInfo": {"status": "Accepted"},
        })
        logger.info(
            "OCPP simulated StartTransaction: transactionId=%d connectorId=%d idTag=%s meterStart=%d",
            self._transaction_id, self._connector_id, id_tag, meter_start,
        )

        # StatusNotification: Charging
        self._protocol.build_status_notification(StatusNotificationRequest(
            connector_id=self._connector_id,
            error_code=ChargePointErrorCode.NO_ERROR,
            status=ChargePointStatus.CHARGING,
        ))
        self._protocol.handle_status_notification_response({})
        logger.info("OCPP simulated StatusNotification: status=Charging connector=%d", self._connector_id)
        self._status = "Charging"

        # Charging loop
        duration = random.randint(10, 30)
        for _ in range(duration):
            if not self._running:
                break
            power = round(random.uniform(5.0, 60.0), 1)
            voltage = round(random.uniform(370.0, 390.0), 1)
            current = round(power / voltage * 1000, 1)
            temperature = round(random.uniform(30.0, 55.0), 1)
            energy_delta = power * (self.config.meter_sample_interval / 3600)
            self._meter_value += energy_delta

            self._sim_power = power
            self._sim_voltage = voltage
            self._sim_current = current
            self._sim_temperature = temperature

            # Send MeterValues via protocol
            now = datetime.now(UTC).isoformat()
            self._protocol.build_meter_values(MeterValuesRequest(
                connector_id=self._connector_id,
                transaction_id=self._transaction_id,
                meter_value=[MeterValue(
                    timestamp=now,
                    sampled_value=[
                        SampledValue(str(round(voltage, 1)), Measurand.VOLTAGE, UnitOfMeasure.V),
                        SampledValue(str(round(current, 1)), Measurand.CURRENT_IMPORT, UnitOfMeasure.A),
                        SampledValue(str(round(power * 1000, 0)), Measurand.POWER_ACTIVE_IMPORT, UnitOfMeasure.W),
                        SampledValue(str(round(self._meter_value * 1000, 0)), Measurand.ENERGY_ACTIVE_IMPORT_REGISTER, UnitOfMeasure.WH),
                        SampledValue(str(round(temperature, 1)), Measurand.TEMPERATURE, UnitOfMeasure.CELSIUS),
                    ],
                )],
            ))
            self._protocol.handle_meter_values_response({})

            self._emit_telemetry(
                power=power,
                voltage=voltage,
                current=current,
                temperature=temperature,
                status="Charging",
            )

            # Occasionally simulate temperature alarm
            if temperature > 50.0 and random.random() < 0.1:
                self._emit_alarm("high_temperature", f"Charger temperature high: {temperature}°C")

            await asyncio.sleep(self.config.meter_sample_interval)

        # StopTransaction
        meter_stop = int(self._meter_value * 1000)  # kWh → Wh
        self._protocol.build_stop_transaction(StopTransactionRequest(
            transaction_id=self._transaction_id,
            meter_stop=meter_stop,
            reason=StopReason.EV_DISCONNECTED,
            id_tag=id_tag,
        ))
        self._protocol.handle_stop_transaction_response({
            "idTagInfo": {"status": "Accepted"},
        })
        self._protocol.remove_transaction(self._transaction_id)
        logger.info(
            "OCPP simulated StopTransaction: transactionId=%d meterStop=%d reason=EVDisconnected",
            self._transaction_id, meter_stop,
        )
        self._is_charging = False

        # StatusNotification: Available
        self._protocol.build_status_notification(StatusNotificationRequest(
            connector_id=self._connector_id,
            error_code=ChargePointErrorCode.NO_ERROR,
            status=ChargePointStatus.AVAILABLE,
        ))
        self._protocol.handle_status_notification_response({})
        logger.info("OCPP simulated StatusNotification: status=Available connector=%d", self._connector_id)
        self._status = "Available"

    async def _simulate_idle_period(self) -> None:
        """Simulate idle period with periodic MeterValues"""
        duration = random.randint(5, 15)
        for _ in range(duration):
            if not self._running:
                break
            self._sim_power = 0.0
            self._sim_voltage = 380.0
            self._sim_current = 0.0
            self._sim_temperature = round(random.uniform(22.0, 28.0), 1)

            # Send idle MeterValues via protocol
            now = datetime.now(UTC).isoformat()
            self._protocol.build_meter_values(MeterValuesRequest(
                connector_id=self._connector_id,
                meter_value=[MeterValue(
                    timestamp=now,
                    sampled_value=[
                        SampledValue(str(round(self._sim_voltage, 1)), Measurand.VOLTAGE, UnitOfMeasure.V),
                        SampledValue(str(round(self._sim_current, 1)), Measurand.CURRENT_IMPORT, UnitOfMeasure.A),
                        SampledValue("0", Measurand.POWER_ACTIVE_IMPORT, UnitOfMeasure.W),
                        SampledValue(str(round(self._meter_value * 1000, 0)), Measurand.ENERGY_ACTIVE_IMPORT_REGISTER, UnitOfMeasure.WH),
                        SampledValue(str(round(self._sim_temperature, 1)), Measurand.TEMPERATURE, UnitOfMeasure.CELSIUS),
                    ],
                )],
            ))
            self._protocol.handle_meter_values_response({})

            self._emit_telemetry(
                power=0.0,
                voltage=380.0,
                current=0.0,
                temperature=self._sim_temperature,
                status="Available",
            )
            await asyncio.sleep(self.config.meter_sample_interval)

    # ── Real charger WebSocket connection (OCPP 1.6J ChargePoint) ──────

    async def _run_real_charger(self) -> None:
        """Connect to a real OCPP CSMS as a ChargePoint via WebSocket.

        Implements the full OCPP 1.6J ChargePoint protocol:
          - BootNotification
          - Heartbeat
          - MeterValues
          - StatusNotification
          - StartTransaction / StopTransaction
          - Authorize
        """
        try:
            import websockets
            from ocpp.routing import after, on
            from ocpp.v16 import ChargePoint as Cp
            from ocpp.v16.enums import (
                Action,
            )
            from ocpp.v16.enums import (
                ChargePointErrorCode as OcppCpErrorCode,
            )
            from ocpp.v16.enums import (
                ChargePointStatus as OcppCpStatus,
            )
            from ocpp.v16.enums import (
                RegistrationStatus as OcppRegStatus,
            )

            adapter = self

            class TianlianChargePoint(Cp):
                """OCPP 1.6J ChargePoint implementation for Tianlian Edge Gateway"""

                @after(Action.boot_notification)
                async def after_boot_notification(self, charge_point_vendor, charge_point_model, **kwargs):
                    logger.info(
                        "OCPP BootNotification sent: vendor=%s model=%s charger=%s",
                        charge_point_vendor, charge_point_model, adapter.config.charger_id,
                    )
                    adapter._protocol.build_boot_notification(BootNotificationRequest(
                        charge_point_vendor=charge_point_vendor,
                        charge_point_model=charge_point_model,
                    ))

                @after(Action.heartbeat)
                async def after_heartbeat(self, **kwargs):
                    logger.debug("OCPP Heartbeat sent: charger=%s", adapter.config.charger_id)
                    adapter._protocol.build_heartbeat()

                @after(Action.meter_values)
                async def after_meter_values(self, connector_id, meter_value, **kwargs):
                    logger.debug(
                        "OCPP MeterValues sent: connector=%d samples=%d",
                        connector_id, len(meter_value),
                    )

                @after(Action.status_notification)
                async def after_status_notification(self, connector_id, error_code, status, **kwargs):
                    logger.info(
                        "OCPP StatusNotification sent: connector=%d status=%s error=%s",
                        connector_id, status, error_code,
                    )

                @after(Action.start_transaction)
                async def after_start_transaction(self, connector_id, id_tag, meter_start, **kwargs):
                    logger.info(
                        "OCPP StartTransaction sent: connector=%d idTag=%s meterStart=%d",
                        connector_id, id_tag, meter_start,
                    )

                @after(Action.stop_transaction)
                async def after_stop_transaction(self, transaction_id, meter_stop, **kwargs):
                    logger.info(
                        "OCPP StopTransaction sent: transactionId=%d meterStop=%d",
                        transaction_id, meter_stop,
                    )

                @after(Action.authorize)
                async def after_authorize(self, id_tag, **kwargs):
                    logger.info("OCPP Authorize sent: idTag=%s", id_tag)

                @on(Action.remote_start_transaction)
                async def on_remote_start_transaction(self, id_tag, connector_id=None, **kwargs):
                    """Handle remote start command from CSMS"""
                    logger.info("OCPP RemoteStartTransaction received: idTag=%s", id_tag)
                    adapter._is_charging = True
                    adapter._status = "Charging"
                    return {"status": "Accepted"}

                @on(Action.remote_stop_transaction)
                async def on_remote_stop_transaction(self, transaction_id, **kwargs):
                    """Handle remote stop command from CSMS"""
                    logger.info("OCPP RemoteStopTransaction received: transactionId=%d", transaction_id)
                    adapter._is_charging = False
                    adapter._status = "Available"
                    return {"status": "Accepted"}

                @on(Action.reset)
                async def on_reset(self, type, **kwargs):
                    """Handle reset command from CSMS"""
                    logger.info("OCPP Reset received: type=%s", type)
                    return {"status": "Accepted"}

            # Parse WebSocket URL
            url = self.config.ws_url
            logger.info("OCPP connecting to CSMS at %s", url)

            async with websockets.connect(
                url,
                subprotocols=["ocpp1.6"],
                ping_interval=30,
                ping_timeout=10,
            ) as ws:
                self._ws_connected = True
                cp = TianlianChargePoint(
                    id=self.config.charger_id,
                    connection=ws,
                )

                logger.info("OCPP WebSocket connected to %s", url)

                try:
                    # 1. Send BootNotification
                    boot_result = await cp.call(_ocpp_call.BootNotification(
                        charge_point_vendor=self.config.charger_vendor,
                        charge_point_model=self.config.charger_model,
                        charge_point_serial_number=self.config.charger_id,
                        charge_box_serial_number=f"CB-{self.config.charger_id}",
                        firmware_version="1.0.0",
                        iccid="",
                        imsi="",
                        meter_type="Tianlian SmartMeter",
                        meter_serial_number=f"MTR-{self.config.charger_id}",
                    ))
                    logger.info(
                        "OCPP BootNotification response: status=%s interval=%s currentTime=%s",
                        boot_result.status,
                        getattr(boot_result, "interval", "N/A"),
                        getattr(boot_result, "current_time", "N/A"),
                    )

                    if boot_result.status != OcppRegStatus.accepted:
                        logger.error("OCPP BootNotification rejected: %s", boot_result.status)
                        self._ws_connected = False
                        return

                    # 2. Send initial StatusNotification
                    await cp.call(_ocpp_call.StatusNotification(
                        connector_id=self._connector_id,
                        error_code=OcppCpErrorCode.no_error,
                        status=OcppCpStatus.available,
                        timestamp=datetime.now(UTC).isoformat(),
                    ))

                    # 3. Main message loop: heartbeat + meter values
                    heartbeat_task = asyncio.create_task(
                        self._real_heartbeat_loop(cp)
                    )
                    meter_task = asyncio.create_task(
                        self._real_meter_loop(cp)
                    )

                    # Wait for either task to complete or connection to close
                    done, pending = await asyncio.wait(
                        [heartbeat_task, meter_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in pending:
                        task.cancel()

                except websockets.exceptions.ConnectionClosed as e:
                    logger.warning("OCPP WebSocket connection closed: code=%d reason=%s", e.code, e.reason)
                    self._ws_connected = False
                    # Reconnect if still running
                    if self._running:
                        logger.info("Reconnecting OCPP in %ds", self.config.heartbeat_interval)
                        await asyncio.sleep(self.config.heartbeat_interval)
                        await self._run_real_charger()
                    return
                except Exception as e:
                    logger.error("OCPP ChargePoint error: %s", e)
                    # Trigger reconnect via outer handler
                    self._ws_connected = False
                    if self._running:
                        raise
                finally:
                    self._ws_connected = False

        except ImportError as e:
            logger.error("OCPP real charger mode requires 'ocpp' and 'websockets' packages: %s", e)
            logger.info("Falling back to simulation mode")
            self.config.use_real_charger = False
            await self._run_simulated_charger()
        except (TimeoutError, OSError, ConnectionRefusedError) as e:
            self._reconnect_count += 1
            logger.error("OCPP WebSocket connection failed: %s (attempt %d/%d)",
                         e, self._reconnect_count, self._max_reconnects)
            if self._reconnect_count >= self._max_reconnects:
                logger.warning("Max reconnects (%d) reached, falling back to simulation",
                              self._max_reconnects)
                self.config.use_real_charger = False
                await self._run_simulated_charger()
                return
            logger.info("Will retry connection in %d seconds", self.config.heartbeat_interval)
            await asyncio.sleep(self.config.heartbeat_interval)
            if self._running:
                await self._run_real_charger()
        except Exception as e:
            self._reconnect_count += 1
            logger.error("OCPP real charger unexpected error: %s (attempt %d/%d)",
                         e, self._reconnect_count, self._max_reconnects)
            if self._reconnect_count >= self._max_reconnects:
                logger.warning("Max reconnects (%d) reached, falling back to simulation",
                              self._max_reconnects)
                self.config.use_real_charger = False
                await self._run_simulated_charger()
                return
            logger.info("Will retry connection in %d seconds", self.config.heartbeat_interval)
            await asyncio.sleep(self.config.heartbeat_interval)
            if self._running:
                await self._run_real_charger()

    async def _real_heartbeat_loop(self, cp) -> None:
        """Send periodic Heartbeat messages to CSMS"""
        while self._running and self._ws_connected:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                if not self._running or not self._ws_connected:
                    break
                heartbeat = await cp.call(_ocpp_call.Heartbeat())
                logger.debug(
                    "OCPP Heartbeat response: currentTime=%s",
                    heartbeat.current_time,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("OCPP Heartbeat error: %s", e)

    async def _real_meter_loop(self, cp) -> None:
        """Send periodic MeterValues to CSMS with voltage/current/power/energy"""
        while self._running and self._ws_connected:
            try:
                await asyncio.sleep(self.config.meter_sample_interval)
                if not self._running or not self._ws_connected:
                    break

                # Build MeterValues payload
                from ocpp.v16.enums import Measurand as OcppMeasurand
                from ocpp.v16.enums import ReadingContext as OcppContext
                from ocpp.v16.enums import UnitOfMeasure as OcppUnit

                now = datetime.now(UTC).isoformat()
                sampled_values = [
                    {
                        "value": str(round(self._last_voltage, 1)),
                        "measurand": OcppMeasurand.voltage.value,
                        "unit": OcppUnit.v.value,
                        "context": OcppContext.sample_periodic.value,
                    },
                    {
                        "value": str(round(self._last_current, 1)),
                        "measurand": OcppMeasurand.current_import.value,
                        "unit": OcppUnit.a.value,
                        "context": OcppContext.sample_periodic.value,
                    },
                    {
                        "value": str(round(self._last_power * 1000, 0)),  # kW → W
                        "measurand": OcppMeasurand.power_active_import.value,
                        "unit": OcppUnit.w.value,
                        "context": OcppContext.sample_periodic.value,
                    },
                    {
                        "value": str(round(self._meter_value * 1000, 0)),  # kWh → Wh
                        "measurand": OcppMeasurand.energy_active_import_register.value,
                        "unit": OcppUnit.wh.value,
                        "context": OcppContext.sample_periodic.value,
                    },
                    {
                        "value": str(round(self._last_temperature, 1)),
                        "measurand": OcppMeasurand.temperature.value,
                        "unit": OcppUnit.celsius.value,
                        "context": OcppContext.sample_periodic.value,
                    },
                ]

                await cp.call(_ocpp_call.MeterValues(
                    connector_id=self._connector_id,
                    meter_value=[{
                        "timestamp": now,
                        "sampledValue": sampled_values,
                    }],
                ))

                # Emit telemetry through callback
                self._emit_telemetry(
                    power=self._last_power,
                    voltage=self._last_voltage,
                    current=self._last_current,
                    temperature=self._last_temperature,
                    status=self._status,
                )

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("OCPP MeterValues error: %s", e)

    # ── Periodic loops (simulated mode) ────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat (simulated mode)"""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                if self._running and not self.config.use_real_charger:
                    self._protocol.build_heartbeat()
                    self._protocol.handle_heartbeat_response({
                        "currentTime": datetime.now(UTC).isoformat(),
                    })
                    logger.debug("OCPP heartbeat: charger=%s", self.config.charger_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("OCPP heartbeat error: %s", e)

    async def _meter_loop(self) -> None:
        """Emit meter value telemetry at configured interval.

        In simulation mode, this is handled by _simulate_charging_session.
        In real mode, MeterValues arrive asynchronously from the charger.
        This loop provides a fallback for real mode.
        """
        while self._running:
            try:
                await asyncio.sleep(self.config.meter_sample_interval)
                if self.config.use_real_charger and self._running:
                    self._emit_telemetry(
                        power=self._last_power,
                        voltage=self._last_voltage,
                        current=self._last_current,
                        temperature=self._last_temperature,
                        status=self._status,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("OCPP meter loop error: %s", e)

    # ── Manual simulation injection (for debug API) ───────────────────

    def inject_telemetry(
        self,
        power: float = 0.0,
        voltage: float = 380.0,
        current: float = 0.0,
        temperature: float = 25.0,
        energy: float | None = None,
        status: str = "Available",
    ) -> TelemetryPoint:
        """Manually inject a telemetry point (for debug/simulation API).

        Returns the created TelemetryPoint.
        """
        if energy is not None:
            self._meter_value = energy

        self._sim_power = power
        self._sim_voltage = voltage
        self._sim_current = current
        self._sim_temperature = temperature
        self._status = status

        point = TelemetryPoint(
            device_id=self.config.charger_id,
            power=power,
            voltage=voltage,
            current=current,
            temperature=temperature,
            energy=round(self._meter_value, 3),
            status=status,
        )

        if self._on_telemetry:
            self._on_telemetry(point)

        logger.info(
            "OCPP injected telemetry: charger=%s power=%.1fkW voltage=%.1fV current=%.1fA temp=%.1f°C status=%s",
            self.config.charger_id, power, voltage, current, temperature, status,
        )

        return point

    def inject_alarm(self, alarm_type: str, message: str) -> None:
        """Manually trigger an alarm (for debug/simulation API)."""
        self._emit_alarm(alarm_type, message)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _emit_telemetry(
        self,
        power: float,
        voltage: float,
        current: float,
        temperature: float,
        status: str,
    ) -> None:
        """Emit a telemetry point through the registered callback"""
        point = TelemetryPoint(
            device_id=self.config.charger_id,
            power=power,
            voltage=voltage,
            current=current,
            temperature=temperature,
            energy=round(self._meter_value, 3),
            status=status,
        )

        if self._on_telemetry:
            self._on_telemetry(point)

        logger.debug(
            "OCPP telemetry: charger=%s power=%.1fkW voltage=%.1fV current=%.1fA temp=%.1f°C energy=%.3fkWh status=%s",
            self.config.charger_id, power, voltage, current, temperature, self._meter_value, status,
        )

    def _emit_alarm(self, alarm_type: str, message: str) -> None:
        """Emit an alarm through the registered callback"""
        if self._on_alarm:
            self._on_alarm(self.config.charger_id, alarm_type, message)

        logger.warning(
            "OCPP alarm: charger=%s type=%s message=%s",
            self.config.charger_id, alarm_type, message,
        )
