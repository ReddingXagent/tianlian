"""
开票平台配置 — 扩展字段 (OAuth/RSA) + 敏感字段脱敏 回归测试。

覆盖任务: InvoicePlatformConfig 模型扩展 + API schema:
- Create/Update 接受新字段 (access_token_url / private_key_enc / device_no /
  callback_url / ext_config_json)
- private_key_enc 写入时 Fernet 加密存储 (DB 中为密文, 非明文), 读取时 API 层不回显明文
- app_secret / private_key_enc 列表/详情返回脱敏 (仅回显后 4 位)
- token_cache_json (含运行时 access_token) 不回显明文, 仅暴露是否存在缓存
"""
import json

import pytest

import ipaddress
import socket

from app.core import url_safety


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    """SSRF 校验(卡 fb8b8106)需解析出站 URL 主机名; 测试环境无 DNS,
    域名一律伪造解析为公网 IP, 不触发真实网络。"""
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
            return real_getaddrinfo(host, *args, **kwargs)
        except ValueError:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)


from app.core import crypto_utils
from app.core.crypto_utils import decrypt_field
from app.models.ops_settlement.invoice_platform_config import (
    InvoicePlatformConfig,
    PlatformType,
)


PLAIN_PRIVATE_KEY = (
    "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAQ\n"
    "-----END PRIVATE KEY-----"
)


def _row(client, platform_id):
    return client._sesh.query(InvoicePlatformConfig).filter_by(id=platform_id).first()


class TestCreateExtendedFields:
    def test_create_with_extended_fields_echoed(self, client):
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_type": "nuonuo",
            "platform_name": "诺诺生产",
            "api_url": "https://api.nuonuo.com",
            "app_key": "nk001",
            "app_secret": "sk-secret-9999",
            "access_token_url": "https://api.nuonuo.com/oauth2/token",
            "private_key_enc": PLAIN_PRIVATE_KEY,
            "device_no": "DEV-001",
            "callback_url": "https://ops.example.com/invoice/callback",
            "ext_config_json": json.dumps({"order": "nuonuo", "test": True}),
        })
        assert r.status_code == 200, r.text
        data = r.json()["data"]

        # 新字段原样回显
        assert data["access_token_url"] == "https://api.nuonuo.com/oauth2/token"
        assert data["device_no"] == "DEV-001"
        assert data["callback_url"] == "https://ops.example.com/invoice/callback"
        assert json.loads(data["ext_config_json"]) == {"order": "nuonuo", "test": True}

    def test_private_key_encrypted_in_db_not_plaintext(self, client):
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_type": "nuonuo",
            "platform_name": "诺诺",
            "private_key_enc": PLAIN_PRIVATE_KEY,
        })
        assert r.status_code == 200
        pid = r.json()["data"]["id"]

        row = _row(client, pid)
        # DB 中是密文, 非原始明文
        assert row.private_key_enc != PLAIN_PRIVATE_KEY
        assert PLAIN_PRIVATE_KEY not in (row.private_key_enc or "")
        # 密文可解密还原明文
        assert decrypt_field(row.private_key_enc) == PLAIN_PRIVATE_KEY


class TestDesensitization:
    def test_app_secret_masked_last4(self, client):
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_type": "baiwang",
            "platform_name": "百旺",
            "app_secret": "sk-secret-9999",
        })
        assert r.status_code == 200
        pid = r.json()["data"]["id"]

        item = client.get("/api/v1/operate/invoice-platforms").json()["data"]["items"][0]
        assert item["id"] == pid
        # 仅回显后 4 位
        assert item["app_secret"] == "****9999"
        assert "sk-secret" not in item["app_secret"]

    def test_private_key_enc_masked_in_response(self, client):
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_type": "nuonuo",
            "platform_name": "诺诺",
            "private_key_enc": PLAIN_PRIVATE_KEY,
        })
        pid = r.json()["data"]["id"]
        row = _row(client, pid)

        item = client.get("/api/v1/operate/invoice-platforms").json()["data"]["items"][0]
        # 脱敏: 仅回显密文后 4 位, 不泄露明文也不泄露完整密文
        assert item["private_key_enc"] == "****" + row.private_key_enc[-4:]
        assert PLAIN_PRIVATE_KEY not in json.dumps(item)

    def test_token_cache_not_leaked(self, client):
        """token_cache_json 含运行时 access_token, 列表不得回显明文。"""
        from datetime import datetime, timezone
        p = InvoicePlatformConfig(
            team_id=0,
            platform_type=PlatformType.NUONUO,
            platform_name="带缓存",
            token_cache_json=json.dumps({
                "access_token": "LEAK_ME_BEARER_TOKEN_xyz",
                "expires_at": "2099-01-01T00:00:00+00:00",
                "obtained_at": datetime.now(timezone.utc).isoformat(),
            }),
        )
        client._sesh.add(p)
        client._sesh.commit()
        client._sesh.refresh(p)

        item = client.get("/api/v1/operate/invoice-platforms").json()["data"]["items"][0]
        serialized = json.dumps(item)
        # 存在缓存标记
        assert item.get("token_cached") is True
        # 明文 access_token 绝不出现在响应里
        assert "LEAK_ME_BEARER_TOKEN_xyz" not in serialized
        assert "token_cache_json" not in item

    def test_empty_secrets_return_none(self, client):
        """未配置 app_secret / private_key_enc 时返回 None 而非 '****'。"""
        client.post("/api/v1/operate/invoice-platforms", json={
            "platform_type": "other",
            "platform_name": "无密钥",
        })
        item = client.get("/api/v1/operate/invoice-platforms").json()["data"]["items"][0]
        assert item["app_secret"] is None
        assert item["private_key_enc"] is None
        assert item["token_cached"] is False


class TestUpdateExtendedFields:
    def test_update_extended_fields(self, client):
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_type": "nuonuo",
            "platform_name": "诺诺",
        })
        pid = r.json()["data"]["id"]

        upd = client.put(f"/api/v1/operate/invoice-platforms/{pid}", json={
            "device_no": "DEV-NEW",
            "access_token_url": "https://new.token.url",
            "callback_url": "https://cb.url",
        })
        assert upd.status_code == 200
        data = upd.json()["data"]
        assert data["device_no"] == "DEV-NEW"
        assert data["access_token_url"] == "https://new.token.url"

    def test_update_private_key_enc_re_encrypts(self, client):
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_type": "nuonuo",
            "platform_name": "诺诺",
            "private_key_enc": PLAIN_PRIVATE_KEY,
        })
        pid = r.json()["data"]["id"]
        old_ct = _row(client, pid).private_key_enc

        new_plain = PLAIN_PRIVATE_KEY.replace("MIIEvg", "MIIEvh")
        upd = client.put(f"/api/v1/operate/invoice-platforms/{pid}", json={
            "private_key_enc": new_plain,
        })
        assert upd.status_code == 200
        new_ct = _row(client, pid).private_key_enc
        # 密文已变化且可解为新明文
        assert new_ct != old_ct
        assert new_ct != new_plain
        assert decrypt_field(new_ct) == new_plain

    def test_update_clear_private_key(self, client):
        """更新传空私钥 -> 清空 (None)。"""
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_type": "nuonuo",
            "platform_name": "诺诺",
            "private_key_enc": PLAIN_PRIVATE_KEY,
        })
        pid = r.json()["data"]["id"]
        assert _row(client, pid).private_key_enc is not None

        client.put(f"/api/v1/operate/invoice-platforms/{pid}", json={
            "private_key_enc": "",
        })
        assert _row(client, pid).private_key_enc is None
