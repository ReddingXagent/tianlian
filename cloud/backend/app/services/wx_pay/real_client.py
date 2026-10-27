"""IM-B支付 v3 真实客户端骨架 (卡 6c8f930c A1 / 7f5b4d4f A2, 凭证无关)

按 WxPayClient 抽象实现IM-B支付服务商模式 v3 API:
- unified_order: POST /v3/transactions/jsapi|app (scene 决定端点与 appid)
- query_order:  GET /v3/transactions/out-trade-no/{no} (sp_mchid+sub_mchid 过滤)
- refund:       POST /v3/refund/domestic/refunds
- verify_and_decrypt_notify: Wechatpay-Signature 平台证书验签 + AES-256-GCM 解密
- generate_sub_mchid: GET /v3/applyment4sub/applyment_id/{id} (进件 FINISH 取 sub_mchid)

凭证无关设计:
- 凭证 (sp_mchid/serial/私钥/APIv3 key/appid) 只从 settings (env) 读, 严禁硬编码;
  构造时齐备校验 fail-loud → WxPayError (不静默回退 mock)。
- HTTP 传输可注入 (transport 参数, 默认 httpx.Client): 单测打桩零网络。
- 平台证书自动下载/轮换 (卡 7f5b4d4f A2): GET /v3/certificates → APIv3 key
  AES-GCM 解密证书密文 → 按 effective_time/expire_time 选有效证书 → 缓存 +
  剩余有效期 < 1/3 时刷新 → 下载失败回退缓存 → 无可用证书 fail-closed。
  _platform_pubkey / platform_verifier 仍供测试注入 (优先于下载链)。

底层异常约定 (client.py WxPayError docstring): httpx 异常/解析异常统一转
WxPayError, 由 service/router 兜底映射 502。
"""
import base64
import json
import logging
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.services.wx_pay.client import (
    WxPayClient,
    WxPayError,
    PrepayResult,
    NotifyResult,
    OrderQueryResult,
    RefundResult,
)

logger = logging.getLogger(__name__)

_API_BASE = "https://api.mch.weixin.qq.com"
_TIMEOUT_SECONDS = 10.0

# 回调防重放窗 (秒, 卡 071194e4 A3 启用): envelope.create_time 距 now
# 超窗 (过旧=重放 / 过新=时钟投毒) → 拒绝; 缺失/解析失败 fail-closed。
_TIMESTAMP_WINDOW = 300

# 平台证书缓存刷新阈值: 剩余有效期 < 总有效期 1/3 → 每次验签前重新下载
# (IM-B平台证书通常周一轮换, 提前刷新保证新旧证书平滑过渡)。
_CERT_REFRESH_FRACTION = 3


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_wx_time(s) -> Optional[datetime]:
    """IM-B RFC3339 (+08:00) → aware UTC datetime; 失败 → None。

    naive 输入 → None: astimezone 对 naive 按进程 TZ 就地解释 (2026-08-17
    20:00 会被读成 CST 而非保持 naive), 语义不确定即拒绝 (卡 071194e4 A3)。
    """
    if not isinstance(s, str):
        return None
    try:
        parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _notify_time_in_window(envelope: dict) -> bool:
    """envelope.create_time 在 now±_TIMESTAMP_WINDOW 内 → True (卡 071194e4 A3)。

    防重放闸: 过旧 (重放报文) / 过新 (时钟投毒) / 缺失 / 解析失败 / naive 无
    时区 → False。naive 显式拒绝: astimezone 对 naive 按进程 TZ 解释, 语义
    不确定即 fail-closed (资金安全闸风格, 参照 A1 金额闸)。
    """
    create_time = envelope.get("create_time") if isinstance(envelope, dict) else None
    if not isinstance(create_time, str):
        logger.warning("回调缺 create_time, fail-closed 拒绝 (防重放)")
        return False
    ts = _parse_wx_time(create_time)
    if ts is None or ts.tzinfo is None:
        logger.warning(
            "回调 create_time 解析失败/无时区, fail-closed 拒绝: %r", create_time
        )
        return False
    delta = abs((ts - _now_utc()).total_seconds())
    if delta > _TIMESTAMP_WINDOW:
        logger.warning(
            "回调 create_time 超出 %ss 防重放窗 (delta=%.0fs), 拒绝: %s",
            _TIMESTAMP_WINDOW, delta, create_time,
        )
        return False
    return True


class _PlatformCert:
    """一张平台证书条目 (解密后的公钥 + 有效期窗口)。"""

    __slots__ = ("serial", "pubkey", "effective_at", "expire_at")

    def __init__(self, serial: str, pubkey, effective_at, expire_at) -> None:
        self.serial = serial
        self.pubkey = pubkey
        self.effective_at = effective_at
        self.expire_at = expire_at

    def is_valid_at(self, now: datetime) -> bool:
        if self.effective_at is None or self.expire_at is None:
            return False  # 有效期缺失按不可用处理 (fail-closed)
        return self.effective_at <= now <= self.expire_at

    def needs_refresh(self, now: datetime) -> bool:
        """剩余有效期 < 总有效期 1/3 → 建议刷新 (rotate 前平滑接续)。"""
        if self.effective_at is None or self.expire_at is None:
            return True
        total = (self.expire_at - self.effective_at).total_seconds()
        if total <= 0:
            return True
        remaining = (self.expire_at - now).total_seconds()
        return remaining * _CERT_REFRESH_FRACTION < total


class _PlatformCertStore:
    """平台证书缓存 + 下载单飞 (卡 7f5b4d4f A2 / 071194e4 A3 锁外下载)。

    线程模型 (A3 改造, A2 的 WARNING 遗留): A2 全程持 _lock 下载 → 并发
    验签串行阻塞 (下载 10s 超时 × N 并发 = 串行长尾)。改为:
    1. _lock (缓存锁) 内查缓存 → 命中且可用直接返回 (零下载)
    2. 未命中/需刷新 → _download_lock (下载锁) 外层判断 → 锁内单飞下载
       (下载本身在两把锁外执行, 不阻塞缓存读)
    3. 下载完成锁内双检回填 (等待者复用首批结果, 不重复下载)
    下载失败回退缓存; 无可用证书 fail-closed (None) — A2 不变量全部保持。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()          # 缓存状态锁 (轻临界区)
        self._download_lock = threading.Lock()  # 下载单飞锁 (谁持锁谁下载)
        self.certs: dict = {}  # serial(str) → _PlatformCert
        self._have_downloaded = False

    def get_for_serial(self, serial: str, refresh_fn) -> Optional[_PlatformCert]:
        """按 Wechatpay-Serial 取可用证书; 未命中/需刷新时经 refresh_fn 下载。

        refresh_fn: () → list[_PlatformCert] (下载+解密, 抛异常表示失败)。
        下载失败回退已缓存证书 (可用性优先); 无可用证书 → None (fail-closed)。
        """
        now = _now_utc()
        # 快路径: 锁内查缓存, 命中且可用即返回 (不发请求, 不碰下载锁)
        with self._lock:
            cached = self.certs.get(serial)
            if (
                cached is not None
                and cached.is_valid_at(now)
                and self._have_downloaded
                and not cached.needs_refresh(now)
            ):
                return cached
        # 慢路径: 需下载/刷新。抢下载权 (单飞): 先到者下载, 后到者等结果。
        if self._download_lock.acquire():
            # 双检: 排队期间可能已被前一个下载者满足 (缓存已可用)
            with self._lock:
                cached = self.certs.get(serial)
                if (
                    cached is not None
                    and cached.is_valid_at(now)
                    and self._have_downloaded
                    and not cached.needs_refresh(now)
                ):
                    self._download_lock.release()
                    return cached
            try:
                try:
                    certs = refresh_fn()  # 网络在锁外: 不阻塞其他 serial 验签
                except Exception as exc:
                    logger.error(
                        "平台证书下载失败, 回退缓存 serial=%s: %s", serial, exc
                    )
                else:
                    with self._lock:
                        self.certs = {c.serial: c for c in certs}
                        self._have_downloaded = True
            finally:
                self._download_lock.release()
        else:
            # 单飞等待者: 有人在下载 → 等其完成 (下载锁释放), 复用结果。
            with self._download_lock:
                pass
        with self._lock:
            cert = self.certs.get(serial)
            if cert is not None and cert.is_valid_at(now):
                return cert
            return None



class RealWxPayClient(WxPayClient):
    """IM-B支付 v3 真实客户端 (服务商模式)。

    transport: 注入式 HTTP 客户端 (需提供 post/get, 签名后的请求原样发出);
               None → 懒构造 httpx.Client。
    platform_verifier: 可注入 (body, signature_b64, serial) → bool 的验签函数,
               覆盖默认平台证书验签 (测试用假密钥对)。
    """

    def __init__(self, settings, transport=None, platform_verifier=None) -> None:
        self.settings = settings
        self._transport = transport
        self._platform_verifier = platform_verifier
        # 平台证书缓存/下载单飞 (卡 7f5b4d4f A2)
        self._platform_certs = _PlatformCertStore()
        # 查单 sub_mchid 提示 (服务商查单接口必传): 骨架阶段用 sp_mchid 自身占位,
        # A2 与 applyment service 集成后由调用方按订单解析传入。
        self._sub_mchid_hint = getattr(settings, "WX_PAY_SP_MCHID", "")
        self._private_key = self._load_private_key(settings)
        self._validate_credentials(settings)

    # ─────────────────────────── 凭证 ───────────────────────────

    @staticmethod
    def _load_private_key(settings):
        path = getattr(settings, "WX_PAY_PRIVATE_KEY_PATH", None)
        if not path:
            return None
        try:
            pem = Path(path).read_bytes()
            return serialization.load_pem_private_key(pem, password=None)
        except Exception as exc:
            raise WxPayError(f"IM-B支付商户私钥加载失败: {path}") from exc

    @staticmethod
    def _validate_credentials(settings) -> None:
        """real 模式凭证齐备校验: 任一必需项缺失 → WxPayError (fail-loud)。"""
        required = {
            "WX_PAY_SP_MCHID": getattr(settings, "WX_PAY_SP_MCHID", None),
            "WX_PAY_PRIVATE_KEY_PATH": getattr(settings, "WX_PAY_PRIVATE_KEY_PATH", None),
            "WX_PAY_CERT_SERIAL": getattr(settings, "WX_PAY_CERT_SERIAL", None),
            "WX_PAY_APIV3_KEY": getattr(settings, "WX_PAY_APIV3_KEY", None),
            "WX_PAY_APPID_MINIPROGRAM": getattr(settings, "WX_PAY_APPID_MINIPROGRAM", None),
            "WX_PAY_APPID_APP": getattr(settings, "WX_PAY_APPID_APP", None),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise WxPayError(
                f"WX_PAY_MODE=real 但支付凭证缺失: {', '.join(missing)} (拒绝静默回退 mock)"
            )

    # ───────────────────────── 签名 / 验签 ─────────────────────────

    def _sign(self, message: str) -> str:
        """商户 API 私钥 SHA256withRSA 签名, base64 输出 (请求签名 / paySign 同源)。"""
        if self._private_key is None:
            raise WxPayError("商户私钥未加载, 无法签名")
        signature = self._private_key.sign(
            message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
        )
        return base64.b64encode(signature).decode("ascii")

    def _verify_platform(self, body: bytes, signature_b64: str, serial: str) -> bool:
        """平台证书验签 (回调请求来源校验)。fail-closed: 不可验即拒。

        优先级: platform_verifier 注入 > _platform_pubkey 注入 > 自动下载链
        (卡 7f5b4d4f A2: GET /v3/certificates → AES-GCM 解密 → 按 serial 选证书)。
        """
        if self._platform_verifier is not None:
            try:
                return bool(self._platform_verifier(body, signature_b64, serial))
            except Exception:
                logger.exception("平台证书验签器异常 serial=%s", serial)
                return False
        pubkey = getattr(self, "_platform_pubkey", None)
        if pubkey is not None:
            return self._verify_with_key(pubkey, body, signature_b64)
        cert = self._platform_certs.get_for_serial(
            serial, self._download_platform_certs
        )
        if cert is None:
            # 无可用平台证书 → fail-closed (不放宽验签, 伪造回调风险 > 可用性)
            logger.error("无可用平台证书, 回调验签 fail-closed serial=%s", serial)
            return False
        return self._verify_with_key(cert.pubkey, body, signature_b64)

    @staticmethod
    def _verify_with_key(pubkey, body: bytes, signature_b64: str) -> bool:
        try:
            pubkey.verify(
                base64.b64decode(signature_b64),
                body,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False

    # ─────────────── 平台证书下载/轮换 (卡 7f5b4d4f A2) ───────────────

    def _download_platform_certs(self) -> list:
        """GET /v3/certificates → 解密证书密文 → 有效期过滤后的证书列表。

        仅返回当前时刻有效的证书 (effective_time ≤ now ≤ expire_time);
        过期/未生效/解密失败的条目跳过。供 _PlatformCertStore 单飞调用。
        """
        data = self._request("GET", "/v3/certificates")
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise WxPayError("平台证书响应结构异常 (缺 data 数组)")
        now = _now_utc()
        certs = []
        for item in items:
            cert = self._parse_platform_cert_item(item)
            if cert is None:
                continue
            if not cert.is_valid_at(now):
                continue
            certs.append(cert)
        return certs

    def _parse_platform_cert_item(self, item) -> Optional[_PlatformCert]:
        """单条证书项 → _PlatformCert; 解密/解析/加载失败 → None (跳过)。"""
        try:
            enc = item["encrypt_certificate"]
            resource = {
                "nonce": enc["nonce"],
                "associated_data": enc.get("associated_data") or "",
                "ciphertext": enc["ciphertext"],
            }
            pem_bytes = self._decrypt_resource_bytes(resource)
            if pem_bytes is None:
                return None
            cert = x509.load_pem_x509_certificate(pem_bytes)
            effective_at = _parse_wx_time(item.get("effective_time"))
            expire_at = _parse_wx_time(item.get("expire_time"))
            serial = str(item.get("serial_no") or "")
            if not serial:
                return None
            return _PlatformCert(
                serial=serial,
                pubkey=cert.public_key(),
                effective_at=effective_at,
                expire_at=expire_at,
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.error("平台证书条目解析失败, 跳过: %s", exc)
            return None

    def _decrypt_resource_bytes(self, resource: dict) -> Optional[bytes]:
        """AES-256-GCM 解密 (APIv3 key), 返回明文字节; 失败 → None。

        与 _decrypt_resource (JSON 场景) 同算法, 证书密文解出 PEM 字节。
        """
        try:
            key = bytes.fromhex(self.settings.WX_PAY_APIV3_KEY)
            nonce = resource["nonce"].encode("utf-8")
            aad = (resource.get("associated_data") or "").encode("utf-8")
            ct = base64.b64decode(resource["ciphertext"])
            return AESGCM(key).decrypt(nonce, ct, aad)
        except (InvalidTag, KeyError, ValueError, TypeError):
            logger.exception("AES-GCM 解密失败")
            return None

    # ───────────────────────── AES-GCM 解密 ─────────────────────────

    def _decrypt_resource(self, resource: dict) -> Optional[dict]:
        """回调 resource AES-256-GCM 解密 (APIv3 key)。失败 → None。"""
        try:
            key = bytes.fromhex(self.settings.WX_PAY_APIV3_KEY)
            nonce = resource["nonce"].encode("utf-8")
            aad = (resource.get("associated_data") or "").encode("utf-8")
            ct = base64.b64decode(resource["ciphertext"])
            plaintext = AESGCM(key).decrypt(nonce, ct, aad)
            return json.loads(plaintext.decode("utf-8"))
        except (InvalidTag, KeyError, ValueError, TypeError, json.JSONDecodeError):
            logger.exception("回调 resource 解密失败")
            return None

    # ───────────────────────── HTTP 层 ─────────────────────────

    def _http(self):
        """懒构造 httpx.Client (构造期零网络副作用)。"""
        if self._transport is None:
            import httpx

            self._transport = httpx.Client(timeout=_TIMEOUT_SECONDS)
        return self._transport

    def _auth_header(self, method: str, url_path: str, body: str = "") -> str:
        """v3 请求签名 Authorization 头 (Authorization: WECHATPAY2-SHA256-RSA2048 ...)。"""
        ts = str(int(_now_utc().timestamp()))
        nonce = secrets.token_hex(16)
        message = f"{method}\n{url_path}\n{ts}\n{nonce}\n{body}\n"
        sig = self._sign(message)
        mchid = self.settings.WX_PAY_SP_MCHID
        serial = self.settings.WX_PAY_CERT_SERIAL
        return (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{mchid}",'
            f'nonce_str="{nonce}",signature="{sig}",timestamp="{ts}",'
            f'serial_no="{serial}"'
        )

    def _request(self, method: str, url_path: str, payload: Optional[dict] = None) -> dict:
        """发签名请求 → 解析 JSON。网络/非 2xx/解析失败统一 WxPayError。"""
        body = json.dumps(payload, ensure_ascii=False) if payload is not None else ""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": self._auth_header(method, url_path, body),
        }
        url = f"{_API_BASE}{url_path}"
        try:
            http = self._http()
            if method == "GET":
                resp = http.get(url, headers=headers, timeout=_TIMEOUT_SECONDS)
            else:
                resp = http.post(url, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS)
        except WxPayError:
            raise
        except Exception as exc:
            raise WxPayError(f"IM-B支付接口请求失败 {url_path}: {exc}") from exc
        try:
            data = resp.json()
        except Exception as exc:
            raise WxPayError(f"IM-B支付响应解析失败 {url_path}") from exc
        if resp.status_code >= 400:
            code = data.get("code", "UNKNOWN")
            message = data.get("message", "")
            raise WxPayError(f"IM-B支付接口错误 {url_path}: {code} {message}")
        return data

    # ─────────────────────── WxPayClient 抽象实现 ───────────────────────

    def unified_order(
        self,
        *,
        out_trade_no: str,
        sub_mchid: str,
        amount_fen: int,
        description: str,
        openid: str,
        scene: str,
    ) -> PrepayResult:
        """服务商统一下单。scene=miniprogram → jsapi 端点 / app → app 端点。"""
        if scene == "app":
            endpoint = "/v3/transactions/app"
            appid = self.settings.WX_PAY_APPID_APP
            payer_key = "sp_openid"  # app 场景同为 sp appid 下 openid
        else:
            endpoint = "/v3/transactions/jsapi"
            appid = self.settings.WX_PAY_APPID_MINIPROGRAM
            payer_key = "sp_openid"
        payload = {
            "sp_appid": appid,
            "sp_mchid": self.settings.WX_PAY_SP_MCHID,
            "sub_mchid": sub_mchid,
            "description": description,
            "out_trade_no": out_trade_no,
            "notify_url": self.settings.WX_PAY_NOTIFY_URL,
            "amount": {"total": amount_fen, "currency": "CNY"},
            "payer": {payer_key: openid},
        }
        data = self._request("POST", endpoint, payload)
        prepay_id = data.get("prepay_id")
        if not prepay_id:
            raise WxPayError(f"统一下单响应缺 prepay_id: {data.get('code')} {data.get('message')}")
        # paySign: 商户私钥对 appId\ntimeStamp\nnonceStr\npackage\n 签名 (端侧五字段之一)
        time_stamp = str(int(_now_utc().timestamp()))
        nonce_str = secrets.token_hex(16).upper()
        package = f"prepay_id={prepay_id}"
        pay_sign = self._sign(f"{appid}\n{time_stamp}\n{nonce_str}\n{package}\n")
        return PrepayResult(
            prepay_id=prepay_id,
            time_stamp=time_stamp,
            nonce_str=nonce_str,
            package=package,
            sign_type="RSA",
            pay_sign=pay_sign,
        )

    def verify_and_decrypt_notify(
        self, raw_body: bytes, headers: dict
    ) -> Optional[NotifyResult]:
        """回调验签 + 解密。验签失败 / 解密失败 / 缺必需字段 → None。"""
        signature = headers.get("Wechatpay-Signature") or headers.get(
            "im_bpay-signature"
        )
        serial = headers.get("Wechatpay-Serial") or headers.get("im_bpay-serial")
        if not signature or not serial:
            logger.error("回调缺验签头 (Wechatpay-Signature/Serial), 拒绝处理")
            return None
        if not self._verify_platform(raw_body, signature, serial):
            logger.error("回调平台验签失败 serial=%s", serial)
            return None
        try:
            envelope = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        # 防重放窗 (卡 071194e4 A3): 验签后、解密前校验 envelope.create_time。
        # 时序在验签之后: 伪造报文先被签名闸拦, 不产生时间窗日志噪音。
        if not _notify_time_in_window(envelope):
            return None
        resource = envelope.get("resource") if isinstance(envelope, dict) else None
        if not isinstance(resource, dict):
            return None
        data = self._decrypt_resource(resource)
        if not isinstance(data, dict):
            return None
        out_trade_no = data.get("out_trade_no")
        tx_id = data.get("transaction_id")
        trade_state = data.get("trade_state")
        if not out_trade_no or not tx_id or not trade_state:
            return None
        amount = data.get("amount") or {}
        amount_fen = int(amount.get("total", 0)) if isinstance(amount, dict) else 0
        paid_at = None
        success_time = data.get("success_time")
        if str(trade_state).upper() == "SUCCESS" and success_time:
            try:
                # IM-B RFC3339 (+08:00) → 统一 UTC 落库
                paid_at = (
                    datetime.fromisoformat(str(success_time).replace("Z", "+00:00"))
                    .astimezone(timezone.utc)
                )
            except ValueError:
                paid_at = None
        if paid_at is None and str(trade_state).upper() == "SUCCESS":
            paid_at = _now_utc()
        return NotifyResult(
            out_trade_no=out_trade_no,
            wx_transaction_id=tx_id,
            trade_state=str(trade_state).upper(),
            amount_fen=amount_fen,
            paid_at=paid_at,
            appid=data.get("sp_appid"),
            sub_mchid=data.get("sub_mchid"),
        )

    def query_order(self, out_trade_no: str, sub_mchid: Optional[str] = None) -> OrderQueryResult:
        """查单 (对账 / 主动轮询)。sp_mchid + sub_mchid 查服务商侧单。

        sub_mchid (卡 7f5b4d4f A2 参数化): 服务商查单接口必传, 调用方按订单
        解析传入; 缺省回退 _sub_mchid_hint (sp_mchid 占位, A1 兼容行为)。
        """
        from urllib.parse import quote

        sub = sub_mchid or self._sub_mchid_hint
        path = (
            f"/v3/transactions/out-trade-no/{quote(out_trade_no, safe='')}"
            f"?sp_mchid={self.settings.WX_PAY_SP_MCHID}"
            f"&sub_mchid={sub}"
        )
        data = self._request("GET", path)
        trade_state = str(data.get("trade_state", "")).upper()
        paid_at = None
        if trade_state == "SUCCESS" and data.get("success_time"):
            try:
                paid_at = (
                    datetime.fromisoformat(str(data["success_time"]).replace("Z", "+00:00"))
                    .astimezone(timezone.utc)
                )
            except ValueError:
                paid_at = None
        return OrderQueryResult(
            out_trade_no=out_trade_no,
            wx_transaction_id=data.get("transaction_id"),
            trade_state=trade_state,
            paid_at=paid_at,
        )

    def refund(
        self,
        *,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount_fen: int,
        reason: str,
    ) -> RefundResult:
        """服务商退款。out_refund_no 幂等键 (同号重复请求返回同一退款)。"""
        payload = {
            "out_trade_no": out_trade_no,
            "out_refund_no": out_refund_no,
            "reason": reason,
            "amount": {"refund": refund_amount_fen, "currency": "CNY", "total": refund_amount_fen},
            "notify_url": self.settings.WX_PAY_NOTIFY_URL,
        }
        data = self._request("POST", "/v3/refund/domestic/refunds", payload)
        refund_id = data.get("refund_id")
        if not refund_id:
            raise WxPayError(f"退款响应缺 refund_id: {data.get('code')} {data.get('message')}")
        amount = data.get("amount") or {}
        return RefundResult(
            out_refund_no=out_refund_no,
            refund_id=refund_id,
            status=str(data.get("status", "")).upper(),
            refund_amount_fen=int(amount.get("refund", refund_amount_fen)),
        )

    def generate_sub_mchid(self, applyment_id: Optional[int] = None) -> str:
        """进件查询取 sub_mchid (applyment4sub)。

        applyment_id (卡 7f5b4d4f A2 参数化): 调用方持IM-B侧进件单号时按号
        查询 GET /v3/applyment4sub/applyment_id/{id}; 缺省查全局最近一次
        (/latest, A1 兼容行为)。

        TODO(7f5b4d4f 集成缝): applyment service 的 Merchant 模型当前无IM-B侧
        applyment_id 列 (仅自产 business_code), advance 流程无号可传仍走
        /latest。加列属 schema 变更拍板项 —— 丁哥确认后此处由调用方传
        merchant.wx_applyment_id 即可, 接口已就位无需再改本方法。
        """
        target = applyment_id if applyment_id is not None else "latest"
        data = self._request("GET", f"/v3/applyment4sub/applyment_id/{target}")
        sub = data.get("sub_mchid")
        if not sub:
            raise WxPayError(
                f"进件查询无 sub_mchid (state={data.get('applyment_state')})"
            )
        return sub
