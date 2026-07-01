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

from config import GatewayConfig, CloudConfig
from models import TelemetryPoint, TelemetryBatch
from adapters.modbus_adapter import ModbusAdapter
from adapters.ocpp_adapter import OCPPAdapter
from adapters.mqtt_client import MQTTClient
from adapters.cloud_client import CloudClient
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

        # Throughput counters (T-1202)
        self._telemetry_count: int = 0
        self._alarm_count: int = 0
        self._cloud_push_count: int = 0
        self._cloud_push_failures: int = 0

        # Telemetry batch buffer for cloud upload
        self._telemetry_buffer: List[TelemetryPoint] = []
        self._alarm_buffer: List[dict] = []

        # Components (initialized in start())
        self.cache: Optional[TelemetryCache] = None
        self.modbus: Optional[ModbusAdapter] = None
        self.ocpp: Optional[OCPPAdapter] = None
        self.mqtt: Optional[MQTTClient] = None
        self.cloud: Optional[CloudClient] = None
        self._api_task: Optional[asyncio.Task] = None
        self._sync_task: Optional[asyncio.Task] = None
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

        # 5. Start Cloud client (register + heartbeat)
        # Pass cache for offline degradation (telemetry/alarm cached when cloud unreachable)
        self.cloud = CloudClient(
            self.config.cloud, self.config.gateway_id, cache=self.cache
        )
        try:
            await self.cloud.start()
        except Exception as e:
            self.logger.warning("Cloud client start failed (non-fatal): %s", e)

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
            telemetry_count_callback=lambda: self._telemetry_count,
            alarm_count_callback=lambda: self._alarm_count,
            cloud_push_callback=lambda: {
                "push_total": self._cloud_push_count,
                "push_failures": self._cloud_push_failures,
            },
        )
        self._api_task = asyncio.create_task(run_api(self.config.local_api, app))

        # 8. Start background tasks
        self._sync_task = asyncio.create_task(self._offline_sync_loop())
        self._cloud_upload_task = asyncio.create_task(self._cloud_upload_loop())

        self.logger.info("Edge Gateway started successfully")

    async def stop(self) -> None:
        """Graceful shutdown"""
        self.logger.info("Edge Gateway shutting down...")
        self._running = False

        # Stop cloud client (deregister + heartbeat cancel)
        if self.cloud:
            try:
                await self.cloud.stop()
            except Exception as e:
                self.logger.warning("Cloud client stop error: %s", e)

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

    # ── Cloud Registration (delegated to CloudClient) ─────────────
    # The following methods were previously inline cloud API calls.
    # They are now handled by adapters/cloud_client.py CloudClient class.
    # Only telemetry/alarm upload remains here for buffer management.

    MAX_TELEMETRY_BUFFER = 500  # max buffered telemetry points
    MAX_ALARM_BUFFER = 100      # max buffered alarms

    def _trim_telemetry_buffer(self) -> None:
        """Cap telemetry buffer to prevent memory growth"""
        if len(self._telemetry_buffer) > self.MAX_TELEMETRY_BUFFER:
            dropped = len(self._telemetry_buffer) - self.MAX_TELEMETRY_BUFFER
            self._telemetry_buffer = self._telemetry_buffer[-self.MAX_TELEMETRY_BUFFER:]
            self.logger.warning("Telemetry buffer trimmed: %d old entries dropped", dropped)

    def _trim_alarm_buffer(self) -> None:
        """Cap alarm buffer to prevent memory growth"""
        if len(self._alarm_buffer) > self.MAX_ALARM_BUFFER:
            dropped = len(self._alarm_buffer) - self.MAX_ALARM_BUFFER
            self._alarm_buffer = self._alarm_buffer[-self.MAX_ALARM_BUFFER:]
            self.logger.warning("Alarm buffer trimmed: %d old entries dropped", dropped)

    # ── Cloud Telemetry Upload ──────────────────────────────────────

    async def _cloud_upload_loop(self) -> None:
        """Periodically upload buffered telemetry to cloud in batches"""
        while self._running:
            try:
                await asyncio.sleep(self.config.cloud.upload_interval)
                if not self._running:
                    break

                await self._upload_telemetry_batch()
                await self._upload_alarm_batch()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.warning("Cloud upload error: %s", e)

    async def _upload_telemetry_batch(self) -> None:
        """Upload buffered telemetry points to cloud via CloudClient.

        Note: data is already cached locally by _handle_telemetry().
        CloudClient also falls back to cache on failure, so no re-buffer needed.
        """
        if not self._telemetry_buffer:
            return

        batch = list(self._telemetry_buffer)
        self._telemetry_buffer.clear()

        if self.cloud:
            ok = await self.cloud.push_telemetry_batch(batch)
            self._cloud_push_count += 1
            if not ok:
                self._cloud_push_failures += 1
        else:
            # No cloud client: put back in buffer (capped)
            self._telemetry_buffer.extend(batch)
            self._trim_telemetry_buffer()

    async def _upload_alarm_batch(self) -> None:
        """Upload buffered alarms to cloud via CloudClient.

        Alarms are also cached by CloudClient on failure. Buffer is capped
        to prevent unbounded growth during prolonged cloud outage.
        """
        if not self._alarm_buffer:
            return

        alarms = list(self._alarm_buffer)
        self._alarm_buffer.clear()

        if self.cloud:
            await self.cloud.push_alarm_batch(alarms)
        else:
            self._alarm_buffer.extend(alarms)

        # Cap alarm buffer to prevent OOM during extended cloud outage
        self._trim_alarm_buffer()

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
            self._telemetry_count += 1

            # Publish to MQTT (non-blocking, best-effort)
            if self.mqtt:
                await self.mqtt.publish_telemetry(point)

            # Buffer for cloud upload — CloudClient.push_telemetry_batch
            # will write to cache on failure, so no pre-cache here.
            # This eliminates the double-cache bug (T-1202).
            self._telemetry_buffer.append(point)
            if len(self._telemetry_buffer) > self.MAX_TELEMETRY_BUFFER:
                self._trim_telemetry_buffer()

        except Exception as e:
            self.logger.error("Telemetry handling error: %s", e)

    async def _handle_alarm(self, device_id: str, alarm_type: str, message: str,
                             severity: str = "warning") -> None:
        """Process incoming alarm: cache + MQTT publish + cloud buffer"""
        alarm = {
            "device_id": device_id,
            "alarm_type": alarm_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": severity,
        }

        # Buffer for cloud upload — CloudClient.push_alarm_batch will
        # cache on failure, so no pre-cache here (T-1202 double-cache fix).
        self._alarm_buffer.append(alarm)
        self._alarm_count += 1
        if len(self._alarm_buffer) > self.MAX_ALARM_BUFFER:
            self._trim_alarm_buffer()

        # Publish to MQTT if connected
        if self.mqtt:
            try:
                await self.mqtt.publish_alarm(device_id, alarm)
            except Exception as e:
                self.logger.debug("MQTT alarm publish error: %s", e)

    # ── Offline Sync (Enhanced T-1102) ─────────────────────────────

    async def _offline_sync_loop(self) -> None:
        """Periodically retry syncing cached telemetry & alarms to MQTT.

        Enhanced with batch sync, priority handling, and alarm forwarding.
        """
        cleanup_counter = 0
        while self._running:
            try:
                await asyncio.sleep(self.config.storage.retry_interval)
                if not self._running:
                    break

                # Sync alarms first (higher priority)
                await self._sync_cached_alarms()

                # Sync telemetry in batches
                await self._sync_cached_telemetry()

                # Periodic cleanup (every cleanup_interval / retry_interval cycles)
                cleanup_counter += 1
                cleanup_cycles = max(1, self.config.storage.cleanup_interval // self.config.storage.retry_interval)
                if cleanup_counter >= cleanup_cycles:
                    cleanup_counter = 0
                    deleted = self.cache.cleanup(max_age_days=7)
                    if deleted:
                        self.logger.info("Cache cleanup: %d old entries removed", deleted)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.warning("Offline sync error: %s", e)

    async def _sync_cached_telemetry(self) -> None:
        """Sync cached telemetry entries to MQTT in batches"""
        batch_size = self.config.storage.batch_sync_size
        unsynced = self.cache.get_unsynced(limit=batch_size)
        if not unsynced:
            return

        self.logger.debug("Telemetry sync: %d pending entries", len(unsynced))

        if not self.mqtt or not self.mqtt.connected:
            # MQTT still down, increment retries to eventually drop dead entries
            self.cache.increment_retry([e["id"] for e in unsynced])
            return

        # Group by device_id for efficient batch MQTT publishing
        device_batches: dict[str, list] = {}
        entry_ids: list[int] = []
        for entry in unsynced:
            device_batches.setdefault(entry["device_id"], []).append(entry)
            entry_ids.append(entry["id"])

        synced_ids: list[int] = []
        failed_ids: list[int] = []

        for device_id, entries in device_batches.items():
            topic = f"{self.config.mqtt.topic_prefix}/telemetry/{device_id}/batch"
            payload = json.dumps({
                "device_id": device_id,
                "count": len(entries),
                "telemetry": [e["payload"] for e in entries],
                "replayed": True,  # flag: this is offline replay
            })
            success = await self._mqtt_publish(topic, payload)
            if success:
                synced_ids.extend(e["id"] for e in entries)
            else:
                failed_ids.extend(e["id"] for e in entries)

        if synced_ids:
            self.cache.mark_synced(synced_ids)
            self.logger.info("Telemetry sync: %d entries synced", len(synced_ids))
        if failed_ids:
            self.cache.increment_retry(failed_ids)
            self.logger.warning("Telemetry sync: %d entries failed", len(failed_ids))

    async def _sync_cached_alarms(self) -> None:
        """Sync cached alarm entries to MQTT"""
        unsynced = self.cache.get_unsynced_alarms(limit=50)
        if not unsynced:
            return

        if not self.mqtt or not self.mqtt.connected:
            self.cache.increment_alarm_retry([e["id"] for e in unsynced])
            return

        synced_ids: list[int] = []
        failed_ids: list[int] = []

        for entry in unsynced:
            topic = f"{self.config.mqtt.topic_prefix}/alarm/{entry['device_id']}"
            payload = json.dumps({
                **entry["payload"],
                "replayed": True,
            })
            success = await self._mqtt_publish(topic, payload)
            if success:
                synced_ids.append(entry["id"])
            else:
                failed_ids.append(entry["id"])

        if synced_ids:
            self.cache.mark_alarms_synced(synced_ids)
            self.logger.info("Alarm sync: %d entries synced", len(synced_ids))
        if failed_ids:
            self.cache.increment_alarm_retry(failed_ids)

    async def _mqtt_publish(self, topic: str, payload: str) -> bool:
        """Publish to MQTT from sync loop (uses public API)"""
        if not self.mqtt or not self.mqtt.connected:
            return False

        return await self.mqtt.publish_raw(topic, payload)


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
