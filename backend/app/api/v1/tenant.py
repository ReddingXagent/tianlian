"""
多租户管理 API

功能:
- 管理员: 创建/管理租户
- 租户信息查询
- 租户统计
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Literal, Optional
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.database import get_db
from app.services.audit_service import audit_service
from app.core.response import success_response, paginated_response, action_response
from app.models.tenant import Tenant
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter(tags=["多租户管理"], dependencies=[Depends(get_current_user)])


# ========== Helpers ==========

def _get_role(user: User) -> str:
    """获取用户角色字符串"""
    return user.role if isinstance(user.role, str) else user.role.value


def _is_admin(user: User) -> bool:
    """检查是否为管理员"""
    return _get_role(user) in ("admin", "super_admin")


# ========== Schemas ==========

class TenantCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    max_stations: int = 10
    max_devices: int = 100
    max_users: int = 20


class TenantResetPasswordBody(BaseModel):
    """租户用户密码重置请求体 (卡 922b2fba): 空 new_password → 生成临时密码。"""
    new_password: Optional[str] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    status: Optional[Literal["active", "inactive", "suspended"]] = None
    max_stations: Optional[int] = None
    max_devices: Optional[int] = None
    max_users: Optional[int] = None


# ========== API Endpoints ==========

@router.get("/stats/summary", summary="租户统计摘要")
def tenant_stats_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取租户统计摘要 - 总数/活跃数"""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可查看统计")
    total = db.query(Tenant).count()
    active = db.query(Tenant).filter(Tenant.status == "active").count()
    inactive = db.query(Tenant).filter(Tenant.status == "inactive").count()
    suspended = db.query(Tenant).filter(Tenant.status == "suspended").count()
    return success_response({
        "total": total,
        "active": active,
        "inactive": inactive,
        "suspended": suspended,
    })


@router.get("", summary="获取租户列表")
def list_tenants(
    status: Optional[str] = None,
    keyword: Optional[str] = Query(None),
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取租户列表"""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="无权访问租户管理")

    query = db.query(Tenant)

    if status:
        query = query.filter(Tenant.status == status)

    # 支持 keyword 和 search 两种参数
    search_term = keyword or search
    if search_term:
        query = query.filter(
            (Tenant.name.ilike(f"%{search_term}%")) |
            (Tenant.code.ilike(f"%{search_term}%"))
        )

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response(
        items=[{
            "id": t.id,
            "name": t.name,
            "code": t.code,
            "description": t.description,
            "status": t.status,
            "is_active": t.is_active,
            "contact_name": t.contact_name,
            "contact_phone": t.contact_phone,
            "contact_email": t.contact_email,
            "max_stations": t.max_stations,
            "max_devices": t.max_devices,
            "max_users": t.max_users,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        } for t in items],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("", summary="创建租户")
def create_tenant(
    data: TenantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建新租户"""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可创建租户")

    if db.query(Tenant).filter(Tenant.code == data.code).first():
        raise HTTPException(status_code=400, detail="租户编码已存在")

    tenant = Tenant(**data.dict())
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="create", module="tenants",
            target_id=str(tenant.id), target_desc=f"创建租户:{tenant.name}",
        )
    except Exception:
        pass

    return success_response({
        "id": tenant.id,
        "name": tenant.name,
        "code": tenant.code,
        "status": tenant.status,
    }, message="租户创建成功")


@router.get("/{tenant_id}", summary="获取租户详情")
def get_tenant_detail(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取租户详情"""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="无权访问")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")

    return success_response({
        "id": tenant.id,
        "name": tenant.name,
        "code": tenant.code,
        "description": tenant.description,
        "contact_name": tenant.contact_name,
        "contact_phone": tenant.contact_phone,
        "contact_email": tenant.contact_email,
        "status": tenant.status,
        "is_active": tenant.is_active,
        "max_stations": tenant.max_stations,
        "max_devices": tenant.max_devices,
        "max_users": tenant.max_users,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None,
        "expired_at": tenant.expired_at.isoformat() if tenant.expired_at else None,
    })


@router.put("/{tenant_id}", summary="更新租户")
def update_tenant(
    tenant_id: int,
    data: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新租户信息"""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="无权访问")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")

    for field, value in data.dict(exclude_unset=True).items():
        setattr(tenant, field, value)

    tenant.updated_at = datetime.now(timezone.utc)
    db.commit()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="update", module="tenants",
            target_id=str(tenant_id), target_desc=f"更新租户:{tenant.name}",
        )
    except Exception:
        pass

    return action_response(message="租户更新成功")


@router.delete("/{tenant_id}", summary="删除租户")
def delete_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除租户"""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可删除租户")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")

    # 卡 21205721: 服务层显式级联（config/audit/usage/brand NOT NULL 级联删,
    # station/vehicle/api_key 等可空引用置空保留）
    from app.services.fk_cascade import purge_tenant_children
    purge_tenant_children(db, tenant_id)

    db.delete(tenant)
    db.commit()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="delete", module="tenants",
            target_id=str(tenant_id), target_desc=f"删除租户:{tenant.name}",
        )
    except Exception:
        pass

    return action_response(message="租户删除成功")


@router.get("/{tenant_id}/users", summary="获取租户用户列表")
def get_tenant_users(
    tenant_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取租户下的用户列表。

    User 无 tenant_id 字段（多租户隔离尚未落地），通过 tenant.code → Team.code
    关联到 Team，再取 User.team_id 成员；无匹配 Team 时返回空列表，不造数据。
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="无权访问租户管理")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")

    from app.models.user import Team

    team_ids = [t.id for t in db.query(Team.id).filter(Team.code == tenant.code).all()]

    query = db.query(User).filter(User.team_id.in_(team_ids)) if team_ids else None
    if query is None:
        return paginated_response([], 0, page, page_size)

    total = query.count()
    items = query.order_by(User.id.asc()).offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response(
        items=[{
            "id": u.id,
            "username": u.username,
            "real_name": u.real_name,
            "role": u.role.value if u.role else "engineer",
            "phone": u.phone,
            "status": u.status,
            "last_login": u.last_login.isoformat() if u.last_login else None,
        } for u in items],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{tenant_id}/stats", summary="获取租户统计")
def get_tenant_stats(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取租户统计数据"""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="无权访问")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")

    from app.models.station import Station
    from app.models.device import Device

    stats = {
        "total_stations": db.query(Station).filter(Station.tenant_id == tenant_id).count(),
        "total_devices": db.query(Device).filter(Device.station.has(tenant_id=tenant_id)).count(),
        "total_users": 0,
        "active_alarms": 0,
        "pending_workorders": 0,
    }

    return success_response(stats)


@router.get("/{tenant_id}/usage", summary="查询租户用量趋势")
def get_tenant_usage(
    tenant_id: int,
    date_from: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取租户用量趋势（历史快照）+ 当前实时用量"""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="无权访问")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")

    from app.models.tenant_usage import TenantUsage
    from app.services.tenant_usage_service import compute_current_usage

    def _parse_date(d: str):
        try:
            return datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")

    query = db.query(TenantUsage).filter(TenantUsage.tenant_id == tenant_id)
    if date_from:
        query = query.filter(TenantUsage.record_date >= _parse_date(date_from))
    if date_to:
        query = query.filter(TenantUsage.record_date <= _parse_date(date_to))

    records = query.order_by(TenantUsage.record_date.asc()).all()

    return success_response({
        "tenant_id": tenant_id,
        "current": compute_current_usage(db, tenant_id),
        "history": [{
            "record_date": r.record_date.isoformat() if r.record_date else None,
            "station_count": r.station_count,
            "device_count": r.device_count,
            "user_count": r.user_count,
            "storage_used_gb": r.storage_used_gb,
            "api_calls_today": r.api_calls_today,
        } for r in records],
    })


@router.post("/{tenant_id}/users/{user_id}/reset-password", summary="重置租户用户密码")
def reset_tenant_user_password(
    tenant_id: int,
    user_id: int,
    body: TenantResetPasswordBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """重置租户下指定用户密码 (卡 922b2fba)。

    校验用户归属该租户 (Tenant.code → Team.code → User.team_id 关联链,
    与 get_tenant_users 同源), 不归属 → 404 不泄露; 密码逻辑复用
    users.reset_user_password。
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可重置用户密码")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")

    from app.models.user import Team
    from app.api.v1.users import reset_user_password

    team_ids = [t.id for t in db.query(Team.id).filter(Team.code == tenant.code).all()]
    user = db.query(User).filter(User.id == user_id, User.team_id.in_(team_ids)).first() if team_ids else None
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return success_response(reset_user_password(db, user, body.new_password))
