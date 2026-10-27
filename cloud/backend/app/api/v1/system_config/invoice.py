"""
系统配置 - 发票配置域 (admin spec §2.3)
/invoice (GET/PUT)
JSON 配置存取复用 common._load_json_config / _save_json_config
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.api.deps import assert_config_domain_access
from app.models.user import User
from app.core.response import success_response
from app.services.audit_service import audit_service

from .common import _check_admin_or_permission, _load_json_config, _save_json_config

router = APIRouter(tags=["系统配置"])


DEFAULT_INVOICE_CONFIG = {
    "provider": "百望云",
    "enabled": False,
    "tax_rate": 6,
    "company_name": "",
    "tax_number": "",
    "bank_name": "",
    "bank_account": "",
    "company_address": "",
    "company_phone": "",
    "reviewer": "",
    "payer": "",
    "params": {},
}


class InvoiceConfigUpdate(BaseModel):
    provider: Optional[str] = Field(None, max_length=100)
    enabled: Optional[bool] = None
    tax_rate: Optional[float] = Field(None, ge=0, le=100)
    company_name: Optional[str] = Field(None, max_length=200)
    tax_number: Optional[str] = Field(None, max_length=50)
    bank_name: Optional[str] = Field(None, max_length=200)
    bank_account: Optional[str] = Field(None, max_length=50)
    company_address: Optional[str] = Field(None, max_length=300)
    company_phone: Optional[str] = Field(None, max_length=30)
    reviewer: Optional[str] = Field(None, max_length=50)
    payer: Optional[str] = Field(None, max_length=50)
    params: Optional[dict] = None


@router.get("/invoice")
async def get_invoice_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取发票配置 (invoice 域: 平台管理员 + ops_company 可读)"""
    assert_config_domain_access(db, current_user, "invoice")
    config = _load_json_config(db, "invoice_config", DEFAULT_INVOICE_CONFIG)
    return success_response(config)


@router.put("/invoice")
def update_invoice_config(
    data: InvoiceConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新发票配置 (invoice 域: 平台管理员 + ops_company 可写)"""
    assert_config_domain_access(db, current_user, "invoice")
    _check_admin_or_permission(current_user, "system:config")

    config = _load_json_config(db, "invoice_config", DEFAULT_INVOICE_CONFIG)
    old_value = dict(config)
    updates = data.dict(exclude_none=True)
    config.update(updates)
    _save_json_config(db, "invoice_config", config, "invoice")
    db.commit()

    audit_service.log_crud(
        user_id=current_user.id,
        username=current_user.username,
        action="update",
        module="system_config",
        target_desc="更新发票配置",
        old_value=str(old_value),
        new_value=str(config),
    )

    return success_response(config, message="发票配置已更新")
