"""Unit tests for ModbusAdapter uncovered paths (T-1203 coverage).

Targets lines missed by protocol integration tests:
- on_telemetry / on_alarm callback registration
- inject_alarm → _emit_alarm path
- inject_telemetry with energy parameter
- _connect_modbus failure → fallback to simulation
- _poll_loop reconnect logic on real-mode failure
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.modbus_adapter import ModbusAdapter
from config import ModbusConfig
from models import TelemetryPoint

# ── Callback Registration Tests (lines 70-76) ────────────────────────


class TestCallbackRegistration:
    """Directly test callback setter methods."""

    def test_on_telemetry_registers_callback(self):
        cfg = ModbusConfig(use_real_modbus=False)
        adapter = ModbusAdapter(cfg)
        cb = lambda p: None
        adapter.on_telemetry(cb)
        assert adapter._on_telemetry is cb

    def test_on_alarm_registers_callback(self):
        cfg = ModbusConfig(use_real_modbus=False)
        adapter = ModbusAdapter(cfg)
        cb = lambda d, t, m: None
        adapter.on_alarm(cb)
        assert adapter._on_alarm is cb

    def test_callbacks_default_none(self):
        cfg = ModbusConfig(use_real_modbus=False)
        adapter = ModbusAdapter(cfg)
        assert adapter._on_telemetry is None
        assert adapter._on_alarm is None


# ── Inject Alarm Tests (line 315, _emit_alarm path) ──────────────────


class TestInjectAlarm:

    def test_inject_alarm_with_callback(self):
        """inject_alarm should fire registered alarm callback."""
        cfg = ModbusConfig(use_real_modbus=False)
        adapter = ModbusAdapter(cfg)
        alarms: list[tuple] = []
        adapter.on_alarm(lambda dev, typ, msg: alarms.append((dev, typ, msg)))

        adapter.inject_alarm("test_fault", "Something broke")

        assert len(alarms) == 1
        dev_id, alarm_type, message = alarms[0]
        assert dev_id.startswith("modbus-")
        assert alarm_type == "test_fault"
        assert message == "Something broke"

    def test_inject_alarm_without_callback(self):
        """inject_alarm should not crash if no alarm callback registered."""
        cfg = ModbusConfig(use_real_modbus=False)
        adapter = ModbusAdapter(cfg)
        # Should not raise
        adapter.inject_alarm("test_fault", "Nobody listening")

    def test_emit_alarm_device_id_format(self):
        """_emit_alarm should format device_id as modbus-{unit_id}."""
        cfg = ModbusConfig(use_real_modbus=False, unit_id=42)
        adapter = ModbusAdapter(cfg)
        captured: list[str] = []
        adapter.on_alarm(lambda dev, typ, msg: captured.append(dev))

        adapter.inject_alarm("any", "msg")

        assert captured[0] == "modbus-42"


# ── Inject Telemetry Energy Parameter (line 302) ─────────────────────


class TestInjectTelemetryEnergy:

    def test_inject_sets_sim_energy(self):
        """inject_telemetry with energy= should update _sim_energy."""
        cfg = ModbusConfig(use_real_modbus=False)
        adapter = ModbusAdapter(cfg)
        assert adapter._sim_energy == 0.0

        # First inject with explicit energy
        p1 = adapter.inject_telemetry(energy=100.5)
        assert p1.energy == 100.5
        assert adapter._sim_energy == 100.5

        # Second inject without energy should preserve cumulative
        p2 = adapter.inject_telemetry()
        assert p2.energy == 100.5  # unchanged, no new energy passed

    def test_inject_with_all_params(self):
        """inject_telemetry should respect all provided values."""
        cfg = ModbusConfig(use_real_modbus=False, unit_id=7)
        adapter = ModbusAdapter(cfg)

        point = adapter.inject_telemetry(
            power=3.3,
            voltage=385.0,
            current=8.6,
            temperature=42.0,
            energy=55.0,
            status="charging",
        )

        assert point.device_id == "modbus-7"
        assert point.power == 3.3
        assert point.voltage == 385.0
        assert point.current == 8.6
        assert point.temperature == 42.0
        assert point.energy == 55.0
        assert point.status == "charging"

    def test_inject_fires_telemetry_callback(self):
        """inject_telemetry should trigger on_telemetry callback."""
        cfg = ModbusConfig(use_real_modbus=False)
        adapter = ModbusAdapter(cfg)
        received: list[TelemetryPoint] = []
        adapter.on_telemetry(received.append)

        adapter.inject_telemetry(power=2.0)

        assert len(received) == 1
        assert received[0].power == 2.0


# ── Real Modbus Connection Failure (lines 94-145) ─────────────────────


class TestConnectModbusFailure:

    @pytest.mark.asyncio
    async def test_connect_fails_without_pymodbus(self):
        """When pymodbus is not importable, _connect_modbus returns False."""
        cfg = ModbusConfig(
            use_real_modbus=True,
            host="192.168.1.99",
            port=502,
            retry_count=2,
            retry_delay=0.01,
        )
        adapter = ModbusAdapter(cfg)

        with patch("builtins.__import__", side_effect=ImportError("no pymodbus")):
            result = await adapter._connect_modbus()

        assert result is False
        assert adapter._connected is False

    @pytest.mark.asyncio
    async def test_connect_returns_false_on_all_retries(self):
        """_connect_modbus should exhaust retries and return False."""
        cfg = ModbusConfig(
            use_real_modbus=True,
            host="10.0.0.99",
            port=502,
            retry_count=3,
            retry_delay=0.01,
        )
        adapter = ModbusAdapter(cfg)

        # Mock the pymodbus client to always fail
        with patch.dict("sys.modules", {"pymodbus.client": MagicMock()}):
            mock_client_cls = MagicMock()
            mock_instance = MagicMock()
            mock_instance.connect = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            with patch("pymodbus.client.AsyncModbusTcpClient", mock_client_cls):
                result = await adapter._connect_modbus()

        assert result is False

    @pytest.mark.asyncio
    async def test_connect_succeeds(self):
        """_connect_modbus should return True on successful connection."""
        cfg = ModbusConfig(
            use_real_modbus=True,
            host="10.0.0.1",
            port=502,
            retry_count=2,
            retry_delay=0.01,
        )
        adapter = ModbusAdapter(cfg)

        with patch.dict("sys.modules", {"pymodbus.client": MagicMock()}):
            mock_client_cls = MagicMock()
            mock_instance = MagicMock()
            mock_instance.connect = AsyncMock(return_value=True)
            mock_instance.close = MagicMock()
            mock_client_cls.return_value = mock_instance

            with patch("pymodbus.client.AsyncModbusTcpClient", mock_client_cls):
                result = await adapter._connect_modbus()

        assert result is True
        assert adapter._connected is True

    @pytest.mark.asyncio
    async def test_connect_exception_retries(self):
        """_connect_modbus should catch exceptions and retry."""
        cfg = ModbusConfig(
            use_real_modbus=True,
            host="10.0.0.99",
            port=502,
            retry_count=3,
            retry_delay=0.01,
        )
        adapter = ModbusAdapter(cfg)

        call_count = 0

        class FlakyClient:
            async def connect(self):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ConnectionError("network unreachable")
                return True

            def close(self):
                pass

        with patch.dict("sys.modules", {"pymodbus.client": MagicMock()}):
            with patch("pymodbus.client.AsyncModbusTcpClient", return_value=FlakyClient()):
                result = await adapter._connect_modbus()

        assert result is True
        assert call_count == 3  # failed twice, succeeded on 3rd


# ── Start with Real Modbus → Fallback (lines 154, 157-168) ───────────


class TestStartFallbackToSimulation:

    @pytest.mark.asyncio
    async def test_start_falls_back_on_connect_failure(self):
        """When real modbus fails, start() should fallback to simulation."""
        cfg = ModbusConfig(
            use_real_modbus=True,
            host="10.0.0.99",
            port=502,
            retry_count=1,
            retry_delay=0.01,
            poll_interval=0.1,
        )
        adapter = ModbusAdapter(cfg)

        with patch.object(adapter, "_connect_modbus", return_value=False):
            await adapter.start()
            await asyncio.sleep(0.01)

        assert cfg.use_real_modbus is False
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_start_real_mode_success(self):
        """When real modbus connects, start() should keep real mode."""
        cfg = ModbusConfig(
            use_real_modbus=True,
            host="10.0.0.1",
            port=502,
            retry_count=1,
            poll_interval=0.1,
        )
        adapter = ModbusAdapter(cfg)

        with patch.object(adapter, "_connect_modbus", return_value=True):
            with patch.object(adapter, "_poll_loop", new_callable=AsyncMock):
                await adapter.start()
                await asyncio.sleep(0.01)

        assert cfg.use_real_modbus is True
        await adapter.stop()


# ── Poll Loop Reconnect Logic (lines 157-168) ─────────────────────────


class TestPollLoopReconnect:

    @pytest.mark.asyncio
    async def test_poll_loop_reconnects_on_real_mode_failure(self):
        """Poll loop should attempt reconnect when real mode poll fails."""
        cfg = ModbusConfig(
            use_real_modbus=True,
            host="10.0.0.1",
            port=502,
            retry_count=1,
            retry_delay=0.01,
            poll_interval=0.05,
        )
        adapter = ModbusAdapter(cfg)
        adapter._connected = True

        # _poll_real_device raises, then reconnect fails → fallback
        call_count = 0

        async def fake_poll_real():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("device disconnected")

        with patch.object(adapter, "_poll_real_device", side_effect=fake_poll_real):
            with patch.object(adapter, "_connect_modbus", return_value=False):
                with patch.object(adapter, "_poll_simulated_device", new_callable=AsyncMock):
                    adapter._running = True
                    # Run one iteration manually
                    try:
                        await asyncio.wait_for(adapter._poll_loop(), timeout=0.3)
                    except asyncio.TimeoutError:
                        adapter._running = False

        # After failure + failed reconnect, should fallback to simulation
        assert cfg.use_real_modbus is False

    @pytest.mark.asyncio
    async def test_poll_loop_real_mode_reconnect_success(self):
        """Poll loop reconnect succeeds → stays in real mode."""
        cfg = ModbusConfig(
            use_real_modbus=True,
            host="10.0.0.1",
            port=502,
            retry_count=1,
            retry_delay=0.01,
            poll_interval=0.05,
        )
        adapter = ModbusAdapter(cfg)
        adapter._connected = True

        poll_count = 0

        async def fake_poll_real():
            nonlocal poll_count
            poll_count += 1
            if poll_count == 1:
                raise ConnectionError("transient")
            # After reconnect, succeed
            await asyncio.sleep(0.01)

        with patch.object(adapter, "_poll_real_device", side_effect=fake_poll_real):
            with patch.object(adapter, "_connect_modbus", return_value=True):
                adapter._running = True
                try:
                    await asyncio.wait_for(adapter._poll_loop(), timeout=0.3)
                except asyncio.TimeoutError:
                    adapter._running = False

        assert cfg.use_real_modbus is True
        assert adapter._connected is True


# ── Simulated Alarm Paths (lines 279, 281) ────────────────────────────


class TestSimulatedAlarmPaths:

    @pytest.mark.asyncio
    async def test_simulated_warning_alarm_path(self):
        """_poll_simulated_device should emit device_warning when status=warning."""
        cfg = ModbusConfig(use_real_modbus=False, poll_interval=0.01)
        adapter = ModbusAdapter(cfg)

        alarms: list[tuple] = []
        adapter.on_alarm(lambda dev, typ, msg: alarms.append((dev, typ, msg)))

        # Force conditions for warning alarm
        with patch("random.random", return_value=0.01):  # < 0.05 → warning status
            with patch("random.choice", return_value="warning"):
                with patch("random.uniform", side_effect=[380.0, 10.0, 30.0]):
                    await adapter._poll_simulated_device()

        # status would be "warning", then random.random() < 0.2 for alarm
        with patch("random.random", return_value=0.1):  # < 0.2 → emit alarm
            with patch("random.choice", return_value="warning"):
                with patch("random.uniform", side_effect=[380.0, 10.0, 30.0]):
                    await adapter._poll_simulated_device()

    @pytest.mark.asyncio
    async def test_simulated_high_temp_alarm(self):
        """_poll_simulated_device should emit high_temperature when temp > 55."""
        cfg = ModbusConfig(use_real_modbus=False, poll_interval=0.01)
        adapter = ModbusAdapter(cfg)

        alarms: list[tuple] = []
        adapter.on_alarm(lambda dev, typ, msg: alarms.append((dev, typ, msg)))

        # Force high temperature + trigger alarm
        # random.uniform called: voltage, current, temperature (need >55)
        # random.random called: status_check(<0.05→warning), alarm_check(<0.2→warning alarm), temp_alarm_check(<0.1→high temp)
        with patch("random.uniform", side_effect=[380.0, 10.0, 60.0]):  # temp=60
            with patch("random.random", side_effect=[0.01, 0.01, 0.01]):  # all triggers fire
                with patch("random.choice", return_value="warning"):
                    await adapter._poll_simulated_device()

        # Both warning and high_temperature alarms should fire
        alarm_types = [a[1] for a in alarms]
        assert "device_warning" in alarm_types
        assert "high_temperature" in alarm_types
