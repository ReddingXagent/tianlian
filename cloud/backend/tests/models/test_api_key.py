#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Key 模型测试
"""
import pytest
from app.models.api_key import ApiKey, ApiKeyUsageLog, ClientCertificate, generate_api_key, hash_api_key

class TestApiKeyModel:
    def test_generate_api_key_format(self):
        key = generate_api_key()
        assert key.startswith("tl_")
        assert len(key) > 10

    def test_generate_api_key_uniqueness(self):
        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100

    def test_hash_api_key_length(self):
        key = generate_api_key()
        h = hash_api_key(key)
        assert len(h) == 64
        assert h.isalnum() or all(c in "abcdef0123456789" for c in h)

    def test_hash_consistency(self):
        key = "tl_testkey123"
        h1 = hash_api_key(key)
        h2 = hash_api_key(key)
        assert h1 == h2

    def test_hash_different_keys(self):
        h1 = hash_api_key("tl_key1")
        h2 = hash_api_key("tl_key2")
        assert h1 != h2

    def test_api_key_columns(self):
        cols = [c.name for c in ApiKey.__table__.columns]
        assert "id" in cols
        assert "key_hash" in cols
        assert "name" in cols
        assert "scopes" in cols
        assert "is_active" in cols

    def test_usage_log_columns(self):
        cols = [c.name for c in ApiKeyUsageLog.__table__.columns]
        assert "id" in cols
        assert "path" in cols  # ApiKeyUsageLog uses path
        assert "api_key_id" in cols

    def test_client_cert_columns(self):
        cols = [c.name for c in ClientCertificate.__table__.columns]
        assert "id" in cols
        assert "cert_serial" in cols
        assert "cert_pem" in cols  # ClientCertificate uses cert_pem

class TestApiKeyExpiryTimezone:
    """is_expired 对 naive/aware datetime 的兼容 (卡b70a0d39)。

    DB 的 Column(DateTime) 无 tz，从 SQLite 读出的 expires_at/valid_until 为 naive datetime，
    与 datetime.now(timezone.utc) 直接比较会抛 TypeError。
    """

    def test_apikey_is_expired_naive_past_no_typeerror(self):
        from datetime import datetime
        key = ApiKey(key_hash="x" * 64, key_prefix="tl_", name="t",
                     expires_at=datetime(2020, 1, 1))
        assert key.is_expired() is True

    def test_apikey_is_expired_naive_future_no_typeerror(self):
        from datetime import datetime
        key = ApiKey(key_hash="y" * 64, key_prefix="tl_", name="t",
                     expires_at=datetime(2099, 1, 1))
        assert key.is_expired() is False

    def test_apikey_is_expired_none(self):
        key = ApiKey(key_hash="w" * 64, key_prefix="tl_", name="t", expires_at=None)
        assert key.is_expired() is False

    def test_clientcert_is_expired_naive_past_no_typeerror(self):
        from datetime import datetime
        cert = ClientCertificate(
            cert_serial="serial-1", cert_fingerprint="fp-1", cert_subject="sub",
            cert_issuer="iss", cert_pem="pem", name="c",
            valid_from=datetime(2020, 1, 1), valid_until=datetime(2020, 1, 2),
        )
        assert cert.is_expired() is True
