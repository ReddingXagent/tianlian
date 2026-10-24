"""
运营平台 - 租户品牌 CRUD API (工作卡 28546b66 — 云端配套① 租户品牌服务)

契约: backend/docs/contracts/user-client-contract.md §1 (品牌录入: ops 运营后台，团队级)

端点 (挂在 /operate 前缀下):
- POST /operate/tenant-brands            upsert (按 tenant_id 创建或更新)
- GET  /operate/tenant-brands            列表 (team scoping)
- GET  /operate/tenant-brands/{tenant_id} 详情 (team scoping, 跨团队 → 404)
- DELETE /operate/tenant-brands/{tenant_id} 删除 (team scoping, 跨团队 → 404)

权限门: require_permission("operate:manage") (与 operate/* 同模式)。
team scoping: team_id 取 current_user.team_id (服务端强制, 与 supervision 同源);
admin/平台级豁免 team 过滤。
"""
import logging
import re
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_permission
from app.api.deps import team_scope, assert_team_access
from app.models.user import User
from app.models.tenant import Tenant
from app.models.tenant_brand import TenantBrand

router = APIRouter(dependencies=[Depends(require_permission("operate:manage"))])

logger = logging.getLogger(__name__)

# theme_color 合法 hex: #RGB / #RRGGBB (大小写不敏感)
_HEX_RE = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


# ========== Schemas ==========

class TenantBrandUpsert(BaseModel):
    tenant_id: int = Field(..., description="品牌归属租户 ID (唯一)")
    operator_name: str = Field(..., min_length=1, max_length=100, description="运营商展示名称")
    logo_url: str = Field("", max_length=500, description="logo 绝对 URL (http/https)")
    service_phone: str = Field("", max_length=50, description="客服电话")
    theme_color: str = Field("#00A86B", max_length=20, description="主题色 hex，如 #00A86B")


# ========== Helpers ==========

def _to_dict(b: TenantBrand) -> dict:
    return {
        "id": b.id,
        "tenant_id": b.tenant_id,
        "team_id": b.team_id,
        "operator_name": b.operator_name,
        "logo_url": b.logo_url,
        "service_phone": b.service_phone,
        "theme_color": b.theme_color,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def _validate_theme_color(v: str) -> None:
    if not _HEX_RE.match(v or ""):
        raise HTTPException(400, "theme_color 须为合法 hex，如 #00A86B 或 #abc")


def _validate_logo_url(v: str) -> None:
    """logo_url 非空时须为合法 http/https 绝对 URL；空串允许 (无 logo)。"""
    if not v:
        return
    p = urlparse(v)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise HTTPException(400, "logo_url 须为合法 http(s) 绝对 URL")


def _get_brand_by_tenant(db: Session, tenant_id: int) -> Optional[TenantBrand]:
    """按 tenant_id 取品牌；不存在返回 None。team 归属由调用方用 assert_team_access 校验。"""
    return db.query(TenantBrand).filter(TenantBrand.tenant_id == tenant_id).first()


# ========== CRUD ==========

@router.post("/tenant-brands", summary="租户品牌 upsert (创建或按 tenant_id 更新)")
def upsert_tenant_brand(
    data: TenantBrandUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        _validate_theme_color(data.theme_color)
        _validate_logo_url(data.logo_url)

        # 品牌必须挂在已存在的租户上
        if not db.query(Tenant).filter(Tenant.id == data.tenant_id).first():
            raise HTTPException(404, "租户不存在")

        existing = _get_brand_by_tenant(db, data.tenant_id)
        if existing is not None:
            # 已存在 → 更新；跨团队 → 404 (不泄露存在)
            assert_team_access(current_user, existing.team_id)
            existing.operator_name = data.operator_name
            existing.logo_url = data.logo_url
            existing.service_phone = data.service_phone
            existing.theme_color = data.theme_color
            db.commit()
            db.refresh(existing)
            return success_response(_to_dict(existing), message="租户品牌已更新")

        brand = TenantBrand(
            tenant_id=data.tenant_id,
            team_id=current_user.team_id or 0,  # admin(无 team) → 0，与 supervision 同模式
            operator_name=data.operator_name,
            logo_url=data.logo_url,
            service_phone=data.service_phone,
            theme_color=data.theme_color,
        )
        db.add(brand)
        db.commit()
        db.refresh(brand)
        return success_response(_to_dict(brand), message="租户品牌已创建")
    except HTTPException:
        raise
    except Exception:
        logger.exception("租户品牌 upsert 失败 tenant_id=%s", data.tenant_id)
        raise HTTPException(500, "租户品牌保存失败")


@router.get("/tenant-brands", summary="租户品牌列表 (按团队过滤)")
def list_tenant_brands(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        q = db.query(TenantBrand)
        scope = team_scope(current_user)
        if scope is not None:
            q = q.filter(TenantBrand.team_id == scope)

        total = q.count()
        items = (
            q.order_by(TenantBrand.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return paginated_response(
            items=[_to_dict(b) for b in items],
            total=total, page=page, page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("租户品牌列表查询失败")
        raise HTTPException(500, "租户品牌列表查询失败")


@router.get("/tenant-brands/{tenant_id}", summary="租户品牌详情 (team scoping)")
def get_tenant_brand(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        b = _get_brand_by_tenant(db, tenant_id)
        if b is None:
            raise HTTPException(404, "租户品牌不存在")
        assert_team_access(current_user, b.team_id)
        return success_response(_to_dict(b))
    except HTTPException:
        raise
    except Exception:
        logger.exception("租户品牌详情查询失败 tenant_id=%s", tenant_id)
        raise HTTPException(500, "租户品牌详情查询失败")


@router.delete("/tenant-brands/{tenant_id}", summary="删除租户品牌 (team scoping)")
def delete_tenant_brand(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        b = _get_brand_by_tenant(db, tenant_id)
        if b is None:
            raise HTTPException(404, "租户品牌不存在")
        assert_team_access(current_user, b.team_id)
        db.delete(b)
        db.commit()
        return action_response(message=f"租户 {tenant_id} 品牌已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("租户品牌删除失败 tenant_id=%s", tenant_id)
        raise HTTPException(500, "租户品牌删除失败")
