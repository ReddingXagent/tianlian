# -*- coding: utf-8 -*-
"""
出站 Webhook 管理测试 (SPEC §2.6)

覆盖:
- CRUD 全流程 (创建/列表/详情/更新/删除)
- 事件类型校验
- 启用/停用
- 测试发送 (mocked)
- 投递日志查询
"""
import ipaddress
import json
import socket
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.models.webhook import WebhookDelivery


@pytest.fixture(autouse=True)
def _mock_dns(monkeypatch):
    """默认 mock DNS 解析,确保测试确定性(不依赖真实网络)。

    - IP 字面量(含 IPv6)原样返回,交由 ipaddress 属性判定内网/公网
    - 域名一律解析为公网 1.1.1.1,模拟公网回调放行
    单测需要模拟内网解析时,在测试内再次 monkeypatch 覆盖即可。
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


class TestWebhooks:
    """Webhook 管理 CRUD + 测试发送 + 投递日志"""

    def test_create_webhook(self, client):
        resp = client.post("/api/v1/webhooks", json={
            "name": "告警回调",
            "url": "https://example.com/hooks/alert",
            "event_types": ["alert", "ticket"],
            "secret": "my-secret-key",
            "retry_count": 5,
            "retry_interval": 30,
            "timeout": 15,
            "enabled": True,
            "description": "用于接收告警和工单事件",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] > 0
        assert data["name"] == "告警回调"
        assert data["url"] == "https://example.com/hooks/alert"
        assert "alert" in data["event_types"]
        assert "ticket" in data["event_types"]
        assert data["secret"] == "my-secret-key"
        assert data["retry_count"] == 5
        assert data["enabled"] is True
        assert data["description"] == "用于接收告警和工单事件"

    def test_create_default_values(self, client):
        resp = client.post("/api/v1/webhooks", json={
            "name": "默认配置",
            "url": "https://example.com/hook",
            "event_types": [],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["retry_count"] == 3
        assert data["retry_interval"] == 60
        assert data["timeout"] == 10
        assert data["enabled"] is True

    def test_invalid_event_type(self, client):
        resp = client.post("/api/v1/webhooks", json={
            "name": "bad",
            "url": "https://example.com/hook",
            "event_types": ["invalid_type"],
        })
        assert resp.status_code == 400

    def test_list_and_filter(self, client):
        # Create multiple
        client.post("/api/v1/webhooks", json={
            "name": "告警Hook", "url": "https://a.com/h",
            "event_types": ["alert"], "enabled": True,
        })
        client.post("/api/v1/webhooks", json={
            "name": "订单Hook", "url": "https://b.com/h",
            "event_types": ["order"], "enabled": False,
        })
        client.post("/api/v1/webhooks", json={
            "name": "设备Hook", "url": "https://c.com/h",
            "event_types": ["device"], "enabled": True,
        })

        # 全量
        resp = client.get("/api/v1/webhooks")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 3

        # 按启用筛选
        resp = client.get("/api/v1/webhooks?enabled=true")
        items = resp.json()["data"]["items"]
        assert all(i["enabled"] is True for i in items)
        assert resp.json()["data"]["total"] >= 2

        # 按事件类型筛选
        resp = client.get("/api/v1/webhooks?event_type=order")
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert "order" in items[0]["event_types"]

        # 关键字搜索
        resp = client.get("/api/v1/webhooks?keyword=告警")
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["name"] == "告警Hook"

    def test_get_detail(self, client):
        r = client.post("/api/v1/webhooks", json={
            "name": "详情测试", "url": "https://d.com/h",
            "event_types": ["alert"],
        })
        wid = r.json()["data"]["id"]

        resp = client.get(f"/api/v1/webhooks/{wid}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == wid
        assert data["name"] == "详情测试"

    def test_get_404(self, client):
        assert client.get("/api/v1/webhooks/99999").status_code == 404

    def test_update(self, client):
        r = client.post("/api/v1/webhooks", json={
            "name": "原名", "url": "https://e.com/h",
            "event_types": ["alert"],
        })
        wid = r.json()["data"]["id"]

        resp = client.put(f"/api/v1/webhooks/{wid}", json={
            "name": "新名称",
            "url": "https://f.com/new",
            "event_types": ["alert", "device"],
            "retry_count": 7,
            "timeout": 30,
            "description": "更新后的描述",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "新名称"
        assert data["url"] == "https://f.com/new"
        assert "device" in data["event_types"]
        assert data["retry_count"] == 7
        assert data["timeout"] == 30
        assert data["description"] == "更新后的描述"

    def test_update_invalid_event_type(self, client):
        r = client.post("/api/v1/webhooks", json={
            "name": "test", "url": "https://g.com/h",
            "event_types": ["alert"],
        })
        wid = r.json()["data"]["id"]
        resp = client.put(f"/api/v1/webhooks/{wid}", json={
            "event_types": ["bad_type"],
        })
        assert resp.status_code == 400

    def test_update_404(self, client):
        assert client.put("/api/v1/webhooks/99999", json={"name": "x"}).status_code == 404

    def test_toggle(self, client):
        r = client.post("/api/v1/webhooks", json={
            "name": "toggle", "url": "https://h.com/h",
            "event_types": ["alert"], "enabled": True,
        })
        wid = r.json()["data"]["id"]

        # 停用
        resp = client.put(f"/api/v1/webhooks/{wid}/toggle", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["data"]["enabled"] is False

        # 启用
        resp = client.put(f"/api/v1/webhooks/{wid}/toggle", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["data"]["enabled"] is True

    def test_toggle_404(self, client):
        assert client.put("/api/v1/webhooks/99999/toggle", json={"enabled": False}).status_code == 404

    def test_delete(self, client):
        r = client.post("/api/v1/webhooks", json={
            "name": "todelete", "url": "https://i.com/h",
            "event_types": ["alert"],
        })
        wid = r.json()["data"]["id"]

        assert client.delete(f"/api/v1/webhooks/{wid}").status_code == 200
        assert client.get(f"/api/v1/webhooks/{wid}").status_code == 404

    def test_delete_404(self, client):
        assert client.delete("/api/v1/webhooks/99999").status_code == 404

    def test_test_send_mocked(self, client):
        """测试发送 — mock httpx.AsyncClient 避免真实网络请求"""
        r = client.post("/api/v1/webhooks", json={
            "name": "test-hook", "url": "https://j.com/hook",
            "event_types": ["alert"], "secret": "sign-secret",
        })
        wid = r.json()["data"]["id"]

        # Mock the httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"ok": true}'

        with patch("app.api.v1.webhooks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            resp = client.post(f"/api/v1/webhooks/{wid}/test")
            assert resp.status_code == 200
            # 卡 e7d88c10:投递后台化,响应仅返回 queued,结果查投递日志
            assert resp.json()["data"]["status"] == "queued"
            data = client.get(f"/api/v1/webhooks/{wid}/deliveries").json()["data"]["items"][0]
            assert data["status"] == "success"
            assert data["status_code"] == 200
            assert data["event_type"] == "test"
            assert data["duration_ms"] >= 0

    def test_test_send_404(self, client):
        assert client.post("/api/v1/webhooks/99999/test").status_code == 404

    def test_deliveries_log(self, client):
        # Create webhook + send a mocked test -> should produce a delivery record
        # retry_count=0 避免退避等待;500 语义修复后属可重试,置 0 保持单次
        r = client.post("/api/v1/webhooks", json={
            "name": "delivery-test", "url": "https://k.com/h",
            "event_types": ["alert"],
            "retry_count": 0,
        })
        wid = r.json()["data"]["id"]

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("app.api.v1.webhooks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            client.post(f"/api/v1/webhooks/{wid}/test")

        # Query deliveries
        resp = client.get(f"/api/v1/webhooks/{wid}/deliveries")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["webhook_id"] == wid
        assert item["status"] == "failed"  # 500 -> failed
        assert item["status_code"] == 500

    def test_deliveries_filter_status(self, client):
        r = client.post("/api/v1/webhooks", json={
            "name": "filter-test", "url": "https://l.com/h",
            "event_types": ["alert"],
        })
        wid = r.json()["data"]["id"]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("app.api.v1.webhooks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            client.post(f"/api/v1/webhooks/{wid}/test")

        # Filter by success
        resp = client.get(f"/api/v1/webhooks/{wid}/deliveries?status=success")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "success"

        # Filter by failed → should be empty
        resp = client.get(f"/api/v1/webhooks/{wid}/deliveries?status=failed")
        assert resp.json()["data"]["total"] == 0

    def test_deliveries_404(self, client):
        assert client.get("/api/v1/webhooks/99999/deliveries").status_code == 404

    def test_deliveries_invalid_status(self, client):
        r = client.post("/api/v1/webhooks", json={
            "name": "valid", "url": "https://m.com/h",
            "event_types": [],
        })
        wid = r.json()["data"]["id"]
        resp = client.get(f"/api/v1/webhooks/{wid}/deliveries?status=invalid")
        assert resp.status_code == 400

    def test_cascade_delete_deliveries(self, client):
        """删除 webhook 时级联删除投递日志"""
        r = client.post("/api/v1/webhooks", json={
            "name": "cascade", "url": "https://n.com/h",
            "event_types": ["alert"],
        })
        wid = r.json()["data"]["id"]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("app.api.v1.webhooks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            client.post(f"/api/v1/webhooks/{wid}/test")

        # Delete webhook
        client.delete(f"/api/v1/webhooks/{wid}")
        # Deliveries endpoint should 404
        assert client.get(f"/api/v1/webhooks/{wid}/deliveries").status_code == 404


class TestWebhookUrlSafety:
    """SSRF 防护:回调 URL scheme/host 校验 (卡 310ac90a)"""

    @pytest.mark.parametrize("bad_url", [
        "http://169.254.169.254/latest/meta-data/",  # 云元数据 (link-local) → 完整读 SSRF
        "http://127.0.0.1/",                          # IPv4 loopback 127/8
        "http://127.0.0.1:8080/admin",
        "http://10.0.0.1/",                           # private 10/8
        "http://10.255.255.255/",
        "http://192.168.1.1/",                        # private 192.168/16
        "http://172.16.0.1/",                         # private 172.16/12
        "http://localhost/",                          # localhost 字面量
        "http://localhost:8080/",
        "file:///etc/passwd",                         # 非 http(s) scheme
        "ftp://1.1.1.1/",                             # 非 http(s) scheme
        "gopher://127.0.0.1/",
        "http://[::1]/",                              # IPv6 loopback
        "http://[fc00::1]/",                          # IPv6 ULA fc00::/7
        "http://[fe80::1]/",                          # IPv6 link-local
        "javascript:alert(1)",                        # 非 http(s) scheme
        "not-a-url",                                  # 缺主机名
    ])
    def test_create_rejects_unsafe_url(self, client, bad_url):
        resp = client.post("/api/v1/webhooks", json={
            "name": "evil", "url": bad_url, "event_types": ["alert"],
        })
        assert resp.status_code == 422, f"应拒绝不安全 URL: {bad_url}"

    def test_create_rejects_dns_failure(self, client, monkeypatch):
        """DNS 解析失败也拒绝(默认拒绝,不留隐式放行)"""
        from app.core import url_safety
        import socket as _socket

        def raise_gaierror(host, *args, **kwargs):
            raise _socket.gaierror("DNS failed")

        monkeypatch.setattr(url_safety.socket, "getaddrinfo", raise_gaierror)
        resp = client.post("/api/v1/webhooks", json={
            "name": "nodns", "url": "https://nonexistent.invalid/hook", "event_types": [],
        })
        assert resp.status_code == 422

    def test_create_accepts_public_https(self, client):
        # 域名经 autouse mock 解析为公网 1.1.1.1 → 放行
        resp = client.post("/api/v1/webhooks", json={
            "name": "ok", "url": "https://example.com/hooks/alert", "event_types": ["alert"],
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["url"] == "https://example.com/hooks/alert"

    def test_create_accepts_public_ip_literal(self, client):
        # 公网 IP 字面量(autouse mock 原样返回)→ 放行
        resp = client.post("/api/v1/webhooks", json={
            "name": "ok-ip", "url": "https://8.8.8.8/hook", "event_types": [],
        })
        assert resp.status_code == 200

    def test_update_rejects_unsafe_url(self, client):
        r = client.post("/api/v1/webhooks", json={
            "name": "u", "url": "https://example.com/h", "event_types": ["alert"],
        })
        wid = r.json()["data"]["id"]
        resp = client.put(f"/api/v1/webhooks/{wid}", json={"url": "http://169.254.169.254/"})
        assert resp.status_code == 422

    def test_update_none_url_passes(self, client):
        # url 未提供(None)不触发校验,其余字段正常更新
        r = client.post("/api/v1/webhooks", json={
            "name": "u2", "url": "https://example.com/h", "event_types": ["alert"],
        })
        wid = r.json()["data"]["id"]
        resp = client.put(f"/api/v1/webhooks/{wid}", json={"name": "renamed"})
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "renamed"

    def test_update_accepts_public_url(self, client):
        r = client.post("/api/v1/webhooks", json={
            "name": "u3", "url": "https://example.com/h", "event_types": ["alert"],
        })
        wid = r.json()["data"]["id"]
        resp = client.put(f"/api/v1/webhooks/{wid}", json={"url": "https://example.com/new"})
        assert resp.status_code == 200
        assert resp.json()["data"]["url"] == "https://example.com/new"


class TestWebhookDeliverSSRFGuard:
    """_deliver 发送前二次校验:防 DNS 重绑定 / 数据投毒 (卡 310ac90a)"""

    def test_deliver_blocks_metadata_url_no_egress(self, client, db_session):
        """库里 URL 已指向云元数据(模拟数据投毒/DNS重绑定),二次校验拦截且不外发"""
        from app.models.webhook import Webhook

        wh = Webhook(
            name="poisoned",
            url="http://169.254.169.254/latest/meta-data/",
            event_types='["alert"]',
            enabled=True,
        )
        db_session.add(wh)
        db_session.commit()
        db_session.refresh(wh)
        wid = wh.id

        with patch("app.api.v1.webhooks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock()
            mock_client_cls.return_value = mock_client

            resp = client.post(f"/api/v1/webhooks/{wid}/test")

        # 接口本身正常返回(queued),后台投递被标失败
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "queued"
        data = client.get(f"/api/v1/webhooks/{wid}/deliveries").json()["data"]["items"][0]
        assert data["status"] == "failed"
        assert data["error_message"]
        assert "安全校验失败" in data["error_message"]
        # 关键:二次校验在发送前拦截,httpx.post 绝不应被调用(零外发)
        mock_client.post.assert_not_called()

    def test_deliver_passes_public_url(self, client):
        """公网 URL 二次校验放行,正常发送(mock httpx)"""
        r = client.post("/api/v1/webhooks", json={
            "name": "ok", "url": "https://example.com/hook", "event_types": ["alert"],
        })
        wid = r.json()["data"]["id"]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"
        with patch("app.api.v1.webhooks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            resp = client.post(f"/api/v1/webhooks/{wid}/test")

        assert resp.status_code == 200
        items = client.get(f"/api/v1/webhooks/{wid}/deliveries").json()["data"]["items"]
        assert items[0]["status"] == "success"
        mock_client.post.assert_called_once()


class TestWebhookRetry:
    """重试契约 (卡 952e2d5b):_deliver 按 retry_count 重试,5xx/网络异常重试,4xx 终态"""

    @staticmethod
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

    @staticmethod
    def _resp(code, text="resp"):
        r = MagicMock()
        r.status_code = code
        r.text = text
        return r

    def _create(self, client, retry_count, retry_interval=1):
        r = client.post("/api/v1/webhooks", json={
            "name": "retry-hook", "url": "https://retry.example.com/hook",
            "event_types": ["alert"], "retry_count": retry_count,
            "retry_interval": retry_interval,
        })
        assert r.status_code == 200
        return r.json()["data"]["id"]

    @staticmethod
    def _latest_delivery(client, wid):
        # 卡 e7d88c10:test 端点后台投递,结果经投递日志查询
        items = client.get(f"/api/v1/webhooks/{wid}/deliveries").json()["data"]["items"]
        assert items, "后台投递未产出日志记录"
        return items[0]

    def test_retry_then_success(self, client):
        """500,500 → 200:post 共调用 retry_count+1 次,最终 success,attempt 递增"""
        wid = self._create(client, retry_count=2)

        mock_client_cls, mock_client = self._mock_httpx([
            self._resp(500), self._resp(500), self._resp(200, '{"ok":1}'),
        ])
        try:
            with patch("app.api.v1.webhooks.asyncio.sleep", new=AsyncMock()) as mock_sleep:
                resp = client.post(f"/api/v1/webhooks/{wid}/test")
        finally:
            mock_client_cls.stop()

        assert resp.status_code == 200
        data = self._latest_delivery(client, wid)
        assert data["status"] == "success"
        assert data["status_code"] == 200
        assert data["attempt"] == 3
        assert mock_client.post.await_count == 3  # retry_count(2) + 1
        assert mock_sleep.await_count == 2  # 两次退避

    def test_network_exception_retry_then_success(self, client):
        """网络异常 → 重试成功:post 调用 retry_count+1 次"""
        wid = self._create(client, retry_count=1)

        mock_client_cls, mock_client = self._mock_httpx([
            httpx.ConnectError("conn refused"), self._resp(200),
        ])
        try:
            with patch("app.api.v1.webhooks.asyncio.sleep", new=AsyncMock()):
                resp = client.post(f"/api/v1/webhooks/{wid}/test")
        finally:
            mock_client_cls.stop()

        assert resp.status_code == 200
        data = self._latest_delivery(client, wid)
        assert data["status"] == "success"
        assert mock_client.post.await_count == 2

    def test_4xx_no_retry(self, client):
        """403 终态失败:post 仅调用 1 次"""
        wid = self._create(client, retry_count=3)

        mock_client_cls, mock_client = self._mock_httpx([self._resp(403, "Forbidden")])
        try:
            resp = client.post(f"/api/v1/webhooks/{wid}/test")
        finally:
            mock_client_cls.stop()

        assert resp.status_code == 200
        data = self._latest_delivery(client, wid)
        assert data["status"] == "failed"
        assert data["status_code"] == 403
        assert mock_client.post.await_count == 1

    def test_retry_count_zero_single_post(self, client):
        """retry_count=0:单次调用,行为与现状一致"""
        wid = self._create(client, retry_count=0)

        mock_client_cls, mock_client = self._mock_httpx([self._resp(500)])
        try:
            resp = client.post(f"/api/v1/webhooks/{wid}/test")
        finally:
            mock_client_cls.stop()

        assert resp.status_code == 200
        data = self._latest_delivery(client, wid)
        assert data["status"] == "failed"
        assert data["status_code"] == 500
        assert mock_client.post.await_count == 1

    def test_exhausted_retries_failed(self, client):
        """全部 500 重试耗尽:post 调用 retry_count+1 次,终态 failed,attempt=N+1"""
        wid = self._create(client, retry_count=2)

        mock_client_cls, mock_client = self._mock_httpx([
            self._resp(500), self._resp(500), self._resp(500),
        ])
        try:
            with patch("app.api.v1.webhooks.asyncio.sleep", new=AsyncMock()):
                resp = client.post(f"/api/v1/webhooks/{wid}/test")
        finally:
            mock_client_cls.stop()

        assert resp.status_code == 200
        data = self._latest_delivery(client, wid)
        assert data["status"] == "failed"
        assert data["status_code"] == 500
        assert data["attempt"] == 3
        assert mock_client.post.await_count == 3

    def test_retrying_status_observable(self, client, db_session, tmp_path):
        """重试期间 delivery.status 出现 retrying(退避时刻读库捕获中途状态)"""
        import asyncio
        import sqlite3
        from app.api.v1.webhooks import _deliver
        from app.models.webhook import Webhook

        wh = Webhook(
            name="retrying-obs", url="https://obs.example.com/hook",
            event_types='["alert"]', enabled=True, retry_count=1, retry_interval=1,
        )
        db_session.add(wh)
        db_session.commit()
        db_session.refresh(wh)

        db_file = str(tmp_path / "obs.db")
        seen_statuses = []

        async def fake_sleep(seconds):
            # 退避时刻同步读同一 sqlite 文件:retrying 状态在 sleep 前 commit
            conn = sqlite3.connect(db_file)
            try:
                row = conn.execute(
                    "SELECT status, attempt FROM webhook_deliveries "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()
                seen_statuses.append(row)
            finally:
                conn.close()

        mock_client_cls, mock_client = self._mock_httpx([
            self._resp(500), self._resp(200),
        ])
        try:
            with patch("app.api.v1.webhooks.asyncio.sleep", new=fake_sleep):
                async def run():
                    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
                    from sqlalchemy.orm import sessionmaker
                    from app.core.database import Base
                    engine = create_async_engine(
                        f"sqlite+aiosqlite:///{db_file}", future=True)
                    async_session = sessionmaker(
                        engine, class_=AsyncSession, expire_on_commit=False)
                    async with engine.begin() as conn:
                        await conn.run_sync(Base.metadata.create_all)
                    async with async_session() as adb:
                        await _deliver(wh, {"x": 1}, adb, event_type="test")
                    await engine.dispose()
                asyncio.run(run())
        finally:
            mock_client_cls.stop()

        assert seen_statuses == [("retrying", 1)]
        assert mock_client.post.await_count == 2


class TestSignatureTimestampBinding:
    """HMAC 签名绑定时间戳 (防重放): 签名 = HMAC-SHA256(secret, "{ts}.{body}")"""

    def _create_webhook(self, client, secret=None):
        payload = {
            "name": "sig-hook", "url": "https://sig.example.com/h",
            "event_types": ["alert"], "retry_count": 0,
        }
        if secret is not None:
            payload["secret"] = secret
        r = client.post("/api/v1/webhooks", json=payload)
        assert r.status_code == 200, r.text
        return r.json()["data"]["id"]

    def _mock_post_and_test(self, client, wid):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"ok": true}'
        with patch("app.api.v1.webhooks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            resp = client.post(f"/api/v1/webhooks/{wid}/test")
            assert resp.status_code == 200, resp.text
        kwargs = mock_client.post.await_args.kwargs
        return kwargs["headers"], kwargs["content"]

    def test_signed_headers_match_hmac(self, client):
        """有 secret: 带 Timestamp/Signature/Version 头, 签名与 HMAC 对拍"""
        import hashlib
        import hmac as hmac_mod
        wid = self._create_webhook(client, secret="sec-123")
        headers, body = self._mock_post_and_test(client, wid)

        ts = headers["X-Webhook-Timestamp"]
        assert ts.isdigit()  # 纯数字秒级时间戳
        assert headers["X-Webhook-Signature-Version"] == "v1"
        expected = hmac_mod.new(b"sec-123", f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
        assert headers["X-Webhook-Signature"] == expected

    def test_no_secret_no_signature_headers(self, client):
        """无 secret: 不发送任何签名/时间戳头"""
        wid = self._create_webhook(client)
        headers, _ = self._mock_post_and_test(client, wid)
        assert "X-Webhook-Signature" not in headers
        assert "X-Webhook-Timestamp" not in headers

    def test_same_body_different_ts_different_sig(self):
        """同 body 不同 timestamp → 签名不同 (防重放核心)"""
        from app.api.v1.webhooks import _compute_signature
        sig1 = _compute_signature("s", "1700000000", '{"a":1}')
        sig2 = _compute_signature("s", "1700000001", '{"a":1}')
        assert sig1 != sig2


class TestTestWebhookNonBlockingE7D88C10:
    """卡 e7d88c10:test_webhook 不得在请求内 await _deliver 重试循环。

    根因:retry_count(0-10)+retry_interval(1-3600s) 合法配置下,内联 await 最长挂起 ~10h。
    契约:端点将 _deliver 移入 background_tasks,立即返回 queued;
    投递结果经 GET /{id}/deliveries 查询。
    """

    def _create(self, client, retry_count, retry_interval):
        r = client.post("/api/v1/webhooks", json={
            "name": "nb-hook", "url": "https://nb.example.com/hook",
            "event_types": ["alert"],
            "retry_count": retry_count, "retry_interval": retry_interval,
        })
        assert r.status_code == 200
        return r.json()["data"]["id"]

    def test_returns_queued_immediately_under_large_retry_config(self, client):
        """retry_count=10/interval=3600 极端配置:端点立即返回 queued,不携带重试退避"""
        wid = self._create(client, retry_count=10, retry_interval=3600)

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "boom"
        with patch("app.api.v1.webhooks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client
            # 后台退避 sleep 一并 mock,使 TestClient 内联执行的后台任务快速完成
            with patch("app.api.v1.webhooks.asyncio.sleep", new=AsyncMock()):
                resp = client.post(f"/api/v1/webhooks/{wid}/test")

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "queued"
        # 投递仍由后台完成(退避全 mock 后即时结束),结果可经日志查询
        log = client.get(f"/api/v1/webhooks/{wid}/deliveries").json()["data"]
        assert log["total"] == 1
        assert log["items"][0]["status"] == "failed"

    def test_deliver_scheduled_via_background_not_inline_await(self, client, monkeypatch):
        """_deliver 必须经 background_tasks 调度:响应体构造于投递之前(queued),而非内联结果"""
        wid = self._create(client, retry_count=0, retry_interval=1)
        deliver_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("app.api.v1.webhooks._deliver", deliver_mock)

        resp = client.post(f"/api/v1/webhooks/{wid}/test")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "queued"
        # TestClient 等待 ASGI 完成,后台任务此时已执行
        deliver_mock.assert_awaited_once()
        assert deliver_mock.await_args.kwargs.get("event_type") == "test"
