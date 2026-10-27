"""
场站 VIN 充电授权白名单 API

功能:
- GET /api/v1/stations/{station_id}/vin-whitelist —— 获取场站的 VIN 白名单
- DELETE /api/v1/stations/{station_id}/vin-whitelist/{vin} —— 移除单个 VIN
- POST /api/v1/stations/{station_id}/vin-whitelist —— 手动添加 VIN
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, validator

from app.api.deps import assert_station_team_access
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.models.enterprise_vehicle import StationVinWhitelist
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_write_permission("fleet:manage"))])


class ManualVinAddRequest(BaseModel):
    vin: str
    enterprise_id: int

    @validator('vin')
    def validate_vin(cls, v):
        v = v.strip().upper()
        if len(v) != 17:
            raise ValueError('VIN码必须为17位')
        return v


@router.get("/{station_id}/vin-whitelist", summary="获取场站 VIN 白名单")
def get_station_vin_whitelist(
    station_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取场站的 VIN 充电授权白名单"""
    # team scoping（任务卡 1c19b59a）：站点归属校验前置，跨团队 → 404。
    assert_station_team_access(db, station_id, user)
    query = db.query(StationVinWhitelist).filter(
        StationVinWhitelist.station_id == station_id
    )
    total = query.count()
    items = query.order_by(StationVinWhitelist.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return paginated_response(
        items=[
            {
                "id": w.id,
                "station_id": w.station_id,
                "vin": w.vin,
                "enterprise_id": w.enterprise_id,
                "source": w.source,
                "created_at": w.created_at.isoformat() if w.created_at else None,
            }
            for w in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{station_id}/vin-whitelist", summary="手动添加 VIN 到白名单")
def add_vin_to_whitelist(
    station_id: int,
    data: ManualVinAddRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动添加 VIN 到场站白名单"""
    # team scoping（任务卡 1c19b59a）：站点归属校验前置，跨团队 → 404。
    assert_station_team_access(db, station_id, user)
    existing = db.query(StationVinWhitelist).filter(
        StationVinWhitelist.station_id == station_id,
        StationVinWhitelist.vin == data.vin,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"VIN {data.vin} 已在白名单中")

    entry = StationVinWhitelist(
        station_id=station_id,
        vin=data.vin,
        enterprise_id=data.enterprise_id,
        source="manual",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return success_response(
        {
            "id": entry.id,
            "station_id": entry.station_id,
            "vin": entry.vin,
            "enterprise_id": entry.enterprise_id,
            "source": entry.source,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        },
        message="VIN 添加成功",
    )


@router.delete("/{station_id}/vin-whitelist/{vin}", summary="从白名单移除 VIN")
def remove_vin_from_whitelist(
    station_id: int,
    vin: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """从场站白名单移除指定 VIN"""
    # team scoping（任务卡 1c19b59a）：站点归属校验前置（先于 VIN 查找），
    # 跨团队 → 404 站点不存在，不泄露资源存在。
    assert_station_team_access(db, station_id, user)
    entry = db.query(StationVinWhitelist).filter(
        StationVinWhitelist.station_id == station_id,
        StationVinWhitelist.vin == vin,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="VIN 不在白名单中")

    db.delete(entry)
    db.commit()

    return action_response(message="VIN 已从白名单移除")
