"""
站点管理 API - 数据库版 (重构编码生成)
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Response
from typing import Literal, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.station import Station
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.models.user import User
from app.api.deps import is_platform_admin, assert_station_team_access, resolve_team_filter
from app.services.code_generator import CodeGenerator
from pydantic import BaseModel, Field

from app.services.audit_service import audit_service
from app.core.response import success_response, paginated_response, action_response
from app.core.cache import cache
from app.services.tenant_brand_service import branding_for_tenant, branding_map

# 契约 §1 缓存: 场站响应 (含 branding) 端侧可缓存 5 分钟 (工作卡 28546b66)
STATION_CACHE_CONTROL = "public, max-age=300"

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_write_permission("station:edit"))])


def _safe_enum_val(v, default="unknown"):
    """安全获取枚举值，兼容DB中不在枚举范围内的旧数据"""
    if v is None:
        return default
    if hasattr(v, 'value'):
        return v.value
    return str(v)


# USING get_db FROM app.core.database


class StationAssignRequest(BaseModel):
    team_id: int = Field(..., description="运维团队ID")


class StationCreate(BaseModel):
    name: str = Field(..., max_length=100)
    region: str = Field("HN", description="区域码，如HN(河南)、GD(广东)等，用于生成编码")
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    operator_id: Optional[int] = None
    operator_name: Optional[str] = None
    team_id: Optional[int] = None
    total_power: Optional[float] = None
    gun_count: Optional[int] = None
    status: Optional[Literal["normal", "maintenance", "closed", "active"]] = "normal"
    venue_type: Optional[str] = Field(None, description="建设场所: highway_station/transport_hub/mall/community/industrial_park")
    total_cost: Optional[float] = Field(None, ge=0, description="站点总成本(元)")
    parking_spots: Optional[int] = Field(None, description="车位数")
    station_type: Optional[str] = Field(None, description="站点类型: public/private/residential")
    contact_person: Optional[str] = Field(None, max_length=50)
    contact_phone: Optional[str] = Field(None, max_length=30)
    description: Optional[str] = None
    pv_capacity: Optional[float] = Field(None, ge=0, description="光伏装机量(kWp)")
    ess_capacity: Optional[float] = Field(None, ge=0, description="储能装机量(kWh)")


class StationUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    code: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    operator_id: Optional[int] = None
    operator_name: Optional[str] = None
    team_id: Optional[int] = None
    total_power: Optional[float] = None
    gun_count: Optional[int] = None
    status: Optional[Literal["normal", "maintenance", "closed", "active"]] = None
    venue_type: Optional[str] = None
    total_cost: Optional[float] = Field(None, ge=0)
    parking_spots: Optional[int] = None
    station_type: Optional[str] = None
    contact_person: Optional[str] = Field(None, max_length=50)
    contact_phone: Optional[str] = Field(None, max_length=30)
    description: Optional[str] = None
    pv_capacity: Optional[float] = Field(None, ge=0, description="光伏装机量(kWp)")
    ess_capacity: Optional[float] = Field(None, ge=0, description="储能装机量(kWh)")


def _station_to_dict(station: Station, branding: Optional[dict] = None) -> dict:
    """Station ORM → dict

    branding: 契约 §1 场站响应附带的品牌对象 (operator_name/logo_url/
    service_phone/theme_color + source)。传入时附加到响应；不传则不含。
    """
    data = {
        "id": station.id,
        "name": station.name,
        "code": station.code,
        "province": station.province,
        "city": station.city,
        "district": station.district,
        "address": station.address,
        "lat": station.lat,
        "lon": station.lon,
        "operator_id": station.operator_id,
        "operator_name": station.operator_name,
        "team_id": station.team_id,
        "total_power": station.total_power,
        "total_devices": station.total_devices,
        "gun_count": station.gun_count,
        "venue_type": station.venue_type,
        "total_cost": float(station.total_cost) if station.total_cost is not None else None,
        "parking_spots": station.parking_spots,
        "station_type": station.station_type,
        "contact_person": station.contact_person,
        "contact_phone": station.contact_phone,
        "description": station.description,
        "pv_capacity": station.pv_capacity,
        "ess_capacity": station.ess_capacity,
        "status": _safe_enum_val(station.status, "normal"),
        "health_score": station.health_score,
        "created_at": station.created_at.isoformat() if station.created_at else None,
        "updated_at": station.updated_at.isoformat() if station.updated_at else None,
    }
    if branding is not None:
        data["branding"] = branding
    return data


@router.get("")
def list_stations(
    response: Response,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    city: Optional[str] = None,
    team_id: Optional[int] = Query(None, description="按团队过滤（卡 2285f54a：admin 可指定任意团队；团队级用户仅限本团队，他团队 403）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取站点列表（team scoping：非 admin 仅返回本 team 站点）。

    可选 ``team_id`` 查询参数（卡 2285f54a）：admin 可按任意团队过滤，
    团队级用户仅允许显式指定本团队（他团队 403、不存在 404）——供
    Tenants TeamDataView 站点 Tab 使用。

    注：移除原 @cached(ttl=30) —— 其 cache key 不含 user.team_id，跨用户同 URL
    会命中同一缓存导致串数据。站点列表非超高频，安全优先（任务卡 1f13817b）。

    契约 §1: 响应携带轻量版 branding (operator_name/theme_color + source)，
    供端侧列表渲染；Cache-Control: public, max-age=300 (工作卡 28546b66)。
    """
    response.headers["Cache-Control"] = STATION_CACHE_CONTROL

    query = db.query(Station)
    scope_team = resolve_team_filter(db, user, team_id)
    if scope_team is not None:
        query = query.filter(Station.team_id == scope_team)
    elif not is_platform_admin(user):
        query = query.filter(Station.team_id == user.team_id)

    if status:
        from app.models.station import StationStatus
        try:
            query = query.filter(Station.status == StationStatus(status))
        except ValueError:
            pass

    if keyword:
        query = query.filter(
            Station.name.contains(keyword) | Station.address.contains(keyword)
        )

    if city:
        query = query.filter(Station.city == city)

    total = query.count()
    items = (
        query.order_by(Station.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # 批量解析本页站点的品牌 (轻量版)，一次查询避免 N+1
    bmap = branding_map(db, [s.tenant_id for s in items], lightweight=True)
    # 站点利用率聚合(2026-10-09 丁哥: 站内充电桩24h活跃采样点占比; 无遥测=None)
    umap = {}
    station_ids = [s.id for s in items]
    if station_ids:
        try:
            from sqlalchemy import text as _text
            rows = db.execute(_text(
                "SELECT d.station_id, "
                "COUNT(*) FILTER (WHERE t.charger_power > 0.5)::float / NULLIF(COUNT(*), 0) "
                "FROM telemetry_charger t JOIN devices d ON t.device_id = d.id "
                "WHERE t.timestamp > now() - interval '24 hours' "
                "AND d.station_id = ANY(:ids) GROUP BY d.station_id"
            ), {"ids": station_ids}).all()
            umap = {r[0]: round(r[1] * 100, 1) for r in rows}
        except Exception:
            pass
    result = [_station_to_dict(s, branding=bmap.get(s.tenant_id)) for s in items]
    for item in result:
        item["utilization_rate"] = umap.get(item.get("id"))
    return paginated_response(
        result,
        total,
        page,
        page_size
    )


@router.get("/{station_id}")
def get_station(
    station_id: int,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取站点详情（team scoping：跨团队 → 404）

    契约 §1: 响应携带全量 branding (operator_name/logo_url/service_phone/
    theme_color + source)；Cache-Control: public, max-age=300 (工作卡 28546b66)。
    """
    response.headers["Cache-Control"] = STATION_CACHE_CONTROL
    station = assert_station_team_access(db, station_id, user)
    branding = branding_for_tenant(db, station.tenant_id, lightweight=False)
    return success_response(_station_to_dict(station, branding=branding))


@router.post("")
def create_station(station: StationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """创建站点 - 自动生成编码。

    team scoping: 非 admin 创建的站点强制归属其本 team（team_id = user.team_id），
    忽略请求体内的 team_id，防止越权指定他组。
    """
    # 自动生成站点编码
    station_code = CodeGenerator.generate_station_code(station.region, db)

    # 检查 code 唯一性
    existing = db.query(Station).filter(Station.code == station_code).first()
    if existing:
        # 如果编码冲突(极少情况),重新生成
        station_code = CodeGenerator.generate_station_code(station.region, db)

    new_station = Station(
        name=station.name,
        code=station_code,  # 使用自动生成的编码
        province=station.province,
        city=station.city,
        district=station.district,
        address=station.address,
        lat=station.lat,
        lon=station.lon,
        operator_id=station.operator_id,
        operator_name=station.operator_name,
        team_id=station.team_id if is_platform_admin(user) else user.team_id,
        total_power=station.total_power,
        gun_count=station.gun_count,
        venue_type=station.venue_type,
        total_cost=station.total_cost,
        parking_spots=station.parking_spots,
        station_type=station.station_type,
        contact_person=station.contact_person,
        contact_phone=station.contact_phone,
        description=station.description,
        pv_capacity=station.pv_capacity,
        ess_capacity=station.ess_capacity,
        status=station.status or "normal"
    )
    db.add(new_station)
    db.commit()
    db.refresh(new_station)
    audit_service.log_crud(user.id, user.username, "create", "stations", str(new_station.id), target_desc=f"station:{new_station.name}(编码:{station_code})")
    cache.delete_pattern("stations:*")
    return success_response(_station_to_dict(
        new_station,
        branding=branding_for_tenant(db, new_station.tenant_id),
    ))


@router.put("/{station_id}")
def update_station(station_id: int, station: StationUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新站点。

    team scoping: 非 admin 仅可改本 team 站点；且禁止改 team_id（防越权转移归属）。
    """
    existing = assert_station_team_access(db, station_id, user)

    update_data = station.model_dump(exclude_unset=True)
    if not is_platform_admin(user):
        update_data.pop("team_id", None)  # 团队级用户不得变更站点归属
    for key, value in update_data.items():
        setattr(existing, key, value)

    db.commit()
    db.refresh(existing)
    audit_service.log_crud(user.id, user.username, "update", "stations", str(station_id), target_desc=f"station:{station.name}")
    cache.delete_pattern("stations:*")
    return success_response(_station_to_dict(
        existing,
        branding=branding_for_tenant(db, existing.tenant_id),
    ))


@router.put("/{station_id}/assign")
def assign_station(station_id: int, req: StationAssignRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """分配站点给运维团队。

    平台级操作：仅 admin/super_admin 可执行；团队级用户 → 403。
    """
    if not is_platform_admin(user):
        raise HTTPException(status_code=403, detail="仅平台管理员可分配站点给团队")
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="站点不存在")

    from app.models.user import Team
    team = db.query(Team).filter(Team.id == req.team_id).first()
    if not team:
        raise HTTPException(status_code=400, detail=f"团队 {req.team_id} 不存在")

    old_team_id = station.team_id
    station.team_id = req.team_id
    db.commit()
    db.refresh(station)

    try:
        audit_service.log_crud(
            user_id=user.id,
            username=user.username,
            action="assign",
            module="stations",
            target_id=str(station_id),
            target_desc=f"station:{station.name}",
            old_value=str(old_team_id) if old_team_id else "None",
            new_value=str(req.team_id),
            detail=f"分配团队: {team.name}({team.code})"
        )
    except Exception:
        pass

    cache.delete_pattern("stations:*")

    return success_response({
        "station_id": station_id,
        "station_name": station.name,
        "team_id": req.team_id,
        "team_name": team.name,
        "message": f"站点已分配给团队 {team.name}"
    })


@router.delete("/{station_id}")
def delete_station(station_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除站点（team scoping：跨团队 → 404）"""
    station = assert_station_team_access(db, station_id, user)

    # 卡 ed537344: 服务层显式级联（子表无 ondelete, 裸 delete 在 PG 下 IntegrityError 500 / SQLite 下留孤儿）
    from app.services.fk_cascade import purge_station_children
    purge_station_children(db, station_id)

    db.delete(station)
    db.commit()
    audit_service.log_crud(user.id, user.username, "delete", "stations", str(station_id))
    cache.delete_pattern("stations:*")
    return action_response(message=f"站点 {station_id} 已删除")
