"""
API网关核心模块 - Phase11开放API网关
支持OAuth2.0、限流、第三方对接
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2AuthorizationCodeBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import jwt
import hashlib
import secrets
import uuid

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.config import settings
from app.core.jwt_utils import decode_token, get_active_secret_key
from app.core.rate_limit import limiter, rate_limits
from app.models.api_gateway import ApiClient, GatewayApiKey as ApiKey, ApiEndpoint, ApiRequestLog, OAuthAuthorizationCode
from app.models.user import User
from app.services.audit_service import audit_service
from app.core.response import success_response

# 卡片 ba9d3461: 挂载到 api_router (prefix=/api/v1), 故此处只写相对前缀,
# 完整路径 /api/v1/gateway/* 与 oauth2_scheme 声明的 URL 一致。
router = APIRouter(prefix="/gateway", tags=["API网关"])

# OAuth2配置
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl="/api/v1/gateway/oauth/authorize",
    tokenUrl="/api/v1/gateway/oauth/token",
    scopes={
        "read": "读取权限",
        "write": "写入权限",
        "admin": "管理员权限"
    }
)

# ============ Pydantic Models ============

class ApiClientCreate(BaseModel):
    """创建API客户端请求"""
    name: str = Field(..., min_length=1, max_length=100, description="客户端名称")
    description: Optional[str] = Field(None, max_length=500, description="客户端描述")
    callback_url: Optional[str] = Field(None, description="回调URL")
    scopes: List[str] = Field(default=["read"], description="权限范围")

class ApiClientResponse(BaseModel):
    """API客户端响应"""
    client_id: str
    client_secret: str
    name: str
    description: Optional[str]
    callback_url: Optional[str]
    scopes: List[str]
    status: str
    created_at: datetime
    rate_limit: int = 1000  # 默认限流: 1000次/分钟

    class Config:
        from_attributes = True

class ApiKeyCreate(BaseModel):
    """创建API密钥请求"""
    client_id: str = Field(..., max_length=64, description="客户端ID")
    name: str = Field(..., min_length=1, max_length=50, description="密钥名称")
    expires_in: Optional[int] = Field(None, ge=1, le=365, description="有效期(天)")

class ApiKeyResponse(BaseModel):
    """API密钥响应"""
    key_id: str
    client_id: str
    name: str
    api_key: str
    expires_at: Optional[datetime]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class ApiKeyRotate(BaseModel):
    """轮换API密钥请求 (卡片 ba9d3461)"""
    expires_in: Optional[int] = Field(None, ge=1, le=365, description="新密钥有效期(天)")

class OAuthTokenRequest(BaseModel):
    """OAuth令牌请求"""
    grant_type: str = Field(..., description="授权类型")
    client_id: str = Field(..., description="客户端ID")
    client_secret: Optional[str] = Field(None, description="客户端密钥")
    code: Optional[str] = Field(None, description="授权码")
    redirect_uri: Optional[str] = Field(None, description="重定向URI")
    refresh_token: Optional[str] = Field(None, description="刷新令牌")
    scope: Optional[str] = Field(None, description="权限范围")

class OAuthTokenResponse(BaseModel):
    """OAuth令牌响应"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: Optional[str]
    scope: str

class EndpointRegister(BaseModel):
    """注册API端点"""
    path: str = Field(..., max_length=500, description="端点路径")
    method: str = Field(..., description="HTTP方法")
    description: Optional[str] = Field(None, description="端点描述")
    rate_limit: Optional[int] = Field(None, ge=1, description="限流次数/分钟")
    require_auth: bool = Field(True, description="是否需要认证")

class ApiUsageStats(BaseModel):
    """API使用统计"""
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_response_time: float
    top_endpoints: List[Dict[str, Any]]

# ============ 工具函数 ============

def generate_client_id() -> str:
    """生成客户端ID"""
    return f"client_{uuid.uuid4().hex[:16]}"

def generate_client_secret() -> str:
    """生成客户端密钥"""
    return secrets.token_urlsafe(32)

def generate_api_key() -> str:
    """生成API密钥"""
    return f"tianlian_{uuid.uuid4().hex}_{secrets.token_urlsafe(16)}"

def verify_api_key(api_key: str, db: Session) -> Optional[ApiKey]:
    """验证API密钥"""
    key_record = db.query(ApiKey).filter(
        ApiKey.api_key == api_key,
        ApiKey.status == "active"
    ).first()
    
    if not key_record:
        return None
    
    # 检查是否过期
    _expires_at = key_record.expires_at
    if _expires_at and _expires_at.tzinfo is None:
        _expires_at = _expires_at.replace(tzinfo=timezone.utc)
    if _expires_at and _expires_at < datetime.now(timezone.utc):
        key_record.status = "expired"
        db.commit()
        return None
    
    return key_record

def verify_client_credentials(client_id: str, client_secret: str, db: Session) -> Optional[ApiClient]:
    """验证客户端凭证"""
    client = db.query(ApiClient).filter(
        ApiClient.client_id == client_id,
        ApiClient.status == "active"
    ).first()
    
    if not client:
        return None
    
    # 验证客户端密钥（简单哈希比较）
    secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
    if secret_hash != client.client_secret_hash:
        return None
    
    return client

def create_access_token(data: dict, expires_minutes: int = 60) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, get_active_secret_key(), algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_access_token(token: str) -> Optional[dict]:
    """验证访问令牌"""
    try:
        payload = decode_token(token)
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问令牌已过期"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的访问令牌"
        )

# ============ API端点 ============

@router.post("/clients")
@limiter.limit(rate_limits["write"])
def create_api_client(
    request: Request,
    client_data: ApiClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建API客户端
    
    权限要求: admin角色
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    
    # 生成客户端凭证
    client_id = generate_client_id()
    client_secret = generate_client_secret()
    secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
    
    # 创建客户端记录
    client = ApiClient(
        client_id=client_id,
        client_secret_hash=secret_hash,
        name=client_data.name,
        description=client_data.description,
        callback_url=client_data.callback_url,
        scopes=",".join(client_data.scopes),
        status="active",
        created_by=current_user.id
    )
    
    db.add(client)
    db.commit()
    db.refresh(client)
    
    # 审计日志
    audit_service.log(
        action="api_client_create",
        user_id=current_user.id,
        resource_type="api_client",
        resource_id=client.id,
        details={"client_id": client_id, "name": client_data.name}
    )
    
    return ApiClientResponse(
        client_id=client_id,
        client_secret=client_secret,
        name=client.name,
        description=client.description,
        callback_url=client.callback_url,
        scopes=client.scopes.split(","),
        status=client.status,
        created_at=client.created_at,
        rate_limit=client.rate_limit
    )

@router.post("/keys")
@limiter.limit(rate_limits["write"])
def create_api_key(
    request: Request,
    key_data: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建API密钥
    
    权限要求: 客户端所有者或管理员
    """
    # 验证客户端
    client = db.query(ApiClient).filter(
        ApiClient.client_id == key_data.client_id,
        ApiClient.status == "active"
    ).first()
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户端不存在或已禁用"
        )
    
    # 检查权限（客户端创建者或管理员）
    if client.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权为此客户端创建密钥"
        )
    
    # 生成API密钥
    api_key = generate_api_key()
    
    # 计算过期时间
    expires_at = None
    if key_data.expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(days=key_data.expires_in)
    
    # 创建密钥记录
    key_record = ApiKey(
        key_id=f"key_{uuid.uuid4().hex[:12]}",
        client_id=client.id,
        name=key_data.name,
        api_key=api_key,
        expires_at=expires_at,
        status="active",
        created_by=current_user.id
    )
    
    db.add(key_record)
    db.commit()
    db.refresh(key_record)
    
    # 审计日志
    audit_service.log(
        action="api_key_create",
        user_id=current_user.id,
        resource_type="api_key",
        resource_id=key_record.id,
        details={"client_id": key_data.client_id, "name": key_data.name}
    )
    
    return ApiKeyResponse(
        key_id=key_record.key_id,
        client_id=key_data.client_id,
        name=key_record.name,
        api_key=api_key,
        expires_at=key_record.expires_at,
        status=key_record.status,
        created_at=key_record.created_at
    )

def _assert_key_permission(key_record: ApiKey, current_user: User) -> None:
    """密钥操作权限: 创建者或 admin (与 create_api_key 同口径)。"""
    if key_record.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此密钥"
        )


@router.post("/keys/{key_id}/revoke")
@limiter.limit(rate_limits["write"])
def revoke_api_key(
    request: Request,
    key_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    撤销API密钥 (卡片 ba9d3461)

    权限要求: 密钥创建者或管理员
    """
    key_record = db.query(ApiKey).filter(ApiKey.key_id == key_id).first()
    if not key_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="密钥不存在"
        )
    _assert_key_permission(key_record, current_user)

    old_api_key = key_record.api_key
    key_record.status = "revoked"
    db.commit()

    # 联动失效 30s TTL 鉴权缓存, 保证撤销立即生效
    from app.core.auth_throttle import evict_cached_gateway_key
    evict_cached_gateway_key(old_api_key)

    audit_service.log(
        action="api_key_revoke",
        user_id=current_user.id,
        resource_type="api_key",
        resource_id=key_record.id,
        details={"key_id": key_id}
    )

    return success_response("API密钥已撤销")


@router.post("/keys/{key_id}/rotate")
@limiter.limit(rate_limits["write"])
def rotate_api_key(
    request: Request,
    key_id: str,
    rotate_data: Optional[ApiKeyRotate] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    轮换API密钥 (卡片 ba9d3461): 旧 key 置 revoked, 签发新 key

    权限要求: 密钥创建者或管理员
    """
    key_record = db.query(ApiKey).filter(ApiKey.key_id == key_id).first()
    if not key_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="密钥不存在"
        )
    _assert_key_permission(key_record, current_user)

    old_api_key = key_record.api_key
    client_id_str = key_record.client.client_id
    key_record.status = "revoked"
    db.commit()
    new_api_key = generate_api_key()
    expires_at = None
    if rotate_data and rotate_data.expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(days=rotate_data.expires_in)

    new_record = ApiKey(
        key_id=f"key_{uuid.uuid4().hex[:12]}",
        client_id=key_record.client_id,
        name=key_record.name,
        api_key=new_api_key,
        expires_at=expires_at,
        status="active",
        created_by=current_user.id
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)

    # 旧 key 缓存联动失效
    from app.core.auth_throttle import evict_cached_gateway_key
    evict_cached_gateway_key(old_api_key)

    audit_service.log(
        action="api_key_rotate",
        user_id=current_user.id,
        resource_type="api_key",
        resource_id=new_record.id,
        details={"old_key_id": key_id, "new_key_id": new_record.key_id}
    )

    return ApiKeyResponse(
        key_id=new_record.key_id,
        client_id=client_id_str,
        name=new_record.name,
        api_key=new_api_key,
        expires_at=new_record.expires_at,
        status=new_record.status,
        created_at=new_record.created_at
    )


@router.post("/oauth/token")
@limiter.limit(rate_limits["login"])
async def get_oauth_token(
    request: Request,
    token_request: OAuthTokenRequest,
    db: Session = Depends(get_db)
):
    """
    OAuth2.0令牌端点
    
    支持授权类型:
    - client_credentials: 客户端凭证
    - authorization_code: 授权码
    - refresh_token: 刷新令牌
    """
    # 验证客户端
    client = verify_client_credentials(
        token_request.client_id,
        token_request.client_secret or "",
        db
    )
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="客户端认证失败"
        )
    
    # 根据授权类型处理
    if token_request.grant_type == "client_credentials":
        # 客户端凭证模式
        scope = token_request.scope or "read"
        token_data = {
            "sub": f"client:{client.client_id}",
            "client_id": client.client_id,
            "scope": scope,
            "type": "client_credentials"
        }
        
        access_token = create_access_token(token_data, expires_minutes=60)
        refresh_token = create_access_token(
            {"sub": f"refresh:{client.client_id}", "type": "refresh"},
            expires_minutes=1440  # 24小时
        )
        
        return OAuthTokenResponse(
            access_token=access_token,
            expires_in=3600,  # 1小时
            refresh_token=refresh_token,
            scope=scope
        )
    
    elif token_request.grant_type == "authorization_code":
        # 授权码模式
        if not token_request.code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="授权码模式需要 code 参数"
            )
        # 卡片 ba9d3461: 查 OAuthAuthorizationCode 表验证授权码
        # (归属当前 client / 未使用 / 未过期), 用后即焚 (used=True)
        auth_code = db.query(OAuthAuthorizationCode).filter(
            OAuthAuthorizationCode.code == token_request.code,
            OAuthAuthorizationCode.client_id == client.id,
            OAuthAuthorizationCode.used == False  # noqa: E712
        ).first()
        if not auth_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的授权码"
            )
        _code_expires = auth_code.expires_at
        if _code_expires and _code_expires.tzinfo is None:
            _code_expires = _code_expires.replace(tzinfo=timezone.utc)
        if _code_expires and _code_expires < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="授权码已过期"
            )
        auth_code.used = True
        db.commit()
        scope = token_request.scope or auth_code.scopes or "read"
        token_data = {
            "sub": f"auth:{client.client_id}",
            "client_id": client.client_id,
            "code": token_request.code,
            "scope": scope,
            "type": "authorization_code",
        }
        access_token = create_access_token(token_data, expires_minutes=60)
        refresh_token = create_access_token(
            {"sub": f"refresh:{client.client_id}", "type": "refresh"},
            expires_minutes=1440
        )
        return OAuthTokenResponse(
            access_token=access_token,
            expires_in=3600,
            refresh_token=refresh_token,
            scope=scope
        )
    
    elif token_request.grant_type == "refresh_token":
        # 刷新令牌模式
        if not token_request.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="刷新令牌模式需要 refresh_token 参数"
            )
        # 验证刷新令牌
        refresh_payload = verify_access_token(token_request.refresh_token)
        if refresh_payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的刷新令牌"
            )
        # 签发新的访问令牌
        scope = token_request.scope or refresh_payload.get("scope", "read")
        token_data = {
            "sub": refresh_payload.get("sub", f"refresh:{client.client_id}"),
            "client_id": client.client_id,
            "scope": scope,
            "type": "refresh_token",
        }
        access_token = create_access_token(token_data, expires_minutes=60)
        new_refresh_token = create_access_token(
            {"sub": f"refresh:{client.client_id}", "type": "refresh"},
            expires_minutes=1440
        )
        return OAuthTokenResponse(
            access_token=access_token,
            expires_in=3600,
            refresh_token=new_refresh_token,
            scope=scope
        )
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的授权类型: {token_request.grant_type}"
        )

@router.get("/stats")
@limiter.limit(rate_limits["global"])
def get_api_stats(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="统计天数(1-90)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取API使用统计
    
    权限要求: admin角色
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    
    # 计算时间范围
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    # 查询统计数据
    logs = db.query(ApiRequestLog).filter(
        ApiRequestLog.request_time >= start_time,
        ApiRequestLog.request_time <= end_time
    ).all()
    
    total_requests = len(logs)
    successful_requests = len([log for log in logs if 200 <= log.response_status < 300])
    failed_requests = total_requests - successful_requests
    
    # 计算平均响应时间
    response_times = [log.response_time or 0 for log in logs if log.response_time]
    average_response_time = sum(response_times) / len(response_times) if response_times else 0
    
    # 获取热门端点
    from collections import Counter
    endpoint_counter = Counter(f"{log.method} {log.endpoint}" for log in logs)
    top_endpoints = [
        {"endpoint": endpoint, "count": count}
        for endpoint, count in endpoint_counter.most_common(10)
    ]
    
    return ApiUsageStats(
        total_requests=total_requests,
        successful_requests=successful_requests,
        failed_requests=failed_requests,
        average_response_time=average_response_time,
        top_endpoints=top_endpoints
    )

@router.post("/endpoints/register")
@limiter.limit(rate_limits["write"])
def register_api_endpoint(
    request: Request,
    endpoint_data: EndpointRegister,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    注册API端点
    
    权限要求: admin角色
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    
    # 检查端点是否已存在
    existing = db.query(ApiEndpoint).filter(
        ApiEndpoint.path == endpoint_data.path,
        ApiEndpoint.method == endpoint_data.method.upper()
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="API端点已存在"
        )
    
    # 创建端点记录
    endpoint = ApiEndpoint(
        path=endpoint_data.path,
        method=endpoint_data.method.upper(),
        description=endpoint_data.description,
        rate_limit=endpoint_data.rate_limit or 1000,
        require_auth=endpoint_data.require_auth,
        status="active",
        registered_by=current_user.id
    )
    
    db.add(endpoint)
    db.commit()
    
    # 审计日志
    audit_service.log(
        action="api_endpoint_register",
        user_id=current_user.id,
        resource_type="api_endpoint",
        resource_id=endpoint.id,
        details={"path": endpoint_data.path, "method": endpoint_data.method}
    )
    
    return success_response("API端点注册成功")