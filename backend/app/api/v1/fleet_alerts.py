"""
车队告警规则引擎 API - SPEC §4.3

提供端点:
- POST   /api/v1/fleet/alert-rules            创建告警规则
- GET    /api/v1/fleet/alert-rules            查询规则列表(分页+企业/类型过滤)
- PUT    /api/v1/fleet/alert-rules/{id}       更新规则
- DELETE /api/v1/fleet/alert-rules/{id}       删除规则
- POST   /api/v1/fleet/alert-rules/{id}/test  模拟触发一条告警记录
- GET    /api/v1/fleet/alert-records          查询告警记录(分页+企业/状态过滤)
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import assert_enterprise_team_access
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.fleet_alert_rule import (
    FleetAlertRule,
    FleetAlertRecord,
    AlertRuleType,
    AlertRecordStatus,
)
from app.models.user import User
from app.schemas.fleet_alert import (
    FleetAlertRuleCreate,
    FleetAlertRuleUpdate,
    FleetAlertTestPayload,
)

router = APIRouter(tags=["车队告警规则引擎"], dependencies=[Depends(require_write_permission("fleet:manage"))])


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

_VALID_RULE_TYPES = {t.value for t in AlertRuleType}


def _rule_to_dict(r: FleetAlertRule) -> dict:
    return {
        "id": r.id,
        "enterprise_id": r.enterprise_id,
        "rule_type": r.rule_type.value if hasattr(r.rule_type, "value") else str(r.rule_type),
        "threshold": r.threshold or {},
        "notify_channels": r.notify_channels or [],
        "enable": bool(r.enable),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _record_to_dict(rec: FleetAlertRecord) -> dict:
    return {
        "id": rec.id,
        "rule_id": rec.rule_id,
        "enterprise_id": rec.enterprise_id,
        "vehicle_id": rec.vehicle_id,
        "plate_number": rec.plate_number,
        "triggered_at": rec.triggered_at.isoformat() if rec.triggered_at else None,
        "alert_value": rec.alert_value,
        "notified": bool(rec.notified),
        "status": rec.status.value if hasattr(rec.status, "value") else str(rec.status),
    }


# ----------------------------------------------------------------------
# 规则 CRUD
# ----------------------------------------------------------------------

@router.post("/alert-rules", summary="创建车队告警规则")
def create_rule(
    data: FleetAlertRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建一条车队告警规则。"""
    if data.rule_type not in _VALID_RULE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"无效规则类型 '{data.rule_type}', 可选: {', '.join(sorted(_VALID_RULE_TYPES))}",
        )

    assert_enterprise_team_access(db, data.enterprise_id, current_user)

    rule = FleetAlertRule(
        enterprise_id=data.enterprise_id,
        rule_type=AlertRuleType(data.rule_type),
        threshold=data.threshold,
        notify_channels=data.notify_channels,
        enable=data.enable,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return success_response(_rule_to_dict(rule), "告警规则创建成功")


@router.get("/alert-rules", summary="查询车队告警规则列表")
def list_rules(
    enterprise_id: int = Query(..., gt=0, description="企业ID"),
    rule_type: Optional[str] = Query(None, description="可选规则类型过滤"),
    enable: Optional[bool] = Query(None, description="可选启用状态过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询告警规则列表, 支持企业/类型/启用状态过滤。"""
    assert_enterprise_team_access(db, enterprise_id, current_user)
    query = db.query(FleetAlertRule).filter(FleetAlertRule.enterprise_id == enterprise_id)
    if rule_type:
        if rule_type not in _VALID_RULE_TYPES:
            raise HTTPException(status_code=400, detail=f"无效规则类型 '{rule_type}'")
        query = query.filter(FleetAlertRule.rule_type == AlertRuleType(rule_type))
    if enable is not None:
        query = query.filter(FleetAlertRule.enable.is_(enable))

    total = query.count()
    rules = (
        query.order_by(desc(FleetAlertRule.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated_response([_rule_to_dict(r) for r in rules], total, page, page_size)


@router.put("/alert-rules/{rule_id}", summary="更新车队告警规则")
def update_rule(
    rule_id: int,
    data: FleetAlertRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新告警规则, 仅传入的字段会被更新。"""
    rule = db.query(FleetAlertRule).filter(FleetAlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")
    assert_enterprise_team_access(db, rule.enterprise_id, current_user)

    if data.rule_type is not None:
        if data.rule_type not in _VALID_RULE_TYPES:
            raise HTTPException(status_code=400, detail=f"无效规则类型 '{data.rule_type}'")
        rule.rule_type = AlertRuleType(data.rule_type)
    if data.threshold is not None:
        rule.threshold = data.threshold
    if data.notify_channels is not None:
        rule.notify_channels = data.notify_channels
    if data.enable is not None:
        rule.enable = data.enable

    db.commit()
    db.refresh(rule)
    return success_response(_rule_to_dict(rule), "告警规则更新成功")


@router.delete("/alert-rules/{rule_id}", summary="删除车队告警规则")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除告警规则(同时清理其触发的告警记录)。"""
    rule = db.query(FleetAlertRule).filter(FleetAlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")
    assert_enterprise_team_access(db, rule.enterprise_id, current_user)

    # D3: 先删记录再删规则需事务保护, 任一步失败必须 rollback 避免数据不一致
    try:
        db.query(FleetAlertRecord).filter(FleetAlertRecord.rule_id == rule_id).delete()
        db.delete(rule)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="删除告警规则失败, 请重试")
    return success_response({"id": rule_id}, "告警规则已删除")


@router.post("/alert-rules/{rule_id}/test", summary="模拟触发告警记录")
def trigger_test(
    rule_id: int,
    payload: Optional[FleetAlertTestPayload] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """模拟触发一条告警记录, 用于规则配置后的手动验证。"""
    rule = db.query(FleetAlertRule).filter(FleetAlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")
    assert_enterprise_team_access(db, rule.enterprise_id, current_user)

    vehicle_id = None
    plate_number = None
    if payload and payload.vehicle_id:
        vehicle_id = payload.vehicle_id
        # D1(安全): 必须校验 vehicle 属于规则所在企业, 杜绝跨租户 vehicle_id 泄露车牌
        vehicle = db.query(EnterpriseVehicle).filter(
            EnterpriseVehicle.id == vehicle_id,
            EnterpriseVehicle.enterprise_id == rule.enterprise_id,
        ).first()
        if vehicle:
            plate_number = vehicle.plate_number
        else:
            # 跨企业或不存在: 置空 vehicle_id, 避免脏绑定其他企业车辆
            vehicle_id = None

    rec = FleetAlertRecord(
        rule_id=rule.id,
        enterprise_id=rule.enterprise_id,
        vehicle_id=vehicle_id,
        plate_number=plate_number,
        triggered_at=datetime.now(timezone.utc),
        alert_value="[test] manually triggered",
        notified=False,
        status=AlertRecordStatus.ACTIVE,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return success_response(_record_to_dict(rec), "告警已模拟触发")


# ----------------------------------------------------------------------
# 告警记录查询
# ----------------------------------------------------------------------

@router.get("/alert-records", summary="查询车队告警记录")
def list_records(
    enterprise_id: int = Query(..., gt=0, description="企业ID"),
    status: Optional[str] = Query(None, description="可选状态过滤: active/acknowledged/resolved"),
    vehicle_id: Optional[int] = Query(None, gt=0, description="可选车辆ID过滤"),
    rule_type: Optional[str] = Query(None, description="可选规则类型过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询告警记录列表, 支持企业/状态/车辆/规则类型过滤。"""
    assert_enterprise_team_access(db, enterprise_id, current_user)
    query = db.query(FleetAlertRecord).filter(FleetAlertRecord.enterprise_id == enterprise_id)
    if status:
        if status not in {s.value for s in AlertRecordStatus}:
            raise HTTPException(status_code=400, detail=f"无效状态 '{status}'")
        query = query.filter(FleetAlertRecord.status == AlertRecordStatus(status))
    if vehicle_id:
        query = query.filter(FleetAlertRecord.vehicle_id == vehicle_id)
    if rule_type:
        if rule_type not in _VALID_RULE_TYPES:
            raise HTTPException(status_code=400, detail=f"无效规则类型 '{rule_type}'")
        query = query.join(FleetAlertRule, FleetAlertRecord.rule_id == FleetAlertRule.id).filter(
            FleetAlertRule.rule_type == AlertRuleType(rule_type)
        )

    total = query.count()
    records = (
        query.order_by(desc(FleetAlertRecord.triggered_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated_response([_record_to_dict(r) for r in records], total, page, page_size)
