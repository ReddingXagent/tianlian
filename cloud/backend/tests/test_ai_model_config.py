"""
AI 模型配置管理 API 测试

覆盖: /api/v1/ai-model_config/*
- GET  获取配置（API Key 脱敏）
- PUT  全量更新 / Provider 更新 / 任务映射更新

注意: model_manager 是全局单例且 _save() 会写真实 JSON 文件，
      测试中 monkeypatch _save 并备份/恢复 config，避免污染。
"""
import pytest


@pytest.fixture(autouse=True)
def preserve_model_config(monkeypatch):
    """每个用例前后：禁用落盘 + 备份/恢复内存配置"""
    from app.services.ai_model_config import model_manager
    import copy
    original = copy.deepcopy(model_manager.config)
    monkeypatch.setattr(model_manager, "_save", lambda: None)
    yield
    model_manager.config = original


@pytest.fixture(autouse=True)
def _fake_public_dns(monkeypatch):
    """api.example.com 本机不可解析; SSRF 校验按公网 IP 放行(确定性)。"""
    import socket
    from app.core import url_safety
    real = socket.getaddrinfo
    def fake(host, *a, **kw):
        try:
            return real(host, *a, **kw)
        except (socket.gaierror, socket.error):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake)


def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
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


def test_get_config_structure(client, seed_users):
    headers = _auth(client)
    resp = client.get("/api/v1/ai-model_config", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "providers" in data
    assert "task_mappings" in data
    assert "fallback_strategy" in data
    assert isinstance(data["providers"], list)


def test_update_full_config_and_mask_apikey(client, seed_users):
    headers = _auth(client)
    resp = client.put("/api/v1/ai-model_config", json={
        "providers": [_provider()],
        "task_mappings": {"chat_general": "TEST-MODEL"},
        "fallback_strategy": "next_available",
    }, headers=headers)
    assert resp.status_code == 200
    providers = resp.json()["data"]["providers"]
    assert any(p["name"] == "TEST-MODEL" for p in providers)
    # api_key 被脱敏
    p = [p for p in providers if p["name"] == "TEST-MODEL"][0]
    assert "***" in p["api_key"]
    assert "sk-1234567890abcdef1234567890" not in p["api_key"]


def test_update_providers(client, seed_users):
    headers = _auth(client)
    resp = client.put("/api/v1/ai-model_config/providers",
                      json=[_provider(name="P-A"), _provider(name="P-B", enabled=False)],
                      headers=headers)
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["data"]["providers"]]
    assert "P-A" in names and "P-B" in names


def test_update_task_mappings(client, seed_users):
    headers = _auth(client)
    resp = client.put("/api/v1/ai-model_config/task-mappings",
                      json={"mappings": {"chat_general": "TEST-MODEL"}},
                      headers=headers)
    assert resp.status_code == 200
    mappings = resp.json()["data"]["task_mappings"]
    assert mappings.get("chat_general") == "TEST-MODEL"


def test_update_task_mappings_ignores_unknown_task(client, seed_users):
    """未知 task_type 被静默忽略，不影响已知映射"""
    headers = _auth(client)
    client.put("/api/v1/ai-model_config/task-mappings",
               json={"mappings": {"chat_general": "KNOWN"}},
               headers=headers)
    resp = client.put("/api/v1/ai-model_config/task-mappings",
                      json={"mappings": {"unknown_task": "X"}},
                      headers=headers)
    assert resp.status_code == 200
    mappings = resp.json()["data"]["task_mappings"]
    assert mappings.get("chat_general") == "KNOWN"
    assert "unknown_task" not in mappings


def test_ai_model_config_requires_auth(anon_client):
    resp = anon_client.get("/api/v1/ai-model_config")
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────
# 异常 / 边界分支补全：每个 PUT 端点 1 正常 + 1 异常/边界
# ─────────────────────────────────────────────────────────────

def test_update_full_config_save_error_returns_500(client, seed_users, monkeypatch):
    """PUT 全量更新：model_manager._save 抛异常时返回 500（覆盖 except 分支）"""
    from app.services.ai_model_config import model_manager

    def _boom():
        raise RuntimeError("disk full")

    # autouse fixture 已把 _save 设为 noop；这里覆盖为抛异常，触发端点 try/except
    monkeypatch.setattr(model_manager, "_save", _boom)
    headers = _auth(client)
    resp = client.put("/api/v1/ai-model_config", json={
        "providers": [_provider()],
        "task_mappings": {"chat_general": "TEST-MODEL"},
    }, headers=headers)
    assert resp.status_code == 500
    # 安全：异常原文(disk full)不得泄露到响应体，须返回通用消息
    assert "disk full" not in resp.json().get("detail", "")
    assert resp.json().get("detail") == "内部服务器错误"


def test_update_full_config_missing_task_mappings_returns_422(client, seed_users):
    """PUT 全量更新：缺必填 task_mappings 字段 → 422"""
    headers = _auth(client)
    resp = client.put("/api/v1/ai-model_config", json={
        "providers": [_provider()],
        # 缺 task_mappings
    }, headers=headers)
    assert resp.status_code == 422


def test_update_providers_empty_list(client, seed_users):
    """PUT providers：空列表是合法输入 → 200 且 providers 被清空（边界）"""
    headers = _auth(client)
    resp = client.put("/api/v1/ai-model_config/providers", json=[], headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["providers"] == []


def test_update_providers_invalid_item_returns_422(client, seed_users):
    """PUT providers：单个 provider 缺必填字段 → 422"""
    headers = _auth(client)
    resp = client.put("/api/v1/ai-model_config/providers",
                      json=[{"provider": "llm_generic"}],  # 缺 model_id / name / base_url
                      headers=headers)
    assert resp.status_code == 422


def test_update_providers_requires_auth(anon_client):
    """PUT providers：无 token（带合法 body）→ 401"""
    resp = anon_client.put("/api/v1/ai-model_config/providers", json=[_provider()])
    assert resp.status_code == 401


def test_update_task_mappings_missing_mappings_returns_422(client, seed_users):
    """PUT task-mappings：缺必填 mappings 字段 → 422"""
    headers = _auth(client)
    resp = client.put("/api/v1/ai-model_config/task-mappings",
                      json={"foo": "bar"},  # 缺 mappings
                      headers=headers)
    assert resp.status_code == 422


def test_update_task_mappings_requires_auth(anon_client):
    """PUT task-mappings：无 token（带合法 body）→ 401"""
    resp = anon_client.put("/api/v1/ai-model_config/task-mappings",
                      json={"mappings": {"chat_general": "TEST-MODEL"}})
    assert resp.status_code == 401
