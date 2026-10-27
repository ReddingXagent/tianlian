"""
天链 V3 边缘网关 - 主入口
整合所有模块：注册心跳、OCPP、Modbus、遥测上报、断网续传
"""
import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.core.config import config
from app.core.logging import logger
from app.modules.registry import gateway_registry
from app.modules.ocpp_server import ocpp_server
from app.modules.modbus_master import modbus_master
from app.modules.telemetry_reporter import telemetry_reporter
from app.modules.offline_buffer import offline_buffer
from app.modules.transaction_store import transaction_store


# ========== 模块生命周期管理 ==========

async def start_all_modules():
    """启动所有模块"""
    logger.info("=" * 60)
    logger.info(f"天链 V3 边缘网关启动中... [SN: {config.gateway.sn}]")
    logger.info(f"云端地址: {config.cloud.api_base}")
    logger.info("=" * 60)

    # 1. 断网续传（最先启动，确保数据不丢失）
    await offline_buffer.start()

    # 2. 充电交易缓存与回传（OCPP handler 依赖，须先于 OCPP 启动）
    await transaction_store.start()

    # 3. 网关注册与心跳
    await gateway_registry.start()

    # 4. OCPP WebSocket 服务端
    await ocpp_server.start()

    # 4. Modbus TCP 主站
    await modbus_master.start()

    # 5. 遥测上报
    await telemetry_reporter.start()

    logger.info("所有模块已启动 ✓")


async def stop_all_modules():
    """停止所有模块"""
    logger.info("正在停止所有模块...")

    await telemetry_reporter.stop()
    await modbus_master.stop()
    await ocpp_server.stop()
    await transaction_store.stop()
    await gateway_registry.stop()
    await offline_buffer.stop()

    logger.info("所有模块已停止 ✓")


# ========== FastAPI 管理 API ==========

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动
    await start_all_modules()
    yield
    # 停止
    await stop_all_modules()


app = FastAPI(
    title="天链 V3 边缘网关",
    description="Edge Gateway for Tianlian V3 Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 管理 API 路由 ==========

@app.get("/")
async def root():
    """网关信息"""
    return {
        "service": "天链 V3 边缘网关",
        "version": "1.0.0",
        "sn": config.gateway.sn,
        "name": config.gateway.name,
        "status": "running",
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "healthy",
        "gateway": {
            "registered": gateway_registry.is_registered,
            "online": gateway_registry.is_online,
            "gateway_id": gateway_registry.gateway_id,
        },
        "ocpp": {
            "enabled": config.ocpp.enabled,
            "connections": len(ocpp_server.connections),
        },
        "modbus": {
            "enabled": config.modbus.enabled,
            "devices": len(modbus_master.devices),
        },
        "telemetry": telemetry_reporter.stats,
        "transactions": {
            **transaction_store.stats,
            "outbox_pending": await transaction_store.outbox_pending_count(),
        },
        "offline_buffer": offline_buffer.stats,
    }


@app.get("/status")
async def status():
    """详细状态"""
    return {
        "gateway": {
            "sn": config.gateway.sn,
            "name": config.gateway.name,
            "model": config.gateway.model,
            "registered": gateway_registry.is_registered,
            "online": gateway_registry.is_online,
            "gateway_id": gateway_registry.gateway_id,
        },
        "ocpp": {
            "enabled": config.ocpp.enabled,
            "host": config.ocpp.host,
            "port": config.ocpp.port,
            "connections": len(ocpp_server.connections),
            "charge_points": await ocpp_server.get_connected_charge_points(),
        },
        "modbus": {
            "enabled": config.modbus.enabled,
            "devices": await modbus_master.get_device_status(),
        },
        "telemetry": telemetry_reporter.stats,
        "transactions": {
            **transaction_store.stats,
            "outbox_pending": await transaction_store.outbox_pending_count(),
        },
        "offline_buffer": offline_buffer.stats,
    }


@app.get("/ocpp/connections")
async def list_ocpp_connections():
    """获取 OCPP 充电桩连接列表"""
    return {
        "count": len(ocpp_server.connections),
        "connections": await ocpp_server.get_connected_charge_points(),
    }


@app.post("/ocpp/{charge_point_id}/start")
async def ocpp_remote_start(charge_point_id: str, id_tag: str = "DEFAULT"):
    """远程启动充电"""
    success = await ocpp_server.send_remote_start(charge_point_id, id_tag)
    return {"success": success, "charge_point_id": charge_point_id}


@app.post("/ocpp/{charge_point_id}/stop")
async def ocpp_remote_stop(charge_point_id: str, transaction_id: int):
    """远程停止充电"""
    success = await ocpp_server.send_remote_stop(charge_point_id, transaction_id)
    return {"success": success, "charge_point_id": charge_point_id}


@app.post("/ocpp/{charge_point_id}/reset")
async def ocpp_reset(charge_point_id: str, reset_type: str = "Soft"):
    """重置充电桩"""
    success = await ocpp_server.send_reset(charge_point_id, reset_type)
    return {"success": success, "charge_point_id": charge_point_id}


@app.get("/modbus/devices")
async def list_modbus_devices():
    """获取 Modbus 设备状态"""
    return {"devices": await modbus_master.get_device_status()}


@app.post("/offline-buffer/flush")
async def flush_offline_buffer():
    """手动触发离线缓存补传"""
    flushed = await offline_buffer.flush_pending(batch_size=100)
    return {"flushed": flushed, "pending": await offline_buffer.get_pending_count()}


@app.get("/offline-buffer/stats")
async def offline_buffer_stats():
    """离线缓存统计"""
    return {
        **offline_buffer.stats,
        "pending_count": await offline_buffer.get_pending_count(),
    }


# ========== 主函数 ==========

def main():
    """主入口"""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level=config.logging.level.lower(),
    )


if __name__ == "__main__":
    main()
