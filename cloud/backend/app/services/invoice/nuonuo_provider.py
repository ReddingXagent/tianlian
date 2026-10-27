"""
诺诺 (nuonuo) 开票平台适配器。

能力:
- OAuth access_token 换取与自动刷新: token_cache_json 缓存, 过期前 5 分钟提前刷新。
- RSA-SHA256 签名: 业务报文 biz_content 用配置的 RSA 私钥 (private_key_enc 解密后) 签名。
- 开票请求组装 (issue_invoice) / 查询 (query_invoice) / 作废红冲 (void_invoice)。
- 异步结果回调入口 (handle_callback): 平台开票完成后推送, 归一化为 IssueResult。

测试要点: http_client 与 clock 注入, 私钥经 crypto_utils 加密后解密签名往返。
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.core.crypto_utils import decrypt_field
from app.services.invoice.provider_base import (
    InvoiceProvider,
    IssueResult,
    QueryResult,
    VoidResult,
)

# token 提前刷新窗口: 过期前 5 分钟即视为需刷新, 留网络往返余量。
_TOKEN_REFRESH_LEAD = timedelta(minutes=5)
# 默认 token 有效期 (秒), 平台未返回 expires_in 时兜底。
_DEFAULT_EXPIRES_IN = 7200


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class NuonuoProvider(InvoiceProvider):
    """诺诺开票适配器。"""

    def __init__(
        self,
        config: Any,
        http_client: Any = None,
        clock: Callable[[], datetime] = None,
    ) -> None:
        super().__init__(config, http_client=http_client, clock=clock)
        # 懒初始化 httpx.Client: 避免模块导入期副作用, 且未配置时也不报错。
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=10.0)
        self._clock_fn = clock or _now_utc

    # ─────────────── token 缓存 ───────────────

    def _load_cache(self) -> Optional[dict]:
        raw = getattr(self.config, "token_cache_json", None)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    def _save_cache(self, access_token: str, expires_at: datetime, obtained_at: datetime) -> None:
        cache = {
            "access_token": access_token,
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
            "obtained_at": obtained_at.astimezone(timezone.utc).isoformat(),
        }
        # 写回 config (ORM 实例属性); 由调用方 (service 层) 负责持久化 commit。
        self.config.token_cache_json = json.dumps(cache, ensure_ascii=False)

    def _cached_token_valid(self, cache: dict, now: datetime) -> bool:
        """缓存 token 仍有效: 未过期且超出提前刷新窗口。"""
        if not cache or not cache.get("access_token") or not cache.get("expires_at"):
            return False
        try:
            expires_at = datetime.fromisoformat(cache["expires_at"])
        except ValueError:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > now + _TOKEN_REFRESH_LEAD

    def refresh_token(self, force: bool = False) -> str:
        """返回有效 access_token。命中缓存且未临近过期则直接返回, 否则换取新 token 并写缓存。"""
        cache = self._load_cache()
        now = self._clock_fn()
        if not force and self._cached_token_valid(cache, now):
            return cache["access_token"]

        token_data = self._request_token()
        access_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", _DEFAULT_EXPIRES_IN))
        expires_at = now + timedelta(seconds=expires_in)
        self._save_cache(access_token, expires_at=expires_at, obtained_at=now)
        return access_token

    def _request_token(self) -> dict:
        """向 access_token_url 换取 token (client_credentials)。"""
        url = getattr(self.config, "access_token_url", None)
        if not url:
            raise ValueError("未配置 access_token_url, 无法换取 token")
        body = {
            "grant_type": "client_credentials",
            "client_id": getattr(self.config, "app_key", None),
            "client_secret": getattr(self.config, "app_secret", None),
        }
        resp = self._http.post(
            url, json=body, headers={"Content-Type": "application/json"}
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or "access_token" not in data:
            raise RuntimeError(f"换取 token 失败, 平台响应无 access_token: {data}")
        return data

    # ─────────────── RSA-SHA256 签名 ───────────────

    def sign(self, data: str) -> str:
        """用配置的 RSA 私钥对 data 做 PKCS1v15 + SHA256 签名, 返回 base64。"""
        enc = getattr(self.config, "private_key_enc", None)
        if not enc:
            raise ValueError("未配置 RSA 私钥 (private_key_enc), 无法签名")
        pem = decrypt_field(enc)
        if not pem:
            raise ValueError("RSA 私钥解密为空, 无法签名")
        private_key = serialization.load_pem_private_key(
            pem.encode("utf-8"), password=None
        )
        signature = private_key.sign(
            data.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
        )
        return base64.b64encode(signature).decode("ascii")

    # ─────────────── 开票请求组装 ───────────────

    def _build_headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def _issue_body(self, payload: dict, token: str) -> dict:
        """组装诺诺开票请求体: biz_content (业务报文) + RSA 签名 + 鉴权。"""
        biz_content = json.dumps(payload, ensure_ascii=False)
        return {
            "app_key": getattr(self.config, "app_key", None),
            "token": token,
            "timestamp": self._clock_fn().strftime("%Y-%m-%d %H:%M:%S"),
            "biz_content": biz_content,
            "sign": self.sign(biz_content),
        }

    def issue_invoice(self, payload: dict) -> IssueResult:
        url = getattr(self.config, "api_url", None)
        if not url:
            raise ValueError("未配置 api_url, 无法发起开票")
        token = self.refresh_token()
        body = self._issue_body(payload, token)
        resp = self._http.post(url, json=body, headers=self._build_headers())
        resp.raise_for_status()
        data = resp.json()
        return self._parse_issue_response(data)

    def _parse_issue_response(self, data: dict) -> IssueResult:
        """归一化诺诺开票响应。code/status 判定受理状态。"""
        code = str(data.get("code", data.get("status", "")))
        if code in ("0", "0000", "200", "success"):
            status = "success"
        elif code in ("E0001", "pending", "processing"):
            status = "pending"  # 异步受理, 等回调
        else:
            status = "failed"
        return IssueResult(
            status=status,
            request_id=data.get("requestId") or data.get("fpqqlsh"),
            invoice_no=data.get("invoiceNo") or data.get("fphm"),
            invoice_url=data.get("pdfUrl"),
            message=data.get("describe") or data.get("message"),
            raw=data,
        )

    # ─────────────── 查询 / 作废 ───────────────

    def query_invoice(
        self,
        request_id: Optional[str] = None,
        invoice_no: Optional[str] = None,
    ) -> QueryResult:
        url = getattr(self.config, "api_url", None)
        if not url:
            raise ValueError("未配置 api_url, 无法查询发票")
        if not request_id and not invoice_no:
            raise ValueError("查询发票需提供 request_id 或 invoice_no")
        token = self.refresh_token()
        biz = {"requestId": request_id, "invoiceNo": invoice_no}
        biz_content = json.dumps(biz, ensure_ascii=False)
        body = {
            "app_key": getattr(self.config, "app_key", None),
            "token": token,
            "biz_content": biz_content,
            "sign": self.sign(biz_content),
        }
        resp = self._http.post(url, json=body, headers=self._build_headers())
        resp.raise_for_status()
        data = resp.json()
        code = str(data.get("code", data.get("status", "")))
        status = "success" if code in ("0", "0000", "200", "success") else "failed"
        return QueryResult(
            status=status,
            invoice_no=data.get("invoiceNo") or data.get("fphm"),
            invoice_url=data.get("pdfUrl"),
            message=data.get("describe") or data.get("message"),
            raw=data,
        )

    def void_invoice(self, invoice_no: str, reason: Optional[str] = None) -> VoidResult:
        url = getattr(self.config, "api_url", None)
        if not url:
            raise ValueError("未配置 api_url, 无法作废发票")
        token = self.refresh_token()
        biz = {"invoiceNo": invoice_no, "reason": reason}
        biz_content = json.dumps(biz, ensure_ascii=False)
        body = {
            "app_key": getattr(self.config, "app_key", None),
            "token": token,
            "biz_content": biz_content,
            "sign": self.sign(biz_content),
        }
        resp = self._http.post(url, json=body, headers=self._build_headers())
        resp.raise_for_status()
        data = resp.json()
        code = str(data.get("code", data.get("status", "")))
        status = "success" if code in ("0", "0000", "200", "success") else "failed"
        return VoidResult(
            status=status,
            message=data.get("describe") or data.get("message"),
            raw=data,
        )

    # ─────────────── 异步回调入口 ───────────────

    def handle_callback(self, payload: dict) -> IssueResult:
        """平台开票完成后的异步推送回调入口, 归一化为 IssueResult。"""
        status_raw = str(payload.get("status", payload.get("kpzt", "")))
        if status_raw in ("0", "0000", "success", "Success"):
            status = "success"
        elif status_raw in ("1", "failed", "Failed"):
            status = "failed"
        else:
            status = "pending"
        return IssueResult(
            status=status,
            request_id=payload.get("requestId") or payload.get("fpqqlsh"),
            invoice_no=payload.get("invoiceNo") or payload.get("fphm"),
            invoice_url=payload.get("pdfUrl"),
            message=payload.get("describe") or payload.get("message"),
            raw=payload,
        )
