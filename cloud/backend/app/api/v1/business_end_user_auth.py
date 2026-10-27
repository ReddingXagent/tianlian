"""C端用户认证/资料/设备token API (用户端契约§8 P1, 卡 d95dafd3)."""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.exc import IntegrityError
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    MissingRequiredClaimError,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.jwt_utils import decode_token_for_audience, encode_token
from app.core.rate_limit import limiter
from app.models.channel_config import ChannelConfig, ChannelType
from app.models.end_user import EndUser, EndUserStatus
from app.models.end_user_device_token import EndUserDeviceToken
from app.services.wx_pay import response as rsp

logger = logging.getLogger(__name__)
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_WX_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
_END_USER_AUD = "end_user"
_TOKEN_EXPIRES_SECONDS = 12 * 60 * 60


def _mask_phone(phone: str) -> str:
    if len(phone) < 7:
        return "***"
    return f"{phone[:3]}****{phone[-4:]}"


class WxLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=256)
    app_id: Optional[str] = Field(None, max_length=128)


class ProfileUpdateRequest(BaseModel):
    nickname: Optional[str] = Field(None, max_length=100)
    avatar_url: Optional[str] = Field(None, max_length=500)


class PhoneBindRequest(BaseModel):
    phone: str = Field(..., min_length=5, max_length=20)
    sms_code: str = Field(..., min_length=4, max_length=8)


class DeviceTokenRequest(BaseModel):
    platform: str = Field(..., pattern="^(ios|android)$")
    device_token: str = Field(..., min_length=1, max_length=512)
    app_version: Optional[str] = Field(None, max_length=50)
    # 卡 7f601f7f: token 归属厂商 (端侧上报 JPush RegistrationID 时传 "jpush")。
    # 缺省向后兼容 (现有调用不带该字段); 当前唯一真实厂商为 JPush,
    # 分发层将全部 token 视为 RegistrationID。落列持久化属迁移另卡。
    provider: Optional[str] = Field(None, pattern="^(jpush)$")


class DeviceTokenDeleteRequest(BaseModel):
    platform: str = Field(..., pattern="^(ios|android)$")


def _credentials_configured() -> bool:
    return bool(settings.WX_MP_APPID) and bool(settings.WX_MP_SECRET)


async def _code2session(code: str) -> dict:
    params = {
        "appid": settings.WX_MP_APPID,
        "secret": settings.WX_MP_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(_WX_CODE2SESSION_URL, params=params)
    try:
        body = response.json()
    except Exception as exc:
        raise HTTPException(502, "IM-B登录服务响应异常") from exc
    if response.status_code != 200 or body.get("errcode"):
        logger.warning("code2session failed status=%s body=%s", response.status_code, body)
        raise HTTPException(502, "IM-B登录失败")
    if not body.get("openid"):
        raise HTTPException(502, "IM-B登录失败: openid缺失")
    return body


def _profile(end_user: EndUser, include_created_at: bool = True) -> dict:
    data = {
        "end_user_id": end_user.id,
        "nickname": end_user.nickname or "",
        "avatar_url": end_user.avatar_url or "",
        "phone": end_user.phone,
        "user_type": end_user.user_type.value if hasattr(end_user.user_type, "value") else str(end_user.user_type),
    }
    if include_created_at:
        data["created_at"] = end_user.created_at.isoformat() if end_user.created_at else None
    return data


def _issue_end_user_token(end_user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(end_user_id),
        "aud": _END_USER_AUD,
        "iat": now,
        "exp": now + timedelta(seconds=_TOKEN_EXPIRES_SECONDS),
    }
    return encode_token(payload)


def _wx_login_db_sync(openid: str, unionid: Optional[str]) -> tuple[EndUser, bool]:
    """wx_login 的同步DB段: 查/建用户 + 并发首登兜底, 返回 (end_user, is_new)。

    Session 在本函数内经 SessionLocal 创建/关闭 (不跨线程复用请求级 session),
    供 async wx_login 经 asyncio.to_thread 调用, 避免阻塞事件循环 (卡67523030)。
    """
    import app.core.database as db_module

    db = db_module.SessionLocal()
    try:
        end_user = db.query(EndUser).filter(EndUser.wx_openid == openid).first()
        is_new = end_user is None
        if is_new:
            end_user = EndUser(wx_openid=openid, wx_unionid=unionid)
            db.add(end_user)
        elif unionid and not end_user.wx_unionid:
            end_user.wx_unionid = unionid
        # 卡 1c54c2b2: 并发首登同 openid, 本请求 INSERT 撞唯一约束 → 回滚后
        # 回查先行落库的用户, 按已存在语义正常返回 (全 rollback 而非 savepoint:
        # SQLite + pysqlite 的 SAVEPOINT 在 IntegrityError 后状态清理不可靠)。
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.query(EndUser).filter(EndUser.wx_openid == openid).first()
            if existing is None:
                raise
            end_user = existing
            if unionid and not end_user.wx_unionid:
                end_user.wx_unionid = unionid
                db.commit()
            is_new = False
        db.refresh(end_user)
        return end_user, is_new
    finally:
        db.close()


@router.post("/auth/wx-login")
@limiter.limit("20/minute")
async def wx_login(request: Request, body: WxLoginRequest, db: Session = Depends(get_db)):
    is_mock = not _credentials_configured()
    if is_mock:
        openid = "mock_" + hashlib.sha1(body.code.encode()).hexdigest()[:16]
        unionid = None
    else:
        wx_body = await _code2session(body.code)
        openid = wx_body["openid"]
        unionid = wx_body.get("unionid")

    end_user, is_new = await asyncio.to_thread(_wx_login_db_sync, openid, unionid)

    return rsp.ok(
        {
            "token": _issue_end_user_token(end_user.id),
            "token_type": "Bearer",
            "expires_in": _TOKEN_EXPIRES_SECONDS,
            "is_mock": is_mock,
            "is_new": is_new,
            "user": _profile(end_user, include_created_at=False),
        }
    )


def get_current_end_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> EndUser:
    credentials_exception = HTTPException(
        401,
        "无效的C端认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token_for_audience(token, _END_USER_AUD)
    except ExpiredSignatureError:
        raise HTTPException(
            401,
            "C端认证凭证已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (DecodeError, InvalidAudienceError, MissingRequiredClaimError):
        raise credentials_exception

    if payload.get("aud") != _END_USER_AUD or payload.get("sub") is None:
        raise credentials_exception
    try:
        end_user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise credentials_exception

    end_user = db.get(EndUser, end_user_id)
    if end_user is None or end_user.status != EndUserStatus.ACTIVE:
        raise credentials_exception
    return end_user


@router.get("/user/me")
@limiter.limit("60/minute")
def get_me(
    request: Request,
    end_user: EndUser = Depends(get_current_end_user),
):
    return rsp.ok(_profile(end_user))


@router.patch("/user/me")
@limiter.limit("60/minute")
def update_me(
    request: Request,
    body: ProfileUpdateRequest,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    updates = body.dict(exclude_unset=True)
    # 契约§8未规定null语义；决策:显式null=清空字段(存空串,_profile回显空串),
    # 与回显语义一致；nickname列NOT NULL不能存None。exclude_unset=True仍会
    # 包含显式null的键,须防None.strip()。
    if "nickname" in updates:
        end_user.nickname = updates["nickname"].strip() if updates["nickname"] else ""
    if "avatar_url" in updates:
        end_user.avatar_url = updates["avatar_url"].strip() if updates["avatar_url"] else ""
    db.commit()
    db.refresh(end_user)
    return rsp.ok(_profile(end_user))


def _sms_configured(db: Session) -> bool:
    channel = ChannelType.SMS
    config = (
        db.query(ChannelConfig)
        .filter(
            ChannelConfig.team_id.is_(None),
            ChannelConfig.channel == channel,
            ChannelConfig.enabled.is_(True),
        )
        .first()
    )
    credentials = config.config if config and config.config else {}
    return bool(credentials.get("sms_access_key")) and bool(credentials.get("sms_secret"))


@router.post("/user/phone-bind")
@limiter.limit("20/minute")
def bind_phone(
    request: Request,
    body: PhoneBindRequest,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    is_mock = not _sms_configured(db)
    if not is_mock:
        raise HTTPException(501, "短信通道尚未接入")

    # 卡 5f1c5f45: mock code 由 settings 配置 (SMS_DEV_CODE), 且仅在
    # SMS_DEV_MODE=True (演示环境) 时参与校验; 生产置 False 后任何固定码
    # 都不得通过, 与真实通道未接入行为一致返回 501。
    if not settings.SMS_DEV_MODE:
        raise HTTPException(501, "短信通道尚未接入")

    if body.sms_code != settings.SMS_DEV_CODE:
        raise HTTPException(422, "短信验证码错误")

    logger.warning(
        "SMS_DEV_MODE mock code accepted phone=%s (演示模式固定验证码, 生产须置 SMS_DEV_MODE=False)",
        _mask_phone(body.phone),
    )

    existing = (
        db.query(EndUser)
        .filter(
            EndUser.phone == body.phone,
            EndUser.id != end_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(409, "手机号已被绑定")

    end_user.phone = body.phone
    db.commit()
    db.refresh(end_user)
    data = _profile(end_user)
    data["is_mock"] = True
    return rsp.ok(data)


@router.post("/devices/token")
@limiter.limit("60/minute")
def register_device_token(
    request: Request,
    body: DeviceTokenRequest,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    device = (
        db.query(EndUserDeviceToken)
        .filter(
            EndUserDeviceToken.end_user_id == end_user.id,
            EndUserDeviceToken.platform == body.platform,
        )
        .first()
    )
    if device is None:
        device = EndUserDeviceToken(
            end_user_id=end_user.id,
            platform=body.platform,
            device_token=body.device_token,
            app_version=body.app_version,
        )
        db.add(device)
    else:
        device.device_token = body.device_token
        if body.app_version is not None:
            device.app_version = body.app_version
    # 卡 1c54c2b2: 并发注册同 (end_user_id, platform), 本请求 INSERT 撞
    # uq_end_user_device_platform → 回滚后回查先行落库的行, 转为更新语义。
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(EndUserDeviceToken)
            .filter(
                EndUserDeviceToken.end_user_id == end_user.id,
                EndUserDeviceToken.platform == body.platform,
            )
            .first()
        )
        if existing is None:
            raise
        existing.device_token = body.device_token
        if body.app_version is not None:
            existing.app_version = body.app_version
        db.commit()
    return rsp.ok({"registered": True})


@router.delete("/devices/token")
@limiter.limit("60/minute")
def delete_device_token(
    request: Request,
    body: DeviceTokenDeleteRequest,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    deleted = (
        db.query(EndUserDeviceToken)
        .filter(
            EndUserDeviceToken.end_user_id == end_user.id,
            EndUserDeviceToken.platform == body.platform,
        )
        .delete()
    )
    db.commit()
    return rsp.ok({"registered": False, "deleted": bool(deleted)})
