"""RealWxPayClient 骨架 + 工厂切换测试 (卡 6c8f930c A1, 凭证无关)

被测:
- app/services/wx_pay/real_client.py — IM-B支付 v3 真实客户端骨架 (HTTP 传输注入)
- app/services/wx_pay/client.py — get_wxpay_client 按 WX_PAY_MODE 切换

设计: 凭证 (mchid/serial/私钥/APIv3 key) 只从 settings 读; 缺失时 real 模式
fail-loud 抛 WxPayError (不静默回退 mock — mock 假 paySign 混进真实支付流比
宕掉更危险)。mock 模式不要求凭证 (现有环境零配置)。默认 mock 不变, 调用方零改动。

测试缝: transport (HTTP 替身) / signer / verifier / platform_verifier 注入。
验签单测用 cryptography 生成的假密钥对构造测试向量, 不依赖IM-B真实证书。
"""
import base64
import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.services.wx_pay import client as cli
from app.services.wx_pay.client import (
    WxPayError,
    PrepayResult,
    NotifyResult,
    OrderQueryResult,
    RefundResult,
    get_wxpay_client,
    reset_wxpay_client_for_testing,
)


# ═══════════════════════════════════════════════════════════════
# 脚手架: 假密钥对 + 凭证命名空间
# ═══════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def keypair():
    """2048 位 RSA 假密钥对 (模块级复用, 生成 ~0.1s)。"""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def _settings(**over):
    base = dict(
        WX_PAY_MODE="mock",
        WX_PAY_SP_MCHID=None,
        WX_PAY_PRIVATE_KEY_PATH=None,
        WX_PAY_CERT_SERIAL=None,
        WX_PAY_APIV3_KEY=None,
        WX_PAY_APPID_MINIPROGRAM=None,
        WX_PAY_APPID_APP=None,
        WX_PAY_NOTIFY_URL=None,
    )
    base.update(over)
    ns = SimpleNamespace(**base)
    # 透传真实 settings 的其余属性 (工厂/real_client 不读其他键时也可不透传,
    # 但保持 SimpleNamespace 最小面: 只暴露 WX_PAY_* 被测面)
    return ns


def _patch_settings(monkeypatch, ns):
    """把 ns 注入工厂模块级 settings 引用 (client.py 从 app.core.config 导入)。"""
    import app.core.config as cfg
    monkeypatch.setattr(cfg, "settings", ns)
    # client._build_client_from_settings 内部 from app.core.config import settings
    # 是函数级 import, 每次调用取 cfg.settings 属性 → patch cfg.settings 即生效。


def _full_settings(**over):
    """齐备凭证的 settings (私钥路径由用例写入 tmp 文件)。"""
    base = dict(
        WX_PAY_MODE="real",
        WX_PAY_SP_MCHID="1900000001",
        WX_PAY_CERT_SERIAL="SERIAL0001",
        WX_PAY_APIV3_KEY="0123456789abcdef0123456789abcdef",
        WX_PAY_APPID_MINIPROGRAM="wx1111111111111111",
        WX_PAY_APPID_APP="wx2222222222222222",
        WX_PAY_NOTIFY_URL="https://api.tianlian.example/v1/business/payments/notify",
    )
    base.update(over)
    return _settings(**base)





@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_wxpay_client_for_testing(None)
    yield
    reset_wxpay_client_for_testing(None)


# ═══════════════════════════════════════════════════════════════
# 工厂切换 — WX_PAY_MODE
# ═══════════════════════════════════════════════════════════════
class TestFactoryMode:
    def test_default_mode_is_mock(self, monkeypatch):
        """未配置 WX_PAY_MODE → MockWxPayClient (现状不变, 调用方零改动)。"""
        from app.services.wx_pay.mock_client import MockWxPayClient
        _patch_settings(monkeypatch, _settings(WX_PAY_MODE="mock"))
        assert isinstance(get_wxpay_client(), MockWxPayClient)

    def test_mode_mock_explicit(self, monkeypatch):
        from app.services.wx_pay.mock_client import MockWxPayClient
        _patch_settings(monkeypatch, _settings(WX_PAY_MODE="mock"))
        assert isinstance(get_wxpay_client(), MockWxPayClient)

    def test_concurrent_first_calls_init_once_real_mode(self, monkeypatch, tmp_path, keypair):
        """real 模式下双检锁仍成立: 并发首调只构造一次 RealWxPayClient。"""
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, _ = keypair
        pem = tmp_path / "k_conc.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        _patch_settings(monkeypatch, _full_settings(
            WX_PAY_PRIVATE_KEY_PATH=str(pem),
        ))
        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(get_wxpay_client())

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 8
        assert all(r is results[0] for r in results)
        assert isinstance(results[0], RealWxPayClient)

    def test_mode_real_with_credentials(self, monkeypatch, tmp_path, keypair):
        """real + 凭证齐备 → RealWxPayClient。"""
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, _ = keypair
        pem = tmp_path / "apiclient_key.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        _patch_settings(monkeypatch, _full_settings(
            WX_PAY_PRIVATE_KEY_PATH=str(pem),
        ))
        c = get_wxpay_client()
        assert isinstance(c, RealWxPayClient)

    def test_mode_real_missing_credentials_raises(self, monkeypatch):
        """real + 凭证缺失 → WxPayError (fail-loud, 不静默回退 mock)。"""
        _patch_settings(monkeypatch, _full_settings(
            WX_PAY_PRIVATE_KEY_PATH=None,
        ))
        with pytest.raises(WxPayError, match="凭证"):
            get_wxpay_client()

    def test_mode_real_partial_credentials_raises(self, monkeypatch, tmp_path, keypair):
        """real + 私钥在但 APIv3 key 缺 → 同样 WxPayError (任一必需凭证缺失即拒)。"""
        priv, _ = keypair
        pem = tmp_path / "k.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        _patch_settings(monkeypatch, _full_settings(
            WX_PAY_PRIVATE_KEY_PATH=str(pem),
            WX_PAY_APIV3_KEY=None,
        ))
        with pytest.raises(WxPayError, match="凭证"):
            get_wxpay_client()

    def test_mode_real_bad_private_key_raises(self, monkeypatch, tmp_path):
        """real + 私钥文件内容非法 → WxPayError (非裸 ValueError 冒泡)。"""
        bad = tmp_path / "bad.pem"
        bad.write_text("not a pem key")
        _patch_settings(monkeypatch, _full_settings(
            WX_PAY_PRIVATE_KEY_PATH=str(bad),
        ))
        with pytest.raises(WxPayError):
            get_wxpay_client()

    def test_singleton_preserved_in_real_mode(self, monkeypatch, tmp_path, keypair):
        """real 模式单例: 重复 get 同实例 (双检锁语义在两种模式下都保持)。"""
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, _ = keypair
        pem = tmp_path / "k2.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        _patch_settings(monkeypatch, _full_settings(
            WX_PAY_PRIVATE_KEY_PATH=str(pem),
        ))
        c1 = get_wxpay_client()
        c2 = get_wxpay_client()
        assert c1 is c2
        assert isinstance(c1, RealWxPayClient)

    def test_unknown_mode_raises(self, monkeypatch):
        """WX_PAY_MODE 非法值 → WxPayError (不猜默认)。"""
        _patch_settings(monkeypatch, _settings(WX_PAY_MODE="weird"))
        with pytest.raises(WxPayError, match="WX_PAY_MODE"):
            get_wxpay_client()


# ═══════════════════════════════════════════════════════════════
# 签名 / 验签 — RSA-SHA256 往返 (假密钥对测试向量)
# ═══════════════════════════════════════════════════════════════
class TestSignVerifyRoundtrip:
    def _client(self, keypair, monkeypatch, tmp_path, transport=None, verifier=None):
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, pub = keypair
        pem = tmp_path / "k_sv.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        settings = _full_settings(WX_PAY_PRIVATE_KEY_PATH=str(pem))
        return (
            RealWxPayClient(settings, transport=transport,
                            platform_verifier=verifier),
            priv, pub,
        )

    def test_sign_verify_roundtrip(self, monkeypatch, tmp_path, keypair):
        """私钥签名 → 平台公钥验签通过; 换另一密钥对验签失败。"""
        c, priv, pub = self._client(keypair, monkeypatch, tmp_path)
        msg = "appId\ntimeStamp\nnonceStr\npackage\n"
        sig = c._sign(msg)
        # 正确公钥验签通过
        pub.verify(base64.b64decode(sig), msg.encode(), padding.PKCS1v15(), hashes.SHA256())
        # 篡改消息 → 验签失败
        with pytest.raises(Exception):
            pub.verify(
                base64.b64decode(sig), b"tampered", padding.PKCS1v15(), hashes.SHA256()
            )

    def test_verify_platform_signature(self, monkeypatch, tmp_path, keypair):
        """外部构造的签名 (模拟IM-B平台证书私钥) → 客户端验签通过/失败两分支。"""
        platform_priv, platform_pub = rsa.generate_private_key(65537, 2048), None
        platform_pub = platform_priv.public_key()
        c, _, _ = self._client(keypair, monkeypatch, tmp_path)
        # 注入平台公钥 verifier
        c._platform_pubkey = platform_pub
        body = b'{"id":"evt1"}'
        sig = base64.b64encode(platform_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        assert c._verify_platform(body, sig, "SERIAL_X") is True
        # 错误签名 → False
        assert c._verify_platform(body, "AAAAAAAA", "SERIAL_X") is False


# ═══════════════════════════════════════════════════════════════
# AES-256-GCM 解密 (APIv3 key)
# ═══════════════════════════════════════════════════════════════
class TestAesGcmDecrypt:
    def _client(self, keypair, tmp_path):
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, _ = keypair
        pem = tmp_path / "k_aes.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        return RealWxPayClient(
            _full_settings(WX_PAY_PRIVATE_KEY_PATH=str(pem))
        )

    def test_decrypt_roundtrip(self, keypair, tmp_path):
        """用 APIv3 key 加密构造 resource → 客户端解密回原文。"""
        c = self._client(keypair, tmp_path)
        key = bytes.fromhex(c.settings.WX_PAY_APIV3_KEY)
        nonce = b"0123456789ab"
        aad = b"evt_123"
        plaintext = json.dumps({
            "out_trade_no": "TL_1", "transaction_id": "4200",
            "trade_state": "SUCCESS",
            "amount": {"total": 8200},
            "success_time": "2026-08-17T10:00:00+08:00",
        }).encode()
        ct = AESGCM(key).encrypt(nonce, plaintext, aad)
        resource = {
            "ciphertext": base64.b64encode(ct).decode(),
            "nonce": nonce.decode(),
            "associated_data": aad.decode(),
        }
        out = c._decrypt_resource(resource)
        assert out["out_trade_no"] == "TL_1"
        assert out["amount"]["total"] == 8200

    def test_decrypt_bad_ciphertext_returns_none(self, keypair, tmp_path):
        """密文损坏 → None (不抛)。"""
        c = self._client(keypair, tmp_path)
        resource = {
            "ciphertext": base64.b64encode(b"garbage").decode(),
            "nonce": "0123456789ab",
            "associated_data": "evt_1",
        }
        assert c._decrypt_resource(resource) is None


# ═══════════════════════════════════════════════════════════════
# unified_order — HTTP 传输注入
# ═══════════════════════════════════════════════════════════════
class _FakeTransport:
    """同步 httpx.Client 替身: post(url, json, headers) → MockResponse。"""

    def __init__(self, responses=None, exc=None):
        self.calls = []
        self._responses = responses or {}
        self._exc = exc

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self._exc is not None:
            raise self._exc
        for substr, spec in self._responses.items():
            if substr in url:
                r = SimpleNamespace()
                r.status_code = spec.get("status_code", 200)
                r.json = lambda payload=spec.get("payload", {}): payload
                r.raise_for_status = lambda sc=spec.get("status_code", 200): (
                    None if sc < 400 else (_ for _ in ()).raise_http_error()
                )
                return r
        r = SimpleNamespace()
        r.status_code = 200
        r.json = lambda: {}
        r.raise_for_status = lambda: None
        return r

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers})
        for substr, spec in self._responses.items():
            if substr in url:
                r = SimpleNamespace()
                r.status_code = spec.get("status_code", 200)
                r.json = lambda payload=spec.get("payload", {}): payload
                r.raise_for_status = lambda sc=spec.get("status_code", 200): (
                    None if sc < 400 else (_ for _ in ()).raise_http_error()
                )
                return r
        r = SimpleNamespace()
        r.status_code = 200
        r.json = lambda: {}
        r.raise_for_status = lambda: None
        return r


class TestUnifiedOrder:
    def test_posts_v3_transactions_and_returns_five_fields(self, keypair, tmp_path):
        """unified_order → POST /v3/transactions/jsapi (scene=miniprogram), 响应映射
        PrepayResult + paySign 用商户私钥对四行消息签名。"""
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, pub = keypair
        pem = tmp_path / "k_uo.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        tp = _FakeTransport(responses={"transactions/jsapi": {
            "status_code": 200,
            "payload": {"prepay_id": "wx21270abcdef"},
        }})
        c = RealWxPayClient(
            _full_settings(WX_PAY_PRIVATE_KEY_PATH=str(pem)), transport=tp
        )
        r = c.unified_order(
            out_trade_no="TL_20260817_aaaa", sub_mchid="2490000001",
            amount_fen=8200, description="充电订单", openid="oXYZ", scene="miniprogram",
        )
        assert isinstance(r, PrepayResult)
        assert r.prepay_id == "wx21270abcdef"
        assert r.package == "prepay_id=wx21270abcdef"
        assert r.sign_type == "RSA"
        # paySign 可被公钥验签 (四行消息: appId\nts\nnonce\npackage\n)
        msg = f"{c.settings.WX_PAY_APPID_MINIPROGRAM}\n{r.time_stamp}\n{r.nonce_str}\n{r.package}\n"
        pub.verify(base64.b64decode(r.pay_sign), msg.encode(), padding.PKCS1v15(), hashes.SHA256())
        # 请求体含服务商三要素 + 金额
        body = tp.calls[0]["json"]
        assert body["sp_mchid"] == "1900000001"
        assert body["sub_mchid"] == "2490000001"
        assert body["amount"]["total"] == 8200
        assert body["payer"]["sp_openid"] == "oXYZ"

    def test_scene_app_uses_app_appid(self, keypair, tmp_path):
        """scene=app → appid 用 WX_PAY_APPID_APP。"""
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, _ = keypair
        pem = tmp_path / "k_app.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        tp = _FakeTransport(responses={"transactions/app": {
            "payload": {"prepay_id": "wxAPP"},
        }})
        c = RealWxPayClient(
            _full_settings(WX_PAY_PRIVATE_KEY_PATH=str(pem)), transport=tp
        )
        c.unified_order(
            out_trade_no="TL_x", sub_mchid="249", amount_fen=1,
            description="d", openid="o", scene="app",
        )
        assert "transactions/app" in tp.calls[0]["url"]

    def test_http_error_wrapped_wxpayerror(self, keypair, tmp_path):
        """传输层异常 (网络) → WxPayError (service/router 兜底约定)。"""
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, _ = keypair
        pem = tmp_path / "k_err.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        c = RealWxPayClient(
            _full_settings(WX_PAY_PRIVATE_KEY_PATH=str(pem)),
            transport=_FakeTransport(exc=ConnectionError("network down")),
        )
        with pytest.raises(WxPayError):
            c.unified_order(
                out_trade_no="TL_x", sub_mchid="249", amount_fen=1,
                description="d", openid="o", scene="miniprogram",
            )

    def test_wx_biz_error_wrapped(self, keypair, tmp_path):
        """IM-B业务错误 (响应无 prepay_id) → WxPayError。"""
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, _ = keypair
        pem = tmp_path / "k_biz.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        c = RealWxPayClient(
            _full_settings(WX_PAY_PRIVATE_KEY_PATH=str(pem)),
            transport=_FakeTransport(responses={"jsapi": {"payload": {
                "code": "PARAM_ERROR", "message": "参数错误",
            }}}),
        )
        with pytest.raises(WxPayError):
            c.unified_order(
                out_trade_no="TL_x", sub_mchid="249", amount_fen=1,
                description="d", openid="o", scene="miniprogram",
            )


# ═══════════════════════════════════════════════════════════════
# verify_and_decrypt_notify — 验签 + 解密全链
# ═══════════════════════════════════════════════════════════════
class TestVerifyAndDecryptNotify:
    def _make_client(self, keypair, tmp_path, platform_priv):
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, _ = keypair
        pem = tmp_path / "k_notify.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        c = RealWxPayClient(_full_settings(WX_PAY_PRIVATE_KEY_PATH=str(pem)))
        c._platform_pubkey = platform_priv.public_key()
        return c

    def _signed_body(self, platform_priv, payload: bytes):
        sig = base64.b64encode(platform_priv.sign(
            payload, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        headers = {
            "Wechatpay-Signature": sig,
            "Wechatpay-Serial": "PLAT0001",
            "Wechatpay-Timestamp": "1786000000",
            "Wechatpay-Nonce": "nonce123",
        }
        return headers

    def test_full_chain_verifies_and_decrypts(self, keypair, tmp_path):
        """验签通过 + AES-GCM 解密 → NotifyResult 含金额/身份字段。"""
        platform_priv = rsa.generate_private_key(65537, 2048)
        c = self._make_client(keypair, tmp_path, platform_priv)
        api_key = bytes.fromhex(c.settings.WX_PAY_APIV3_KEY)
        nonce = b"0123456789ab"
        aad = b"transaction"
        plaintext = json.dumps({
            "sp_appid": "wx1111111111111111",
            "sp_mchid": "1900000001",
            "sub_mchid": "2490000001",
            "out_trade_no": "TL_notify1",
            "transaction_id": "4200NOTIFY1",
            "trade_state": "SUCCESS",
            "amount": {"total": 8200},
            "success_time": "2026-08-17T10:00:00+08:00",
        }).encode()
        ct = AESGCM(api_key).encrypt(nonce, plaintext, aad)
        # create_time 用当前时刻: 防重放窗 (卡 071194e4 A3) 校验 create_time
        # 在 now±300s 内, 写死历史时刻会被正确拒绝。
        from datetime import datetime, timedelta, timezone
        wx_now = datetime.now(timezone.utc).astimezone(
            timezone(timedelta(hours=8))
        )
        body = json.dumps({
            "id": "EV-NOTIFY-1",
            "create_time": wx_now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {
                "ciphertext": base64.b64encode(ct).decode(),
                "nonce": nonce.decode(),
                "associated_data": aad.decode(),
            },
        }).encode()
        headers = self._signed_body(platform_priv, body)
        r = c.verify_and_decrypt_notify(body, headers)
        assert isinstance(r, NotifyResult)
        assert r.out_trade_no == "TL_notify1"
        assert r.amount_fen == 8200
        assert r.trade_state == "SUCCESS"
        assert r.sub_mchid == "2490000001"
        assert r.appid == "wx1111111111111111"
        assert r.paid_at is not None

    def test_bad_signature_returns_none(self, keypair, tmp_path):
        """验签失败 (签名不匹配) → None, 不进解密。"""
        platform_priv = rsa.generate_private_key(65537, 2048)
        c = self._make_client(keypair, tmp_path, platform_priv)
        other_priv = rsa.generate_private_key(65537, 2048)
        body = b'{"event_type":"TRANSACTION.SUCCESS","resource":{}}'
        sig = base64.b64encode(other_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        r = c.verify_and_decrypt_notify(body, {
            "Wechatpay-Signature": sig, "Wechatpay-Serial": "PLAT0001",
        })
        assert r is None

    def test_missing_signature_header_returns_none(self, keypair, tmp_path):
        """缺 Wechatpay-Signature 头 → None (伪造回调直接拒)。"""
        platform_priv = rsa.generate_private_key(65537, 2048)
        c = self._make_client(keypair, tmp_path, platform_priv)
        assert c.verify_and_decrypt_notify(b"{}", {}) is None

    def test_missing_required_fields_returns_none(self, keypair, tmp_path):
        """解密成功但缺 out_trade_no → None。"""
        platform_priv = rsa.generate_private_key(65537, 2048)
        c = self._make_client(keypair, tmp_path, platform_priv)
        api_key = bytes.fromhex(c.settings.WX_PAY_APIV3_KEY)
        plaintext = json.dumps({"transaction_id": "4200", "trade_state": "SUCCESS"}).encode()
        ct = AESGCM(api_key).encrypt(b"0123456789ab", plaintext, b"transaction")
        body = json.dumps({
            "resource": {
                "ciphertext": base64.b64encode(ct).decode(),
                "nonce": "0123456789ab",
                "associated_data": "transaction",
            },
        }).encode()
        headers = self._signed_body(platform_priv, body)
        assert c.verify_and_decrypt_notify(body, headers) is None


# ═══════════════════════════════════════════════════════════════
# query_order / refund / generate_sub_mchid 骨架行为
# ═══════════════════════════════════════════════════════════════
class TestQueryRefundApplyment:
    def _client(self, keypair, tmp_path, transport):
        from app.services.wx_pay.real_client import RealWxPayClient
        priv, _ = keypair
        pem = tmp_path / "k_misc.pem"
        pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        return RealWxPayClient(
            _full_settings(WX_PAY_PRIVATE_KEY_PATH=str(pem)), transport=transport
        )

    def test_query_order_maps_response(self, keypair, tmp_path):
        from app.services.wx_pay.client import OrderQueryResult
        tp = _FakeTransport(responses={"transactions/out-trade-no": {
            "payload": {
                "out_trade_no": "TL_q", "transaction_id": "4200Q",
                "trade_state": "SUCCESS",
                "success_time": "2026-08-17T10:00:00+08:00",
            },
        }})
        c = self._client(keypair, tmp_path, tp)
        r = c.query_order("TL_q")
        assert isinstance(r, OrderQueryResult)
        assert r.wx_transaction_id == "4200Q"
        assert r.trade_state == "SUCCESS"
        assert r.paid_at is not None

    def test_refund_maps_response(self, keypair, tmp_path):
        from app.services.wx_pay.client import RefundResult
        tp = _FakeTransport(responses={"refunds": {
            "payload": {
                "out_refund_no": "RF_1", "refund_id": "4200RF",
                "status": "SUCCESS", "amount": {"refund": 5000},
            },
        }})
        c = self._client(keypair, tmp_path, tp)
        r = c.refund(
            out_trade_no="TL_r", out_refund_no="RF_1",
            refund_amount_fen=5000, reason="测试",
        )
        assert isinstance(r, RefundResult)
        assert r.refund_id == "4200RF"
        assert r.status == "SUCCESS"
        assert r.refund_amount_fen == 5000
        body = tp.calls[0]["json"]
        assert body["out_trade_no"] == "TL_r"
        assert body["amount"]["refund"] == 5000

    def test_generate_sub_mchid_from_applyment_query(self, keypair, tmp_path):
        """generate_sub_mchid: 调 applyment4sub 查询接口取 sub_mchid。"""
        tp = _FakeTransport(responses={"applyment4sub": {
            "payload": {
                "applyment_state": "FINISH",
                "sub_mchid": "2490000999",
            },
        }})
        c = self._client(keypair, tmp_path, tp)
        assert c.generate_sub_mchid() == "2490000999"
