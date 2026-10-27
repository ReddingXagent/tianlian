"""IM-B小程序订阅消息推送 (用户端云端契约 §5.5, 工作卡 3591ea8f)

职责:
- access_token 管理: stable_token 接口获取 + 进程内缓存 (7200s, 提前 5min 刷新避免边界失效)
- send_subscribe_msg: HTTP POST cgi-bin/message/subscribe/send, 失败重试 + 日志
- resolve_openid: 从 InvoiceRequest.order_ids 取任一订单 → 查 payment_orders.openid

设计要点:
- 通知层保持纯函数 (大圣方案A): openid 由 service 层解析后传入, 本模块不耦合 InvoiceRequest 语义
- 无 settings.WX_MP_APPID 时优雅降级为日志 (开发/测试零配置可用)
- IM-B订阅消息属「平台级单租户能力」: access_token 凭证来自 settings.WX_MP_APPID/SECRET
  (非 ChannelConfig 的 webhook_url 模式), 凭证缺失 → 降级日志不发, 不抛异常
- HTTP: httpx 超时 5s, 失败重试 2 次 (指数退避, 与 channel_providers 同源)

测试缝:
- get_access_token / send_subscribe_msg 接受注入式 client (FakeClient), 绕过真实 httpx
- backoff 参数归零 + monkeypatch asyncio.sleep 跳过退避
- settings 通过模块属性引用, 测试 monkeypatch mod.settings 切换凭证有无分支

参考文档:
- 订阅消息发送: https://developers.weixin.qq.com/miniprogram/dev/api-backend/open-api/subscribe-message/subscribeMessage.send.html
- access_token (stable_token): https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/mp-access-token/getStableAccessToken.html
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.models.payment_order import PaymentOrder
from app.utils.sanitize import mask_token

logger = logging.getLogger(__name__)

# IM-B API 端点
_WX_API_BASE = "https://api.weixin.qq.com"
_TOKEN_PATH = "/cgi-bin/stable_token"
_SUBSCRIBE_SEND_PATH = "/cgi-bin/message/subscribe/send"

# access_token 缓存: IM-B文档标称 7200s, 提前 300s 刷新避免边界过期 (errcode 40001)
_TOKEN_TTL = 7200
_TOKEN_REFRESH_MARGIN = 300

# 发送参数 (与 channel_providers 一致: 超时 5s, 重试 2 次)
DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF = 0.1

# 进程内 access_token 缓存 {value, expires_at(绝对 epoch 秒)}; 模块级单例
_token_cache: Dict[str, float | str] = {"value": None, "expires_at": 0.0}

# 并发刷新保护: get_access_token 的 double-check 锁, 防止缓存过期瞬间多个协程
# 并发触发 _fetch_access_token (其内部 await httpx 会让出事件循环)。
# async 场景用 asyncio.Lock (非 threading.Lock)。lazy 初始化: 首次使用时在运行协程的
# loop 上创建, 兼容 Python 3.9 (其 asyncio.Lock 在 __init__ 即绑定 get_event_loop,
# 模块级实例化会绑到 import 时的 loop, 与 asyncio.run 的新 loop 冲突)。
_token_lock: Optional[asyncio.Lock] = None


def _credentials_configured() -> bool:
    """APPID + SECRET 是否齐备 (均非空)。测试通过 monkeypatch mod.settings 切换。"""
    return bool(getattr(settings, "WX_MP_APPID", None)) and bool(
        getattr(settings, "WX_MP_SECRET", None)
    )


# ============================================================
# access_token 管理 (stable_token, 进程内缓存)
# ============================================================

async def _fetch_access_token(client=None) -> Optional[str]:
    """调用 stable_token 取 access_token。

    stable_token 较 gettoken 受限频策略更宽松 (无 QPS 上限), 适合服务端循环发送。
    client 为 None 时自建 httpx.AsyncClient 并用后关闭; 注入式 client 原样用不关闭。

    凭证未配置 → 不发请求, 返回 None (优雅降级)。
    失败 (非 200 / errcode != 0 / 异常) → 记日志返回 None, 不抛。
    """
    if not _credentials_configured():
        logger.info("[WX SUBSCRIBE] APPID/SECRET 未配置, 跳过 access_token 获取")
        return None

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
    try:
        payload = {
            "grant_type": "client_credential",
            "appid": settings.WX_MP_APPID,
            "secret": settings.WX_MP_SECRET,
            "force_refresh": False,
        }
        resp = await client.post(
            f"{_WX_API_BASE}{_TOKEN_PATH}",
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
        body = _safe_json(resp)
    except Exception as e:
        logger.error("[WX SUBSCRIBE] access_token 请求异常: %s", e)
        return None
    finally:
        if own_client:
            await client.aclose()

    if not body or body.get("errcode"):
        logger.error(
            "[WX SUBSCRIBE] access_token 获取失败 body=%s", body
        )
        return None
    token = body.get("access_token")
    ttl = body.get("expires_in", _TOKEN_TTL)
    if not token:
        return None
    # 缓存 (绝对过期时间, 提前刷新余量)
    _token_cache["value"] = token
    _token_cache["expires_at"] = time.time() + int(ttl) - _TOKEN_REFRESH_MARGIN
    return token


async def get_access_token(client=None) -> Optional[str]:
    """取 access_token, 命中未过期缓存直接返回, 否则刷新。

    凭证未配置 / 刷新失败 → None (调用方据此降级日志)。
    并发安全 (卡 b03224c4): 无锁快检查 → 过期则持 _token_lock → double-check →
    仍过期才调 _fetch_access_token, 防止多协程并发重复刷新 (其内部 await httpx
    会让出事件循环, 期间其他协程可能发现缓存过期)。
    """
    if not _credentials_configured():
        return None
    now = time.time()
    cached = _token_cache.get("value")
    if cached and _token_cache.get("expires_at", 0) > now:
        return cached
    # lazy 初始化锁 (见 _token_lock 注释), 必须在协程内取运行 loop
    global _token_lock
    if _token_lock is None:
        _token_lock = asyncio.Lock()
    async with _token_lock:
        # double-check: 持锁后可能有协程已刷新成功, 命中则免刷新
        cached = _token_cache.get("value")
        if cached and _token_cache.get("expires_at", 0) > time.time():
            return cached
        return await _fetch_access_token(client)


def invalidate_access_token() -> None:
    """清空 access_token 缓存 (发送遇 40001 失效 token 时调用, 或测试隔离)。"""
    _token_cache["value"] = None
    _token_cache["expires_at"] = 0.0


# ============================================================
# 订阅消息发送
# ============================================================

def _safe_json(resp) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {}


async def _post_subscribe(
    client, url, payload, *,
    max_retries=DEFAULT_MAX_RETRIES, timeout=DEFAULT_TIMEOUT, backoff=DEFAULT_BACKOFF,
):
    """POST 订阅消息发送, 5xx/异常重试 (指数退避), 2xx/4xx 立即返回。

    重试耗尽抛最后一次异常 (由调用方 catch 降级)。"""
    attempts = max_retries + 1
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            resp = await client.post(url, json=payload, headers=None, timeout=timeout)
            if resp.status_code < 500:
                return resp
            last_exc = RuntimeError(f"http {resp.status_code}")
        except Exception as e:
            last_exc = e
        if attempt < attempts - 1:
            await asyncio.sleep(backoff * (2 ** attempt))
    raise last_exc if last_exc else RuntimeError("subscribe send failed")


async def send_subscribe_msg(
    openid: str,
    template_id: str,
    data: Dict[str, Dict[str, str]],
    page: Optional[str] = None,
    *,
    miniprogram_state: Optional[str] = None,
    lang: str = "zh_CN",
    client=None,
    max_retries=DEFAULT_MAX_RETRIES,
    timeout=DEFAULT_TIMEOUT,
    backoff=DEFAULT_BACKOFF,
) -> Dict[str, Any]:
    """发送一条订阅消息。

    Args:
        openid: 接收用户 openid (由 service 层 resolve_openid 解析后传入)
        template_id: 小程序后台订阅消息模板 ID
        data: 模板参数 {key: {value: ...}} (IM-B订阅消息标准结构)
        page: 点击跳转小程序页面 (可选, 如 pages/invoice/detail?id=1)
        miniprogram_state: 开发版/体验版/正式版 (developer/trial/formal)
        lang: 语言, 默认 zh_CN
        client: 注入式 httpx 客户端 (测试缝); None 则自建

    Returns:
        {status: sent|skipped|failed, channel: "wx_subscribe", ...}
        - APPID/SECRET 未配置 → skipped (no_credentials)
        - access_token 获取失败 → failed (no_access_token)
        - IM-B errcode == 0 → sent
        - errcode != 0 / 异常 → failed (含 error)
    永不抛异常 (best-effort: 失败仅记日志, 不阻断开票主流程)。
    """
    if not _credentials_configured():
        logger.info(
            "[WX SUBSCRIBE MOCK] openid=%s tpl=%s page=%s (APPID 未配置, 降级日志)",
            mask_token(openid), template_id, page,
        )
        return {"status": "skipped", "channel": "wx_subscribe",
                "reason": "no_credentials"}

    token = await get_access_token(client)
    if not token:
        return {"status": "failed", "channel": "wx_subscribe",
                "error": "no_access_token"}

    payload: Dict[str, Any] = {
        "touser": openid,
        "template_id": template_id,
        "page": page,
        "data": data,
        "lang": lang,
    }
    if miniprogram_state:
        payload["miniprogram_state"] = miniprogram_state

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout)
    try:
        # token 失效自愈 (卡 e38e2082): 遇 errcode 40001/42001 → invalidate 缓存
        # → 重取 token → 重发一次 (单次防循环); 重取失败或重发仍失败按 failed 返回
        retried_on_token_error = False
        while True:
            url = f"{_WX_API_BASE}{_SUBSCRIBE_SEND_PATH}?access_token={token}"
            try:
                resp = await _post_subscribe(
                    client, url, payload,
                    max_retries=max_retries, timeout=timeout, backoff=backoff,
                )
            except Exception as e:
                logger.error("[WX SUBSCRIBE] 发送请求异常 openid=%s: %s", mask_token(openid), e)
                return {"status": "failed", "channel": "wx_subscribe", "error": str(e)}
            body = _safe_json(resp)
            if (
                body.get("errcode") in (40001, 42001)
                and not retried_on_token_error
            ):
                retried_on_token_error = True
                logger.warning(
                    "[WX SUBSCRIBE] access_token 失效 (errcode=%s), 失效缓存重取重发 openid=%s",
                    body.get("errcode"), mask_token(openid),
                )
                invalidate_access_token()
                token = await get_access_token(client)
                if not token:
                    return {"status": "failed", "channel": "wx_subscribe",
                            "error": "no_access_token"}
                continue
            break
    finally:
        if own_client:
            await client.aclose()

    if body.get("errcode") == 0 or (not body.get("errcode") and resp.status_code == 200):
        logger.info("[WX SUBSCRIBE] 已发送 openid=%s tpl=%s", mask_token(openid), template_id)
        return {"status": "sent", "channel": "wx_subscribe"}
    logger.error(
        "[WX SUBSCRIBE] 发送失败 openid=%s body=%s http=%s",
        mask_token(openid), body, resp.status_code,
    )
    return {"status": "failed", "channel": "wx_subscribe",
            "error": str(body) or f"http {resp.status_code}"}


# ============================================================
# resolve_openid: InvoiceRequest → openid (service 层调用)
# ============================================================

def _invoice_order_ids(invoice_request) -> list[str]:
    """从 InvoiceRequest 提取订单号列表 (兼容 JSON 字符串 / list / 缺失)。"""
    raw = getattr(invoice_request, "order_ids", None)
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw]
    # JSON 字符串 (生产 InvoiceRequest.order_ids 存 json.dumps 结果)
    import json
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


def resolve_openid(db, invoice_request) -> Optional[str]:
    """从开票申请解析用户 openid (契约 §5.5 推送目标)。

    取 invoice_request.order_ids 的任一订单号 → 查 payment_orders.business_order_no
    → 返回该支付单 openid。任一订单有支付单即返回 (用户 openid 唯一, 取首个命中)。

    无支付单记录 (余额支付/历史脏数据未建 payment_order) → None (调用方据此降级日志)。
    永不抛异常 (best-effort)。
    """
    order_ids = _invoice_order_ids(invoice_request)
    for oid in order_ids:
        try:
            po = (
                db.query(PaymentOrder)
                .filter(PaymentOrder.business_order_no == oid)
                .first()
            )
        except Exception as e:
            logger.warning("[WX SUBSCRIBE] resolve_openid 查询异常 order=%s: %s", oid, e)
            continue
        if po and po.openid:
            return po.openid
    return None
