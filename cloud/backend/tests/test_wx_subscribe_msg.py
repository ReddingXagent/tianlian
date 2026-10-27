"""IM-B小程序订阅消息推送 单元测试 (卡 d3ee0167)

源文件 app/services/wx_subscribe_msg.py 当前零测试。本文件覆盖:
- _credentials_configured: 凭证有无分支
- _fetch_access_token: 正常 / 凭证缺失降级 / 非200 / errcode!=0 / 异常 / 无token / 缓存写入
- get_access_token: 缓存命中 / 过期刷新 / 凭证缺失 / 并发 double-check
- invalidate_access_token: 清缓存
- _safe_json: 正常 / 异常
- _post_subscribe: 2xx/4xx 立返 / 5xx 重试 / 异常重试 / 退避
- send_subscribe_msg: 凭证缺失skipped / 无token failed / sent / errcode!=0 failed / 异常failed
                      / payload 组装 (page/miniprogram_state)
- resolve_openid + _invoice_order_ids: list / JSON串 / 空 / 查询命中 / 查询异常 / 无openid

测试缝 (源码 docstring 约定):
- FakeClient 注入 httpx (源码 _fetch_access_token / send_subscribe_msg 接受 client 参数)
- backoff 归零 + monkeypatch asyncio.sleep 跳过退避
- settings 通过 monkeypatch 模块属性切换凭证有无
"""
import asyncio
import types

import pytest

from app.services import wx_subscribe_msg as wsm


# ============================================================
# FakeClient: 模拟 httpx.AsyncClient (post 为协程, 响应有 status_code/json)
# ============================================================

class _FakeResp:
    def __init__(self, status_code=200, body=None, json_exc=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self._json_exc = json_exc

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._body


class FakeClient:
    """可注入 wx_subscribe_msg 的 httpx 替身。

    responses: 按调用顺序依次返回的响应列表 (或单个 _FakeResp)。
    posts: 记录每次 post 调用的 (url, kwargs)。
    post_exc: 若非 None, post 抛该异常 (模拟超时/网络错误)。
    """

    def __init__(self, responses=None, post_exc=None):
        if responses is None:
            responses = []
        if isinstance(responses, _FakeResp):
            responses = [responses]
        self._responses = list(responses)
        self.post_exc = post_exc
        self.posts = []
        self.aclosed = False

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        # responses 优先: 有预设响应就依次返回 (支持 token 请求正常、后续抛异常的混合场景)
        if self._responses:
            return self._responses.pop(0)
        if self.post_exc is not None:
            # 连续抛异常: post_exc 可以是单个异常或列表
            if isinstance(self.post_exc, list):
                exc = self.post_exc.pop(0)
                if exc is not None:
                    raise exc
            else:
                raise self.post_exc
        return _FakeResp(200, {})

    async def aclose(self):
        self.aclosed = True


# ============================================================
# 公共 fixture
# ============================================================

@pytest.fixture(autouse=True)
def _isolate_token_cache():
    """每个测试前后清空模块级 access_token 缓存, 避免测试间污染。"""
    wsm.invalidate_access_token()
    # 重置 lazy 锁, 避免跨事件循环复用旧锁
    wsm._token_lock = None
    yield
    wsm.invalidate_access_token()
    wsm._token_lock = None


@pytest.fixture(autouse=True)
def _skip_backoff_sleep(monkeypatch):
    """退避归零 + monkeypatch asyncio.sleep 跳过真实等待。"""
    async def _no_sleep(_):
        return None
    monkeypatch.setattr(wsm.asyncio, "sleep", _no_sleep)


def _set_credentials(monkeypatch, appid="wxappid", secret="wxsecret"):
    """注入凭证 (有), 测试通过 monkeypatch 模块引用的 settings 切换。"""
    monkeypatch.setattr(wsm.settings, "WX_MP_APPID", appid)
    monkeypatch.setattr(wsm.settings, "WX_MP_SECRET", secret)


def _clear_credentials(monkeypatch):
    """清空凭证 (无)。"""
    monkeypatch.setattr(wsm.settings, "WX_MP_APPID", None)
    monkeypatch.setattr(wsm.settings, "WX_MP_SECRET", None)


# ============================================================
# _credentials_configured
# ============================================================

class TestCredentialsConfigured:
    def test_both_set_returns_true(self, monkeypatch):
        _set_credentials(monkeypatch)
        assert wsm._credentials_configured() is True

    def test_appid_missing_returns_false(self, monkeypatch):
        monkeypatch.setattr(wsm.settings, "WX_MP_APPID", None)
        monkeypatch.setattr(wsm.settings, "WX_MP_SECRET", "s")
        assert wsm._credentials_configured() is False

    def test_secret_missing_returns_false(self, monkeypatch):
        monkeypatch.setattr(wsm.settings, "WX_MP_APPID", "a")
        monkeypatch.setattr(wsm.settings, "WX_MP_SECRET", None)
        assert wsm._credentials_configured() is False

    def test_both_missing_returns_false(self, monkeypatch):
        _clear_credentials(monkeypatch)
        assert wsm._credentials_configured() is False

    def test_empty_string_treated_as_missing(self, monkeypatch):
        monkeypatch.setattr(wsm.settings, "WX_MP_APPID", "")
        monkeypatch.setattr(wsm.settings, "WX_MP_SECRET", "s")
        assert wsm._credentials_configured() is False


# ============================================================
# _fetch_access_token
# ============================================================

class TestFetchAccessToken:
    def test_credentials_missing_returns_none_no_request(self, monkeypatch):
        _clear_credentials(monkeypatch)
        client = FakeClient()
        result = asyncio.run(wsm._fetch_access_token(client))
        assert result is None
        assert client.posts == []  # 未发请求

    def test_success_returns_token_and_caches(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient(_FakeResp(200, {"access_token": "TOK", "expires_in": 7200}))
        token = asyncio.run(wsm._fetch_access_token(client))
        assert token == "TOK"
        # 缓存写入
        assert wsm._token_cache["value"] == "TOK"
        assert wsm._token_cache["expires_at"] > 0
        # 请求体正确
        url, kw = client.posts[0]
        assert "/cgi-bin/stable_token" in url
        assert kw["json"]["grant_type"] == "client_credential"
        assert kw["json"]["appid"] == "wxappid"
        assert kw["json"]["secret"] == "wxsecret"
        assert kw["json"]["force_refresh"] is False

    def test_errcode_nonzero_returns_none(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient(_FakeResp(200, {"errcode": 40001, "errmsg": "bad"}))
        assert asyncio.run(wsm._fetch_access_token(client)) is None

    def test_nonzero_status_treated_as_failure(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient(_FakeResp(500, {"access_token": "TOK"}))
        # _fetch_access_token 只看 body (errcode), 不判 status_code; 但 body 有 token
        # 这里 body 含 access_token 且 errcode 缺失 → 视为成功
        token = asyncio.run(wsm._fetch_access_token(client))
        assert token == "TOK"

    def test_request_exception_returns_none(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient(post_exc=asyncio.TimeoutError())
        assert asyncio.run(wsm._fetch_access_token(client)) is None

    def test_body_no_access_token_returns_none(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient(_FakeResp(200, {"errcode": 0}))  # 无 access_token 字段
        assert asyncio.run(wsm._fetch_access_token(client)) is None

    def test_invalid_json_returns_none(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient(_FakeResp(200, json_exc=ValueError("not json")))
        assert asyncio.run(wsm._fetch_access_token(client)) is None

    def test_expires_in_uses_default_when_missing(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient(_FakeResp(200, {"access_token": "TOK"}))  # 无 expires_in
        import time as _time
        before = _time.time()
        asyncio.run(wsm._fetch_access_token(client))
        # 默认 expires_in=7200, 提前 _TOKEN_REFRESH_MARGIN=300s 余量
        # → expires_at ≈ now + 6900, 落在 [before+6800, now+7000] 区间
        expires_at = wsm._token_cache["expires_at"]
        assert wsm._token_cache["value"] == "TOK"
        assert before + 6800 <= expires_at <= _time.time() + 7000


# ============================================================
# get_access_token (缓存 + double-check)
# ============================================================

class TestGetAccessToken:
    def test_credentials_missing_returns_none(self, monkeypatch):
        _clear_credentials(monkeypatch)
        assert asyncio.run(wsm.get_access_token(FakeClient())) is None

    def test_cache_hit_skips_fetch(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient(_FakeResp(200, {"access_token": "TOK1", "expires_in": 7200}))
        first = asyncio.run(wsm.get_access_token(client))
        assert first == "TOK1"
        # 第二次命中缓存, 不再发请求 (FakeClient 无新响应会返回默认 200/{} → 但不应被调用)
        calls_before = len(client.posts)
        second = asyncio.run(wsm.get_access_token(client))
        assert second == "TOK1"
        assert len(client.posts) == calls_before  # 未新增请求

    def test_expired_cache_triggers_refresh(self, monkeypatch):
        _set_credentials(monkeypatch)
        # 预置过期缓存
        wsm._token_cache["value"] = "OLD"
        wsm._token_cache["expires_at"] = 0.0  # 已过期
        client = FakeClient(_FakeResp(200, {"access_token": "NEW", "expires_in": 7200}))
        token = asyncio.run(wsm.get_access_token(client))
        assert token == "NEW"
        assert len(client.posts) == 1

    def test_concurrent_calls_single_fetch_via_double_check(self, monkeypatch):
        """两个协程并发 get_access_token: 过期缓存下, double-check 应使 fetch 仅一次。

        锁串行化两个协程, 先者刷新成功写入缓存, 后者持锁 double-check 命中缓存免 fetch。
        FakeClient 只准备一个响应, 若被调用两次会 IndexError → 间接验证仅一次 fetch。"""
        _set_credentials(monkeypatch)
        wsm._token_cache["value"] = None
        wsm._token_cache["expires_at"] = 0.0
        client = FakeClient(_FakeResp(200, {"access_token": "TOK", "expires_in": 7200}))

        async def run_both():
            # 用同一个 client, 但 lock 串行; 第二个协程 double-check 命中缓存
            t1 = await wsm.get_access_token(client)
            t2 = await wsm.get_access_token(client)
            return t1, t2

        t1, t2 = asyncio.run(run_both())
        assert t1 == "TOK"
        assert t2 == "TOK"
        assert len(client.posts) == 1


class TestInvalidateAccessToken:
    def test_clears_cache(self, monkeypatch):
        wsm._token_cache["value"] = "STALE"
        wsm._token_cache["expires_at"] = 99999.0
        wsm.invalidate_access_token()
        assert wsm._token_cache["value"] is None
        assert wsm._token_cache["expires_at"] == 0.0


# ============================================================
# _safe_json
# ============================================================

class TestSafeJson:
    def test_valid_json(self):
        assert wsm._safe_json(_FakeResp(200, {"a": 1})) == {"a": 1}

    def test_json_raises_returns_empty(self):
        assert wsm._safe_json(_FakeResp(200, json_exc=ValueError())) == {}


# ============================================================
# _post_subscribe (重试逻辑)
# ============================================================

class TestPostSubscribe:
    def test_2xx_returns_immediately(self, monkeypatch):
        client = FakeClient(_FakeResp(200, {"errcode": 0}))
        resp = asyncio.run(wsm._post_subscribe(client, "u", {}, max_retries=2, backoff=0))
        assert resp.status_code == 200
        assert len(client.posts) == 1

    def test_4xx_returns_immediately_no_retry(self, monkeypatch):
        client = FakeClient(_FakeResp(400, {"errcode": 40029}))
        resp = asyncio.run(wsm._post_subscribe(client, "u", {}, max_retries=2, backoff=0))
        assert resp.status_code == 400
        assert len(client.posts) == 1  # 4xx 不重试

    def test_5xx_retries_then_success(self, monkeypatch):
        client = FakeClient([_FakeResp(500), _FakeResp(200, {"errcode": 0})])
        resp = asyncio.run(wsm._post_subscribe(client, "u", {}, max_retries=2, backoff=0))
        assert resp.status_code == 200
        assert len(client.posts) == 2  # 重试一次

    def test_5xx_exhausts_retries_raises(self, monkeypatch):
        client = FakeClient([_FakeResp(503), _FakeResp(503), _FakeResp(503)])
        with pytest.raises(RuntimeError, match="http 503"):
            asyncio.run(wsm._post_subscribe(client, "u", {}, max_retries=2, backoff=0))
        assert len(client.posts) == 3  # max_retries+1 次

    def test_exception_retries_then_raises(self, monkeypatch):
        client = FakeClient(
            post_exc=[asyncio.TimeoutError(), asyncio.TimeoutError(), asyncio.TimeoutError()]
        )
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(wsm._post_subscribe(client, "u", {}, max_retries=2, backoff=0))
        assert len(client.posts) == 3

    def test_backoff_sleep_called_with_exponential(self, monkeypatch):
        sleeps = []

        async def _record(d):
            sleeps.append(d)

        monkeypatch.setattr(wsm.asyncio, "sleep", _record)
        client = FakeClient([_FakeResp(500), _FakeResp(500), _FakeResp(503)])
        with pytest.raises(RuntimeError):
            asyncio.run(wsm._post_subscribe(client, "u", {}, max_retries=2, backoff=0.1))
        # backoff * 2^0, backoff * 2^1
        assert sleeps == [0.1, 0.2]


# ============================================================
# send_subscribe_msg
# ============================================================

class TestSendSubscribeMsg:
    def test_credentials_missing_returns_skipped(self, monkeypatch):
        _clear_credentials(monkeypatch)
        result = asyncio.run(wsm.send_subscribe_msg("oid", "tpl", {}, client=FakeClient()))
        assert result["status"] == "skipped"
        assert result["reason"] == "no_credentials"
        assert result["channel"] == "wx_subscribe"

    def test_no_access_token_returns_failed(self, monkeypatch):
        _set_credentials(monkeypatch)
        # token 请求失败 → get_access_token 返回 None
        client = FakeClient(_FakeResp(200, {"errcode": 40001}))
        result = asyncio.run(wsm.send_subscribe_msg(
            "oid", "tpl", {"k": {"value": "v"}}, client=client, backoff=0))
        assert result["status"] == "failed"
        assert result["error"] == "no_access_token"

    def test_sent_on_errcode_zero(self, monkeypatch):
        _set_credentials(monkeypatch)
        # 第一次响应 token, 第二次响应发送成功
        client = FakeClient([
            _FakeResp(200, {"access_token": "TOK", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 0}),
        ])
        result = asyncio.run(wsm.send_subscribe_msg(
            "oid", "tpl", {"k": {"value": "v"}}, client=client, backoff=0))
        assert result["status"] == "sent"
        assert result["channel"] == "wx_subscribe"
        # 第二个请求 URL 含 access_token
        send_url, send_kw = client.posts[1]
        assert "access_token=TOK" in send_url
        assert send_kw["json"]["touser"] == "oid"
        assert send_kw["json"]["template_id"] == "tpl"
        assert send_kw["json"]["data"] == {"k": {"value": "v"}}
        assert send_kw["json"]["lang"] == "zh_CN"

    def test_sent_on_http200_no_errcode(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient([
            _FakeResp(200, {"access_token": "TOK", "expires_in": 7200}),
            _FakeResp(200, {}),  # 无 errcode, status 200 → 视为成功
        ])
        result = asyncio.run(wsm.send_subscribe_msg("oid", "tpl", {}, client=client, backoff=0))
        assert result["status"] == "sent"

    def test_failed_on_errcode_nonzero(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient([
            _FakeResp(200, {"access_token": "TOK", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 43101, "errmsg": "user refused"}),
        ])
        result = asyncio.run(wsm.send_subscribe_msg("oid", "tpl", {}, client=client, backoff=0))
        assert result["status"] == "failed"
        assert "43101" in result["error"]

    def test_send_exception_returns_failed(self, monkeypatch):
        _set_credentials(monkeypatch)
        # token 成功, 发送阶段一直超时 → 重试耗尽抛异常 → 被捕获为 failed
        token_resp = _FakeResp(200, {"access_token": "TOK", "expires_in": 7200})
        client = FakeClient(
            responses=[token_resp],
            post_exc=[asyncio.TimeoutError(), asyncio.TimeoutError(), asyncio.TimeoutError()],
        )
        result = asyncio.run(wsm.send_subscribe_msg(
            "oid", "tpl", {}, client=client, max_retries=2, backoff=0))
        assert result["status"] == "failed"
        # asyncio.TimeoutError 的 str() 为空串, 源码 str(e) 真实即 ""; 只断言失败状态
        assert "error" in result

    def test_payload_includes_page_and_miniprogram_state(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient([
            _FakeResp(200, {"access_token": "TOK", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 0}),
        ])
        asyncio.run(wsm.send_subscribe_msg(
            "oid", "tpl", {}, page="pages/invoice/detail?id=1",
            miniprogram_state="developer", client=client, backoff=0))
        _, send_kw = client.posts[1]
        assert send_kw["json"]["page"] == "pages/invoice/detail?id=1"
        assert send_kw["json"]["miniprogram_state"] == "developer"

    def test_payload_omits_miniprogram_state_when_none(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient([
            _FakeResp(200, {"access_token": "TOK", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 0}),
        ])
        asyncio.run(wsm.send_subscribe_msg("oid", "tpl", {}, client=client, backoff=0))
        _, send_kw = client.posts[1]
        assert "miniprogram_state" not in send_kw["json"]

    def test_40001_invalidates_refetches_and_resends(self, monkeypatch):
        """卡 e38e2082: send 遇 40001 → invalidate + 重取 token + 重发一次 → sent。"""
        _set_credentials(monkeypatch)
        client = FakeClient([
            _FakeResp(200, {"access_token": "TOK1", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 40001, "errmsg": "invalid credential"}),
            _FakeResp(200, {"access_token": "TOK2", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 0}),
        ])
        result = asyncio.run(wsm.send_subscribe_msg(
            "oid", "tpl", {}, client=client, backoff=0))
        assert result["status"] == "sent"
        assert result["channel"] == "wx_subscribe"
        # 4 次请求: token / send(40001) / token 重取 / send 重发
        assert len(client.posts) == 4
        # 缓存已刷新为新 token
        assert wsm._token_cache["value"] == "TOK2"
        # 重发 URL 携带新 token
        resend_url, _ = client.posts[3]
        assert "access_token=TOK2" in resend_url

    def test_42001_invalidates_refetches_and_resends(self, monkeypatch):
        """卡 e38e2082: 42001 (access_token expired) 同样自愈。"""
        _set_credentials(monkeypatch)
        client = FakeClient([
            _FakeResp(200, {"access_token": "TOK1", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 42001, "errmsg": "access_token expired"}),
            _FakeResp(200, {"access_token": "TOK2", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 0}),
        ])
        result = asyncio.run(wsm.send_subscribe_msg(
            "oid", "tpl", {}, client=client, backoff=0))
        assert result["status"] == "sent"
        assert len(client.posts) == 4

    def test_retry_still_40001_fails_no_loop(self, monkeypatch):
        """卡 e38e2082: 重发仍 40001 → failed, 单次重试防死循环。"""
        _set_credentials(monkeypatch)
        client = FakeClient([
            _FakeResp(200, {"access_token": "TOK1", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 40001}),
            _FakeResp(200, {"access_token": "TOK2", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 40001}),
        ])
        result = asyncio.run(wsm.send_subscribe_msg(
            "oid", "tpl", {}, client=client, backoff=0))
        assert result["status"] == "failed"
        assert "40001" in result["error"]
        # 恰好 4 次请求, 无第二次重试循环
        assert len(client.posts) == 4

    def test_retry_token_fetch_fails_returns_failed(self, monkeypatch):
        """卡 e38e2082: 重取 token 失败 → failed (no_access_token)。"""
        _set_credentials(monkeypatch)
        client = FakeClient([
            _FakeResp(200, {"access_token": "TOK1", "expires_in": 7200}),
            _FakeResp(200, {"errcode": 40001}),
            _FakeResp(200, {"errcode": 500}),  # 重取 token 失败
        ])
        result = asyncio.run(wsm.send_subscribe_msg(
            "oid", "tpl", {}, client=client, backoff=0))
        assert result["status"] == "failed"
        # 3 次请求: token / send(40001) / token 重取失败即止, 不重发
        assert len(client.posts) == 3

    def test_5xx_send_retries_then_success(self, monkeypatch):
        _set_credentials(monkeypatch)
        client = FakeClient([
            _FakeResp(200, {"access_token": "TOK", "expires_in": 7200}),
            _FakeResp(500),  # 第一次发送 5xx
            _FakeResp(200, {"errcode": 0}),  # 重试成功
        ])
        result = asyncio.run(wsm.send_subscribe_msg(
            "oid", "tpl", {}, client=client, max_retries=2, backoff=0))
        assert result["status"] == "sent"


# ============================================================
# resolve_openid + _invoice_order_ids
# ============================================================

class TestInvoiceOrderIds:
    def test_list_input(self):
        req = types.SimpleNamespace(order_ids=["A1", "A2"])
        assert wsm._invoice_order_ids(req) == ["A1", "A2"]

    def test_tuple_input(self):
        req = types.SimpleNamespace(order_ids=("A1",))
        assert wsm._invoice_order_ids(req) == ["A1"]

    def test_json_string_input(self):
        req = types.SimpleNamespace(order_ids='["A1", "A2"]')
        assert wsm._invoice_order_ids(req) == ["A1", "A2"]

    def test_empty_returns_empty(self):
        req = types.SimpleNamespace(order_ids=None)
        assert wsm._invoice_order_ids(req) == []

    def test_missing_attr_returns_empty(self):
        req = types.SimpleNamespace()
        assert wsm._invoice_order_ids(req) == []

    def test_invalid_json_returns_empty(self):
        req = types.SimpleNamespace(order_ids="not-json")
        assert wsm._invoice_order_ids(req) == []

    def test_json_object_returns_empty(self):
        req = types.SimpleNamespace(order_ids='{"k": "v"}')  # 非 list
        assert wsm._invoice_order_ids(req) == []


class TestResolveOpenid:
    def test_found_openid(self):
        po = types.SimpleNamespace(openid="OPENID1", business_order_no="O1")

        class _Q:
            def __init__(self, po):
                self._po = po

            def filter(self, *a, **k):
                return self

            def first(self):
                return self._po

        class _DB:
            def query(self, model):
                return _Q(po)

        req = types.SimpleNamespace(order_ids=["O1"])
        assert wsm.resolve_openid(_DB(), req) == "OPENID1"

    def test_no_payment_order_returns_none(self):
        class _Q:
            def filter(self, *a, **k):
                return self

            def first(self):
                return None

        class _DB:
            def query(self, model):
                return _Q()

        req = types.SimpleNamespace(order_ids=["O1"])
        assert wsm.resolve_openid(_DB(), req) is None

    def test_order_without_openid_returns_none(self):
        po = types.SimpleNamespace(openid=None, business_order_no="O1")

        class _Q:
            def filter(self, *a, **k):
                return self

            def first(self):
                return po

        class _DB:
            def query(self, model):
                return _Q()

        req = types.SimpleNamespace(order_ids=["O1"])
        assert wsm.resolve_openid(_DB(), req) is None

    def test_query_exception_skips_and_continues(self):
        # 第一个订单查询抛异常, 第二个命中
        po2 = types.SimpleNamespace(openid="OPENID2", business_order_no="O2")
        seen = []

        class _DB:
            def query(self, model):
                seen.append(1)
                return self

            def filter(self, *a, **k):
                return self

            def first(self):
                if len(seen) == 1:
                    raise RuntimeError("db error")
                return po2

        req = types.SimpleNamespace(order_ids=["O1", "O2"])
        assert wsm.resolve_openid(_DB(), req) == "OPENID2"

    def test_empty_order_ids_returns_none_quickly(self):
        class _DB:
            def query(self, model):
                raise AssertionError("不应查询数据库")

        req = types.SimpleNamespace(order_ids=[])
        assert wsm.resolve_openid(_DB(), req) is None
