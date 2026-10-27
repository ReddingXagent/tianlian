"""
开票平台配置 SSRF 防护测试 (卡 fb8b8106)

create/update 写端点的 api_url / access_token_url 落库前经
validate_external_url 校验 (内网/环回/链路本地/IPv4-mapped 拒绝);
callback_url 是平台回调我方的入站地址, 不套用出站校验。

DNS 全程 monkeypatch (零真实网络依赖), 同 test_ai_model_ssrf 模式。
"""
import ipaddress
import socket

import pytest

from app.core import url_safety


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """测试域名一律解析为公网 IP; IP 字面量走真实 getaddrinfo(保留内网属性判断)。"""
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
            return real_getaddrinfo(host, *args, **kwargs)
        except ValueError:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)


UNSAFE_URLS = [
    "http://192.168.1.1/x",          # 私网 IPv4
    "http://127.0.0.1",              # 环回
    "http://10.0.0.5/api",           # 私网
    "http://[::ffff:169.254.169.254]/metadata",  # IPv4-mapped 链路本地 (metadata)
    "http://[::1]/token",            # IPv6 环回
    "http://localhost:8080",         # localhost 字面量
    "ftp://api.nuonuo.com",          # 非法 scheme
    "http://169.254.169.254/latest/meta-data",   # 云 metadata
]


class TestCreateSSRF:
    def test_unsafe_api_url_rejected_422(self, client):
        for url in UNSAFE_URLS:
            r = client.post("/api/v1/operate/invoice-platforms", json={
                "platform_name": "诺诺", "api_url": url,
            })
            assert r.status_code == 422, f"{url} 应被拒绝, got {r.status_code}"

    def test_unsafe_access_token_url_rejected_422(self, client):
        for url in UNSAFE_URLS:
            r = client.post("/api/v1/operate/invoice-platforms", json={
                "platform_name": "诺诺", "access_token_url": url,
            })
            assert r.status_code == 422, f"{url} 应被拒绝, got {r.status_code}"

    def test_public_https_pass(self, client):
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_name": "诺诺生产",
            "api_url": "https://api.nuonuo.com/openinvoice",
            "access_token_url": "https://api.nuonuo.com/token",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["api_url"] == "https://api.nuonuo.com/openinvoice"
        assert data["access_token_url"] == "https://api.nuonuo.com/token"

    def test_none_or_empty_skipped(self, client):
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_name": "无URL配置",
            "api_url": None,
            "access_token_url": "",
        })
        assert r.status_code == 200
        assert r.json()["data"]["api_url"] is None
        assert r.json()["data"]["access_token_url"] in (None, "")

    def test_callback_url_intranet_allowed(self, client):
        """callback_url 是平台回调我方的入站地址, 不做出站 SSRF 校验。"""
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_name": "内网回调",
            "api_url": "https://api.nuonuo.com",
            "callback_url": "http://192.168.1.1/invoice/callback",
        })
        assert r.status_code == 200
        assert r.json()["data"]["callback_url"] == "http://192.168.1.1/invoice/callback"


class TestUpdateSSRF:
    def _seed(self, client):
        from app.models.ops_settlement.invoice_platform_config import InvoicePlatformConfig
        p = InvoicePlatformConfig(
            team_id=1, platform_name="存量配置",
            platform_type="nuonuo",
            api_url="https://api.nuonuo.com",
        )
        client._sesh.add(p)
        client._sesh.commit()
        return p.id

    def test_unsafe_update_rejected_422(self, client):
        pid = self._seed(client)
        for url in UNSAFE_URLS:
            r = client.put(f"/api/v1/operate/invoice-platforms/{pid}", json={
                "api_url": url,
            })
            assert r.status_code == 422, f"{url} 应被拒绝, got {r.status_code}"
            r = client.put(f"/api/v1/operate/invoice-platforms/{pid}", json={
                "access_token_url": url,
            })
            assert r.status_code == 422, f"{url} 应被拒绝, got {r.status_code}"

    def test_update_none_skipped_public_pass(self, client):
        pid = self._seed(client)
        r = client.put(f"/api/v1/operate/invoice-platforms/{pid}", json={
            "api_url": None,
        })
        assert r.status_code == 200
        r = client.put(f"/api/v1/operate/invoice-platforms/{pid}", json={
            "access_token_url": "https://token.nuonuo.com/t",
        })
        assert r.status_code == 200
        assert r.json()["data"]["access_token_url"] == "https://token.nuonuo.com/t"

    def test_update_callback_url_intranet_allowed(self, client):
        pid = self._seed(client)
        r = client.put(f"/api/v1/operate/invoice-platforms/{pid}", json={
            "callback_url": "http://127.0.0.1:9000/cb",
        })
        assert r.status_code == 200
        assert r.json()["data"]["callback_url"] == "http://127.0.0.1:9000/cb"
