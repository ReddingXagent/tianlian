# -*- coding: utf-8 -*-
"""
出站 Webhook 重试链时间戳/签名新鲜度 + 投递幂等 ID (卡 211f5c97)

缺陷:
1. _deliver 曾在 for attempt 循环前一次性构建 headers,重试链全程复用同一
   ts/签名 — 接收方按 docstring 契约校验时间戳新鲜度(拒绝过期时间戳)必然
   拒绝晚到重试(合法配置下重试可晚至 retry_count×retry_interval≈10h),
   重试机制自毁。
2. headers 无投递幂等 ID:"服务端已处理但响应丢失"的网络异常重试会让
   接收方重复处理同一事件(重复扣费/重复建单风险)。

契约:
- 每个 attempt 重新计算 X-Webhook-Timestamp + X-Webhook-Signature
  (body 不变仅 ts 变,签名继续覆盖 "{ts}.{body}")
- 每个 attempt 携带 X-Webhook-Delivery-Id: {delivery.id} (明文,跨 attempt 一致)
"""
import ipaddress
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_dns(monkeypatch):
    """默认 mock DNS 解析,确保测试确定性(不依赖真实网络)。

    与 test_webhooks.py 同形态:IP 字面量原样返回,域名一律解析为公网
    1.1.1.1 模拟公网回调放行。覆盖创建时与发送前二次校验两处 DNS 查询。
    """
    from app.core import url_safety

    def fake_getaddrinfo(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)  # 合法 IP 字面量 → 原样返回
            ip = host
        except ValueError:
            ip = "1.1.1.1"  # 域名 → 公网 IP
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)


class _FakeTime:
    """可控时钟(卡 211f5c97):time() 每次调用严格 +1s,monotonic() 平滑递增。

    替换 app.api.v1.webhooks.time 模块引用,使 _deliver 内的
    time.time()/time.monotonic() 全部走假时钟 — 两次 attempt 之间无需真实
    经过 retry_interval 秒即可断言时间戳严格递增。
    """

    def __init__(self, base=1_700_000_000):
        self._base = base
        self._n = 0
        self._mono = 100.0

    def time(self):
        self._n += 1
        return float(self._base + self._n)

    def monotonic(self):
        self._mono += 0.05
        return self._mono


def _resp(code, text="resp"):
    r = MagicMock()
    r.status_code = code
    r.text = text
    return r


def _mock_httpx(responses):
    """构造 httpx.AsyncClient mock。responses 为每次 post 的返回值或异常。"""
    mock_client_cls = patch("app.api.v1.webhooks.httpx.AsyncClient")
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=responses)
    cm = mock_client_cls.start()
    cm.return_value = mock_client
    return mock_client_cls, mock_client


def _create_hook(client, secret=None, retry_count=2):
    payload = {
        "name": "retry-sig-hook",
        "url": "https://retry-sig.example.com/hook",
        "event_types": ["alert"],
        "retry_count": retry_count,
        "retry_interval": 1,  # 合法最小值
    }
    if secret is not None:
        payload["secret"] = secret
    r = client.post("/api/v1/webhooks", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _run_delivery(client, wid, responses, fake_time):
    """触发测试投递(后台任务经 TestClient 内联完成),返回 (post mock, 投递记录)。"""
    mock_client_cls, mock_client = _mock_httpx(responses)
    try:
        with patch("app.api.v1.webhooks.asyncio.sleep", new=AsyncMock()):
            with patch("app.api.v1.webhooks.time", fake_time):
                resp = client.post(f"/api/v1/webhooks/{wid}/test")
                assert resp.status_code == 200, resp.text
    finally:
        mock_client_cls.stop()
    items = client.get(f"/api/v1/webhooks/{wid}/deliveries").json()["data"]["items"]
    assert items, "后台投递未产出日志记录"
    return mock_client, items[0]


class TestRetrySignatureFreshness211f5c97:
    """缺陷1:重试链 ts/签名必须在每个 attempt 重算,不得循环外一次构建"""

    def test_second_attempt_timestamp_strictly_greater(self, client):
        """① attempt2 的 X-Webhook-Timestamp 严格大于 attempt1(重试不携带过期时间戳)"""
        wid = _create_hook(client, secret="sec-211f5c97", retry_count=1)
        mock_client, delivery = _run_delivery(
            client, wid,
            [_resp(500), _resp(200, '{"ok":1}')],
            _FakeTime(),
        )
        assert mock_client.post.await_count == 2
        h1 = mock_client.post.await_args_list[0].kwargs["headers"]
        h2 = mock_client.post.await_args_list[1].kwargs["headers"]
        ts1, ts2 = h1["X-Webhook-Timestamp"], h2["X-Webhook-Timestamp"]
        assert ts1.isdigit() and ts2.isdigit()
        assert int(ts2) > int(ts1), (
            f"重试链时间戳冻结: attempt1 ts={ts1}, attempt2 ts={ts2}"
        )
        assert delivery["status"] == "success"

    def test_signature_tracks_timestamp_per_attempt(self, client):
        """③ 签名对 ts 敏感:每个 attempt 的签名 == HMAC(secret, "{ts_i}.{body}"),互不相同"""
        from app.api.v1.webhooks import _compute_signature

        wid = _create_hook(client, secret="sec-211f5c97", retry_count=2)
        mock_client, delivery = _run_delivery(
            client, wid,
            [_resp(500), _resp(500), _resp(200)],
            _FakeTime(),
        )
        assert mock_client.post.await_count == 3

        sigs, tss, bodies = [], [], []
        for call in mock_client.post.await_args_list:
            h = call.kwargs["headers"]
            sigs.append(h["X-Webhook-Signature"])
            tss.append(h["X-Webhook-Timestamp"])
            bodies.append(call.kwargs["content"])

        assert len(set(tss)) == 3, "三次 attempt 时间戳应互不相同"
        assert len(set(sigs)) == 3, "时间戳不同则签名必须不同(签名对 ts 敏感)"
        # 每个 attempt 的签名与该次的 ts/body 独立对拍
        for ts, sig, body in zip(tss, sigs, bodies):
            assert sig == _compute_signature("sec-211f5c97", ts, body)
        # body 不变(仅 ts 变)
        assert len(set(bodies)) == 1
        assert delivery["status"] == "success"

    def test_retry_timestamps_increase_over_long_chain(self, client):
        """多次重试(500×3 后成功)全链时间戳严格递增"""
        wid = _create_hook(client, secret="sec-211f5c97", retry_count=3)
        mock_client, delivery = _run_delivery(
            client, wid,
            [_resp(500)] * 3 + [_resp(200)],
            _FakeTime(),
        )
        assert mock_client.post.await_count == 4
        tss = [c.kwargs["headers"]["X-Webhook-Timestamp"]
               for c in mock_client.post.await_args_list]
        assert all(int(b) > int(a) for a, b in zip(tss, tss[1:])), tss
        assert delivery["status"] == "success"


class TestDeliveryIdempotencyId211f5c97:
    """缺陷2:投递幂等 ID — 接收方凭 X-Webhook-Delivery-Id 去重响应丢失重试"""

    def test_delivery_id_present_and_stable_on_every_attempt(self, client):
        """② 每次 attempt 均带 X-Webhook-Delivery-Id,值一致且 == WebhookDelivery.id"""
        wid = _create_hook(client, secret="sec-211f5c97", retry_count=1)
        mock_client, delivery = _run_delivery(
            client, wid,
            [_resp(500), _resp(200)],
            _FakeTime(),
        )
        assert mock_client.post.await_count == 2
        ids = []
        for call in mock_client.post.await_args_list:
            h = call.kwargs["headers"]
            assert "X-Webhook-Delivery-Id" in h, "每个 attempt 必须携带投递幂等 ID"
            ids.append(h["X-Webhook-Delivery-Id"])
            # 既有接收方兼容:基础头语义不变
            assert h["Content-Type"] == "application/json"
        assert ids[0] == ids[1], "同一次投递的幂等 ID 跨 attempt 必须一致"
        assert ids[0] == str(delivery["id"]), "幂等 ID 必须对应 WebhookDelivery.id"

    def test_no_secret_still_carries_delivery_id(self, client):
        """无 secret:签名头缺席,但幂等 ID 头仍在(去重能力不依赖签名配置)"""
        wid = _create_hook(client, retry_count=0)
        mock_client, delivery = _run_delivery(
            client, wid, [_resp(200)], _FakeTime(),
        )
        assert mock_client.post.await_count == 1
        h = mock_client.post.await_args.kwargs["headers"]
        assert "X-Webhook-Signature" not in h
        assert "X-Webhook-Timestamp" not in h
        assert h["X-Webhook-Delivery-Id"] == str(delivery["id"])
