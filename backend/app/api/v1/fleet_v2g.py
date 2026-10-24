"""
V2G 车队调度 API

提供端点:
- POST/GET /api/v1/fleet/v2g/plans     创建/查询V2G充放电计划
- POST/GET /api/v1/fleet/v2g/revenue   记录/查询V2G放电收益
- GET    /api/v1/fleet/v2g/status      V2G调度状态概览
- GET    /api/v1/fleet/v2g/records     调度执行记录(复用 v2g_dispatch_logs)
"""
import logging
from datetime import date
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import assert_enterprise_team_access, is_platform_admin
from app.api.v1.auth import require_role, get_current_user
from app.core.response import success_response, paginated_response
from app.models.fleet_v2g import (
    FleetV2GPlan,
    FleetV2GRevenue,
    V2GPlanStatus,
)
from app.models.v2g_dispatch import V2GDispatchLog
from app.models.device import Device
from app.models.station import Station
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.tasks.tz_utils import biz_day_bounds_utc_naive
from app.models.user import User
from app.schemas.fleet_v2g import (
    FleetV2GPlanRequest,
    FleetV2GRevenueRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2g", tags=["V2G车队调度"], dependencies=[Depends(require_role("admin", "operator"))])

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _plan_to_dict(p: FleetV2GPlan) -> dict:
    return {
        "id": p.id,
        "enterprise_id": p.enterprise_id,
        "vehicle_id": p.vehicle_id,
        "plan_date": p.plan_date.isoformat() if p.plan_date else None,
        "planned_charge_start": p.planned_charge_start.isoformat() if p.planned_charge_start else None,
        "planned_charge_end": p.planned_charge_end.isoformat() if p.planned_charge_end else None,
        "planned_discharge_start": p.planned_discharge_start.isoformat() if p.planned_discharge_start else None,
        "planned_discharge_end": p.planned_discharge_end.isoformat() if p.planned_discharge_end else None,
        "target_soc_min": p.target_soc_min,
        "target_soc_max": p.target_soc_max,
        "status": p.status.value if hasattr(p.status, "value") else str(p.status),
    }


def _revenue_to_dict(r: FleetV2GRevenue) -> dict:
    return {
        "id": r.id,
        "enterprise_id": r.enterprise_id,
        "vehicle_id": r.vehicle_id,
        "record_date": r.record_date.isoformat() if r.record_date else None,
        "discharge_energy_kwh": float(r.discharge_energy_kwh or 0),
        "discharge_revenue": float(r.discharge_revenue or 0),
        "grid_response_count": r.grid_response_count or 0,
        "peak_shaving_kwh": float(r.peak_shaving_kwh or 0),
        "valley_filling_kwh": float(r.valley_filling_kwh or 0),
        "total_revenue": float(r.total_revenue or 0),
    }


def _dispatch_to_dict(d: V2GDispatchLog) -> dict:
    return {
        "id": d.id,
        "device_id": d.device_id,
        "dispatch_type": d.dispatch_type,
        "target_power_kw": d.target_power_kw,
        "actual_power_kw": d.actual_power_kw,
        "status": d.status,
        "start_at": d.start_at.isoformat() if d.start_at else None,
        "end_at": d.end_at.isoformat() if d.end_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


# ----------------------------------------------------------------------
# V2G Plan CRUD
# ----------------------------------------------------------------------

@router.post("/plans", summary="创建V2G充放电计划")
def create_plan(
    data: FleetV2GPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建一个V2G充电/放电计划。"""
    try:
        # 校验企业归属（含存在性）
        assert_enterprise_team_access(db, data.enterprise_id, current_user)

        # 校验车辆存在
        vehicle = db.query(EnterpriseVehicle).filter(
            EnterpriseVehicle.id == data.vehicle_id
        ).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail=f"车辆 {data.vehicle_id} 不存在")

        plan = FleetV2GPlan(
            enterprise_id=data.enterprise_id,
            vehicle_id=data.vehicle_id,
            plan_date=data.plan_date,
            planned_charge_start=data.planned_charge_start,
            planned_charge_end=data.planned_charge_end,
            planned_discharge_start=data.planned_discharge_start,
            planned_discharge_end=data.planned_discharge_end,
            target_soc_min=data.target_soc_min,
            target_soc_max=data.target_soc_max,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        return success_response(_plan_to_dict(plan), "V2G充放电计划创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("创建V2G计划失败 enterprise_id=%s vehicle_id=%s", data.enterprise_id, data.vehicle_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/plans", summary="查询V2G充放电计划列表")
def list_plans(
    enterprise_id: int = Query(..., gt=0, description="企业ID"),
    vehicle_id: Optional[int] = Query(None, gt=0, description="可选车辆ID过滤"),
    plan_date: Optional[date] = Query(None, description="可选计划日期过滤(YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="可选状态过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询V2G充放电计划列表，支持企业/车辆/日期/状态过滤。"""
    try:
        assert_enterprise_team_access(db, enterprise_id, current_user)
        query = db.query(FleetV2GPlan).filter(
            FleetV2GPlan.enterprise_id == enterprise_id
        )
        if vehicle_id:
            query = query.filter(FleetV2GPlan.vehicle_id == vehicle_id)
        if plan_date:
            query = query.filter(FleetV2GPlan.plan_date == plan_date)
        if status:
            query = query.filter(FleetV2GPlan.status == status)

        total = query.count()
        plans = (
            query.order_by(desc(FleetV2GPlan.plan_date))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return paginated_response(
            [_plan_to_dict(p) for p in plans], total, page, page_size
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询V2G计划列表失败 enterprise_id=%s", enterprise_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/plans/{plan_id}", summary="查询单个V2G计划详情")
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定ID的V2G计划详情。"""
    try:
        plan = db.query(FleetV2GPlan).filter(FleetV2GPlan.id == plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail=f"计划 {plan_id} 不存在")
        assert_enterprise_team_access(db, plan.enterprise_id, current_user)
        return success_response(_plan_to_dict(plan))
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询V2G计划详情失败 plan_id=%s", plan_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.put("/plans/{plan_id}/status", summary="更新V2G计划状态")
def update_plan_status(
    plan_id: int,
    new_status: str = Query(..., description="新状态: scheduled/charging/discharging/completed/cancelled/failed"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新V2G计划的状态。"""
    try:
        plan = db.query(FleetV2GPlan).filter(FleetV2GPlan.id == plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail=f"计划 {plan_id} 不存在")
        assert_enterprise_team_access(db, plan.enterprise_id, current_user)

        valid_statuses = [s.value for s in V2GPlanStatus]
        if new_status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"无效状态 '{new_status}'，可选: {', '.join(valid_statuses)}",
            )

        plan.status = V2GPlanStatus(new_status)
        db.commit()
        db.refresh(plan)
        return success_response(_plan_to_dict(plan), f"计划状态已更新为 {new_status}")
    except HTTPException:
        raise
    except Exception:
        logger.exception("更新V2G计划状态失败 plan_id=%s", plan_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


# ----------------------------------------------------------------------
# V2G Revenue Management
# ----------------------------------------------------------------------

@router.post("/revenue", summary="记录V2G放电收益")
def record_revenue(
    data: FleetV2GRevenueRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """记录一次V2G放电收益数据。"""
    try:
        # 校验企业归属（含存在性）
        assert_enterprise_team_access(db, data.enterprise_id, current_user)

        # 校验车辆存在
        vehicle = db.query(EnterpriseVehicle).filter(
            EnterpriseVehicle.id == data.vehicle_id
        ).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail=f"车辆 {data.vehicle_id} 不存在")

        revenue = FleetV2GRevenue(
            enterprise_id=data.enterprise_id,
            vehicle_id=data.vehicle_id,
            record_date=data.record_date,
            discharge_energy_kwh=Decimal(str(data.discharge_energy_kwh)),
            discharge_revenue=Decimal(str(data.discharge_revenue)),
            grid_response_count=data.grid_response_count,
            peak_shaving_kwh=Decimal(str(data.peak_shaving_kwh)),
            valley_filling_kwh=Decimal(str(data.valley_filling_kwh)),
            total_revenue=Decimal(str(data.total_revenue)),
        )
        db.add(revenue)
        db.commit()
        db.refresh(revenue)
        return success_response(_revenue_to_dict(revenue), "V2G放电收益记录成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("记录V2G收益失败 enterprise_id=%s vehicle_id=%s", data.enterprise_id, data.vehicle_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/revenue", summary="查询V2G收益记录列表")
def list_revenue(
    enterprise_id: int = Query(..., gt=0, description="企业ID"),
    vehicle_id: Optional[int] = Query(None, gt=0, description="可选车辆ID过滤"),
    start_date: Optional[date] = Query(None, description="起始日期(YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="截止日期(YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询V2G收益记录列表，支持企业/车辆/日期范围过滤。"""
    try:
        assert_enterprise_team_access(db, enterprise_id, current_user)
        query = db.query(FleetV2GRevenue).filter(
            FleetV2GRevenue.enterprise_id == enterprise_id
        )
        if vehicle_id:
            query = query.filter(FleetV2GRevenue.vehicle_id == vehicle_id)
        if start_date:
            query = query.filter(FleetV2GRevenue.record_date >= start_date)
        if end_date:
            query = query.filter(FleetV2GRevenue.record_date <= end_date)

        total = query.count()
        records = (
            query.order_by(desc(FleetV2GRevenue.record_date))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return paginated_response(
            [_revenue_to_dict(r) for r in records], total, page, page_size
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询V2G收益列表失败 enterprise_id=%s", enterprise_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


# ----------------------------------------------------------------------
# V2G Status Overview
# ----------------------------------------------------------------------

@router.get("/status", summary="V2G调度状态概览")
def get_status(
    enterprise_id: int = Query(..., gt=0, description="企业ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询指定企业的V2G调度状态概览。"""
    try:
        assert_enterprise_team_access(db, enterprise_id, current_user)
        # 计划状态汇总
        status_counts_raw = (
            db.query(FleetV2GPlan.status, func.count(FleetV2GPlan.id))
            .filter(FleetV2GPlan.enterprise_id == enterprise_id)
            .group_by(FleetV2GPlan.status)
            .all()
        )
        status_counts = {
            s.value if hasattr(s, "value") else str(s): cnt
            for s, cnt in status_counts_raw
        }

        # 最近计划
        recent_plans = (
            db.query(FleetV2GPlan)
            .filter(FleetV2GPlan.enterprise_id == enterprise_id)
            .order_by(desc(FleetV2GPlan.plan_date))
            .limit(5)
            .all()
        )

        # 收益汇总
        revenue_summary_raw = (
            db.query(
                func.sum(FleetV2GRevenue.total_revenue).label("total"),
                func.sum(FleetV2GRevenue.discharge_energy_kwh).label("energy"),
                func.count(FleetV2GRevenue.id).label("records"),
            )
            .filter(FleetV2GRevenue.enterprise_id == enterprise_id)
            .first()
        )

        return success_response({
            "enterprise_id": enterprise_id,
            "plan_status_counts": status_counts,
            "recent_plans": [_plan_to_dict(p) for p in recent_plans],
            "revenue_summary": {
                "total_revenue": float(revenue_summary_raw.total or 0),
                "total_discharge_energy_kwh": float(revenue_summary_raw.energy or 0),
                "total_records": revenue_summary_raw.records or 0,
            },
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询V2G状态概览失败 enterprise_id=%s", enterprise_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


# ----------------------------------------------------------------------
# V2G Dispatch Records (复用 v2g_dispatch_logs)
# ----------------------------------------------------------------------

@router.get("/records", summary="查询V2G调度执行记录")
def list_records(
    enterprise_id: int = Query(..., gt=0, description="企业ID"),
    dispatch_type: Optional[str] = Query(None, description="调度类型: charge/discharge/standby"),
    start_date: Optional[date] = Query(None, description="起始日期(YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="截止日期(YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询V2G调度执行记录（复用运维平台 v2g_dispatch_logs 表）。

    卡 9e9e8f96: 团队级用户按 enterprise 归属 team 过滤 —— 经
    Device→Station 强制 Station.team_id == Enterprise.owner_team_id，
    杜绝传本 team enterprise_id 越权读全平台调度日志。admin 豁免全量。
    """
    try:
        ent = assert_enterprise_team_access(db, enterprise_id, current_user)
        query = db.query(V2GDispatchLog)
        if not is_platform_admin(current_user):
            # 团队级用户只能看本团队(即该 enterprise 归属 team)设备的调度日志
            query = (
                query.join(Device, Device.id == V2GDispatchLog.device_id)
                .join(Station, Station.id == Device.station_id)
                .filter(Station.team_id == ent.owner_team_id)
            )

        # 按调度类型过滤
        if dispatch_type:
            query = query.filter(V2GDispatchLog.dispatch_type == dispatch_type)

        # 按日期范围过滤 (卡 77b1ed08): start_date/end_date 是用户业务日期,
        # 旧 func.date(created_at)(UTC 日)在上海 00:00-08:00 窗口错位 8h;
        # 参照 fleet_charging_policies 用 biz_day_bounds_utc_naive 换算
        # naive-UTC 闭开时间窗直接比较 created_at。
        if start_date:
            day_start, _ = biz_day_bounds_utc_naive(start_date)
            query = query.filter(V2GDispatchLog.created_at >= day_start)
        if end_date:
            _, day_end = biz_day_bounds_utc_naive(end_date)
            query = query.filter(V2GDispatchLog.created_at < day_end)

        total = query.count()
        records = (
            query.order_by(desc(V2GDispatchLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return paginated_response(
            [_dispatch_to_dict(r) for r in records], total, page, page_size
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询V2G调度记录失败 enterprise_id=%s", enterprise_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")
