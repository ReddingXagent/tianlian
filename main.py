#!/usr/bin/env python3
"""天链V3 Edge Gateway - Main Entry Point

Orchestrates all adapters (Modbus, OCPP, MQTT), local cache, and debug API.

Usage:
    python main.py                   # Run with default config
    python main.py --config cfg.yaml # Run with custom config file
    GATEWAY_ID=GW-002 python main.py # Override via environment variables

Architecture:
    ┌──────────────────────────────────────────────────────┐
    │                      main.py                          │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
    │  │  Modbus  │  │   OCPP   │  │   MQTT   │           │
    │  │ Adapter  │  │ Adapter  │  │  Client  │           │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
    │       │             │             │                   │
    │       └──────┬──────┘             │                   │
    │              │ on_telemetry       │                   │
    │              ▼                    ▼                   │
    │       ┌─────────────┐    ┌──────────────┐            │
    │       │  Telemetry  │    │  Local API   │            │
    │       │   Cache     │    │  (FastAPI)   │            │
    │       └─────────────┘    └──────────────┘            │
    │              │                                       │
    │              ▼                                       │
    │       ┌─────────────┐                                │
    │       │  Cloud API  │  (register/heartbeat/alarm)    │
    │       └─────────────┘                                │
    └──────────────────────────────────────────────────────┘
"""

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Ensure project root is on sys.path
_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import GatewayConfig
from models import TelemetryPoint, TelemetryBatch
from adapters.modbus_adapter import ModbusAdapter
from adapters.ocpp_adapter import OCPPAdapter
from adapters.mqtt_client import MQTTClient
from storage.cache import TelemetryCache
from api.server import create_app, run_api

# ── Logging ─────────────────────────────────────────────────────────────

def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("pymodbus").setLevel(logging.WARNING)
    logging.getLogger("paho").setLevel(logging.WARNING)


# ── Gateway Core ─────────────────────────────────────────────────────────

class EdgeGateway:
    """天链V3 Edge Gateway - main orchestrator"""

    def __init__(self, config: GatewayConfig):
        self.config = config
        self.logger = logging.getLogger("gateway")

        # State
        self._start_time: float = 0.0
        self._running: bool = False
        self._latest_telemetry: Dict[str, dict] = {}
        self._device_count: int = 0
        self._registered: bool = False
        self._cloud_token: Optional[str] = None

        # Telemetry batch buffer for cloud upload
        self._telemetry_buffer: List[TelemetryPoint] = []
        self._alarm_buffer: List[dict] = []

        # Components (initialized in start())
        self.cache: Optional[TelemetryCache] = None
        self.modbus: Optional[ModbusAdapter] = None
        self.ocpp: Optional[OCPPAdapter] = None
        self.mqtt: Optional[MQTTClient] = None
        self._api_task: Optional[asyncio.Task] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._cloud_heartbeat_task: Optional[asyncio.Task] = None
        self._cloud_upload_task: Optional[asyncio.Task] = None

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start all gateway components"""
        self._start_time = time.monotonic()
        self._running = True

        self.logger.info(
            "Edge Gateway starting: id=%s name=%s",
            self.config.gateway_id,
            self.config.gateway_name,
        )

        # 1. Initialize local cache
        self.cache = TelemetryCache(self.config.storage)
        self.logger.info("Telemetry cache initialized (db=%s)", self.config.storage.db_path)

        # 2. Initialize adapters
        self.modbus = ModbusAdapter(self.config.modbus)
        self.ocpp = OCPPAdapter(self.config.ocpp)
        self.mqtt = MQTTClient(self.config.mqtt)

        # 3. Wire telemetry callbacks: adapter → cache + MQTT publish + cloud buffer
        def on_telemetry(point: TelemetryPoint) -> None:
            asyncio.create_task(self._handle_telemetry(point))

        def on_alarm(device_id: str, alarm_type: str, message: str) -> None:
            asyncio.create_task(self._handle_alarm(device_id, alarm_type, message))

        self.modbus.on_telemetry(on_telemetry)
        self.modbus.on_alarm(on_alarm)
        self.ocpp.on_telemetry(on_telemetry)
        self.ocpp.on_alarm(on_alarm)

        # 4. Connect MQTT
        try:
            await self.mqtt.connect()
        except Exception as e:
            self.logger.warning("MQTT connection failed (non-fatal): %s", e)

        # 5. Register with cloud
        if self.config.cloud.register_on_startup:
            await self._register_with_cloud()

        # 6. Start adapters
        await self.modbus.start()
        await self.ocpp.start()

        # 7. Start local API
        app = create_app(
            cache=self.cache,
            start_time=self._start_time,
            device_count_callback=lambda: self._device_count,
            latest_telemetry_callback=lambda: self._latest_telemetry,
            modbus_adapter=self.modbus,
            ocpp_adapter=self.ocpp,
        )
        self._api_task = asyncio.create_task(run_api(self.config.local_api, app))

        # 8. Start background tasks
        self._sync_task = asyncio.create_task(self._offline_sync_loop())
        self._cloud_heartbeat_task = asyncio.create_task(self._cloud_heartbeat_loop())
        self._cloud_upload_task = asyncio.create_task(self._cloud_upload_loop())

        self.logger.info("Edge Gateway started successfully")

    async def stop(self) -> None:
        """Graceful shutdown"""
        self.logger.info("Edge Gateway shutting down...")
        self._running = False

        # Deregister from cloud
        if self._registered and self.config.cloud.deregister_on_shutdown:
            await self._deregister_from_cloud()

        # Stop adapters (order matters: stop polling first)
        for name, adapter in [("Modbus", self.modbus), ("OCPP", self.ocpp)]:
            if adapter:
                try:
                    await adapter.stop()
                except Exception as e:
                    self.logger.warning("%s stop error: %s", name, e)

        # Stop MQTT
        if self.mqtt:
            try:
                await self.mqtt.disconnect()
            except Exception as e:
                self.logger.warning("MQTT disconnect error: %s", e)

        # Cancel background tasks
        for name, task in [
            ("API", self._api_task),
            ("Sync", self._sync_task),
            ("CloudHeartbeat", self._cloud_heartbeat_task),
            ("CloudUpload", self._cloud_upload_task),
        ]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    self.logger.warning("%s task error: %s", name, e)

        # Close cache
        if self.cache:
            self.cache.close()

        self.logger.info("Edge Gateway stopped")

    # ── Cloud Registration ──────────────────────────────────────────

    async def _register_with_cloud(self) -> None:
        """Register this gateway with the cloud platform (POST /gateways)"""
        try:
            import aiohttp

            url = f"{self.config.cloud.base_url}/gateways"
            payload = {
                "gateway_id": self.config.gateway_id,
                "gateway_name": self.config.gateway_name,
                "status": "online",
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "version": "0.2.0",
                    "adapters": {
                        "modbus": {
                            "host": self.config.modbus.host,
                            "port": self.config.modbus.port,
                            "mode": "real" if self.config.modbus.use_real_modbus else "simulated",
                        },
                        "ocpp": {
                            "charger_id": self.config.ocpp.charger_id,
                            "mode": "real" if self.config.ocpp.use_real_charger else "simulated",
                        },
                    },
                },
            }

            headers = {"Content-Type": "application/json"}
            if self.config.cloud.token:
                headers["Authorization"] = f"Bearer {self.config.cloud.token}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        self._cloud_token = data.get("token", self.config.cloud.token)
                        self._registered = True
                        self.logger.info(
                            "Gateway registered with cloud: %s (status=%d)",
                            self.config.gateway_id, resp.status,
                        )
                    elif resp.status == 409:
                        # Gateway already exists, treat as success
                        self._registered = True
                        self.logger.info(
                            "Gateway already registered with cloud: %s (status=%d)",
                            self.config.gateway_id, resp.status,
                        )
                    else:
                        self.logger.warning(
                            "Cloud registration failed: %s (status=%d)",
                            self.config.gateway_id, resp.status,
                        )
        except ImportError:
            self.logger.warning("aiohttp not installed, skipping cloud registration")
        except Exception as e:
            self.logger.warning("Cloud registration error: %s", e)

    async def _deregister_from_cloud(self) -> None:
        """Deregister this gateway from the cloud platform (DELETE /gateways/{id})"""
        try:
            import aiohttp

            url = f"{self.config.cloud.base_url}/gateways/{self.config.gateway_id}"
            headers = {"Content-Type": "application/json"}
            if self._cloud_token:
                headers["Authorization"] = f"Bearer {self._cloud_token}"

            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status in (200, 204):
                        self.logger.info(
                            "Gateway deregistered from cloud: %s",
                            self.config.gateway_id,
                        )
                    else:
                        self.logger.warning(
                            "Cloud deregistration failed: %s (status=%d)",
                            self.config.gateway_id, resp.status,
                        )
        except ImportError:
            pass
        except Exception as e:
            self.logger.warning("Cloud deregistration error: %s", e)
        finally:
            self._registered = False

    # ── Cloud Heartbeat ─────────────────────────────────────────────

    async def _cloud_heartbeat_loop(self) -> None:
        """Periodically send heartbeat to cloud platform"""
        while self._running:
            try:
                await asyncio.sleep(self.config.cloud.heartbeat_interval)
                if not self._running:
                    break

                if not self._registered:
                    continue

                await self._send_cloud_heartbeat()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.warning("Cloud heartbeat error: %s", e)

    async def _send_cloud_heartbeat(self) -> None:
        """Send a single heartbeat to cloud"""
        try:
            import aiohttp

            url = f"{self.config.cloud.base_url}/gateways/{self.config.gateway_id}/heartbeat"
            payload = {
                "gateway_id": self.config.gateway_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "online",
                "device_count": self._device_count,
                "cache_size": self.cache.get_cache_size() if self.cache else 0,
            }

            headers = {"Content-Type": "application/json"}
            if self._cloud_token:
                headers["Authorization"] = f"Bearer {self._cloud_token}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status in (200, 201, 204):
                        self.logger.debug("Cloud heartbeat sent: %s", self.config.gateway_id)
                    else:
                        self.logger.warning(
                            "Cloud heartbeat failed: status=%d", resp.status,
                        )
        except ImportError:
            pass
        except Exception as e:
            self.logger.debug("Cloud heartbeat send error: %s", e)

    # ── Cloud Telemetry Upload ──────────────────────────────────────

    async def _cloud_upload_loop(self) -> None:
        """Periodically upload buffered telemetry to cloud in batches"""
        while self._running:
            try:
                await asyncio.sleep(self.config.cloud.heartbeat_interval)
                if not self._running:
                    break

                await self._upload_telemetry_batch()
                await self._upload_alarm_batch()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.warning("Cloud upload error: %s", e)

    async def _upload_telemetry_batch(self) -> None:
        """Upload buffered telemetry points to cloud (POST /telemetry/batch)"""
        if not self._telemetry_buffer:
            return

        try:
            import aiohttp

            batch = TelemetryBatch(
                gateway_id=self.config.gateway_id,
                points=list(self._telemetry_buffer),
            )
            self._telemetry_buffer.clear()

            url = f"{self.config.cloud.base_url}/telemetry/batch"
            headers = {"Content-Type": "application/json"}
            if self._cloud_token:
                headers["Authorization"] = f"Bearer {self._cloud_token}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=batch.to_api_payload(), headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status in (200, 201, 204):
                        self.logger.debug(
                            "Cloud telemetry uploaded: %d points", len(batch.points),
                        )
                    else:
                        self.logger.warning(
                            "Cloud telemetry upload failed: status=%d", resp.status,
                        )
                        # Re-buffer on failure
                        self._telemetry_buffer.extend(batch.points)
        except ImportError:
            pass
        except Exception as e:
            self.logger.warning("Cloud telemetry upload error: %s", e)

    async def _upload_alarm_batch(self) -> None:
        """Upload buffered alarms to cloud (POST /alarms/batch)"""
        if not self._alarm_buffer:
            return

        try:
            import aiohttp

            alarms = list(self._alarm_buffer)
            self._alarm_buffer.clear()

            url = f"{self.config.cloud.base_url}/alarms/batch"
            payload = {
                "gateway_id": self.config.gateway_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "alarms": alarms,
            }

            headers = {"Content-Type": "application/json"}
            if self._cloud_token:
                headers["Authorization"] = f"Bearer {self._cloud_token}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status in (200, 201, 204):
                        self.logger.info("Cloud alarms uploaded: %d alarms", len(alarms))
                    else:
                        self.logger.warning(
                            "Cloud alarm upload failed: status=%d", resp.status,
                        )
                        self._alarm_buffer.extend(alarms)
        except ImportError:
            pass
        except Exception as e:
            self.logger.warning("Cloud alarm upload error: %s", e)

    # ── Telemetry Pipeline ──────────────────────────────────────────

    async def _handle_telemetry(self, point: TelemetryPoint) -> None:
        """Process incoming telemetry: cache locally + publish to MQTT + buffer for cloud"""
        try:
            # Update latest telemetry state
            self._latest_telemetry[point.device_id] = {
                "device_id": point.device_id,
                "timestamp": point.timestamp,
                "power": point.power,
                "voltage": point.voltage,
                "current": point.current,
                "temperature": point.temperature,
                "energy": point.energy,
                "soc": point.soc,
                "status": point.status,
            }
            self._device_count = len(self._latest_telemetry)

            # Cache locally for offline resilience
            self.cache.cache_telemetry(point)

            # Publish to MQTT (non-blocking, best-effort)
            if self.mqtt:
                await self.mqtt.publish_telemetry(point)

            # Buffer for cloud upload
            self._telemetry_buffer.append(point)

        except Exception as e:
            self.logger.error("Telemetry handling error: %s", e)

    async def _handle_alarm(self, device_id: str, alarm_type: str, message: str) -> None:
        """Process incoming alarm: log + buffer for cloud upload"""
        alarm = {
            "device_id": device_id,
            "alarm_type": alarm_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "warning",
        }
        self._alarm_buffer.append(alarm)

        # Also publish to MQTT if connected
        if self.mqtt:
            try:
                topic = f"{self.config.mqtt.topic_prefix}/alarm/{device_id}"
                payload = json.dumps(alarm)
                await self._mqtt_publish(topic, payload)
            except Exception:
                pass

    # ── Offline Sync ────────────────────────────────────────────────

    async def _offline_sync_loop(self) -> None:
        """Periodically retry syncing cached telemetry to MQTT"""
        while self._running:
            try:
                await asyncio.sleep(self.config.storage.retry_interval)
                if not self._running:
                    break

                unsynced = self.cache.get_unsynced(limit=50)
                if not unsynced:
                    continue

                self.logger.debug("Offline sync: %d pending entries", len(unsynced))
                synced_ids = []
                failed_ids = []

                for entry in unsynced:
                    try:
                        topic = f"{self.config.mqtt.topic_prefix}/telemetry/{entry['device_id']}"
                        payload = json.dumps(entry["payload"])
                        success = await self._mqtt_publish(topic, payload)
                        if success:
                            synced_ids.append(entry["id"])
                        else:
                            failed_ids.append(entry["id"])
                    except Exception:
                        failed_ids.append(entry["id"])

                if synced_ids:
                    self.cache.mark_synced(synced_ids)
                    self.logger.info("Offline sync: %d entries synced", len(synced_ids))
                if failed_ids:
                    self.cache.increment_retry(failed_ids)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.warning("Offline sync error: %s", e)

    async def _mqtt_publish(self, topic: str, payload: str) -> bool:
        """Publish to MQTT from sync loop"""
        if not self.mqtt or not self.mqtt._connected or not self.mqtt._client:
            return False

        import paho.mqtt.client as mqtt_lib

        def _do_publish():
            info = self.mqtt._client.publish(topic, payload, qos=self.mqtt.config.qos)
            return info.rc == mqtt_lib.MQTT_ERR_SUCCESS

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _do_publish)


# ── Signal Handling ──────────────────────────────────────────────────────

_gateway: Optional[EdgeGateway] = None


def _signal_handler(sig: int) -> None:
    """Handle SIGINT/SIGTERM for graceful shutdown"""
    logger = logging.getLogger("gateway")
    logger.info("Received signal %s, shutting down...", signal.Signals(sig).name)
    if _gateway:
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(lambda: asyncio.create_task(_gateway.stop()))


# ── Entry Point ──────────────────────────────────────────────────────────

async def main() -> None:
    """Main entry point"""
    global _gateway

    # Load configuration
    config = GatewayConfig.from_env()
    setup_logging(config.log_level)

    logger = logging.getLogger("gateway")
    logger.info("=" * 60)
    logger.info("天链V3 Edge Gateway v0.2.0")
    logger.info("Gateway ID: %s", config.gateway_id)
    logger.info("Cloud: %s (register=%s)", config.cloud.base_url, config.cloud.register_on_startup)
    logger.info("MQTT: %s:%d", config.mqtt.host, config.mqtt.port)
    logger.info("Modbus: %s:%d (mode=%s)", config.modbus.host, config.modbus.port,
                "real" if config.modbus.use_real_modbus else "simulated")
    logger.info("OCPP Charger: %s (mode=%s)", config.ocpp.charger_id,
                "real" if config.ocpp.use_real_charger else "simulated")
    logger.info("Local API: %s:%d", config.local_api.host, config.local_api.port)
    logger.info("=" * 60)

    # Create and start gateway
    _gateway = EdgeGateway(config)

    # Register signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: _signal_handler(s))
        except NotImplementedError:
            signal.signal(sig, lambda s, frame: _signal_handler(s))

    try:
        await _gateway.start()
        while _gateway._running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception("Fatal error: %s", e)
    finally:
        if _gateway and _gateway._running:
            await _gateway.stop()


if __name__ == "__main__":
    asyncio.run(main())
