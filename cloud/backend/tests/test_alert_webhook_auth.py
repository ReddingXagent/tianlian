"""
Alertmanager webhook 认证测试 (Phase17 安全加固 da16d511)

修复零认证漏洞：POST /alert-webhook 原先无任何认证且在 enforce_auth 公开白名单中，
任何人可 POST 伪造 critical 告警刷屏IM（通知通道 DoS）。

校验规则：
  - 请求头 X-Webhook-Secret 或 query ?secret= 必须与 settings.ALERT_WEBHOOK_SECRET 匹配
  - 不匹配 -> 403
  - secret 未配置(None/空) -> 拒绝所有请求 -> 403（强制配置，不保留裸奔兼容）
"""
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import alert_webhook as webhook_module
from app.core.config import settings


WEBHOOK_URL = "/api/v1/alert-webhook"
SECRET = "s3cret-webhook-token-da16d511"

# 一条 critical 告警 payload（真实 DoS 场景：伪造严重告警刷屏）
CRITICAL_PAYLOAD = {
    "status": "firing",
    "alerts": [{
        "status": "firing",
        "labels": {
            "alertname": "BackendDown",
            "severity": "critical",
            "instance": "localhost:8000",
        },
        "annotations": {"summary": "后端服务不可用"},
    }],
}


@pytest.fixture(autouse=True)
def _stub_im(monkeypatch):
    """隔离IM外发：替换单例方法，避免测试触达真实 webhook。"""
    monkeypatch.setattr(
        webhook_module.im_notify_service,
        "notify_prometheus_alerts",
        AsyncMock(return_value={"sent": 1, "failed": 0}),
    )


class TestAlertWebhookAuth:
    """/alert-webhook secret 认证回归。"""

    def test_no_secret_returns_403(self, client, monkeypatch):
        """已配置 secret 但请求不带 secret -> 403。"""
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", SECRET)
        resp = client.post(WEBHOOK_URL, json=CRITICAL_PAYLOAD)
        assert resp.status_code == 403

    def test_wrong_secret_header_returns_403(self, client, monkeypatch):
        """X-Webhook-Secret 错误 -> 403。"""
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", SECRET)
        resp = client.post(
            WEBHOOK_URL,
            json=CRITICAL_PAYLOAD,
            headers={"X-Webhook-Secret": "wrong-secret"},
        )
        assert resp.status_code == 403

    def test_wrong_secret_query_returns_403(self, client, monkeypatch):
        """?secret= 错误 -> 403。"""
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", SECRET)
        resp = client.post(f"{WEBHOOK_URL}?secret=wrong", json=CRITICAL_PAYLOAD)
        assert resp.status_code == 403

    def test_correct_secret_header_forwards(self, client, monkeypatch):
        """X-Webhook-Secret 正确 -> 200 且转发到IM。"""
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", SECRET)
        resp = client.post(
            WEBHOOK_URL,
            json=CRITICAL_PAYLOAD,
            headers={"X-Webhook-Secret": SECRET},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # 确认确实转发到IM（而非被认证挡下）
        webhook_module.im_notify_service.notify_prometheus_alerts.assert_awaited_once()

    def test_correct_secret_query_forwards(self, client, monkeypatch):
        """?secret= 正确 -> 200（Alertmanager webhook_configs url 携带方式）。"""
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", SECRET)
        resp = client.post(f"{WEBHOOK_URL}?secret={SECRET}", json=CRITICAL_PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        webhook_module.im_notify_service.notify_prometheus_alerts.assert_awaited_once()

    def test_secret_not_configured_rejects_all(self, client, monkeypatch):
        """secret 未配置(None) -> 即便带正确 secret 也 403（强制配置）。"""
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", None)
        resp = client.post(
            WEBHOOK_URL,
            json=CRITICAL_PAYLOAD,
            headers={"X-Webhook-Secret": SECRET},
        )
        assert resp.status_code == 403

    def test_empty_secret_rejects_all(self, client, monkeypatch):
        """secret 配为空串 -> 视同未配置 -> 403。"""
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", "")
        resp = client.post(
            WEBHOOK_URL,
            json=CRITICAL_PAYLOAD,
            headers={"X-Webhook-Secret": ""},
        )
        assert resp.status_code == 403
