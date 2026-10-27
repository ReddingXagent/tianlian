"""
AI 模型配置 API 鉴权矩阵缺口测试

补充 test_ai_model_config.py 未覆盖的鉴权路径（端点本身已被那里覆盖 CRUD/422/500）：
- 非 admin 角色（engineer / viewer）访问 → 403（require_role("admin") 真实缺口）
- 匿名访问 → 401 的正确写法（用 anon_client）

注：test_ai_model_config.py 中 test_*_requires_auth 三个用例误用了 `client` fixture
（conftest 里 client 默认注入 admin token），故匿名场景实际返回 200 而非 401，长期失败。
本文件用 `anon_client` 给出匿名拒绝的正确覆盖，详见 test_*_anonymous_rejected。
"""
import pytest


@pytest.fixture(autouse=True)
def preserve_model_config(monkeypatch):
    """禁用 model_manager 落盘 + 用例后恢复内存配置，避免污染全局单例。"""
    from app.services.ai_model_config import model_manager
    import copy
    original = copy.deepcopy(model_manager.config)
    monkeypatch.setattr(model_manager, "_save", lambda: None)
    yield
    model_manager.config = original


def _login(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    token = r.json().get("data", {}).get("token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


def _provider(**over):
    base = {
        "provider": "llm_generic",
        "model_id": "gpt-test",
        "name": "TEST-MODEL",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-1234567890abcdef1234567890",
        "context_window": 128000,
        "max_tokens": 8192,
        "enabled": True,
    }
    base.update(over)
    return base


_FULL_BODY = {
    "providers": [_provider()],
    "task_mappings": {"chat_general": "TEST-MODEL"},
    "fallback_strategy": "next_available",
}


# ───────────────────────── 非 admin → 403 ─────────────────────────


def test_get_config_forbidden_for_engineer(client, seed_users):
    """engineer 角色 GET 配置 → 403（require_role('admin')）"""
    headers = _login(client, "engineer1", "eng123")
    resp = client.get("/api/v1/ai-model_config", headers=headers)
    assert resp.status_code == 403


def test_get_config_forbidden_for_viewer(client, seed_users):
    """viewer 角色 GET 配置 → 403"""
    headers = _login(client, "viewer1", "view123")
    resp = client.get("/api/v1/ai-model_config", headers=headers)
    assert resp.status_code == 403


def test_update_full_config_forbidden_for_engineer(client, seed_users):
    """engineer 角色 PUT 全量配置 → 403"""
    headers = _login(client, "engineer1", "eng123")
    resp = client.put("/api/v1/ai-model_config", json=_FULL_BODY, headers=headers)
    assert resp.status_code == 403


def test_update_providers_forbidden_for_viewer(client, seed_users):
    """viewer 角色 PUT providers → 403"""
    headers = _login(client, "viewer1", "view123")
    resp = client.put("/api/v1/ai-model_config/providers",
                      json=[_provider()], headers=headers)
    assert resp.status_code == 403


def test_update_task_mappings_forbidden_for_engineer(client, seed_users):
    """engineer 角色 PUT task-mappings → 403"""
    headers = _login(client, "engineer1", "eng123")
    resp = client.put("/api/v1/ai-model_config/task-mappings",
                      json={"mappings": {"chat_general": "TEST-MODEL"}}, headers=headers)
    assert resp.status_code == 403


# ───────────────────────── 匿名 → 401（anon_client 正确写法） ─────────────────────────


def test_get_config_anonymous_rejected(anon_client):
    """匿名（无 token）GET → 401（用 anon_client，对比旧测试误用 client）"""
    resp = anon_client.get("/api/v1/ai-model_config")
    assert resp.status_code == 401


def test_update_full_config_anonymous_rejected(anon_client):
    """匿名（无 token）PUT 全量 → 401"""
    resp = anon_client.put("/api/v1/ai-model_config", json=_FULL_BODY)
    assert resp.status_code == 401


# ───────────────────────── 掩码哨兵防回写 (卡 7ada32c8) ─────────────────────────


class TestMaskedKeySentinel:
    """GET 回填掩码 api_key 再 PUT 时，不得覆盖真实密钥。"""

    @pytest.fixture(autouse=True)
    def _fake_dns(self, monkeypatch):
        """SSRF 校验需解析 base_url 主机名; 测试环境无 DNS, 伪造解析为公网 IP。"""
        import ipaddress
        import socket
        from app.core import url_safety
        real = socket.getaddrinfo

        def fake(host, *a, **kw):
            try:
                ipaddress.ip_address(host)
                return real(host, *a, **kw)
            except ValueError:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake)

    def _seed(self):
        from app.services.ai_model_config import model_manager
        model_manager.config["providers"] = [_provider()]
        return model_manager

    def test_put_full_config_masked_key_preserved(self, client):
        """PUT 全量: 掩码形态 api_key 回传 → 保留存量真实 key。"""
        mm = self._seed()
        masked = mm.to_config_dict()["providers"][0]["api_key"]
        assert masked.endswith("***")
        body = {**_FULL_BODY, "providers": [_provider(api_key=masked)]}
        resp = client.put("/api/v1/ai-model_config", json=body)
        assert resp.status_code == 200
        assert mm.config["providers"][0]["api_key"] == "sk-1234567890abcdef1234567890"

    def test_put_providers_masked_key_preserved(self, client):
        """PUT /providers: 掩码形态 api_key 回传 → 保留存量真实 key。"""
        mm = self._seed()
        masked = mm.to_config_dict()["providers"][0]["api_key"]
        resp = client.put("/api/v1/ai-model_config/providers",
                          json=[_provider(api_key=masked)])
        assert resp.status_code == 200
        assert mm.config["providers"][0]["api_key"] == "sk-1234567890abcdef1234567890"

    def test_put_real_key_updates(self, client):
        """PUT 真实新 key → 正常生效。"""
        mm = self._seed()
        resp = client.put("/api/v1/ai-model_config",
                          json={**_FULL_BODY, "providers": [_provider(api_key="sk-brand-new-key-999")]})
        assert resp.status_code == 200
        assert mm.config["providers"][0]["api_key"] == "sk-brand-new-key-999"

    def test_put_short_masked_key_preserved(self, client):
        """短 key (≤12) 掩码为整体 "***" → 回传同样保留存量。"""
        mm = self._seed()
        mm.config["providers"][0]["api_key"] = "short-key-1"
        assert mm.to_config_dict()["providers"][0]["api_key"] == "***"
        resp = client.put("/api/v1/ai-model_config/providers",
                          json=[_provider(api_key="***")])
        assert resp.status_code == 200
        assert mm.config["providers"][0]["api_key"] == "short-key-1"
