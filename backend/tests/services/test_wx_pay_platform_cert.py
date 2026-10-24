"""平台证书自动下载/轮换链测试 (卡 7f5b4d4f A2, 凭证无关)

被测: app/services/wx_pay/real_client.py — RealWxPayClient 平台证书管理:
- GET /v3/certificates 下载平台证书列表 (APIv3 key AES-256-GCM 解密证书密文)
- 按证书 effective_time/expire_time 选有效证书
- 缓存: 剩余有效期 < 1/3 时刷新; 下载失败回退已缓存证书 (可用性优先)
- fail-closed: 无可用证书 → 验签拒绝 (伪造回调风险 > 可用性)
- 并发下载单飞: 多线程并发验签只触发一次下载 (锁保护)

设计对齐IM-B官方:
- /v3/certificates 响应的 encrypt_certificate {nonce, associated_data, ciphertext}
  用 APIv3 key AES-256-GCM 解密 → PEM 证书串 → 加载公钥。
- Wechatpay-Serial 与证书 serial_no 匹配的证书验签 (平台证书轮换期新旧并存)。
- 全程 HTTP 打桩 (复用 A1 _FakeTransport 模式), 零网络。
"""
import base64
import json
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509.oid import NameOID

from app.services.wx_pay.client import WxPayError
from app.services.wx_pay.real_client import RealWxPayClient


# ═══════════════════════════════════════════════════════════════
# 脚手架: 自签平台证书 (含有效期) + 加密下载响应
# ═══════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def keypair():
    """商户 API 私钥假密钥对 (模块级复用, RealWxPayClient 构造签名用)。"""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()

def _make_platform_cert(
    serial: str,
    not_before: datetime,
    not_after: datetime,
):
    """自签一张平台证书, 返回 (cert, private_key)。serial 进证书序列号。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "im_bpay-test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(int(serial))
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    return cert, key


def _cert_pem_b64(cert) -> str:
    return base64.b64encode(
        cert.public_bytes(serialization.Encoding.PEM)
    ).decode()


def _rfc3339(dt: datetime) -> str:
    """IM-B证书接口时间格式 (RFC3339, +08:00)。"""
    return dt.astimezone(timezone(timedelta(hours=8))).strftime(
        "%Y-%m-%dT%H:%M:%S+08:00"
    )


def _encrypted_cert_payload(api_key_hex: str, cert, nonce: bytes = b"certnonce99") -> dict:
    """构造 /v3/certificates 单条证书项 (AES-GCM 加密的 PEM)。"""
    key = bytes.fromhex(api_key_hex)
    plaintext = cert.public_bytes(serialization.Encoding.PEM)
    ct = AESGCM(key).encrypt(nonce, plaintext, b"certificate")
    return {
        "serial_no": format(cert.serial_number, "X"),
        "effective_time": _rfc3339(cert.not_valid_before_utc),
        "expire_time": _rfc3339(cert.not_valid_after_utc),
        "encrypt_certificate": {
            "algorithm": "AEAD_AES_256_GCM",
            "nonce": nonce.decode(),
            "associated_data": "certificate",
            "ciphertext": base64.b64encode(ct).decode(),
        },
    }


class _CertTransport:
    """/v3/certificates 下载替身: 记录调用次数, 可控抛错。"""

    def __init__(self, cert_payloads=None, exc=None):
        self.cert_calls = 0
        self._payloads = cert_payloads
        self._exc = exc

    def get(self, url, headers=None, timeout=None):
        if "/v3/certificates" in url:
            self.cert_calls += 1
            if self._exc is not None:
                raise self._exc
            r = SimpleNamespace()
            r.status_code = 200
            r.json = lambda: {"data": list(self._payloads)}
            return r
        raise AssertionError(f"unexpected url: {url}")

    def post(self, url, json=None, headers=None, timeout=None):
        raise AssertionError(f"unexpected post: {url}")


def _settings_with_key(tmp_path, keypair, **over):
    """齐备凭证 settings (私钥写 tmp 文件)。"""
    priv, _ = keypair
    pem = tmp_path / "k_cert.pem"
    pem.write_bytes(priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    base = dict(
        WX_PAY_MODE="real",
        WX_PAY_SP_MCHID="1900000001",
        WX_PAY_PRIVATE_KEY_PATH=str(pem),
        WX_PAY_CERT_SERIAL="SERIAL0001",
        WX_PAY_APIV3_KEY="0123456789abcdef0123456789abcdef",
        WX_PAY_APPID_MINIPROGRAM="wx1111111111111111",
        WX_PAY_APPID_APP="wx2222222222222222",
        WX_PAY_NOTIFY_URL="https://api.tianlian.example/v1/business/payments/notify",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _valid_cert_pair(days_total=90, frac_left=0.9):
    """一张有效期内的证书: now_before 提前 1 天起, 长 days_total 天。"""
    now = datetime.now(timezone.utc)
    nb = now - timedelta(days=1)
    na = nb + timedelta(days=days_total)
    return _make_platform_cert(
        format(int.from_bytes(b"AAAABBBB", "big"), "d"), nb, na,
    )


def _sign_body(priv, body: bytes) -> dict:
    sig = base64.b64encode(priv.sign(
        body, padding.PKCS1v15(), hashes.SHA256()
    )).decode()
    return {"Wechatpay-Signature": sig, "Wechatpay-Serial": "WHATEVER"}
# ═══════════════════════════════════════════════════════════════
# 1. 正常下载轮换链
# ═══════════════════════════════════════════════════════════════
class TestCertDownloadRotation:
    def test_first_verify_triggers_download_and_verifies(
        self, keypair, tmp_path
    ):
        """未缓存 → 下载 /v3/certificates → 解密证书 → 用其公钥验签通过。"""
        cert, plat_priv = _valid_cert_pair()
        api_key = _settings_with_key(tmp_path, keypair).WX_PAY_APIV3_KEY
        tp = _CertTransport([_encrypted_cert_payload(api_key, cert)])
        c = RealWxPayClient(_settings_with_key(tmp_path, keypair), transport=tp)

        body = b'{"event_type":"TRANSACTION.SUCCESS"}'
        ok = c._verify_platform(
            body,
            base64.b64encode(plat_priv.sign(body, padding.PKCS1v15(), hashes.SHA256())).decode(),
            format(cert.serial_number, "X"),
        )
        assert ok is True
        assert tp.cert_calls == 1

    def test_verify_via_full_notify_chain(self, keypair, tmp_path):
        """verify_and_decrypt_notify 全链: 平台证书自动下载后验签+解密出 NotifyResult。"""
        cert, plat_priv = _valid_cert_pair()
        settings = _settings_with_key(tmp_path, keypair)
        tp = _CertTransport([_encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, cert)])
        c = RealWxPayClient(settings, transport=tp)

        api_key = bytes.fromhex(settings.WX_PAY_APIV3_KEY)
        nonce = b"0123456789ab"
        plaintext = json.dumps({
            "sp_appid": "wx1111111111111111",
            "sp_mchid": "1900000001",
            "sub_mchid": "2490000001",
            "out_trade_no": "TL_cert1",
            "transaction_id": "4200CERT1",
            "trade_state": "SUCCESS",
            "amount": {"total": 8200},
            "success_time": "2026-08-17T10:00:00+08:00",
        }).encode()
        ct = AESGCM(api_key).encrypt(nonce, plaintext, b"transaction")
        body = json.dumps({
            "id": "EV-CERT-1",
            # 防重放窗 (卡 071194e4 A3) 必带: 用当前时刻 (走真实时钟的用例)
            "create_time": _rfc3339(datetime.now(timezone.utc)),
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {
                "ciphertext": base64.b64encode(ct).decode(),
                "nonce": nonce.decode(),
                "associated_data": "transaction",
            },
        }).encode()
        r = c.verify_and_decrypt_notify(body, {
            "Wechatpay-Signature": base64.b64encode(plat_priv.sign(
                body, padding.PKCS1v15(), hashes.SHA256()
            )).decode(),
            "Wechatpay-Serial": format(cert.serial_number, "X"),
        })
        assert r is not None
        assert r.out_trade_no == "TL_cert1"
        assert r.amount_fen == 8200

    def test_cached_cert_no_repeat_download(self, keypair, tmp_path):
        """证书缓存命中 (剩余有效期充足) → 二次验签不再下载。"""
        cert, plat_priv = _valid_cert_pair()
        settings = _settings_with_key(tmp_path, keypair)
        tp = _CertTransport([_encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, cert)])
        c = RealWxPayClient(settings, transport=tp)
        body = b'{"evt":1}'
        sig = base64.b64encode(plat_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        serial = format(cert.serial_number, "X")
        assert c._verify_platform(body, sig, serial) is True
        assert c._verify_platform(body, sig, serial) is True
        assert tp.cert_calls == 1

    def test_rotation_selects_new_cert_by_serial(self, keypair, tmp_path):
        """平台轮换期新旧两张证书并存 → 按 Wechatpay-Serial 各自验签通过。"""
        now = datetime.now(timezone.utc)
        old_cert, old_priv = _make_platform_cert(
            "1001", now - timedelta(days=80), now + timedelta(days=10),
        )
        new_cert, new_priv = _make_platform_cert(
            "2002", now - timedelta(days=1), now + timedelta(days=89),
        )
        settings = _settings_with_key(tmp_path, keypair)
        payloads = [
            _encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, old_cert),
            _encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, new_cert),
        ]
        c = RealWxPayClient(
            settings, transport=_CertTransport(payloads)
        )
        body = b'{"evt":"rotate"}'
        for priv, cert in ((old_priv, old_cert), (new_priv, new_cert)):
            sig = base64.b64encode(priv.sign(
                body, padding.PKCS1v15(), hashes.SHA256()
            )).decode()
            assert c._verify_platform(
                body, sig, format(cert.serial_number, "X")
            ) is True

    def test_expired_cert_not_used(self, keypair, tmp_path):
        """证书已过期 (expire_time < now) → 不入可用集 → 验签 fail-closed。"""
        now = datetime.now(timezone.utc)
        expired, expired_priv = _make_platform_cert(
            "3003", now - timedelta(days=100), now - timedelta(days=1),
        )
        settings = _settings_with_key(tmp_path, keypair)
        c = RealWxPayClient(
            settings,
            transport=_CertTransport([
                _encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, expired),
            ]),
        )
        body = b'{"evt":"x"}'
        sig = base64.b64encode(expired_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        assert c._verify_platform(
            body, sig, format(expired.serial_number, "X")
        ) is False

    def test_not_yet_effective_cert_not_used(self, keypair, tmp_path):
        """证书 effective_time 在未来 → 不入可用集 → 验签 fail-closed。"""
        now = datetime.now(timezone.utc)
        future, future_priv = _make_platform_cert(
            "4004", now + timedelta(days=1), now + timedelta(days=91),
        )
        settings = _settings_with_key(tmp_path, keypair)
        c = RealWxPayClient(
            settings,
            transport=_CertTransport([
                _encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, future),
            ]),
        )
        body = b'{"evt":"y"}'
        sig = base64.b64encode(future_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        assert c._verify_platform(
            body, sig, format(future.serial_number, "X")
        ) is False


# ═══════════════════════════════════════════════════════════════
# 2. 刷新策略: 剩余有效期 < 1/3
# ═══════════════════════════════════════════════════════════════
class TestCertRefreshPolicy:
    def test_refresh_when_less_than_third_remaining(self, keypair, tmp_path):
        """剩余有效期 < 1/3 (90 天证书只剩 20 天) → 每次验签触发重新下载。"""
        now = datetime.now(timezone.utc)
        nb = now - timedelta(days=70)
        cert, plat_priv = _make_platform_cert("5005", nb, nb + timedelta(days=90))
        settings = _settings_with_key(tmp_path, keypair)
        tp = _CertTransport([_encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, cert)])
        c = RealWxPayClient(settings, transport=tp)
        body = b'{"evt":"r1"}'
        sig = base64.b64encode(plat_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        serial = format(cert.serial_number, "X")
        assert c._verify_platform(body, sig, serial) is True
        assert c._verify_platform(body, sig, serial) is True
        assert tp.cert_calls >= 2  # 剩余不足 1/3 → 不吃缓存, 重新拉

    def test_fresh_cert_no_refresh(self, keypair, tmp_path):
        """剩余充足 (>1/3) → 不刷新 (cached 用例的对照, 显式化策略)。"""
        cert, plat_priv = _valid_cert_pair(days_total=90, frac_left=0.9)
        settings = _settings_with_key(tmp_path, keypair)
        tp = _CertTransport([_encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, cert)])
        c = RealWxPayClient(settings, transport=tp)
        body = b'{"evt":"r2"}'
        sig = base64.b64encode(plat_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        c._verify_platform(body, sig, format(cert.serial_number, "X"))
        c._verify_platform(body, sig, format(cert.serial_number, "X"))
        assert tp.cert_calls == 1


# ═══════════════════════════════════════════════════════════════
# 3. 下载失败回退 / fail-closed
# ═══════════════════════════════════════════════════════════════
class TestCertDownloadFailure:
    def test_refresh_failure_falls_back_to_cached(self, keypair, tmp_path):
        """刷新失败 (网络断) → 回退已缓存证书继续验签 (可用性优先)。"""
        now = datetime.now(timezone.utc)
        nb = now - timedelta(days=70)  # 剩 20 天 < 1/3 → 每次都尝试刷新
        cert, plat_priv = _make_platform_cert("6006", nb, nb + timedelta(days=90))
        settings = _settings_with_key(tmp_path, keypair)
        payload = _encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, cert)
        tp = _CertTransport([payload])
        c = RealWxPayClient(settings, transport=tp)
        body = b'{"evt":"fb"}'
        sig = base64.b64encode(plat_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        serial = format(cert.serial_number, "X")
        assert c._verify_platform(body, sig, serial) is True
        # 断网: 后续刷新全失败, 但缓存证书仍可验签
        tp._exc = ConnectionError("network down")
        tp._payloads = None
        assert c._verify_platform(body, sig, serial) is True

    def test_no_valid_cert_rejects_verify(self, keypair, tmp_path):
        """下载返回空列表 (无有效证书) → 验签拒绝 (fail-closed, 不放宽)。"""
        settings = _settings_with_key(tmp_path, keypair)
        c = RealWxPayClient(settings, transport=_CertTransport([]))
        attacker = rsa.generate_private_key(65537, 2048)
        body = b'{"evt":"attack"}'
        sig = base64.b64encode(attacker.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        assert c._verify_platform(body, sig, "9999") is False

    def test_download_exception_rejects_when_no_cache(self, keypair, tmp_path):
        """首下载即网络异常 (无缓存可回退) → fail-closed 拒绝验签, 不抛。"""
        settings = _settings_with_key(tmp_path, keypair)
        c = RealWxPayClient(
            settings, transport=_CertTransport(exc=ConnectionError("down"))
        )
        attacker = rsa.generate_private_key(65537, 2048)
        body = b'{"evt":"cold"}'
        sig = base64.b64encode(attacker.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        assert c._verify_platform(body, sig, "1234") is False

    def test_bad_ciphertext_cert_skipped(self, keypair, tmp_path):
        """证书密文损坏 (解密失败) → 跳过该条; 全损坏 → fail-closed。"""
        settings = _settings_with_key(tmp_path, keypair)
        bad = {
            "serial_no": "7007",
            "effective_time": _rfc3339(datetime.now(timezone.utc) - timedelta(days=1)),
            "expire_time": _rfc3339(datetime.now(timezone.utc) + timedelta(days=89)),
            "encrypt_certificate": {
                "algorithm": "AEAD_AES_256_GCM",
                "nonce": "badnonce0000",
                "associated_data": "certificate",
                "ciphertext": base64.b64encode(b"garbage-bytes").decode(),
            },
        }
        c = RealWxPayClient(settings, transport=_CertTransport([bad]))
        attacker = rsa.generate_private_key(65537, 2048)
        body = b'{"evt":"bad"}'
        sig = base64.b64encode(attacker.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        assert c._verify_platform(body, sig, "7007") is False


# ═══════════════════════════════════════════════════════════════
# 4. 并发下载单飞
# ═══════════════════════════════════════════════════════════════
class TestConcurrentDownloadSingleFlight:
    def test_concurrent_verify_downloads_once(self, keypair, tmp_path):
        """8 线程并发首验签 → /v3/certificates 只下载一次 (锁单飞)。"""
        cert, plat_priv = _valid_cert_pair()
        settings = _settings_with_key(tmp_path, keypair)
        tp = _CertTransport([_encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, cert)])
        c = RealWxPayClient(settings, transport=tp)
        body = b'{"evt":"conc"}'
        sig = base64.b64encode(plat_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        serial = format(cert.serial_number, "X")
        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(c._verify_platform(body, sig, serial))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(r is True for r in results)
        assert tp.cert_calls == 1


# ═══════════════════════════════════════════════════════════════
# 5. 注入兼容: _platform_pubkey 直注 (A1 遗留测试路径不破坏)
# ═══════════════════════════════════════════════════════════════
class TestInjectedPubkeyCompat:
    def test_injected_pubkey_still_wins(self, keypair, tmp_path):
        """_platform_pubkey 直注 → 不触发下载, 直接用注入公钥验签 (A1 测试路径)。"""
        platform_priv = rsa.generate_private_key(65537, 2048)
        settings = _settings_with_key(tmp_path, keypair)
        tp = _CertTransport([])  # 下载必返回空 → 若走下载链必 fail
        c = RealWxPayClient(settings, transport=tp)
        c._platform_pubkey = platform_priv.public_key()
        body = b'{"evt":"inj"}'
        sig = base64.b64encode(platform_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        assert c._verify_platform(body, sig, "ANY") is True
        assert tp.cert_calls == 0

    def test_platform_verifier_injection_still_wins(self, keypair, tmp_path):
        """platform_verifier 构造注入优先级最高 (A1 测试路径)。"""
        settings = _settings_with_key(tmp_path, keypair)
        tp = _CertTransport([])
        c = RealWxPayClient(
            settings, transport=tp,
            platform_verifier=lambda b, s, ser: True,
        )
        assert c._verify_platform(b"{}", "AA", "S1") is True
        assert tp.cert_calls == 0
