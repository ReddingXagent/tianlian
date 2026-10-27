"""
通知发送服务 — 委托 notification_dispatcher 真实发送

send_notification() 根据 channel 调用 NotificationDispatcher 的真实通道：
- sms: dispatcher.send_sms_to_user(phone, content)
- email: dispatcher.send_email_to_user(email, title, content)
- app / app_push: 仅返回 ok（站内消息落库由端点处理）

发送失败如实返回 {'status': 'failed', ...}，不再假成功。
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from app.services.notification_dispatcher import notification_dispatcher
from app.core.database import SessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)


def _get_user_contact(db, user_id: str) -> Optional[User]:
    """从 DB 查用户联系方式 (phone/email)。返回 User 对象或 None。"""
    if not user_id:
        return None
    # user_id 可能是数字 (User.id) 或字符串
    try:
        uid_int = int(user_id)
    except (ValueError, TypeError):
        return None
    return db.query(User).filter(User.id == uid_int).first()


def send_notification(
    user_id: str,
    title: str,
    content: str,
    channel: str = "app",
    db=None,
) -> dict:
    """
    发送通知的主入口（委托 notification_dispatcher 真实发送）

    Args:
        user_id: 接收用户ID
        title: 通知标题
        content: 通知内容
        channel: 发送渠道 (sms/email/app/app_push)
        db: 可选 DB session（传入则复用，不传则内部自建）

    Returns:
        {'status': 'ok'|'failed', 'channel': ..., 'user_id': ..., 'title': ..., 'sent_at': ...}
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # app / app_push 渠道：无外部发送，站内落库由端点处理
    if channel in ("app", "app_push"):
        logger.info(
            "Notification (in-app) user_id=%s title=%s", user_id, title
        )
        return {
            "status": "ok",
            "channel": channel,
            "user_id": user_id,
            "title": title,
            "sent_at": timestamp,
        }

    # sms / email：需要查用户联系方式后委托 dispatcher 真实发送
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        user = _get_user_contact(db, user_id)

        if user is None:
            logger.warning(
                "send_notification: user not found user_id=%s channel=%s",
                user_id, channel,
            )
            return {
                "status": "failed",
                "channel": channel,
                "user_id": user_id,
                "title": title,
                "sent_at": timestamp,
                "error": "user not found",
            }

        if channel == "sms":
            phone = user.phone
            if not phone:
                return {
                    "status": "failed",
                    "channel": channel,
                    "user_id": user_id,
                    "title": title,
                    "sent_at": timestamp,
                    "error": "user has no phone number",
                }
            success = notification_dispatcher.send_sms_to_user(phone, content)

        elif channel == "email":
            email = user.email
            if not email:
                return {
                    "status": "failed",
                    "channel": channel,
                    "user_id": user_id,
                    "title": title,
                    "sent_at": timestamp,
                    "error": "user has no email address",
                }
            success = notification_dispatcher.send_email_to_user(email, title, content)

        else:
            # 不应该到这里（端点已校验），但防御性处理
            return {
                "status": "failed",
                "channel": channel,
                "user_id": user_id,
                "title": title,
                "sent_at": timestamp,
                "error": f"unsupported channel: {channel}",
            }

        if success:
            logger.info(
                "Notification sent: channel=%s user_id=%s title=%s",
                channel, user_id, title,
            )
            return {
                "status": "ok",
                "channel": channel,
                "user_id": user_id,
                "title": title,
                "sent_at": timestamp,
            }
        else:
            logger.warning(
                "Notification FAILED: channel=%s user_id=%s title=%s",
                channel, user_id, title,
            )
            return {
                "status": "failed",
                "channel": channel,
                "user_id": user_id,
                "title": title,
                "sent_at": timestamp,
                "error": "send failed",
            }
    except Exception as e:
        logger.exception("send_notification unexpected error")
        return {
            "status": "failed",
            "channel": channel,
            "user_id": user_id,
            "title": title,
            "sent_at": timestamp,
            "error": str(e),
        }
    finally:
        if should_close:
            db.close()
