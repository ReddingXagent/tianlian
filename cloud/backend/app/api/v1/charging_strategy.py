"""
充电策略引擎 API(P7)

端点:
- GET    /charging/strategies          列举全部充电模式(按优先级)
- GET    /charging/strategy/current    查询当前激活模式
- POST   /charging/strategy/switch     切换模式
- GET    /charging/forecast/solar      未来24h光伏预测
- GET    /charging/storage/status      储能调度状态
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, assert_station_team_access
from app.middleware.permission import require_write_permission
from app.models.user import User
from app.schemas.charging import StrategySwitchRequest
from app.services.charging import get_charging_engine
from app.services.charging.solar_forecast import SolarForecaster
from app.services.charging.storage_optimizer import StorageOptimizer

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_write_permission("charging:manage"))])


@router.get("/strategies", summary="列举全部充电模式")
async def list_strategies(user: User = Depends(get_current_user)):
    """返回 5 种充电模式及其优先级(数字越小优先级越高)"""
    engine = get_charging_engine()
    return {
        "success": True,
        "data": engine.list_strategies(),
    }


@router.get("/strategy/current", summary="查询当前激活模式")
async def get_current_strategy(
    station_id: Optional[str] = Query(None, description="站点ID(可选)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询全局或指定站点的当前充电模式"""
    # team scoping（任务卡 ab5c5f17）：指定站点时非 admin 仅可查本 team 站点；越权/不存在 → 404。
    if station_id and not is_platform_admin(user):
        assert_station_team_access(db, int(station_id), user)
    engine = get_charging_engine()
    mode = engine.get_current_mode(station_id)
    return {
        "success": True,
        "data": {
            "mode": mode.value,
            "station_id": station_id,
        },
    }


@router.post("/strategy/switch", summary="切换充电模式")
async def switch_strategy(
    req: StrategySwitchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """切换全局或指定站点的充电模式"""
    # team scoping（任务卡 ab5c5f17）：指定站点时非 admin 仅可切本 team 站点；越权/不存在 → 404。
    # 置于引擎切换前，越权先于业务，不泄露存在。
    if req.station_id and not is_platform_admin(user):
        assert_station_team_access(db, int(req.station_id), user)
    engine = get_charging_engine()
    previous = engine.get_current_mode(req.station_id)
    try:
        engine.switch_mode(req.mode, req.station_id)
    except ValueError as e:
        logger.exception("切换充电模式失败 mode=%s station_id=%s", req.mode, req.station_id)
        raise HTTPException(status_code=400, detail="充电模式切换失败, 请检查参数")
    return {
        "success": True,
        "data": {
            "mode": req.mode,
            "station_id": req.station_id,
            "switched_at": engine.last_switched_at,
            "previous_mode": previous.value,
        },
    }


@router.get("/forecast/solar", summary="未来24h光伏预测")
async def get_solar_forecast(
    installed_kw: float = Query(..., gt=0, description="光伏装机容量(kW)"),
    weather: str = Query("sunny", description="天气: sunny/cloudy/rainy"),
    user: User = Depends(get_current_user),
):
    """基于装机容量 + 天气预测未来 24h 逐小时发电量"""
    forecaster = SolarForecaster()
    try:
        result = forecaster.forecast_24h(installed_kw, weather)
    except ValueError as e:
        logger.exception("光伏预测失败 installed_kw=%s weather=%s", installed_kw, weather)
        raise HTTPException(status_code=400, detail="光伏预测失败, 请检查参数")
    return {
        "success": True,
        "data": {
            "weather": result.weather,
            "installed_kw": result.installed_kw,
            "points": [
                {"hour": p.hour, "power_kw": p.power_kw}
                for p in result.points
            ],
            "total_kwh": result.total_kwh,
            "peak_power_kw": result.peak_power_kw,
        },
    }


@router.get("/storage/status", summary="储能调度状态")
async def get_storage_status(
    soc: float = Query(..., ge=0, le=1, description="当前SOC(0-1)"),
    pv_surplus_kw: float = Query(0, ge=0, description="光伏余电(kW)"),
    grid_price: Optional[float] = Query(None, ge=0, description="实时电价(元/kWh)"),
    load_kw: float = Query(0, ge=0, description="负荷(kW)"),
    temp_c: Optional[float] = Query(None, ge=-50, le=100, description="储能温度(℃)"),
    target_soc: Optional[float] = Query(None, ge=0, le=1, description="目标SOC"),
    user: User = Depends(get_current_user),
):
    """根据 SOC/光伏余电/电价/温度决策储能充放电动作"""
    optimizer = StorageOptimizer()
    action = optimizer.optimize(
        soc=soc,
        pv_surplus_kw=pv_surplus_kw,
        grid_price=grid_price,
        load_kw=load_kw,
        temp_c=temp_c,
        target_soc=target_soc,
    )
    return {
        "success": True,
        "data": {
            "soc": soc,
            "target_soc": action.target_soc,
            "action": action.action,
            "power_kw": action.power_kw,
            "reason": action.reason,
            "health_ok": action.health_ok,
            "within_safe_range": action.within_safe_range,
        },
    }
