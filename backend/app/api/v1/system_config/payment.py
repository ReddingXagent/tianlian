"""
系统配置 - 支付通道域 (admin spec §2.3)
/payment-channels (GET/POST/PUT/DELETE)
支付通道列表以 JSON 存于 system_configs.payment_channels
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.core.response import success_response, action_response
from app.services.audit_service import audit_service

from .common import _check_admin_or_permission

router = APIRouter(tags=["系统配置"])


class PaymentChannelCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    channel_type: str = Field(..., pattern="^(im_b|alipay|unionpay|bank_transfer)$")
    config: dict = Field(default_factory=dict)
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    enabled: bool = True
    sort_order: int = 0


class PaymentChannelUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    enabled: Optional[bool] = None
    sort_order: Optional[int] = None


def _mask_secret(secret: Optional[str]) -> Optional[str]:
    """api_secret 打码（卡 74277557）：仅保留前3 + **** + 尾4。短 secret（≤8）全打码
    防泄露。None/空 → None。与 app/api/v1/webhooks.py 同款。"""
    if not secret:
        return None
    if len(secret) <= 8:
        return "****"
    return f"{secret[:3]}****{secret[-4:]}"


def _is_masked_sentinel(value: str) -> bool:
    """判断入参 api_secret 是否为掩码哨兵值（以 **** 前缀形态回传），
    用于 PUT 时跳过覆盖真实密钥。"""
    return "****" in value


def _load_payment_channels(db: Session) -> list:
    """从 system_configs 读取支付通道列表"""
    import json
    row = db.execute(
        text("SELECT config_value FROM system_configs WHERE config_key = 'payment_channels'"),
    ).first()
    if row and row[0]:
        try:
            val = row[0] if isinstance(row[0], str) else str(row[0])
            data = json.loads(val)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def _save_payment_channels(db: Session, channels: list):
    """保存支付通道列表"""
    import json
    val_json = json.dumps(channels, ensure_ascii=False)
    existing = db.execute(
        text("SELECT id FROM system_configs WHERE config_key = 'payment_channels'"),
    ).first()
    if existing:
        db.execute(
            text("UPDATE system_configs SET config_value = :v, updated_at = CURRENT_TIMESTAMP WHERE config_key = 'payment_channels'"),
            {"v": val_json},
        )
    else:
        db.execute(
            text("INSERT INTO system_configs (config_key, config_value, type, created_at, updated_at) VALUES ('payment_channels', :v, 'payment', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
            {"v": val_json},
        )


@router.get("/payment-channels")
async def list_payment_channels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取支付通道列表"""
    _check_admin_or_permission(current_user, "system:config")

    channels = _load_payment_channels(db)
    channels.sort(key=lambda x: x.get("sort_order", 0))
    masked = [{**c, "api_secret": _mask_secret(c.get("api_secret"))} for c in channels]
    return success_response({"items": masked, "total": len(masked)})


@router.post("/payment-channels", status_code=201)
def create_payment_channel(
    data: PaymentChannelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建支付通道"""
    _check_admin_or_permission(current_user, "system:config")

    channels = _load_payment_channels(db)

    # 生成新 ID
    new_id = max([c.get("id", 0) for c in channels], default=0) + 1

    channel = {
        "id": new_id,
        "name": data.name,
        "channel_type": data.channel_type,
        "config": data.config,
        "api_key": data.api_key or "",
        "api_secret": data.api_secret or "",
        "enabled": data.enabled,
        "sort_order": data.sort_order,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    channels.append(channel)
    _save_payment_channels(db, channels)
    db.commit()

    audit_service.log_crud(
        user_id=current_user.id,
        username=current_user.username,
        action="create",
        module="system_config",
        target_id=str(new_id),
        target_desc=f"创建支付通道 {data.name}",
    )

    return success_response(
        {**channel, "api_secret": _mask_secret(channel["api_secret"])},
        message=f"支付通道 {data.name} 创建成功",
    )


@router.put("/payment-channels/{channel_id}")
def update_payment_channel(
    channel_id: int,
    data: PaymentChannelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新支付通道"""
    _check_admin_or_permission(current_user, "system:config")

    channels = _load_payment_channels(db)
    found = None
    for c in channels:
        if c.get("id") == channel_id:
            found = c
            break

    if not found:
        raise HTTPException(status_code=404, detail="支付通道不存在")

    updates = data.dict(exclude_none=True)
    # 掩码哨兵守卫 (卡 74277557): None/空串/含 **** 的掩码回传均跳过, 防覆盖真实密钥
    incoming_secret = updates.get("api_secret")
    if incoming_secret is not None and (incoming_secret == "" or _is_masked_sentinel(incoming_secret)):
        updates.pop("api_secret")
    old_value = dict(found)
    found.update(updates)
    found["updated_at"] = datetime.now(timezone.utc).isoformat()

    _save_payment_channels(db, channels)
    db.commit()

    audit_service.log_crud(
        user_id=current_user.id,
        username=current_user.username,
        action="update",
        module="system_config",
        target_id=str(channel_id),
        target_desc=f"更新支付通道 {found.get('name', '')}",
        old_value=str(old_value),
        new_value=str(found),
    )

    return success_response(
        {**found, "api_secret": _mask_secret(found.get("api_secret"))},
        message="支付通道已更新",
    )


@router.delete("/payment-channels/{channel_id}")
def delete_payment_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除支付通道"""
    _check_admin_or_permission(current_user, "system:config")

    channels = _load_payment_channels(db)
    found = None
    for c in channels:
        if c.get("id") == channel_id:
            found = c
            break

    if not found:
        raise HTTPException(status_code=404, detail="支付通道不存在")

    name = found.get("name", "")
    channels = [c for c in channels if c.get("id") != channel_id]
    _save_payment_channels(db, channels)
    db.commit()

    audit_service.log_crud(
        user_id=current_user.id,
        username=current_user.username,
        action="delete",
        module="system_config",
        target_id=str(channel_id),
        target_desc=f"删除支付通道 {name}",
    )

    return action_response(success=True, message=f"支付通道 {name} 已删除")
