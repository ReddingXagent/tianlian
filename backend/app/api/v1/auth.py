"""
认证模块
"""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import and_
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models.sms_verification import SmsVerificationCode
from datetime import datetime, timedelta, timezone
import jwt
from jwt.exceptions import DecodeError, ExpiredSignatureError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import secrets
import logging
import math

from app.core.rate_limit import limiter, rate_limits
from app.core.database import get_db
from app.core.config import settings
from app.core.jwt_utils import decode_token, get_active_secret_key
from app.models.user import User, UserRole
from app.services.audit_service import audit_service
from app.core.response import success_response, action_response
from app.utils.sanitize import mask_phone
import traceback

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Pydantic 模型
class UserLogin(BaseModel):
    username: str = Field(..., max_length=50)
    password: str

class SmsSendRequest(BaseModel):
    phone: str
    purpose: Literal["login", "register", "reset", "login_2fa"] = "login"

class SmsVerifyRequest(BaseModel):
    phone: str
    code: str
    purpose: Literal["login", "register", "reset"] = "login"

class SmsLoginRequest(BaseModel):
    phone: str
    code: str

class Verify2FARequest(BaseModel):
    temp_token: str
    code: str

class PasswordResetRequest(BaseModel):
    phone: str
    code: str  # 短信验证码
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_password_bytes(cls, v: str) -> str:
        return check_password_byte_length(v)

class SmsLoginResponse(BaseModel):
    token: str
    user: dict

class UserCreate(BaseModel):
    username: str = Field(..., max_length=50)
    password: str
    real_name: str = Field(..., max_length=100)
    phone: str = None
    email: EmailStr = None
    role: Literal["super_admin", "admin", "dispatcher", "station_master", "engineer", "operator", "viewer", "technician", "auditor"] = "technician"

    @field_validator("password")
    @classmethod
    def _check_password_bytes(cls, v: str) -> str:
        return check_password_byte_length(v)

class UserResponse(BaseModel):
    id: int
    username: str
    real_name: str
    phone: str = None
    email: str = None
    role: str
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

# bcrypt 5.0 对 >72 字节密码直接抛 ValueError → 500 (卡 d827fd9a)。
# 入口防御: 字节级 (UTF-8) 校验, 禁止静默截断。HTTPException 在 pydantic
# validator 中抛出会原样穿透 (pydantic v2 仅捕获 ValueError/AssertionError),
# 故 schema validator 与函数守卫共用同一 helper, 保证全路径统一 400。
BCRYPT_MAX_PASSWORD_BYTES = 72

def check_password_byte_length(password: str) -> str:
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度超过72字节限制",
        )
    return password

# 工具函数
def verify_password(plain_password: str, hashed_password: str) -> bool:
    import hashlib
    import hmac
    # 支持 SHA256 和 bcrypt 两种hash
    sha256_hash = hashlib.sha256(plain_password.encode()).hexdigest()
    # 常量时间比较 (hmac.compare_digest) 防时序侧信道; hexdigest 恒为小写,
    # 故对存储值做大写归一化后再比较, 保持遗留 hash (含大写存储) 兼容 (卡 9e9c519e)
    if hmac.compare_digest(str(hashed_password).lower(), sha256_hash):
        return True
    if hashed_password.startswith('$2'):
        import bcrypt
        # bcrypt 5.0 checkpw 对 >72 字节明文抛 ValueError (卡 d827fd9a),
        # 统一按 400 拒绝而非吞异常, 避免用户误判为密码错误。
        check_password_byte_length(plain_password)
        try:
            return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
        except ValueError:
            return False
    return False

def get_password_hash(password: str) -> str:
    import bcrypt
    check_password_byte_length(password)
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, get_active_secret_key(), algorithm=settings.ALGORITHM)
    return encoded_jwt

# 鉴权函数 - 获取当前用户
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """验证token并返回当前用户对象"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证凭证已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except DecodeError:
        raise credentials_exception
    
    # 查询用户
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    # 每请求鉴权补防线 (卡 5d6a978b): 与 login/refresh 口径一致, 非 active 即拒;
    # token_version 比对 — 改密后递增, 旧 token (tv 不一致) 立即驱逐。
    if user.status != "active":
        raise credentials_exception
    if payload.get("tv", 0) != (user.token_version or 0):
        raise credentials_exception
    return user


def require_role(*roles: str):
    """角色校验依赖 - ADMIN角色始终通过"""
    async def check_role(current_user: User = Depends(get_current_user)):
        user_role = current_user.role if isinstance(current_user.role, str) else current_user.role.value
        if user_role.upper() in ("ADMIN", "SUPER_ADMIN"):
            return current_user
        if user_role.upper() not in [r.upper() for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，需要角色: {', '.join(roles)}",
            )
        return current_user
    return check_role


# ─── 全局认证强制（白名单豁免）───
# 可选 token 抓取：白名单路径无 token 也要能通过，故 auto_error=False
_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# 公开路径白名单（相对 /api/v1 前缀）。集中维护，enforce_auth 与测试通过
# is_public_path 共享单一真相源，新增公开端点只改这里。
_PUBLIC_PATH_PREFIXES = (
    "/scan",          # 扫码报修（匿名）
    "/telemetry",     # 设备数据上报（网关 X-API-Key 或 token，已有自身认证）
    "/pod",           # Pod 矩阵路由层 — 自注册/心跳/查询（基础设施，现有契约匿名）
    "/cross",         # 跨 Pod 查询 — Pod 间 RPC（基础设施，现有契约匿名）
    "/alert-webhook", # Alertmanager 回调 — 靠 ALERT_WEBHOOK_SECRET 自证 (见 alert_webhook._verify_webhook_secret)，无 user JWT
    "/open/parking",  # 停车场对接开放API (卡 309b4132) — 靠 X-App-Key/X-App-Secret 自证, 无 user JWT
)
_PUBLIC_PATH_EXACT = {
    # 健康检查（health.router 无 prefix，端点分散）
    "/health", "/live", "/livez", "/ready", "/readyz", "/ping",
    "/devices/health",
    # POST /devices/health/refresh 已收紧 admin (卡69acc93c D2): 移出白名单,
    # 走 enforce_auth + require_platform_admin, anon→401 / 非 admin→403
    "/pipeline/health", "/pipeline/stats", "/gateway/health",
    # 认证公开端点：登录 / 注册 / 短信验证码 / 密码重置 / 刷新 / 登出
    "/auth/login", "/auth/register",
    "/auth/sms/send", "/auth/sms/verify", "/auth/sms/login",
    "/auth/password-reset", "/auth/refresh", "/auth/logout",
    # 忘记密码申请 (卡 922b2fba): 匿名提交, 统一响应不泄露账号存在性;
    # 仅此精确路径公开, /auth/forgot-password/requests* 需管理员 token
    "/auth/forgot-password",
    # 两步登录第二步 (任务卡 78c7404b): 验 temp_token+短信码换正式 token, 匿名可访问
    "/auth/login/verify-2fa",
    # 企业注册(卡 c8f7be6f): 执照上传 + 企业注册申请 — 注册前置, 匿名可访问
    "/auth/register/upload-license", "/auth/register/enterprise",
    # IM-B支付回调 (IM-B→云端外部回调, 靠IM-B签名校验自证, 无 user JWT);
    # 仅 notify 端点公开, prepay/orders 仍需 C 端用户 token (卡 280c85ee 契约§2.2)
    "/business/payments/notify",
    # 发票文件下载 (卡a09f8a21 契约§5.5): 签名令牌自证 (2h 过期), 支持端侧/邮箱分享转发,
    # 无 Bearer; 靠 itsdangerous 签名校验放行 (token 无效/过期 → 403)
    "/business/invoice-file",
    # C端IM-B登录 (契约§8.1): code 自证, 登录成功签发 aud=end_user token
    "/business/auth/wx-login",
}

# C端专用端点 (契约§8): 由 get_current_end_user 校验 aud=end_user;
# 不进入全局 get_current_user, 避免 PyJWT 因 aud claim 拒绝解码。
# P2 (卡36396f29): /business/vehicles 与 /business/favorites 前缀加入 —
# 含路径参数子路径 (/{id}, /{id}/default, /{station_id}), 用前缀匹配。
_END_USER_PATH_EXACT = {
    "/business/user/me",
    "/business/user/phone-bind",
    "/business/devices/token",
}
_END_USER_PATH_PREFIXES = (
    "/business/vehicles",
    "/business/favorites",
    # 卡 089b01b2 — C端端侧路径 (无 /business 前缀): 充电订单 / 优惠券 / 积分。
    # 运营 charging_orders.router 级挂 get_current_user, enforce_auth 放行后叠加兜底,
    # 鉴权不破坏; C端端点级 get_current_end_user 校验 aud=end_user, 运营 token→401。
    "/charging-orders",
    "/coupons",
    "/points",
)

_API_PREFIX = "/api/v1"


def is_public_path(full_path: str) -> bool:
    """判断完整 URL 路径是否属于白名单（公开，无需认证）。"""
    rel = full_path[len(_API_PREFIX):] if full_path.startswith(_API_PREFIX) else full_path
    if rel in _PUBLIC_PATH_EXACT or rel.startswith(_PUBLIC_PATH_PREFIXES):
        return True
    # 卡 089b01b2 — C端品牌端点 /tenants/{tenantId}/branding (含路径参数, 无法精确匹配):
    # 仅放行 /branding 后缀, 不影响运营 tenant.router 的 /tenants/{id} 详情鉴权
    # (后者 router 级挂 get_current_user, 即便误放行亦兜底 401)。
    return rel.startswith("/tenants/") and rel.endswith("/branding")


def is_end_user_path(full_path: str) -> bool:
    """判断是否为契约§8 C端专用端点 (认证由端点自身依赖完成)."""
    rel = full_path[len(_API_PREFIX):] if full_path.startswith(_API_PREFIX) else full_path
    return (
        rel in _END_USER_PATH_EXACT
        or rel.startswith(_END_USER_PATH_PREFIXES)
    )


def enforce_auth(
    request: Request,
    token: Optional[str] = Depends(_optional_oauth2),
    db: Session = Depends(get_db),
):
    """全局认证依赖：白名单路径放行，其余强制 Bearer token 认证。

    挂载在 api_router 级别 (dependencies=[Depends(enforce_auth)])，对全部
    /api/v1/* 端点生效。子路由已有的 Depends(get_current_user)/require_role 会
    叠加执行——重复解码同一 token，无副作用；白名单路径直接放行，不影响其自身
    认证（如 telemetry 的网关 X-API-Key 机制）。同步函数由 FastAPI 在线程池执行。
    """
    if is_public_path(request.url.path):
        return
    if is_end_user_path(request.url.path):
        return
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供有效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 复用 get_current_user 的 token 校验逻辑（失败抛 401）。
    # 卡 a1c26a22: 把校验结果挂到 request.state —— AuditMiddleware / logging_middleware
    # 依赖 request.state.user 提取 user_id, 不挂则写操作审计被静默跳过。
    user = get_current_user(token=token, db=db)
    request.state.user = user
    request.state.user_id = user.id


# ─── 临时令牌工具函数 ───
def generate_reset_token(phone: str, sms_record_id: int) -> str:
    """生成密码重置临时令牌（有效期5分钟）"""
    token_data = {
        "sub": phone,
        "sms_id": sms_record_id,
        "purpose": "password_reset",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(token_data, get_active_secret_key(), algorithm=settings.ALGORITHM)


def verify_reset_token(token: str) -> dict:
    """验证并解析临时重置令牌，返回 {"phone", "sms_id"} 或抛出"""
    try:
        payload = decode_token(token)
        if payload.get("purpose") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的重置令牌"
            )
        return {"phone": payload["sub"], "sms_id": payload["sms_id"]}
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="重置令牌已过期"
        )
    except (DecodeError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的重置令牌"
        )

# ─── 两步登录(2FA)临时令牌工具 ───
# temp_token 用 itsdangerous URLSafeTimedSerializer 签名(非 JWT): 轻量、短期、
# 自带 max_age 过期。salt 限定用途, 隔离其它 itsdangerous 令牌(如发票签名)。
_2FA_SALT = "login_2fa"
_2FA_MAX_AGE = 300  # 5 分钟


def _get_2fa_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_active_secret_key(), salt=_2FA_SALT)


def _create_sms_code(db: Session, phone: str, purpose: str) -> str:
    """生成并存入一条短信验证码, 返回明文验证码 (复用于 send_sms / 2FA 触发)。

    用 secrets(CSPRNG) 生成 6 位, 清同 phone+purpose 旧码, 存新码, 5 分钟过期。
    """
    code = str(secrets.randbelow(900000) + 100000)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    db.query(SmsVerificationCode).filter(
        and_(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.purpose == purpose,
            SmsVerificationCode.used == 0,
        )
    ).update({SmsVerificationCode.used: 1})
    db.add(SmsVerificationCode(
        phone=phone, code=code, purpose=purpose, expires_at=expires_at
    ))
    db.commit()
    logging.getLogger(__name__).info("发送验证码: %s (purpose: %s)", mask_phone(phone), purpose)
    return code


def _audit_failed_login(
    user_id: Optional[int],
    username: str,
    request: Request,
    error: str,
    db: Session,
) -> None:
    """登录失败留痕 (卡 69142d4e): 密码错误/用户不存在/账户锁定三类分支共用。

    审计是旁路观测, 任何故障不得影响登录响应本身 (契约同 audit_service.log
    内部吞异常, 卡 be2dbf042) —— 故整体 try/except 兜底只记 logger, 永不抛。
    error 内部区分 user_not_found / wrong_password / locked, 用户可见
    detail 不受此影响 (防枚举)。
    """
    try:
        audit_service.log_login(
            user_id,
            username,
            ip=request.client.host if request.client else None,
            success=False,
            error=error,
            db=db,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "登录失败审计写入异常 user=%s error=%s", username, error
        )


def _issue_2fa_temp_token(user: User, db: Session) -> dict:
    """2FA 团队用户密码通过后: 发验证码 + 签发 temp_token, 返回登录端点的 2FA 响应体。

    不调用 audit log_login(尚未真正登录成功), 不签发正式 access_token。
    """
    phone = user.phone or ""
    if phone:
        _create_sms_code(db, phone, "login_2fa")
    token = _get_2fa_serializer().dumps({"uid": user.id, "phone": phone})
    # 手机号脱敏: 保留前3后4
    masked = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else phone
    return {
        "second_factor_required": True,
        "temp_token": token,
        "method": "sms",
        "phone_masked": masked,
    }


def _finalize_login(user: User, db: Session) -> dict:
    """签发正式 access_token 并记审计, 返回登录成功响应体 (login / verify-2fa 共用)。

    抽出公共段: 取权限 → 编 JWT → audit → 组装 {token, user}。
    """
    from app.middleware.permission import get_user_permissions
    team = user.team
    team_type = team.type.value if team and team.type else None
    user_permissions = get_user_permissions(user)
    role_val = user.role.value if hasattr(user.role, 'value') else user.role
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "role": role_val,
            "permissions": user_permissions,
            "team_type": team_type,
            "tv": user.token_version or 0,
        },
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    audit_service.log_login(user.id, user.username, success=True, db=db)
    return {
        "token": access_token,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "real_name": user.real_name or "",
            "role": role_val,
            "team_type": team_type,
            "team_id": user.team_id,
        },
    }


# 路由
@router.post("/register")
@limiter.limit(rate_limits["register"])
def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    """用户注册"""
    # 检查用户名
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    # 验证角色 (卡 19c0ee73 P0): 匿名自注册只允许最低权限角色白名单,
    # 防止直接注册 super_admin/admin 等后台角色。正式建人走 admin 入口。
    allowed_roles = ("viewer", "technician")
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"注册不允许的角色: {user.role}，注册可选角色: {list(allowed_roles)}"
        )
    
    # 创建用户
    db_user = User(
        username=user.username,
        password_hash=get_password_hash(user.password),
        real_name=user.real_name,
        phone=user.phone,
        email=user.email,
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return success_response({
        "id": db_user.id,
        "username": db_user.username,
        "real_name": db_user.real_name,
        "phone": db_user.phone,
        "email": db_user.email,
        "role": db_user.role
    })

@router.post("/login")
@limiter.limit(rate_limits["login"])
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """用户名密码登录 - 数据库认证"""
    try:
        # 查询用户 — 并发 login 失败计数读改写需行锁防丢更新 (SQLite 下 with_for_update 为 no-op, 由持锁后基于最新快照复查兜底; 生产 PostgreSQL 行锁生效)
        user = db.query(User).filter(User.username == form_data.username).with_for_update().first()
        logger = logging.getLogger(__name__)
        logger.debug("login: user=%s found=%s", form_data.username, user is not None)
        
        if not user:
            logger.debug("login: user not found: %s", form_data.username)
            # 失败留痕 (卡 69142d4e): 不存在的用户名无 user_id, 仅记尝试名。
            _audit_failed_login(None, form_data.username, request, "user_not_found", db)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )
        
        # 登录前锁定检查 (D8 爆破防护, spec admin§2.1): now < locked_until → 423
        now = datetime.now(timezone.utc)
        locked_until = user.locked_until
        if locked_until and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until and now < locked_until:
            remaining_min = max(1, math.ceil((locked_until - now).total_seconds() / 60))
            logger.warning(
                "login: 账户已锁定 user=%s id=%s locked_until=%s",
                user.username, user.id, user.locked_until,
            )
            # 失败留痕 (卡 69142d4e): 锁定期间的尝试即爆破特征, 须进 /threats
            _audit_failed_login(user.id, user.username, request, "locked", db)
            raise HTTPException(
                status_code=423,
                detail=f"账户已锁定，请{remaining_min}分钟后重试",
            )

        # 密码校验
        pwd_hash = user.password_hash
        pwd_ok = verify_password(form_data.password, pwd_hash)
        
        if not pwd_ok:
            # 失败计数累加; 达5次 → 锁定15分钟并归零, 记审计 WARNING
            user.login_fail_count = (user.login_fail_count or 0) + 1
            if user.login_fail_count >= 5:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                user.login_fail_count = 0
                logger.warning(
                    "账户锁定: user=%s id=%s reason=连续5次密码错误 locked_until=%s ip=%s",
                    user.username, user.id, user.locked_until,
                    request.client.host if request.client else None,
                )
            db.commit()
            # 失败留痕 (卡 69142d4e): 须在 db.commit() 之后 —— 锁定计数已落库,
            # 审计写失败不会回滚掉锁定状态。
            _audit_failed_login(user.id, user.username, request, "wrong_password", db)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )
        if user.status == "inactive":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账户已被禁用",
            )

        # 登录成功: 清空失败计数与锁定, 记录登录 IP 与最后登录时间
        user.login_fail_count = 0
        user.locked_until = None
        user.last_login_ip = request.client.host if request.client else None
        user.last_login = datetime.now(timezone.utc)

        # 透明升级: 本次命中的 hash 非 bcrypt ($2 前缀) 即遗留无盐 SHA256 快hash,
        # 用明文密码重哈希为 bcrypt 写回, 一次性迁移, 避免快hash永久暴露于
        # GPU/彩虹表爆破 (卡 9e9c519e)。verify_password 仅在 sha256/bcrypt 命中时
        # 返回 True, 故走到此处且非 $2 必为 sha256 命中, 升级条件充分。
        if not pwd_hash.startswith("$2"):
            user.password_hash = get_password_hash(form_data.password)

        db.commit()

        # team_type 回填 (卡 6c5d28fa): 前端 resolveTeamType 据此判定
        # ops_company/maintenance_team/fleet, 不再走兜底链误判运维工程师为公司。
        # user 未挂团队 (team_id 为空) → team_type 为 null, 响应与 JWT 一致返回 null。
        team = user.team
        team_type = team.type.value if team and team.type else None

        # 两步登录(2FA, 任务卡 78c7404b): 团队开启 second_factor_enabled 时, 密码虽已
        # 通过, 但不发正式 token —— 发短信验证码 + 签发短期 temp_token, 由 verify-2fa
        # 端点验码后再签 token。默认关闭, 不影响现有登录路径。
        if team and getattr(team, "second_factor_enabled", False):
            return success_response(_issue_2fa_temp_token(user, db))

        # 获取用户权限列表并编码到 JWT
        logger.debug("login: success for %s", user.username)
        return success_response(_finalize_login(user, db))
    except HTTPException:
        raise
    except Exception as e:
        _log = logging.getLogger(__name__)
        _log.error("login: UNEXPECTED EXCEPTION: %s", str(e))
        _log.error("login: traceback=%s", traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录内部错误，请稍后重试",
        )

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息 (含权限)"""
    from app.middleware.permission import get_user_permissions
    perms = get_user_permissions(current_user)
    role_val = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    # team_type/team_id 回填 (卡 6c5d28fa), 与 /auth/login 响应保持一致。
    team = current_user.team
    team_type = team.type.value if team and team.type else None
    return success_response({
        "id": current_user.id,
        "username": current_user.username,
        "real_name": current_user.real_name,
        "role": role_val,
        "permissions": perms,
        "team_type": team_type,
        "team_id": current_user.team_id,
    })

@router.post("/logout")
async def logout():
    """登出"""
    audit_service.log(user_id=0, username="system", action='logout', module='auth')
    return action_response(message="登出成功")

@router.post("/refresh")
def refresh_token(
    current_token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """刷新 Token (卡 a65f8b2c 安全修复)。

    旧 token 必须经 decode_token 验证(无效/过期 401); 新 token 按 user_id
    反查 DB 取新鲜角色权限 —— 而非完整继承旧 claims, 防角色/权限被变更后
    refresh 仍携带过期权限持续续期。
    """
    from app.middleware.permission import get_user_permissions
    from jwt import ExpiredSignatureError, DecodeError

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(current_token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证凭证已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except DecodeError:
        raise credentials_exception
    user_id = payload.get("user_id")
    if user_id is None:
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.status != "active":
        raise credentials_exception
    # 改密驱逐 (卡 5d6a978b): 旧 token 的 tv 与当前 token_version 不一致即拒,
    # 防改密后旧 token 经 refresh 续期复活。
    if payload.get("tv", 0) != (user.token_version or 0):
        raise credentials_exception
    team = user.team
    team_type = team.type.value if team and team.type else None
    role_val = user.role.value if hasattr(user.role, "value") else user.role
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "role": role_val,
            "permissions": get_user_permissions(user),
            "team_type": team_type,
            "tv": user.token_version or 0,
        },
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return success_response({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    })

@router.post("/sms/login")
@limiter.limit(rate_limits["login"])
def sms_login(request: Request, body: SmsLoginRequest, db: Session = Depends(get_db)):
    """验证码登录 — 已停用 (任务卡 78c7404b)。

    统一改用密码登录(必要时配合两步登录 verify-2fa)。本端点不再校验验证码,
    一律返回 410 Gone, 提示用户改用密码登录。保留路由避免旧客户端硬 404。
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="验证码登录已停用，请使用密码登录",
    )


@router.post("/login/verify-2fa")
@limiter.limit(rate_limits["login"])
def verify_2fa(request: Request, body: Verify2FARequest, db: Session = Depends(get_db)):
    """两步登录第二步: 验证 temp_token + 短信验证码, 通过则签发正式 access_token。

    流程(任务卡 78c7404b): /auth/login 对 2FA 团队返回 temp_token + 发验证码 →
    本端点验 temp_token(itsdangerous, 5min) 与验证码 → 返回 {token, user}。
    """
    # 1. 验签 temp_token (过期/篡改/格式错 → 400)
    try:
        payload = _get_2fa_serializer().loads(body.temp_token, max_age=_2FA_MAX_AGE)
    except SignatureExpired:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="二次验证令牌已过期，请重新登录")
    except BadSignature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的二次验证令牌")

    phone = payload.get("phone") or ""
    user_id = payload.get("uid")

    # 2. 查有效验证码 (phone + purpose=login_2fa + 未使用 + 未过期), 实施 attempts 防爆破
    # 行锁防并发丢更新: SQLite 下 with_for_update 为 no-op, 由持锁后基于最新快照复查兜底; 生产 PostgreSQL 行锁生效
    sms_record = db.query(SmsVerificationCode).filter(
        and_(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.purpose == "login_2fa",
            SmsVerificationCode.used == 0,
            SmsVerificationCode.expires_at > datetime.now(timezone.utc),
        )
    ).with_for_update().first()
    if not sms_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期")
    if sms_record.attempts >= 5:
        sms_record.used = 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误次数过多，已失效")
    if sms_record.code != body.code:
        sms_record.attempts += 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期")

    # 3. 定位用户 (按 temp_token 内 uid, 兜底按 phone)
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if user is None and phone:
        user = db.query(User).filter(User.phone == phone).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户不存在")
    if user.status == "inactive":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已被禁用")

    # 4. 验证码标记已用, 更新登录时间, 签发正式 token
    sms_record.used = 1
    user.login_fail_count = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    return success_response(_finalize_login(user, db))


@router.post("/sms/send")
@limiter.limit(rate_limits["sms_send"])
def send_sms(request: Request, body: SmsSendRequest, db: Session = Depends(get_db)):
    """发送短信验证码"""
    import re

    # 手机号格式验证
    if not re.match(r'^1[3-9]\d{9}$', body.phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手机号格式错误"
        )

    # 生成6位验证码 — 用 secrets (CSPRNG) 而非 random (MT19937 可预测),
    # 防爆破/猜测 (卡 42d650f5)。范围 [100000, 999999] 与旧实现等价。
    code = str(secrets.randbelow(900000) + 100000)

    # 设置过期时间（5分钟）
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    # 清除该手机号同用途的未使用验证码
    db.query(SmsVerificationCode).filter(
        and_(
            SmsVerificationCode.phone == body.phone,
            SmsVerificationCode.purpose == body.purpose,
            SmsVerificationCode.used == 0
        )
    ).update({SmsVerificationCode.used: 1})

    # 保存新验证码
    sms_record = SmsVerificationCode(
        phone=body.phone,
        code=code,
        purpose=body.purpose,
        expires_at=expires_at
    )
    db.add(sms_record)
    db.commit()

    # 实际应该调用短信接口，这里仅打印日志（开发环境）
    logging.getLogger(__name__).info("发送验证码: %s (purpose: %s)", mask_phone(body.phone), body.purpose)

    return success_response({"message": "验证码已发送"})


@router.post("/sms/verify")
@limiter.limit(rate_limits["login"])
def verify_sms(request: Request, body: SmsVerifyRequest, db: Session = Depends(get_db)):
    """验证短信验证码"""
    # 先按 phone+purpose+未使用+未过期 查出记录 (不带 code), 实施 attempts 锁定防爆破
    # 行锁防并发丢更新: SQLite 下 with_for_update 为 no-op, 由持锁后基于最新快照复查兜底; 生产 PostgreSQL 行锁生效
    sms_record = db.query(SmsVerificationCode).filter(
        and_(
            SmsVerificationCode.phone == body.phone,
            SmsVerificationCode.purpose == body.purpose,
            SmsVerificationCode.used == 0,
            SmsVerificationCode.expires_at > datetime.now(timezone.utc)
        )
    ).with_for_update().first()

    if not sms_record:
        return success_response({"valid": False}, message="验证码错误或已过期")

    # 错误尝试达上限 → 直接失效, 防爆破
    if sms_record.attempts >= 5:
        sms_record.used = 1
        db.commit()
        return success_response({"valid": False}, message="验证码错误次数过多，已失效")

    if sms_record.code != body.code:
        sms_record.attempts += 1
        db.commit()
        return success_response({"valid": False}, message="验证码错误或已过期")

    # 匹配 → 标记为已使用
    sms_record.used = 1
    db.commit()

    return success_response({"valid": True})


@router.post("/password-reset")
@limiter.limit(rate_limits["login"])
def password_reset(request: Request, body: PasswordResetRequest, db: Session = Depends(get_db)):
    """密码重置"""
    # 先按 phone+purpose=reset+未使用+未过期 查出记录 (不带 code), 实施 attempts 锁定防爆破
    # 行锁防并发丢更新: SQLite 下 with_for_update 为 no-op, 由持锁后基于最新快照复查兜底; 生产 PostgreSQL 行锁生效
    sms_record = db.query(SmsVerificationCode).filter(
        and_(
            SmsVerificationCode.phone == body.phone,
            SmsVerificationCode.purpose == "reset",
            SmsVerificationCode.used == 0,
            SmsVerificationCode.expires_at > datetime.now(timezone.utc)
        )
    ).with_for_update().first()

    if not sms_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已过期"
        )

    # 错误尝试达上限 → 失效
    if sms_record.attempts >= 5:
        sms_record.used = 1
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误次数过多，已失效"
        )

    if sms_record.code != body.code:
        sms_record.attempts += 1
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已过期"
        )

    # 查找用户
    user = db.query(User).filter(User.phone == body.phone).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="手机号未注册"
        )

    # 公开演示账户保护: demo 只读体验账户禁止改密 (开源演示环境用)
    if user.username == "demo":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="演示账户为只读体验账户，不允许修改密码",
        )

    # 更新密码
    user.password_hash = get_password_hash(body.new_password)
    # 改密驱逐 (卡 5d6a978b): 递增 token_version, 全部已签发旧 token 立即失效
    user.token_version = (user.token_version or 0) + 1
    # 标记验证码为已使用
    sms_record.used = 1
    db.commit()

    return success_response({"message": "密码重置成功"})


# ─── 忘记密码申请 (卡 922b2fba) ───

class ForgotPasswordBody(BaseModel):
    account: str = Field(..., min_length=1, max_length=100)


@router.post("/forgot-password")
@limiter.limit(rate_limits["forgot_password"])
def forgot_password(request: Request, body: ForgotPasswordBody, db: Session = Depends(get_db)):
    """忘记密码申请 — 统一响应, 不泄露账号存在性。

    任何 account (存在与否) 均返回同一 message; 申请落库 pending,
    由平台管理员线下核实后走 users reset-password 重置。
    """
    from app.models.password_reset_request import PasswordResetRequest
    try:
        db.add(PasswordResetRequest(account=body.account, status="pending"))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("forgot_password 落库失败 account=%s", body.account)
        # 落库失败也不改变响应 — 不泄露存在性优先
    return success_response({"message": "已提交申请, 请联系平台管理员处理"})


@router.get("/forgot-password/requests")
def list_forgot_password_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """忘记密码申请列表 (平台管理员 only)。"""
    from app.api.deps import is_platform_admin
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="仅平台管理员可查看忘记密码申请")
    from app.models.password_reset_request import PasswordResetRequest
    query = db.query(PasswordResetRequest)
    if status_filter:
        query = query.filter(PasswordResetRequest.status == status_filter)
    rows = query.order_by(PasswordResetRequest.id.desc()).limit(200).all()
    return success_response({
        "items": [{
            "id": r.id,
            "account": r.account,
            "status": r.status,
            "handled_by": r.handled_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
        "total": len(rows),
    })


@router.post("/forgot-password/requests/{request_id}/resolve")
def resolve_forgot_password_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记忘记密码申请已处理 (平台管理员 only)。"""
    from app.api.deps import is_platform_admin
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="仅平台管理员可处理忘记密码申请")
    from app.models.password_reset_request import PasswordResetRequest
    row = db.query(PasswordResetRequest).filter(PasswordResetRequest.id == request_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="申请不存在")
    row.status = "resolved"
    row.handled_by = current_user.id
    db.commit()
    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="update", module="auth",
            target_id=str(request_id), target_desc=f"处理忘记密码申请:{row.account}",
        )
    except Exception:
        pass
    return success_response({"id": request_id, "status": "resolved"})
