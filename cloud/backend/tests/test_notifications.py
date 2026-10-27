"""
通知发送 API 测试

覆盖: POST /api/v1/notifications/send
- app/sms/email 渠道成功
- 不支持渠道返回业务码 400
- 默认渠道为 app

卡 5b884e14: sms/email 渠道现已委托真实 dispatcher，测试需 mock dispatcher
避免依赖外部 SMS/SMTP 服务。
"""
from unittest.mock import patch

import app.services.notification_service as ns_module


def test_send_notification_app_channel(client):
    """app 渠道发送成功"""
    resp = client.post("/api/v1/notifications/send", json={
        "user_id": "u001",
        "title": "充电完成",
        "content": "您的车辆已充电完成",
        "channel": "app",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["status"] == "ok"
    assert data["channel"] == "app"
    assert data["user_id"] == "u001"
    assert data["title"] == "充电完成"


def test_send_notification_sms_channel(client):
    """sms 渠道发送成功 (mock dispatcher, 避免依赖外部 SMS 网关)"""
    # 先在测试 DB 创建有 phone 的用户
    from app.core.database import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    try:
        user = User(
            username="test_sms_api_user",
            password_hash="dummy",
            real_name="SMS测试用户",
            phone="13800000000",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = str(user.id)
    finally:
        db.close()

    with patch.object(ns_module, 'notification_dispatcher') as mock_disp:
        mock_disp.send_sms_to_user.return_value = True
        resp = client.post("/api/v1/notifications/send", json={
            "user_id": user_id,
            "title": "告警通知",
            "content": "设备温度过高",
            "channel": "sms",
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["channel"] == "sms"
    assert body["data"]["sent_at"]


def test_send_notification_unsupported_channel(client):
    """不支持渠道返回业务码 400"""
    resp = client.post("/api/v1/notifications/send", json={
        "user_id": "u003",
        "title": "x",
        "content": "y",
        "channel": "im_b",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400
    assert "不支持" in body["message"]


def test_send_notification_default_channel(client):
    """未指定 channel 时默认 app"""
    resp = client.post("/api/v1/notifications/send", json={
        "user_id": "u004",
        "title": "默认渠道",
        "content": "内容",
    })
    assert resp.status_code == 200
    assert resp.json()["data"]["channel"] == "app"
