"""场站运维授权管理 API — 运维分离架构 (任务卡 00d7d49a)。

实际路径 (router 不挂前缀, 内部用完整路径):
- POST   /api/v1/station-maintenance-grants        运营公司授权运维团队
- GET    /api/v1/station-maintenance-grants        授权列表 (运营看发出/运维看收到)
- DELETE /api/v1/station-maintenance-grants/{id}   撤销授权 (仅授权方)
- GET    /api/v1/stations/maintained               运维团队视角: 被授权站点

越权一律 404 (不泄露存在), 与 deps.assert_*_team_access 同源。
仅 ops_company 可发起授权; 授权目标须为 maintenance_team; 站点须属授权方。
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import is_platform_admin
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.models.station import Station
from app.models.station_maintenance_grant import (
    StationMaintenanceGrant, GrantScope, GrantStatus,
)
from app.models.user import Team, TeamType, User

# 写端点收紧: viewer/auditor 只读不可写。operate:manage 覆盖运营/运维操作级角色
# (OPERATOR/ENGINEER/DISPATCHER 等)。真正的 ops_company 身份校验在端点内
# (_require_ops_company), 因为 require_write_permission 只到角色权限矩阵层, 不感知 team.type。
router = APIRouter(
    dependencies=[Depends(get_current_user), Depends(require_write_permission("operate:manage"))]
)


# ─── Schemas ───

class GrantCreateRequest(BaseModel):
    station_id: int = Field(..., gt=0, description="授权场站ID (须属授权方运营公司)")
    maintenance_team_id: int = Field(..., gt=0, description="被授权运维团队ID (须为 maintenance_team)")
    scope: GrantScope = Field(GrantScope.FULL, description="授权范围")
    expires_at: Optional[datetime] = Field(None, description="过期时间(空=永久)")
    remark: Optional[str] = Field(None, max_length=500, description="授权备注")


# ─── Helpers ───

def _resolve_user_team_type(db: Session, user: User):
    """显式查 DB 取 user.team.type (避免异步上下文 lazy-load); 无 team → None。"""
    if user.team_id is None:
        return None
    t = db.query(Team.type).filter(Team.id == user.team_id).scalar()
    return t.value if hasattr(t, "value") else t


def _require_ops_company(db: Session, user: User) -> None:
    """发起授权/撤销须为 ops_company (运营公司)。平台 admin 走 is_platform_admin 旁路。

    非运营公司 (运维团队/车队) → 403。
    """
    if is_platform_admin(user):
        return
    team_type = _resolve_user_team_type(db, user)
    if team_type != TeamType.OPS_COMPANY.value:
        raise HTTPException(status_code=403, detail="仅运营公司可管理运维授权")


def _grant_to_dict(g: StationMaintenanceGrant) -> dict:
    def _iso(dt):
        if dt is None:
            return None
        # naive(SQLite DB 墙钟) 直接 isoformat; aware 去掉 tz 与历史口径一致
        tz = getattr(dt, "tzinfo", None)
        return dt.replace(tzinfo=None).isoformat() if tz else dt.isoformat()

    return {
        "id": g.id,
        "station_id": g.station_id,
        "maintenance_team_id": g.maintenance_team_id,
        "granted_by_team_id": g.granted_by_team_id,
        "scope": g.scope.value if hasattr(g.scope, "value") else g.scope,
        "status": g.status.value if hasattr(g.status, "value") else g.status,
        "granted_at": _iso(g.granted_at),
        "revoked_at": _iso(g.revoked_at),
        "expires_at": _iso(g.expires_at),
        "remark": g.remark,
    }


def _get_or_404(db: Session, grant_id: int) -> StationMaintenanceGrant:
    g = db.query(StationMaintenanceGrant).filter(StationMaintenanceGrant.id == grant_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="授权不存在")
    return g


# ─── Endpoints: 授权 CRUD ───

@router.post("/station-maintenance-grants", summary="运营公司授权运维团队运维某场站")
def create_grant(
    data: GrantCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建运维授权。校验:
      - 仅 ops_company 可操作 (平台 admin 旁路);
      - 站点须属当前运营公司 team (跨团队 → 404, 不泄露存在);
      - 授权目标须为 MAINTENANCE_TEAM 类型 (否则 400);
      - 重复 active 授权 → 409; 撤销后重授权复活原行。
    """
    _require_ops_company(db, current_user)

    # 平台 admin 须显式指定 granted_by_team_id? —— admin 旁路但 station 须存在。
    # admin 不归属 ops_company, 此处 admin 仅能授权已存在站点 (归属校验对 admin 跳过 team 匹配)。
    station = db.query(Station).filter(Station.id == data.station_id).first()
    if station is None:
        raise HTTPException(status_code=404, detail="站点不存在")
    if not is_platform_admin(current_user) and station.team_id != current_user.team_id:
        # 站点不属于本运营公司 → 404 (不泄露存在)
        raise HTTPException(status_code=404, detail="站点不存在")

    # 授权目标须为 maintenance_team
    target_type = db.query(Team.type).filter(Team.id == data.maintenance_team_id).scalar()
    target_val = target_type.value if hasattr(target_type, "value") else target_type
    if target_val != TeamType.MAINTENANCE_TEAM.value:
        raise HTTPException(status_code=400, detail="授权目标须为运维团队(maintenance_team)")

    # 授权方 team_id: admin 旁路时取 station.team_id (站点归属的运营公司)
    grantor_team_id = current_user.team_id if not is_platform_admin(current_user) else station.team_id

    # 重复 active 授权检测 (含已撤销行复活语义)
    existing = (
        db.query(StationMaintenanceGrant)
        .filter(
            StationMaintenanceGrant.station_id == data.station_id,
            StationMaintenanceGrant.maintenance_team_id == data.maintenance_team_id,
        )
        .first()
    )
    if existing is not None:
        if existing.status == GrantStatus.ACTIVE:
            raise HTTPException(status_code=409, detail="该场站对该运维团队的授权已存在")
        # 已撤销/过期行 → 复活为新授权 (保留唯一索引不冲突)
        existing.scope = data.scope
        existing.status = GrantStatus.ACTIVE
        existing.granted_by_team_id = grantor_team_id
        existing.granted_at = datetime.now(timezone.utc)
        existing.revoked_at = None
        existing.expires_at = data.expires_at
        existing.remark = data.remark
        db.commit()
        db.refresh(existing)
        return success_response(_grant_to_dict(existing), "授权创建成功")

    grant = StationMaintenanceGrant(
        station_id=data.station_id,
        maintenance_team_id=data.maintenance_team_id,
        granted_by_team_id=grantor_team_id,
        scope=data.scope,
        status=GrantStatus.ACTIVE,
        expires_at=data.expires_at,
        remark=data.remark,
    )
    db.add(grant)
    try:
        db.commit()
    except IntegrityError:
        # 并发撞唯一索引 (station_id, maintenance_team_id) → 409
        db.rollback()
        raise HTTPException(status_code=409, detail="该场站对该运维团队的授权已存在")
    db.refresh(grant)
    return success_response(_grant_to_dict(grant), "授权创建成功")


@router.get("/station-maintenance-grants", summary="运维授权列表")
def list_grants(
    station_id: Optional[int] = Query(None, gt=0, description="场站ID筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """授权列表, 按主体视角过滤:
      - 平台 admin → 全部;
      - ops_company → 自己发出的授权 (granted_by_team_id == user.team_id);
      - maintenance_team → 自己收到的授权 (maintenance_team_id == user.team_id);
      - 其它 (fleet 等) → 空。
    """
    query = db.query(StationMaintenanceGrant)
    if not is_platform_admin(current_user):
        team_type = _resolve_user_team_type(db, current_user)
        if team_type == TeamType.OPS_COMPANY.value:
            query = query.filter(StationMaintenanceGrant.granted_by_team_id == current_user.team_id)
        elif team_type == TeamType.MAINTENANCE_TEAM.value:
            query = query.filter(StationMaintenanceGrant.maintenance_team_id == current_user.team_id)
        else:
            query = query.filter(StationMaintenanceGrant.id == -1)  # 永空
    if station_id is not None:
        query = query.filter(StationMaintenanceGrant.station_id == station_id)

    total = query.count()
    items = (
        query.order_by(StationMaintenanceGrant.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated_response([_grant_to_dict(g) for g in items], total, page, page_size)


@router.delete("/station-maintenance-grants/{grant_id}", summary="撤销运维授权")
def revoke_grant(
    grant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """撤销授权 (软删除 → status=revoked + revoked_at)。仅授权方运营公司可操作。

    资源归属语义 (非"能力资格"): 非授权方一律 404 (不泄露存在) —— 含运维团队、
    其它运营公司、未授权主体。与 deps.assert_*_team_access 同源。
    admin 旁路 (平台级)。
    """
    grant = _get_or_404(db, grant_id)

    # 仅授权方可撤销; admin 旁路。非授权方 → 404 (不泄露存在)
    if not is_platform_admin(current_user) and grant.granted_by_team_id != current_user.team_id:
        raise HTTPException(status_code=404, detail="授权不存在")

    if grant.status == GrantStatus.ACTIVE:
        grant.status = GrantStatus.REVOKED
        grant.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(grant)
    return action_response(message="授权已撤销")


# ─── Endpoint: 运维团队视角 — 被授权站点 ───

@router.get("/stations/maintained", summary="运维团队视角: 自己被授权的场站列表")
def list_maintained_stations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回当前用户 (运维团队) 被 active 授权的场站列表。

    平台 admin → 全部场站; ops_company → 自有名下站点; maintenance_team → 被授权站点;
    其它 → 空。
    """
    if is_platform_admin(current_user):
        stations = db.query(Station).all()
    else:
        team_type = _resolve_user_team_type(db, current_user)
        if team_type == TeamType.OPS_COMPANY.value:
            stations = db.query(Station).filter(Station.team_id == current_user.team_id).all()
        elif team_type == TeamType.MAINTENANCE_TEAM.value:
            grant_station_ids = (
                db.query(StationMaintenanceGrant.station_id)
                .filter(
                    StationMaintenanceGrant.maintenance_team_id == current_user.team_id,
                    StationMaintenanceGrant.status == GrantStatus.ACTIVE,
                )
                .all()
            )
            ids = [r[0] for r in grant_station_ids]
            stations = db.query(Station).filter(Station.id.in_(ids)).all() if ids else []
        else:
            stations = []

    return success_response([
        {
            "id": st.id,
            "name": st.name,
            "code": st.code,
            "status": st.status.value if hasattr(st.status, "value") else st.status,
        }
        for st in stations
    ])
