"""notification_service 单元测试"""
import logging
from app.services.notification_service import send_notification


class TestSendNotification:
    """send_notification 主入口测试"""

    def test_default_channel(self):
        result = send_notification("user_001", "标题", "内容")
        assert result["status"] == "ok"
        assert result["channel"] == "app"
        assert result["user_id"] == "user_001"
        assert result["title"] == "标题"
        assert "sent_at" in result

    def test_sms_channel(self):
        result = send_notification("u1", "t", "c", channel="sms")
        assert result["channel"] == "sms"

    def test_email_channel(self):
        result = send_notification("u1", "t", "c", channel="email")
        assert result["channel"] == "email"

    def test_return_keys_complete(self):
        result = send_notification("uid", "标题1", "内容1", channel="app")
        expected_keys = {"status", "channel", "user_id", "title", "sent_at"}
        assert set(result.keys()) == expected_keys

    def test_sent_at_format(self):
        result = send_notification("u", "t", "c")
        # 格式 YYYY-MM-DD HH:MM:SS
        ts = result["sent_at"]
        assert len(ts) == 19
        assert ts[4] == "-" and ts[7] == "-" and ts[10] == " "
        assert ts[13] == ":" and ts[16] == ":"

    def test_empty_content(self):
        """空内容不报错"""
        result = send_notification("u", "t", "")
        assert result["status"] == "ok"

    def test_special_chars(self):
        """特殊字符正常传递"""
        result = send_notification("u", "标题<>&", "内容\"'")
        assert result["title"] == "标题<>&"
        assert result["status"] == "ok"

    def test_logs_info(self, caplog):
        """logger.info 被正确调用"""
        with caplog.at_level(logging.INFO, logger="app.services.notification_service"):
            send_notification("log_user", "log_title", "log_content")
        # app 渠道走 in-app 分支日志（app/services/notification_service.py:59），
        # "Notification sent: channel=%s" 仅 sms/email 成功路径输出
        assert any("Notification (in-app)" in r.message for r in caplog.records)
        assert any("user_id=log_user" in r.message for r in caplog.records)
