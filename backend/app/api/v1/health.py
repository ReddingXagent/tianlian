"""
健康检查 + 健康度监控

端点:
  - /api/v1/health  — 基本信息（已有）
  - /api/v1/live    — liveness：仅检查进程存活
  - /api/v1/ready   — readiness：全量依赖检查
"""
import os
import shutil
import logging
import time as time_module
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.api.deps import require_platform_admin
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.core.database import get_db, engine, DB_TYPE
from app.services.health_monitor import health_monitor
from app.models.device import Device
from app.core.response import success_response

logger = logging.getLogger(__name__)

router = APIRouter()

_uptime_start = time_module.time()


# ─── 依赖项检查 ───

def check_database() -> Dict[str, Any]:
    """检查数据库连接池状态"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        # 获取连接池状态
        pool = engine.pool
        result = {
            "status": "ok",
            "pool_size": pool.size(),
            "active_connections": pool.checkedin(),
            "idle_connections": pool.checkedin(),
            "waiting_connections": 0,
            "db_type": DB_TYPE,
        }

        # SQLAlchemy 2.0+ 的 pool 没有 overflow() / checkedout() ?
        # 保守处理，捕获可能没有的方法
        try:
            result["active_connections"] = pool.checkedout()
            result["idle_connections"] = pool.size() - pool.checkedout()
        except Exception:
            pass

        try:
            result["waiting_connections"] = max(0, pool.overflow())
        except Exception:
            pass

        return result
    except Exception as e:
        logger.warning("数据库健康检查失败: %s", e)
        return {
            "status": "error",
            "error": "健康检查失败",
        }


def check_redis() -> Dict[str, Any]:
    """检查 Redis 可达性（如果配置了）"""
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return {
            "status": "disabled",
            "reason": "REDIS_URL 未配置",
        }
    try:
        import redis as _redis
        # socket_timeout 补齐操作阶段超时 (socket_connect_timeout 只管建连):
        # 无 socket_timeout 下 ping()/info() 遇 Redis 停顿永久 hang → 健康检查端点卡死。
        # 3s 与 app.core.cache.CacheService 口径一致。
        r = _redis.from_url(
            redis_url,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        r.ping()
        info = r.info()
        return {
            "status": "ok",
            "version": info.get("redis_version", "unknown"),
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "connected_clients": info.get("connected_clients", 0),
        }
    except Exception as e:
        logger.warning("Redis 健康检查失败: %s", e)
        return {
            "status": "error",
            "error": "健康检查失败",
        }


def check_mqtt_broker() -> Dict[str, Any]:
    """检查 MQTT broker 可达性（通过尝试建立 socket 连接）"""
    import socket
    mqtt_url = os.getenv("MQTT_BROKER", "")
    if not mqtt_url:
        return {
            "status": "disabled",
            "reason": "MQTT_BROKER 未配置",
        }

    # 解析 mqtt://host:port 格式
    try:
        host = mqtt_url.replace("mqtt://", "").replace("mqtts://", "").split(":")[0]
        port_str = mqtt_url.split(":")[-1].split("/")[0]
        port = int(port_str) if port_str.isdigit() else 1883
    except Exception:
        host = "localhost"
        port = 1883

    try:
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
        return {
            "status": "ok",
            "host": host,
            "port": port,
        }
    except Exception as e:
        logger.warning("MQTT broker 健康检查失败: %s", e)
        return {
            "status": "error",
            "host": host,
            "port": port,
            "error": "健康检查失败",
        }


def check_filesystem() -> Dict[str, Any]:
    """检查文件系统可用空间"""
    paths_to_check = [
        ".",  # 当前目录
        "/tmp",
    ]
    results = {}
    for p in paths_to_check:
        try:
            usage = shutil.disk_usage(p)
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            pct_free = round(usage.free / usage.total * 100, 1) if usage.total > 0 else 0
            results[p] = {
                "total_gb": round(total_gb, 1),
                "free_gb": round(free_gb, 1),
                "free_pct": pct_free,
            }
        except Exception as e:
            logger.warning("文件系统检查失败: %s", e)
            results[p] = {
                "error": "文件系统检查失败",
            }
    return {"paths": results}


# ─── 端点 ───

@router.get("/health")
async def health_check():
    from app.core.config import settings
    return success_response({
        "status": "healthy",
        "version": settings.APP_VERSION,
        "service": f"天链光储充运维系统 V{settings.APP_VERSION}",
    })


@router.get("/live")
async def liveness():
    """
    Liveness 探针：仅检查进程是否存活
    不依赖任何外部服务
    """
    return {
        "status": "alive",
        "uptime_seconds": round(time_module.time() - _uptime_start),
    }


@router.get("/livez")
async def liveness_short():
    """Kubernetes 兼容 liveness 探针别名"""
    return await liveness()


@router.get("/ready")
async def readiness():
    """
    Readiness 探针：检查所有依赖服务

    返回每个依赖的状态和整体判断
    """
    db_status = check_database()
    redis_status = check_redis()
    mqtt_status = check_mqtt_broker()
    fs_status = check_filesystem()

    # 整合结果
    checks = {
        "database": db_status,
        "redis": redis_status,
        "mqtt_broker": mqtt_status,
        "filesystem": fs_status,
    }

    # 整体判断：数据库必须 ok；其他非必选可以 disabled 但不能 error
    overall = "ready"
    error_checks = []
    for name, status in checks.items():
        if status.get("status") == "error":
            overall = "degraded" if name != "database" else "unhealthy"
            error_checks.append(name)

    result = {
        "status": overall,
        "checks": checks,
        "uptime_seconds": round(time_module.time() - _uptime_start),
    }
    if error_checks:
        result["unhealthy_checks"] = error_checks

    return success_response(result)


@router.get("/readyz")
async def readiness_short():
    """Kubernetes 兼容 readiness 探针别名"""
    return await readiness()


@router.get("/ping")
async def ping():
    return success_response({"message": "pong"})


@router.get("/devices/health")
def get_all_device_health(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """获取所有设备健康度"""
    devices = db.query(Device).all()
    return success_response({
        "items": [
            {
                "id": d.id,
                "code": d.code,
                "name": d.name,
                "type": d.type,
                "health_score": d.health_score,
                "status": d.status,
            }
            for d in devices
        ]
    })


@router.post("/devices/health/refresh")
async def refresh_health_scores(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """刷新所有设备健康度 (admin only, 卡69acc93c D2)"""
    results = health_monitor.calculate_all_health(db)
    alarms = health_monitor.check_and_create_alarms(db)
    return success_response({
        "message": f"更新了 {len(results)} 个设备健康度，创建了 {len(alarms)} 个告警",
        "devices": results,
        "alarms": alarms
    }, message="健康度刷新完成")


@router.get("/pipeline/health")
async def pipeline_health(user: User = Depends(require_platform_admin)):
    """数据管道健康状态"""
    from app.gateway.health_probe import check_gateway_health
    try:
        health = await check_gateway_health()
        return success_response(health)
    except Exception as e:
        logger.exception("数据管道健康检查异常")
        return success_response({
            "gateways": {"total": 0, "healthy": 0, "unhealthy": 0, "details": []},
            "throughput": {"total_requests": 0, "total_errors": 0, "total_bytes": 0, "requests_per_sec": 0, "error_rate": 0},
            "error": "数据管道健康检查异常"
        })


@router.get("/pipeline/stats")
async def pipeline_stats(user: User = Depends(require_platform_admin)):
    """数据管道吞吐量统计"""
    from app.gateway.health_probe import get_throughput_stats
    return success_response(get_throughput_stats())


@router.get("/gateway/health")
async def gateway_health(user: User = Depends(require_platform_admin)):
    """网关健康探针 (Phase33-Task3)

    返回已注册协议与数据管道吞吐量（含消息数/秒、平均延迟、错误率）。
    """
    from app.gateway.health_probe import check_gateway_health
    try:
        health = await check_gateway_health()
        return success_response(health)
    except Exception as e:
        logger.exception("网关健康检查异常")
        return success_response({
            "protocols": {"registered_count": 0, "registered": [], "device_type_mappings": {}},
            "throughput": {
                "total_requests": 0, "total_errors": 0, "total_bytes": 0,
                "requests_per_sec": 0, "avg_latency_ms": 0, "error_rate_pct": 0,
            },
            "error": "网关健康检查异常"
        })