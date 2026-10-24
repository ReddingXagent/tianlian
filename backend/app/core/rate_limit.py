"""
API 限流配置 (基于 SlowAPI)

速率限制:
  全局限流: 1000 req/min
  登录端点: 20 req/min (per real IP)
  POST/PUT/DELETE: 100 req/min
"""
import os

from fastapi import HTTPException
from limits import parse
from slowapi import Limiter
from starlette.requests import Request


def _rate_limit_enabled(default: bool = True) -> bool:
    """读取 RATE_LIMIT_ENABLED 开关 (默认开启)。

    测试环境设为 false 关闭限流, 避免 TestClient 同 IP 撞 5/min 登录上限;
    需测限流本身时在测试内 monkeypatch limiter.enabled=True。
    """
    raw = os.getenv("RATE_LIMIT_ENABLED")
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def get_real_ip(request: Request) -> str:
    """获取真实客户端 IP (nginx 反代下读 X-Forwarded-For 首段)。

    优先级: X-Forwarded-For 首段 > X-Real-IP > remote_addr。
    生产 nginx 已设 proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    只取首段(=原始客户端), 防多级代理串。
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


# 创建限流器
limiter = Limiter(
    key_func=get_real_ip,
    default_limits=["1000/minute"],  # 全局限流: 1000 req/min
    enabled=_rate_limit_enabled(),
)

# 端点级限流策略
rate_limits = {
    "global": "1000/minute",
    "login": "20/minute",  # per real IP; 原 5/min 在 nginx 下全站共享会误锁
    "register": "5/minute",  # 注册 per real IP; 防批量注册 (卡 d8fff697)
    "sms_send": "1/minute",  # 短信验证码 per real IP; 防短信轰炸 (高成本, 卡 d8fff697)
    "forgot_password": "5/minute",  # 忘记密码申请 per real IP; 防刷满申请表 (卡 56712a04)
    "write": "100/minute",  # POST/PUT/DELETE
    "sensitive": "10/minute",  # 敏感操作（如修改密码）
    # Pod/Cross 通信端点 per real IP: 合法心跳 30s 一次=2/min, 远低于阈值;
    # 仅拦固定外网IP高频穷举 X-Pod-Secret (卡 d59fdbd5 D2加固)
    "pod": "60/minute",
}


# Pod/Cross 通信限流依赖实例 (60/min per real IP)。
# 不用 @limiter.limit 装饰器: 装饰器在端点函数内执行, 落后于 Depends(verify_pod_comm_secret),
# 鉴权失败(403)不计入 → 拦不住固定外网IP穷举 secret (生产全403)。改用路由级 dependency
# (FastAPI 中 route dependencies 先于端点参数依赖执行), 使 403 与 200 共享同一 IP 配额。
_POD_COMM_LIMIT = parse(rate_limits["pod"])


def limit_pod_comm(request: Request) -> None:
    """Pod/Cross 通信端点 per-real-IP 限流 (60/min)。

    作为路由级 dependency 先于 verify_pod_comm_secret 执行, 故鉴权失败(403)也
    计入同一 IP 配额 — 正是拦固定外网IP高频穷举 X-Pod-Secret 所需。复用全局 limiter
    的 storage / key_func(get_real_ip 读 X-Forwarded-For 首段, 防伪造) / enabled。
    """
    if not limiter.enabled:
        return
    if not limiter._limiter.hit(_POD_COMM_LIMIT, get_real_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁, 请稍后重试",
        )
