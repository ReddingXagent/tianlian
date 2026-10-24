"""JPush 极光推送 PushProvider 实现 (卡 7f601f7f, 丁哥 22:28 拍板选型).

REST v3: POST https://api.jpush.cn/v3/push
- Basic auth = AppKey:MasterSecret (httpx auth 参数, 凭证不落日志)
- audience 用 registration_id 数组定向 (device token 体系即 RegistrationID)
- notification: android{title,alert,extras} + ios{alert,extras}, extras 带
  invoice_id/status 供端侧路由

行为:
- 失败重试 1 次 (5xx/网络异常; 4xx 业务错误不重试)
- errcode 1011 (invalid registration_id) → token 记入失效列表, 上层经
  drain_invalid_tokens() 取走后清理库 (duck-typed, 不入 PushProvider 接口)
- 凭证未配置 / JIGUANG_ENABLED=False → 不发请求降级日志返回 True
  (与 base.py no-op 语义一致)
- 永不抛异常 (best-effort), send 返回 bool

测试缝: _client() 注入式 httpx 替身 (与 wx_subscribe_msg 同源),
monkeypatch mod.asyncio.sleep 跳过退避。

参考: https://docs.jiguang.cn/jpush/server/push/rest_api_v3_push
"""
import asyncio
import logging
from typing import Optional

import httpx

from app.core.config import settings
from app.services.push.base import PushProvider

logger = logging.getLogger(__name__)

_JPUSH_API_URL = "https://api.jpush.cn/v3/push"

DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_RETRIES = 1  # 失败重试 1 次 (共 2 次尝试)
DEFAULT_BACKOFF = 0.2

# JPush errcode 1011: 无效的 registration_id (设备卸载/长时间未活跃)
# → 该 token 永久失效, 上层应清理避免持续空发
_ERRCODE_INVALID_REGISTRATION_ID = 1011


class JPushProvider(PushProvider):
    """极光推送 REST v3 适配器 (同步 send 接口, 内部桥接 httpx 异步)。"""

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT,
                 max_retries: int = DEFAULT_MAX_RETRIES,
                 backoff: float = DEFAULT_BACKOFF):
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff = backoff
        self._invalid_tokens: list[str] = []

    # ── 配置判定 ────────────────────────────────────────────────────────────

    @staticmethod
    def _configured() -> bool:
        return (
            bool(getattr(settings, "JIGUANG_ENABLED", False))
            and bool(getattr(settings, "JIGUANG_APP_KEY", None))
            and bool(getattr(settings, "JIGUANG_MASTER_SECRET", None))
        )

    def _client(self):
        """测试缝: 测试 monkeypatch 本方法注入 FakeClient。"""
        return httpx.AsyncClient(timeout=self._timeout)

    # ── 失效 token 信号 (卡 7f601f7f: 1011 → 上层清理) ─────────────────────

    def drain_invalid_tokens(self) -> list[str]:
        """取走本轮累计的失效 registration_id (一次性消费)。"""
        drained, self._invalid_tokens = self._invalid_tokens, []
        return drained

    # ── 发送 ────────────────────────────────────────────────────────────────

    def send(self, end_user_id: int, title: str, body: str, payload: dict) -> bool:
        if not self._configured():
            logger.info(
                "[JPUSH MOCK] end_user_id=%s title=%s payload_keys=%s "
                "(JIGUANG 凭证未配置或未启用, 降级日志)",
                end_user_id, title, sorted(payload),
            )
            return True

        registration_id = payload.get("device_token")
        if not registration_id:
            logger.warning(
                "[JPUSH] 无 device_token, 跳过发送 end_user_id=%s", end_user_id,
            )
            return False

        from app.services.channel_providers import _run_sync

        try:
            return _run_sync(self._send_one(registration_id, title, body, payload))
        except Exception:
            logger.exception(
                "[JPUSH] 发送异常 end_user_id=%s", end_user_id,
            )
            return False

    async def _send_one(self, registration_id: str, title: str, body: str,
                        payload: dict) -> bool:
        """单 token POST v3/push (含重试)。永不抛, 返回是否成功。"""
        extras = {
            k: payload[k] for k in ("invoice_id", "status")
            if k in payload
        }
        api_payload = {
            "platform": ["android", "ios"],
            "audience": {"registration_id": [registration_id]},
            "notification": {
                "android": {"alert": body, "title": title, "extras": extras},
                "ios": {"alert": body, "extras": extras},
            },
        }
        auth = (settings.JIGUANG_APP_KEY, settings.JIGUANG_MASTER_SECRET)

        client = self._client()
        # 注入式替身无 aclose (测试缝); 真实 httpx 客户端需显式关闭
        should_close = hasattr(client, "aclose")
        try:
            attempts = self._max_retries + 1
            for attempt in range(attempts):
                status, resp_body = await self._post(
                    client, api_payload, auth,
                )
                errcode = resp_body.get("errcode")
                if status == 200 and not errcode:
                    return True
                # errcode 1011: registration_id 失效, 不重试, 记入待清理列表
                if errcode == _ERRCODE_INVALID_REGISTRATION_ID:
                    self._invalid_tokens.append(registration_id)
                    logger.info(
                        "[JPUSH] registration_id 已失效 (errcode 1011), "
                        "待上层清理",
                    )
                    return False
                # 其余业务错误 (2xx 带 errcode / 4xx) 不重试
                if status < 500:
                    logger.error(
                        "[JPUSH] 发送失败 http=%s errcode=%s", status, errcode,
                    )
                    return False
                # 5xx / 网络异常 (status=599) → 重试
                logger.warning(
                    "[JPUSH] 第 %s 次尝试失败 http=%s errcode=%s",
                    attempt + 1, status, errcode,
                )
                if attempt < attempts - 1:
                    await asyncio.sleep(self._backoff)
            return False
        finally:
            if should_close:
                await client.aclose()

    async def _post(self, client, api_payload: dict, auth: tuple):
        """单次 POST, 网络异常由调用方重试循环捕获。返回 (status, body)。"""
        try:
            resp = await client.post(
                _JPUSH_API_URL, json=api_payload, auth=auth,
                timeout=self._timeout,
            )
            try:
                body = resp.json()
            except Exception:
                body = {}
            return resp.status_code, body
        except Exception as e:
            logger.warning("[JPUSH] 请求异常: %s", e)
            return 599, {}  # 视同可重试失败
