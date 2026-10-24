"""
AI 模型配置 SSRF 防护测试 (卡 7efb1f24)

保存侧: update_providers / update_full_config / add_provider 落盘前
复用 validate_external_url 校验 base_url, API 层 400 非 500。
出站侧: ai_chat / ai_diagnosis _call_llm 拼接前兜底校验。

DNS 全程 monkeypatch (零真实网络依赖, 确定性)。
"""
import socket
from unittest.mock import MagicMock, patch

import pytest

from app.core import url_safety
from app.core.url_safety import UnsafeURLError, validate_external_url
from app.services.ai_model_config import AIModelManager, DEFAULT_CONFIG


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """测试域名一律解析为公网 IP; 真实内网 IP 字面量不走 DNS 判断分支。"""

    import ipaddress as _ipa
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        # IP 字面量走真实 getaddrinfo(保留内网属性判断); 仅域名伪造为公网 IP
        try:
            _ipa.ip_address(host)
            return real_getaddrinfo(host, *args, **kwargs)
        except ValueError:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)


@pytest.fixture(autouse=True)
def preserve_model_config(monkeypatch):
    """禁用落盘 + 备份/恢复全局单例配置。"""
    import copy
    mgr = AIModelManager()
    original = copy.deepcopy(mgr.config)
    monkeypatch.setattr(mgr, "_save", lambda: None)
    yield
    mgr.config = original


PUBLIC_URL = "https://token-plan.cn-beijing.maas.cloud_providercs.com/compatible-mode/v1"


def _provider(**over):
    base = {
        "provider": "cloud_provider-token",
        "model_id": "test-model",
        "name": "TEST-MODEL",
        "base_url": PUBLIC_URL,
        "api_key": "sk-1234567890abcdef",
        "context_window": 128000,
        "max_tokens": 8192,
        "enabled": True,
    }
    base.update(over)
    return base


# ───────────────────────── 校验矩阵 ─────────────────────────


class TestUnsafeBaseUrlsRejected:
    """内网 IP / localhost / file:// / 空 host 各 1 例被拒"""

    @pytest.mark.parametrize("bad_url", [
        "http://10.0.0.5/v1",                 # 内网 10.x
        "http://192.168.1.10/v1",             # 内网 192.168.x
        "http://169.254.169.254/latest/meta-data",  # 云元数据
        "http://localhost:8000/v1",           # localhost 字面量
        "http://127.0.0.1:8000/v1",           # 环回 IP
        "file:///etc/passwd",                 # 非 http(s) scheme
        "https:///v1",                        # 空 host
    ])
    def test_validate_external_url_rejects(self, bad_url):
        with pytest.raises(UnsafeURLError):
            validate_external_url(bad_url)

    def test_public_cloud_provider_allowed(self):
        assert validate_external_url(PUBLIC_URL) == PUBLIC_URL


# ───────────────────────── 保存侧: service 层 ─────────────────────────


class TestServiceValidation:
    def test_update_providers_rejects_private_ip(self):
        mgr = AIModelManager()
        with pytest.raises(UnsafeURLError):
            mgr.update_providers([_provider(base_url="http://192.168.1.10/v1")])
        # 原配置未被污染
        assert mgr.config["providers"] != [_provider(base_url="http://192.168.1.10/v1")]

    def test_update_providers_rejects_metadata(self):
        with pytest.raises(UnsafeURLError):
            AIModelManager().update_providers([_provider(base_url="http://169.254.169.254/v1")])

    def test_add_provider_rejects_localhost(self):
        with pytest.raises(UnsafeURLError):
            AIModelManager().add_provider(_provider(base_url="http://localhost/v1"))

    def test_add_provider_rejects_file_scheme(self):
        with pytest.raises(UnsafeURLError):
            AIModelManager().add_provider(_provider(base_url="file:///etc/passwd"))

    def test_add_provider_allows_public(self):
        mgr = AIModelManager()
        before = len(mgr.config["providers"])
        mgr.add_provider(_provider())
        assert len(mgr.config["providers"]) == before + 1

    def test_default_config_base_url_allowed(self):
        """默认 cloud_provider 公网 base_url 必须全部通过校验(启动/空配置回退不崩)"""
        from app.services.ai_model_config import validate_provider_urls
        validate_provider_urls(DEFAULT_CONFIG["providers"])


# ───────────────────────── 保存侧: API 层 (400 非 500) ─────────────────────────


def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json().get("data", {}).get("token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


class TestApiValidation:
    def test_put_full_config_private_ip_returns_400(self, client, seed_users):
        body = {
            "providers": [_provider(base_url="http://10.0.0.5/v1")],
            "task_mappings": {"chat_general": "TEST-MODEL"},
        }
        resp = client.put("/api/v1/ai-model_config", json=body, headers=_auth(client))
        assert resp.status_code == 400
        assert "不安全" in resp.json()["detail"]

    def test_put_providers_metadata_returns_400(self, client, seed_users):
        resp = client.put(
            "/api/v1/ai-model_config/providers",
            json=[_provider(base_url="http://169.254.169.254/v1")],
            headers=_auth(client),
        )
        assert resp.status_code == 400

    def test_put_full_config_public_allowed(self, client, seed_users):
        body = {
            "providers": [_provider()],
            "task_mappings": {"chat_general": "TEST-MODEL"},
        }
        resp = client.put("/api/v1/ai-model_config", json=body, headers=_auth(client))
        assert resp.status_code == 200


# ───────────────────────── 出站侧兜底 ─────────────────────────


class TestOutboundGuard:
    def test_ai_chat_rejects_private_base_url(self):
        from app.services import ai_chat
        with patch.object(ai_chat.model_manager, "get_model_for_task",
                          return_value=_cfg(base_url="http://192.168.1.10/v1")), \
             patch.object(ai_chat.model_manager, "get_providers", return_value=[]):
            with pytest.raises(ValueError, match="base_url 不安全"):
                ai_chat._call_llm([{"role": "user", "content": "hi"}])

    def test_ai_chat_allows_public(self):
        from app.services import ai_chat
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
        with patch.object(ai_chat.model_manager, "get_model_for_task",
                          return_value=_cfg()), \
             patch("app.services.ai_chat.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            result = ai_chat._call_llm([{"role": "user", "content": "hi"}])
            assert result["content"] == "ok"
            mock_req.post.assert_called_once()

    def test_ai_diagnosis_rejects_private_base_url(self):
        from app.services.ai_diagnosis import _call_llm
        with pytest.raises(ValueError, match="base_url 不安全"):
            _call_llm(_cfg(base_url="http://169.254.169.254/v1"), "sys", "user")

    def test_ai_diagnosis_no_request_made_when_unsafe(self):
        from app.services.ai_diagnosis import _call_llm
        with patch("requests.post") as mock_post:
            with pytest.raises(ValueError):
                _call_llm(_cfg(base_url="http://10.0.0.5/v1"), "sys", "user")
            mock_post.assert_not_called()


def _cfg(**over):
    base = {
        "base_url": PUBLIC_URL,
        "api_key": "sk-test",
        "model_id": "test-model",
        "name": "TestProvider",
        "max_tokens": 8000,
    }
    base.update(over)
    return base
