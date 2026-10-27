"""
crypto_utils 单元测试 — Fernet 字段级加解密。

覆盖:
- 对称往返 (encrypt -> decrypt 还原)
- None / 空串透传
- 密钥派生稳定性 (同一 SECRET_KEY 派生同一 Fernet)
- 密文每次不同 (Fernet 内置随机 IV)
- 显式 FIELD_ENCRYPTION_KEY 注入
- 密文损坏 / 密钥不匹配 -> CryptoError
"""
import base64

import pytest
from cryptography.fernet import Fernet

from app.core import crypto_utils
from app.core.crypto_utils import CryptoError, decrypt_field, encrypt_field


class TestCryptoRoundTrip:
    def test_encrypt_decrypt_roundtrip(self):
        plain = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAI...\n-----END RSA PRIVATE KEY-----"
        token = encrypt_field(plain)
        assert token != plain
        assert decrypt_field(token) == plain

    def test_none_passthrough(self):
        assert encrypt_field(None) is None
        assert decrypt_field(None) is None

    def test_empty_string_passthrough(self):
        assert encrypt_field("") == ""
        assert decrypt_field("") == ""

    def test_ciphertext_differs_each_call(self):
        """Fernet 内置随机 IV, 同一明文两次加密密文不同。"""
        plain = "sk-secret-123"
        a = encrypt_field(plain)
        b = encrypt_field(plain)
        assert a != b
        assert decrypt_field(a) == decrypt_field(b) == plain

    def test_unicode_roundtrip(self):
        plain = "纳税人识别号_测试🔐"
        assert decrypt_field(encrypt_field(plain)) == plain


class TestKeyDerivation:
    def test_derivation_stable_across_calls(self):
        """同一进程 (同一 SECRET_KEY 派生) 加密后可解密。"""
        token = encrypt_field("stable-value")
        assert decrypt_field(token) == "stable-value"

    def test_explicit_field_encryption_key_used(self, monkeypatch):
        """配置 FIELD_ENCRYPTION_KEY 时直接用该 key (非派生)。"""
        explicit_key = Fernet.generate_key()
        from app.core.config import settings

        monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", explicit_key.decode())
        # 清缓存使新 key 生效
        crypto_utils._get_fernet.cache_clear()
        try:
            token = encrypt_field("with-explicit-key")
            # 用同一 key 直接解密验证未被派生改写
            assert Fernet(explicit_key).decrypt(token.encode()).decode() == "with-explicit-key"
        finally:
            crypto_utils._get_fernet.cache_clear()
            monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", None)

    def test_derived_key_when_unconfigured(self, monkeypatch):
        """未配置时从 SECRET_KEY 经 HKDF 派生 (32 字节 -> urlsafe base64 合法 Fernet key)。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", None)
        crypto_utils._get_fernet.cache_clear()
        f = crypto_utils._get_fernet()
        # 派生 key 必为合法 Fernet key (能加解密)
        token = f.encrypt(b"x")
        assert f.decrypt(token) == b"x"


class TestErrorHandling:
    def test_corrupt_ciphertext_raises_crypto_error(self):
        with pytest.raises(CryptoError):
            decrypt_field("not-a-valid-fernet-token###")

    def test_key_mismatch_raises_crypto_error(self, monkeypatch):
        """用 key A 加密, 换 key B 后解密 -> 失败。"""
        from app.core.config import settings

        crypto_utils._get_fernet.cache_clear()
        monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", None)
        crypto_utils._get_fernet.cache_clear()
        token = encrypt_field("under-derived-key")

        # 换成另一个派生源 (不同 SECRET_KEY)
        monkeypatch.setattr(settings, "SECRET_KEY", "a-completely-different-secret" * 2)
        crypto_utils._get_fernet.cache_clear()
        with pytest.raises(CryptoError):
            decrypt_field(token)
