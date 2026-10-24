"""网关 X-API-Key 鉴权: 节流器 + TTL 缓存 + 鉴权依赖

从 telemetry.py 抽离 (卡 4c8120a6 纯重构, 零行为变更, API 契约不变)。

生产实证 (timing 埋点, 单位 ms): 同一 client IP 突发并发时 auth_ms 飙到
850-1842ms, 常态仅 5ms; insert/commit 段 <100ms 正常。
根因: 每请求都对同一 api_key 行 UPDATE last_used_at → commit 段行锁串行 →
DB 连接持有更久 → 连接池 (pool_size=50) 占用累积 → 后续请求 auth 段 get_db
checkout 排队 (auth_ms 窗口含 get_db checkout + key SELECT)。
优化 (低风险, API 契约不变):
  ① last_used_at 按 key_id 节流: 进程内 60s/key 最多写一次 DB → 消除并发行锁串行;
  ② key 查询结果 30s TTL 内存缓存 → auth 段免 DB SELECT。
仅进程内 dict + lock, 无 redis 依赖。GatewayApiKey.last_used_at 全仓无读取方,
60s 粒度完全可接受; caller dict 结构不变, 调用方 (telemetry / charging-sessions) 无感。
"""
import logging
import os
import threading
import time
from datetime import datetime as dt, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.timing import warn_auth_internal_slow, warn_dispatch_slow

logger = logging.getLogger("app.core.auth_throttle")

# ─── 网关 API key 鉴权路径性能优化 (卡 round2b auth 段瓶颈) ───────────────
_GATEWAY_LAST_USED_THROTTLE_S = float(
    os.getenv("GATEWAY_LAST_USED_THROTTLE_S", "60")
)
_GATEWAY_KEY_CACHE_TTL_S = float(os.getenv("GATEWAY_KEY_CACHE_TTL_S", "30"))

_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# key_id -> 上次写 last_used_at 的 monotonic 时刻
_last_used_recorded_at: dict = {}
_last_used_lock = threading.Lock()

# api_key -> (caller_dict, expire_monotonic)
_gateway_caller_cache: dict = {}
_gateway_caller_cache_lock = threading.Lock()


def _should_record_last_used(key_id: int) -> bool:
    """节流: 同一 key_id 在 _GATEWAY_LAST_USED_THROTTLE_S 内只允许写一次 DB。

    返回 True 表示本次应写 (并登记时刻); False 表示窗口内已写过, 应跳过。
    进程内 dict + lock, 临界区仅 dict 读写, 不阻塞事件循环。
    """
    now = time.monotonic()
    with _last_used_lock:
        last = _last_used_recorded_at.get(key_id)
        if last is not None and (now - last) < _GATEWAY_LAST_USED_THROTTLE_S:
            return False
        _last_used_recorded_at[key_id] = now
        return True


def _get_cached_gateway_caller(api_key: str):
    """返回未过期的缓存 caller dict, 否则 None。"""
    now = time.monotonic()
    with _gateway_caller_cache_lock:
        entry = _gateway_caller_cache.get(api_key)
        if entry is not None and entry[1] > now:
            return entry[0]
    return None


def _set_cached_gateway_caller(api_key: str, caller: dict) -> None:
    """写入 caller 缓存, TTL = _GATEWAY_KEY_CACHE_TTL_S。"""
    with _gateway_caller_cache_lock:
        _gateway_caller_cache[api_key] = (
            caller,
            time.monotonic() + _GATEWAY_KEY_CACHE_TTL_S,
        )


def evict_cached_gateway_key(api_key: str) -> None:
    """撤销/轮换/过期时联动失效 caller 缓存 (卡片 ba9d3461)。

    30s TTL 缓存内的 key 即便已在 DB 侧 revoked/expired 也会被放行,
    管理面状态变更必须显式驱逐, 保证生命周期动作立即生效。
    """
    with _gateway_caller_cache_lock:
        _gateway_caller_cache.pop(api_key, None)


def _reset_gateway_auth_caches() -> None:
    """清空进程内节流/缓存状态 (测试辅助)。

    用 .clear() 原地清空, 保持 dict 对象身份不变 — telemetry.py 的 back-compat
    re-import 与本模块引用同一对象, in-place 清空对双方均可见。
    """
    with _last_used_lock, _gateway_caller_cache_lock:
        _last_used_recorded_at.clear()
        _gateway_caller_cache.clear()


def get_current_gateway_or_user(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Depends(_optional_oauth2),
    db: Session = Depends(get_db),
):
    # round2c: async def → def。原 async def 内跑同步 db.query 阻塞事件循环,
    # burst 时后续请求 auth 段排队 1-2s(生产 timing 实证: 缓存命中 auth 仍 1046-1354ms)。
    # 转 sync def 后 FastAPI 自动挪线程池执行, 解除 loop 阻塞。
    # 先例: get_current_user(auth.py:114) 已是 sync def。
    _t_auth_enter = time.perf_counter()
    # round2f: 测量 middleware→线程池 dispatch 延迟
    warn_dispatch_slow(request, _t_auth_enter)
    if x_api_key:
        from app.models.api_gateway import GatewayApiKey

        # 路径②: 缓存命中免 DB SELECT, 直接复用 caller dict
        caller = _get_cached_gateway_caller(x_api_key)
        if caller is not None:
            if _should_record_last_used(caller["key_id"]):
                # 节流放行 (60s/key 一次): 独立 Core UPDATE, 随主事务提交释放锁
                db.query(GatewayApiKey).filter(
                    GatewayApiKey.id == caller["key_id"]
                ).update(
                    {GatewayApiKey.last_used_at: dt.now(timezone.utc)},
                    synchronize_session=False,
                )
            warn_auth_internal_slow("cache_hit", _t_auth_enter)
            return caller

        # 路径①: 缓存未命中 → 查 DB 校验 key 并回填缓存
        key = db.query(GatewayApiKey).filter(
            GatewayApiKey.api_key == x_api_key,
            GatewayApiKey.status == "active"
        ).first()
        if not key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        # 卡片 ba9d3461: cache-miss 路径补 expires_at 判定, 对齐
        # api_gateway.verify_api_key 范式 — DB 读出 naive 补 UTC 比较;
        # 过期惰性 UPDATE status='expired' 并 401。
        _expires_at = key.expires_at
        if _expires_at and _expires_at.tzinfo is None:
            _expires_at = _expires_at.replace(tzinfo=timezone.utc)
        if _expires_at and _expires_at < dt.now(timezone.utc):
            key.status = "expired"
            db.commit()
            raise HTTPException(status_code=401, detail="Invalid API key")
        caller = {"type": "gateway", "key_id": key.id, "client_id": key.client_id}
        _set_cached_gateway_caller(x_api_key, caller)
        # 节流放行才标记 last_used_at (ORM 脏标记, 随主事务 commit 一并提交,
        # 不单独 commit — 卡 96593abe)
        if _should_record_last_used(key.id):
            key.last_used_at = dt.now(timezone.utc)
        warn_auth_internal_slow("cache_miss", _t_auth_enter)
        return caller
    if token:
        from app.api.v1.auth import get_current_user
        warn_auth_internal_slow("token", _t_auth_enter)
        return get_current_user(token=token, db=db)
    raise HTTPException(
        status_code=401,
        detail="需要 X-API-Key 或 Bearer Token 认证"
    )
