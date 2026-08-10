"""Tests for enhanced MQTT client (T-1101: batch publish, LWT, auto-reconnect)"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.mqtt_client import MQTTClient
from config import MQTTConfig
from models import TelemetryPoint


@pytest.fixture
def mqtt_config():
    return MQTTConfig(
        host="localhost",
        port=1883,
        client_id="test-gw-001",
        topic_prefix="tianlian/test",
        batch_size=10,
        batch_interval=5,
    )


@pytest.fixture
def mqtt_client(mqtt_config):
    return MQTTClient(mqtt_config)


@pytest.fixture
def sample_points():
    return [
        TelemetryPoint(device_id="EVSE-001", power=22.5, voltage=400.0, current=56.0),
        TelemetryPoint(device_id="EVSE-001", power=23.0, voltage=400.1, current=56.2),
        TelemetryPoint(device_id="EVSE-002", power=11.0, voltage=398.0, current=27.5),
        TelemetryPoint(device_id="EVSE-003", power=0.0, voltage=0.0, current=0.0, status="idle"),
    ]


class TestMQTTClientInit:
    """Test MQTT client initialization"""

    def test_mqtt_client_creation(self, mqtt_client):
        assert mqtt_client._connected is False
        assert mqtt_client._client is None
        assert mqtt_client._should_reconnect is False

    def test_mqtt_client_callbacks_lists(self, mqtt_client):
        assert mqtt_client._on_reconnect_callbacks == []
        assert mqtt_client._on_disconnect_callbacks == []

    def test_connected_property(self, mqtt_client):
        assert mqtt_client.connected is False
        mqtt_client._connected = True
        assert mqtt_client.connected is True


class TestLWT:
    """Test Last Will and Testament construction"""

    def test_lwt_topic(self, mqtt_client, mqtt_config):
        topic, payload, qos, retain = mqtt_client._build_lwt()
        assert topic == f"{mqtt_config.topic_prefix}/status/offline"
        assert qos == mqtt_config.qos
        assert retain is True

    def test_lwt_payload_content(self, mqtt_client, mqtt_config):
        _, payload_str, _, _ = mqtt_client._build_lwt()
        payload = json.loads(payload_str)
        assert payload["status"] == "offline"
        assert payload["reason"] == "unexpected_disconnect"
        assert "timestamp" in payload

    def test_lwt_uses_client_id(self, mqtt_client, mqtt_config):
        _, payload_str, _, _ = mqtt_client._build_lwt()
        payload = json.loads(payload_str)
        assert payload["gateway_id"] == mqtt_config.client_id


class TestReconnectCallbacks:
    """Test reconnect/disconnect callback registration and firing"""

    def test_register_reconnect_callback(self, mqtt_client):
        cb = MagicMock()
        mqtt_client.on_reconnect(cb)
        assert cb in mqtt_client._on_reconnect_callbacks

    def test_register_disconnect_callback(self, mqtt_client):
        cb = MagicMock()
        mqtt_client.on_disconnect(cb)
        assert cb in mqtt_client._on_disconnect_callbacks

    def test_reconnect_callback_fired_on_connect(self, mqtt_client):
        cb = MagicMock()
        mqtt_client.on_reconnect(cb)
        # Simulate connect success
        mqtt_client._on_connect(None, None, None, 0)
        cb.assert_called_once()

    def test_disconnect_callback_fired_on_disconnect(self, mqtt_client):
        cb = MagicMock()
        mqtt_client.on_disconnect(cb)
        # Simulate unexpected disconnect
        mqtt_client._on_disconnect(None, None, 1)
        cb.assert_called_once()

    def test_reconnect_resets_attempt_counter(self, mqtt_client):
        mqtt_client._reconnect_attempts = 5
        mqtt_client._on_connect(None, None, None, 0)
        assert mqtt_client._reconnect_attempts == 0


class TestSinglePublish:
    """Test single telemetry publishing"""

    @pytest.mark.asyncio
    async def test_publish_when_not_connected(self, mqtt_client, sample_points):
        result = await mqtt_client.publish_telemetry(sample_points[0])
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_when_connected(self, mqtt_client, sample_points, mqtt_config):
        mqtt_client._connected = True
        mqtt_client._client = MagicMock()
        mock_info = MagicMock()
        mock_info.rc = 0  # MQTT_ERR_SUCCESS
        mqtt_client._client.publish = MagicMock(return_value=mock_info)

        import paho.mqtt.client as mqtt_lib
        with patch.object(mqtt_lib, 'MQTT_ERR_SUCCESS', 0):
            result = await mqtt_client.publish_telemetry(sample_points[0])

        assert result is True
        # Check publish was called with correct topic
        call_args = mqtt_client._client.publish.call_args
        expected_topic = f"{mqtt_config.topic_prefix}/telemetry/EVSE-001"
        assert call_args[0][0] == expected_topic


class TestBatchPublish:
    """Test batch telemetry publishing (T-1101 core feature)"""

    @pytest.mark.asyncio
    async def test_batch_publish_not_connected(self, mqtt_client, sample_points):
        result = await mqtt_client.publish_telemetry_batch(sample_points)
        assert result["success_count"] == 0
        assert result["failure_count"] == 4
        assert result["total"] == 4

    @pytest.mark.asyncio
    async def test_batch_publish_connected(self, mqtt_client, sample_points, mqtt_config):
        mqtt_client._connected = True
        mqtt_client._client = MagicMock()
        mock_info = MagicMock()
        mock_info.rc = 0
        mqtt_client._client.publish = MagicMock(return_value=mock_info)

        import paho.mqtt.client as mqtt_lib
        with patch.object(mqtt_lib, 'MQTT_ERR_SUCCESS', 0):
            result = await mqtt_client.publish_telemetry_batch(sample_points)

        assert result["success_count"] == 4
        assert result["failure_count"] == 0
        assert result["total"] == 4

    @pytest.mark.asyncio
    async def test_batch_publish_groups_by_device(self, mqtt_client, sample_points, mqtt_config):
        mqtt_client._connected = True
        mqtt_client._client = MagicMock()
        mock_info = MagicMock()
        mock_info.rc = 0
        mqtt_client._client.publish = MagicMock(return_value=mock_info)

        import paho.mqtt.client as mqtt_lib
        with patch.object(mqtt_lib, 'MQTT_ERR_SUCCESS', 0):
            await mqtt_client.publish_telemetry_batch(sample_points)

        # Should have 3 calls (EVSE-001, EVSE-002, EVSE-003)
        assert mqtt_client._client.publish.call_count == 3

    @pytest.mark.asyncio
    async def test_batch_publish_empty_list(self, mqtt_client):
        result = await mqtt_client.publish_telemetry_batch([])
        assert result == {"success_count": 0, "failure_count": 0, "total": 0}

    @pytest.mark.asyncio
    async def test_batch_publish_partial_failure(self, mqtt_client, sample_points):
        mqtt_client._connected = True
        mqtt_client._client = MagicMock()

        # Alternate success/failure
        mock_success = MagicMock()
        mock_success.rc = 0
        mock_fail = MagicMock()
        mock_fail.rc = 1
        mqtt_client._client.publish = MagicMock(
            side_effect=[mock_success, mock_success, mock_fail]
        )

        import paho.mqtt.client as mqtt_lib
        with patch.object(mqtt_lib, 'MQTT_ERR_SUCCESS', 0):
            result = await mqtt_client.publish_telemetry_batch(sample_points)

        assert result["failure_count"] > 0


class TestPublishStatus:
    """Test status message publishing"""

    @pytest.mark.asyncio
    async def test_publish_status_not_connected(self, mqtt_client):
        result = await mqtt_client.publish_status("online")
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_status_connected(self, mqtt_client, mqtt_config):
        mqtt_client._connected = True
        mqtt_client._client = MagicMock()
        mock_info = MagicMock()
        mock_info.rc = 0
        mqtt_client._client.publish = MagicMock(return_value=mock_info)

        import paho.mqtt.client as mqtt_lib
        with patch.object(mqtt_lib, 'MQTT_ERR_SUCCESS', 0):
            result = await mqtt_client.publish_status("online", {"uptime": 3600})

        assert result is True
        call_args = mqtt_client._client.publish.call_args
        assert call_args[1]["retain"] is True

    @pytest.mark.asyncio
    async def test_publish_alarm(self, mqtt_client):
        mqtt_client._connected = True
        mqtt_client._client = MagicMock()
        mock_info = MagicMock()
        mock_info.rc = 0
        mqtt_client._client.publish = MagicMock(return_value=mock_info)

        import paho.mqtt.client as mqtt_lib
        with patch.object(mqtt_lib, 'MQTT_ERR_SUCCESS', 0):
            result = await mqtt_client.publish_alarm("EVSE-001", {"type": "overtemp"})

        assert result is True


class TestMQTTConnect:
    """Test MQTT connect flow"""

    @pytest.mark.asyncio
    async def test_connect_sets_client_id(self, mqtt_client, mqtt_config):
        with patch("adapters.mqtt_client.mqtt.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            with patch("adapters.mqtt_client.asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_in_executor = AsyncMock(return_value=None)
                mock_loop.return_value = loop

                await mqtt_client.connect()

            # Verify client was created with correct client_id
            mock_client_cls.assert_called_once()
            call_kwargs = mock_client_cls.call_args
            assert "test-gw-001" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_connect_sets_will(self, mqtt_client):
        with patch("adapters.mqtt_client.mqtt.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            with patch("adapters.mqtt_client.asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_in_executor = AsyncMock(return_value=None)
                mock_loop.return_value = loop

                await mqtt_client.connect()

            # Verify will_set was called
            mock_client.will_set.assert_called_once()
            will_args = mock_client.will_set.call_args[0]
            assert "status/offline" in will_args[0]


# ── Coverage: _do_connect internal execution ────────────────────────────


class TestMQTTConnectInternal:
    """Cover lines 103-104: actual _do_connect callback execution."""

    @pytest.mark.asyncio
    async def test_do_connect_executes_inner_connect(self, mqtt_client):
        """When run_in_executor calls the function, _client.connect + loop_start execute."""
        with patch("adapters.mqtt_client.mqtt.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            async def run_in_executor_real(pool, fn):
                fn()  # Actually execute the nested function
                return None

            with patch("adapters.mqtt_client.asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_in_executor = run_in_executor_real
                mock_loop.return_value = loop

                await mqtt_client.connect()

            # Verify _do_connect's internals ran
            mock_client.connect.assert_called_once_with(
                mqtt_client.config.host, mqtt_client.config.port, mqtt_client.config.keepalive
            )
            mock_client.loop_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_alarm_not_connected_returns_false(self, mqtt_client):
        """Line 212: publish_alarm returns False when not connected."""
        mqtt_client._connected = False
        mqtt_client._client = None
        result = await mqtt_client.publish_alarm("EVSE-001", {"type": "overtemp"})
        assert result is False
