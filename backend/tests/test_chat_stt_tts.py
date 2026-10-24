"""
卡 c8c04542: chat.py TTS/STT HTTP 调用缺陷修复测试

覆盖:
- TTS cloud_provider 分支: 缓冲式返回普通 audio/wav Response（client 关闭后仍有效，
  不再依赖 httpx _content 缓冲的侥幸路径）
- TTS 超时提升到 60s（connect/read 分离），2000 字合成不再被 30s 掐断
- TTS 上游超时/异常 → 业务码 500
- STT audio_base64 加 max_length=10_000_000，超长 payload 422，杜绝无界内存
"""
import httpx
import pytest


class _FakeResp:
    def __init__(self, *, json_payload=None, content=b"", exc=None):
        self._json = json_payload
        self.content = content
        self._exc = exc

    def json(self):
        if self._exc:
            raise self._exc
        return self._json

    async def aiter_bytes(self):
        yield self.content


class _FakeAsyncClient:
    def __init__(self, resp):
        self._resp = resp
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        if isinstance(self._resp._exc, Exception):
            raise self._resp._exc
        return self._resp


def _patch_asyncclient(monkeypatch, resp):
    fake = _FakeAsyncClient(resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **kw: fake)
    return fake


def _login_headers(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, f"login 失败: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


# ---------- TTS: 缓冲式返回 + 超时提升 ----------

def test_tts_returns_buffered_audio_response(client, monkeypatch):
    """TTS 全量缓冲后返回普通 Response，client 已关闭但 content 有效"""
    monkeypatch.setenv("TTS_PROVIDER", "cloud-a")
    monkeypatch.setenv("ALIYUN_TTS_API_KEY", "test-key")
    audio = b"WAVDATA" * 512
    fake = _patch_asyncclient(monkeypatch, _FakeResp(content=audio))

    resp = client.post("/api/v1/chat/tts", json={"text": "你好"}, headers=_login_headers(client))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/wav")
    assert resp.content == audio
    assert len(fake.post_calls) == 1
    assert "cloud_providercs.com" in fake.post_calls[0]["url"]


def test_tts_timeout_raised_to_60s(client, monkeypatch):
    """TTS 超时提升：read=60s（connect 10s 分离），2000 字合成不再被 30s 掐断"""
    monkeypatch.setenv("TTS_PROVIDER", "cloud-a")
    monkeypatch.setenv("ALIYUN_TTS_API_KEY", "test-key")
    fake = _patch_asyncclient(monkeypatch, _FakeResp(content=b"audio"))

    client.post("/api/v1/chat/tts", json={"text": "你好"}, headers=_login_headers(client))
    timeout = fake.post_calls[0]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 60.0
    assert timeout.connect == 10.0


def test_tts_upstream_timeout_returns_500(client, monkeypatch):
    """TTS 上游超时 → 业务码 500，不抛裸异常"""
    monkeypatch.setenv("TTS_PROVIDER", "cloud-a")
    monkeypatch.setenv("ALIYUN_TTS_API_KEY", "test-key")
    _patch_asyncclient(monkeypatch, _FakeResp(exc=httpx.TimeoutException("upstream timeout")))

    resp = client.post("/api/v1/chat/tts", json={"text": "你好"}, headers=_login_headers(client))
    assert resp.status_code == 200
    assert resp.json()["code"] == 500


# ---------- STT: payload 上限 ----------

def test_stt_oversized_audio_rejected_422(client, monkeypatch, seed_users):
    """STT audio_base64 超过 10MB 上限 → 422，禁止无界内存放大"""
    monkeypatch.setenv("STT_PROVIDER", "cloud-a")
    monkeypatch.setenv("ALIYUN_ASR_API_KEY", "test-key")
    called = []

    def _must_not_call(*a, **k):
        called.append(1)
        raise AssertionError("超长 payload 不应触达上游")

    monkeypatch.setattr("httpx.AsyncClient", _must_not_call)

    resp = client.post("/api/v1/chat/stt", json={
        "audio_base64": "A" * 10_000_001,
    }, headers=_login_headers(client))
    assert resp.status_code == 422
    assert not called


def test_stt_within_limit_still_works(client, monkeypatch):
    """STT 合法长度 payload 正常转发（回归守卫）"""
    monkeypatch.setenv("STT_PROVIDER", "cloud-a")
    monkeypatch.setenv("ALIYUN_ASR_API_KEY", "test-key")
    fake = _patch_asyncclient(monkeypatch, _FakeResp(json_payload={"result": "回归通过"}))

    resp = client.post("/api/v1/chat/stt", json={
        "audio_base64": "QUJD", "format": "wav", "sample_rate": 16000,
    }, headers=_login_headers(client))
    assert resp.status_code == 200
    assert resp.json()["data"]["text"] == "回归通过"
    assert len(fake.post_calls) == 1
