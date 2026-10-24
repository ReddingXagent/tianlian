"""
效率报表 API

提供三类设备效率报表:
- GET /reports/utilization  — 各站点/类型利用率排名 + 低利用率预警(<30%) + 过载标记(>90%)
- GET /reports/efficiency   — 充电效率排名 + 异常低效设备预警
- GET /reports/generation   — 光伏PR值排名 + 实际vs理论对比
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
import logging

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.response import success_response
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, assert_station_team_access
from app.models.device import Device, DeviceType
from app.models.device_efficiency_log import DeviceEfficiencyLog
from app.models.station import Station
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["效率报表"])


@router.get("/utilization")
def get_utilization_report(
    station_id: Optional[str] = None,
    device_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    设备利用率排名报表

    返回:
    - 各站点/类型 利用率排名
    - 低利用率预警 (<30%)
    - 过载标记 (>90%)
    """
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅本 team 设备；
    # station_id 越权 → 404（不泄露站点存在）。置于 try 外避免被 except 吞成 500。
    if not is_platform_admin(user):
        if station_id:
            assert_station_team_access(db, int(station_id), user)
    try:
        query = db.query(
            Device.id,
            Device.name,
            Device.code,
            Device.type,
            Device.station_id,
            Device.utilization_rate,
            Station.name.label("station_name"),
        ).join(Station, Device.station_id == Station.id, isouter=True)

        if station_id:
            query = query.filter(Device.station_id == int(station_id))
        if device_type:
            query = query.filter(Device.type == device_type)
        if not is_platform_admin(user):
            query = query.filter(Station.team_id == user.team_id)

        devices = query.all()

        def _safe_type_val(t) -> str:
            """安全获取 device type，兼容 DB 中的旧值"""
            if t is None:
                return "unknown"
            if hasattr(t, 'value'):
                return t.value
            return str(t)

        items = []
        low_utilization = []
        overload = []

        for d in devices:
            rate = float(d.utilization_rate or 0)
            item = {
                "device_id": d.id,
                "device_name": d.name,
                "device_code": d.code,
                "device_type": _safe_type_val(d.type),
                "station_id": d.station_id,
                "station_name": d.station_name or "",
                "utilization_rate": round(rate, 1),
            }
            items.append(item)

            if rate < 30:
                low_utilization.append(item)
            if rate > 90:
                overload.append(item)

        items.sort(key=lambda x: x["utilization_rate"], reverse=True)

        # 分页（任务卡 e2999336，防 DoS 响应膨胀）：alerts 基于全量设备计算，
        # items 切片当前页；total 反映全量设备数（设备维度有界）。
        total = len(items)
        offset = (page - 1) * page_size
        paged_items = items[offset : offset + page_size]

        return success_response({
            "items": paged_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "alerts": {
                "low_utilization": {
                    "count": len(low_utilization),
                    "threshold": "<30%",
                    "items": low_utilization,
                },
                "overload": {
                    "count": len(overload),
                    "threshold": ">90%",
                    "items": overload,
                },
            },
        })
    except Exception as e:
        logger.error("获取利用率排名失败: %s", e)
        raise HTTPException(status_code=500, detail="查询失败")


@router.get("/efficiency")
def get_efficiency_report(
    station_id: Optional[str] = None,
    min_efficiency: Optional[float] = Query(None, ge=0, le=100, description="最低效率阈值"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    充电效率排名 + 异常低效设备预警

    返回:
    - 各设备充电效率排名
    - 效率低于阈值(默认 70%)的异常设备预警
    """
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅本 team；station_id 越权 → 404。
    # 置于 try 外避免被 except 吞成 500。
    if not is_platform_admin(user):
        if station_id:
            assert_station_team_access(db, int(station_id), user)
    try:
        threshold = min_efficiency if min_efficiency is not None else 70.0

        # 从 device_efficiency_logs 获取最新的充电效率指标
        subq = (
            db.query(
                DeviceEfficiencyLog.device_id,
                func.max(DeviceEfficiencyLog.recorded_at).label("max_ts"),
            )
            .filter(DeviceEfficiencyLog.metric_type == "charge")
            .group_by(DeviceEfficiencyLog.device_id)
            .subquery()
        )

        query = (
            db.query(
                DeviceEfficiencyLog.device_id,
                DeviceEfficiencyLog.metric_value,
                Device.name,
                Device.code,
                Device.type,
                Device.station_id,
                Station.name.label("station_name"),
            )
            .join(
                subq,
                (DeviceEfficiencyLog.device_id == subq.c.device_id)
                & (DeviceEfficiencyLog.recorded_at == subq.c.max_ts),
            )
            .join(Device, DeviceEfficiencyLog.device_id == Device.id)
            .join(Station, Device.station_id == Station.id, isouter=True)
            .filter(DeviceEfficiencyLog.metric_type == "charge")
        )

        if station_id:
            query = query.filter(Device.station_id == int(station_id))
        if not is_platform_admin(user):
            query = query.filter(Station.team_id == user.team_id)

        results = query.all()

        items = []
        abnormal = []

        for r in results:
            eff = float(r.metric_value or 0)
            item = {
                "device_id": r.device_id,
                "device_name": r.name,
                "device_code": r.code,
                "device_type": r.type.value if hasattr(r.type, 'value') else (str(r.type) if r.type else "unknown"),
                "station_id": r.station_id,
                "station_name": r.station_name or "",
                "charge_efficiency": round(eff, 1),
            }
            items.append(item)

            if eff < threshold:
                abnormal.append(item)

        items.sort(key=lambda x: x["charge_efficiency"], reverse=True)

        # 分页（任务卡 e2999336）：alerts 基于全量设备计算，items 切片防响应膨胀。
        total = len(items)
        offset = (page - 1) * page_size
        paged_items = items[offset : offset + page_size]

        return success_response({
            "items": paged_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "alerts": {
                "abnormal_low_efficiency": {
                    "count": len(abnormal),
                    "threshold": f"<{threshold}%",
                    "items": abnormal,
                },
            },
        })
    except Exception as e:
        logger.error("获取充电效率排名失败: %s", e)
        raise HTTPException(status_code=500, detail="查询失败")


@router.get("/generation")
def get_generation_report(
    station_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    光伏PR值排名 + 实际vs理论对比

    返回:
    - 光伏逆变器设备的PR(Performance Ratio)值排名
    - 实际发电 vs 理论发电对比
    """
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅本 team；station_id 越权 → 404。
    # 置于 try 外避免被 except 吞成 500。
    if not is_platform_admin(user):
        if station_id:
            assert_station_team_access(db, int(station_id), user)
    try:
        query = (
            db.query(
                Device.id,
                Device.name,
                Device.code,
                Device.type,
                Device.station_id,
                Device.utilization_rate,
                Device.pv_pr_ratio,
                Device.rated_power,
                Device.total_runtime_hours,
                Device.total_generation_kwh,
                Station.name.label("station_name"),
            )
            .filter(
                Device.type.in_([DeviceType.PV_INVERTER, DeviceType.BATTERY_INVERTER])
            )
            .join(Station, Device.station_id == Station.id, isouter=True)
        )

        if station_id:
            query = query.filter(Device.station_id == int(station_id))
        if not is_platform_admin(user):
            query = query.filter(Station.team_id == user.team_id)

        devices = query.all()

        items = []
        high_performance = []
        low_performance = []

        for d in devices:
            rated_power = float(d.rated_power or 0)
            runtime_hours = float(d.total_runtime_hours or 0)
            actual_gen = float(d.total_generation_kwh or 0)
            pv_pr = float(d.pv_pr_ratio) if d.pv_pr_ratio is not None else None

            theoretical_gen = (
                rated_power * runtime_hours
                if rated_power > 0 and runtime_hours > 0
                else None
            )

            item = {
                "device_id": d.id,
                "device_name": d.name,
                "device_code": d.code,
                "device_type": d.type.value if hasattr(d.type, 'value') else (str(d.type) if d.type else "inverter"),
                "station_id": d.station_id,
                "station_name": d.station_name or "",
                "pv_pr_ratio": round(pv_pr, 4) if pv_pr is not None else None,
                "rated_power_kw": round(rated_power, 2),
                "runtime_hours": round(runtime_hours, 1),
                "actual_generation_kwh": round(actual_gen, 2),
                "theoretical_generation_kwh": (
                    round(theoretical_gen, 2)
                    if theoretical_gen is not None
                    else None
                ),
                "generation_ratio": (
                    round(actual_gen / theoretical_gen, 4)
                    if theoretical_gen and theoretical_gen > 0
                    else None
                ),
            }
            items.append(item)

            if pv_pr is not None:
                if pv_pr >= 0.80:
                    high_performance.append(item)
                elif pv_pr < 0.65:
                    low_performance.append(item)

        items.sort(
            key=lambda x: x["pv_pr_ratio"] if x["pv_pr_ratio"] is not None else 0,
            reverse=True,
        )

        # 分页（任务卡 e2999336）：alerts 基于全量设备计算，items 切片防响应膨胀。
        total = len(items)
        offset = (page - 1) * page_size
        paged_items = items[offset : offset + page_size]

        return success_response({
            "items": paged_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "alerts": {
                "high_performance": {
                    "count": len(high_performance),
                    "threshold": "PR >= 0.80",
                    "items": high_performance,
                },
                "low_performance": {
                    "count": len(low_performance),
                    "threshold": "PR < 0.65",
                    "items": low_performance,
                },
            },
        })
    except Exception as e:
        logger.error("获取光伏PR排名失败: %s", e)
        raise HTTPException(status_code=500, detail="查询失败")