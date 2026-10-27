"""
企业充电策略管理 API - fleet-platform-spec §4.3 规划表

挂载前缀 /fleet (见 api/v1/__init__.py), 实际路径:
- GET    /api/v1/fleet/policies              策略列表(企业筛选)
- POST   /api/v1/fleet/policies              创建策略
- PUT    /api/v1/fleet/policies/{id}         更新策略
- DELETE /api/v1/fleet/policies/{id}         删除策略
- GET    /api/v1/fleet/policies/check        校验站点/时段/日限额(返回 allowed+reason)
"""
from datetime import datetime
from typing import List, Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import assert_enterprise_team_access, team_scope
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.enterprise import Enterprise
from app.models.fleet_charging_policy import FleetChargingPolicy
from app.models.user import User
from app.tasks.tz_utils import biz_day_bounds_utc_naive, today_in_biz_tz

router = APIRouter(dependencies=[Depends(require_write_permission("fleet:manage"))])

logger = logging.getLogger(__name__)


# ─── Schemas ───

class PolicyCreateRequest(BaseModel):
    enterprise_id: int
    daily_kwh_limit: float = Field(0.0, ge=0.0, description="企业日充电限额(kWh), 0表示不限")
    allowed_time_slots: Optional[List[str]] = Field(None, description="允许时段, 如 ['谷','平']; 空/缺省表示不限")
    allowed_station_ids: Optional[List[int]] = Field(None, description="允许站点ID列表; 空/缺省表示不限")
    enable: bool = True


class PolicyUpdateRequest(BaseModel):
    daily_kwh_limit: Optional[float] = Field(None, ge=0.0)
    allowed_time_slots: Optional[List[str]] = None
    allowed_station_ids: Optional[List[int]] = None
    enable: Optional[bool] = None


# ─── Helpers ───

def _policy_to_dict(p: FleetChargingPolicy) -> dict:
    return {
        "id": p.id,
        "enterprise_id": p.enterprise_id,
        "daily_kwh_limit": p.daily_kwh_limit if p.daily_kwh_limit is not None else 0.0,
        "allowed_time_slots": p.allowed_time_slots or [],
        "allowed_station_ids": p.allowed_station_ids or [],
        "enable": bool(p.enable),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _get_or_404(db: Session, policy_id: int) -> FleetChargingPolicy:
    policy = db.query(FleetChargingPolicy).filter(FleetChargingPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="充电策略不存在")
    return policy


def _today_used_kwh(db: Session, enterprise_id: int) -> float:
    """企业当日(业务时区/上海日界)累计充电量(kWh), 经车辆关联聚合, 排除已取消订单。

    ChargingOrder.created_at 以 aware-UTC 写入但 SQLite DateTime 落库即 naive-UTC,
    故窗口用 biz_day_bounds_utc_naive 把业务日 [00:00,24:00) 换算为 naive-UTC 区间,
    与卡 ba16a9ff 前的 UTC 零点相比, 修正上海 00:00-08:00 订单被计入昨日/漏计的 8h 错窗。
    """
    day_start, _ = biz_day_bounds_utc_naive(today_in_biz_tz())
    total = (
        db.query(func.coalesce(func.sum(ChargingOrder.charged_kwh), 0))
        .join(EnterpriseVehicle, EnterpriseVehicle.id == ChargingOrder.vehicle_id)
        .filter(
            EnterpriseVehicle.enterprise_id == enterprise_id,
            ChargingOrder.created_at >= day_start,
            ChargingOrder.order_status != OrderStatus.CANCELLED,
        )
        .scalar()
    )
    return float(total or 0.0)


def _active_policy(db: Session, enterprise_id: int) -> Optional[FleetChargingPolicy]:
    """取企业最新一条启用策略(无则 None)。"""
    return (
        db.query(FleetChargingPolicy)
        .filter(
            FleetChargingPolicy.enterprise_id == enterprise_id,
            FleetChargingPolicy.enable.is_(True),
        )
        .order_by(desc(FleetChargingPolicy.id))
        .first()
    )


# ─── Endpoints ───
# 注意: /check 必须在 /{policy_id} 之前注册, 否则会被路径参数吞掉。

@router.get("", summary="获取企业充电策略列表")
def list_policies(
    enterprise_id: Optional[int] = Query(None, description="企业ID筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取充电策略列表, 支持按企业筛选。"""
    query = db.query(FleetChargingPolicy)
    scope = team_scope(current_user)
    if scope is not None:
        # FleetChargingPolicy.enterprise_id 为非空FK, join即内联, 无孤儿行被outerjoin差异
        query = query.join(Enterprise, Enterprise.id == FleetChargingPolicy.enterprise_id).filter(
            Enterprise.owner_team_id == scope
        )
    if enterprise_id is not None:
        assert_enterprise_team_access(db, enterprise_id, current_user)
        query = query.filter(FleetChargingPolicy.enterprise_id == enterprise_id)

    total = query.count()
    items = (
        query.order_by(FleetChargingPolicy.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated_response(
        [_policy_to_dict(p) for p in items], total, page, page_size
    )


@router.post("", summary="创建企业充电策略")
def create_policy(
    data: PolicyCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建企业充电策略。"""
    assert_enterprise_team_access(db, data.enterprise_id, current_user)

    policy = FleetChargingPolicy(
        enterprise_id=data.enterprise_id,
        daily_kwh_limit=data.daily_kwh_limit,
        allowed_time_slots=data.allowed_time_slots,
        allowed_station_ids=data.allowed_station_ids,
        enable=data.enable,
    )
    db.add(policy)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("充电策略创建冲突 enterprise_id=%s", data.enterprise_id)
        raise HTTPException(status_code=409, detail="充电策略写入冲突")
    except Exception:
        db.rollback()
        logger.exception("充电策略创建失败 enterprise_id=%s", data.enterprise_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(policy)
    return success_response(_policy_to_dict(policy), message="充电策略创建成功")


@router.get("/check", summary="校验充电是否被策略允许")
def check_policy(
    enterprise_id: int = Query(..., gt=0, description="企业ID"),
    station_id: int = Query(..., gt=0, description="站点ID"),
    time_slot: str = Query(..., description="时段, 如 峰/平/谷"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    校验企业在指定站点/时段是否允许充电:
    - 无启用策略 -> 放行
    - 站点白名单(非空时): station_id 必须在列表
    - 时段白名单(非空时): time_slot 必须在列表
    - 日限额(>0时): 当日累计已达限额则拒绝
    """
    assert_enterprise_team_access(db, enterprise_id, current_user)
    policy = _active_policy(db, enterprise_id)
    used_today = _today_used_kwh(db, enterprise_id)

    base = {
        "enterprise_id": enterprise_id,
        "station_id": station_id,
        "time_slot": time_slot,
        "used_today_kwh": used_today,
    }

    if not policy:
        return success_response({
            **base,
            "allowed": True,
            "reason": "未配置启用的充电策略，允许充电",
            "policy_id": None,
            "daily_kwh_limit": None,
        })

    base["policy_id"] = policy.id
    base["daily_kwh_limit"] = policy.daily_kwh_limit

    reasons = []
    # 站点白名单(非空才校验)
    allowed_stations = policy.allowed_station_ids or []
    if allowed_stations and station_id not in allowed_stations:
        reasons.append(f"站点 {station_id} 不在允许列表 {allowed_stations}")
    # 时段白名单(非空才校验)
    allowed_slots = policy.allowed_time_slots or []
    if allowed_slots and time_slot not in allowed_slots:
        reasons.append(f"时段 {time_slot} 不在允许时段 {allowed_slots}")
    # 日限额(>0才校验)
    if policy.daily_kwh_limit and policy.daily_kwh_limit > 0 and used_today >= policy.daily_kwh_limit:
        reasons.append(f"当日已充电 {used_today} kWh，达到日限额 {policy.daily_kwh_limit} kWh")

    if reasons:
        return success_response({**base, "allowed": False, "reason": "；".join(reasons)})
    return success_response({**base, "allowed": True, "reason": "符合充电策略"})


@router.put("/{policy_id}", summary="更新企业充电策略")
def update_policy(
    policy_id: int,
    data: PolicyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新充电策略, 仅覆盖传入字段。"""
    policy = _get_or_404(db, policy_id)
    assert_enterprise_team_access(db, policy.enterprise_id, current_user)
    if data.daily_kwh_limit is not None:
        policy.daily_kwh_limit = data.daily_kwh_limit
    if data.allowed_time_slots is not None:
        policy.allowed_time_slots = data.allowed_time_slots
    if data.allowed_station_ids is not None:
        policy.allowed_station_ids = data.allowed_station_ids
    if data.enable is not None:
        policy.enable = data.enable
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("充电策略更新冲突 policy_id=%s", policy_id)
        raise HTTPException(status_code=409, detail="充电策略写入冲突")
    except Exception:
        db.rollback()
        logger.exception("充电策略更新失败 policy_id=%s", policy_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(policy)
    return success_response(_policy_to_dict(policy), message="充电策略更新成功")


@router.delete("/{policy_id}", summary="删除企业充电策略")
def delete_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除充电策略。"""
    policy = _get_or_404(db, policy_id)
    assert_enterprise_team_access(db, policy.enterprise_id, current_user)
    db.delete(policy)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("充电策略删除失败 policy_id=%s", policy_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return action_response(message="充电策略删除成功")
