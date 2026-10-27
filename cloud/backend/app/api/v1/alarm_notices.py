"""
告警通知 API（基于 Alarm 模型）
通知 = 未处理的告警 + 实时告警推送
"""
import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import case
from app.core.database import get_db
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.station import Station
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, assert_alarm_team_access
from app.middleware.permission import require_write_permission
from app.models.user import User
from app.core.response import success_response, paginated_response

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_write_permission("alarm:process"))])


# USING get_db FROM app.core.database


def _serialize_notice(alarm: Alarm) -> dict:
    """序列化告警通知"""
    return {
        'id': alarm.id,
        'device_id': alarm.device_id,
        'station_id': alarm.station_id,
        'rule_id': alarm.rule_id,
        'alarm_type': alarm.alarm_type,
        'level': alarm.level.value if alarm.level else 'info',
        'content': alarm.content,
        'fault_code': alarm.fault_code,
        'fault_source': alarm.fault_source,
        'trigger_metric': alarm.trigger_metric,
        'trigger_value': alarm.trigger_value,
        'trigger_threshold': alarm.trigger_threshold,
        'status': alarm.status.value if alarm.status else 'active',
        'handler_id': alarm.handler_id,
        'handle_desc': alarm.handle_desc,
        'created_at': alarm.created_at.isoformat() if alarm.created_at else None,
        'handled_at': alarm.handled_at.isoformat() if alarm.handled_at else None,
    }


@router.get("")
def list_alarm_notices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    level: Optional[str] = None,
    status: Optional[str] = None,
    hours: Optional[int] = Query(None, ge=1, le=720, description="最近N小时(边界1~720)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取告警通知列表"""
    try:
        query = db.query(Alarm)
        if not is_platform_admin(user):
            query = query.join(Station, Station.id == Alarm.station_id).filter(Station.team_id == user.team_id)

        if level:
            query = query.filter(Alarm.level == level)
        if status:
            query = query.filter(Alarm.status == status)
        else:
            # 默认只显示未处理的告警
            query = query.filter(Alarm.status != AlarmStatus.RESOLVED.value)
            query = query.filter(Alarm.status != AlarmStatus.IGNORED.value)
        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            query = query.filter(Alarm.created_at >= cutoff)

        total = query.count()
        items = query.order_by(
            # 严重级别优先
            case(
                (Alarm.level == AlarmLevel.FATAL, 0),
                (Alarm.level == AlarmLevel.CRITICAL, 1),
                (Alarm.level == AlarmLevel.WARNING, 2),
                else_=3
            ),
            Alarm.created_at.desc()
        ).offset((page - 1) * page_size).limit(page_size).all()

        return paginated_response([_serialize_notice(a) for a in items], total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_alarm_notices 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/stats")
def get_alarm_notice_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取告警通知统计"""
    try:
        query = db.query(Alarm).filter(
            Alarm.status.notin_([AlarmStatus.RESOLVED, AlarmStatus.IGNORED])
        )
        if not is_platform_admin(user):
            query = query.join(Station, Station.id == Alarm.station_id).filter(Station.team_id == user.team_id)

        total_unread = query.count()
        critical = query.filter(Alarm.level == AlarmLevel.CRITICAL).count()
        fatal = query.filter(Alarm.level == AlarmLevel.FATAL).count()
        warning = query.filter(Alarm.level == AlarmLevel.WARNING).count()
        info = query.filter(Alarm.level == AlarmLevel.INFO).count()

        return success_response({
            'total_unread': total_unread,
            'critical': critical,
            'fatal': fatal,
            'warning': warning,
            'info': info,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_alarm_notice_stats 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/{alarm_id}/read")
def mark_notice_read(alarm_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """标记告警为已读（确认）"""
    try:
        alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        if not alarm:
            raise HTTPException(status_code=404, detail="告警不存在")
        assert_alarm_team_access(db, alarm_id, user)

        alarm.status = AlarmStatus.ACKNOWLEDGED
        alarm.handled_at = datetime.now(timezone.utc)
        db.commit()

        return success_response({'status': 'acknowledged'}, message='已确认')
    except HTTPException:
        raise
    except Exception:
        logger.exception("mark_notice_read 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/{alarm_id}/resolve")
def resolve_notice(alarm_id: int, handle_desc: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """解决告警"""
    try:
        alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        if not alarm:
            raise HTTPException(status_code=404, detail="告警不存在")
        assert_alarm_team_access(db, alarm_id, user)

        alarm.status = AlarmStatus.RESOLVED
        alarm.handle_desc = handle_desc
        alarm.handled_at = datetime.now(timezone.utc)
        db.commit()

        return success_response({'status': 'resolved'}, message='已解决')
    except HTTPException:
        raise
    except Exception:
        logger.exception("resolve_notice 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/{alarm_id}/ignore")
def ignore_notice(alarm_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """忽略告警"""
    try:
        alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        if not alarm:
            raise HTTPException(status_code=404, detail="告警不存在")
        assert_alarm_team_access(db, alarm_id, user)

        alarm.status = AlarmStatus.IGNORED
        alarm.handled_at = datetime.now(timezone.utc)
        db.commit()

        return success_response({'status': 'ignored'}, message='已忽略')
    except HTTPException:
        raise
    except Exception:
        logger.exception("ignore_notice 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """标记所有未读告警为已读"""
    try:
        query = db.query(Alarm).filter(Alarm.status.in_([AlarmStatus.ACTIVE]))
        if not is_platform_admin(user):
            # Query.update() 不允许 join，改用子查询限定本 team 告警
            own_ids = (
                db.query(Alarm.id)
                .join(Station, Station.id == Alarm.station_id)
                .filter(Station.team_id == user.team_id)
            )
            query = query.filter(Alarm.id.in_(own_ids))
        count = query.update({Alarm.status: AlarmStatus.ACKNOWLEDGED}, synchronize_session=False)
        db.commit()

        return success_response({'updated': count}, message='全部已读')
    except HTTPException:
        raise
    except Exception:
        logger.exception("mark_all_read 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
