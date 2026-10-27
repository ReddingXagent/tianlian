"""
Pod 健康检查与注册 API

路由:
- GET  /api/v1/pod/health        → 本Pod健康信息
- POST /api/v1/pod/register      → 向全局路由中心注册本Pod
- POST /api/v1/pod/heartbeat     → 心跳保活
- GET  /api/v1/pod/routes        → 本Pod负责的场站列表
- GET  /api/v1/pod/stations      → 本Pod所有场站聚合统计

Phase 2: Pod 间通信层
"""
import time
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func

# psutil 可选依赖
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

from app.core.database import get_db
from app.core.station_router import get_station_router
from app.core.timing_log import emit_write_timing
from app.core.config import settings
from app.core.pod_security import verify_pod_comm_secret, validate_pod_id
from app.core.url_safety import validate_external_url
from app.core.rate_limit import limit_pod_comm
from app.models.station import Station
from app.models.device import Device

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pod", tags=["Pod管理"])


# ========== 请求模型 ==========

class PodRegisterRequest(BaseModel):
    """Pod 注册请求"""
    pod_id: str = Field(..., description="Pod ID")
    region_id: str = Field(..., description="区域 ID")
    endpoint: str = Field(..., description="访问地址")
    version: str = Field(default="3.0.0", description="版本号")

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint(cls, v: str) -> str:
        """SSRF 防护 (卡 bab27c02): endpoint 会被 cross_pod 出站主动请求,
        必须指向公网 http/https 端点。

        取舍说明: url_safety 无白名单机制,内网多 Pod 部署(10.x/192.168.x)
        需公网可达地址或经反向代理暴露;出站侧 _query_remote 有同款兜底校验。
        """
        validate_external_url(v)
        return v


class PodHeartbeatRequest(BaseModel):
    """Pod 心跳请求"""
    pod_id: str = Field(..., description="Pod ID")
    load: Optional[Dict[str, Any]] = Field(default=None, description="负载信息")


# ========== 响应模型 ==========

class PodHealthResponse(BaseModel):
    """Pod 健康响应"""
    pod_id: str
    region_id: str
    status: str = "healthy"
    endpoint: str
    version: str
    load: Dict[str, Any]
    uptime_seconds: int


class PodRoutesResponse(BaseModel):
    """Pod 场站路由响应"""
    pod_id: str
    region_id: str
    station_count: int
    stations: List[int]


class PodStationsStatsResponse(BaseModel):
    """Pod 场站聚合统计响应"""
    pod_id: str
    region_id: str
    stations: Dict[str, Any]
    devices: Dict[str, Any]


# ========== API 端点 ==========

@router.get("/health", dependencies=[Depends(limit_pod_comm)])
def get_pod_health(_secret: None = Depends(verify_pod_comm_secret)):
    """
    获取本 Pod 健康信息
    
    返回:
    - pod_id: Pod ID
    - region_id: 区域 ID
    - status: 健康状态
    - endpoint: 访问地址
    - version: 版本号
    - load: 负载信息（场站数/设备数/内存）
    - uptime_seconds: 运行时间
    """
    station_router = get_station_router()
    
    # 获取系统负载信息
    try:
        if PSUTIL_AVAILABLE:
            memory = psutil.virtual_memory()
            memory_usage_pct = memory.percent
            
            # 获取进程启动时间（近似 uptime）
            process = psutil.Process()
            uptime_seconds = int(time.time() - process.create_time())
        else:
            memory_usage_pct = 0
            uptime_seconds = 0
    except Exception:
        memory_usage_pct = 0
        uptime_seconds = 0
    
    # 从数据库获取场站/设备数量（如果可用）
    try:
        db_gen = get_db()
        db = next(db_gen)
        station_count = db.query(func.count(Station.id)).scalar() or 0
        device_count = db.query(func.count(Device.id)).scalar() or 0
        db_gen.close()
    except Exception:
        station_count = 0
        device_count = 0
    
    return PodHealthResponse(
        pod_id=station_router.pod_id,
        region_id=station_router.region_id,
        status="healthy",
        endpoint=station_router.endpoint,
        version=settings.APP_VERSION,
        load={
            "stations": station_count,
            "devices": device_count,
            "memory_usage_pct": memory_usage_pct,
        },
        uptime_seconds=uptime_seconds
    )


@router.post("/register", dependencies=[Depends(limit_pod_comm)])
async def register_pod(
    request: PodRegisterRequest,
    _secret: None = Depends(verify_pod_comm_secret),
):
    """
    向全局路由中心注册本 Pod

    注意: 单Pod模式下此操作无效

    Args:
        pod_id: Pod ID
        region_id: 区域 ID
        endpoint: 访问地址
        version: 版本号
    """
    # pod_id 格式校验 (卡69acc93c): 防 ../../、空格、$() 注入 Redis key/日志
    validate_pod_id(request.pod_id)
    station_router = get_station_router()
    
    if station_router.local_only:
        return {
            "success": False,
            "message": "单Pod模式不支持 Pod 注册",
            "pod_id": station_router.pod_id,
        }
    
    # 多Pod模式：注册到 Redis
    success = station_router.register_pod(
        pod_id=request.pod_id,
        region_id=request.region_id,
        endpoint=request.endpoint,
        version=request.version
    )
    
    if success:
        return {
            "success": True,
            "message": "Pod 注册成功",
            "pod_id": request.pod_id,
        }
    else:
        raise HTTPException(status_code=500, detail="Pod 注册失败")


@router.post("/heartbeat", dependencies=[Depends(limit_pod_comm)])
async def pod_heartbeat(
    request: PodHeartbeatRequest,
    _secret: None = Depends(verify_pod_comm_secret),
):
    """
    Pod 心跳保活

    用于定期向路由中心报告存活状态
    推荐间隔: 30秒

    Args:
        pod_id: Pod ID
        load: 可选的负载信息
    """
    # pod_id 格式校验 (卡69acc93c): 防 Redis key/日志注入
    validate_pod_id(request.pod_id)
    # 卡 f78a8e44: heartbeat 无 auth / 无 DB, 写操作为 Redis set。全程函数内
    # perf_counter 分段: parse(前置+读) / insert(Redis 写); auth_ms / commit_ms 记 0。
    t_start = time.perf_counter()

    def _emit(parse_end: float, insert_start: float, insert_end: float) -> None:
        emit_write_timing(
            "pod/heartbeat", 1,
            auth_ms=0.0,
            parse_ms=(parse_end - t_start) * 1000,
            insert_ms=(insert_end - insert_start) * 1000,
            commit_ms=0.0,
            total_ms=(insert_end - t_start) * 1000,
        )

    station_router = get_station_router()
    
    if station_router.local_only:
        now = time.perf_counter()
        _emit(now, now, now)
        return {
            "success": True,
            "message": "单Pod模式心跳（无实际操作）",
            "pod_id": station_router.pod_id,
        }
    
    # 多Pod模式：更新 Redis 中的 Pod 信息
    try:
        # 更新 Pod 注册信息中的 last_heartbeat
        pod_info = station_router.get_pod_info(request.pod_id)
        if pod_info:
            pod_info["last_heartbeat"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if request.load:
                pod_info["load"] = request.load
            
            # 写回 Redis
            import json
            key = f"tianlian:route:pod:registry:{request.pod_id}"
            t_insert_start = time.perf_counter()
            if station_router.redis:
                station_router.redis.set(key, json.dumps(pod_info))
            t_insert_end = time.perf_counter()
            _emit(t_insert_start, t_insert_start, t_insert_end)
            
            return {
                "success": True,
                "message": "心跳更新成功",
                "pod_id": request.pod_id,
            }
        else:
            # Pod 未注册，自动注册
            t_insert_start = time.perf_counter()
            station_router.register_pod(
                pod_id=request.pod_id,
                region_id=station_router.region_id,
                endpoint=station_router.endpoint,
            )
            t_insert_end = time.perf_counter()
            _emit(t_insert_start, t_insert_start, t_insert_end)
            return {
                "success": True,
                "message": "Pod 自动注册并心跳成功",
                "pod_id": request.pod_id,
            }
    except Exception as e:
        logger.error("心跳更新失败: %s", e)
        now = time.perf_counter()
        _emit(now, now, now)
        return {
            "success": False,
            "message": "心跳更新失败",
            "pod_id": request.pod_id,
        }


@router.get("/routes", dependencies=[Depends(limit_pod_comm)])
async def get_pod_routes(_secret: None = Depends(verify_pod_comm_secret)):
    """
    获取本 Pod 负责的场站路由列表
    
    返回:
    - pod_id: Pod ID
    - region_id: 区域 ID
    - station_count: 场站数量
    - stations: 场站 ID 列表
    """
    station_router = get_station_router()
    
    # 从路由器获取本 Pod 场站列表
    station_ids = station_router.list_by_pod(station_router.pod_id)
    
    return PodRoutesResponse(
        pod_id=station_router.pod_id,
        region_id=station_router.region_id,
        station_count=len(station_ids),
        stations=station_ids
    )


@router.get("/stations", dependencies=[Depends(limit_pod_comm)])
def get_pod_stations_stats(
    _secret: None = Depends(verify_pod_comm_secret),
    db: Session = Depends(get_db),
):
    """
    获取本 Pod 所有场站的聚合统计
    
    返回:
    - pod_id: Pod ID
    - region_id: 区域 ID
    - stations: 场站统计（总数/正常/维护/关闭）
    - devices: 设备统计（总数/在线/离线/故障）
    """
    station_router = get_station_router()
    
    # 场站统计
    total_stations = db.query(func.count(Station.id)).scalar() or 0
    normal_stations = db.query(func.count(Station.id)).filter(
        Station.status == "normal"
    ).scalar() or 0
    maintenance_stations = db.query(func.count(Station.id)).filter(
        Station.status == "maintenance"
    ).scalar() or 0
    closed_stations = db.query(func.count(Station.id)).filter(
        Station.status == "closed"
    ).scalar() or 0
    
    # 设备统计
    total_devices = db.query(func.count(Device.id)).scalar() or 0
    online_devices = db.query(func.count(Device.id)).filter(
        Device.status == "online"
    ).scalar() or 0
    offline_devices = db.query(func.count(Device.id)).filter(
        Device.status == "offline"
    ).scalar() or 0
    fault_devices = db.query(func.count(Device.id)).filter(
        Device.status == "fault"
    ).scalar() or 0
    
    return PodStationsStatsResponse(
        pod_id=station_router.pod_id,
        region_id=station_router.region_id,
        stations={
            "total": total_stations,
            "normal": normal_stations,
            "maintenance": maintenance_stations,
            "closed": closed_stations,
        },
        devices={
            "total": total_devices,
            "online": online_devices,
            "offline": offline_devices,
            "fault": fault_devices,
        }
    )


@router.get("/list", dependencies=[Depends(limit_pod_comm)])
async def list_all_pods(_secret: None = Depends(verify_pod_comm_secret)):
    """
    列出所有已注册的 Pod
    
    返回所有 Pod 的基本信息（用于跨 Pod 发现）
    """
    station_router = get_station_router()
    pods = station_router.list_all_pods()
    
    return {
        "count": len(pods),
        "pods": pods,
    }


@router.get("/info/{pod_id}", dependencies=[Depends(limit_pod_comm)])
async def get_pod_info(pod_id: str, _secret: None = Depends(verify_pod_comm_secret)):
    """
    获取指定 Pod 的详细信息
    
    Args:
        pod_id: Pod ID
    """
    station_router = get_station_router()
    pod_info = station_router.get_pod_info(pod_id)
    
    if pod_info:
        return pod_info
    else:
        raise HTTPException(status_code=404, detail=f"Pod {pod_id} 未找到")