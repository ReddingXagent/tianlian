"""wx_subscribe_msg 零测试补全 — token缓存/retry/resolve_openid edge case (卡63c928d2)

被测: app/services/wx_subscribe_msg.py — IM-B订阅消息推送服务

12 个 edge case:
  1.  get_access_token 缓存命中 (不调 HTTP)
  2.  get_access_token 缓存过期 → 刷新
  3.  get_access_token 提前刷新 (expires_at - margin 边界)
  4.  _fetch_access_token 成功缓存
  5.  _fetch_access_token IM-B errcode != 0 → None
  6.  send_subscribe_msg 成功 (errcode==0)
  7.  send_subscribe_msg IM-B业务失败 (errcode!=0)
  8.  send_subscribe_msg 5xx 重试 + 指数退避
  9.  send_subscribe_msg 全部重试失败 → failed
 10.  send_subscribe_msg 无凭证 → skipped
 11.  resolve_openid 正常命中
 12.  resolve_openid 无订单 / 无 openid / 查询异常

测试缝:
  - FakeAsyncClient 注入绕过真实 httpx
  - monkeypatch mod.settings 切换凭证
  - monkeypatch asyncio.sleep 跳过退避
  - invalidate_access_token() 隔离缓存
"""
import asyncio
import json
import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from app.services import wx_subscribe_msg as mod


# ============================================================
# Helpers / Fakes
# ============================================================

class FakeResponse:
    """模拟 httpx.Response"""
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class FakeAsyncClient:
    """模拟 httpx.AsyncClient — 记录调用次数和参数"""
    def __init__(self, responses=None, exc=None):
        # responses: list of FakeResponse (按调用顺序弹出)
        self._responses = responses or []
        self._exc = exc
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        # If responses exhausted and exc set, raise
        if not self._responses and self._exc:
            raise self._exc
        if self._responses:
            return self._responses.pop(0)
        if self._exc:
            raise self._exc
        return FakeResponse(200, {"errcode": 0})

    async def aclose(self):
        pass


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """每个测试前后清空 token 缓存 + 复位 lazy 锁, 隔离副作用。

    锁复位: lazy 锁绑运行 loop, 跨测试 (各自独立 event loop) 复用会触发
    "attached to a different loop" (Python 3.9 开发/测试环境)。
    """
    mod.invalidate_access_token()
    mod._token_lock = None
    yield
    mod.invalidate_access_token()
    mod._token_lock = None


@pytest.fixture
def with_credentials(monkeypatch):
    """注入 WX_MP_APPID / SECRET"""
    monkeypatch.setattr(mod.settings, "WX_MP_APPID", "wx_test_appid_123")
    monkeypatch.setattr(mod.settings, "WX_MP_SECRET", "wx_test_secret_456")


@pytest.fixture
def no_credentials(monkeypatch):
    """移除 WX_MP_APPID / SECRET"""
    monkeypatch.setattr(mod.settings, "WX_MP_APPID", None)
    monkeypatch.setattr(mod.settings, "WX_MP_SECRET", None)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """跳过 asyncio.sleep (指数退避)"""
    async def _noop(_):
        pass
    monkeypatch.setattr(mod.asyncio, "sleep", _noop)


# ============================================================
# access_token 缓存测试
# ============================================================

@pytest.mark.asyncio
async def test_token_cache_hit(with_credentials):
    """缓存命中: 第二次调用不发起 HTTP 请求。"""
    client = FakeAsyncClient(responses=[
        FakeResponse(200, {"access_token": "tok_abc", "expires_in": 7200})
    ])
    t1 = await mod.get_access_token(client)
    assert t1 == "tok_abc"
    # 第二次应命中缓存, client.calls 不增加
    calls_before = len(client.calls)
    t2 = await mod.get_access_token(client)
    assert t2 == "tok_abc"
    assert len(client.calls) == calls_before  # 无新请求


@pytest.mark.asyncio
async def test_token_cache_expired_refresh(with_credentials):
    """缓存过期后重新刷新。"""
    client = FakeAsyncClient(responses=[
        FakeResponse(200, {"access_token": "tok_old", "expires_in": 7200}),
        FakeResponse(200, {"access_token": "tok_new", "expires_in": 7200}),
    ])
    t1 = await mod.get_access_token(client)
    assert t1 == "tok_old"
    # 模拟过期
    mod._token_cache["expires_at"] = time.time() - 1
    t2 = await mod.get_access_token(client)
    assert t2 == "tok_new"


@pytest.mark.asyncio
async def test_token_refresh_margin_boundary(with_credentials):
    """提前 5min 刷新: expires_at 正好等于 now 时触发刷新。"""
    client = FakeAsyncClient(responses=[
        FakeResponse(200, {"access_token": "tok_a", "expires_in": 7200}),
        FakeResponse(200, {"access_token": "tok_b", "expires_in": 7200}),
    ])
    t1 = await mod.get_access_token(client)
    assert t1 == "tok_a"
    # expires_at 设为当前时间 (边界: 不大于 now → 缓存不命中)
    mod._token_cache["expires_at"] = time.time()
    t2 = await mod.get_access_token(client)
    assert t2 == "tok_b"


@pytest.mark.asyncio
async def test_fetch_token_success_caches(with_credentials):
    """_fetch_access_token 成功后正确写入缓存。"""
    client = FakeAsyncClient(responses=[
        FakeResponse(200, {"access_token": "cached_tok", "expires_in": 7200})
    ])
    tok = await mod._fetch_access_token(client)
    assert tok == "cached_tok"
    assert mod._token_cache["value"] == "cached_tok"
    assert mod._token_cache["expires_at"] > time.time() + 6000


@pytest.mark.asyncio
async def test_fetch_token_errcode_returns_none(with_credentials):
    """IM-B返回 errcode != 0 → None, 不写缓存。"""
    client = FakeAsyncClient(responses=[
        FakeResponse(200, {"errcode": 40013, "errmsg": "invalid appid"})
    ])
    tok = await mod._fetch_access_token(client)
    assert tok is None
    assert mod._token_cache["value"] is None


# ============================================================
# send_subscribe_msg 测试
# ============================================================

@pytest.mark.asyncio
async def test_send_subscribe_msg_success(with_credentials):
    """发送成功 errcode==0 → status=sent。"""
    # access_token 响应 + subscribe 发送响应
    client = FakeAsyncClient(responses=[
        FakeResponse(200, {"access_token": "tok_ok", "expires_in": 7200}),
        FakeResponse(200, {"errcode": 0, "errmsg": "ok"}),
    ])
    result = await mod.send_subscribe_msg(
        openid="oXxx123", template_id="tpl_001",
        data={"thing01": {"value": "测试"}},
        client=client,
    )
    assert result["status"] == "sent"
    assert result["channel"] == "wx_subscribe"


@pytest.mark.asyncio
async def test_send_subscribe_msg_wx_error(with_credentials):
    """IM-B业务失败 errcode!=0 → status=failed。"""
    client = FakeAsyncClient(responses=[
        FakeResponse(200, {"access_token": "tok_ok", "expires_in": 7200}),
        FakeResponse(200, {"errcode": 43101, "errmsg": "user refuse"}),
    ])
    result = await mod.send_subscribe_msg(
        openid="oXxx123", template_id="tpl_001",
        data={"thing01": {"value": "测试"}},
        client=client,
    )
    assert result["status"] == "failed"
    assert "43101" in str(result.get("error", ""))


@pytest.mark.asyncio
async def test_send_subscribe_msg_5xx_retry(with_credentials):
    """5xx 触发重试, 第三次成功 → sent。"""
    # token + 两次 502 + 最终 200 成功
    client = FakeAsyncClient(responses=[
        FakeResponse(200, {"access_token": "tok_ok", "expires_in": 7200}),
        FakeResponse(502),
        FakeResponse(502),
        FakeResponse(200, {"errcode": 0, "errmsg": "ok"}),
    ])
    result = await mod.send_subscribe_msg(
        openid="oXxx123", template_id="tpl_001",
        data={"thing01": {"value": "测试"}},
        client=client, max_retries=2, backoff=0,
    )
    assert result["status"] == "sent"
    # 验证 post 调用次数: 1 token + 3 subscribe = 4
    assert len(client.calls) == 4


@pytest.mark.asyncio
async def test_send_subscribe_msg_all_retries_fail(with_credentials):
    """全部重试耗尽 → status=failed。"""
    client = FakeAsyncClient(responses=[
        FakeResponse(200, {"access_token": "tok_ok", "expires_in": 7200}),
        FakeResponse(500),
        FakeResponse(500),
        FakeResponse(500),
    ])
    result = await mod.send_subscribe_msg(
        openid="oXxx123", template_id="tpl_001",
        data={"thing01": {"value": "测试"}},
        client=client, max_retries=2, backoff=0,
    )
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_send_subscribe_msg_no_credentials(no_credentials):
    """无 APPID/SECRET → status=skipped, 不发 HTTP。"""
    client = FakeAsyncClient()
    result = await mod.send_subscribe_msg(
        openid="oXxx123", template_id="tpl_001",
        data={"thing01": {"value": "测试"}},
        client=client,
    )
    assert result["status"] == "skipped"
    assert result["reason"] == "no_credentials"
    assert len(client.calls) == 0


@pytest.mark.asyncio
async def test_send_subscribe_msg_exception(with_credentials):
    """HTTP 异常 → failed (不抛)。"""
    client = FakeAsyncClient(responses=[
        FakeResponse(200, {"access_token": "tok_ok", "expires_in": 7200}),
    ], exc=ConnectionError("network down"))
    result = await mod.send_subscribe_msg(
        openid="oXxx123", template_id="tpl_001",
        data={"thing01": {"value": "测试"}},
        client=client, max_retries=0, backoff=0,
    )
    assert result["status"] == "failed"
    assert "network down" in str(result.get("error", ""))


# ============================================================
# resolve_openid 测试
# ============================================================

class FakeInvoiceRequest:
    """模拟 InvoiceRequest"""
    def __init__(self, order_ids=None):
        self.order_ids = order_ids


def test_resolve_openid_found():
    """正常场景: 从 payment_orders 查到 openid。"""
    mock_po = MagicMock()
    mock_po.openid = "oTestOpenid456"

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = mock_po

    mock_db = MagicMock()
    mock_db.query.return_value = mock_query

    inv = FakeInvoiceRequest(order_ids=["ORD-001"])
    result = mod.resolve_openid(mock_db, inv)
    assert result == "oTestOpenid456"


def test_resolve_openid_no_orders():
    """order_ids 为空 → None。"""
    mock_db = MagicMock()
    inv = FakeInvoiceRequest(order_ids=[])
    result = mod.resolve_openid(mock_db, inv)
    assert result is None
    mock_db.query.assert_not_called()


def test_resolve_openid_no_payment_order():
    """有订单号但无 payment_order 记录 → None。"""
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None

    mock_db = MagicMock()
    mock_db.query.return_value = mock_query

    inv = FakeInvoiceRequest(order_ids=["ORD-NONE"])
    result = mod.resolve_openid(mock_db, inv)
    assert result is None


def test_resolve_openid_empty_openid():
    """payment_order 存在但 openid 为空 → None。"""
    mock_po = MagicMock()
    mock_po.openid = None

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = mock_po

    mock_db = MagicMock()
    mock_db.query.return_value = mock_query

    inv = FakeInvoiceRequest(order_ids=["ORD-002"])
    result = mod.resolve_openid(mock_db, inv)
    assert result is None


def test_resolve_openid_json_string_order_ids():
    """order_ids 为 JSON 字符串 → 正确解析。"""
    mock_po = MagicMock()
    mock_po.openid = "oJsonOpenid"

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = mock_po

    mock_db = MagicMock()
    mock_db.query.return_value = mock_query

    inv = FakeInvoiceRequest(order_ids=json.dumps(["ORD-JSON-001"]))
    result = mod.resolve_openid(mock_db, inv)
    assert result == "oJsonOpenid"


def test_resolve_openid_db_exception_skipped():
    """DB 查询异常 → 跳过该订单, 不抛异常。"""
    mock_query = MagicMock()
    mock_query.filter.side_effect = Exception("DB error")

    mock_db = MagicMock()
    mock_db.query.return_value = mock_query

    inv = FakeInvoiceRequest(order_ids=["ORD-ERR"])
    result = mod.resolve_openid(mock_db, inv)
    assert result is None


# ============================================================
# _invoice_order_ids 辅助函数测试
# ============================================================

def test_invoice_order_ids_list():
    """list 输入 → list 输出。"""
    inv = FakeInvoiceRequest(order_ids=["A", "B", "C"])
    assert mod._invoice_order_ids(inv) == ["A", "B", "C"]


def test_invoice_order_ids_none():
    """order_ids 为 None → 空列表。"""
    inv = FakeInvoiceRequest(order_ids=None)
    assert mod._invoice_order_ids(inv) == []


def test_invoice_order_ids_invalid_json():
    """无效 JSON 字符串 → 空列表。"""
    inv = FakeInvoiceRequest(order_ids="not-json")
    assert mod._invoice_order_ids(inv) == []


# ============================================================
# invalidate_access_token 测试
# ============================================================

def test_invalidate_access_token():
    """invalidate 后缓存为空。"""
    mod._token_cache["value"] = "some_token"
    mod._token_cache["expires_at"] = time.time() + 9999
    mod.invalidate_access_token()
    assert mod._token_cache["value"] is None
    assert mod._token_cache["expires_at"] == 0.0
