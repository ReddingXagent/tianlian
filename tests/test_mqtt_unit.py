"""Unit tests for MQTTClient uncovered paths.

Targets:
- _on_connect failure path (rc != 0)
- _on_disconnect clean (rc == 0) + callback error handling
- connect() with credentials
- disconnect() full flow
- _do_publish exception path
- publish_raw
- callback error resilience
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.mqtt_client import MQTTClient
from config import MQTTConfig


@pytest.fixture
def cfg():
    return MQTTConfig(
        host="localhost",
        port=1883,
        client_id="test-gw-001",
        topic_prefix="tianlian/test",
        username=None,
        password=None,
    )


@pytest.fixture
def client(cfg):
    return MQTTClient(cfg)


@pytest.fixture
def connected_client(client):
    """MQTTClient with mocked internal client in connected state."""
    client._connected = True
    client._client = MagicMock()
    mock_info = MagicMock()
    mock_info.rc = 0  # MQTT_ERR_SUCCESS
    client._client.publish.return_value = mock_info
    return client


# ── _on_connect failure path (line 52-55) ────────────────────────────


class TestOnConnectFailure:

    def test_on_connect_failure_sets_no_connection(self, client):
        """_on_connect with rc != 0 should not set _connected."""
        client._on_connect(None, None, None, rc=1)
        assert client._connected is False

    def test_on_connect_failure_logs_error(self, client, caplog):
        """_on_connect with rc != 0 should log error."""
        import logging
        with caplog.at_level(logging.ERROR):
            client._on_connect(None, None, None, rc=2)
        assert any("rc=2" in r.message for r in caplog.records)

    def test_on_connect_resets_attempts_on_success(self, client):
        """_on_connect with rc=0 should reset reconnect_attempts."""
        client._reconnect_attempts = 7
        client._on_connect(None, None, None, rc=0)
        assert client._reconnect_attempts == 0
        assert client._connected is True


# ── _on_disconnect paths (lines 62, 67-68) ────────────────────────────


class TestOnDisconnect:

    def test_clean_disconnect(self, client):
        """_on_disconnect with rc=0 should log clean disconnect."""
        client._connected = True
        client._on_disconnect(None, None, 0)
        assert client._connected is False

    def test_unexpected_disconnect(self, client):
        """_on_disconnect with rc!=0 should log warning."""
        client._connected = True
        client._on_disconnect(None, None, 1)
        assert client._connected is False

    def test_disconnect_callback_error_is_swallowed(self, client):
        """Errors in disconnect callbacks should not propagate."""
        client.on_disconnect(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        # Should not raise
        client._on_disconnect(None, None, 0)

    def test_reconnect_callback_error_is_swallowed(self, client):
        """Errors in reconnect callbacks should not propagate."""
        client.on_reconnect(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        # Should not raise
        client._on_connect(None, None, None, 0)
        assert client._connected is True


# ── connect() with credentials (lines 91, 103-104) ───────────────────


class TestConnectWithCredentials:

    @pytest.mark.asyncio
    async def test_connect_with_username_password(self):
        cfg = MQTTConfig(
            host="broker.example.com",
            port=8883,
            client_id="auth-gw",
            topic_prefix="tianlian/auth",
            username="user",
            password="secret",
        )
        c = MQTTClient(cfg)

        with patch("adapters.mqtt_client.mqtt.Client") as mock_cls:
            mock_inner = MagicMock()
            mock_cls.return_value = mock_inner
            with patch("adapters.mqtt_client.asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_in_executor = AsyncMock()
                mock_loop.return_value = loop
                await c.connect()

            mock_inner.username_pw_set.assert_called_once_with("user", "secret")
            mock_inner.reconnect_delay_set.assert_called_once_with(min_delay=1, max_delay=30)

    @pytest.mark.asyncio
    async def test_connect_no_credentials(self, client):
        """connect() without username should skip username_pw_set."""
        with patch("adapters.mqtt_client.mqtt.Client") as mock_cls:
            mock_inner = MagicMock()
            mock_cls.return_value = mock_inner
            with patch("adapters.mqtt_client.asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_in_executor = AsyncMock()
                mock_loop.return_value = loop
                await client.connect()

            mock_inner.username_pw_set.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_sets_should_reconnect(self, client):
        with patch("adapters.mqtt_client.mqtt.Client") as mock_cls:
            mock_inner = MagicMock()
            mock_cls.return_value = mock_inner
            with patch("adapters.mqtt_client.asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_in_executor = AsyncMock()
                mock_loop.return_value = loop
                await client.connect()

            assert client._should_reconnect is True

    @pytest.mark.asyncio
    async def test_connect_default_client_id(self):
        """When client_id not set, should use fallback pattern."""
        cfg = MQTTConfig(host="broker", port=1883, client_id="", topic_prefix="t")
        c = MQTTClient(cfg)

        with patch("adapters.mqtt_client.mqtt.Client") as mock_cls:
            mock_inner = MagicMock()
            mock_cls.return_value = mock_inner
            with patch("adapters.mqtt_client.asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_in_executor = AsyncMock()
                mock_loop.return_value = loop
                await c.connect()

            # Verify fallback client_id was used
            call_args = mock_cls.call_args
            assert "gateway-" in str(call_args)


# ── disconnect() full flow (lines 112-141) ────────────────────────────


class TestDisconnect:

    @pytest.mark.asyncio
    async def test_disconnect_publishes_offline_and_stops(self, client, cfg):
        """disconnect() should publish offline, shutdown, then stop+disconnect."""
        client._connected = True
        mock_inner = MagicMock()
        client._client = mock_inner

        await client.disconnect()

        # Should publish offline status
        publish_calls = mock_inner.publish.call_args_list
        assert len(publish_calls) == 2
        # First: offline/clear LWT
        assert "status/offline" in publish_calls[0][0][0]
        # Second: online/shutdown
        assert "status/online" in publish_calls[1][0][0]

        mock_inner.loop_stop.assert_called_once()
        mock_inner.disconnect.assert_called_once()
        assert client._connected is False
        assert client._should_reconnect is False

    @pytest.mark.asyncio
    async def test_disconnect_cancels_reconnect_task(self, client):
        """disconnect() should cancel pending reconnect task."""
        mock_task = MagicMock()
        mock_task.done.return_value = False
        client._reconnect_task = mock_task
        client._connected = True
        client._client = MagicMock()

        await client.disconnect()

        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_without_client(self, client):
        """disconnect() with no client should not crash."""
        client._client = None
        await client.disconnect()
        assert client._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_offline_payload_content(self, client, cfg):
        """disconnect() offline payload should have graceful_shutdown reason."""
        client._connected = True
        mock_inner = MagicMock()
        client._client = mock_inner

        await client.disconnect()

        first_publish = mock_inner.publish.call_args_list[0]
        payload_str = first_publish[0][1]
        payload = json.loads(payload_str)
        assert payload["reason"] == "graceful_shutdown"
        assert payload["status"] == "offline"


# ── _do_publish exception path (lines 232-234) ────────────────────────


class TestDoPublishException:

    @pytest.mark.asyncio
    async def test_do_publish_handles_exception(self, connected_client):
        """_do_publish should return False on exception."""
        connected_client._client.publish.side_effect = Exception("network error")
        result = await connected_client._do_publish("topic", "payload")
        assert result is False

    @pytest.mark.asyncio
    async def test_do_publish_failure_rc(self, connected_client):
        """_do_publish should return False when rc != MQTT_ERR_SUCCESS."""
        mock_info = MagicMock()
        mock_info.rc = 1  # failure
        connected_client._client.publish.return_value = mock_info
        result = await connected_client._do_publish("topic", "payload")
        assert result is False

    @pytest.mark.asyncio
    async def test_do_publish_success(self, connected_client):
        """_do_publish should return True on success."""
        result = await connected_client._do_publish("topic", "payload", retain=True)
        assert result is True


# ── publish_raw (lines 242-244) ───────────────────────────────────────


class TestPublishRaw:

    @pytest.mark.asyncio
    async def test_publish_raw_not_connected(self, client):
        result = await client.publish_raw("custom/topic", "{}")
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_raw_connected(self, connected_client):
        result = await connected_client.publish_raw(
            "custom/topic", '{"key":"value"}', retain=True
        )
        assert result is True
        call_args = connected_client._client.publish.call_args
        assert call_args[0][0] == "custom/topic"

    @pytest.mark.asyncio
    async def test_publish_raw_no_retain_default(self, connected_client):
        result = await connected_client.publish_raw("topic", "data")
        assert result is True
        call_args = connected_client._client.publish.call_args
        assert call_args[1]["retain"] is False
