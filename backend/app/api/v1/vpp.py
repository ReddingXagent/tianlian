"""
虚拟电厂(VPP)调度优化 API
多站点协同 + 电网互动响应
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from app.services.vpp import (
    get_vpp_coordinator,
    ResourceType,
    DispatchMode,
    GridSignalType,
    GridSignal,
    get_vpp_lp_optimizer,
)
from app.services.vpp.auto_scheduler import get_vpp_auto_scheduler
from app.middleware.permission import require_write_permission
from app.api.deps import require_platform_admin

logger = logging.getLogger(__name__)

# 越权高危修复（审计 #2）: coordinator 为进程级全局单例，无 team 归属，
# operator 可注册/篡改/注销全平台任意站点资源、clear_all 清空平台 VPP 状态、
# 启停平台自动调度器。全模块端点（含返回全平台聚合数据的 GET）一律收紧
# platform admin，模式对齐 protocol_instances / ssl_certificates（require_platform_admin）。
router = APIRouter(dependencies=[
    Depends(require_write_permission("device:edit")),
    Depends(require_platform_admin),
])


# ─── 请求/响应模型 ───

class StationRegisterRequest(BaseModel):
    """站点注册请求"""
    station_id: str = Field(..., description="站点ID")
    station_name: str = Field(..., description="站点名称")
    total_pv_kw: float = Field(0, ge=0, description="光伏装机容量(kW)")
    total_battery_kwh: float = Field(0, ge=0, description="储能容量(kWh)")
    total_ev_chargers: int = Field(0, ge=0, description="充电桩数量")
    current_load_kw: float = Field(0, description="当前负荷(kW)")
    current_pv_output_kw: float = Field(0, description="当前光伏出力(kW)")
    current_battery_soc: float = Field(0.5, description="储能SOC(0-1)")
    available_dispatch_kw: float = Field(0, description="可调度容量(kW)")


class ResourceRegisterRequest(BaseModel):
    """资源注册请求"""
    resource_id: str = Field(..., description="资源ID")
    resource_type: str = Field(..., description="资源类型: pv/battery/ev/load")
    station_id: str = Field(..., description="所属站点ID")
    rated_power_kw: float = Field(0, description="额定功率(kW)")
    current_power_kw: float = Field(0, description="当前功率(kW)")
    available_power_kw: float = Field(0, description="可调度功率(kW)")
    soc: Optional[float] = Field(None, description="储能SOC(0-1)")
    efficiency: float = Field(0.95, description="转换效率")
    priority: int = Field(5, description="调度优先级(1最高)")
    cost_per_kwh: float = Field(0, ge=0, description="边际成本(元/kWh)")


class GridSignalRequest(BaseModel):
    """电网信号请求"""
    signal_type: str = Field(..., description="信号类型: price/demand_response/frequency_regulation/peak_alert/emergency")
    target_power_kw: Optional[float] = Field(None, description="目标功率(kW)")
    duration_min: Optional[int] = Field(None, description="持续时间(分钟)")
    price_per_kwh: Optional[float] = Field(None, ge=0, description="电价(元/kWh)")
    reward_per_kwh: Optional[float] = Field(None, ge=0, description="响应奖励(元/kWh)")
    penalty_per_kwh: Optional[float] = Field(None, ge=0, description="未响应惩罚(元/kWh)")
    urgency: float = Field(0.5, description="紧急程度(0-1)")


class DispatchRequest(BaseModel):
    """调度请求"""
    mode: str = Field("auto", description="调度模式: auto/economic/peak_shaving/demand_response/multi_station")
    grid_signal: Optional[GridSignalRequest] = Field(None, description="电网信号(需求响应时必填)")
    peak_threshold_kw: Optional[float] = Field(None, description="峰值阈值(削峰模式)")


class LPDispatchRequest(BaseModel):
    """LP优化调度请求"""
    target_power_kw: float = Field(0, description="目标功率(kW), 正=放电, 负=充电, 0=自动")
    duration_min: int = Field(15, ge=5, le=240, description="持续时间(分钟)")
    mode: str = Field("economic", description="调度模式: economic/peak_shaving/demand_response/grid_support")
    peak_threshold_kw: Optional[float] = Field(None, description="削峰阈值(kW)")
    dr_reward_per_kwh: float = Field(0.5, ge=0, le=5, description="需求响应奖励(元/kWh)")


class StationStatusUpdateRequest(BaseModel):
    """站点状态更新"""
    current_load_kw: Optional[float] = None
    current_pv_output_kw: Optional[float] = None
    current_battery_soc: Optional[float] = None
    available_dispatch_kw: Optional[float] = None
    online: Optional[bool] = None


# ─── API 端点 ───

@router.get("/capacity", summary="获取VPP聚合容量")
async def get_vpp_capacity():
    """获取VPP聚合容量总览"""
    coordinator = get_vpp_coordinator()
    return {
        "success": True,
        "data": coordinator.get_aggregate_capacity(),
    }


@router.get("/stations", summary="获取所有站点状态")
async def list_stations():
    """获取VPP管理的所有站点状态"""
    coordinator = get_vpp_coordinator()
    stations = []
    for s in coordinator.stations.values():
        stations.append({
            'station_id': s.station_id,
            'station_name': s.station_name,
            'total_pv_kw': s.total_pv_kw,
            'total_battery_kwh': s.total_battery_kwh,
            'total_ev_chargers': s.total_ev_chargers,
            'current_load_kw': s.current_load_kw,
            'current_pv_output_kw': s.current_pv_output_kw,
            'current_battery_soc': s.current_battery_soc,
            'available_dispatch_kw': s.available_dispatch_kw,
            'online': s.online,
        })
    return {
        "success": True,
        "data": stations,
    }


@router.post("/stations", summary="注册站点")
async def register_station(req: StationRegisterRequest):
    """向VPP注册新站点"""
    from app.services.vpp.dispatch_optimizer import StationStatus
    coordinator = get_vpp_coordinator()
    station = StationStatus(
        station_id=req.station_id,
        station_name=req.station_name,
        total_pv_kw=req.total_pv_kw,
        total_battery_kwh=req.total_battery_kwh,
        total_ev_chargers=req.total_ev_chargers,
        current_load_kw=req.current_load_kw,
        current_pv_output_kw=req.current_pv_output_kw,
        current_battery_soc=req.current_battery_soc,
        available_dispatch_kw=req.available_dispatch_kw,
    )
    coordinator.register_station(station)
    return {
        "success": True,
        "message": f"站点 {req.station_name} 已注册",
        "data": {"station_id": req.station_id},
    }


@router.put("/stations/{station_id}", summary="更新站点状态")
async def update_station_status(station_id: str, req: StationStatusUpdateRequest):
    """更新站点实时状态"""
    coordinator = get_vpp_coordinator()
    if station_id not in coordinator.stations:
        raise HTTPException(status_code=404, detail=f"站点 {station_id} 不存在")
    
    updates = {k: v for k, v in req.dict().items() if v is not None}
    coordinator.update_station_status(station_id, **updates)
    return {
        "success": True,
        "message": f"站点 {station_id} 状态已更新",
    }


@router.delete("/stations/{station_id}", summary="注销站点")
async def unregister_station(station_id: str):
    """从VPP注销站点"""
    coordinator = get_vpp_coordinator()
    if station_id not in coordinator.stations:
        raise HTTPException(status_code=404, detail=f"站点 {station_id} 不存在")
    coordinator.unregister_station(station_id)
    return {
        "success": True,
        "message": f"站点 {station_id} 已注销",
    }


@router.post("/resources", summary="注册资源")
async def register_resource(req: ResourceRegisterRequest):
    """向VPP注册可调度资源"""
    from app.services.vpp.dispatch_optimizer import ResourceCapability
    coordinator = get_vpp_coordinator()
    
    try:
        res_type = ResourceType(req.resource_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效资源类型: {req.resource_type}")
    
    resource = ResourceCapability(
        resource_id=req.resource_id,
        resource_type=res_type,
        station_id=req.station_id,
        rated_power_kw=req.rated_power_kw,
        current_power_kw=req.current_power_kw,
        available_power_kw=req.available_power_kw,
        soc=req.soc,
        efficiency=req.efficiency,
        priority=req.priority,
        cost_per_kwh=req.cost_per_kwh,
    )
    coordinator.register_resource(resource)
    return {
        "success": True,
        "message": f"资源 {req.resource_id} 已注册",
    }


@router.post("/dispatch", summary="执行调度")
async def execute_dispatch(req: DispatchRequest):
    """
    执行VPP调度
    - auto: 自动选择最优模式
    - economic: 经济调度(峰谷套利)
    - peak_shaving: 削峰填谷
    - demand_response: 需求响应(需提供grid_signal)
    - multi_station: 多站点协同
    """
    coordinator = get_vpp_coordinator()
    
    # 解析电网信号
    grid_signal = None
    if req.grid_signal:
        try:
            signal_type = GridSignalType(req.grid_signal.signal_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效信号类型: {req.grid_signal.signal_type}")
        
        grid_signal = GridSignal(
            signal_type=signal_type,
            timestamp=datetime.now(timezone.utc),
            target_power_kw=req.grid_signal.target_power_kw,
            duration_min=req.grid_signal.duration_min,
            price_per_kwh=req.grid_signal.price_per_kwh,
            reward_per_kwh=req.grid_signal.reward_per_kwh,
            penalty_per_kwh=req.grid_signal.penalty_per_kwh,
            urgency=req.grid_signal.urgency,
        )
    
    # 执行调度
    try:
        if req.mode == "auto":
            plan = coordinator.auto_dispatch(grid_signal)
        elif req.mode == "economic":
            plan = coordinator.dispatch_economic()
        elif req.mode == "peak_shaving":
            plan = coordinator.dispatch_peak_shaving(req.peak_threshold_kw)
        elif req.mode == "demand_response":
            if not grid_signal:
                raise HTTPException(status_code=400, detail="需求响应模式需要提供grid_signal")
            plan = coordinator.dispatch_demand_response(grid_signal)
        elif req.mode == "multi_station":
            plan = coordinator.dispatch_multi_station(grid_signal)
        else:
            raise HTTPException(status_code=400, detail=f"无效调度模式: {req.mode}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("调度执行失败")
        raise HTTPException(status_code=500, detail="调度执行失败")
    
    return {
        "success": True,
        "data": {
            "plan_id": plan.plan_id,
            "mode": plan.mode.value,
            "trigger": plan.trigger,
            "stations_involved": plan.stations_involved,
            "total_dispatch_kw": round(plan.total_dispatch_kw, 2),
            "estimated_revenue": round(plan.estimated_revenue, 2),
            "estimated_cost": round(plan.estimated_cost, 2),
            "net_profit": round(plan.net_profit, 2),
            "commands": [
                {
                    "resource_id": c.resource_id,
                    "station_id": c.station_id,
                    "resource_type": c.resource_type.value,
                    "target_power_kw": round(c.target_power_kw, 2),
                    "duration_min": c.duration_min,
                    "priority": c.priority,
                    "estimated_revenue": round(c.estimated_revenue, 2),
                    "estimated_cost": round(c.estimated_cost, 2),
                    "dispatch_mode": c.dispatch_mode.value,
                }
                for c in plan.commands
            ],
            "created_at": plan.created_at.isoformat(),
        },
    }


@router.get("/dispatch/history", summary="获取调度历史")
async def get_dispatch_history(limit: int = Query(20, ge=1, le=100)):
    """获取VPP调度历史记录"""
    coordinator = get_vpp_coordinator()
    return {
        "success": True,
        "data": coordinator.get_dispatch_history(limit=limit),
    }


@router.get("/price", summary="获取当前电价")
async def get_current_price():
    """获取当前分时电价"""
    from app.services.vpp.dispatch_optimizer import VPPOptimizer
    from app.services.vpp.dispatch_optimizer.optimizer import _pricing_hour
    optimizer = VPPOptimizer()
    hour = _pricing_hour()
    price = optimizer.get_current_price(hour)

    # 确定时段
    if price >= optimizer.PEAK_PRICE:
        period = "尖峰"
    elif price >= optimizer.HIGH_PRICE:
        period = "高峰"
    elif price >= optimizer.FLAT_PRICE:
        period = "平段"
    else:
        period = "低谷"

    return {
        "success": True,
        "data": {
            "current_price": round(price, 3),
            "period": period,
            "hour": round(hour, 2),
            "price_schedule": {
                "peak": optimizer.PEAK_PRICE,
                "high": optimizer.HIGH_PRICE,
                "flat": optimizer.FLAT_PRICE,
                "valley": optimizer.VALLEY_PRICE,
            },
        },
    }


@router.post("/dispatch/lp", summary="LP优化调度")
async def execute_lp_dispatch(req: LPDispatchRequest):
    """
    使用线性规划(LP)优化执行VPP调度
    - 基于scipy.optimize.linprog求解最优功率分配
    - 支持经济调度、削峰填谷、需求响应、电网支撑
    - 如果scipy不可用，自动回退到启发式调度
    """
    lp_optimizer = get_vpp_lp_optimizer()
    coordinator = get_vpp_coordinator()

    stations = list(coordinator.stations.values())
    resources = list(coordinator.resources.values())

    try:
        mode = DispatchMode(req.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效调度模式: {req.mode}")

    try:
        plan = lp_optimizer.optimize_dispatch(
            stations=stations,
            resources=resources,
            target_power_kw=req.target_power_kw,
            duration_min=req.duration_min,
            mode=mode,
            peak_threshold_kw=req.peak_threshold_kw,
            dr_reward_per_kwh=req.dr_reward_per_kwh,
        )
    except Exception as e:
        logger.exception("LP优化调度失败")
        raise HTTPException(status_code=500, detail="LP优化调度失败")

    # 记录到调度历史
    coordinator._record_plan(plan)

    return {
        "success": True,
        "data": {
            "plan_id": plan.plan_id,
            "mode": plan.mode.value,
            "trigger": plan.trigger,
            "stations_involved": plan.stations_involved,
            "total_dispatch_kw": round(plan.total_dispatch_kw, 2),
            "estimated_revenue": round(plan.estimated_revenue, 2),
            "estimated_cost": round(plan.estimated_cost, 2),
            "net_profit": round(plan.net_profit, 2),
            "commands": [
                {
                    "resource_id": c.resource_id,
                    "station_id": c.station_id,
                    "resource_type": c.resource_type.value,
                    "target_power_kw": round(c.target_power_kw, 2),
                    "duration_min": c.duration_min,
                    "priority": c.priority,
                    "estimated_revenue": round(c.estimated_revenue, 2),
                    "estimated_cost": round(c.estimated_cost, 2),
                    "dispatch_mode": c.dispatch_mode.value,
                }
                for c in plan.commands
            ],
            "created_at": plan.created_at.isoformat(),
        },
    }


@router.get("/optimize/status", summary="LP优化器状态")
async def get_optimizer_status():
    """获取LP优化器状态"""
    try:
        import scipy
        scipy_version = scipy.__version__
        scipy_available = True
    except ImportError:
        scipy_version = None
        scipy_available = False

    return {
        "success": True,
        "data": {
            "lp_optimizer_available": scipy_available,
            "scipy_version": scipy_version,
            "supported_modes": ["economic", "peak_shaving", "demand_response", "grid_support"],
            "constraints": [
                "SOC上下限约束",
                "最大功率约束",
                "爬坡速率约束",
                "功率需求等式约束(允许10%偏差)",
            ],
        },
    }


@router.get("/resources", summary="获取所有资源")
async def list_resources():
    """获取VPP管理的所有可调度资源"""
    coordinator = get_vpp_coordinator()
    resources = []
    for r in coordinator.resources.values():
        resources.append({
            'resource_id': r.resource_id,
            'resource_type': r.resource_type.value,
            'station_id': r.station_id,
            'rated_power_kw': r.rated_power_kw,
            'current_power_kw': r.current_power_kw,
            'available_power_kw': r.available_power_kw,
            'soc': r.soc,
            'efficiency': r.efficiency,
            'priority': r.priority,
            'cost_per_kwh': r.cost_per_kwh,
        })
    return {
        "success": True,
        "data": resources,
    }


@router.post("/simulate", summary="重新加载模拟数据")
async def reload_simulation(count: int = Query(5, ge=1, le=10)):
    """重新加载模拟站点数据"""
    global _coordinator
    import app.services.vpp.dispatch_optimizer as vpp_module
    coordinator = vpp_module.get_vpp_coordinator()
    
    # 清除现有数据
    # 清除现有数据(持锁, 避免与调度循环竞态)
    coordinator.clear_all()
    
    # 重新模拟
    coordinator.simulate_station_data(count=count)
    
    return {
        "success": True,
        "message": f"已加载 {count} 个模拟站点",
        "data": coordinator.get_aggregate_capacity(),
    }


@router.get("/auto-scheduler/status", summary="获取自动调度器状态")
async def get_auto_scheduler_status():
    """获取VPP自动调度器运行状态"""
    scheduler = get_vpp_auto_scheduler()
    return {
        "success": True,
        "data": scheduler.get_status(),
    }


@router.post("/auto-scheduler/start", summary="启动自动调度")
async def start_auto_scheduler():
    """启动VPP自动调度器"""
    scheduler = get_vpp_auto_scheduler()
    await scheduler.start()
    return {
        "success": True,
        "message": "VPP自动调度器已启动",
        "data": scheduler.get_status(),
    }


@router.post("/auto-scheduler/stop", summary="停止自动调度")
async def stop_auto_scheduler():
    """停止VPP自动调度器"""
    scheduler = get_vpp_auto_scheduler()
    await scheduler.stop()
    return {
        "success": True,
        "message": "VPP自动调度器已停止",
        "data": scheduler.get_status(),
    }


@router.patch("/auto-scheduler/config", summary="更新自动调度配置")
async def update_auto_scheduler_config(
    economic_interval: Optional[int] = Query(None, ge=60, le=3600, description="经济调度间隔(秒)"),
    health_interval: Optional[int] = Query(None, ge=10, le=300, description="健康检查间隔(秒)"),
    soc_threshold: Optional[float] = Query(None, ge=0.05, le=0.5, description="SOC告警阈值"),
    peak_threshold: Optional[float] = Query(None, ge=100, le=10000, description="削峰阈值(kW)"),
):
    """更新VPP自动调度器配置"""
    scheduler = get_vpp_auto_scheduler()
    if economic_interval is not None:
        scheduler.economic_dispatch_interval_sec = economic_interval
    if health_interval is not None:
        scheduler.health_check_interval_sec = health_interval
    if soc_threshold is not None:
        scheduler.soc_alert_threshold = soc_threshold
    if peak_threshold is not None:
        scheduler.peak_threshold_kw = peak_threshold
    return {
        "success": True,
        "message": "配置已更新",
        "data": scheduler.get_status(),
    }
