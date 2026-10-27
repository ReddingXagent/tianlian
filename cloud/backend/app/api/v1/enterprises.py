"""
企业账户管理 API - Phase42 运营管理

提供企业账户的 CRUD 操作:
- GET    /api/v1/enterprises        列表（支持分页和筛选）
- GET    /api/v1/enterprises/{id}   详情
- POST   /api/v1/enterprises        创建
- PUT    /api/v1/enterprises/{id}   更新
- DELETE /api/v1/enterprises/{id}   删除
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Any, Dict, List, Literal
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.enterprise import Enterprise, EnterpriseStatus, enterprise_stations
from app.models.station import Station
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import team_scope, assert_team_access, is_platform_admin

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_write_permission("fleet:manage"))])


# ─── Pydantic 模型 ───

class EnterpriseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="企业名称")
    code: str = Field(..., min_length=1, max_length=50, description="企业编码")
    contact: Optional[str] = Field(None, max_length=100, description="联系人")
    phone: Optional[str] = Field(None, max_length=20, description="联系电话")
    # 余额调减应走专用调整接口（留痕），此处仅守卫非负
    balance: Optional[float] = Field(0.0, ge=0, description="账户余额(元)")
    credit_limit: Optional[float] = Field(0.0, ge=0, description="信用额度(元)")
    default_vehicle_config: Optional[Dict[str, Any]] = Field(None, description="默认车辆配置(JSON)")
    address: Optional[str] = Field(None, max_length=500, description="企业地址")
    description: Optional[str] = Field(None, description="企业描述")
    status: Optional[Literal["active", "inactive", "suspended"]] = Field("active", description="状态: active/inactive/suspended")
    owner_team_id: Optional[int] = Field(None, description="经营团队ID")
    station_ids: Optional[List[int]] = Field(None, description="绑定场站ID列表")


class EnterpriseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="企业名称")
    code: Optional[str] = Field(None, min_length=1, max_length=50, description="企业编码")
    contact: Optional[str] = Field(None, max_length=100, description="联系人")
    phone: Optional[str] = Field(None, max_length=20, description="联系电话")
    # 余额调减应走专用调整接口（留痕），此处仅守卫非负
    balance: Optional[float] = Field(None, ge=0, description="账户余额(元)")
    credit_limit: Optional[float] = Field(None, ge=0, description="信用额度(元)")
    default_vehicle_config: Optional[Dict[str, Any]] = Field(None, description="默认车辆配置(JSON)")
    address: Optional[str] = Field(None, max_length=500, description="企业地址")
    description: Optional[str] = Field(None, description="企业描述")
    status: Optional[Literal["active", "inactive", "suspended"]] = Field(None, description="状态: active/inactive/suspended")
    owner_team_id: Optional[int] = Field(None, description="经营团队ID")


class SetStationsRequest(BaseModel):
    """设置企业绑定场站请求体（覆盖式）"""
    station_ids: List[int] = Field(default_factory=list, description="场站ID列表")


# ─── Helper ───

def _enterprise_to_dict(ent: Enterprise) -> dict:
    return {
        "id": ent.id,
        "name": ent.name,
        "code": ent.code,
        "contact": ent.contact,
        "phone": ent.phone,
        "balance": float(ent.balance) if ent.balance else 0.0,
        "credit_limit": float(ent.credit_limit) if ent.credit_limit else 0.0,
        "default_vehicle_config": ent.default_vehicle_config,
        "address": ent.address,
        "description": ent.description,
        "status": ent.status.value if ent.status else "active",
        "owner_team_id": ent.owner_team_id,
        "created_at": ent.created_at.isoformat() if ent.created_at else None,
        "updated_at": ent.updated_at.isoformat() if ent.updated_at else None,
    }


# ─── API 端点 ───

@router.get("/enterprises")
def list_enterprises(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: Optional[str] = Query(None, description="状态筛选: active/inactive/suspended"),
    keyword: Optional[str] = Query(None, description="名称/编码搜索"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """企业账户列表（支持分页和筛选）

    任务卡 708350b3: team_id 服务端强制——团队级用户仅见本 team 企业
    （按 owner_team_id 过滤）；admin/平台级看全部。
    """
    q = db.query(Enterprise)

    scope = team_scope(current_user)
    if scope is not None:
        q = q.filter(Enterprise.owner_team_id == scope)

    if status:
        try:
            es = EnterpriseStatus(status)
            q = q.filter(Enterprise.status == es)
        except ValueError:
            pass

    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(
            (Enterprise.name.ilike(kw)) | (Enterprise.code.ilike(kw))
        )

    total = q.count()
    items = q.order_by(Enterprise.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()

    return paginated_response(
        items=[_enterprise_to_dict(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/enterprises/{enterprise_id}")
def get_enterprise(
    enterprise_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """企业账户详情"""
    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not ent:
        raise HTTPException(status_code=404, detail="企业账户不存在")
    assert_team_access(current_user, ent.owner_team_id)
    return success_response(_enterprise_to_dict(ent))


@router.post("/enterprises")
def create_enterprise(
    body: EnterpriseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建企业账户

    任务卡 708350b3: owner_team_id 服务端强制——admin 可指定任意团队；
    团队级用户创建的企业归属其本人 team（body owner_team_id 被忽略）。
    """
    # 检查编码唯一性
    existing = db.query(Enterprise).filter(Enterprise.code == body.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"企业编码 '{body.code}' 已存在")

    # owner_team_id 服务端强制：admin 用 body 指定，团队级用户锁本人 team
    owner_team_id = body.owner_team_id if is_platform_admin(current_user) else current_user.team_id

    try:
        ent = Enterprise(
            name=body.name,
            code=body.code,
            contact=body.contact,
            phone=body.phone,
            balance=body.balance,
            credit_limit=body.credit_limit,
            default_vehicle_config=body.default_vehicle_config,
            address=body.address,
            description=body.description,
            status=EnterpriseStatus(body.status) if body.status else EnterpriseStatus.ACTIVE,
            owner_team_id=owner_team_id,
        )
        db.add(ent)
        db.commit()
        db.refresh(ent)

        # 绑定场站（校验归属同一经营团队）
        if body.station_ids:
            _bind_stations(db, ent, body.station_ids)

        return success_response(_enterprise_to_dict(ent), "企业账户创建成功")
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的状态值，请使用 active/inactive/suspended")


@router.put("/enterprises/{enterprise_id}")
def update_enterprise(
    enterprise_id: int,
    body: EnterpriseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新企业账户"""
    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not ent:
        raise HTTPException(status_code=404, detail="企业账户不存在")
    assert_team_access(current_user, ent.owner_team_id)

    if body.name is not None:
        ent.name = body.name
    if body.code is not None:
        existing = db.query(Enterprise).filter(
            Enterprise.code == body.code, Enterprise.id != enterprise_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"企业编码 '{body.code}' 已被占用")
        ent.code = body.code
    if body.contact is not None:
        ent.contact = body.contact
    if body.phone is not None:
        ent.phone = body.phone
    if body.balance is not None or body.credit_limit is not None:
        # 行锁: SELECT ... FOR UPDATE 串行化并发直写, 防止读-改-写丢更新(lost update)。
        # 生产 PostgreSQL 下真正锁行; SQLite 下为 no-op(对照 enterprise_balance_service.deduct)。
        # populate_existing 强制重发 SELECT 刷新 identity-map 陈旧快照(对照 fleet_drivers._lock_account)。
        locked = (
            db.query(Enterprise)
            .filter(Enterprise.id == enterprise_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if locked is None:
            raise HTTPException(status_code=404, detail="企业账户不存在")
        ent = locked
    if body.balance is not None:
        ent.balance = body.balance
    if body.credit_limit is not None:
        ent.credit_limit = body.credit_limit
    if body.default_vehicle_config is not None:
        ent.default_vehicle_config = body.default_vehicle_config
    if body.address is not None:
        ent.address = body.address
    if body.description is not None:
        ent.description = body.description
    if body.status is not None:
        try:
            ent.status = EnterpriseStatus(body.status)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的状态值，请使用 active/inactive/suspended")
    if body.owner_team_id is not None and is_platform_admin(current_user):
        ent.owner_team_id = body.owner_team_id

    db.commit()
    db.refresh(ent)
    return success_response(_enterprise_to_dict(ent), "企业账户更新成功")


@router.delete("/enterprises/{enterprise_id}")
def delete_enterprise(
    enterprise_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除企业账户"""
    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not ent:
        raise HTTPException(status_code=404, detail="企业账户不存在")
    assert_team_access(current_user, ent.owner_team_id)

    # 卡 21205721: 账本完整性优先 —— 存在交易/充值/账单/开票/资金账户或
    # 非零余额时拒绝删除（409），不做级联；干净企业则级联删除 fleet 配置类
    # 子表后删主行
    from app.services.fk_cascade import (
        enterprise_has_ledger_data, purge_enterprise_children,
    )
    if enterprise_has_ledger_data(db, ent):
        raise HTTPException(
            status_code=409,
            detail="该企业存在交易/结算账本数据，禁止删除；请先完成对账清算",
        )
    purge_enterprise_children(db, enterprise_id)

    db.delete(ent)
    db.commit()
    return success_response(None, "企业账户已删除")


# ─── 场站绑定辅助 ───

def _bind_stations(db: Session, ent: Enterprise, station_ids: List[int]):
    """绑定场站到企业，校验场站归属同一经营团队"""
    # 先清除旧绑定
    db.execute(
        delete(enterprise_stations).where(enterprise_stations.c.enterprise_id == ent.id)
    )

    if not station_ids:
        db.commit()
        return

    stations = db.query(Station).filter(Station.id.in_(station_ids)).all()
    found_ids = {s.id for s in stations}
    missing = set(station_ids) - found_ids
    if missing:
        raise HTTPException(status_code=422, detail=f"场站不存在: {missing}")

    # 校验场站归属同一经营团队
    if ent.owner_team_id:
        for st in stations:
            if st.team_id and st.team_id != ent.owner_team_id:
                raise HTTPException(
                    status_code=403,
                    detail=f"场站 '{st.name}' (id={st.id}) 不属于该企业经营团队(team_id={ent.owner_team_id})"
                )

    # 写入新绑定（卡 0e7deb3d 性能优化）：原循环逐条 insert（M 个场站 = M 条 SQL），
    # 改为一次批量 values，行为/顺序一致。
    db.execute(
        enterprise_stations.insert().values(
            [{"enterprise_id": ent.id, "station_id": sid} for sid in station_ids]
        )
    )
    db.commit()


def _station_to_dict(st: Station) -> dict:
    return {
        "id": st.id,
        "name": st.name,
        "code": st.code,
        "address": st.address,
        "status": st.status.value if st.status else None,
        "team_id": st.team_id,
        "lat": st.lat,
        "lon": st.lon,
    }


# ─── 场站绑定 API ───

@router.get("/enterprises/{enterprise_id}/stations")
def list_enterprise_stations(
    enterprise_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取企业已绑定的场站列表"""
    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not ent:
        raise HTTPException(status_code=404, detail="企业账户不存在")
    assert_team_access(current_user, ent.owner_team_id)

    rows = db.execute(
        select(Station).join(enterprise_stations, enterprise_stations.c.station_id == Station.id)
        .where(enterprise_stations.c.enterprise_id == enterprise_id)
    ).scalars().all()

    return success_response([_station_to_dict(s) for s in rows])


@router.put("/enterprises/{enterprise_id}/stations")
def set_enterprise_stations(
    enterprise_id: int,
    data: SetStationsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """设置企业绑定的场站（覆盖式）

    Body: {"station_ids": [1, 2, 3]}
    校验: 场站必须归属同一经营团队
    """
    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not ent:
        raise HTTPException(status_code=404, detail="企业账户不存在")
    assert_team_access(current_user, ent.owner_team_id)

    station_ids: List[int] = data.station_ids

    # 如果有 station_ids 且企业有 owner_team_id，校验归属
    if station_ids and ent.owner_team_id:
        stations = db.query(Station).filter(Station.id.in_(station_ids)).all()
        for st in stations:
            if st.team_id and st.team_id != ent.owner_team_id:
                raise HTTPException(
                    status_code=403,
                    detail=f"场站 '{st.name}' (id={st.id}) 不属于该企业经营团队(team_id={ent.owner_team_id})"
                )

    _bind_stations(db, ent, station_ids)

    # 返回最新绑定列表
    rows = db.execute(
        select(Station).join(enterprise_stations, enterprise_stations.c.station_id == Station.id)
        .where(enterprise_stations.c.enterprise_id == enterprise_id)
    ).scalars().all()

    return success_response([_station_to_dict(s) for s in rows], "场站绑定更新成功")


@router.get("/enterprises/{enterprise_id}/available-stations")
def list_available_stations(
    enterprise_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取该企业经营团队下可选的场站列表（按 owner_team_id 过滤）"""
    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not ent:
        raise HTTPException(status_code=404, detail="企业账户不存在")
    assert_team_access(current_user, ent.owner_team_id)

    q = db.query(Station)
    if ent.owner_team_id:
        q = q.filter(Station.team_id == ent.owner_team_id)
    else:
        # 无经营团队则返回全部
        pass

    stations = q.order_by(Station.name).all()
    return success_response([_station_to_dict(s) for s in stations])
