"""通知渠道真实发送 (卡 8d98ebe3)

按 ChannelConfig(team_id, channel) 凭证做真实触达:
- im: 群机器人 webhook, markdown/text 消息体, HMAC-SHA256 签名 (timestamp+secret)
- wecom:  群机器人 webhook, text/markdown 消息体
- webhook: 自定义 URL, JSON payload
- sms/voice: Provider 接口 (ABC) + 云服务商 SDK 形状占位, 未报备期间走 mock log
- email: mock (真实 SMTP 在 notification_dispatcher, 本模块不重复)

HTTP: httpx.AsyncClient 超时 5s, 失败重试 2 次 (指数退避), 最终失败由调用方落
notification_logs。渠道未配置 / enabled=False / 凭证缺失 → 跳过不发 (INFO)。

测试缝: send_channel 接受注入式 ``client`` (FakeClient), 绕过真实 httpx; 退避通过
``backoff`` 参数归零, ``cp.asyncio.sleep`` 可被 monkeypatch。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union

import httpx

from app.models.channel_config import ChannelConfig, ChannelType
from app.utils.sanitize import mask_email, mask_phone, mask_token

logger = logging.getLogger(__name__)

# 默认发送参数 (与卡面契约一致: 超时 5s, 重试 2 次)
DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF = 0.1

# 需要 webhook_url 的 HTTP 渠道
_HTTP_CHANNELS = ("im", "wecom", "webhook")


# ============================================================
# IM签名 (官方自定义机器人 HMAC-SHA256)
# 文档: https://open.im.cn/document/client-docs/bot-v3/add-custom-bot
# ============================================================

def im_sign(timestamp: int, secret: str) -> str:
    """IM自定义机器人签名: 以 ``f"{timestamp}\\n{secret}"`` 为 key 的 HMAC-SHA256,
    base64 编码。timestamp 为秒级整数的字符串形式 (官方约定)。"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _build_im_payload(content: str, secret: Optional[str]) -> Dict[str, Any]:
    """构造IM消息体。有 secret 时附加 timestamp + sign。"""
    payload: Dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": content},
    }
    if secret:
        ts = int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = im_sign(ts, secret)
    return payload


def _eval_im(resp) -> Dict[str, Any]:
    """判定IM响应: code==0 或旧版 StatusCode==0 视为成功。"""
    try:
        body = resp.json()
    except Exception:
        body = {}
    if body.get("code") == 0 or body.get("StatusCode") == 0:
        return {"status": "sent", "channel": "im"}
    return {"status": "failed", "channel": "im", "error": str(body)}


# ============================================================
# HTTP 重试 (超时 5s + 指数退避, 5xx/异常重试, 4xx 不重试)
# ============================================================

async def _post_with_retry(
    client, url, payload, headers, *,
    max_retries=DEFAULT_MAX_RETRIES, timeout=DEFAULT_TIMEOUT, backoff=DEFAULT_BACKOFF,
):
    """POST with retry. 5xx 与网络异常重试 (指数退避 backoff*2^attempt),
    2xx/4xx 立即返回交由调用方判定业务成功。重试耗尽抛最后一次异常。

    client 为 None 时自建 httpx.AsyncClient(timeout) 并用后关闭; 注入式 client
    (测试 FakeClient) 原样使用不关闭。"""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout)
    attempts = max_retries + 1
    last_exc: Optional[Exception] = None
    try:
        for attempt in range(attempts):
            try:
                resp = await client.post(
                    url, json=payload, headers=headers, timeout=timeout
                )
                if resp.status_code < 500:
                    return resp  # 2xx/4xx: 不重试
                last_exc = RuntimeError(f"http {resp.status_code}")
            except Exception as e:
                last_exc = e
            if attempt < attempts - 1:
                await asyncio.sleep(backoff * (2 ** attempt))
        raise last_exc if last_exc else RuntimeError("send failed")
    finally:
        if own_client:
            await client.aclose()


# ============================================================
# 各渠道真实发送 (async)
# ============================================================

async def _send_im(config, content, client, **retry_kw) -> Dict[str, Any]:
    url = (config or {}).get("webhook_url")
    if not url:
        return {"status": "skipped", "channel": "im", "reason": "no webhook_url"}
    secret = (config or {}).get("secret")
    payload = _build_im_payload(content, secret)
    try:
        resp = await _post_with_retry(
            client, url, payload, {"Content-Type": "application/json"}, **retry_kw
        )
    except Exception as e:
        return {"status": "failed", "channel": "im", "error": str(e)}
    return _eval_im(resp)


async def _send_wecom(config, content, client, **retry_kw) -> Dict[str, Any]:
    url = (config or {}).get("webhook_url")
    if not url:
        return {"status": "skipped", "channel": "wecom", "reason": "no webhook_url"}
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    try:
        resp = await _post_with_retry(
            client, url, payload, {"Content-Type": "application/json"}, **retry_kw
        )
    except Exception as e:
        return {"status": "failed", "channel": "wecom", "error": str(e)}
    try:
        body = resp.json()
    except Exception:
        body = {}
    if body.get("errcode") == 0:
        return {"status": "sent", "channel": "wecom"}
    return {"status": "failed", "channel": "wecom", "error": str(body)}


async def _send_webhook(config, content, subject, client, **retry_kw) -> Dict[str, Any]:
    url = (config or {}).get("webhook_url")
    if not url:
        return {"status": "skipped", "channel": "webhook", "reason": "no webhook_url"}
    payload = {"text": content, "subject": subject, "content": content}
    headers = {"Content-Type": "application/json"}
    secret = (config or {}).get("secret")
    if secret:
        headers["X-Webhook-Secret"] = secret  # 自定义校验头 (预留)
    try:
        resp = await _post_with_retry(client, url, payload, headers, **retry_kw)
    except Exception as e:
        return {"status": "failed", "channel": "webhook", "error": str(e)}
    if 200 <= resp.status_code < 300:
        return {"status": "sent", "channel": "webhook"}
    return {"status": "failed", "channel": "webhook", "error": f"http {resp.status_code}"}


# ============================================================
# SMS / Voice Provider 接口 (未报备 → mock log)
# ============================================================

class SmsProvider(ABC):
    """短信服务商接口 (云服务商 SDK 形状)。报备完成前实现走 mock log。"""

    @abstractmethod
    def send(self, phone: str, content: str, config: Dict[str, Any]) -> Dict[str, Any]:
        ...


class VoiceProvider(ABC):
    """语音外呼服务商接口。报备完成前实现走 mock log。"""

    @abstractmethod
    def send(self, phone: str, content: str, config: Dict[str, Any]) -> Dict[str, Any]:
        ...


class _CloudProviderSmsProvider(SmsProvider):
    """云服务商短信占位 (未报备): 预留 AccessKey/Secret/SignName/TemplateCode 配置位,
    实际发送走 mock log, 不触达。报备后切真实 SDK 仅改本类 send 体。"""

    def send(self, phone, content, config):
        logger.info(
            "[SMS ALIYUN-STUB] to=%s sign=%s tpl=%s msg=%s",
            mask_phone(phone), (config or {}).get("sign_name"),
            (config or {}).get("template_code"), (content or "")[:60],
        )
        return {
            "status": "mock", "channel": "sms", "provider": "cloud_provider-stub",
            "phone": phone,
        }


class _CloudProviderVoiceProvider(VoiceProvider):
    """云端语音外呼占位 (未报备): 同上, mock log。"""

    def send(self, phone, content, config):
        logger.info(
            "[VOICE ALIYUN-STUB] to=%s caller=%s tpl=%s msg=%s",
            mask_phone(phone), (config or {}).get("voice_caller"),
            (config or {}).get("voice_template_code"), (content or "")[:60],
        )
        return {
            "status": "mock", "channel": "voice", "provider": "cloud_provider-stub",
            "phone": phone,
        }


def get_sms_provider(config: Dict[str, Any]) -> SmsProvider:
    """短信服务商工厂。预留 provider 配置位切换; 默认云服务商形状 stub (未报备)。"""
    name = (config or {}).get("provider", "cloud-a")
    if name == "cloud-a":
        return _CloudProviderSmsProvider()
    return _CloudProviderSmsProvider()  # 其余厂商亦走 stub 直至报备


def get_voice_provider(config: Dict[str, Any]) -> VoiceProvider:
    """语音服务商工厂。默认云服务商形状 stub (未报备)。"""
    return _CloudProviderVoiceProvider()


def _provider_result(channel: str, phone: str, send_result,
                     exc: Exception = None) -> Dict[str, Any]:
    """透传 provider.send() 结果 (卡 c7b06c98)。

    mock status (未报备 stub) → 保持 sent+provider:mock 向后兼容;
    非 mock status 原样透传 (真实 provider 失败不再被吞);
    异常 → failed 不上抛。"""
    if exc is not None:
        logger.error("[%s PROVIDER] 发送异常 phone=%s: %s",
                     channel.upper(), mask_phone(phone), exc)
        return {"status": "failed", "channel": channel,
                "error": str(exc), "phone": phone}
    result = dict(send_result or {})
    if result.get("status") == "mock":
        # 向后兼容: mock 阶段未真实触达, 统一报 sent+provider:mock
        return {"status": "sent", "channel": channel,
                "provider": "mock", "phone": phone}
    result.setdefault("channel", channel)
    result.setdefault("phone", phone)
    return result


def _send_sms(config, content, receiver) -> Dict[str, Any]:
    phone = (receiver or {}).get("phone") or (receiver or {}).get("id") or ""
    provider = get_sms_provider(config or {})
    result = provider.send(phone, content, config or {})  # 异常上抛 (卡 4d257e26)
    return _provider_result("sms", phone, result)


def _send_voice(config, content, receiver) -> Dict[str, Any]:
    phone = (receiver or {}).get("phone") or (receiver or {}).get("id") or ""
    provider = get_voice_provider(config or {})
    result = provider.send(phone, content, config or {})  # 异常上抛 (卡 4d257e26)
    return _provider_result("voice", phone, result)


def _send_email_mock(config, content, receiver, subject) -> Dict[str, Any]:
    # 真实 SMTP 在 notification_dispatcher; 本模块仅 mock (卡面真实化范围不含 email)
    logger.info("[EMAIL MOCK] to=%s subject=%s msg=%s",
                mask_email((receiver or {}).get("email") or ""),
                subject, (content or "")[:60])
    return {"status": "sent", "channel": "email", "provider": "mock"}


# ============================================================
# IM-B小程序订阅消息 (卡 3591ea8f, 凭证来自 settings.WX_MP_* 而非 webhook_url)
# ============================================================

async def _send_wx_subscribe(config, content, client, **retry_kw) -> Dict[str, Any]:
    """IM-B小程序订阅消息发送。

    config 运行时字段 (由调用方注入):
      - openid: 接收用户 openid (service 层 resolve_openid 解析后传入)
      - template_id: 订阅消息模板 ID
      - data: 模板参数 {key: {value: ...}} (可选, 缺省空 dict)
      - page: 跳转页 (可选)
      - miniprogram_state: 开发/体验/正式版 (可选)

    access_token 凭证来自 settings.WX_MP_APPID/SECRET (平台级), 非本渠道 config。
    APPID 未配置 → send_subscribe_msg 内部降级 skipped (no_credentials)。
    """
    from app.services import wx_subscribe_msg

    cfg = config or {}
    openid = cfg.get("openid")
    template_id = cfg.get("template_id")
    if not openid:
        return {"status": "skipped", "channel": "wx_subscribe",
                "reason": "no_openid"}
    if not template_id:
        return {"status": "skipped", "channel": "wx_subscribe",
                "reason": "no_template_id"}
    try:
        return await wx_subscribe_msg.send_subscribe_msg(
            openid=openid,
            template_id=template_id,
            data=cfg.get("data") or {},
            page=cfg.get("page"),
            miniprogram_state=cfg.get("miniprogram_state"),
            client=client,
            max_retries=retry_kw.get("max_retries", DEFAULT_MAX_RETRIES),
            timeout=retry_kw.get("timeout", DEFAULT_TIMEOUT),
            backoff=retry_kw.get("backoff", DEFAULT_BACKOFF),
        )
    except Exception as e:
        # send_subscribe_msg 本应不抛 (best-effort), 此处二次兜底防 channel 路径漏网
        logger.error("[WX SUBSCRIBE] 渠道发送异常 openid=%s: %s", mask_token(openid), e)
        return {"status": "failed", "channel": "wx_subscribe", "error": str(e)}


# ============================================================
# send_channel: 单渠道发送入口 (async)
# ============================================================

def _norm_channel(channel: Union[str, ChannelType]) -> str:
    if isinstance(channel, ChannelType):
        return channel.value
    return str(channel)


async def send_channel(
    channel, config, content, subject=None, receiver=None, *,
    client=None, max_retries=DEFAULT_MAX_RETRIES,
    timeout=DEFAULT_TIMEOUT, backoff=DEFAULT_BACKOFF,
) -> Dict[str, Any]:
    """向单渠道发送。返回 {status: sent|skipped|failed, channel, error?}。

    Args:
        channel: 渠道名 (str) 或 ChannelType
        config: ChannelConfig.config 凭证 dict
        client: 可选注入式 httpx 客户端 (测试缝); None 则自建
        max_retries: 失败重试次数 (默认 2)
        timeout: HTTP 超时秒 (默认 5)
        backoff: 退避基数秒 (默认 0.1, 指数 0.1/0.2)
    """
    ch = _norm_channel(channel)
    retry_kw = dict(max_retries=max_retries, timeout=timeout, backoff=backoff)
    if ch == "im":
        return await _send_im(config, content, client, **retry_kw)
    if ch == "wecom":
        return await _send_wecom(config, content, client, **retry_kw)
    if ch == "webhook":
        return await _send_webhook(config, content, subject, client, **retry_kw)
    if ch == "sms":
        return _send_sms(config, content, receiver)
    if ch == "voice":
        return _send_voice(config, content, receiver)
    if ch == "email":
        return _send_email_mock(config, content, receiver, subject)
    if ch == "wx_subscribe":
        return await _send_wx_subscribe(config, content, client, **retry_kw)
    return {"status": "failed", "channel": ch, "error": f"unsupported channel: {ch}"}


# ============================================================
# dispatch_real_channel: ChannelConfig 查询 + 跳过 + 同步桥接
# ============================================================

def _run_sync(coro):
    """同步执行协程, 不污染线程全局事件循环 (同 im_notify._run_coro_sync)。

    有运行循环 (async worker) → 独立线程跑; 无 → asyncio.run。"""
    try:
        asyncio.get_running_loop()
        running = True
    except RuntimeError:
        running = False
    if running:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _lookup_channel_config(db, team_id: Optional[int], channel: str):
    """查启用的 ChannelConfig: 先 team 级, 再平台级 (team_id NULL) 回退。"""
    try:
        ch_enum = ChannelType(channel)
    except ValueError:
        return None
    cfg = db.query(ChannelConfig).filter(
        ChannelConfig.team_id == team_id,
        ChannelConfig.channel == ch_enum,
        ChannelConfig.enabled == True,  # noqa: E712
    ).first()
    if cfg is None and team_id is not None:
        cfg = db.query(ChannelConfig).filter(
            ChannelConfig.team_id.is_(None),
            ChannelConfig.channel == ch_enum,
            ChannelConfig.enabled == True,  # noqa: E712
        ).first()
    return cfg


def dispatch_real_channel(
    channel, team_id, db, receiver, content, subject=None, *, client=None,
) -> Dict[str, Any]:
    """读 ChannelConfig 凭证做真实发送 (同步入口, 供 notification_sender 调用)。

    返回 {status: sent|skipped|failed, channel, reason/error?}:
    - 渠道未配置/enabled=False → skipped (no_config)
    - HTTP 渠道缺 webhook_url → skipped (no_credential)
    - 发送重试耗尽/异常 → failed
    - 成功 → sent
    永不抛异常 (状态由调用方落 notification_logs)。"""
    ch = _norm_channel(channel)
    cfg = _lookup_channel_config(db, team_id, ch)
    if cfg is None:
        logger.info("渠道 %s 未配置/未启用 (team=%s), 跳过", ch, team_id)
        return {"status": "skipped", "channel": ch, "reason": "no_config"}
    config = cfg.config or {}
    if ch in _HTTP_CHANNELS and not config.get("webhook_url"):
        logger.info("渠道 %s 缺 webhook_url (team=%s), 跳过", ch, team_id)
        return {"status": "skipped", "channel": ch, "reason": "no_credential"}
    try:
        return _run_sync(send_channel(
            ch, config, content, subject=subject, receiver=receiver, client=client
        ))
    except Exception as e:
        logger.error("渠道 %s 真实发送异常 (team=%s): %s", ch, team_id, e)
        return {"status": "failed", "channel": ch, "error": str(e)}
