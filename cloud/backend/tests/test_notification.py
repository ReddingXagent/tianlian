"""
通知发送 API 测试
覆盖: /api/v1/notifications/send
"""
import pytest


def test_send_notification_returns_200(client):
    """测试发送通知端点返回 200"""
    resp = client.post(
        "/api/v1/notifications/send",
        json={
            "user_id": "test_user",
            "title": "测试通知",
            "content": "这是一条测试通知",
            "channel": "app"
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0 or data.get("data", {}).get("status") == "ok"