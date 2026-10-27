"""
天链助手 AI 对话 API 测试

覆盖:
- POST /api/v1/chat            通用对话（mock chat_service 避免外部LLM调用）
- GET  /api/v1/chat/voice-config  语音配置
- POST /api/v1/chat/stt        语音识别（未配置provider → 业务码400）
- POST /api/v1/chat/tts        语音合成（未配置provider → 业务码400）

卡 ad02f1ea: chat 端点不得阻塞事件循环 —— 同步 LLM 调用(requests, timeout=120)
必须移出事件循环线程。async def 路由体跑在事件循环线程内, LLM 慢/挂会冻结同
worker 全部 API(含 /health); 同步 def 路由由 FastAPI 自动放线程池执行, 是
diagnosis 系列的既有模式。以下用 thread-id + running-loop 双重观测锚定。
"""
import asyncio

import pytest


def _fake_chat_answer(**kwargs):
    """模拟非流式对话返回"""
    return {
        "answer": "这是测试回答",
        "confidence": 0.9,
        "sources": ["知识库A"],
        "actions": [{"label": "查看", "url": "/devices/1"}],
        "needs_human": False,
    }


def _login_headers(client, username="admin", password="admin123"):
    """登录换取 Bearer token (依赖 seed_users 注入的 admin)"""
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"login 失败: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def test_chat_voice_config(client):
    """GET /chat/voice-config 返回可插拔语音配置"""
    resp = client.get("/api/v1/chat/voice-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"]
    assert isinstance(body["available_providers"], list)
    assert "web_speech" in body["available_providers"]


def test_chat_success(client, seed_users, monkeypatch):
    """非流式对话返回回答内容"""
    monkeypatch.setattr("app.api.v1.chat.chat_service", _fake_chat_answer)
    resp = client.post("/api/v1/chat", json={"message": "充电桩故障如何排查?"}, headers=_login_headers(client))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["answer"] == "这是测试回答"
    assert data["confidence"] == 0.9
    assert data["sources"] == ["知识库A"]
    assert data["needs_human"] is False


def test_chat_with_history(client, seed_users, monkeypatch):
    """带历史记录的对话正常调用"""
    captured = {}

    def _capture(**kwargs):
        captured["history"] = kwargs.get("history")
        return {"answer": "ok", "confidence": 0.5}

    monkeypatch.setattr("app.api.v1.chat.chat_service", _capture)
    resp = client.post("/api/v1/chat", json={
        "message": "继续",
        "history": [{"role": "user", "content": "之前的问题"}],
    }, headers=_login_headers(client))
    assert resp.status_code == 200
    assert captured["history"] is not None


def test_chat_empty_message_rejected(client, seed_users):
    """空消息触发 422 校验错误（鉴权通过后由 body 校验拦截）"""
    resp = client.post("/api/v1/chat", json={"message": ""}, headers=_login_headers(client))
    assert resp.status_code == 422


def test_chat_stream_response(client, seed_users, monkeypatch):
    """stream=True 返回流式响应（fallback 生成器）"""
    monkeypatch.setattr("app.api.v1.chat.chat_service", _fake_chat_answer)
    resp = client.post("/api/v1/chat", json={"message": "你好", "stream": True}, headers=_login_headers(client))
    assert resp.status_code == 200
    assert "x-ndjson" in resp.headers.get("content-type", "")
    # 流式body非空
    assert resp.text.strip()


# ---- 卡 ad02f1ea: 事件循环阻塞修复 —— chat 同步 LLM 调用必须移出事件循环线程 ----


def _off_loop_detector(**kwargs):
    """观测锚点: 记录 chat_service 执行时是否处于事件循环线程。

    事件循环线程上 asyncio.get_running_loop() 成功; 线程池工作线程上抛 RuntimeError。
    (不能用 thread id 对比: TestClient 经 blocking portal 在独立线程跑事件循环,
    测试主线程 id 与 app 线程 id 天然不同, 比较无区分度。)
    """
    try:
        asyncio.get_running_loop()
        _off_loop_detector.on_loop = True
    except RuntimeError:
        _off_loop_detector.on_loop = False
    return _fake_chat_answer()


_off_loop_detector.on_loop = None


def test_chat_endpoint_runs_off_event_loop_thread(client, seed_users, monkeypatch):
    """非流式: chat_service 必须在线程池工作线程执行, 而非事件循环线程。

    async def 路由的函数体在事件循环线程内执行 —— 同步 requests.post(timeout=120)
    在此直接调用会阻塞事件循环最长 120s, 同 worker 全部 API(含 /health)冻结。
    同步 def 路由由 FastAPI 自动调度到 anyio 工作线程池, 与 diagnosis 系列一致。
    """
    monkeypatch.setattr("app.api.v1.chat.chat_service", _off_loop_detector)
    resp = client.post("/api/v1/chat", json={"message": "充电桩故障如何排查?"}, headers=_login_headers(client))
    assert resp.status_code == 200
    assert resp.json()["data"]["answer"] == "这是测试回答"
    assert _off_loop_detector.on_loop is False, (
        "chat_service 在事件循环线程内被同步调用 —— "
        "同步 LLM 调用(requests, timeout=120)会阻塞事件循环(卡 ad02f1ea)"
    )


def test_chat_stream_endpoint_runs_off_event_loop_thread(client, seed_users, monkeypatch):
    """流式: chat_service(stream=True) 同样必须移出事件循环线程; SSE ndjson 输出格式不变。

    修复前该端点在事件循环线程内完成 RAG 检索 + requests.post(timeout=120) 建立
    流连接, LLM 慢/挂时 /health 等全部 API 冻结。修复后由线程池执行 chat_service,
    stream_generator(sync generator)仍由 Starlette 自动在线程池迭代。
    """
    monkeypatch.setattr("app.api.v1.chat.chat_service", _off_loop_detector)
    resp = client.post("/api/v1/chat", json={"message": "你好", "stream": True}, headers=_login_headers(client))
    assert resp.status_code == 200
    assert "x-ndjson" in resp.headers.get("content-type", "")
    assert _off_loop_detector.on_loop is False, (
        "stream=True 分支的 chat_service 在事件循环线程内被同步调用 (卡 ad02f1ea)"
    )
    # SSE 输出格式不变: chunk/done 两类 JSON 行 + 换行符 (fallback gen 分支)
    lines = resp.text.strip().splitlines()
    assert lines, "流式响应体不得为空"
    assert lines[-1] == '{"type":"done"}'
    for line in lines[:-1]:
        assert line.startswith('{"type":"chunk","content":"')


def test_chat_stt_no_provider(client):
    """未配置 STT provider 返回业务码 400"""
    resp = client.post("/api/v1/chat/stt", json={
        "audio_base64": "data",
        "format": "wav",
        "sample_rate": 16000,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400


def test_chat_tts_no_provider(client):
    """未配置 TTS provider 返回业务码 400"""
    resp = client.post("/api/v1/chat/tts", json={"text": "你好"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400


# ---- cloud_provider 转发路径：必须走异步 httpx，不得用同步 requests 阻塞 event loop ----


class _FakeResp:
    """模拟 httpx.Response：json() + 全量缓冲 content（卡 c8c04542 缓冲语义）"""
    def __init__(self, json_payload=None, content=b""):
        self._json = json_payload
        self.content = content

    def json(self):
        return self._json or {}


class _FakeAsyncClient:
    """模拟 httpx.AsyncClient（async context manager + post 协程）"""
    def __init__(self, resp):
        self._resp = resp
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        return self._resp


def _patch_asyncclient(monkeypatch, resp):
    fake = _FakeAsyncClient(resp)
    # mock 全局 httpx.AsyncClient；实现须以 `import httpx` + httpx.AsyncClient() 形式调用方可命中
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **kw: fake)
    return fake


def _block_sync_requests(*a, **k):
    """阻断同步 requests：async 端点内禁止使用，同时防止测试真连外网。"""
    raise AssertionError("async 端点不得使用同步 requests（必须走 httpx 异步）")


def test_chat_stt_cloud_provider_uses_async_httpx(client, monkeypatch):
    """STT 云服务商路径走异步 httpx 转发，保留 timeout=30，不连外网"""
    monkeypatch.setenv("STT_PROVIDER", "cloud-a")
    monkeypatch.setenv("ALIYUN_ASR_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", _block_sync_requests)  # 防退回同步 requests
    fake = _patch_asyncclient(monkeypatch, _FakeResp(json_payload={"result": "你好世界"}))

    resp = client.post("/api/v1/chat/stt", json={
        "audio_base64": "AAAA", "format": "wav", "sample_rate": 16000,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["text"] == "你好世界"
    # 确实走了异步 httpx，且 timeout 保留为 30
    assert len(fake.post_calls) == 1
    assert fake.post_calls[0]["timeout"] == 30
    assert "cloud_providercs.com" in fake.post_calls[0]["url"]


def test_chat_tts_cloud_provider_streams_async_httpx(client, monkeypatch):
    """TTS 云服务商路径走异步 httpx 并缓冲回灌 audio/wav 响应（卡 c8c04542: read 超时 60s）"""
    monkeypatch.setenv("TTS_PROVIDER", "cloud-a")
    monkeypatch.setenv("ALIYUN_TTS_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", _block_sync_requests)  # 防退回同步 requests
    audio = b"AUDIODATA" * 128
    fake = _patch_asyncclient(monkeypatch, _FakeResp(content=audio))

    resp = client.post("/api/v1/chat/tts", json={"text": "你好", "voice": "default", "speed": 1.0})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/wav")
    assert resp.content == audio
    # 确实走了异步 httpx，且 read 超时提升到 60s（卡 c8c04542）
    assert len(fake.post_calls) == 1
    assert fake.post_calls[0]["timeout"].read == 60.0
    assert "cloud_providercs.com" in fake.post_calls[0]["url"]
