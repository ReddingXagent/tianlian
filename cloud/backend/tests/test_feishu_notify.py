"""
Phase19 IM告警通知服务测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.im_notify import IMNotifyService, im_notify_service
from app.models.alarm import Alarm, AlarmLevel


@pytest.fixture
def im_service():
    """IM通知服务实例"""
    service = IMNotifyService()
    service.webhook_url = "https://open.im.cn/open-apis/bot/v2/hook/test-webhook"
    return service


@pytest.fixture
def sample_prometheus_alert():
    """Prometheus 告警示例"""
    return {
        "status": "firing",
        "labels": {
            "alertname": "HighErrorRate",
            "severity": "critical",
            "instance": "backend:8000",
            "job": "tianlian-api"
        },
        "annotations": {
            "summary": "API 错误率超过 5%",
            "description": "过去5分钟错误率达到 8.3%"
        },
        "startsAt": "2026-05-31T13:00:00Z",
        "endsAt": ""
    }


@pytest.fixture
def sample_warning_alert():
    """警告级别告警示例"""
    return {
        "status": "firing",
        "labels": {
            "alertname": "HighLatency",
            "severity": "warning",
            "instance": "frontend:3000"
        },
        "annotations": {
            "summary": "响应延迟偏高"
        },
        "startsAt": "2026-05-31T13:05:00Z"
    }


@pytest.fixture
def sample_resolved_alert():
    """已恢复告警示例"""
    return {
        "status": "resolved",
        "labels": {
            "alertname": "BackendDown",
            "severity": "critical",
            "instance": "backend:8000"
        },
        "annotations": {
            "summary": "后端服务已恢复"
        },
        "startsAt": "2026-05-31T12:00:00Z",
        "endsAt": "2026-05-31T13:10:00Z"
    }


class TestIMNotifyService:
    """IM通知服务测试"""

    def test_format_prometheus_alert_firing(self, im_service, sample_prometheus_alert):
        """测试格式化触发状态的 Prometheus 告警"""
        card = im_service.format_prometheus_alert(sample_prometheus_alert)

        assert card["msg_type"] == "interactive"
        assert "card" in card

        header = card["card"]["header"]
        assert "告警触发" in header["title"]["content"]
        assert header["template"] == "red"

        # 检查元素包含关键信息
        elements = card["card"]["elements"]
        assert len(elements) > 0

        # 检查摘要字段
        found_summary = False
        for elem in elements:
            if elem.get("tag") == "div":
                text = elem.get("text", {}).get("content", "")
                if "API 错误率超过 5%" in text:
                    found_summary = True
        assert found_summary

    def test_format_prometheus_alert_resolved(self, im_service, sample_resolved_alert):
        """测试格式化已恢复状态的 Prometheus 告警"""
        card = im_service.format_prometheus_alert(sample_resolved_alert)

        header = card["card"]["header"]
        assert "已恢复" in header["title"]["content"]
        assert header["template"] == "green"

    def test_format_alarm_message_critical(self, im_service):
        """测试格式化系统内部严重告警"""
        alarm = Alarm(
            id=1,
            content="逆变器过温警告",
            level=AlarmLevel.CRITICAL,
            device_id=5,
            fault_code="E001",
            created_at=datetime.now()
        )

        card = im_service.format_alarm_message(alarm)

        assert card["msg_type"] == "interactive"
        header = card["card"]["header"]
        assert header["template"] == "red"
        assert "严重" in header["title"]["content"] or "告警" in header["title"]["content"]

    def test_format_alarm_message_warning(self, im_service):
        """测试格式化系统内部警告"""
        alarm = Alarm(
            id=2,
            content="电池 SOC 偏低",
            level=AlarmLevel.WARNING,
            device_id=3,
            created_at=datetime.now()
        )

        card = im_service.format_alarm_message(alarm)

        header = card["card"]["header"]
        assert header["template"] == "yellow"

    def test_build_summary_card(self, im_service):
        """测试构建告警汇总卡片"""
        warning_alerts = [
            {"labels": {"alertname": "HighLatency", "instance": "api:8000"}},
            {"labels": {"alertname": "DBSlowQuery", "instance": "db:5432"}},
        ]
        info_alerts = [
            {"labels": {"alertname": "InfoTest"}},
        ]

        card = im_service._build_summary_card("firing", warning_alerts, info_alerts)

        assert card["msg_type"] == "interactive"
        elements = card["card"]["elements"]

        # 检查警告部分
        found_warning = False
        for elem in elements:
            if elem.get("tag") == "div":
                text = elem.get("text", {}).get("content", "")
                if "警告" in text:
                    found_warning = True
        assert found_warning

    @pytest.mark.asyncio
    async def test_send_webhook_message_success(self, im_service):
        """测试成功发送IM Webhook 消息"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            content = {"msg_type": "text", "content": {"text": "test"}}
            result = await im_service.send_webhook_message(content)

            assert result is True

    @pytest.mark.asyncio
    async def test_send_webhook_message_no_config(self):
        """测试未配置 Webhook URL 时跳过发送"""
        service = IMNotifyService()
        service.webhook_url = None

        result = await service.send_webhook_message({"test": "data"})
        assert result is False

    @pytest.mark.asyncio
    async def test_notify_prometheus_alerts(self, im_service, sample_prometheus_alert, sample_warning_alert):
        """测试发送 Prometheus 告警通知"""
        alerts = [sample_prometheus_alert, sample_warning_alert]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await im_service.notify_prometheus_alerts("firing", alerts)

            assert result["total"] == 2
            assert result["sent"] >= 1
            assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_notify_prometheus_alerts_no_config(self, sample_prometheus_alert):
        """测试未配置时返回错误"""
        service = IMNotifyService()
        service.webhook_url = None

        result = await service.notify_prometheus_alerts("firing", [sample_prometheus_alert])
        assert result["success"] is False
        assert "未配置" in result["error"]


# ═══════════════════════════════════════════════════════════════════
# 卡 9fbc00ce: 平台级 webhook 签名 (IM_SECRET) + 5xx 重试
#
# 缺口: send_webhook_message body 无 timestamp/sign (机器人开启「签名校验」后
# 必被拒, 官方算法 base64(hmac_sha256(key=f"{ts}\n{secret}", data="")) 已在
# channel_providers.im_sign 正确实现可复用); HTTP 5xx 走 _interpret_response
# 直接 False 不重试, 与 channel_providers._post_with_retry 的 5xx 重试语义不一致。
# ═══════════════════════════════════════════════════════════════════

class TestIMWebhookSignatureAndRetry:
    """IM webhook 签名字段 + 5xx 重试语义 (卡 9fbc00ce)。"""

    SECRET = "test-sign-secret"

    @staticmethod
    def _resp(status_code=200, body=None):
        m = MagicMock()
        m.status_code = status_code
        m.json.return_value = body if body is not None else {"code": 0}
        return m

    @pytest.fixture(autouse=True)
    def _no_retry_sleep(self):
        # 5xx 重试退避不真睡 (RED 阶段旧实现不触发重试, GREEN 后生效)
        with patch("app.services.im_notify._retry_sleep", new_callable=AsyncMock):
            yield

    @pytest.mark.asyncio
    async def test_secret_adds_timestamp_and_sign(self, im_service):
        """配置 secret → body 附加 timestamp+sign, 算法对齐IM官方
        (独立重算 base64(hmac_sha256(key=f"{ts}\\n{secret}", data="")))。"""
        import base64
        import hashlib
        import hmac

        im_service.secret = self.SECRET
        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.return_value = self._resp()
            mock_client.return_value.__aenter__.return_value = instance

            content = {"msg_type": "text", "content": {"text": "hi"}}
            result = await im_service.send_webhook_message(content)

        assert result is True
        sent = instance.post.call_args.kwargs["json"]
        assert "timestamp" in sent, "缺少签名字段 timestamp"
        assert "sign" in sent, "缺少签名字段 sign"
        ts = int(sent["timestamp"])
        expected = base64.b64encode(
            hmac.new(f"{ts}\n{self.SECRET}".encode("utf-8"),
                     digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        assert sent["sign"] == expected  # 与官方算法逐字节对齐
        assert sent["msg_type"] == "text"  # 原内容字段保留
        # 不 mutate 调用方传入的 content dict
        assert "timestamp" not in content and "sign" not in content

    @pytest.mark.asyncio
    async def test_no_secret_keeps_payload_compatible(self, im_service):
        """未配置 secret → 不附加签名字段, 发送 body 与 content 完全一致 (兼容)。"""
        im_service.secret = None
        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.return_value = self._resp()
            mock_client.return_value.__aenter__.return_value = instance

            content = {"msg_type": "text", "content": {"text": "hi"}}
            result = await im_service.send_webhook_message(content)

        assert result is True
        assert instance.post.call_args.kwargs["json"] == content

    @pytest.mark.asyncio
    async def test_5xx_retries_then_succeeds(self, im_service):
        """HTTP 5xx 纳入重试 (对齐 channel_providers._post_with_retry 语义)。"""
        im_service.secret = None
        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.side_effect = [self._resp(500), self._resp(200, {"code": 0})]
            mock_client.return_value.__aenter__.return_value = instance

            result = await im_service.send_webhook_message({"msg_type": "text"})

        assert result is True
        assert instance.post.await_count == 2  # 500 → 重试 → 200

    @pytest.mark.asyncio
    async def test_4xx_no_retry(self, im_service):
        """HTTP 4xx 终态不重试。"""
        im_service.secret = None
        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.return_value = self._resp(404)
            mock_client.return_value.__aenter__.return_value = instance

            result = await im_service.send_webhook_message({"msg_type": "text"})

        assert result is False
        assert instance.post.await_count == 1

    @pytest.mark.asyncio
    async def test_signature_recomputed_per_attempt(self, im_service):
        """重试链上签名逐次重算: ts 不冻结、两次 sign 不同 (对齐 211f5c97
        每 attempt 重算语义)。"""
        im_service.secret = self.SECRET
        with patch("httpx.AsyncClient") as mock_client, \
             patch("app.services.im_notify._now_ts",
                   side_effect=[1700000000, 1700000300], raising=False):
            instance = AsyncMock()
            instance.post.side_effect = [self._resp(500), self._resp(200, {"code": 0})]
            mock_client.return_value.__aenter__.return_value = instance

            result = await im_service.send_webhook_message({"msg_type": "text"})

        assert result is True
        payloads = [c.kwargs["json"] for c in instance.post.call_args_list]
        assert payloads[0]["timestamp"] == "1700000000"
        assert payloads[1]["timestamp"] == "1700000300"  # ts 不冻结
        assert payloads[0]["sign"] != payloads[1]["sign"]


class TestAlertWebhook:
    """告警 Webhook 端点测试"""

    WEBHOOK_SECRET = "test-webhook-secret"

    @pytest.fixture(autouse=True)
    def _webhook_secret(self, async_client, monkeypatch):
        """da16d511 安全加固后端点强制 secret：注入配置+请求头使合法转发用例通过。

        secret 缺失/错误 -> 403 的反向路径由 test_alert_webhook_auth.py 覆盖。
        """
        from app.core.config import settings
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", self.WEBHOOK_SECRET)
        async_client.headers["X-Webhook-Secret"] = self.WEBHOOK_SECRET

    @pytest.mark.asyncio
    async def test_alertmanager_webhook_firing(self, async_client, sample_prometheus_alert):
        """测试接收 Alertmanager 触发告警"""
        payload = {
            "status": "firing",
            "alerts": [sample_prometheus_alert]
        }

        # Mock IM服务
        with patch.object(im_notify_service, "notify_prometheus_alerts", new_callable=AsyncMock) as mock_notify:
            mock_notify.return_value = {"success": True, "sent": 1, "failed": 0}

            response = await async_client.post("/api/v1/alert-webhook", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["groups"]["critical"] == 1
            assert "im_notify" in data
            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_alertmanager_webhook_resolved(self, async_client, sample_resolved_alert):
        """测试接收已恢复告警"""
        payload = {
            "status": "resolved",
            "alerts": [sample_resolved_alert]
        }

        with patch.object(im_notify_service, "notify_prometheus_alerts", new_callable=AsyncMock) as mock_notify:
            mock_notify.return_value = {"success": True, "sent": 1}

            response = await async_client.post("/api/v1/alert-webhook", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_webhook_health(self, async_client):
        """测试 Webhook 健康检查"""
        response = await async_client.get("/api/v1/alert-webhook/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "alertmanager" in data["capabilities"]

    @pytest.mark.asyncio
    async def test_webhook_empty_alerts(self, async_client):
        """测试空告警列表"""
        payload = {"status": "firing", "alerts": []}

        response = await async_client.post("/api/v1/alert-webhook", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "无告警"

    @pytest.mark.asyncio
    async def test_webhook_invalid_json(self, async_client):
        """测试无效 JSON"""
        response = await async_client.post(
            "/api/v1/alert-webhook",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400


class TestDispatchAlarmNotification:
    """告警分发测试"""

    def test_dispatch_critical_alarm(self, im_service):
        """测试分发严重告警"""
        alarm = Alarm(
            id=1,
            content="逆变器过温",
            level=AlarmLevel.CRITICAL,
            device_id=5,
            created_at=datetime.now()
        )

        with patch.object(im_service, "notify_system_alarm", new_callable=AsyncMock) as mock_notify:
            mock_notify.return_value = True
            result = im_service.dispatch_alarm_notification(alarm)
            assert result is True

    def test_dispatch_info_alarm_skipped(self, im_service):
        """测试提示级别告警不发送IM"""
        alarm = Alarm(
            id=2,
            content="系统启动",
            level=AlarmLevel.INFO,
            created_at=datetime.now()
        )

        # INFO 级别不触发IM通知
        result = im_service.dispatch_alarm_notification(alarm)
        # 内部会跳过发送，但返回 True（不是失败）
        assert result is True