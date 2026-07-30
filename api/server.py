"""Local debug API server (FastAPI)"""

import logging
import time

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import LocalAPIConfig
from storage.cache import TelemetryCache

logger = logging.getLogger(__name__)

# Module-level references set by create_app
_cache: TelemetryCache | None = None
_start_time: float = 0.0
_device_count: int = 0
_latest_telemetry: dict = {}
_modbus_adapter = None
_ocpp_adapter = None


# ── Pydantic Models ──────────────────────────────────────────────────────

class SimulateTelemetryRequest(BaseModel):
    """Request body for manual telemetry injection"""
    device_type: str = Field(default="ocpp", description="Device type: 'ocpp' or 'modbus'")
    power: float = Field(default=0.0, description="Power in kW")
    voltage: float = Field(default=380.0, description="Voltage in V")
    current: float = Field(default=0.0, description="Current in A")
    temperature: float = Field(default=25.0, description="Temperature in °C")
    energy: float | None = Field(default=None, description="Cumulative energy in kWh")
    status: str = Field(default="normal", description="Device status")


class SimulateAlarmRequest(BaseModel):
    """Request body for manual alarm trigger"""
    device_type: str = Field(default="ocpp", description="Device type: 'ocpp' or 'modbus'")
    alarm_type: str = Field(default="test_alarm", description="Alarm type identifier")
    message: str = Field(default="Manual test alarm", description="Alarm message")


class CacheStatsResponse(BaseModel):
    """Cache statistics response"""
    unsynced_count: int
    total_count: int
    max_cache_size: int
    max_retries: int
    db_path: str


def create_app(
    cache: TelemetryCache,
    start_time: float,
    device_count_callback=None,
    latest_telemetry_callback=None,
    modbus_adapter=None,
    ocpp_adapter=None,
    telemetry_count_callback=None,
    alarm_count_callback=None,
    cloud_push_callback=None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        cache: TelemetryCache instance for cache size queries.
        start_time: Gateway start time (time.monotonic()).
        device_count_callback: Callable returning current device count.
        latest_telemetry_callback: Callable returning latest telemetry dict.
        modbus_adapter: ModbusAdapter instance for debug injection.
        ocpp_adapter: OCPPAdapter instance for debug injection.
    """
    global _cache, _start_time, _modbus_adapter, _ocpp_adapter
    _cache = cache
    _start_time = start_time
    _modbus_adapter = modbus_adapter
    _ocpp_adapter = ocpp_adapter

    app = FastAPI(
        title="天链V3 Edge Gateway API",
        description="Local debug API for edge gateway monitoring",
        version="0.2.0",
    )

    # CORS - allow local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ─────────────────────────────────────────────────────────

    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "gateway": "tianlian-v3-edge",
            "timestamp": time.time(),
        }

    @app.get("/api/v1/status")
    async def gateway_status():
        """Gateway runtime status"""
        uptime = time.monotonic() - _start_time
        devices = device_count_callback() if device_count_callback else 0
        cache_size = _cache.get_cache_size() if _cache else 0

        return {
            "uptime_seconds": round(uptime, 1),
            "uptime_formatted": _format_uptime(uptime),
            "device_count": devices,
            "cache_size": cache_size,
            "cache_max": _cache.config.max_cache_size if _cache else 0,
        }

    @app.get("/api/v1/telemetry/latest")
    async def latest_telemetry():
        """Latest telemetry data from all devices"""
        if latest_telemetry_callback:
            data = latest_telemetry_callback()
        else:
            data = {}

        return {
            "count": len(data),
            "telemetry": data,
        }

    @app.get("/api/v1/devices")
    async def device_list():
        """List of connected devices"""
        if latest_telemetry_callback:
            data = latest_telemetry_callback()
        else:
            data = {}

        devices = []
        for device_id, telemetry in data.items():
            devices.append({
                "device_id": device_id,
                "last_seen": telemetry.get("timestamp", ""),
                "status": telemetry.get("status", "unknown"),
                "power_kw": telemetry.get("power", 0),
                "voltage_v": telemetry.get("voltage", 0),
                "temperature_c": telemetry.get("temperature", 0),
            })

        return {
            "count": len(devices),
            "devices": devices,
        }

    # ── Debug / Simulation Endpoints ────────────────────────────────────

    @app.post("/api/v1/simulate/telemetry")
    async def simulate_telemetry(req: SimulateTelemetryRequest):
        """Manually inject a simulated telemetry point.

        Supports both OCPP and Modbus device types.
        The injected telemetry flows through the normal pipeline
        (cache + MQTT + cloud buffer).
        """
        if req.device_type == "ocpp":
            if not _ocpp_adapter:
                raise HTTPException(status_code=400, detail="OCPP adapter not available")
            point = _ocpp_adapter.inject_telemetry(
                power=req.power,
                voltage=req.voltage,
                current=req.current,
                temperature=req.temperature,
                energy=req.energy,
                status=req.status,
            )
        elif req.device_type == "modbus":
            if not _modbus_adapter:
                raise HTTPException(status_code=400, detail="Modbus adapter not available")
            point = _modbus_adapter.inject_telemetry(
                power=req.power,
                voltage=req.voltage,
                current=req.current,
                temperature=req.temperature,
                energy=req.energy,
                status=req.status,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown device_type: {req.device_type}")

        return {
            "status": "injected",
            "device_type": req.device_type,
            "telemetry": point.to_dict(),
        }

    @app.post("/api/v1/simulate/alarm")
    async def simulate_alarm(req: SimulateAlarmRequest):
        """Manually trigger a simulated alarm.

        The alarm flows through the normal pipeline (MQTT + cloud buffer).
        """
        if req.device_type == "ocpp":
            if not _ocpp_adapter:
                raise HTTPException(status_code=400, detail="OCPP adapter not available")
            _ocpp_adapter.inject_alarm(req.alarm_type, req.message)
        elif req.device_type == "modbus":
            if not _modbus_adapter:
                raise HTTPException(status_code=400, detail="Modbus adapter not available")
            _modbus_adapter.inject_alarm(req.alarm_type, req.message)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown device_type: {req.device_type}")

        return {
            "status": "triggered",
            "device_type": req.device_type,
            "alarm_type": req.alarm_type,
            "message": req.message,
        }

    @app.get("/api/v1/cache/stats", response_model=CacheStatsResponse)
    async def cache_stats():
        """Get cache statistics including unsynced count and configuration."""
        if not _cache:
            raise HTTPException(status_code=500, detail="Cache not initialized")

        # Use the public API to avoid thread-safety issues with direct conn access
        stats = _cache.get_stats()
        tel = stats.get("telemetry", {})
        alarm = stats.get("alarms", {})

        return CacheStatsResponse(
            unsynced_count=(tel.get("unsynced", 0) + alarm.get("unsynced", 0)),
            total_count=(tel.get("total", 0) + alarm.get("total", 0)),
            max_cache_size=_cache.config.max_cache_size,
            max_retries=_cache.config.max_retries,
            db_path=_cache.config.db_path,
        )

    @app.get("/api/v1/dashboard")
    async def dashboard():
        """聚合端点 — 一次请求返回所有关键信息"""
        uptime = time.monotonic() - _start_time
        devices_cb = device_count_callback() if device_count_callback else 0
        latest_cb = latest_telemetry_callback() if latest_telemetry_callback else {}
        tel_count = telemetry_count_callback() if telemetry_count_callback else 0
        alarm_count = alarm_count_callback() if alarm_count_callback else 0
        cloud_info = cloud_push_callback() if cloud_push_callback else {}
        cache_stats = _cache.get_stats() if _cache else {}

        # device list from latest telemetry
        device_list = []
        for device_id, t in latest_cb.items():
            device_list.append({
                "device_id": device_id,
                "status": t.get("status", "unknown"),
                "power_kw": t.get("power", 0),
                "voltage_v": t.get("voltage", 0),
                "temperature_c": t.get("temperature", 0),
                "last_seen": t.get("timestamp", ""),
            })

        # cloud success rate
        cloud_pushed = cloud_info.get("push_total", 0)
        cloud_failed = cloud_info.get("push_failures", 0)
        cloud_total = cloud_pushed + cloud_failed
        cloud_success_rate = round(cloud_pushed / cloud_total, 4) if cloud_total > 0 else 1.0

        return {
            "status": "healthy",
            "gateway": "tianlian-v3-edge",
            "uptime_seconds": round(uptime, 1),
            "uptime_formatted": _format_uptime(uptime),
            "device_count": devices_cb,
            "devices": device_list,
            "telemetry": {
                "latest": latest_cb,
                "total": tel_count,
                "rate_per_sec": round(tel_count / uptime, 2) if uptime > 0 else 0.0,
            },
            "alarms": {
                "total": alarm_count,
                "rate_per_sec": round(alarm_count / uptime, 4) if uptime > 0 else 0.0,
            },
            "cloud": {
                **cloud_info,
                "success_rate": cloud_success_rate,
            },
            "cache": cache_stats,
            "timestamp": time.time(),
        }

    @app.get("/api/v1/perf")
    async def performance_metrics():
        """Runtime performance metrics for monitoring (T-1202).

        Returns buffer sizes, cache stats, throughput counters, and cloud health.
        """
        cache_stats = _cache.get_stats() if _cache else {}
        uptime = time.monotonic() - _start_time
        devices = device_count_callback() if device_count_callback else 0
        tel_count = telemetry_count_callback() if telemetry_count_callback else 0
        alarm_count = alarm_count_callback() if alarm_count_callback else 0
        cloud_info = cloud_push_callback() if cloud_push_callback else {}

        # Calculate rates
        tel_rate = round(tel_count / uptime, 2) if uptime > 0 else 0.0
        alarm_rate = round(alarm_count / uptime, 4) if uptime > 0 else 0.0

        # Cloud push success rate (fields from main.py cloud_push_callback)
        cloud_pushed = cloud_info.get("push_total", 0)
        cloud_failed = cloud_info.get("push_failures", 0)
        cloud_total = cloud_pushed + cloud_failed
        cloud_success_rate = round(cloud_pushed / cloud_total, 4) if cloud_total > 0 else 1.0

        return {
            "uptime_seconds": round(uptime, 1),
            "device_count": devices,
            "throughput": {
                "telemetry_total": tel_count,
                "telemetry_rate_per_sec": tel_rate,
                "alarm_total": alarm_count,
                "alarm_rate_per_sec": alarm_rate,
            },
            "cloud": {
                **cloud_info,
                "success_rate": cloud_success_rate,
            },
            "cache": cache_stats,
            "timestamp": time.time(),
        }

    return app


async def run_api(config: LocalAPIConfig, app: FastAPI) -> None:
    """Run the FastAPI server"""
    config = uvicorn.Config(
        app,
        host=config.host,
        port=config.port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info("Local API starting on %s:%d", config.host, config.port)
    await server.serve()


def _format_uptime(seconds: float) -> str:
    """Format uptime seconds into human-readable string"""
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)
