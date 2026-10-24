"""告警确认 (升级链入口) — POST /api/v1/alerts/{alarm_id}/ack (卡 8d98ebe3)

与既有 PUT /alarms/{alarm_id}/ack 的区别: 本端点在确认告警 (AlarmStatus.ACKNOWLEDGED)
之外, 同步终止告警升级链 (AlarmEscalationTracker.ack), 停止后续短信/语音升级。
供告警升级链场景的确认操作使用。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import assert_alarm_team_access
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.middleware.permission import require_permission
from app.models.alarm import Alarm, AlarmStatus
from app.models.user import User
from app.services.alarm_escalation import alarm_escalation_tracker
from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/{alarm_id}/ack")
def ack_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """确认告警并终止升级链。

    - 告警不存在 → 404; 跨团队 → 404 (不泄露存在);
    - 置 status=ACKNOWLEDGED, handler_id, handled_at;
    - alarm_escalation_tracker.ack(alarm_id) 终止升级链 (首次确认返回 True)。
    """
    try:
        alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        if not alarm:
            raise HTTPException(status_code=404, detail="告警不存在")
        assert_alarm_team_access(db, alarm_id, user)

        alarm.status = AlarmStatus.ACKNOWLEDGED
        alarm.handler_id = getattr(user, "id", None)
        alarm.handled_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(alarm)

        # 终止升级链 (首次确认返回 True, 已确认/无状态返回 False)
        terminated = bool(alarm_escalation_tracker.ack(alarm_id))

        try:
            audit_service.log_crud(
                user_id=user.id, username=user.username,
                action="create", module="alerts",
                target_id=str(alarm.id),
                target_desc=f"确认告警:{alarm.content[:30] if alarm.content else ''}",
            )
        except Exception:
            pass

        status_val = alarm.status.value if hasattr(alarm.status, "value") else alarm.status
        return success_response({
            "alarm_id": alarm.id,
            "status": status_val,
            "escalation_terminated": terminated,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("ack_alarm 异常")
        return JSONResponse(
            status_code=500, content={"detail": "服务器内部错误，请稍后重试"}
        )
