"""MQTT client for publishing telemetry to cloud

Features:
- Batch telemetry publishing (T-1101)
- Last Will and Testament (LWT) for disconnect detection
- Auto-reconnect with exponential backoff
- Connection state change callbacks
- Offline queue (delegates to TelemetryCache)
"""

import asyncio
import json
import logging
import time
from typing import Callable

import paho.mqtt.client as mqtt

from config import MQTTConfig
from models import TelemetryPoint

logger = logging.getLogger(__name__)


class MQTTClient:
    """MQTT publisher for gateway telemetry with batch + resilience support"""

    def __init__(self, config: MQTTConfig):
        self.config = config
        self._client: mqtt.Client | None = None
        self._connected = False
        self._should_reconnect = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_task: asyncio.Task | None = None
        self._on_reconnect_callbacks: list[Callable] = []
        self._on_disconnect_callbacks: list[Callable] = []

    @property
    def connected(self) -> bool:
        return self._connected

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self._connected = True
            self._reconnect_attempts = 0
            logger.info("MQTT connected to %s:%d", self.config.host, self.config.port)
            # Notify reconnect callbacks (for offline cache flush)
            for cb in self._on_reconnect_callbacks:
                try:
                    cb()
                except Exception as e:
                    logger.warning("Reconnect callback error: %s", e)
        else:
            logger.error("MQTT connection failed (rc=%d)", rc)

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False
        if rc != 0:
            logger.warning("MQTT unexpected disconnect (rc=%d), will retry", rc)
        else:
            logger.info("MQTT clean disconnect")
        # Notify disconnect callbacks
        for cb in self._on_disconnect_callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning("Disconnect callback error: %s", e)

    def _build_lwt(self) -> tuple:
        """Build Last Will and Testament message"""
        topic = f"{self.config.topic_prefix}/status/offline"
        payload = json.dumps({
            "gateway_id": self.config.client_id,
            "status": "offline",
            "timestamp": time.time(),
            "reason": "unexpected_disconnect",
        })
        return (topic, payload, self.config.qos, True)  # retain=True

    async def connect(self) -> None:
        """Connect to MQTT broker with LWT and auto-reconnect"""
        loop = asyncio.get_event_loop()
        client_id = self.config.client_id or f"gateway-{self.config.host}"
        self._client = mqtt.Client(client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        # Set credentials
        if self.config.username:
            self._client.username_pw_set(self.config.username, self.config.password)

        # Set Last Will and Testament
        lwt = self._build_lwt()
        self._client.will_set(*lwt)
        logger.info("MQTT LWT set: %s", lwt[0])

        # Enable automatic reconnect by paho
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

        # Run connect in thread pool
        def _do_connect():
            self._client.connect(self.config.host, self.config.port, self.config.keepalive)
            self._client.loop_start()

        await loop.run_in_executor(None, _do_connect)
        self._should_reconnect = True
        logger.info("MQTT connecting to %s:%d...", self.config.host, self.config.port)

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker and publish online=LWT cleanup"""
        self._should_reconnect = False

        # Cancel reconnect task
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()

        if self._client:
            # Publish clean offline status (clear retained LWT)
            offline_topic = f"{self.config.topic_prefix}/status/offline"
            offline_payload = json.dumps({
                "gateway_id": self.config.client_id,
                "status": "offline",
                "timestamp": time.time(),
                "reason": "graceful_shutdown",
            })
            self._client.publish(offline_topic, offline_payload, qos=self.config.qos, retain=True)

            # Publish graceful offline status
            online_topic = f"{self.config.topic_prefix}/status/online"
            self._client.publish(
                online_topic,
                payload=json.dumps({"gateway_id": self.config.client_id, "status": "shutdown"}),
                qos=self.config.qos, retain=True,
            )

            self._client.loop_stop()
            self._client.disconnect()

        self._connected = False
        logger.info("MQTT disconnected")

    async def publish_telemetry(self, point: TelemetryPoint) -> bool:
        """Publish a single telemetry point to MQTT topic"""
        if not self._connected or not self._client:
            logger.debug("MQTT not connected, telemetry will be cached locally")
            return False

        topic = f"{self.config.topic_prefix}/telemetry/{point.device_id}"
        payload = json.dumps(point.to_api_payload())

        return await self._do_publish(topic, payload)

    async def publish_telemetry_batch(self, points: list[TelemetryPoint]) -> dict:
        """Publish a batch of telemetry points efficiently (T-1101)

        Groups points by device_id and sends as a single message per device,
        reducing MQTT overhead for high-frequency telemetry.

        Returns:
            dict with 'success_count', 'failure_count', 'total'
        """
        if not self._connected or not self._client:
            logger.debug("MQTT not connected, batch will be cached locally (%d points)", len(points))
            return {"success_count": 0, "failure_count": len(points), "total": len(points)}

        # Group by device_id for efficient batching
        device_groups: dict[str, list] = {}
        for point in points:
            device_groups.setdefault(point.device_id, []).append(point.to_api_payload())

        success_count = 0
        failure_count = 0

        for device_id, payloads in device_groups.items():
            topic = f"{self.config.topic_prefix}/telemetry/{device_id}/batch"
            batch_payload = json.dumps({
                "device_id": device_id,
                "count": len(payloads),
                "telemetry": payloads,
            })

            ok = await self._do_publish(topic, batch_payload)
            if ok:
                success_count += len(payloads)
            else:
                failure_count += len(payloads)

        logger.debug(
            "MQTT batch published: %d success, %d failed out of %d",
            success_count, failure_count, len(points),
        )
        return {"success_count": success_count, "failure_count": failure_count, "total": len(points)}

    async def publish_status(self, status: str, extra: dict = None) -> bool:
        """Publish gateway status message (online/offline/heartbeat)"""
        if not self._connected or not self._client:
            return False

        topic = f"{self.config.topic_prefix}/status/{status}"
        payload = json.dumps({
            "gateway_id": self.config.client_id,
            "status": status,
            "timestamp": time.time(),
            **(extra or {}),
        })
        return await self._do_publish(topic, payload, retain=True)

    async def publish_alarm(self, device_id: str, alarm: dict) -> bool:
        """Publish alarm event to MQTT"""
        if not self._connected or not self._client:
            return False

        topic = f"{self.config.topic_prefix}/alarm/{device_id}"
        payload = json.dumps(alarm)
        return await self._do_publish(topic, payload)

    async def _do_publish(self, topic: str, payload: str, retain: bool = False) -> bool:
        """Internal publish with thread pool execution"""
        def _publish():
            info = self._client.publish(topic, payload, qos=self.config.qos, retain=retain)
            return info.rc == mqtt.MQTT_ERR_SUCCESS

        loop = asyncio.get_event_loop()
        try:
            success = await loop.run_in_executor(None, _publish)
            if success:
                logger.debug("MQTT published to %s (%d bytes)", topic, len(payload))
            else:
                logger.warning("MQTT publish failed for %s", topic)
            return success
        except Exception as e:
            logger.error("MQTT publish exception for %s: %s", topic, e)
            return False

    async def publish_raw(self, topic: str, payload: str, retain: bool = False) -> bool:
        """Publish raw payload to arbitrary topic (for offline sync use).

        This is a low-level escape hatch — callers are responsible for topic naming.
        Uses the same thread-pool publish path as _do_publish.
        """
        if not self._connected or not self._client:
            return False
        return await self._do_publish(topic, payload, retain=retain)

    def on_reconnect(self, callback: Callable) -> None:
        """Register callback fired when MQTT reconnects (for offline cache flush)"""
        self._on_reconnect_callbacks.append(callback)

    def on_disconnect(self, callback: Callable) -> None:
        """Register callback fired when MQTT disconnects"""
        self._on_disconnect_callbacks.append(callback)
