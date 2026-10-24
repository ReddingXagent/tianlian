"""C端用户车辆管理 API (用户端契约§8 P2 §8.6, 卡 36396f29).

挂 /business 前缀:
- GET    /business/vehicles                      本人车辆列表 (分页, 默认车在前)
- POST   /business/vehicles                      添加车辆 (车牌必填, VIN 可空)
- DELETE /business/vehicles/{vehicle_id}         删除车辆
- PATCH  /business/vehicles/{vehicle_id}/default 设为默认 (幂等, 清除原默认)

认证: C 端 token (get_current_end_user, aud=end_user), 运营 token 一律 401。
隔离: 仅本人车辆可见/可操作, 非本人 vehicle_id 一律 404 (不泄露存在性, 同 §7 订单口径)。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.business_end_user_auth import get_current_end_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.end_user import EndUser
from app.models.end_user_vehicle import EndUserVehicle
from app.services.wx_pay import response as rsp

router = APIRouter()


class VehicleCreateRequest(BaseModel):
    plate_number: str = Field(..., max_length=20)
    vin: Optional[str] = Field(None, min_length=17, max_length=17)
    brand: Optional[str] = Field(None, max_length=50)
    model: Optional[str] = Field(None, max_length=100)

    @validator("plate_number")
    def plate_not_blank(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("车牌号不能为空")
        return v

    @validator("vin")
    def vin_upper(cls, v):
        if v is None:
            return None
        v = v.strip().upper()
        return v if v else None


def _vehicle_to_dict(v: EndUserVehicle) -> dict:
    return {
        "vehicle_id": v.id,
        "plate_number": v.plate_number,
        "vin": v.vin,
        "brand": v.brand,
        "model": v.model,
        "is_default": bool(v.is_default),
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _get_owned_vehicle(db: Session, end_user_id: int, vehicle_id: int) -> EndUserVehicle:
    vehicle = (
        db.query(EndUserVehicle)
        .filter(
            EndUserVehicle.id == vehicle_id,
            EndUserVehicle.end_user_id == end_user_id,
        )
        .first()
    )
    if vehicle is None:
        raise HTTPException(404, "车辆不存在")
    return vehicle


@router.get("/vehicles", summary="本人车辆列表 (契约§8.6)")
@limiter.limit("60/minute")
def list_vehicles(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    q = db.query(EndUserVehicle).filter(EndUserVehicle.end_user_id == end_user.id)
    total = q.count()
    items = (
        q.order_by(EndUserVehicle.is_default.desc(), EndUserVehicle.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rsp.ok(
        {
            "items": [_vehicle_to_dict(v) for v in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/vehicles", summary="添加车辆 (契约§8.6)")
@limiter.limit("30/minute")
def create_vehicle(
    request: Request,
    body: VehicleCreateRequest,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    duplicate = (
        db.query(EndUserVehicle)
        .filter(
            EndUserVehicle.end_user_id == end_user.id,
            EndUserVehicle.plate_number == body.plate_number,
        )
        .first()
    )
    if duplicate is not None:
        raise HTTPException(409, "VEHICLE_DUPLICATE_PLATE")

    has_any = (
        db.query(EndUserVehicle.id)
        .filter(EndUserVehicle.end_user_id == end_user.id)
        .first()
        is not None
    )
    vehicle = EndUserVehicle(
        end_user_id=end_user.id,
        plate_number=body.plate_number,
        vin=body.vin,
        brand=body.brand,
        model=body.model,
        is_default=not has_any,  # 首辆车自动默认
    )
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError:
        # 并发双击竞态: 预检查漏检, INSERT 撞 uq_end_user_vehicle_plate 兜底
        # (卡 d74344ed)。全 rollback 而非 savepoint (SQLite + pysqlite 的
        # SAVEPOINT 在 IntegrityError 后状态清理不可靠), 再回查确认是同用户
        # 同车牌冲突 → 契约§8.6 的 409; 其他约束冲突仍走全局兜底不吞错。
        db.rollback()
        loser = (
            db.query(EndUserVehicle)
            .filter(
                EndUserVehicle.end_user_id == end_user.id,
                EndUserVehicle.plate_number == body.plate_number,
            )
            .first()
        )
        if loser is not None:
            raise HTTPException(409, "VEHICLE_DUPLICATE_PLATE")
        raise
    db.refresh(vehicle)
    return rsp.ok(_vehicle_to_dict(vehicle))


@router.delete("/vehicles/{vehicle_id}", summary="删除车辆 (契约§8.6)")
@limiter.limit("30/minute")
def delete_vehicle(
    request: Request,
    vehicle_id: int,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    vehicle = _get_owned_vehicle(db, end_user.id, vehicle_id)
    db.delete(vehicle)
    db.commit()
    return rsp.ok({"deleted": True, "vehicle_id": vehicle_id})


@router.patch("/vehicles/{vehicle_id}/default", summary="设为默认车辆 (契约§8.6)")
@limiter.limit("30/minute")
def set_default_vehicle(
    request: Request,
    vehicle_id: int,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    vehicle = _get_owned_vehicle(db, end_user.id, vehicle_id)
    if not vehicle.is_default:
        db.query(EndUserVehicle).filter(
            EndUserVehicle.end_user_id == end_user.id,
            EndUserVehicle.is_default.is_(True),
            EndUserVehicle.id != vehicle.id,
        ).update({"is_default": False})
        vehicle.is_default = True
        db.commit()
        db.refresh(vehicle)
    return rsp.ok(_vehicle_to_dict(vehicle))
