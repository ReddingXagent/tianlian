"""Deep coverage for modbus_adapter: _poll_real_device, _connect_modbus,
stop() with client close, poll loop reconnection/fallback paths.

Targeting: L94-97, L174-241
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import ModbusConfig


@pytest.fixture
def modbus_cfg():
    cfg = ModbusConfig()
    cfg.use_real_modbus = True
    cfg.host = "127.0.0.1"
    cfg.port = 502
    cfg.unit_id = 1
    cfg.registers = [0, 1, 2, 3, 4, 5]
    cfg.poll_interval = 0.02
    cfg.retry_count = 2
    cfg.retry_delay = 0.01
    cfg.timeout = 2.0
    return cfg


@pytest.fixture
def adapter(modbus_cfg):
    from adapters.modbus_adapter import ModbusAdapter
    a = ModbusAdapter(modbus_cfg)
    yield a


def _make_read_result(registers, is_error=False):
    """Create a mock read_holding_registers result"""
    result = MagicMock()
    result.isError.return_value = is_error
    if is_error:
        result.__str__ = lambda self: "Modbus Error"
    else:
        result.registers = registers
    return result


# ── stop() with active client (L94-97) ──────────────────────────────

class TestStopWithClient:
    @pytest.mark.asyncio
    async def test_stop_closes_client(self, adapter):
        """stop() closes and nullifies the modbus client"""
        adapter._client = MagicMock()
        adapter._client.close = MagicMock()
        adapter._connected = True
        adapter._running = True

        # Start a polling task so _task is set
        async def fake_poll():
            while adapter._running:
                await asyncio.sleep(0.01)
        adapter._task = asyncio.create_task(fake_poll())

        await adapter.stop()
        assert adapter._client is None
        assert adapter._connected is False
        assert adapter._running is False

    @pytest.mark.asyncio
    async def test_stop_client_close_exception_swallowed(self, adapter):
        """stop() swallows exception from client.close()"""
        adapter._client = MagicMock()
        adapter._client.close = MagicMock(side_effect=RuntimeError("close error"))
        adapter._connected = True
        adapter._running = True

        async def fake_poll():
            while adapter._running:
                await asyncio.sleep(0.01)
        adapter._task = asyncio.create_task(fake_poll())

        # Should not raise
        await adapter.stop()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_stop_no_task_no_client(self, adapter):
        """stop() works with no running task or client"""
        adapter._task = None
        adapter._client = None
        await adapter.stop()  # should not raise


# ── _poll_real_device success (L174-241) ────────────────────────────

class TestPollRealDevice:
    @pytest.mark.asyncio
    async def test_poll_real_success(self, adapter):
        """_poll_real_device reads registers and emits telemetry"""
        telemetry_received = []
        adapter._on_telemetry = lambda p: telemetry_received.append(p)

        # Mock modbus client
        mock_client = MagicMock()
        # Registers: voltage=380, current=15, power=5, temp=35, energy=100, status=3(charging)
        mock_client.read_holding_registers = AsyncMock(
            return_value=_make_read_result([380, 15, 5, 35, 100, 3])
        )
        adapter._client = mock_client
        adapter._connected = True

        await adapter._poll_real_device()

        assert len(telemetry_received) == 1
        point = telemetry_received[0]
        assert point.device_id == "modbus-1"
        assert point.voltage == 380.0
        assert point.current == 15.0
        assert point.power == 5.0
        assert point.temperature == 35.0
        assert point.energy == 100.0
        assert point.status == "charging"

    @pytest.mark.asyncio
    async def test_poll_real_error_result(self, adapter):
        """_poll_real_device handles Modbus error result"""
        mock_client = MagicMock()
        mock_client.read_holding_registers = AsyncMock(
            return_value=_make_read_result([], is_error=True)
        )
        adapter._client = mock_client

        # Should return without raising
        await adapter._poll_real_device()

    @pytest.mark.asyncio
    async def test_poll_real_short_registers(self, adapter):
        """_poll_real_device handles insufficient register count"""
        mock_client = MagicMock()
        mock_client.read_holding_registers = AsyncMock(
            return_value=_make_read_result([380, 15])  # too few
        )
        adapter._client = mock_client

        await adapter._poll_real_device()  # should warn and return

    @pytest.mark.asyncio
    async def test_poll_real_empty_registers(self, adapter):
        """_poll_real_device handles empty register list"""
        mock_client = MagicMock()
        mock_client.read_holding_registers = AsyncMock(
            return_value=_make_read_result([])
        )
        adapter._client = mock_client

        await adapter._poll_real_device()

    @pytest.mark.asyncio
    async def test_poll_real_fault_status_triggers_alarm(self, adapter):
        """Fault status code (2) triggers alarm"""
        alarms = []
        adapter._on_telemetry = lambda p: None
        adapter._on_alarm = lambda dev, atype, msg: alarms.append((dev, atype, msg))

        mock_client = MagicMock()
        mock_client.read_holding_registers = AsyncMock(
            return_value=_make_read_result([380, 15, 5, 35, 100, 2])  # status=2=fault
        )
        adapter._client = mock_client

        await adapter._poll_real_device()

        assert len(alarms) == 1
        assert alarms[0][1] == "device_fault"

    @pytest.mark.asyncio
    async def test_poll_real_high_temp_triggers_alarm(self, adapter):
        """Temperature > 60°C triggers high_temperature alarm"""
        alarms = []
        adapter._on_telemetry = lambda p: None
        adapter._on_alarm = lambda dev, atype, msg: alarms.append((dev, atype, msg))

        mock_client = MagicMock()
        mock_client.read_holding_registers = AsyncMock(
            return_value=_make_read_result([380, 15, 5, 65, 100, 0])  # temp=65, status=0=normal
        )
        adapter._client = mock_client

        await adapter._poll_real_device()

        assert len(alarms) == 1
        assert alarms[0][1] == "high_temperature"

    @pytest.mark.asyncio
    async def test_poll_real_unknown_status(self, adapter):
        """Unknown status code maps to 'unknown'"""
        telemetry = []
        adapter._on_telemetry = lambda p: telemetry.append(p)

        mock_client = MagicMock()
        mock_client.read_holding_registers = AsyncMock(
            return_value=_make_read_result([380, 15, 5, 35, 100, 99])  # unknown status
        )
        adapter._client = mock_client

        await adapter._poll_real_device()

        assert telemetry[0].status == "unknown"

    @pytest.mark.asyncio
    async def test_poll_real_exception_reraised(self, adapter):
        """_poll_real_device re-raises exceptions (for poll loop to handle)"""
        mock_client = MagicMock()
        mock_client.read_holding_registers = AsyncMock(side_effect=ConnectionError("device gone"))
        adapter._client = mock_client

        with pytest.raises(ConnectionError):
            await adapter._poll_real_device()

    @pytest.mark.asyncio
    async def test_poll_real_no_telemetry_callback(self, adapter):
        """Works without telemetry callback set"""
        adapter._on_telemetry = None

        mock_client = MagicMock()
        mock_client.read_holding_registers = AsyncMock(
            return_value=_make_read_result([380, 15, 5, 35, 100, 0])
        )
        adapter._client = mock_client

        await adapter._poll_real_device()  # should not raise


# ── _connect_modbus paths ───────────────────────────────────────────

class TestConnectModbus:
    @pytest.mark.asyncio
    async def test_connect_success(self, adapter):
        """_connect_modbus returns True on successful connection"""
        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_cls.return_value = mock_client

            result = await adapter._connect_modbus()
            assert result is True
            assert adapter._connected is True

    @pytest.mark.asyncio
    async def test_connect_refused_retries(self, adapter):
        """_connect_modbus retries on connection refused"""
        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter._connect_modbus()
            assert result is False
            assert adapter._connected is False

    @pytest.mark.asyncio
    async def test_connect_exception_retries(self, adapter):
        """_connect_modbus handles exceptions and retries"""
        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(side_effect=OSError("network down"))
            mock_cls.return_value = mock_client

            result = await adapter._connect_modbus()
            assert result is False

    @pytest.mark.asyncio
    async def test_connect_import_error(self, adapter):
        """_connect_modbus returns False on ImportError (pymodbus not installed)"""
        with patch.dict("sys.modules", {"pymodbus.client": None}):
            # Force ImportError when AsyncModbusTcpClient is imported
            import builtins
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name.startswith("pymodbus"):
                    raise ImportError("No module named pymodbus")
                return original_import(name, *args, **kwargs)

            builtins.__import__ = mock_import
            try:
                result = await adapter._connect_modbus()
                assert result is False
            finally:
                builtins.__import__ = original_import


# ── Poll loop: real mode fallback to simulation (L160-168) ──────────

class TestPollLoopFallback:
    @pytest.mark.asyncio
    async def test_poll_loop_real_fails_falls_to_sim(self, adapter):
        """Poll loop falls back to simulation when real mode connection fails"""
        adapter.config.use_real_modbus = True
        adapter.config.poll_interval = 0.01

        # Mock _connect_modbus to fail
        async def fail_connect():
            return False
        adapter._connect_modbus = fail_connect

        telemetry = []
        adapter._on_telemetry = lambda p: telemetry.append(p)

        async def stop_soon():
            await asyncio.sleep(0.15)
            adapter._running = False

        # Start adapter (which starts poll loop)
        _stop_task = asyncio.create_task(stop_soon())  # noqa: RUF006
        await adapter.start()

        # Wait for simulation to produce telemetry
        await asyncio.sleep(0.2)
        adapter._running = False

        # Should have switched to simulation mode
        assert adapter.config.use_real_modbus is False
        assert len(telemetry) > 0

    @pytest.mark.asyncio
    async def test_poll_loop_reconnect_after_failure(self, adapter):
        """Poll loop attempts reconnection after real device poll failure"""
        adapter.config.use_real_modbus = True
        adapter._connected = True
        adapter.config.poll_interval = 0.01
        adapter.config.retry_count = 1
        adapter.config.retry_delay = 0.01

        # First poll fails, reconnect succeeds, then stop
        poll_count = 0

        async def failing_real_poll():
            nonlocal poll_count
            poll_count += 1
            raise ConnectionError("device disconnected")

        adapter._poll_real_device = failing_real_poll

        reconnect_called = False

        async def mock_connect():
            nonlocal reconnect_called
            reconnect_called = True
            adapter._connected = True
            return True

        adapter._connect_modbus = mock_connect

        # Make poll loop iterate a few times then stop
        async def stop_soon():
            await asyncio.sleep(0.1)
            adapter._running = False

        adapter._running = True
        _stop_task = asyncio.create_task(stop_soon())  # noqa: RUF006
        await adapter._poll_loop()

        assert reconnect_called


# ── _emit_alarm direct ──────────────────────────────────────────────

class TestEmitAlarm:
    @pytest.mark.asyncio
    async def test_emit_alarm_with_callback(self, adapter):
        """_emit_alarm calls on_alarm when callback is set"""
        alarms = []
        adapter._on_alarm = lambda dev, atype, msg: alarms.append((dev, atype, msg))

        adapter._emit_alarm("test_fault", "test message")
        assert len(alarms) == 1
        assert alarms[0][0] == "modbus-1"
        assert alarms[0][1] == "test_fault"
        assert alarms[0][2] == "test message"

    def test_emit_alarm_no_callback(self, adapter):
        """_emit_alarm does nothing without callback"""
        adapter._on_alarm = None
        adapter._emit_alarm("test", "msg")  # should not raise


# ── Simulated device with realistic values ──────────────────────────

class TestSimulatedDevice:
    @pytest.mark.asyncio
    async def test_sim_poll_emits_telemetry(self, adapter):
        """Simulated poll produces valid telemetry point"""
        adapter.config.use_real_modbus = False
        telemetry = []
        adapter._on_telemetry = lambda p: telemetry.append(p)

        await adapter._poll_simulated_device()

        assert len(telemetry) == 1
        point = telemetry[0]
        assert 350.0 <= point.voltage <= 410.0
        assert 0.0 <= point.current <= 25.0
        assert point.energy >= 0
        assert point.status in ("normal", "warning", "fault", "charging", "idle", "offline")

    @pytest.mark.asyncio
    async def test_sim_poll_energy_accumulates(self, adapter):
        """Simulated energy accumulates across polls"""
        adapter.config.use_real_modbus = False
        adapter._sim_energy = 50.0

        telemetry = []
        adapter._on_telemetry = lambda p: telemetry.append(p)

        await adapter._poll_simulated_device()
        # Energy should be >= 50 (accumulated)
        assert telemetry[0].energy >= 50.0
