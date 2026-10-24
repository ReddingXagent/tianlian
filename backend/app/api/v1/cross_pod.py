"""
跨 Pod 查询接口

路由:
- POST /api/v1/cross/query     → 跨Pod聚合查询
      body: {"station_ids": [1, 2, 3], "query_type": "overview"}

工作流程:
1. 用 StationRouter 查出每个 station 归属的 Pod
2. 按 Pod 分组
3. 本地查询走本地 DB
4. 远程查询走 HTTP 调用（使用 httpx.AsyncClient）
5. 合并结果返回

Phase 2: Pod 间通信层
"""
import asyncio
import logging
from typing import List, Dict, Any
from collections import defaultdict
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db, get_async_db
from app.core.station_router import get_station_router
from app.core.pod_security import verify_pod_comm_secret, POD_SECRET_HEADER
from app.core.rate_limit import limit_pod_comm
from app.core.url_safety import validate_external_url
from app.models.station import Station
from app.models.device import Device

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cross", tags=["跨Pod查询"])

# 远程请求超时（秒）
REMOTE_TIMEOUT = 5.0


# ========== 请求模型 ==========

class CrossPodQueryRequest(BaseModel):
    """跨 Pod 查询请求"""
    station_ids: List[int] = Field(..., description="场站 ID 列表")
    query_type: str = Field(default="overview", description="查询类型: overview/devices/stats")
    include_details: bool = Field(default=False, description="是否包含详细信息")


class CrossPodQueryResponse(BaseModel):
    """跨 Pod 查询响应"""
    query_type: str
    total_stations: int
    results: List[Dict[str, Any]]
    errors: List[Dict[str, str]]
    pods_involved: List[str]


# ========== API 端点 ==========

@router.post("/query", dependencies=[Depends(limit_pod_comm)])
async def cross_pod_query(
    request: CrossPodQueryRequest,
    _secret: None = Depends(verify_pod_comm_secret),
    db: AsyncSession = Depends(get_async_db),
):
    """
    跨 Pod 聚合查询
    
    1. 用 StationRouter 查出每个 station 归属的 Pod
    2. 按 Pod 分组
    3. 本地查询走本地 DB
    4. 远程查询走 HTTP 调用（使用 httpx.AsyncClient）
    5. 合并结果返回
    
    Args:
        station_ids: 场站 ID 列表
        query_type: 查询类型 (overview/devices/stats)
        include_details: 是否包含详细信息
    """
    station_router = get_station_router()
    
    # 按 Pod 分组场站
    pods: Dict[str, List[int]] = defaultdict(list)
    for sid in request.station_ids:
        route = station_router.route_station(sid)
        pods[route["pod_id"]].append(sid)
    
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    pods_involved = list(pods.keys())
    
    # 本地查询
    local_pod_id = station_router.pod_id
    local_ids = pods.get(local_pod_id, [])
    
    if local_ids:
        try:
            local_results = await query_local(
                local_ids, request.query_type, request.include_details, db
            )
            results.extend(local_results)
            logger.info("本地查询完成: %d 个场站", len(local_ids))
        except Exception as e:
            logger.error("本地查询失败: %s", e)
            errors.append({
                "pod_id": local_pod_id,
                "error": "本地查询失败",
                "station_ids": str(local_ids),
            })
    
    # 远程查询（单Pod模式下跳过）
    if not station_router.local_only:
        
        remote_tasks = []
        task_pod_ids = []  # 与 remote_tasks 按索引对应的 pod_id (coroutine 无 pod_id 属性)
        for pod_id, sids in pods.items():
            if pod_id == local_pod_id:
                continue  # 本地已处理
            
            pod_info = station_router.get_pod_info(pod_id)
            if not pod_info:
                errors.append({
                    "pod_id": pod_id,
                    "error": "Pod 未注册或不可达",
                    "station_ids": str(sids),
                })
                continue
            
            endpoint = pod_info.get("endpoint")
            if not endpoint:
                errors.append({
                    "pod_id": pod_id,
                    "error": "Pod endpoint 未配置",
                    "station_ids": str(sids),
                })
                continue
            
            remote_tasks.append(query_remote(
                endpoint, sids, request.query_type, request.include_details, pod_id
            ))
            task_pod_ids.append(pod_id)
        
        # 并发执行远程查询
        if remote_tasks:
            remote_results = await asyncio.gather(*remote_tasks, return_exceptions=True)
            
            for i, result in enumerate(remote_results):
                if isinstance(result, Exception):
                    # 单个 Pod 失败不影响整体
                    pod_id = task_pod_ids[i]
                    errors.append({
                        "pod_id": pod_id,
                        "error": str(result),
                    })
                    logger.warning("远程 Pod %s 查询失败: %s", pod_id, result)
                elif isinstance(result, dict) and "results" in result:
                    results.extend(result["results"])
                    logger.info("远程 Pod %s 查询完成: %d 结果", 
                               result.get("pod_id"), len(result["results"]))
    
    return CrossPodQueryResponse(
        query_type=request.query_type,
        total_stations=len(request.station_ids),
        results=results,
        errors=errors,
        pods_involved=pods_involved
    )


# ========== 查询函数 ==========

async def query_local(
    station_ids: List[int],
    query_type: str,
    include_details: bool,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    本地数据库查询 (异步, 卡52f731ac)

    Args:
        station_ids: 场站 ID 列表
        query_type: 查询类型
        include_details: 是否包含详情
        db: 异步数据库会话 (AsyncSession)

    Returns:
        查询结果列表

    卡 147a4231: 批量预取消除逐站 N+1 —— 场站/设备计数/设备明细各一次 IN 查询,
    内存按 station_ids 输入顺序组装, 缺失场站 skip, 契约不变。
    """
    results = []
    if not station_ids:
        return results

    def _v(x):
        return x.value if hasattr(x, "value") else x

    # 1. 场站批量取
    stations = (await db.execute(
        select(Station).where(Station.id.in_(station_ids))
    )).scalars().all()
    station_by_id = {s.id: s for s in stations}

    # 2. 设备数据按 query_type 批量预取
    count_by_sid: Dict[int, int] = {}
    devices_by_sid: Dict[int, List[Device]] = defaultdict(list)

    if query_type == "overview":
        rows = (await db.execute(
            select(Device.station_id, func.count(Device.id))
            .where(Device.station_id.in_(station_ids))
            .group_by(Device.station_id)
        )).all()
        count_by_sid = {sid: cnt for sid, cnt in rows}

        if include_details:
            for d in (await db.execute(
                select(Device).where(Device.station_id.in_(station_ids))
            )).scalars().all():
                devices_by_sid[d.station_id].append(d)

    elif query_type == "devices":
        for d in (await db.execute(
            select(Device).where(Device.station_id.in_(station_ids))
        )).scalars().all():
            devices_by_sid[d.station_id].append(d)

    elif query_type == "stats":
        # online/offline/fault 三次计数合并为一次 group_by(station_id, status)
        rows = (await db.execute(
            select(Device.station_id, Device.status, func.count(Device.id))
            .where(Device.station_id.in_(station_ids))
            .group_by(Device.station_id, Device.status)
        )).all()
        status_count: Dict[int, Dict[str, int]] = defaultdict(
            lambda: {"online": 0, "offline": 0, "fault": 0}
        )
        for sid, status, cnt in rows:
            status_count[sid][_v(status)] = cnt

    # 3. 按输入顺序组装
    for sid in station_ids:
        station = station_by_id.get(sid)
        if not station:
            continue

        result = {
            "station_id": sid,
            "station_name": station.name,
            "station_code": station.code,
            "pod_id": "local",
        }

        if query_type == "overview":
            # 场站概览
            result.update({
                "status": _v(station.status),
                "health_score": station.health_score,
                "device_count": count_by_sid.get(sid, 0),
                "address": station.address,
            })

            if include_details:
                # 包含设备详情 (保持每站最多 20 条语义)
                result["devices"] = [
                    {
                        "id": d.id,
                        "name": d.name,
                        "type": _v(d.type),
                        "status": _v(d.status),
                    }
                    for d in devices_by_sid.get(sid, [])[:20]
                ]

        elif query_type == "devices":
            # 设备列表
            devices = devices_by_sid.get(sid, [])
            result["devices"] = [
                {
                    "id": d.id,
                    "name": d.name,
                    "sn": d.sn,
                    "type": _v(d.type),
                    "status": _v(d.status),
                    "health_score": d.health_score,
                }
                for d in devices
            ]
            result["device_count"] = len(devices)

        elif query_type == "stats":
            # 统计数据
            cnt = status_count.get(sid, {})
            online_devices = cnt.get("online", 0)
            offline_devices = cnt.get("offline", 0)
            fault_devices = cnt.get("fault", 0)

            result.update({
                "total_devices": online_devices + offline_devices + fault_devices,
                "online_devices": online_devices,
                "offline_devices": offline_devices,
                "fault_devices": fault_devices,
                "health_score": station.health_score,
            })

        results.append(result)

    return results


async def query_remote(
    endpoint: str,
    station_ids: List[int],
    query_type: str,
    include_details: bool,
    pod_id: str
) -> Dict[str, Any]:
    """
    远程 Pod 查询
    
    Args:
        endpoint: Pod 访问地址
        station_ids: 场站 ID 列表
        query_type: 查询类型
        include_details: 是否包含详情
        pod_id: 目标 Pod ID
        
    Returns:
        查询结果字典
    """
    import httpx

    # SSRF 出站兜底 (卡 bab27c02): endpoint 可能来自 Redis 注册表(绕过 register
    # 侧校验的写入路径),拼 URL 前再校验一次,禁止裸 requests 打内网。
    # 保存侧校验见 PodRegisterRequest._validate_endpoint,双端同款语义。
    validate_external_url(endpoint)

    url = f"{endpoint}/api/v1/cross/query"
    payload = {
        "station_ids": station_ids,
        "query_type": query_type,
        "include_details": include_details,
    }
    
    # 携带 X-Pod-Secret 自证 Pod 间 RPC 身份 (卡69acc93c): 远程 /cross/query 已强制
    # 共享密钥校验, 不带头会被远程 Pod 403 → 多 Pod 聚合查询全线失败。本地端点校验
    # 通过方可到此, secret 必已配置; 兜底空 dict 兼容未配置场景 (虽本地会先 403)。
    secret = (settings.POD_COMM_SHARED_SECRET or "").strip()
    rpc_headers = {POD_SECRET_HEADER: secret} if secret else {}
    try:
        async with httpx.AsyncClient(timeout=REMOTE_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=rpc_headers)
            response.raise_for_status()
            data = response.json()
            
            # 标记结果来自哪个 Pod
            for result in data.get("results", []):
                result["pod_id"] = pod_id
            
            return {
                "pod_id": pod_id,
                "results": data.get("results", []),
            }
    
    except httpx.TimeoutException:
        raise Exception(f"Pod {pod_id} 超时 ({REMOTE_TIMEOUT}s)")
    except httpx.HTTPStatusError as e:
        raise Exception(f"Pod {pod_id} HTTP 错误: {e.response.status_code}")
    except Exception as e:
        logger.exception("Pod %s 请求失败", pod_id)
        raise Exception(f"Pod {pod_id} 请求失败")


# ========== 内部接口（供其他 Pod 调用） ==========

@router.post("/internal/query", dependencies=[Depends(limit_pod_comm)])
async def internal_cross_query(
    request: CrossPodQueryRequest,
    _secret: None = Depends(verify_pod_comm_secret),
    db: AsyncSession = Depends(get_async_db),
):
    """
    内部跨 Pod 查询接口（供其他 Pod 调用）

    仅返回本地数据，不发起远程调用

    Args:
        station_ids: 场站 ID 列表
        query_type: 查询类型
        include_details: 是否包含详情
    """
    # 仅查询本地数据
    results = await query_local(
        request.station_ids,
        request.query_type,
        request.include_details,
        db
    )
    
    return {
        "pod_id": get_station_router().pod_id,
        "results": results,
        "station_ids": request.station_ids,
    }


# ========== 批量路由查询 ==========

@router.post("/routes", dependencies=[Depends(limit_pod_comm)])
async def batch_route_query(
    request: CrossPodQueryRequest,
    _secret: None = Depends(verify_pod_comm_secret),
):
    """
    批量路由查询
    
    仅返回场站归属的 Pod 信息，不执行实际查询
    
    Args:
        station_ids: 场站 ID 列表
    """
    station_router = get_station_router()
    
    routes = {}
    for sid in request.station_ids:
        route = station_router.route_station(sid)
        routes[sid] = route
    
    return {
        "total": len(routes),
        "routes": routes,
    }