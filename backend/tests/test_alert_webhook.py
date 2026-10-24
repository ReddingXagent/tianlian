"""
测试 Alertmanager webhook 端点 (Phase17)
"""
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# da16d511 安全加固后 /alert-webhook 强制共享密钥认证
_WEBHOOK_SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def _inject_webhook_secret(monkeypatch):
    """注入 ALERT_WEBHOOK_SECRET 配置与请求头，使本文件的合法转发用例通过。

    secret 缺失/错误 -> 403 的反向路径由 test_alert_webhook_auth.py 覆盖。
    """
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", _WEBHOOK_SECRET)
    client.headers["X-Webhook-Secret"] = _WEBHOOK_SECRET
    yield


class TestAlertWebhook:
    """Alertmanager webhook 端点测试"""

    WEBHOOK_URL = "/api/v1/alert-webhook"

    def test_webhook_health(self):
        """GET /alert-webhook/health 健康检查"""
        resp = client.get(f"{self.WEBHOOK_URL}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["version"] == "1.0"

    def test_webhook_empty_alerts(self):
        """无告警的 webhook 请求"""
        payload = {
            "status": "resolved",
            "alerts": []
        }
        resp = client.post(
            self.WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["message"] == "无告警"

    def test_webhook_single_critical_alert(self):
        """单条严重告警"""
        payload = {
            "status": "firing",
            "alerts": [{
                "status": "firing",
                "labels": {
                    "alertname": "BackendDown",
                    "severity": "critical",
                    "instance": "localhost:8000"
                },
                "annotations": {
                    "summary": "后端服务不可用",
                    "description": "后端服务已宕机超过5分钟"
                }
            }]
        }
        resp = client.post(self.WEBHOOK_URL, json=payload,
                          headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["groups"]["critical"] == 1
        assert data["groups"]["warning"] == 0
        assert data["groups"]["info"] == 0

    def test_webhook_mixed_severity(self):
        """多级别告警混合"""
        payload = {
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HighErrorRate",
                        "severity": "critical",
                        "instance": "prometheus:9090"
                    },
                    "annotations": {"summary": "错误率过高"}
                },
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HighLatency",
                        "severity": "warning",
                        "instance": "api:8000"
                    },
                    "annotations": {"summary": "P99延迟超过2s"}
                },
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "DeviceOffline",
                        "severity": "info",
                        "instance": "station-1"
                    },
                    "annotations": {"summary": "设备离线"}
                }
            ]
        }
        resp = client.post(self.WEBHOOK_URL, json=payload,
                          headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["groups"]["critical"] == 1
        assert data["groups"]["warning"] == 1
        assert data["groups"]["info"] == 1
        assert data["message"] == "已接收 3 条告警"

    def test_webhook_invalid_json(self):
        """非法 JSON 请求应当返回 400"""
        resp = client.post(
            self.WEBHOOK_URL,
            data="not-json",
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code in (400, 422)

    def test_webhook_resolved_alert(self):
        """已恢复的告警"""
        payload = {
            "status": "resolved",
            "alerts": [{
                "status": "resolved",
                "labels": {
                    "alertname": "BackendDown",
                    "severity": "critical",
                    "instance": "localhost:8000"
                },
                "annotations": {"summary": "已恢复"}
            }]
        }
        resp = client.post(self.WEBHOOK_URL, json=payload,
                          headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_metrics_endpoint(self):
        """验证 /metrics 端点存在 (Phase17 Prometheus集成)"""
        resp = client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        # 验证关键指标前缀
        assert "tianlian_http_requests_total" in text
        assert "tianlian_http_request_duration_seconds" in text
        assert "tianlian_http_requests_in_flight" in text
        assert "tianlian_app_info" in text
