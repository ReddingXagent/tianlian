"""
车队充电统计 API

功能:
- GET /api/v1/enterprises/{eid}/vehicles/{vid}/charging-stats —— 单车充电统计（累计+趋势）
- GET /api/v1/enterprises/{eid}/charging-stats                        —— 车队级充电汇总（总量+排行+场站分布）

数据源: charging_orders，通过 vehicle_id / plate_number 关联企业车辆
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, extract

from app.api.deps import assert_enterprise_team_access
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.station import Station
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


# ========== Helpers ==========

def _zero_summary() -> dict:
    """空数据时返回的零值结构"""
    return {
        "total_orders": 0,
        "total_kwh": 0.0,
        "total_amount": 0.0,
        "avg_kwh_per_order": 0.0,
        "avg_amount_per_order": 0.0,
    }


def _zero_trend() -> list:
    """空趋势"""
    return []


def _build_monthly_trend(rows) -> list:
    """将 (year, month, kwh, amount) 行转为趋势列表"""
    return [
        {
            "month": f"{int(r.year)}-{int(r.month):02d}",
            "charged_kwh": float(r.total_kwh or 0),
            "total_amount": float(r.total_amount or 0),
        }
        for r in rows
    ]


# ========== API Endpoints ==========

@router.get(
    "/enterprises/{enterprise_id}/vehicles/{vehicle_id}/charging-stats",
    summary="单车充电统计",
)
def vehicle_charging_stats(
    enterprise_id: int,
    vehicle_id: int,
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    单车充电统计:
    - 累计: 充电次数 / 总电量kWh / 总金额 / 平均单次
    - 趋势: 按月聚合（近12月 电量+金额）
    - 支持日期范围筛选
    """
    # 校验企业归属（含存在性）
    assert_enterprise_team_access(db, enterprise_id, current_user)

    # 校验车辆存在且属于该企业
    vehicle = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.id == vehicle_id,
        EnterpriseVehicle.enterprise_id == enterprise_id,
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="车辆不存在")

    # 构建基础查询: 通过 vehicle_id 或 plate_number 关联
    conds = [ChargingOrder.vehicle_id == vehicle.id]
    if vehicle.plate_number:
        conds.append(ChargingOrder.plate_number == vehicle.plate_number)

    base_query = db.query(ChargingOrder).filter(
        or_(*conds),
        ChargingOrder.order_status == OrderStatus.COMPLETED,
    )

    # 日期筛选
    if start_date:
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            base_query = base_query.filter(ChargingOrder.start_time >= sd)
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date 格式应为 YYYY-MM-DD")
    if end_date:
        try:
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            # 包含当天
            ed = ed + timedelta(days=1)
            base_query = base_query.filter(ChargingOrder.start_time < ed)
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date 格式应为 YYYY-MM-DD")

    # 累计统计
    summary_row = base_query.with_entities(
        func.count(ChargingOrder.id).label("total_orders"),
        func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("total_kwh"),
        func.coalesce(func.sum(ChargingOrder.total_amount), 0).label("total_amount"),
    ).first()

    total_orders = int(summary_row.total_orders or 0)
    total_kwh = float(summary_row.total_kwh or 0)
    total_amount = float(summary_row.total_amount or 0)
    avg_kwh = round(total_kwh / total_orders, 2) if total_orders > 0 else 0.0
    avg_amount = round(total_amount / total_orders, 2) if total_orders > 0 else 0.0

    # 月度趋势（近12个月）
    twelve_months_ago = datetime.now(timezone.utc) - timedelta(days=365)
    trend_query = base_query.filter(
        ChargingOrder.start_time >= twelve_months_ago,
    ).with_entities(
        extract("year", ChargingOrder.start_time).label("year"),
        extract("month", ChargingOrder.start_time).label("month"),
        func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("total_kwh"),
        func.coalesce(func.sum(ChargingOrder.total_amount), 0).label("total_amount"),
    ).group_by(
        extract("year", ChargingOrder.start_time),
        extract("month", ChargingOrder.start_time),
    ).order_by(
        extract("year", ChargingOrder.start_time),
        extract("month", ChargingOrder.start_time),
    ).all()

    return success_response({
        "vehicle": {
            "id": vehicle.id,
            "plate_number": vehicle.plate_number,
            "vin": vehicle.vin,
        },
        "summary": {
            "total_orders": total_orders,
            "total_kwh": round(total_kwh, 2),
            "total_amount": round(total_amount, 2),
            "avg_kwh_per_order": avg_kwh,
            "avg_amount_per_order": avg_amount,
        },
        "monthly_trend": _build_monthly_trend(trend_query),
    })


@router.get(
    "/enterprises/{enterprise_id}/charging-stats",
    summary="车队级充电汇总",
)
def enterprise_charging_stats(
    enterprise_id: int,
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    top_n: int = Query(10, ge=1, le=50, description="车辆排行数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    车队级充电汇总:
    - 车队总充电量 / 总金额 / 活跃车辆数
    - 按车辆排行（Top N 充电量）
    - 按场站分布（各场站充电量）
    """
    # 校验企业归属（含存在性）
    assert_enterprise_team_access(db, enterprise_id, current_user)

    # 获取该企业所有车辆
    vehicles = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.enterprise_id == enterprise_id,
    ).all()

    if not vehicles:
        return success_response({
            "enterprise_id": enterprise_id,
            "summary": _zero_summary(),
            "active_vehicles": 0,
            "top_vehicles": [],
            "station_distribution": [],
        })

    # 构建 vehicle_id -> plate_number 映射
    vehicle_map = {v.id: v.plate_number for v in vehicles}
    vehicle_id_set = set(vehicle_map.keys())
    plate_number_set = set(v.plate_number for v in vehicles if v.plate_number)

    # 基础查询: 属于该企业的充电订单
    # 通过 vehicle_id IN 或 plate_number IN 关联
    order_query = db.query(ChargingOrder).filter(
        ChargingOrder.order_status == OrderStatus.COMPLETED,
        or_(
            ChargingOrder.vehicle_id.in_(vehicle_id_set),
            ChargingOrder.plate_number.in_(plate_number_set),
        ),
    )

    # 日期筛选
    if start_date:
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            order_query = order_query.filter(ChargingOrder.start_time >= sd)
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date 格式应为 YYYY-MM-DD")
    if end_date:
        try:
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            ed = ed + timedelta(days=1)
            order_query = order_query.filter(ChargingOrder.start_time < ed)
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date 格式应为 YYYY-MM-DD")

    # 汇总
    summary_row = order_query.with_entities(
        func.count(ChargingOrder.id).label("total_orders"),
        func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("total_kwh"),
        func.coalesce(func.sum(ChargingOrder.total_amount), 0).label("total_amount"),
    ).first()

    total_orders = int(summary_row.total_orders or 0)
    total_kwh = float(summary_row.total_kwh or 0)
    total_amount = float(summary_row.total_amount or 0)
    avg_kwh = round(total_kwh / total_orders, 2) if total_orders > 0 else 0.0
    avg_amount = round(total_amount / total_orders, 2) if total_orders > 0 else 0.0

    # 活跃车辆数（有充电记录的车辆）
    active_vehicle_ids = set()
    active_orders = order_query.with_entities(
        ChargingOrder.vehicle_id,
        ChargingOrder.plate_number,
    ).all()
    for o in active_orders:
        if o.vehicle_id and o.vehicle_id in vehicle_id_set:
            active_vehicle_ids.add(o.vehicle_id)
        elif o.plate_number and o.plate_number in plate_number_set:
            # 通过车牌匹配
            for vid, plate in vehicle_map.items():
                if plate == o.plate_number:
                    active_vehicle_ids.add(vid)
                    break

    # 车辆排行（Top N 充电量）
    # 需要按车辆聚合
    vehicle_stats = {}  # vid -> {kwh, amount, orders, plate}
    detailed_orders = order_query.with_entities(
        ChargingOrder.vehicle_id,
        ChargingOrder.plate_number,
        ChargingOrder.charged_kwh,
        ChargingOrder.total_amount,
        ChargingOrder.station_id,
    ).all()

    station_stats = {}  # station_id -> {kwh, orders}
    for o in detailed_orders:
        # 确定车辆 ID
        vid = o.vehicle_id if o.vehicle_id and o.vehicle_id in vehicle_id_set else None
        if vid is None and o.plate_number and o.plate_number in plate_number_set:
            for v_id, plate in vehicle_map.items():
                if plate == o.plate_number:
                    vid = v_id
                    break

        if vid is not None:
            if vid not in vehicle_stats:
                vehicle_stats[vid] = {
                    "vehicle_id": vid,
                    "plate_number": vehicle_map.get(vid, ""),
                    "charged_kwh": 0.0,
                    "total_amount": 0.0,
                    "order_count": 0,
                }
            vehicle_stats[vid]["charged_kwh"] += float(o.charged_kwh or 0)
            vehicle_stats[vid]["total_amount"] += float(o.total_amount or 0)
            vehicle_stats[vid]["order_count"] += 1

        # 场站分布
        sid = o.station_id
        if sid is not None:
            if sid not in station_stats:
                station_stats[sid] = {"charged_kwh": 0.0, "order_count": 0}
            station_stats[sid]["charged_kwh"] += float(o.charged_kwh or 0)
            station_stats[sid]["order_count"] += 1

    # Top N 车辆排行
    top_vehicles = sorted(
        vehicle_stats.values(),
        key=lambda x: x["charged_kwh"],
        reverse=True,
    )[:top_n]
    for v in top_vehicles:
        v["charged_kwh"] = round(v["charged_kwh"], 2)
        v["total_amount"] = round(v["total_amount"], 2)

    # 场站分布（关联场站名称）
    station_ids = list(station_stats.keys())
    stations = {}
    if station_ids:
        station_rows = db.query(Station).filter(Station.id.in_(station_ids)).all()
        stations = {s.id: s.name for s in station_rows}

    station_distribution = sorted(
        [
            {
                "station_id": sid,
                "station_name": stations.get(sid, f"场站{sid}"),
                "charged_kwh": round(s["charged_kwh"], 2),
                "order_count": s["order_count"],
            }
            for sid, s in station_stats.items()
        ],
        key=lambda x: x["charged_kwh"],
        reverse=True,
    )

    return success_response({
        "enterprise_id": enterprise_id,
        "summary": {
            "total_orders": total_orders,
            "total_kwh": round(total_kwh, 2),
            "total_amount": round(total_amount, 2),
            "avg_kwh_per_order": avg_kwh,
            "avg_amount_per_order": avg_amount,
        },
        "active_vehicles": len(active_vehicle_ids),
        "top_vehicles": top_vehicles,
        "station_distribution": station_distribution,
    })
