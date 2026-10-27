"""
诺诺 (nuonuo) 开票适配器单元测试。

覆盖:
- token 缓存: 首次换取 / 命中缓存免请求 / 过期前 5min 提前刷新 / force 强刷 /
  expires_in 缺失兜底 7200
- token 换取异常: 未配置 url / 响应无 access_token
- RSA-SHA256 签名: 固定 RSA 私钥 (加密存储) 签名后用公钥验签; 未配置私钥报错
- 开票请求组装: biz_content + sign + token, 响应归一化 (success/pending/failed)
- 查询 / 作废 / 异步回调入口
"""
import base64
import json
import types
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.fernet import Fernet

from app.core import crypto_utils
from app.core.crypto_utils import encrypt_field
from app.services.invoice.nuonuo_provider import NuonuoProvider


NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
TOKEN_URL = "https://api.nuonuo.com/oauth2/token"
API_URL = "https://api.nuonuo.com/openapi/invoice"


# ─────────────── 测试替身 ───────────────


class _Resp:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class _FakeHttp:
    """按 URL 分派响应的 HTTP 替身, 记录所有调用。"""

    def __init__(self):
        self.calls = []
        self._handlers = {}

    def register(self, url, resp):
        self._handlers[url] = resp
        return self

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if url not in self._handlers:
            return _Resp({})
        return self._handlers[url]


def _cfg(**kw):
    base = types.SimpleNamespace(
        app_key="ak001",
        app_secret="sk001",
        api_url=API_URL,
        access_token_url=TOKEN_URL,
        private_key_enc=None,
        token_cache_json=None,
        device_no="D001",
        callback_url=None,
        ext_config_json=None,
    )
    for k, v in kw.items():
        setattr(base, k, v)
    return base


@pytest.fixture
def fixed_crypto(monkeypatch):
    """固定 Fernet 密钥, 使 private_key_enc 加解密确定且与 SECRET_KEY 解耦。"""
    f = Fernet(Fernet.generate_key())
    monkeypatch.setattr(crypto_utils, "_get_fernet", lambda: f)
    return f


@pytest.fixture
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return pem, private_key.public_key()


def _token_resp(access_token="T1", expires_in=7200):
    return _Resp({"access_token": access_token, "expires_in": expires_in, "token_type": "bearer"})


# ─────────────── token 缓存逻辑 ───────────────


class TestTokenRefresh:
    def test_first_call_requests_and_caches(self, fixed_crypto):
        http = _FakeHttp().register(TOKEN_URL, _token_resp("T1", 7200))
        cfg = _cfg()
        p = NuonuoProvider(cfg, http_client=http, clock=lambda: NOW)

        assert p.refresh_token() == "T1"
        assert len(http.calls) == 1 and http.calls[0]["url"] == TOKEN_URL

        cache = json.loads(cfg.token_cache_json)
        assert cache["access_token"] == "T1"
        assert cache["obtained_at"] == NOW.isoformat()
        # expires_at = NOW + 7200s
        assert cache["expires_at"] == (NOW + timedelta(seconds=7200)).isoformat()

    def test_cache_hit_skips_http(self, fixed_crypto):
        http = _FakeHttp()
        cfg = _cfg(token_cache_json=json.dumps({
            "access_token": "CACHED",
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),  # 远未过期
            "obtained_at": NOW.isoformat(),
        }))
        p = NuonuoProvider(cfg, http_client=http, clock=lambda: NOW)

        assert p.refresh_token() == "CACHED"
        assert http.calls == []  # 未发起任何请求

    def test_refreshes_within_5min_lead_window(self, fixed_crypto):
        """过期前 5 分钟内即视为需刷新 (留网络往返余量)。"""
        http = _FakeHttp().register(TOKEN_URL, _token_resp("T2", 7200))
        cfg = _cfg(token_cache_json=json.dumps({
            "access_token": "OLD",
            "expires_at": (NOW + timedelta(minutes=3)).isoformat(),  # 距过期 3min < 5min
            "obtained_at": (NOW - timedelta(hours=2)).isoformat(),
        }))
        p = NuonuoProvider(cfg, http_client=http, clock=lambda: NOW)

        assert p.refresh_token() == "T2"
        assert len(http.calls) == 1  # 触发了刷新

    def test_force_refresh_ignores_valid_cache(self, fixed_crypto):
        http = _FakeHttp().register(TOKEN_URL, _token_resp("NEW", 7200))
        cfg = _cfg(token_cache_json=json.dumps({
            "access_token": "OLD",
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
            "obtained_at": NOW.isoformat(),
        }))
        p = NuonuoProvider(cfg, http_client=http, clock=lambda: NOW)

        assert p.refresh_token(force=True) == "NEW"
        assert len(http.calls) == 1

    def test_default_expires_in_when_missing(self, fixed_crypto):
        """平台未返回 expires_in 时兜底 7200s。"""
        http = _FakeHttp().register(TOKEN_URL, _Resp({"access_token": "T", "token_type": "bearer"}))
        cfg = _cfg()
        p = NuonuoProvider(cfg, http_client=http, clock=lambda: NOW)
        p.refresh_token()

        cache = json.loads(cfg.token_cache_json)
        assert cache["expires_at"] == (NOW + timedelta(seconds=7200)).isoformat()

    def test_corrupt_cache_cache_triggers_refresh(self, fixed_crypto):
        http = _FakeHttp().register(TOKEN_URL, _token_resp("OK", 7200))
        cfg = _cfg(token_cache_json="{not valid json")
        p = NuonuoProvider(cfg, http_client=http, clock=lambda: NOW)
        assert p.refresh_token() == "OK"


class TestTokenRequestErrors:
    def test_missing_access_token_url_raises(self, fixed_crypto):
        p = NuonuoProvider(_cfg(access_token_url=None), http_client=_FakeHttp(), clock=lambda: NOW)
        with pytest.raises(ValueError, match="access_token_url"):
            p.refresh_token()

    def test_response_without_access_token_raises(self, fixed_crypto):
        http = _FakeHttp().register(TOKEN_URL, _Resp({"error": "invalid_client"}))
        p = NuonuoProvider(_cfg(), http_client=http, clock=lambda: NOW)
        with pytest.raises(RuntimeError, match="access_token"):
            p.refresh_token()


# ─────────────── RSA-SHA256 签名 ───────────────


class TestSignature:
    def test_sign_verifies_with_public_key(self, fixed_crypto, rsa_keypair):
        pem, public_key = rsa_keypair
        cfg = _cfg(private_key_enc=encrypt_field(pem))
        p = NuonuoProvider(cfg, http_client=_FakeHttp(), clock=lambda: NOW)

        signature_b64 = p.sign("hello-nuonuo")
        # 用对应公钥验签 (PKCS1v15 + SHA256)
        public_key.verify(
            base64.b64decode(signature_b64),
            b"hello-nuonuo",
            padding.PKCS1v15(),
            hashes.SHA256(),
        )  # 无异常即通过

    def test_sign_without_private_key_raises(self, fixed_crypto):
        p = NuonuoProvider(_cfg(), http_client=_FakeHttp(), clock=lambda: NOW)
        with pytest.raises(ValueError, match="私钥"):
            p.sign("x")

    def test_sign_tampered_data_fails_verify(self, fixed_crypto, rsa_keypair):
        pem, public_key = rsa_keypair
        cfg = _cfg(private_key_enc=encrypt_field(pem))
        p = NuonuoProvider(cfg, http_client=_FakeHttp(), clock=lambda: NOW)

        sig = base64.b64decode(p.sign("original"))
        from cryptography.exceptions import InvalidSignature

        with pytest.raises(InvalidSignature):
            public_key.verify(sig, b"tampered", padding.PKCS1v15(), hashes.SHA256())


# ─────────────── 开票 / 查询 / 作废 / 回调 ───────────────


def _signed_cfg(fixed_crypto, rsa_keypair):
    pem, _ = rsa_keypair
    return _cfg(private_key_enc=encrypt_field(pem))


class TestIssueInvoice:
    def test_issue_success_parses_response(self, fixed_crypto, rsa_keypair):
        http = (
            _FakeHttp()
            .register(TOKEN_URL, _token_resp("TK"))
            .register(API_URL, _Resp({"code": "0", "fpqqlsh": "R1", "invoiceNo": "INV001", "pdfUrl": "http://pdf"}))
        )
        p = NuonuoProvider(_signed_cfg(fixed_crypto, rsa_keypair), http_client=http, clock=lambda: NOW)

        res = p.issue_invoice({"buyerName": "测试公司", "total": 100.0})
        assert res.status == "success"
        assert res.request_id == "R1"
        assert res.invoice_no == "INV001"
        assert res.invoice_url == "http://pdf"

        # 校验请求体组装: 含 token / biz_content / sign
        issue_call = next(c for c in http.calls if c["url"] == API_URL)
        body = issue_call["json"]
        assert body["token"] == "TK"
        assert body["app_key"] == "ak001"
        assert "biz_content" in body and "sign" in body
        assert json.loads(body["biz_content"])["buyerName"] == "测试公司"

    def test_issue_async_pending(self, fixed_crypto, rsa_keypair):
        http = (
            _FakeHttp()
            .register(TOKEN_URL, _token_resp("TK"))
            .register(API_URL, _Resp({"code": "E0001", "describe": "受理中"}))
        )
        p = NuonuoProvider(_signed_cfg(fixed_crypto, rsa_keypair), http_client=http, clock=lambda: NOW)
        res = p.issue_invoice({"x": 1})
        assert res.status == "pending"
        assert res.message == "受理中"

    def test_issue_failed_status(self, fixed_crypto, rsa_keypair):
        http = (
            _FakeHttp()
            .register(TOKEN_URL, _token_resp("TK"))
            .register(API_URL, _Resp({"code": "9999", "describe": "税控设备离线"}))
        )
        p = NuonuoProvider(_signed_cfg(fixed_crypto, rsa_keypair), http_client=http, clock=lambda: NOW)
        res = p.issue_invoice({"x": 1})
        assert res.status == "failed"

    def test_issue_missing_api_url_raises(self, fixed_crypto, rsa_keypair):
        cfg = _signed_cfg(fixed_crypto, rsa_keypair)
        cfg.api_url = None
        p = NuonuoProvider(cfg, http_client=_FakeHttp(), clock=lambda: NOW)
        with pytest.raises(ValueError, match="api_url"):
            p.issue_invoice({"x": 1})


class TestQueryAndVoid:
    def test_query_success(self, fixed_crypto, rsa_keypair):
        http = (
            _FakeHttp()
            .register(TOKEN_URL, _token_resp("TK"))
            .register(API_URL, _Resp({"code": "0", "invoiceNo": "Q1", "pdfUrl": "u"}))
        )
        p = NuonuoProvider(_signed_cfg(fixed_crypto, rsa_keypair), http_client=http, clock=lambda: NOW)
        res = p.query_invoice(request_id="R1")
        assert res.status == "success"
        assert res.invoice_no == "Q1"

    def test_query_requires_identifier(self, fixed_crypto, rsa_keypair):
        p = NuonuoProvider(_signed_cfg(fixed_crypto, rsa_keypair), http_client=_FakeHttp(), clock=lambda: NOW)
        with pytest.raises(ValueError, match="request_id 或 invoice_no"):
            p.query_invoice()

    def test_void_success(self, fixed_crypto, rsa_keypair):
        http = (
            _FakeHttp()
            .register(TOKEN_URL, _token_resp("TK"))
            .register(API_URL, _Resp({"code": "0", "describe": "ok"}))
        )
        p = NuonuoProvider(_signed_cfg(fixed_crypto, rsa_keypair), http_client=http, clock=lambda: NOW)
        res = p.void_invoice("INV001", reason="开错")
        assert res.status == "success"
        assert res.message == "ok"


class TestCallback:
    def test_handle_callback_success(self, fixed_crypto):
        p = NuonuoProvider(_cfg(), http_client=_FakeHttp(), clock=lambda: NOW)
        res = p.handle_callback({"status": "0", "fphm": "INV9", "pdfUrl": "http://pdf"})
        assert res.status == "success"
        assert res.invoice_no == "INV9"
        assert res.invoice_url == "http://pdf"

    def test_handle_callback_failed(self, fixed_crypto):
        p = NuonuoProvider(_cfg(), http_client=_FakeHttp(), clock=lambda: NOW)
        res = p.handle_callback({"status": "1", "describe": "开票失败"})
        assert res.status == "failed"
        assert res.message == "开票失败"

    def test_handle_callback_unknown_is_pending(self, fixed_crypto):
        p = NuonuoProvider(_cfg(), http_client=_FakeHttp(), clock=lambda: NOW)
        res = p.handle_callback({"status": "processing"})
        assert res.status == "pending"
