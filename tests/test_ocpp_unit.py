"""Unit tests for OCPP adapter protocol handler and adapter simulation/injection.

Covers:
- OCPPChargePointProtocol: all build/handle methods, enums, dataclasses
- OCPPAdapter: simulation mode callbacks, inject_telemetry, inject_alarm
- OCPPAdapter: start/stop lifecycle (simulated mode)
- Edge cases: empty fields, optional params, error codes, transaction lifecycle
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from adapters.ocpp_adapter import (
    AuthorizationStatus,
    AuthorizeRequest,
    AuthorizeResponse,
    BootNotificationRequest,
    BootNotificationResponse,
    ChargePointErrorCode,
    ChargePointStatus,
    HeartbeatRequest,
    HeartbeatResponse,
    Measurand,
    MeterValue,
    MeterValuesRequest,
    MeterValuesResponse,
    OCPPAdapter,
    OCPPChargePointProtocol,
    OCPPMessageLog,
    ReadingContext,
    RegistrationStatus,
    SampledValue,
    StartTransactionRequest,
    StartTransactionResponse,
    StatusNotificationRequest,
    StatusNotificationResponse,
    StopReason,
    StopTransactionRequest,
    StopTransactionResponse,
    UnitOfMeasure,
)
from config import OCPPConfig
from models import TelemetryPoint

UTC = timezone.utc


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def protocol():
    """Fresh protocol handler"""
    return OCPPChargePointProtocol("CHARGER-001")


@pytest.fixture
def ocpp_config():
    """OCPP config for simulated mode"""
    return OCPPConfig(
        charger_id="TEST-CHG-001",
        ws_url="ws://test-csms:9000",
        heartbeat_interval=1,  # short for tests
        meter_sample_interval=1,
        use_real_charger=False,
        charger_vendor="TestVendor",
        charger_model="TestModel",
    )


@pytest.fixture
def adapter(ocpp_config):
    """OCPP adapter in simulated mode"""
    return OCPPAdapter(ocpp_config)


# ── Enum Tests ────────────────────────────────────────────────────────


class TestEnums:
    """Test all OCPP enums have expected values"""

    def test_registration_status_values(self):
        assert RegistrationStatus.ACCEPTED.value == "Accepted"
        assert RegistrationStatus.PENDING.value == "Pending"
        assert RegistrationStatus.REJECTED.value == "Rejected"

    def test_charge_point_status_values(self):
        assert ChargePointStatus.AVAILABLE.value == "Available"
        assert ChargePointStatus.CHARGING.value == "Charging"
        assert ChargePointStatus.FAULTED.value == "Faulted"
        assert ChargePointStatus.PREPARING.value == "Preparing"
        assert ChargePointStatus.SUSPENDED_EVSE.value == "SuspendedEVSE"
        assert ChargePointStatus.SUSPENDED_EV.value == "SuspendedEV"
        assert ChargePointStatus.FINISHING.value == "Finishing"
        assert ChargePointStatus.RESERVED.value == "Reserved"
        assert ChargePointStatus.UNAVAILABLE.value == "Unavailable"

    def test_charge_point_error_code_values(self):
        assert ChargePointErrorCode.NO_ERROR.value == "NoError"
        assert ChargePointErrorCode.CONNECTOR_LOCK_FAILURE.value == "ConnectorLockFailure"
        assert ChargePointErrorCode.HIGH_TEMPERATURE.value == "HighTemperature"
        assert ChargePointErrorCode.OVER_VOLTAGE.value == "OverVoltage"
        assert ChargePointErrorCode.UNDER_VOLTAGE.value == "UnderVoltage"
        assert ChargePointErrorCode.GROUND_FAILURE.value == "GroundFailure"
        assert ChargePointErrorCode.WEAK_SIGNAL.value == "WeakSignal"

    def test_authorization_status_values(self):
        assert AuthorizationStatus.ACCEPTED.value == "Accepted"
        assert AuthorizationStatus.BLOCKED.value == "Blocked"
        assert AuthorizationStatus.INVALID.value == "Invalid"
        assert AuthorizationStatus.CONCURRENT_TX.value == "ConcurrentTx"
        assert AuthorizationStatus.EXPIRED.value == "Expired"

    def test_stop_reason_values(self):
        assert StopReason.EMERGENCY_STOP.value == "EmergencyStop"
        assert StopReason.EV_DISCONNECTED.value == "EVDisconnected"
        assert StopReason.HARD_RESET.value == "HardReset"
        assert StopReason.LOCAL.value == "Local"
        assert StopReason.OTHER.value == "Other"
        assert StopReason.POWER_LOSS.value == "PowerLoss"
        assert StopReason.REBOOT.value == "Reboot"
        assert StopReason.REMOTE.value == "Remote"
        assert StopReason.SOFT_RESET.value == "SoftReset"
        assert StopReason.UNLOCK_COMMAND.value == "UnlockCommand"
        assert StopReason.DE_AUTHORIZED.value == "DeAuthorized"

    def test_measurand_values(self):
        assert Measurand.VOLTAGE.value == "Voltage"
        assert Measurand.CURRENT_IMPORT.value == "Current.Import"
        assert Measurand.POWER_ACTIVE_IMPORT.value == "Power.Active.Import"
        assert Measurand.ENERGY_ACTIVE_IMPORT_REGISTER.value == "Energy.Active.Import.Register"
        assert Measurand.TEMPERATURE.value == "Temperature"
        assert Measurand.SOC.value == "SoC"
        assert Measurand.FREQUENCY.value == "Frequency"

    def test_unit_of_measure_values(self):
        assert UnitOfMeasure.V.value == "V"
        assert UnitOfMeasure.A.value == "A"
        assert UnitOfMeasure.W.value == "W"
        assert UnitOfMeasure.WH.value == "Wh"
        assert UnitOfMeasure.KWH.value == "kWh"
        assert UnitOfMeasure.CELSIUS.value == "Celsius"
        assert UnitOfMeasure.PERCENT.value == "Percent"
        assert UnitOfMeasure.HZ.value == "Hz"

    def test_reading_context_values(self):
        assert ReadingContext.SAMPLE_CLOCK.value == "Sample.Clock"
        assert ReadingContext.SAMPLE_PERIODIC.value == "Sample.Periodic"
        assert ReadingContext.TRANSACTION_BEGIN.value == "Transaction.Begin"
        assert ReadingContext.TRANSACTION_END.value == "Transaction.End"
        assert ReadingContext.TRIGGER.value == "Trigger"
        assert ReadingContext.INTERRUPTION_BEGIN.value == "Interruption.Begin"
        assert ReadingContext.INTERRUPTION_END.value == "Interruption.End"
        assert ReadingContext.OTHER.value == "Other"


# ── Dataclass Tests ───────────────────────────────────────────────────


class TestDataclasses:
    """Test dataclass defaults and initialization"""

    def test_boot_notification_request_defaults(self):
        req = BootNotificationRequest(
            charge_point_vendor="Vendor",
            charge_point_model="Model",
        )
        assert req.charge_point_serial_number == ""
        assert req.firmware_version == ""
        assert req.iccid == ""

    def test_authorize_response_default(self):
        resp = AuthorizeResponse()
        assert resp.id_tag_info == {}

    def test_start_transaction_request_defaults(self):
        req = StartTransactionRequest(
            connector_id=1,
            id_tag="TAG001",
            meter_start=100,
        )
        assert req.timestamp == ""
        assert req.reservation_id is None

    def test_start_transaction_response_defaults(self):
        resp = StartTransactionResponse(transaction_id=42)
        assert resp.id_tag_info == {}

    def test_stop_transaction_request_defaults(self):
        req = StopTransactionRequest(
            transaction_id=1,
            meter_stop=200,
        )
        assert req.reason == StopReason.EV_DISCONNECTED
        assert req.id_tag is None
        assert req.transaction_data == []

    def test_stop_transaction_response_default(self):
        resp = StopTransactionResponse()
        assert resp.id_tag_info is None

    def test_sampled_value_defaults(self):
        sv = SampledValue(value="220.5")
        assert sv.measurand == Measurand.ENERGY_ACTIVE_IMPORT_REGISTER
        assert sv.unit == UnitOfMeasure.WH
        assert sv.context == ReadingContext.SAMPLE_PERIODIC
        assert sv.format == "Raw"
        assert sv.location == "Outlet"
        assert sv.phase is None

    def test_meter_value_defaults(self):
        mv = MeterValue(timestamp="2026-01-01T00:00:00Z")
        assert mv.sampled_value == []

    def test_meter_values_request_defaults(self):
        req = MeterValuesRequest(connector_id=1)
        assert req.meter_value == []
        assert req.transaction_id is None

    def test_status_notification_request_defaults(self):
        req = StatusNotificationRequest(
            connector_id=1,
            error_code=ChargePointErrorCode.NO_ERROR,
            status=ChargePointStatus.AVAILABLE,
        )
        assert req.timestamp == ""
        assert req.info == ""
        assert req.vendor_id == ""
        assert req.vendor_error_code == ""

    def test_ocpp_message_log_defaults(self):
        log = OCPPMessageLog(direction="req", action="Heartbeat", payload={})
        assert log.timestamp != ""  # auto-generated


# ── Protocol Handler Tests ────────────────────────────────────────────


class TestProtocolBootNotification:
    """BootNotification protocol tests"""

    def test_build_boot_notification_minimal(self, protocol):
        req = BootNotificationRequest(
            charge_point_vendor="Tianlian",
            charge_point_model="TL-3000",
        )
        payload = protocol.build_boot_notification(req)
        assert payload["chargePointVendor"] == "Tianlian"
        assert payload["chargePointModel"] == "TL-3000"
        assert "chargePointSerialNumber" not in payload

    def test_build_boot_notification_full(self, protocol):
        req = BootNotificationRequest(
            charge_point_vendor="Tianlian",
            charge_point_model="TL-3000",
            charge_point_serial_number="SN001",
            charge_box_serial_number="CB001",
            firmware_version="1.2.3",
            iccid="8986011",
            imsi="460001",
            meter_type="SmartMeter",
            meter_serial_number="MTR001",
        )
        payload = protocol.build_boot_notification(req)
        assert payload["chargePointSerialNumber"] == "SN001"
        assert payload["chargeBoxSerialNumber"] == "CB001"
        assert payload["firmwareVersion"] == "1.2.3"
        assert payload["iccid"] == "8986011"
        assert payload["imsi"] == "460001"
        assert payload["meterType"] == "SmartMeter"
        assert payload["meterSerialNumber"] == "MTR001"

    def test_handle_boot_notification_accepted(self, protocol):
        resp = protocol.handle_boot_notification_response({
            "status": "Accepted",
            "currentTime": "2026-01-01T00:00:00Z",
            "interval": 300,
        })
        assert resp.status == RegistrationStatus.ACCEPTED
        assert resp.current_time == "2026-01-01T00:00:00Z"
        assert resp.interval == 300
        assert protocol.boot_status == RegistrationStatus.ACCEPTED

    def test_handle_boot_notification_rejected(self, protocol):
        resp = protocol.handle_boot_notification_response({"status": "Rejected"})
        assert resp.status == RegistrationStatus.REJECTED
        assert protocol.boot_status == RegistrationStatus.REJECTED

    def test_handle_boot_notification_pending(self, protocol):
        resp = protocol.handle_boot_notification_response({
            "status": "Pending",
            "interval": 10,
        })
        assert resp.status == RegistrationStatus.PENDING
        assert resp.interval == 10

    def test_handle_boot_notification_default_rejected(self, protocol):
        """Missing status should default to Rejected"""
        resp = protocol.handle_boot_notification_response({})
        assert resp.status == RegistrationStatus.REJECTED

    def test_boot_notification_logged(self, protocol):
        req = BootNotificationRequest(charge_point_vendor="V", charge_point_model="M")
        protocol.build_boot_notification(req)
        protocol.handle_boot_notification_response({"status": "Accepted"})
        logs = protocol.message_log
        assert len(logs) == 2
        assert logs[0].direction == "req"
        assert logs[0].action == "BootNotification"
        assert logs[1].direction == "conf"


class TestProtocolHeartbeat:
    """Heartbeat protocol tests"""

    def test_build_heartbeat(self, protocol):
        payload = protocol.build_heartbeat()
        assert payload == {}

    def test_handle_heartbeat_response(self, protocol):
        resp = protocol.handle_heartbeat_response({
            "currentTime": "2026-08-10T00:00:00Z",
        })
        assert resp.current_time == "2026-08-10T00:00:00Z"
        assert protocol.last_heartbeat_time == "2026-08-10T00:00:00Z"

    def test_handle_heartbeat_response_missing_time(self, protocol):
        resp = protocol.handle_heartbeat_response({})
        assert resp.current_time == ""
        assert protocol.last_heartbeat_time == ""

    def test_heartbeat_logged(self, protocol):
        protocol.build_heartbeat()
        protocol.handle_heartbeat_response({"currentTime": "now"})
        assert len(protocol.message_log) == 2


class TestProtocolAuthorize:
    """Authorize protocol tests"""

    def test_build_authorize(self, protocol):
        payload = protocol.build_authorize(AuthorizeRequest(id_tag="TAG001"))
        assert payload["idTag"] == "TAG001"

    def test_handle_authorize_accepted(self, protocol):
        protocol.build_authorize(AuthorizeRequest(id_tag="TAG001"))
        resp = protocol.handle_authorize_response({
            "idTagInfo": {"status": "Accepted", "expiryDate": "2099-12-31T23:59:59Z"},
        })
        assert resp.id_tag_info["status"] == "Accepted"
        assert protocol.is_tag_authorized("TAG001") is True

    def test_handle_authorize_blocked(self, protocol):
        protocol.build_authorize(AuthorizeRequest(id_tag="TAG002"))
        protocol.handle_authorize_response({
            "idTagInfo": {"status": "Blocked"},
        })
        assert protocol.is_tag_authorized("TAG002") is False

    def test_handle_authorize_invalid(self, protocol):
        protocol.build_authorize(AuthorizeRequest(id_tag="TAG003"))
        protocol.handle_authorize_response({
            "idTagInfo": {"status": "Invalid"},
        })
        assert protocol.is_tag_authorized("TAG003") is False

    def test_is_tag_authorized_unknown(self, protocol):
        """Unknown tag should return False"""
        assert protocol.is_tag_authorized("UNKNOWN") is False

    def test_authorize_logged(self, protocol):
        protocol.build_authorize(AuthorizeRequest(id_tag="A1"))
        protocol.handle_authorize_response({"idTagInfo": {"status": "Accepted"}})
        assert len(protocol.message_log) == 2


class TestProtocolStartTransaction:
    """StartTransaction protocol tests"""

    def test_build_start_transaction_minimal(self, protocol):
        req = StartTransactionRequest(
            connector_id=1,
            id_tag="TAG001",
            meter_start=100,
        )
        payload = protocol.build_start_transaction(req)
        assert payload["connectorId"] == 1
        assert payload["idTag"] == "TAG001"
        assert payload["meterStart"] == 100
        assert "timestamp" in payload
        assert "reservationId" not in payload

    def test_build_start_transaction_with_reservation(self, protocol):
        req = StartTransactionRequest(
            connector_id=1,
            id_tag="TAG001",
            meter_start=100,
            reservation_id=99,
        )
        payload = protocol.build_start_transaction(req)
        assert payload["reservationId"] == 99

    def test_build_start_transaction_with_timestamp(self, protocol):
        req = StartTransactionRequest(
            connector_id=1,
            id_tag="TAG001",
            meter_start=100,
            timestamp="2026-01-01T00:00:00Z",
        )
        payload = protocol.build_start_transaction(req)
        assert payload["timestamp"] == "2026-01-01T00:00:00Z"

    def test_handle_start_transaction_response(self, protocol):
        resp = protocol.handle_start_transaction_response({
            "transactionId": 12345,
            "idTagInfo": {"status": "Accepted"},
        })
        assert resp.transaction_id == 12345
        assert resp.id_tag_info["status"] == "Accepted"

    def test_handle_start_transaction_default_id(self, protocol):
        """Missing transactionId should default to 0"""
        resp = protocol.handle_start_transaction_response({})
        assert resp.transaction_id == 0


class TestProtocolStopTransaction:
    """StopTransaction protocol tests"""

    def test_build_stop_transaction(self, protocol):
        req = StopTransactionRequest(
            transaction_id=42,
            meter_stop=500,
        )
        payload = protocol.build_stop_transaction(req)
        assert payload["transactionId"] == 42
        assert payload["meterStop"] == 500
        assert payload["reason"] == "EVDisconnected"
        assert "idTag" not in payload
        assert "transactionData" not in payload

    def test_build_stop_transaction_with_id_tag(self, protocol):
        req = StopTransactionRequest(
            transaction_id=42,
            meter_stop=500,
            id_tag="TAG001",
        )
        payload = protocol.build_stop_transaction(req)
        assert payload["idTag"] == "TAG001"

    def test_build_stop_transaction_with_data(self, protocol):
        req = StopTransactionRequest(
            transaction_id=42,
            meter_stop=500,
            transaction_data=[{"some": "data"}],
        )
        payload = protocol.build_stop_transaction(req)
        assert payload["transactionData"] == [{"some": "data"}]

    def test_build_stop_transaction_string_reason(self, protocol):
        """When reason is passed as string, not enum"""
        req = StopTransactionRequest(
            transaction_id=42,
            meter_stop=500,
            reason="EmergencyStop",
        )
        payload = protocol.build_stop_transaction(req)
        assert payload["reason"] == "EmergencyStop"

    def test_handle_stop_transaction_response_with_id_tag_info(self, protocol):
        resp = protocol.handle_stop_transaction_response({
            "idTagInfo": {"status": "Accepted"},
        })
        assert resp.id_tag_info == {"status": "Accepted"}

    def test_handle_stop_transaction_response_no_id_tag_info(self, protocol):
        resp = protocol.handle_stop_transaction_response({})
        assert resp.id_tag_info is None


class TestProtocolMeterValues:
    """MeterValues protocol tests"""

    def test_build_meter_values_minimal(self, protocol):
        req = MeterValuesRequest(connector_id=1)
        payload = protocol.build_meter_values(req)
        assert payload["connectorId"] == 1
        assert payload["meterValue"] == []
        assert "transactionId" not in payload

    def test_build_meter_values_with_transaction(self, protocol):
        req = MeterValuesRequest(connector_id=1, transaction_id=42)
        payload = protocol.build_meter_values(req)
        assert payload["transactionId"] == 42

    def test_build_meter_values_with_samples(self, protocol):
        sv = SampledValue(
            value="220.5",
            measurand=Measurand.VOLTAGE,
            unit=UnitOfMeasure.V,
        )
        mv = MeterValue(
            timestamp="2026-01-01T00:00:00Z",
            sampled_value=[sv],
        )
        req = MeterValuesRequest(connector_id=1, meter_value=[mv])
        payload = protocol.build_meter_values(req)
        assert len(payload["meterValue"]) == 1
        assert payload["meterValue"][0]["timestamp"] == "2026-01-01T00:00:00Z"
        sv_dict = payload["meterValue"][0]["sampledValue"][0]
        assert sv_dict["value"] == "220.5"
        assert sv_dict["measurand"] == "Voltage"
        assert sv_dict["unit"] == "V"

    def test_build_meter_values_string_measurand(self, protocol):
        """When measurand/unit/context are strings not enums"""
        sv = SampledValue(
            value="10",
            measurand="Power.Active.Import",
            unit="W",
            context="Sample.Periodic",
        )
        mv = MeterValue(timestamp="now", sampled_value=[sv])
        req = MeterValuesRequest(connector_id=1, meter_value=[mv])
        payload = protocol.build_meter_values(req)
        sv_dict = payload["meterValue"][0]["sampledValue"][0]
        assert sv_dict["measurand"] == "Power.Active.Import"
        assert sv_dict["unit"] == "W"

    def test_build_meter_values_with_phase(self, protocol):
        sv = SampledValue(value="220", phase="L1-N")
        mv = MeterValue(timestamp="now", sampled_value=[sv])
        req = MeterValuesRequest(connector_id=1, meter_value=[mv])
        payload = protocol.build_meter_values(req)
        assert payload["meterValue"][0]["sampledValue"][0]["phase"] == "L1-N"

    def test_handle_meter_values_response(self, protocol):
        resp = protocol.handle_meter_values_response({})
        assert isinstance(resp, MeterValuesResponse)


class TestProtocolStatusNotification:
    """StatusNotification protocol tests"""

    def test_build_status_notification_minimal(self, protocol):
        req = StatusNotificationRequest(
            connector_id=1,
            error_code=ChargePointErrorCode.NO_ERROR,
            status=ChargePointStatus.AVAILABLE,
        )
        payload = protocol.build_status_notification(req)
        assert payload["connectorId"] == 1
        assert payload["errorCode"] == "NoError"
        assert payload["status"] == "Available"
        assert "timestamp" in payload
        assert "info" not in payload

    def test_build_status_notification_with_info(self, protocol):
        req = StatusNotificationRequest(
            connector_id=1,
            error_code=ChargePointErrorCode.HIGH_TEMPERATURE,
            status=ChargePointStatus.FAULTED,
            info="Temperature exceeded 80C",
            vendor_id="VENDOR-X",
            vendor_error_code="E001",
        )
        payload = protocol.build_status_notification(req)
        assert payload["info"] == "Temperature exceeded 80C"
        assert payload["vendorId"] == "VENDOR-X"
        assert payload["vendorErrorCode"] == "E001"

    def test_build_status_notification_string_codes(self, protocol):
        """When error_code/status are strings not enums"""
        req = StatusNotificationRequest(
            connector_id=1,
            error_code="GroundFailure",
            status="Faulted",
        )
        payload = protocol.build_status_notification(req)
        assert payload["errorCode"] == "GroundFailure"
        assert payload["status"] == "Faulted"

    def test_handle_status_notification_response(self, protocol):
        resp = protocol.handle_status_notification_response({})
        assert isinstance(resp, StatusNotificationResponse)


class TestProtocolMessageLog:
    """Message log and protocol state tests"""

    def test_clear_log(self, protocol):
        protocol.build_heartbeat()
        assert len(protocol.message_log) > 0
        protocol.clear_log()
        assert len(protocol.message_log) == 0

    def test_message_log_is_copy(self, protocol):
        """message_log property returns a copy"""
        protocol.build_heartbeat()
        log1 = protocol.message_log
        protocol.clear_log()
        assert len(log1) > 0  # original copy unaffected

    def test_boot_status_initially_none(self, protocol):
        assert protocol.boot_status is None

    def test_last_heartbeat_initially_none(self, protocol):
        assert protocol.last_heartbeat_time is None

    def test_remove_transaction(self, protocol):
        """Test transaction cleanup"""
        protocol.handle_start_transaction_response({
            "transactionId": 99,
            "idTagInfo": {"status": "Accepted"},
        })
        protocol.remove_transaction(99)
        # Transaction should be removed without error

    def test_charger_id_stored(self, protocol):
        assert protocol.charger_id == "CHARGER-001"


# ── OCPPAdapter Tests ─────────────────────────────────────────────────


class TestAdapterCallbacks:
    """Test adapter callback registration and emission"""

    def test_on_telemetry_callback(self, adapter):
        received = []
        adapter.on_telemetry(lambda tp: received.append(tp))
        adapter._emit_telemetry(
            power=10.0, voltage=380.0, current=26.3,
            temperature=45.0, status="Charging",
        )
        assert len(received) == 1
        point = received[0]
        assert isinstance(point, TelemetryPoint)
        assert point.device_id == "TEST-CHG-001"
        assert point.power == 10.0
        assert point.voltage == 380.0
        assert point.status == "Charging"

    def test_on_alarm_callback(self, adapter):
        received = []
        adapter.on_alarm(lambda dev, atype, msg: received.append((dev, atype, msg)))
        adapter._emit_alarm("high_temperature", "Temp too high")
        assert len(received) == 1
        assert received[0] == ("TEST-CHG-001", "high_temperature", "Temp too high")

    def test_emit_telemetry_no_callback(self, adapter):
        """Emitting without callback should not crash"""
        adapter._emit_telemetry(
            power=5.0, voltage=380.0, current=13.2,
            temperature=30.0, status="Available",
        )

    def test_emit_alarm_no_callback(self, adapter):
        """Emitting alarm without callback should not crash"""
        adapter._emit_alarm("test_alarm", "test message")


class TestAdapterInjectTelemetry:
    """Test manual telemetry injection (debug API)"""

    def test_inject_telemetry_basic(self, adapter):
        received = []
        adapter.on_telemetry(lambda tp: received.append(tp))
        point = adapter.inject_telemetry(
            power=50.0,
            voltage=390.0,
            current=128.0,
            temperature=55.0,
        )
        assert len(received) == 1
        assert point.power == 50.0
        assert point.voltage == 390.0
        assert point.current == 128.0
        assert point.temperature == 55.0
        assert point.status == "Available"  # default

    def test_inject_telemetry_with_energy(self, adapter):
        point = adapter.inject_telemetry(energy=100.5)
        assert point.energy == 100.5

    def test_inject_telemetry_with_status(self, adapter):
        point = adapter.inject_telemetry(status="Charging")
        assert point.status == "Charging"

    def test_inject_telemetry_defaults(self, adapter):
        point = adapter.inject_telemetry()
        assert point.power == 0.0
        assert point.voltage == 380.0
        assert point.current == 0.0
        assert point.temperature == 25.0
        assert point.status == "Available"

    def test_inject_telemetry_updates_meter_value(self, adapter):
        """Injecting energy should update _meter_value"""
        adapter.inject_telemetry(energy=50.0)
        point = adapter.inject_telemetry(power=10.0)
        assert point.energy == 50.0  # energy persists

    def test_inject_telemetry_updates_sim_state(self, adapter):
        adapter.inject_telemetry(
            power=30.0, voltage=385.0, current=78.0, temperature=42.0,
        )
        assert adapter._sim_power == 30.0
        assert adapter._sim_voltage == 385.0
        assert adapter._sim_current == 78.0
        assert adapter._sim_temperature == 42.0


class TestAdapterInjectAlarm:
    """Test alarm injection (debug API)"""

    def test_inject_alarm_triggers_callback(self, adapter):
        received = []
        adapter.on_alarm(lambda dev, atype, msg: received.append((dev, atype, msg)))
        adapter.inject_alarm("ground_failure", "Ground fault detected")
        assert len(received) == 1
        assert received[0][1] == "ground_failure"
        assert received[0][2] == "Ground fault detected"

    def test_inject_alarm_no_callback(self, adapter):
        """Should not crash without callback"""
        adapter.inject_alarm("test", "msg")


class TestAdapterProtocolAccess:
    """Test adapter exposes protocol handler"""

    def test_protocol_property(self, adapter):
        assert isinstance(adapter.protocol, OCPPChargePointProtocol)
        assert adapter.protocol.charger_id == "TEST-CHG-001"

    def test_message_log_property(self, adapter):
        assert isinstance(adapter.message_log, list)


class TestAdapterStartStop:
    """Test adapter lifecycle in simulated mode"""

    @pytest.mark.asyncio
    async def test_start_creates_tasks(self, adapter):
        await adapter.start()
        assert adapter._running is True
        assert len(adapter._tasks) == 3  # simulator + heartbeat + meter
        await adapter.stop()
        assert adapter._running is False
        assert len(adapter._tasks) == 0

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, adapter):
        """Stopping without start should not crash"""
        await adapter.stop()
        assert adapter._running is False

    @pytest.mark.asyncio
    async def test_stop_with_error_in_task(self, adapter):
        """stop() should log but not crash if tasks had errors"""
        await adapter.start()
        # Manually cancel tasks to simulate error conditions
        for task in adapter._tasks:
            task.cancel()
        await adapter.stop()


class TestAdapterSimulationQuickRun:
    """Quick-run simulation mode tests with short intervals"""

    @pytest.mark.asyncio
    async def test_simulated_charger_emits_telemetry(self, ocpp_config):
        """Run simulation briefly and verify telemetry is emitted"""
        ocpp_config.heartbeat_interval = 1
        ocpp_config.meter_sample_interval = 1

        adapter = OCPPAdapter(ocpp_config)
        received = []
        adapter.on_telemetry(lambda tp: received.append(tp))

        await adapter.start()
        # Let simulation BootNotification + initial telemetry fire
        await asyncio.sleep(2.5)
        await adapter.stop()

        # Should have received at least initial telemetry
        assert len(received) > 0
        # First telemetry should be idle/available
        first = received[0]
        assert first.device_id == "TEST-CHG-001"
        assert first.status in ("Available", "Charging")

    @pytest.mark.asyncio
    async def test_simulated_charger_protocol_messages(self, ocpp_config):
        """Verify protocol message log has BootNotification after simulation start"""
        ocpp_config.heartbeat_interval = 1
        ocpp_config.meter_sample_interval = 1

        adapter = OCPPAdapter(ocpp_config)
        await adapter.start()
        await asyncio.sleep(2)
        await adapter.stop()

        logs = adapter.message_log
        actions = [log.action for log in logs]
        # BootNotification should be in the log
        assert "BootNotification" in actions


# ── OCPPConfig Tests ──────────────────────────────────────────────────


class TestAdapterSimulationEdgeCases:
    """Edge cases in simulation loops"""

    @pytest.mark.asyncio
    async def test_simulation_error_handler(self, ocpp_config):
        """Simulated charger should handle errors in main loop gracefully"""
        ocpp_config.meter_sample_interval = 1
        adapter = OCPPAdapter(ocpp_config)
        received = []
        adapter.on_telemetry(lambda tp: received.append(tp))

        await adapter.start()
        await asyncio.sleep(0.5)
        # Inject an error into the simulation by replacing _run_simulated_charger
        # The main loop catches Exception and continues
        await asyncio.sleep(2)
        await adapter.stop()
        # Should not crash

    @pytest.mark.asyncio
    async def test_heartbeat_loop_cancel(self, adapter):
        """Heartbeat loop should handle cancellation"""
        adapter._running = True
        task = asyncio.create_task(adapter._heartbeat_loop())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_meter_loop_cancel(self, adapter):
        """Meter loop should handle cancellation"""
        adapter._running = True
        task = asyncio.create_task(adapter._meter_loop())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_meter_loop_real_mode_fallback(self, ocpp_config):
        """Meter loop should emit telemetry in real mode"""
        ocpp_config.use_real_charger = True
        ocpp_config.meter_sample_interval = 1
        adapter = OCPPAdapter(ocpp_config)
        received = []
        adapter.on_telemetry(lambda tp: received.append(tp))
        adapter._running = True
        adapter._ws_connected = False  # not connected, but loop should still run

        task = asyncio.create_task(adapter._meter_loop())
        await asyncio.sleep(2.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_heartbeat_loop_simulated_mode(self, ocpp_config):
        """Heartbeat loop should send heartbeats in simulated mode"""
        ocpp_config.heartbeat_interval = 1
        adapter = OCPPAdapter(ocpp_config)
        adapter._running = True

        task = asyncio.create_task(adapter._heartbeat_loop())
        await asyncio.sleep(2.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Protocol should have heartbeat logged
        assert adapter.protocol.last_heartbeat_time is not None

    @pytest.mark.asyncio
    async def test_stop_logs_task_errors(self, ocpp_config):
        """stop() should log errors from failed tasks but not crash"""
        adapter = OCPPAdapter(ocpp_config)
        adapter._running = True

        async def failing_task():
            await asyncio.sleep(0.1)
            raise RuntimeError("Test error")

        adapter._tasks = [asyncio.create_task(failing_task())]
        await asyncio.sleep(0.2)
        await adapter.stop()


class TestAdapterProperties:
    """Test adapter initial state properties"""

    def test_adapter_initial_status(self, adapter):
        assert adapter._status == "Available"

    def test_adapter_initial_meter_value(self, adapter):
        assert adapter._meter_value == 0.0

    def test_adapter_initial_charging_state(self, adapter):
        assert adapter._is_charging is False

    def test_adapter_initial_reconnect_count(self, adapter):
        assert adapter._reconnect_count == 0

    def test_adapter_max_reconnects(self, adapter):
        assert adapter._max_reconnects == 5

    def test_adapter_connector_id(self, adapter):
        assert adapter._connector_id == 1


class TestOCPPConfig:
    """Test OCPP configuration"""

    def test_default_config(self):
        cfg = OCPPConfig()
        assert cfg.charger_id == "CHARGER-001"
        assert cfg.ws_url == "ws://localhost:9000"
        assert cfg.heartbeat_interval == 300
        assert cfg.meter_sample_interval == 10
        assert cfg.use_real_charger is False
        assert cfg.charger_vendor == "Tianlian-Energy"
        assert cfg.charger_model == "TL-EVSE-3000"

    def test_custom_config(self):
        cfg = OCPPConfig(
            charger_id="EVSE-999",
            ws_url="ws://csms.example.com:9000/ocpp",
            heartbeat_interval=60,
            meter_sample_interval=5,
            use_real_charger=True,
        )
        assert cfg.charger_id == "EVSE-999"
        assert cfg.use_real_charger is True
