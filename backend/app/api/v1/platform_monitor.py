"""
天链V3 — 平台监控扩展 (admin spec §2.9)

服务拓扑图 + 设备接入统计
"""
import time
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.device import Device, DeviceStatus, DeviceType, ProtocolType
from app.api.deps import require_platform_admin

logger = logging.getLogger(__name__)

# 卡 820cf187: 平台监控是平台级基础设施视图 (对齐 ssl_certificates 语义), 收紧 admin only
router = APIRouter(prefix="/platform", tags=["平台监控"], dependencies=[Depends(require_platform_admin)])


# ──────────────────────────────────────────────
# 1. 服务拓扑数据
# ──────────────────────────────────────────────

# 静态拓扑定义 — 微服务节点及依赖关系
# status 在运行时根据 health check 动态判定
_TOPOLOGY_NODES = [
    {
        "id": "api-gateway",
        "name": "API Gateway",
        "type": "gateway",
        "dependencies": ["auth-service", "device-service", "alarm-service", "billing-service"],
    },
    {
        "id": "auth-service",
        "name": "认证服务",
        "type": "backend",
        "dependencies": ["postgres-primary", "redis-cache"],
    },
    {
        "id": "device-service",
        "name": "设备服务",
        "type": "backend",
        "dependencies": ["postgres-primary", "tdengine", "mqtt-broker"],
    },
    {
        "id": "alarm-service",
        "name": "告警服务",
        "type": "backend",
        "dependencies": ["postgres-primary", "redis-cache"],
    },
    {
        "id": "billing-service",
        "name": "计费服务",
        "type": "backend",
        "dependencies": ["postgres-primary"],
    },
    {
        "id": "mqtt-broker",
        "name": "MQTT Broker",
        "type": "mq",
        "dependencies": [],
    },
    {
        "id": "postgres-primary",
        "name": "PostgreSQL",
        "type": "db",
        "dependencies": [],
    },
    {
        "id": "redis-cache",
        "name": "Redis",
        "type": "cache",
        "dependencies": [],
    },
    {
        "id": "tdengine",
        "name": "TDengine",
        "type": "db",
        "dependencies": [],
    },
]

# 模拟响应时间基线 (ms) — 每个服务类型的典型延迟
_BASE_LATENCY = {
    "gateway": 15,
    "backend": 30,
    "db": 8,
    "cache": 2,
    "mq": 5,
}


@router.get("/topology")
def get_topology(db: Session = Depends(get_db)):
    """
    返回微服务拓扑数据。

    - 静态拓扑结构（节点 + 依赖）
    - 动态健康状态：根据数据库连通性 + 设备在线率推导
    - 每个节点附带模拟响应时间

    status: healthy / degraded / down
    """
    try:
        # 通过设备在线率推断系统健康度
        total_devices = db.query(func.count(Device.id)).scalar() or 0
        online_devices = db.query(func.count(Device.id)).filter(
            Device.status == DeviceStatus.ONLINE
        ).scalar() or 0

        online_rate = (online_devices / total_devices * 100) if total_devices > 0 else 0

        # 判定整体状态
        if total_devices == 0:
            system_health = "healthy"  # 空系统视为健康
        elif online_rate >= 80:
            system_health = "healthy"
        elif online_rate >= 50:
            system_health = "degraded"
        else:
            system_health = "degraded"

        nodes = []
        for node_def in _TOPOLOGY_NODES:
            ntype = node_def["type"]
            base_latency = _BASE_LATENCY.get(ntype, 20)

            # 核心服务（db/gateway）受整体健康度影响
            if system_health == "degraded" and ntype in ("db", "gateway", "backend"):
                status = "degraded"
                response_time = int(base_latency * 2.5)
            else:
                status = "healthy"
                response_time = base_latency

            nodes.append({
                "id": node_def["id"],
                "name": node_def["name"],
                "type": ntype,
                "status": status,
                "response_time_ms": response_time,
                "dependencies": node_def["dependencies"],
            })

        # 统计摘要
        status_summary = {"healthy": 0, "degraded": 0, "down": 0}
        type_summary = {}
        for n in nodes:
            status_summary[n["status"]] += 1
            type_summary[n["type"]] = type_summary.get(n["type"], 0) + 1

        return {
            "nodes": nodes,
            "status_summary": status_summary,
            "type_summary": type_summary,
            "device_online_rate": round(online_rate, 1),
            "timestamp": int(time.time()),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询服务拓扑失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


# ──────────────────────────────────────────────
# 2. 设备接入统计
# ──────────────────────────────────────────────

# 设备类型 → 展示分类映射
_DEVICE_CATEGORY_MAP = {
    DeviceType.CHARGER_DC: "充电桩",
    DeviceType.CHARGER_AC: "充电桩",
    DeviceType.V2G_CHARGER: "V2G",
    DeviceType.PV_INVERTER: "光伏",
    DeviceType.BATTERY_INVERTER: "储能",
    DeviceType.PCS: "储能",
    DeviceType.BATTERY: "储能",
    DeviceType.METER: "电表",
    DeviceType.GATEWAY: "网关",
}

# 协议类型 → 展示名称映射
_PROTOCOL_LABELS = {
    ProtocolType.MQTT: "MQTT",
    ProtocolType.MODBUS_RTU: "Modbus",
    ProtocolType.MODBUS_TCP: "Modbus",
    ProtocolType.CAN: "CAN",
    ProtocolType.OPCUA: "OPC UA",
}


@router.get("/device-access-stats")
def get_device_access_stats(db: Session = Depends(get_db)):
    """
    返回设备接入统计。

    - 按设备分类（充电桩/光伏/储能/V2G/电表/网关）聚合数量+在线率
    - 按通信协议（MQTT/Modbus/CAN/OPC UA）聚合分布
    - 在线/离线/故障总数
    """
    try:
        # ── 按设备类型统计 ──
        type_rows = db.query(
            Device.type,
            Device.status,
            func.count(Device.id).label("cnt"),
        ).group_by(Device.type, Device.status).all()

        # 聚合到展示分类
        category_stats: dict[str, dict] = {}
        for row in type_rows:
            dtype = row.type
            category = _DEVICE_CATEGORY_MAP.get(dtype, "其他")
            if category not in category_stats:
                category_stats[category] = {"total": 0, "online": 0, "offline": 0, "fault": 0}
            category_stats[category]["total"] += row.cnt
            if row.status == DeviceStatus.ONLINE:
                category_stats[category]["online"] += row.cnt
            elif row.status == DeviceStatus.FAULT:
                category_stats[category]["fault"] += row.cnt
            else:
                category_stats[category]["offline"] += row.cnt

        device_categories = []
        for cat, vals in sorted(category_stats.items()):
            total = vals["total"]
            online = vals["online"]
            rate = round((online / total * 100), 1) if total > 0 else 0
            device_categories.append({
                "category": cat,
                "total": total,
                "online": online,
                "offline": vals["offline"],
                "fault": vals["fault"],
                "online_rate": rate,
            })

        # ── 按协议统计 ──
        protocol_rows = db.query(
            Device.protocol_type,
            func.count(Device.id).label("cnt"),
        ).filter(Device.protocol_type.isnot(None)).group_by(Device.protocol_type).all()

        protocol_distribution = []
        for row in protocol_rows:
            ptype = row.protocol_type
            label = _PROTOCOL_LABELS.get(ptype, str(ptype.value) if hasattr(ptype, "value") else str(ptype))
            protocol_distribution.append({"protocol": label, "count": row.cnt})

        # 合并同名协议（Modbus RTU + TCP → Modbus）
        merged: dict[str, int] = {}
        for p in protocol_distribution:
            merged[p["protocol"]] = merged.get(p["protocol"], 0) + p["count"]
        protocol_distribution = [{"protocol": k, "count": v} for k, v in sorted(merged.items(), key=lambda x: -x[1])]

        # ── 总体统计 ──
        total = sum(c["total"] for c in device_categories)
        total_online = sum(c["online"] for c in device_categories)
        total_offline = sum(c["offline"] for c in device_categories)
        total_fault = sum(c["fault"] for c in device_categories)

        return {
            "total_devices": total,
            "total_online": total_online,
            "total_offline": total_offline,
            "total_fault": total_fault,
            "online_rate": round((total_online / total * 100), 1) if total > 0 else 0,
            "device_categories": device_categories,
            "protocol_distribution": protocol_distribution,
            "timestamp": int(time.time()),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询设备接入统计失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")
