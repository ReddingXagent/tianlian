"""卡 089b01b2 — C端品牌端点 (端侧路径 GET /tenants/{tenantId}/branding, 契约§1).

端侧扫码/定位后先拿品牌再登录 → 匿名公开 (无 C端 token).
复用 tenant_brand_service.branding_for_tenant; 租户未配置 → 天链默认品牌 (source=default).
鉴权: 公开 (auth.py is_public_path 对 /tenants/{id}/branding 后缀特判放行 enforce_auth).
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.services.tenant_brand_service import branding_for_tenant
from app.services.wx_pay import response as rsp

router = APIRouter()


@router.get("/tenants/{tenant_id}/branding", summary="租户品牌 (契约§1, 公开)")
@limiter.limit("60/minute")
def get_branding(
    request: Request,
    tenant_id: int,
    db: Session = Depends(get_db),
):
    """租户品牌配置; 未配置 / tenant 不存在 → 天链默认品牌 (source=default)."""
    return rsp.ok(branding_for_tenant(db, tenant_id, lightweight=False))
