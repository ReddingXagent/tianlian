"""
企业车辆管理 API - Phase43 车队管理

功能:
- GET   /api/v1/enterprises/{enterprise_id}/vehicles —— 车辆列表
- POST  /api/v1/enterprises/{enterprise_id}/vehicles —— 绑定车辆
- PATCH /api/v1/enterprises/{enterprise_id}/vehicles/{vehicle_id} —— 变更车辆状态
- DELETE /api/v1/enterprises/{enterprise_id}/vehicles/{vehicle_id} —— 解绑车辆
- GET    /api/v1/enterprises/{enterprise_id}/vehicles/{vehicle_id}/profile —— 单车详情聚合
- POST   /api/v1/enterprises/{enterprise_id}/vehicles/{vehicle_id}/confirm —— 手动确认
- POST   /api/v1/enterprises/{enterprise_id}/vehicles/{vehicle_id}/reject —— 拒绝
- POST   /api/v1/enterprises/{enterprise_id}/vehicles/batch-confirm —— 批量确认
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import or_, desc, text
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator
from typing import Optional, List

from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import assert_enterprise_team_access
from app.models.user import User
from app.models.enterprise import Enterprise
from app.models.enterprise_vehicle import (
    EnterpriseVehicle, EnterpriseVehicleStatus,
    ApprovalStatus, StationVinWhitelist,
)
from app.models.charging_order import ChargingOrder
from app.models.fleet_v2g import FleetV2GRevenue
from app.models.carbon_emission import CarbonReductionRecord
from app.models.enterprise_transaction import EnterpriseTransaction

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_write_permission("fleet:manage"))])


# ========== Schemas ==========

class VehicleBindRequest(BaseModel):
    plate_number: str = Field(..., max_length=20)
    vin: str
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None

    @validator('vin')
    def validate_vin(cls, v):
        v = v.strip().upper()
        if len(v) != 17:
            raise ValueError('VIN码必须为17位')
        return v


class VehicleStatusUpdateRequest(BaseModel):
    status: EnterpriseVehicleStatus


class BatchConfirmRequest(BaseModel):
    vehicle_ids: List[int]


class RejectRequest(BaseModel):
    reason: Optional[str] = None


# ========== Helpers ==========

def _vehicle_to_dict(v: EnterpriseVehicle) -> dict:
    return {
        "id": v.id,
        "enterprise_id": v.enterprise_id,
        "plate_number": v.plate_number,
        "vin": v.vin,
        "driver_name": v.driver_name,
        "driver_phone": v.driver_phone,
        "status": v.status.value if v.status else "active",
        "approval_status": v.approval_status.value if v.approval_status else "pending",
        "confirmed_at": v.confirmed_at.isoformat() if v.confirmed_at else None,
        "confirmed_by": v.confirmed_by,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


def _charging_order_to_dict(o: ChargingOrder) -> dict:
    return {
        "id": o.id,
        "order_no": o.order_no,
        "station_id": o.station_id,
        "device_id": o.device_id,
        "vehicle_id": o.vehicle_id,
        "plate_number": o.plate_number,
        "start_time": o.start_time.isoformat() if o.start_time else None,
        "end_time": o.end_time.isoformat() if o.end_time else None,
        "duration_minutes": o.duration_minutes or 0,
        "charged_kwh": float(o.charged_kwh or 0),
        "electricity_fee": float(o.electricity_fee or 0),
        "service_fee": float(o.service_fee or 0),
        "total_amount": float(o.total_amount or 0),
        "paid_amount": float(o.paid_amount or 0),
        "order_status": o.order_status.value if o.order_status else None,
        "payment_status": o.payment_status.value if o.payment_status else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def _v2g_revenue_to_dict(r: FleetV2GRevenue) -> dict:
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


def _carbon_record_to_dict(c: CarbonReductionRecord) -> dict:
    return {
        "id": c.id,
        "enterprise_id": c.enterprise_id,
        "vehicle_id": c.vehicle_id,
        "record_date": c.record_date.isoformat() if c.record_date else None,
        "charge_energy_kwh": float(c.charge_energy_kwh or 0),
        "grid_factor": float(c.grid_factor or 0),
        "fuel_factor": float(c.fuel_factor or 0),
        "carbon_reduction_kg": float(c.carbon_reduction_kg or 0),
        "equivalent_fuel_saved_liters": float(c.equivalent_fuel_saved_liters or 0),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _transaction_to_dict(t: EnterpriseTransaction) -> dict:
    return {
        "id": t.id,
        "enterprise_id": t.enterprise_id,
        "vehicle_id": t.vehicle_id,
        "type": t.type.value if t.type else None,
        "amount": float(t.amount or 0),
        "balance_after": float(t.balance_after or 0),
        "order_id": t.order_id,
        "remark": t.remark,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


# ========== Auto-confirm rules ==========

def _get_auto_confirm_config(db: Session) -> dict:
    """从 system_configs 表读取自动确认规则配置。

    配置 key: "fleet_auto_confirm"
    JSON 结构:
    {
        "enabled": false,
        "balance_threshold": 10000,   # 预储值余额>此值自动通过
        "whitelist_enterprise_codes": []  # 白名单企业编码自动通过
    }
    """
    try:
        row = db.execute(
            text("SELECT config_value FROM system_configs WHERE config_key = 'fleet_auto_confirm'")
        ).fetchone()
        if row:
            import json
            return json.loads(row[0])
    except Exception as e:
        logger.warning("读取自动确认配置失败: %s", e)
    return {"enabled": False, "balance_threshold": 0, "whitelist_enterprise_codes": []}


def _evaluate_auto_confirm(db: Session, enterprise: Enterprise) -> bool:
    """评估是否自动确认车辆"""
    config = _get_auto_confirm_config(db)
    if not config.get("enabled"):
        return False

    # 规则1: 白名单企业编码
    wl_codes = config.get("whitelist_enterprise_codes", [])
    if wl_codes and enterprise.code in wl_codes:
        return True

    # 规则2: 预储值余额 > 阈值
    threshold = config.get("balance_threshold", 0)
    if threshold and float(enterprise.balance or 0) >= float(threshold):
        return True

    return False


# ========== VIN Whitelist helpers ==========

def _sync_vin_whitelist_on_confirm(db: Session, vehicle: EnterpriseVehicle):
    """车辆确认后，将 VIN 加入所有相关场站的白名单。

    如果企业的充电策略限定了 allowed_station_ids，则加到这些场站；
    否则不限定（空列表=不限），此处可选择加入所有场站或不加。
    为安全起见：只在策略明确指定场站时才加入白名单。
    如果没有策略或不限场站，则加入所有场站。
    """
    from app.models.fleet_charging_policy import FleetChargingPolicy
    from app.models.station import Station

    # 查找企业的充电策略
    policy = db.query(FleetChargingPolicy).filter(
        FleetChargingPolicy.enterprise_id == vehicle.enterprise_id,
        FleetChargingPolicy.enable == True,
    ).first()

    if policy and policy.allowed_station_ids:
        station_ids = policy.allowed_station_ids
    else:
        # 没有限定场站策略 -> 加入所有场站
        all_stations = db.query(Station).all()
        station_ids = [s.id for s in all_stations]

    for sid in station_ids:
        # 检查是否已存在
        existing = db.query(StationVinWhitelist).filter(
            StationVinWhitelist.station_id == sid,
            StationVinWhitelist.vin == vehicle.vin,
        ).first()
        if not existing:
            entry = StationVinWhitelist(
                station_id=sid,
                vin=vehicle.vin,
                enterprise_id=vehicle.enterprise_id,
                source="vehicle_confirm",
            )
            db.add(entry)


def _remove_vin_whitelist(db: Session, vin: str):
    """移除 VIN 在所有场站的白名单记录"""
    db.query(StationVinWhitelist).filter(
        StationVinWhitelist.vin == vin
    ).delete()


# ========== API Endpoints ==========

@router.get("", summary="获取企业车辆列表")
def list_enterprise_vehicles(
    enterprise_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    approval_status: Optional[str] = Query(None, description="确认状态筛选: pending/confirmed/rejected"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取企业车辆列表"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 企业车辆；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)

    query = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.enterprise_id == enterprise_id
    )
    if approval_status:
        query = query.filter(EnterpriseVehicle.approval_status == approval_status)

    total = query.count()
    items = query.order_by(EnterpriseVehicle.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return paginated_response(
        items=[_vehicle_to_dict(v) for v in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", summary="绑定车辆")
def bind_vehicle(
    enterprise_id: int,
    data: VehicleBindRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """为企业绑定车辆，默认 approval_status=pending，触发自动确认规则评估"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可为本 team 企业绑定车辆；越权/不存在 → 404。
    # assert 返回 Enterprise ORM，复用供自动确认规则评估。
    enterprise = assert_enterprise_team_access(db, enterprise_id, user)

    # 检查 VIN 是否已被绑定
    existing = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.vin == data.vin
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"VIN {data.vin} 已被绑定")

    vehicle = EnterpriseVehicle(
        enterprise_id=enterprise_id,
        plate_number=data.plate_number,
        vin=data.vin,
        driver_name=data.driver_name,
        driver_phone=data.driver_phone,
        status=EnterpriseVehicleStatus.ACTIVE,
        approval_status=ApprovalStatus.PENDING,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    # 自动确认规则评估
    if _evaluate_auto_confirm(db, enterprise):
        vehicle.approval_status = ApprovalStatus.CONFIRMED
        vehicle.confirmed_at = datetime.now(timezone.utc)
        vehicle.confirmed_by = "auto"
        _sync_vin_whitelist_on_confirm(db, vehicle)
        db.commit()
        db.refresh(vehicle)

    return success_response(_vehicle_to_dict(vehicle), message="车辆绑定成功")


@router.patch("/{vehicle_id}", summary="变更车辆状态")
def update_vehicle_status(
    enterprise_id: int,
    vehicle_id: int,
    data: VehicleStatusUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """变更企业车辆状态"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可改本 team 企业车辆；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)

    vehicle = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.id == vehicle_id,
        EnterpriseVehicle.enterprise_id == enterprise_id,
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="车辆不存在")

    vehicle.status = data.status
    db.commit()
    db.refresh(vehicle)

    return success_response(_vehicle_to_dict(vehicle), message="车辆状态变更成功")


@router.delete("/{vehicle_id}", summary="解绑车辆")
def unbind_vehicle(
    enterprise_id: int,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """解绑企业车辆，同时移除 VIN 白名单"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可解绑本 team 企业车辆；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)

    vehicle = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.id == vehicle_id,
        EnterpriseVehicle.enterprise_id == enterprise_id,
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="车辆不存在")

    # 移除 VIN 白名单
    _remove_vin_whitelist(db, vehicle.vin)

    # 级联处置子引用（卡 54dc3406）：v2g 计划/收益、维保、保险随车辆删除；
    # 司机分配/告警规则与记录/交易流水的弱引用置空保留，防裸删 FK 500/孤儿
    from app.services.fk_cascade import purge_enterprise_vehicle_children
    purge_enterprise_vehicle_children(db, vehicle.id)

    db.delete(vehicle)
    db.commit()

    return action_response(message="车辆解绑成功")


@router.get("/{vehicle_id}/profile", summary="车辆详情聚合")
def get_vehicle_profile(
    enterprise_id: int,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """单车详情聚合：车辆信息 + 充电历史 + V2G收益 + 碳减排 + 账户流水。

    各数据源独立 try/except 容错：任一段查询异常或无数据返回空，不抛 500。
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 企业车辆；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)

    vehicle = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.id == vehicle_id,
        EnterpriseVehicle.enterprise_id == enterprise_id,
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="车辆不存在")

    result = {"vehicle": _vehicle_to_dict(vehicle)}

    # 充电历史：ChargingOrder 无 enterprise_id，按 vehicle_id / plate_number 关联，取最近50条
    try:
        conds = [ChargingOrder.vehicle_id == vehicle.id]
        if vehicle.plate_number:
            conds.append(ChargingOrder.plate_number == vehicle.plate_number)
        orders = (
            db.query(ChargingOrder)
            .filter(or_(*conds))
            .order_by(desc(ChargingOrder.created_at))
            .limit(50)
            .all()
        )
        result["charging_history"] = [_charging_order_to_dict(o) for o in orders]
    except Exception as e:
        logger.warning("车辆%s充电历史查询失败: %s", vehicle.id, e)
        result["charging_history"] = []

    # V2G：收益记录 + 总收益
    try:
        revenues = (
            db.query(FleetV2GRevenue)
            .filter(
                FleetV2GRevenue.enterprise_id == enterprise_id,
                FleetV2GRevenue.vehicle_id == vehicle.id,
            )
            .order_by(desc(FleetV2GRevenue.record_date))
            .limit(50)
            .all()
        )
        records = [_v2g_revenue_to_dict(r) for r in revenues]
        result["v2g"] = {
            "records": records,
            "total_revenue": round(sum(r["total_revenue"] for r in records), 2),
        }
    except Exception as e:
        logger.warning("车辆%s V2G查询失败: %s", vehicle.id, e)
        result["v2g"] = {"records": [], "total_revenue": 0}

    # 碳减排记录
    try:
        carbons = (
            db.query(CarbonReductionRecord)
            .filter(
                CarbonReductionRecord.enterprise_id == enterprise_id,
                CarbonReductionRecord.vehicle_id == vehicle.id,
            )
            .order_by(desc(CarbonReductionRecord.record_date))
            .limit(50)
            .all()
        )
        result["carbon"] = [_carbon_record_to_dict(c) for c in carbons]
    except Exception as e:
        logger.warning("车辆%s碳排放查询失败: %s", vehicle.id, e)
        result["carbon"] = []

    # 账户流水
    try:
        txns = (
            db.query(EnterpriseTransaction)
            .filter(
                EnterpriseTransaction.enterprise_id == enterprise_id,
                EnterpriseTransaction.vehicle_id == vehicle.id,
            )
            .order_by(desc(EnterpriseTransaction.created_at))
            .limit(50)
            .all()
        )
        result["transactions"] = [_transaction_to_dict(t) for t in txns]
    except Exception as e:
        logger.warning("车辆%s账户流水查询失败: %s", vehicle.id, e)
        result["transactions"] = []

    return success_response(result, message="车辆详情聚合")


# ========== 确认流端点 ==========

@router.post("/{vehicle_id}/confirm", summary="手动确认车辆")
def confirm_vehicle(
    enterprise_id: int,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动确认车辆 → confirmed，同步 VIN 入场站白名单"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可确认本 team 企业车辆；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)

    vehicle = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.id == vehicle_id,
        EnterpriseVehicle.enterprise_id == enterprise_id,
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="车辆不存在")

    if vehicle.approval_status == ApprovalStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="车辆已确认，无需重复操作")

    vehicle.approval_status = ApprovalStatus.CONFIRMED
    vehicle.confirmed_at = datetime.now(timezone.utc)
    vehicle.confirmed_by = "manual"

    # 同步 VIN 白名单
    _sync_vin_whitelist_on_confirm(db, vehicle)

    db.commit()
    db.refresh(vehicle)

    return success_response(_vehicle_to_dict(vehicle), message="车辆确认成功")


@router.post("/{vehicle_id}/reject", summary="拒绝车辆")
def reject_vehicle(
    enterprise_id: int,
    vehicle_id: int,
    data: RejectRequest = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """拒绝车辆 → rejected，移除 VIN 白名单（可重新提交）"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可拒绝本 team 企业车辆；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)

    vehicle = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.id == vehicle_id,
        EnterpriseVehicle.enterprise_id == enterprise_id,
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="车辆不存在")

    vehicle.approval_status = ApprovalStatus.REJECTED
    vehicle.confirmed_at = None
    vehicle.confirmed_by = None

    # 移除 VIN 白名单
    _remove_vin_whitelist(db, vehicle.vin)

    db.commit()
    db.refresh(vehicle)

    return success_response(_vehicle_to_dict(vehicle), message="车辆已拒绝")


@router.post("/batch-confirm", summary="批量确认车辆")
def batch_confirm_vehicles(
    enterprise_id: int,
    data: BatchConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量确认车辆 → confirmed，同步 VIN 白名单"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可批量确认本 team 企业车辆；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)

    if not data.vehicle_ids:
        raise HTTPException(status_code=400, detail="vehicle_ids 不能为空")

    vehicles = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.id.in_(data.vehicle_ids),
        EnterpriseVehicle.enterprise_id == enterprise_id,
    ).all()

    if not vehicles:
        raise HTTPException(status_code=404, detail="未找到指定车辆")

    confirmed_ids = []
    skipped_ids = []
    for v in vehicles:
        if v.approval_status == ApprovalStatus.CONFIRMED:
            skipped_ids.append(v.id)
            continue
        v.approval_status = ApprovalStatus.CONFIRMED
        v.confirmed_at = datetime.now(timezone.utc)
        v.confirmed_by = "batch"
        _sync_vin_whitelist_on_confirm(db, v)
        confirmed_ids.append(v.id)

    db.commit()

    return success_response({
        "confirmed_ids": confirmed_ids,
        "skipped_ids": skipped_ids,
        "total_requested": len(data.vehicle_ids),
        "total_confirmed": len(confirmed_ids),
    }, message=f"批量确认完成: {len(confirmed_ids)}辆确认, {len(skipped_ids)}辆跳过")
