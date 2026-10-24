"""
Pod 间通信共享密钥校验 (D2 安全加固 — 任务卡 69acc93c)。

背景: /pod /cross 路径原在认证白名单内 (基础设施，现有契约匿名)，导致:
  - 任何人可 POST /pod/register /pod/heartbeat 伪造 pod_id 注册/心跳，污染
    Redis 路由表 (key: tianlian:route:pod:registry:{pod_id})
  - 任何人可 POST /cross/query /cross/internal/query 窃取场站/设备拓扑

加固 (与 alert_webhook._verify_webhook_secret 同源):
  - 共享密钥头 X-Pod-Secret，hmac.compare_digest 常数时间比较，抗时序侧信道
  - secret 未配置(None/空): 拒绝全部请求并 warning，强制生产配置，不保留裸奔兼容
  - pod_id 格式约束 ^[a-zA-Z0-9_-]{1,64}$，防 Redis key / 日志注入
"""
import hmac
import logging
import re

from fastapi import HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)

# Pod ID 格式: 字母/数字/下划线/连字符，1-64 字符。
# 拒绝空格/;/$/../等元字符与路径穿越，防其拼进 Redis key
# (tianlian:route:pod:registry:{pod_id}) 或污染日志。普通 raw string，非 f-string。
POD_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# 共享密钥请求头名
POD_SECRET_HEADER = "X-Pod-Secret"


def verify_pod_comm_secret(request: Request) -> None:
    """Pod 间通信共享密钥校验依赖 (接 Request，由 FastAPI 注入)。

    读请求头 ``X-Pod-Secret``，与 ``settings.POD_COMM_SHARED_SECRET`` 常数时间比较:
      - secret 未配置(None/空) → 拒绝全部请求并 warning (强制配置)
      - 不匹配 → 403

    挂在 /pod register/heartbeat/routes/stations 与 /cross query/internal/query/routes
    端点 (这些路径在 enforce_auth 白名单内，全局认证放行，故必须自证共享密钥)。
    """
    expected = (settings.POD_COMM_SHARED_SECRET or "").strip()
    if not expected:
        logger.warning(
            "POD_COMM_SHARED_SECRET 未配置，/pod /cross 通信端点拒绝所有请求 "
            "（防止伪造 Pod 注册/心跳/跨Pod查询）。请在 .env 配置 POD_COMM_SHARED_SECRET。"
        )
        raise HTTPException(
            status_code=403, detail="Pod communication secret not configured"
        )
    provided = request.headers.get(POD_SECRET_HEADER) or ""
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid pod secret")


def validate_pod_id(pod_id: str) -> str:
    """校验 pod_id 格式，不合法抛 400。

    供 register/heartbeat 端点复用，约束 pod_id 仅含字母/数字/下划线/连字符、
    1-64 字符，防其拼进 Redis key 或日志时被注入。
    """
    if not isinstance(pod_id, str) or not POD_ID_PATTERN.match(pod_id):
        raise HTTPException(
            status_code=400,
            detail="pod_id 格式非法 (仅允许字母数字下划线连字符，长度 1-64)",
        )
    return pod_id
