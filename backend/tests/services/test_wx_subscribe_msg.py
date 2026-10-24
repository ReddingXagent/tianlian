"""wx_subscribe_msg 单元测试 (卡 3591ea8f)

被测: app/services/wx_subscribe_msg.py — IM-B小程序订阅消息推送
(凭证管理 / access_token 缓存 / send_subscribe_msg / resolve_openid)。

覆盖矩阵:
  凭证配置 (_credentials_configured):
    - APPID+SECRET 齐备 → True
    - 任一缺失/空 → False
  access_token (get_access_token / _fetch_access_token):
    - 凭证未配置 → None (不发请求)
    - 缓存命中 (未过期) → 直接返回不刷新
    - 缓存过期 → 重新请求
    - 请求异常 / errcode != 0 → None
    - invalidate_access_token 清空缓存
  send_subscribe_msg (各 status):
    - 未配置 → skipped (no_credentials)
    - access_token 失败 → failed (no_access_token)
    - IM-B errcode == 0 → sent
    - errcode != 0 → failed
    - HTTP 异常重试耗尽 → failed
    - 5xx 重试 → 最终 sent
  resolve_openid:
    - JSON 字符串 order_ids → 命中 PaymentOrder.openid
    - list order_ids → 命中
    - 无支付单 → None
    - 空订单号 → None
    - 查询异常 → 跳过该单继续, 不抛

测试缝: FakeClient (注入式 httpx 替身) + monkeypatch mod.settings + monkeypatch time。
"""
import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import wx_subscribe_msg as mod
from app.models.payment_order import PaymentOrder, PayScene, PaymentStatus


# ═══════════════════════════════════════════════════════════════
# FakeClient — 注入式 httpx 替身 (与 channel_providers 测试同源)
# ═══════════════════════════════════════════════════════════════
class FakeClient:
    """按 url 路径返回不同响应的 httpx 替身。

    responses: {url_substr: {status_code, payload}} 或 payload 抛 exc。
    calls 记录全部请求 (含 token + send)。
    """

    def __init__(self, responses=None, exc=None):
        self.calls = []
        self._responses = responses or {}
        self._exc = exc

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json})
        if self._exc is not None:
            raise self._exc
        for substr, spec in self._responses.items():
            if substr in url:
                r = MagicMock()
                r.status_code = spec.get("status_code", 200)
                r.json.return_value = spec.get("payload", {})
                return r
        # 默认 200 空体
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {}
        return r


async def _noop_sleep(_=None):
    return None


async def _fake_fetch_noop(client=None):
    """最小 _fetch_access_token 替身: 写缓存并返回, 让出事件循环模拟 await httpx。"""
    await asyncio.sleep(0)
    mod._token_cache["value"] = "TOK_SINGLE"
    mod._token_cache["expires_at"] = 9999999999.0
    return "TOK_SINGLE"


def _settings(**over):
    base = dict(WX_MP_APPID=None, WX_MP_SECRET=None)
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """每测清空 access_token 缓存 + 复位 lazy 锁, 隔离测试间状态。

    锁必须复位: lazy 锁在协程内绑到运行 loop, 跨测试 (各自独立 event loop) 复用会
    触发 "attached to a different loop" (Python 3.9 开发/测试环境)。
    """
    mod.invalidate_access_token()
    mod._token_lock = None
    yield
    mod.invalidate_access_token()
    mod._token_lock = None


# ═══════════════════════════════════════════════════════════════
# _credentials_configured
# ═══════════════════════════════════════════════════════════════
class TestCredentialsConfigured:
    def test_both_set_returns_true(self, monkeypatch):
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx123", WX_MP_SECRET="sec"))
        assert mod._credentials_configured() is True

    def test_appid_missing_returns_false(self, monkeypatch):
        monkeypatch.setattr(mod, "settings", _settings(WX_MP_SECRET="sec"))
        assert mod._credentials_configured() is False

    def test_secret_missing_returns_false(self, monkeypatch):
        monkeypatch.setattr(mod, "settings", _settings(WX_MP_APPID="wx123"))
        assert mod._credentials_configured() is False

    def test_both_empty_returns_false(self, monkeypatch):
        monkeypatch.setattr(mod, "settings", _settings(WX_MP_APPID="", WX_MP_SECRET=""))
        assert mod._credentials_configured() is False


# ═══════════════════════════════════════════════════════════════
# access_token 缓存与刷新
# ═══════════════════════════════════════════════════════════════
class TestAccessToken:
    def test_not_configured_returns_none_without_request(self, monkeypatch):
        """凭证未配置 → None, 不发任何 HTTP 请求。"""
        monkeypatch.setattr(mod, "settings", _settings())
        client = FakeClient(responses={"stable_token": {"payload": {"access_token": "T"}}})
        token = asyncio.run(mod.get_access_token(client))
        assert token is None
        assert client.calls == []  # 未发请求

    def test_fetch_success_caches_token(self, monkeypatch):
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        client = FakeClient(responses={"stable_token": {
            "payload": {"access_token": "TOK1", "expires_in": 7200, "errcode": 0}
        }})
        token = asyncio.run(mod.get_access_token(client))
        assert token == "TOK1"
        # 缓存已写入
        assert mod._token_cache["value"] == "TOK1"
        assert mod._token_cache["expires_at"] > 0

    def test_cache_hit_skips_request(self, monkeypatch):
        """未过期缓存命中 → 直接返回, 不再请求。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        client = FakeClient(responses={"stable_token": {
            "payload": {"access_token": "TOK1", "expires_in": 7200}
        }})
        asyncio.run(mod.get_access_token(client))
        assert len(client.calls) == 1
        # 第二次应命中缓存
        token2 = asyncio.run(mod.get_access_token(client))
        assert token2 == "TOK1"
        assert len(client.calls) == 1  # 仍只 1 次请求

    def test_cache_expired_refetches(self, monkeypatch):
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        client = FakeClient(responses={"stable_token": {
            "payload": {"access_token": "TOK2", "expires_in": 7200}
        }})
        # 预置一个已过期的缓存
        mod._token_cache["value"] = "STALE"
        mod._token_cache["expires_at"] = 1.0  # epoch 极早, 必过期
        token = asyncio.run(mod.get_access_token(client))
        assert token == "TOK2"  # 刷新为新 token

    def test_fetch_errcode_returns_none(self, monkeypatch):
        """IM-B返回 errcode (如 40164 IP 白名单) → None, 不缓存。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        client = FakeClient(responses={"stable_token": {
            "payload": {"errcode": 40164, "errmsg": "invalid ip"}
        }})
        token = asyncio.run(mod.get_access_token(client))
        assert token is None
        assert mod._token_cache["value"] is None

    def test_fetch_exception_returns_none(self, monkeypatch):
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        client = FakeClient(exc=RuntimeError("network down"))
        token = asyncio.run(mod.get_access_token(client))
        assert token is None

    def test_invalidate_clears_cache(self, monkeypatch):
        mod._token_cache["value"] = "X"
        mod._token_cache["expires_at"] = 9999999999.0
        mod.invalidate_access_token()
        assert mod._token_cache["value"] is None
        assert mod._token_cache["expires_at"] == 0.0


class TestConcurrentRefresh:
    """并发安全: 多协程并发 get_access_token 时 _fetch_access_token 只触发一次。

    场景 (卡 b03224c4): _token_cache 是模块级全局 dict, _fetch_access_token 内有
    await httpx 调用, 期间其他任务可发现缓存过期并发起重复刷新。asyncio.Lock +
    double-check 应收敛为单次刷新。
    """

    def test_concurrent_get_refreshes_once(self, monkeypatch):
        """N 个并发 get_access_token → _fetch_access_token 恰好 1 次。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        # 缓存已清空 (autouse fixture), expires_at=0.0 必过期 → 走刷新分支
        calls = {"n": 0}
        orig = _fake_fetch_noop

        async def counting_fetch(client=None):
            calls["n"] += 1
            return await orig(client)

        monkeypatch.setattr(mod, "_fetch_access_token", counting_fetch)

        async def run():
            return await asyncio.gather(*[mod.get_access_token() for _ in range(20)])

        tokens = asyncio.run(run())
        # 全部拿到同一 token
        assert tokens == ["TOK_SINGLE"] * 20
        # _fetch 只被调用一次 (锁 + double-check 生效)
        assert calls["n"] == 1

    def test_lock_is_asyncio_lock(self, monkeypatch):
        """锁 lazy 初始化为 asyncio.Lock (首次调用后在运行 loop 上创建, 兼容 3.9)。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        monkeypatch.setattr(mod, "_fetch_access_token", _fake_fetch_noop)
        asyncio.run(mod.get_access_token())
        assert isinstance(mod._token_lock, asyncio.Lock)


# ═══════════════════════════════════════════════════════════════
# send_subscribe_msg
# ═══════════════════════════════════════════════════════════════
class TestSendSubscribeMsg:
    def test_not_configured_skips(self, monkeypatch, caplog):
        """APPID 未配置 → skipped + 日志, 不发请求。"""
        monkeypatch.setattr(mod, "settings", _settings())
        monkeypatch.setattr(mod.asyncio, "sleep", _noop_sleep)
        client = FakeClient()
        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            out = asyncio.run(mod.send_subscribe_msg(
                "openid_1", "TPL", {"k": {"value": "v"}}, client=client,
            ))
        assert out["status"] == "skipped"
        assert out["reason"] == "no_credentials"
        assert client.calls == []
        assert any("WX SUBSCRIBE MOCK" in r.message for r in caplog.records)

    def test_no_access_token_fails(self, monkeypatch):
        """凭证配置但 access_token 获取失败 → failed (no_access_token)。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        client = FakeClient(responses={"stable_token": {
            "payload": {"errcode": 40013}  # token 失败
        }})
        out = asyncio.run(mod.send_subscribe_msg(
            "openid_1", "TPL", {}, client=client,
        ))
        assert out["status"] == "failed"
        assert out["error"] == "no_access_token"

    def test_sent_on_errcode_zero(self, monkeypatch):
        """IM-B返回 errcode == 0 → sent。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        client = FakeClient(responses={
            "stable_token": {"payload": {"access_token": "TOK", "expires_in": 7200}},
            "subscribe/send": {"payload": {"errcode": 0, "errmsg": "ok"}},
        })
        out = asyncio.run(mod.send_subscribe_msg(
            "openid_1", "TPL", {"amount": {"value": "1.00"}},
            page="pages/x?id=1", client=client,
        ))
        assert out["status"] == "sent"
        # send 请求 URL 带 access_token, body 带 openid/template/page/data
        send_call = [c for c in client.calls if "subscribe/send" in c["url"]][0]
        assert "access_token=TOK" in send_call["url"]
        body = send_call["json"]
        assert body["touser"] == "openid_1"
        assert body["template_id"] == "TPL"
        assert body["page"] == "pages/x?id=1"
        assert body["data"]["amount"]["value"] == "1.00"

    def test_failed_on_nonzero_errcode(self, monkeypatch):
        """IM-B返回 errcode != 0 (如 43101 用户未订阅) → failed。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        client = FakeClient(responses={
            "stable_token": {"payload": {"access_token": "TOK", "expires_in": 7200}},
            "subscribe/send": {"payload": {"errcode": 43101, "errmsg": "未订阅"}},
        })
        out = asyncio.run(mod.send_subscribe_msg(
            "openid_1", "TPL", {}, client=client,
        ))
        assert out["status"] == "failed"
        assert "43101" in out["error"]

    def test_http_exception_retries_then_fails(self, monkeypatch):
        """send 请求持续抛异常 → 重试耗尽 → failed。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        monkeypatch.setattr(mod.asyncio, "sleep", _noop_sleep)
        # token 成功, send 持续异常
        client = FakeClient(exc=ConnectionError("reset"))
        # 让 token 接口能成功: FakeClient 对所有 url 都抛同一 exc, 故需预置缓存绕过 token
        mod._token_cache["value"] = "TOK"
        mod._token_cache["expires_at"] = 9999999999.0
        out = asyncio.run(mod.send_subscribe_msg(
            "openid_1", "TPL", {}, client=client, max_retries=2,
        ))
        assert out["status"] == "failed"
        assert "reset" in out["error"]
        # 重试 2 次 → 共 3 次尝试
        assert len(client.calls) == 3

    def test_5xx_retries_then_succeeds(self, monkeypatch):
        """5xx 重试, 最终成功 → sent。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        monkeypatch.setattr(mod.asyncio, "sleep", _noop_sleep)
        mod._token_cache["value"] = "TOK"
        mod._token_cache["expires_at"] = 9999999999.0

        attempts = {"n": 0}

        class RetryClient:
            def __init__(self):
                self.calls = []

            async def post(self, url, json=None, headers=None, timeout=None):
                self.calls.append(url)
                attempts["n"] += 1
                r = MagicMock()
                if attempts["n"] < 2:
                    r.status_code = 500  # 首次 5xx
                    r.json.return_value = {}
                else:
                    r.status_code = 200
                    r.json.return_value = {"errcode": 0}
                return r

        out = asyncio.run(mod.send_subscribe_msg(
            "openid_1", "TPL", {}, client=RetryClient(), max_retries=2,
        ))
        assert out["status"] == "sent"

    def test_miniprogram_state_included(self, monkeypatch):
        """miniprogram_state 透传到 body (developer/trial/formal)。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        client = FakeClient(responses={
            "stable_token": {"payload": {"access_token": "TOK", "expires_in": 7200}},
            "subscribe/send": {"payload": {"errcode": 0}},
        })
        asyncio.run(mod.send_subscribe_msg(
            "openid_1", "TPL", {}, miniprogram_state="trial", client=client,
        ))
        send_call = [c for c in client.calls if "subscribe/send" in c["url"]][0]
        assert send_call["json"]["miniprogram_state"] == "trial"

    def test_default_lang_zh_cn(self, monkeypatch):
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        client = FakeClient(responses={
            "stable_token": {"payload": {"access_token": "TOK", "expires_in": 7200}},
            "subscribe/send": {"payload": {"errcode": 0}},
        })
        asyncio.run(mod.send_subscribe_msg("openid_1", "TPL", {}, client=client))
        send_call = [c for c in client.calls if "subscribe/send" in c["url"]][0]
        assert send_call["json"]["lang"] == "zh_CN"


# ═══════════════════════════════════════════════════════════════
# resolve_openid
# ═══════════════════════════════════════════════════════════════
def _make_payment_order(db, business_order_no, openid="openid_user"):
    po = PaymentOrder(
        out_trade_no=f"TL_{business_order_no}",
        business_order_no=business_order_no,
        openid=openid,
        scene=PayScene.MINIPROGRAM,
        sub_mchid="2490000001",
        amount_fen=10000,
        payment_status=PaymentStatus.PAID,
    )
    db.add(po)
    db.commit()
    return po


class TestResolveOpenid:
    def test_resolves_from_json_order_ids(self, test_db):
        """order_ids 为 JSON 字符串 (生产 InvoiceRequest 格式) → 命中 openid。"""
        import json
        db = test_db["session"]
        _make_payment_order(db, "ord_001", openid="oABC123")
        req = SimpleNamespace(order_ids=json.dumps(["ord_001"]))
        assert mod.resolve_openid(db, req) == "oABC123"

    def test_resolves_from_list_order_ids(self, test_db):
        """order_ids 为 list → 命中首个有支付单的订单 openid。"""
        db = test_db["session"]
        _make_payment_order(db, "ord_002", openid="oLIST")
        req = SimpleNamespace(order_ids=["ord_002"])
        assert mod.resolve_openid(db, req) == "oLIST"

    def test_returns_none_when_no_payment_order(self, test_db):
        """订单无支付单记录 (余额支付/脏数据) → None。"""
        db = test_db["session"]
        req = SimpleNamespace(order_ids=["ord_missing"])
        assert mod.resolve_openid(db, req) is None

    def test_returns_none_when_empty_order_ids(self, test_db):
        db = test_db["session"]
        req = SimpleNamespace(order_ids=None)
        assert mod.resolve_openid(db, req) is None
        req2 = SimpleNamespace(order_ids="[]")
        assert mod.resolve_openid(db, req2) is None

    def test_takes_first_hit_across_orders(self, test_db):
        """多订单: 首个有支付单的订单 openid 即返回 (用户 openid 唯一)。"""
        db = test_db["session"]
        _make_payment_order(db, "ord_b", openid="oB")
        req = SimpleNamespace(order_ids=["ord_none_first", "ord_b"])
        assert mod.resolve_openid(db, req) == "oB"

    def test_invalid_json_returns_none(self, test_db):
        """order_ids 非法 JSON → 当作无订单, None。"""
        db = test_db["session"]
        req = SimpleNamespace(order_ids="not-json{")
        assert mod.resolve_openid(db, req) is None

    def test_query_exception_does_not_raise(self, test_db, monkeypatch):
        """查询抛异常 → 跳过该单, 不向上抛 (best-effort)。"""
        db = test_db["session"]
        req = SimpleNamespace(order_ids=["ord_x"])

        def boom(q):
            raise RuntimeError("db error")

        monkeypatch.setattr(db, "query", boom)
        # 全部订单都异常 → None, 不抛
        assert mod.resolve_openid(db, req) is None


# ═══════════════════════════════════════════════════════════════
# 补全 (卡 676d2fa1): 自建 client 路径 + _invoice_order_ids 非list JSON
#
# 盲区根因: 上方所有用例均注入 FakeClient (client=client), 绕过 client=None 时
# 模块自建 httpx.AsyncClient + finally aclose 的代码路径 (生产环境 client 恒为 None,
# 这条路径零覆盖)。测试缝: monkeypatch httpx.AsyncClient → FakeClient, 触达自建分支
# 同时保持网络隔离 (不触网)。
# ═══════════════════════════════════════════════════════════════
class TestOwnClientPath:
    """client=None 自建 httpx.AsyncClient 路径覆盖 (生产真实路径)。"""

    def _patch_async_client(self, monkeypatch, fake):
        """把 mod.httpx.AsyncClient 替换为返回 FakeClient 的工厂。"""
        monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: fake)
        return fake

    def _closable(self, responses=None, exc=None):
        """带 aclose 的 FakeClient 子类 (自建 client 路径 finally 调 aclose)。"""
        class ClosableFake(FakeClient):
            async def aclose(self):
                self.closed = True
        return ClosableFake(responses=responses, exc=exc)

    def test_fetch_access_token_own_client_success(self, monkeypatch):
        """_fetch_access_token(client=None) 自建 client, 成功取 token 并缓存。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        monkeypatch.setattr(mod.asyncio, "sleep", _noop_sleep)
        fake = self._closable(responses={"stable_token": {
            "payload": {"access_token": "OWN_TOK", "expires_in": 7200, "errcode": 0}
        }})
        self._patch_async_client(monkeypatch, fake)
        token = asyncio.run(mod._fetch_access_token(None))
        assert token == "OWN_TOK"
        assert mod._token_cache["value"] == "OWN_TOK"
        # 自建 client 被复用发了一次 token 请求, finally 已 aclose
        assert len(fake.calls) == 1
        assert "stable_token" in fake.calls[0]["url"]
        assert fake.closed is True

    def test_fetch_access_token_own_client_closed_on_errcode(self, monkeypatch):
        """自建 client 在 errcode 失败分支也被正确 aclose (finally 兜底)。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        closed = {"v": False}

        class ClosableFake(FakeClient):
            async def aclose(self):
                closed["v"] = True

        fake = ClosableFake(responses={"stable_token": {
            "payload": {"errcode": 40164, "errmsg": "invalid ip"}
        }})
        self._patch_async_client(monkeypatch, fake)
        token = asyncio.run(mod._fetch_access_token(None))
        assert token is None  # errcode → None
        assert closed["v"] is True  # finally 关闭

    def test_fetch_access_token_own_client_closed_on_exception(self, monkeypatch):
        """自建 client 在请求异常分支也被 aclose。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))

        class ClosableFake(FakeClient):
            async def aclose(self):
                self.closed = True

        fake = ClosableFake(exc=RuntimeError("net down"))
        self._patch_async_client(monkeypatch, fake)
        token = asyncio.run(mod._fetch_access_token(None))
        assert token is None
        assert fake.closed is True

    def test_send_subscribe_msg_own_client_sent(self, monkeypatch):
        """send_subscribe_msg(client=None) 自建 client, errcode==0 → sent。

        注: 需先经 _fetch_access_token 取 token (自建 client 发 token 请求), 再发
        subscribe 请求, 两次 POST 都走自建 client。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        monkeypatch.setattr(mod.asyncio, "sleep", _noop_sleep)
        fake = self._closable(responses={
            "stable_token": {"payload": {"access_token": "T", "expires_in": 7200}},
            "subscribe/send": {"payload": {"errcode": 0}},
        })
        self._patch_async_client(monkeypatch, fake)
        out = asyncio.run(mod.send_subscribe_msg(
            openid="oABC", template_id="TPL", data={"k": {"value": "v"}},
            backoff=0,
        ))
        assert out == {"status": "sent", "channel": "wx_subscribe"}
        # token + send 两次请求都经自建 client
        assert len(fake.calls) == 2

    def test_send_subscribe_msg_own_client_closed_on_failure(self, monkeypatch):
        """自建 client 在发送失败 (errcode!=0) 后也被 aclose。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        monkeypatch.setattr(mod.asyncio, "sleep", _noop_sleep)

        class ClosableFake(FakeClient):
            async def aclose(self):
                self.closed = True

        fake = ClosableFake(responses={
            "stable_token": {"payload": {"access_token": "T", "expires_in": 7200}},
            "subscribe/send": {"payload": {"errcode": 43101, "errmsg": "refused"}},
        })
        self._patch_async_client(monkeypatch, fake)
        out = asyncio.run(mod.send_subscribe_msg(
            openid="oABC", template_id="TPL", data={}, backoff=0,
        ))
        assert out["status"] == "failed"
        assert fake.closed is True

    def test_send_subscribe_msg_own_client_closed_on_http_exception(self, monkeypatch):
        """自建 client 在 _post_subscribe 重试耗尽抛异常后也被 aclose (finally)。

        token 请求成功 (返回 access_token), subscribe 请求持续抛异常 → 重试耗尽 →
        send_subscribe_msg 捕获落 failed, finally aclose。

        用内联 fake (token 与 send 两路分流), 因 FakeClient 仅按 responses 匹配, 无法
        表达"同 client 一路成功一路抛"。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        monkeypatch.setattr(mod.asyncio, "sleep", _noop_sleep)

        class SplitFake:
            def __init__(self):
                self.calls = []
                self.closed = False

            async def post(self, url, json=None, headers=None, timeout=None):
                self.calls.append({"url": url, "json": json})
                if "stable_token" in url:
                    r = MagicMock()
                    r.status_code = 200
                    r.json.return_value = {"access_token": "T", "expires_in": 7200}
                    return r
                raise ConnectionError("gateway reset")

            async def aclose(self):
                self.closed = True

        fake = SplitFake()
        monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: fake)
        out = asyncio.run(mod.send_subscribe_msg(
            openid="oABC", template_id="TPL", data={}, max_retries=1, backoff=0,
        ))
        assert out["status"] == "failed"
        assert "gateway reset" in out["error"]
        assert fake.closed is True


class TestSafeJsonAndTokenMissing:
    """_safe_json 异常分支 + _fetch_access_token 无 access_token key 分支。

    覆盖 wx_subscribe_msg.py L164-165 (_safe_json except 返回 {}) 与 L118
    (body 无 access_token 字段 → return None)。"""

    def test_safe_json_normal(self):
        resp = MagicMock()
        resp.json.return_value = {"errcode": 0}
        assert mod._safe_json(resp) == {"errcode": 0}

    def test_safe_json_exception_returns_empty(self):
        """resp.json() 抛异常 (IM-B返回非 JSON / 连接中断) → 返回 {}。"""
        resp = MagicMock()
        resp.json.side_effect = ValueError("not json")
        assert mod._safe_json(resp) == {}

    def test_fetch_returns_none_when_no_access_token_key(self, monkeypatch):
        """响应体合法 JSON 但无 access_token 字段 → None (L118)。"""
        monkeypatch.setattr(mod, "settings",
                            _settings(WX_MP_APPID="wx", WX_MP_SECRET="s"))
        monkeypatch.setattr(mod.asyncio, "sleep", _noop_sleep)

        class ClosableFake(FakeClient):
            async def aclose(self):
                self.closed = True

        fake = ClosableFake(responses={"stable_token": {
            "payload": {"errcode": 0, "expires_in": 7200},  # 无 access_token
        }})
        monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: fake)
        token = asyncio.run(mod._fetch_access_token(None))
        assert token is None
        assert mod._token_cache["value"] is None  # 未缓存


class TestInvoiceOrderIdsEdgeCases:
    """_invoice_order_ids 解析边界 (L293 非 list JSON → [] 分支)。"""

    def test_json_dict_returns_empty(self):
        """order_ids 是 JSON 对象 (非数组) → 返回 []。"""
        import json
        req = SimpleNamespace(order_ids=json.dumps({"not": "a list"}))
        assert mod._invoice_order_ids(req) == []

    def test_json_scalar_string_returns_empty(self):
        """order_ids 是 JSON 标量字符串 → 返回 []。"""
        import json
        req = SimpleNamespace(order_ids=json.dumps("ord_001"))
        assert mod._invoice_order_ids(req) == []

    def test_json_scalar_number_returns_empty(self):
        """order_ids 是 JSON 数字 → 返回 []。"""
        import json
        req = SimpleNamespace(order_ids=json.dumps(12345))
        assert mod._invoice_order_ids(req) == []

    def test_tuple_order_ids_coerced_to_str_list(self):
        """tuple 形式 → 逐项 str()。"""
        req = SimpleNamespace(order_ids=("ord_1", "ord_2"))
        assert mod._invoice_order_ids(req) == ["ord_1", "ord_2"]

    def test_non_string_non_collection_returns_empty(self):
        """order_ids 既非 list/tuple 也非 str (如 int) → []。"""
        req = SimpleNamespace(order_ids=12345)
        assert mod._invoice_order_ids(req) == []

    def test_empty_list_returns_empty(self):
        req = SimpleNamespace(order_ids=[])
        assert mod._invoice_order_ids(req) == []
