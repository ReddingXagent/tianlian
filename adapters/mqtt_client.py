"""MQTT client for publishing telemetry to cloud"""

import asyncio
import json
import logging
from typing import Callable, Optional

import paho.mqtt.client as mqtt

from config import MQTTConfig
from models import TelemetryPoint

logger = logging.getLogger(__name__)


class MQTTClient:
    """MQTT publisher for gateway telemetry"""

    def __init__(self, config: MQTTConfig):
        self.config = config
        self._client: Optional[mqtt.Client] = None
        self._connected = False

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self._connected = True
            logger.info("MQTT connected to %s:%d", self.config.host, self.config.port)
        else:
            logger.error("MQTT connection failed (rc=%d)", rc)

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False
        if rc != 0:
            logger.warning("MQTT unexpected disconnect (rc=%d)", rc)

    async def connect(self) -> None:
        """Connect to MQTT broker"""
        loop = asyncio.get_event_loop()
        self._client = mqtt.Client(client_id=f"gateway-{id(self)}")
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        if self.config.username:
            self._client.username_pw_set(self.config.username, self.config.password)

        # Run connect in thread pool
        def _do_connect():
            self._client.connect(self.config.host, self.config.port, self.config.keepalive)
            self._client.loop_start()

        await loop.run_in_executor(None, _do_connect)
        logger.info("MQTT connecting to %s:%d...", self.config.host, self.config.port)

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker"""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
        logger.info("MQTT disconnected")

    async def publish_telemetry(self, point: TelemetryPoint) -> bool:
        """Publish telemetry point to MQTT topic"""
        if not self._connected or not self._client:
            logger.warning("MQTT not connected, dropping telemetry")
            return False

        topic = f"{self.config.topic_prefix}/telemetry/{point.device_id}"
        payload = json.dumps(point.to_api_payload())

        def _do_publish():
            info = self._client.publish(topic, payload, qos=self.config.qos)
            return info.rc == mqtt.MQTT_ERR_SUCCESS

        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, _do_publish)
        if success:
            logger.debug("MQTT published to %s", topic)
        else:
            logger.warning("MQTT publish failed for %s", topic)
        return success
