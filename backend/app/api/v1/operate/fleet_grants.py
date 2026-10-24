"""
车队三级授权管理 API - 公司→场站→设备(桩级白名单) (卡 a1468299)

挂载前缀 /operate (见 api/v1/__init__.py), 实际路径:
- POST   /api/v1/operate/fleet-grants            创建授权(整站/桩级)
- GET    /api/v1/operate/fleet-grants            授权列表(按企业/场站筛选)
- DELETE /api/v1/operate/fleet-grants/{id}       删除授权

运营公司视角: 仅可给本团队(owner_team)企业授权本团队场站/设备, 杜绝跨公司授权。
越权一律 404(不泄露存在), 与 deps.assert_*_team_access 同源。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import assert_enterprise_team_access, assert_station_team_access
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.models.device import Device
from app.models.enterprise_device_grant import EnterpriseDeviceGrant
from app.models.user import User

router = APIRouter(
    dependencies=[Depends(get_current_user), Depends(require_write_permission("fleet:manage"))]
)


# ─── Schemas ───

class GrantCreateRequest(BaseModel):
    enterprise_id: int = Field(..., gt=0, description="被授权的车队(企业)ID")
    station_id: int = Field(..., gt=0, description="授权场站ID")
    device_id: Optional[int] = Field(None, gt=0, description="桩ID; 空=整站授权, 非空=桩级白名单")
    note: Optional[str] = Field(None, max_length=200, description="授权备注")


# ─── Helpers ───

def _grant_to_dict(g: EnterpriseDeviceGrant) -> dict:
    return {
        "id": g.id,
        "enterprise_id": g.enterprise_id,
        "station_id": g.station_id,
        "device_id": g.device_id,
        "note": g.note,
        # naive datetime(SQLite 无 tz) 直接 isoformat; aware 去 tz 后缀保持历史口径一致
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def _get_or_404(db: Session, grant_id: int) -> EnterpriseDeviceGrant:
    g = db.query(EnterpriseDeviceGrant).filter(EnterpriseDeviceGrant.id == grant_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="授权不存在")
    return g


# ─── Endpoints ───

@router.post("/fleet-grants", summary="创建车队设备授权(整站/桩级)")
def create_grant(
    data: GrantCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建授权。校验: 企业+场站均属当前用户团队; 桩须属于该场站; 整站授权去重。

    device_id 空=整站授权(该站所有桩可充); 非空=桩级白名单(仅该桩)。
    """
    # 企业归属校验 (跨团队 → 404)
    assert_enterprise_team_access(db, data.enterprise_id, current_user)
    # 场站归属校验 (跨团队 → 404)
    assert_station_team_access(db, data.station_id, current_user)

    # 桩级授权: 设备须存在且属于该场站
    if data.device_id is not None:
        device = db.query(Device).filter(Device.id == data.device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")
        if device.station_id != data.station_id:
            raise HTTPException(
                status_code=400,
                detail=f"设备 {device.id} 不属于场站 {data.station_id}",
            )

    # 整站授权应用层去重(SQL 唯一索引对 NULL device_id 不去重)
    if data.device_id is None:
        exists = (
            db.query(EnterpriseDeviceGrant)
            .filter(
                EnterpriseDeviceGrant.enterprise_id == data.enterprise_id,
                EnterpriseDeviceGrant.station_id == data.station_id,
                EnterpriseDeviceGrant.device_id.is_(None),
            )
            .first()
        )
        if exists:
            raise HTTPException(
                status_code=409,
                detail=f"企业 {data.enterprise_id} 对场站 {data.station_id} 的整站授权已存在",
            )

    grant = EnterpriseDeviceGrant(
        enterprise_id=data.enterprise_id,
        station_id=data.station_id,
        device_id=data.device_id,
        note=data.note,
    )
    db.add(grant)
    try:
        db.commit()
    except IntegrityError:
        # 桩级授权重复((enterprise, station, device) 撞唯一索引)
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="该授权已存在(企业+场站+设备 唯一)",
        )
    db.refresh(grant)
    return success_response(_grant_to_dict(grant), "授权创建成功")


@router.get("/fleet-grants", summary="获取车队设备授权列表")
def list_grants(
    enterprise_id: Optional[int] = Query(None, gt=0, description="企业ID筛选"),
    station_id: Optional[int] = Query(None, gt=0, description="场站ID筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """授权列表, 支持按企业/场站筛选。按企业筛选时做团队隔离(跨团队 → 404)。"""
    query = db.query(EnterpriseDeviceGrant)
    if enterprise_id is not None:
        assert_enterprise_team_access(db, enterprise_id, current_user)
        query = query.filter(EnterpriseDeviceGrant.enterprise_id == enterprise_id)
    if station_id is not None:
        query = query.filter(EnterpriseDeviceGrant.station_id == station_id)

    total = query.count()
    items = (
        query.order_by(EnterpriseDeviceGrant.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated_response(
        [_grant_to_dict(g) for g in items], total, page, page_size
    )


@router.delete("/fleet-grants/{grant_id}", summary="删除车队设备授权")
def delete_grant(
    grant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除授权。经 grant→enterprise 归属校验(跨团队 → 404)。"""
    grant = _get_or_404(db, grant_id)
    assert_enterprise_team_access(db, grant.enterprise_id, current_user)
    db.delete(grant)
    db.commit()
    return action_response(message="授权删除成功")
