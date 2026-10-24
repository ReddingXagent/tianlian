"""
通知发送服务 — 真实通道委托 + 失败路径测试

卡号 5b884e14

覆盖:
- send_notification 委托 dispatcher 真实发送 (sms/email 成功路径)
- send_notification 失败路径 (dispatcher 返回 False → status=failed)
- send_notification 用户不存在 → failed
- send_notification 用户无 phone/email → failed
- send_notification app 渠道仍返回 ok（不调 dispatcher）
- API 端点: sms 发送失败 → 500 + error detail
"""
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

from app.services import notification_service
from app.services.notification_service import send_notification
from app.services.notification_dispatcher import NotificationDispatcher
from app.models.user import User


# ═══════════════════════════════════════════════════════════
#  单元测试: send_notification 委托 + 失败路径
# ═══════════════════════════════════════════════════════════

class TestSendNotificationDelegation:
    """send_notification 委托 dispatcher 真实发送"""

    def test_app_channel_returns_ok_without_dispatcher(self):
        """app 渠道不调 dispatcher，直接返回 ok"""
        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            result = send_notification("u001", "标题", "内容", channel="app")
            assert result["status"] == "ok"
            assert result["channel"] == "app"
            assert result["user_id"] == "u001"
            assert result["title"] == "标题"
            assert result["sent_at"]
            # dispatcher 不应被调用
            mock_disp.send_sms_to_user.assert_not_called()
            mock_disp.send_email_to_user.assert_not_called()

    def test_app_push_channel_returns_ok_without_dispatcher(self):
        """app_push 渠道也不调 dispatcher"""
        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            result = send_notification("u001", "标题", "内容", channel="app_push")
            assert result["status"] == "ok"
            mock_disp.send_sms_to_user.assert_not_called()

    def test_sms_success_delegates_to_dispatcher(self):
        """sms 渠道成功: 查用户 → 调 dispatcher.send_sms_to_user → ok"""
        mock_user = MagicMock()
        mock_user.phone = "13800000000"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            mock_disp.send_sms_to_user.return_value = True
            result = send_notification("1", "告警", "过温", channel="sms", db=mock_db)

            assert result["status"] == "ok"
            assert result["channel"] == "sms"
            mock_disp.send_sms_to_user.assert_called_once_with("13800000000", "过温")

    def test_email_success_delegates_to_dispatcher(self):
        """email 渠道成功: 查用户 → 调 dispatcher.send_email_to_user → ok"""
        mock_user = MagicMock()
        mock_user.email = "user@example.com"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            mock_disp.send_email_to_user.return_value = True
            result = send_notification("1", "告警", "过温", channel="email", db=mock_db)

            assert result["status"] == "ok"
            assert result["channel"] == "email"
            mock_disp.send_email_to_user.assert_called_once_with("user@example.com", "告警", "过温")


class TestSendNotificationFailures:
    """send_notification 失败路径 — 不许假成功"""

    def test_sms_dispatcher_returns_false(self):
        """sms dispatcher 返回 False → status=failed"""
        mock_user = MagicMock()
        mock_user.phone = "13800000000"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            mock_disp.send_sms_to_user.return_value = False
            result = send_notification("1", "告警", "过温", channel="sms", db=mock_db)

            assert result["status"] == "failed"
            assert result["channel"] == "sms"
            assert "error" in result
            assert result["error"] == "send failed"

    def test_email_dispatcher_returns_false(self):
        """email dispatcher 返回 False → status=failed"""
        mock_user = MagicMock()
        mock_user.email = "user@example.com"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            mock_disp.send_email_to_user.return_value = False
            result = send_notification("1", "告警", "过温", channel="email", db=mock_db)

            assert result["status"] == "failed"
            assert result["channel"] == "email"
            assert result["error"] == "send failed"

    def test_sms_dispatcher_raises_exception(self):
        """sms dispatcher 抛异常 → status=failed (不假成功)"""
        mock_user = MagicMock()
        mock_user.phone = "13800000000"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            mock_disp.send_sms_to_user.side_effect = RuntimeError("smtp gateway down")
            result = send_notification("1", "告警", "过温", channel="sms", db=mock_db)

            assert result["status"] == "failed"
            assert "smtp gateway down" in result["error"]

    def test_email_dispatcher_raises_exception(self):
        """email dispatcher 抛异常 → status=failed"""
        mock_user = MagicMock()
        mock_user.email = "user@example.com"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            mock_disp.send_email_to_user.side_effect = ConnectionError("network unreachable")
            result = send_notification("1", "告警", "过温", channel="email", db=mock_db)

            assert result["status"] == "failed"
            assert "network unreachable" in result["error"]

    def test_user_not_found_returns_failed(self):
        """用户不存在 → failed (不假成功)"""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = send_notification("99999", "告警", "过温", channel="sms", db=mock_db)

        assert result["status"] == "failed"
        assert result["error"] == "user not found"

    def test_sms_user_no_phone_returns_failed(self):
        """sms 渠道但用户无 phone → failed"""
        mock_user = MagicMock()
        mock_user.phone = None
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        result = send_notification("1", "告警", "过温", channel="sms", db=mock_db)

        assert result["status"] == "failed"
        assert result["error"] == "user has no phone number"

    def test_email_user_no_email_returns_failed(self):
        """email 渠道但用户无 email → failed"""
        mock_user = MagicMock()
        mock_user.email = None
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        result = send_notification("1", "告警", "过温", channel="email", db=mock_db)

        assert result["status"] == "failed"
        assert result["error"] == "user has no email address"

    def test_non_numeric_user_id_returns_failed(self):
        """user_id 非数字 → 查不到用户 → failed"""
        mock_db = MagicMock()

        result = send_notification("abc", "告警", "过温", channel="sms", db=mock_db)

        assert result["status"] == "failed"
        assert result["error"] == "user not found"


# ═══════════════════════════════════════════════════════════
#  单元测试: NotificationDispatcher 直接发送方法
# ═══════════════════════════════════════════════════════════

class TestDispatcherDirectSend:
    """dispatcher.send_sms_to_user / send_email_to_user 直接发送"""

    def test_send_sms_to_user_mock_mode(self):
        """SMS API 未配置 → mock 日志 → 返回 True"""
        disp = NotificationDispatcher()
        # _sms_api_url 默认 None (settings 无配置)
        assert disp._sms_api_url is None or disp._sms_api_url == ""
        result = disp.send_sms_to_user("13800000000", "测试短信")
        assert result is True

    def test_send_sms_to_user_empty_phone(self):
        """空手机号 → False"""
        disp = NotificationDispatcher()
        result = disp.send_sms_to_user("", "内容")
        assert result is False

    def test_send_sms_to_user_api_failure(self):
        """SMS API 返回 500 → False"""
        disp = NotificationDispatcher()
        disp._sms_api_url = "http://mock-sms.example.com/send"
        with patch('app.services.notification_dispatcher.requests') as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "server error"
            mock_req.post.return_value = mock_resp
            result = disp.send_sms_to_user("13800000000", "测试")
            assert result is False

    def test_send_sms_to_user_api_exception(self):
        """SMS API 网络异常 → False"""
        disp = NotificationDispatcher()
        disp._sms_api_url = "http://mock-sms.example.com/send"
        with patch('app.services.notification_dispatcher.requests') as mock_req:
            mock_req.post.side_effect = ConnectionError("network down")
            result = disp.send_sms_to_user("13800000000", "测试")
            assert result is False

    # ── 卡 9fbc00ce: send_sms_to_user 零重试单发修复 (6ca6092d 明确遗留) ──

    def test_send_sms_to_user_503_then_200_retries(self, monkeypatch):
        """SMS API 5xx 后重试成功 (对齐 6ca6092d _send_sms 的重试语义)。"""
        from app.services import notification_dispatcher as nd_mod
        monkeypatch.setattr(nd_mod, "_RETRY_BACKOFF", 0.0, raising=False)

        disp = NotificationDispatcher()
        disp._sms_api_url = "http://mock-sms.example.com/send"
        with patch('app.services.notification_dispatcher.requests') as mock_req:
            resp_503 = MagicMock()
            resp_503.status_code = 503
            resp_503.text = "Service Unavailable"
            resp_200 = MagicMock()
            resp_200.status_code = 200
            mock_req.post.side_effect = [resp_503, resp_200]
            result = disp.send_sms_to_user("13800000000", "测试")
        assert result is True
        assert mock_req.post.call_count == 2  # 503 → 重试 → 200

    def test_send_sms_to_user_4xx_no_retry(self):
        """SMS API 4xx 业务拒绝 → 立即 False 不重试。"""
        disp = NotificationDispatcher()
        disp._sms_api_url = "http://mock-sms.example.com/send"
        with patch('app.services.notification_dispatcher.requests') as mock_req:
            resp = MagicMock()
            resp.status_code = 403
            resp.text = "Forbidden"
            mock_req.post.return_value = resp
            result = disp.send_sms_to_user("13800000000", "测试")
        assert result is False
        assert mock_req.post.call_count == 1

    def test_send_sms_to_user_payload_and_timeout(self):
        """重试包装不改变请求契约: payload 截断 + timeout=5。"""
        disp = NotificationDispatcher()
        disp._sms_api_url = "http://mock-sms.example.com/send"
        with patch('app.services.notification_dispatcher.requests') as mock_req:
            resp = MagicMock()
            resp.status_code = 200
            mock_req.post.return_value = resp
            result = disp.send_sms_to_user("13800000000", "x" * 500)
        assert result is True
        kwargs = mock_req.post.call_args.kwargs
        assert kwargs["json"] == {"phone": "13800000000", "content": "x" * 200}
        assert kwargs["timeout"] == 5

    def test_send_email_to_user_mock_mode(self):
        """SMTP 未配置 → mock 日志 → 返回 True"""
        disp = NotificationDispatcher()
        assert disp._email_config['smtp_host'] is None
        result = disp.send_email_to_user("user@example.com", "主题", "正文")
        assert result is True

    def test_send_email_to_user_empty_addr(self):
        """空邮箱 → False"""
        disp = NotificationDispatcher()
        result = disp.send_email_to_user("", "主题", "正文")
        assert result is False

    def test_send_email_to_user_smtp_failure(self):
        """SMTP 连接失败 → False"""
        disp = NotificationDispatcher()
        disp._email_config['smtp_host'] = "smtp.mock.example.com"
        disp._email_config['smtp_port'] = 587
        with patch('app.services.notification_dispatcher.smtplib') as mock_smtplib:
            mock_server = MagicMock()
            mock_server.starttls.side_effect = Exception("TLS handshake failed")
            # context manager: smtplib.SMTP(...).__enter__() returns the server
            mock_smtplib.SMTP.return_value.__enter__.return_value = mock_server
            result = disp.send_email_to_user("user@example.com", "主题", "正文")
            assert result is False


# ═══════════════════════════════════════════════════════════
#  API 端点测试: 失败路径
# ═══════════════════════════════════════════════════════════

class TestNotificationSendAPIFailure:
    """POST /api/v1/notifications/send 失败路径"""

    def test_sms_send_failure_returns_500(self, client):
        """sms 发送失败 → API 返回 500 业务码 + error detail"""
        # 先在测试 DB 里创建一个有 phone 的用户
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            user = User(
                username="test_sms_user",
                password_hash="dummy",
                real_name="测试用户",
                phone="13800000000",
                email="test@example.com",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            user_id = str(user.id)
        finally:
            db.close()

        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            mock_disp.send_sms_to_user.return_value = False
            resp = client.post("/api/v1/notifications/send", json={
                "user_id": user_id,
                "title": "告警通知",
                "content": "设备温度过高",
                "channel": "sms",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 500
        assert "失败" in body["message"]

    def test_sms_send_exception_returns_500(self, client):
        """sms 发送异常 → API 返回 500"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            user = User(
                username="test_sms_exc",
                password_hash="dummy",
                real_name="测试用户2",
                phone="13900000000",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            user_id = str(user.id)
        finally:
            db.close()

        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            mock_disp.send_sms_to_user.side_effect = RuntimeError("gateway crash")
            resp = client.post("/api/v1/notifications/send", json={
                "user_id": user_id,
                "title": "告警通知",
                "content": "设备过温",
                "channel": "sms",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 500

    def test_email_send_failure_returns_500(self, client):
        """email 发送失败 → API 返回 500"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            user = User(
                username="test_email_user",
                password_hash="dummy",
                real_name="邮件用户",
                phone="13700000000",
                email="fail@example.com",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            user_id = str(user.id)
        finally:
            db.close()

        with patch.object(notification_service, 'notification_dispatcher') as mock_disp:
            mock_disp.send_email_to_user.return_value = False
            resp = client.post("/api/v1/notifications/send", json={
                "user_id": user_id,
                "title": "告警通知",
                "content": "设备过温",
                "channel": "email",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 500
        assert "失败" in body["message"]

    def test_sms_user_not_found_returns_500(self, client):
        """sms 渠道但用户不存在 → API 返回 500"""
        resp = client.post("/api/v1/notifications/send", json={
            "user_id": "999999",
            "title": "告警",
            "content": "内容",
            "channel": "sms",
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 500

    def test_app_channel_still_succeeds(self, client):
        """app 渠道不受影响，仍然返回成功"""
        resp = client.post("/api/v1/notifications/send", json={
            "user_id": "u001",
            "title": "充电完成",
            "content": "您的车辆已充电完成",
            "channel": "app",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["data"]["status"] == "ok"
        assert body["data"]["channel"] == "app"

    def test_app_push_inbox_persisted(self, client):
        """app_push 渠道: 收件箱落库逻辑保留"""
        from app.core.database import SessionLocal
        from app.models.notification import Notification
        db = SessionLocal()
        try:
            user = User(
                username="test_inbox_user",
                password_hash="dummy",
                real_name="收件箱用户",
                phone="13600000000",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            user_id = str(user.id)
        finally:
            db.close()

        resp = client.post("/api/v1/notifications/send", json={
            "user_id": user_id,
            "title": "站内通知",
            "content": "请查看详情",
            "channel": "app_push",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "ok"

        # 验证 Notification 收件箱记录已落库
        db = SessionLocal()
        try:
            inbox = db.query(Notification).filter(
                Notification.recipient_id == user_id
            ).first()
            assert inbox is not None
            assert inbox.title == "站内通知"
            assert inbox.content == "请查看详情"
        finally:
            db.close()
