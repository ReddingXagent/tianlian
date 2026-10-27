"""默认日志 PushProvider: 零厂商依赖, 仅留痕返回成功."""

import logging

from app.services.push.base import PushProvider

logger = logging.getLogger(__name__)


class LogPushProvider(PushProvider):
    def send(self, end_user_id: int, title: str, body: str, payload: dict) -> bool:
        logger.info(
            "[PUSH PROVIDER LOG] end_user_id=%s title=%s body=%s payload=%s",
            end_user_id,
            title,
            body,
            payload,
        )
        return True
