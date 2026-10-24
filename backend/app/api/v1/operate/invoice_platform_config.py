"""
运营-第三方开票平台配置 API

团队级配置: 每个运营团队管自己的开票平台（百旺/航信/诺诺）
统一挂载在 /api/v1/operate/invoice-platforms 前缀下

任务卡 708350b3: team_id 一律取 current_user.team_id（服务端强制），
客户端 query/body 传入的 team_id 不再信任；admin/平台级豁免 team 过滤。
"""
from typing import Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response
from app.core.crypto_utils import encrypt_field
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_permission
from app.api.deps import team_scope, assert_team_access
from app.core.url_safety import validate_external_url
from app.models.user import User
from app.models.ops_settlement import InvoicePlatformConfig, PlatformType

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_permission("operate:manage"))])


# ========== Schemas ==========
# team_id 一律服务端取 current_user.team_id，不在 schema 中暴露（客户端传入被 Pydantic 忽略）。
# private_key_enc: 入参为明文 RSA 私钥 (PEM), 写入时 Fernet 加密后落 private_key_enc 列。


class InvoicePlatformCreate(BaseModel):
    platform_type: PlatformType = PlatformType.OTHER
    platform_name: str = Field(..., max_length=100)
    api_url: Optional[str] = None
    app_key: Optional[str] = None
    app_secret: Optional[str] = None
    access_token_url: Optional[str] = None
    private_key_enc: Optional[str] = None
    device_no: Optional[str] = None
    callback_url: Optional[str] = None
    ext_config_json: Optional[str] = None
    taxpayer_id: Optional[str] = None
    tax_classification_code: Optional[str] = None
    is_default: bool = False
    enabled: bool = True
    remark: Optional[str] = None

    @field_validator("api_url", "access_token_url")
    @classmethod
    def _validate_outbound_url(cls, v: Optional[str]) -> Optional[str]:
        """SSRF 防护: 出站 URL 必须指向公网 http/https 端点 (卡 fb8b8106)。

        诺诺 provider 会对 api_url / access_token_url 真实出站 (httpx.post),
        不校验即成 SSRF 面。callback_url 为平台回调我方的入站地址,不在此列。
        空值跳过校验(同 webhook update 语义)。
        """
        if v:
            validate_external_url(v)
        return v


class InvoicePlatformUpdate(BaseModel):
    platform_type: Optional[PlatformType] = None
    platform_name: Optional[str] = None
    api_url: Optional[str] = None
    app_key: Optional[str] = None
    app_secret: Optional[str] = None
    access_token_url: Optional[str] = None
    private_key_enc: Optional[str] = None
    device_no: Optional[str] = None
    callback_url: Optional[str] = None
    ext_config_json: Optional[str] = None
    taxpayer_id: Optional[str] = None
    tax_classification_code: Optional[str] = None
    is_default: Optional[bool] = None
    enabled: Optional[bool] = None
    remark: Optional[str] = None

    @field_validator("api_url", "access_token_url")
    @classmethod
    def _validate_outbound_url(cls, v: Optional[str]) -> Optional[str]:
        """SSRF 防护: 出站 URL 必须指向公网 http/https 端点 (卡 fb8b8106)。空值跳过。"""
        if v:
            validate_external_url(v)
        return v


@router.get("/invoice-platforms", summary="当前团队的开票平台列表")
def list_invoice_platforms(
    platform_type: Optional[str] = Query(None, description="平台类型筛选"),
    enabled: Optional[bool] = Query(None, description="启用状态筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询开票平台配置列表（团队隔离；admin 看全部）。"""
    q = db.query(InvoicePlatformConfig)
    scope = team_scope(current_user)
    if scope is not None:
        q = q.filter(InvoicePlatformConfig.team_id == scope)
    if platform_type:
        q = q.filter(InvoicePlatformConfig.platform_type == PlatformType(platform_type))
    if enabled is not None:
        q = q.filter(InvoicePlatformConfig.enabled == enabled)
    items = q.order_by(
        InvoicePlatformConfig.is_default.desc(),
        InvoicePlatformConfig.created_at.desc(),
    ).all()
    return success_response({
        "items": [_to_dict(p) for p in items],
        "total": len(items),
    })


@router.post("/invoice-platforms", summary="新增平台配置")
def create_invoice_platform(
    body: InvoicePlatformCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # team_id 服务端强制，丢弃 body 中客户端传入的 team_id
    team_id = current_user.team_id or 0

    platform = InvoicePlatformConfig(
        team_id=team_id,
        platform_type=body.platform_type,
        platform_name=body.platform_name,
        api_url=body.api_url,
        app_key=body.app_key,
        app_secret=body.app_secret,
        access_token_url=body.access_token_url,
        device_no=body.device_no,
        callback_url=body.callback_url,
        ext_config_json=body.ext_config_json,
        taxpayer_id=body.taxpayer_id,
        tax_classification_code=body.tax_classification_code,
        is_default=body.is_default,
        enabled=body.enabled,
        remark=body.remark,
    )
    # RSA 私钥: 入参明文经 Fernet 加密后落库 (空值跳过)
    try:
        if body.private_key_enc:
            platform.private_key_enc = encrypt_field(body.private_key_enc)
    except Exception:
        logger.exception("平台配置私钥加密失败 team_id=%s", team_id)
        raise HTTPException(status_code=500, detail="私钥加密失败")

    # 若设为默认，先清除该团队其他默认
    if platform.is_default:
        _clear_team_default(db, team_id)

    db.add(platform)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("平台配置创建冲突 team_id=%s", team_id)
        raise HTTPException(status_code=409, detail="平台配置写入冲突")
    except Exception:
        db.rollback()
        logger.exception("平台配置创建失败 team_id=%s", team_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(platform)
    return success_response(_to_dict(platform), "平台配置已创建")


@router.put("/invoice-platforms/{platform_id}", summary="更新平台配置")
def update_invoice_platform(
    platform_id: int,
    body: InvoicePlatformUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.query(InvoicePlatformConfig).filter(InvoicePlatformConfig.id == platform_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="平台配置不存在")
    assert_team_access(current_user, p.team_id)

    updates = body.model_dump(exclude_unset=True)
    # 掩码哨兵回写守卫 (卡 7ada32c8): GET 回填的掩码串不得覆盖真实密钥,
    # 也不得把掩码串当明文私钥 encrypt_field 加密落库
    for secret_field in ("app_secret", "private_key_enc"):
        if _is_masked_secret(updates.get(secret_field)):
            updates.pop(secret_field)
    for field in ["platform_name", "api_url", "app_key", "app_secret",
                   "access_token_url", "device_no", "callback_url", "ext_config_json",
                   "taxpayer_id", "tax_classification_code", "is_default",
                   "enabled", "remark"]:
        if field in updates:
            setattr(p, field, updates[field])

    # RSA 私钥: 入参明文加密后落库; 传空串则清空 (None)
    if "private_key_enc" in updates:
        plain = updates["private_key_enc"]
        try:
            p.private_key_enc = encrypt_field(plain) if plain else None
        except Exception:
            logger.exception("平台配置私钥加密失败 platform_id=%s", platform_id)
            raise HTTPException(status_code=500, detail="私钥加密失败")

    if "platform_type" in updates:
        p.platform_type = updates["platform_type"]

    # 若设为默认，先清除该团队其他默认
    if updates.get("is_default"):
        _clear_team_default(db, p.team_id, exclude_id=platform_id)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("平台配置更新冲突 platform_id=%s", platform_id)
        raise HTTPException(status_code=409, detail="平台配置写入冲突")
    except Exception:
        db.rollback()
        logger.exception("平台配置更新失败 platform_id=%s", platform_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(p)
    return success_response(_to_dict(p), "平台配置已更新")


@router.delete("/invoice-platforms/{platform_id}", summary="删除平台配置")
def delete_invoice_platform(
    platform_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.query(InvoicePlatformConfig).filter(InvoicePlatformConfig.id == platform_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="平台配置不存在")
    assert_team_access(current_user, p.team_id)
    db.delete(p)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("平台配置删除失败 platform_id=%s", platform_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return success_response({"id": platform_id}, "平台配置已删除")


@router.put("/invoice-platforms/{platform_id}/default", summary="设为团队默认")
def set_default_platform(
    platform_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将指定平台设为该团队的默认开票平台"""
    p = db.query(InvoicePlatformConfig).filter(InvoicePlatformConfig.id == platform_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="平台配置不存在")
    assert_team_access(current_user, p.team_id)

    _clear_team_default(db, p.team_id, exclude_id=platform_id)
    p.is_default = True
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("设默认平台失败 platform_id=%s", platform_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(p)
    return success_response(_to_dict(p), "已设为团队默认")


# ==================== 辅助函数 ====================

def _clear_team_default(db: Session, team_id: int, exclude_id: int = None):
    """清除指定团队的默认标记（排除 exclude_id）"""
    q = db.query(InvoicePlatformConfig).filter(
        InvoicePlatformConfig.team_id == team_id,
        InvoicePlatformConfig.is_default == True,
    )
    if exclude_id:
        q = q.filter(InvoicePlatformConfig.id != exclude_id)
    q.update({InvoicePlatformConfig.is_default: False})


def _is_masked_secret(value) -> bool:
    """判断入参是否为 _mask_secret 掩码产物形态（卡 7ada32c8 哨兵判定），
    用于 PUT 时跳过覆盖真实密钥。空串不算掩码（保留「传空清空」语义）。"""
    return bool(value) and str(value).startswith("****")


def _mask_secret(value):
    """敏感字段脱敏: 仅回显后 4 位; None/空返回 None。"""
    if not value:
        return None
    return "****" + str(value)[-4:]


def _to_dict(p: InvoicePlatformConfig) -> dict:
    return {
        "id": p.id,
        "team_id": p.team_id,
        "platform_type": p.platform_type.value if hasattr(p.platform_type, 'value') else str(p.platform_type),
        "platform_name": p.platform_name,
        "api_url": p.api_url,
        "app_key": p.app_key,
        # 敏感字段脱敏 (仅回显后 4 位), 明文绝不外泄
        "app_secret": _mask_secret(p.app_secret),
        "access_token_url": p.access_token_url,
        "device_no": p.device_no,
        "callback_url": p.callback_url,
        "ext_config_json": p.ext_config_json,
        "private_key_enc": _mask_secret(p.private_key_enc),
        "taxpayer_id": p.taxpayer_id,
        "tax_classification_code": p.tax_classification_code,
        "is_default": p.is_default,
        "enabled": p.enabled,
        "remark": p.remark,
        # token_cache_json 含运行时 access_token, 不回显明文, 仅暴露是否存在缓存
        "token_cached": bool(p.token_cache_json),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
