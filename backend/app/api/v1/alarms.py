#!/usr/bin/env python3
"""
告警管理 API - 规则引擎增强版
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Literal, Optional
from pydantic import BaseModel, Field
from fastapi import Query
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from app.core.database import get_db
from app.tasks.tz_utils import today_in_biz_tz
from app.services.audit_service import audit_service
from app.models.alarm import Alarm, AlarmRule, AlarmRuleLog, AlarmLevel, AlarmStatus
from app.models.alarm_notification import AlarmNotification
from app.models.device import Device
from app.models.station import Station
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, assert_alarm_team_access
from app.api.v1.alarm_rules import (
    apply_rule_list_scope,
    assert_rule_write_access,
    assert_rule_station_ids_writable,
)
from app.middleware.permission import require_permission
from app.models.user import User
from app.core.response import success_response, paginated_response, action_response
from app.core.cache import cache

router = APIRouter(dependencies=[Depends(get_current_user)])

from app.core.rate_limit import limiter


def _evaluate_limit_key(request: Request) -> str:
    """evaluate 按用户维度限流 key (卡 2779d516)。

    slowapi 的 key_func 在端点函数体执行前调用, 此时依赖注入的 user
    尚不可得 → 直接解 Authorization token 取 sub(get_current_user 同源),
    不查库; 解析失败回退 real IP。写法与 business_invoices._send_email_limit_key
    (卡 71062d84) 一致。
    """
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            from app.core.jwt_utils import decode_token
            sub = decode_token(auth[7:]).get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass
    from app.core.rate_limit import get_real_ip
    return get_real_ip(request)

# ============================
# Pydantic 请求/响应模型
# ============================

class AlarmCreate(BaseModel):
    device_id: int
    alarm_type: str = Field(..., max_length=50)
    level: Literal["info", "warning", "critical", "fatal"] = "warning"
    content: str
    rule_id: Optional[int] = None

class AlarmRuleCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    device_type: Optional[str] = ""
    device_ids: Optional[list] = None
    station_ids: Optional[list] = None
    metric: str = Field(..., max_length=50)
    operator: Literal[">", "<", ">=", "<=", "==", "!="]
    threshold: float
    duration: int = 0
    level: Literal["info", "warning", "critical", "fatal"] = "warning"
    alarm_template: Optional[str] = "{metric} = {value}, 超过阈值 {threshold}"
    notify_users: Optional[list] = None
    auto_create_workorder: bool = False
    workorder_priority: Literal["low", "medium", "high", "urgent"] = "medium"
    enabled: bool = True
    silence_minutes: int = 0

class AlarmRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    device_type: Optional[str] = None
    device_ids: Optional[list] = None
    station_ids: Optional[list] = None
    metric: Optional[str] = None
    operator: Optional[Literal[">", "<", ">=", "<=", "==", "!="]] = None
    threshold: Optional[float] = None
    duration: Optional[int] = None
    level: Optional[Literal["info", "warning", "critical", "fatal"]] = None
    alarm_template: Optional[str] = None
    notify_users: Optional[list] = None
    auto_create_workorder: Optional[bool] = None
    workorder_priority: Optional[Literal["low", "medium", "high", "urgent"]] = None
    enabled: Optional[bool] = None
    silence_minutes: Optional[int] = None

# USING get_db FROM app.core.database

# ============================
# 辅助函数 - 告警序列化
# ============================

def _safe_enum_val(v, default="unknown"):
    """安全获取枚举值，兼容DB中不在枚举范围内的旧数据"""
    if v is None:
        return default
    if hasattr(v, 'value'):
        return v.value
    return str(v)


def _serialize_alarm(alarm: Alarm, db: Session = None, device_map: dict = None, station_map: dict = None, rule_map: dict = None) -> dict:
    """将Alarm对象序列化为dict，附加关联信息
    
    Phase47: 支持传入预加载的 device_map/station_map/rule_map 避免 N+1 查询
    """
    d = {
        'id': alarm.id,
        'device_id': alarm.device_id,
        'station_id': alarm.station_id,
        'rule_id': alarm.rule_id,
        'alarm_type': alarm.alarm_type,
        'level': _safe_enum_val(alarm.level, 'info'),
        'content': alarm.content,
        'status': _safe_enum_val(alarm.status, 'active'),
        'fault_code': alarm.fault_code,
        'fault_source': alarm.fault_source,
        'trigger_metric': alarm.trigger_metric,
        'trigger_value': alarm.trigger_value,
        'trigger_threshold': alarm.trigger_threshold,
        'trigger_operator': alarm.trigger_operator,
        'diagnosis_result': alarm.diagnosis_result,
        'repair_suggestion': alarm.repair_suggestion,
        'remote_fixable': alarm.remote_fixable,
        'created_at': alarm.created_at.isoformat() if alarm.created_at else None,
        'handled_at': alarm.handled_at.isoformat() if alarm.handled_at else None,
        'cleared_at': alarm.cleared_at.isoformat() if alarm.cleared_at else None,
    }
    # Phase47: 优先使用预加载的 map, 否则回退到逐条查询
    if alarm.device_id:
        device = device_map.get(alarm.device_id) if device_map else (db.query(Device).filter(Device.id == alarm.device_id).first() if db else None)
        d['device_name'] = device.name if device else f'设备 {alarm.device_id}'
        d['device_code'] = device.code if device and hasattr(device, 'code') else None
    else:
        d['device_name'] = f'设备 {alarm.device_id}'
    if alarm.station_id:
        station = station_map.get(alarm.station_id) if station_map else (db.query(Station).filter(Station.id == alarm.station_id).first() if db else None)
        d['station_name'] = station.name if station else f'站点 {alarm.station_id}'
    else:
        d['station_name'] = f'站点 {alarm.station_id}'
    if alarm.rule_id:
        rule = rule_map.get(alarm.rule_id) if rule_map else (db.query(AlarmRule).filter(AlarmRule.id == alarm.rule_id).first() if db else None)
        d['rule_name'] = rule.name if rule else None
    return d

def _serialize_rule(rule: AlarmRule) -> dict:
    """将AlarmRule对象序列化为dict"""
    return {
        'id': rule.id,
        'name': rule.name,
        'description': rule.description,
        'device_type': rule.device_type,
        'device_ids': rule.device_ids,
        'station_ids': rule.station_ids,
        'metric': rule.metric,
        'operator': rule.operator,
        'threshold': rule.threshold,
        'duration': rule.duration,
        'level': _safe_enum_val(rule.level, 'warning'),
        'alarm_template': rule.alarm_template,
        'notify_users': rule.notify_users,
        'auto_create_workorder': rule.auto_create_workorder,
        'workorder_priority': rule.workorder_priority,
        'enabled': rule.enabled,
        'silence_minutes': rule.silence_minutes,
        'created_at': rule.created_at.isoformat() if rule.created_at else None,
        'updated_at': rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _serialize_alarm_notification(rec: AlarmNotification) -> dict:
    """将AlarmNotification对象序列化为dict"""
    return {
        'id': rec.id,
        'alarm_id': rec.alarm_id,
        'channel': rec.channel,
        'recipient': rec.recipient,
        'sent_at': rec.sent_at.isoformat() if rec.sent_at else None,
        'status': rec.status,
        'result': rec.result,
        'created_at': rec.created_at.isoformat() if rec.created_at else None,
    }

# ============================
# 告警 CRUD
# ============================

@router.get("", dependencies=[Depends(get_current_user)])
def list_alarms(
    status: Optional[str] = None,
    level: Optional[str] = None,
    device_id: Optional[int] = None,
    station_id: Optional[int] = None,
    rule_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取告警列表"""
    query = db.query(Alarm)
    if not is_platform_admin(user):
        query = query.join(Station, Station.id == Alarm.station_id).filter(Station.team_id == user.team_id)
    if status:
        query = query.filter(Alarm.status == status)
    if level:
        query = query.filter(Alarm.level == level)
    if device_id:
        query = query.filter(Alarm.device_id == device_id)
    if station_id:
        query = query.filter(Alarm.station_id == station_id)
    if rule_id:
        query = query.filter(Alarm.rule_id == rule_id)

    total = query.count()
    items = query.order_by(Alarm.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()

    # ── Phase47: 批量预加载关联数据, 消除 N+1 ──
    device_ids = {a.device_id for a in items if a.device_id}
    station_ids = {a.station_id for a in items if a.station_id}
    rule_ids = {a.rule_id for a in items if a.rule_id}
    device_map = {d.id: d for d in db.query(Device).filter(Device.id.in_(device_ids)).all()} if device_ids else {}
    station_map = {s.id: s for s in db.query(Station).filter(Station.id.in_(station_ids)).all()} if station_ids else {}
    rule_map = {r.id: r for r in db.query(AlarmRule).filter(AlarmRule.id.in_(rule_ids)).all()} if rule_ids else {}

    result_items = [_serialize_alarm(a, device_map=device_map, station_map=station_map, rule_map=rule_map) for a in items]

    return paginated_response(result_items, total, page, page_size)

@router.post("")
def create_alarm(
    data: AlarmCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """创建告警 (自动触发AI诊断)"""
    # 推断 device 所属 station/team：非 admin 校验归属，并回填 station_id 供列表过滤
    dev = db.query(Device).filter(Device.id == data.device_id).first()
    dev_team_id = (
        db.query(Station.team_id).filter(Station.id == dev.station_id).scalar()
        if dev and dev.station_id else None
    )
    if not is_platform_admin(user):
        if dev_team_id is None or user.team_id is None or dev_team_id != user.team_id:
            raise HTTPException(status_code=404, detail="设备不存在")
    alarm = Alarm(
        device_id=data.device_id,
        station_id=dev.station_id if dev else None,
        alarm_type=data.alarm_type,
        level=AlarmLevel(data.level) if data.level else AlarmLevel.WARNING,
        content=data.content,
        rule_id=data.rule_id,
        status=AlarmStatus.ACTIVE,
    )
    db.add(alarm)
    db.commit()
    db.refresh(alarm)

    cache.delete("alarms:stats:summary")

    # 后台触发AI诊断
    import threading
    from app.services.diagnostic_pipeline import trigger_auto_diagnosis
    def _run_diagnosis(aid):
        try:
            trigger_auto_diagnosis(aid)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("自动诊断失败 [告警%s]: %s", aid, e)
    threading.Thread(target=_run_diagnosis, args=(alarm.id,), daemon=True).start()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="create", module="alarms",
            target_id=str(alarm.id), target_desc=f"创建告警:{alarm.content[:30] if alarm.content else ''}",
        )
    except Exception:
        pass
    return success_response(_serialize_alarm(alarm, db))

# ============================
# 告警规则 CRUD

# ============================

@router.get("/rules")
def list_rules(
    enabled: Optional[bool] = None,
    device_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取告警规则列表（非 admin 按本 team 站点作用域过滤，卡 960406a8）"""
    query = db.query(AlarmRule)
    if enabled is not None:
        query = query.filter(AlarmRule.enabled == enabled)
    if device_type:
        query = query.filter(AlarmRule.device_type == device_type)
    query = apply_rule_list_scope(query, db, user)
    query = query.order_by(AlarmRule.created_at.desc())
    total = query.count()
    rules = query.offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_serialize_rule(r) for r in rules], total, page, page_size)

@router.get("/rules/{rule_id}")
def get_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取告警规则详情（非 admin 限平台级 + 本 team 站点规则）"""
    from app.api.v1.alarm_rules import _rule_readable, _user_team_station_ids
    rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    if not is_platform_admin(user) and not _rule_readable(rule, _user_team_station_ids(db, user)):
        raise HTTPException(status_code=404, detail="告警规则不存在")
    return success_response(_serialize_rule(rule))

@router.post("/rules")
def create_rule(
    data: AlarmRuleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """创建告警规则（非 admin 须指定本 team 站点）"""
    assert_rule_station_ids_writable(db, data.station_ids, user)
    rule = AlarmRule(
        name=data.name,
        description=data.description,
        device_type=data.device_type or None,
        device_ids=data.device_ids,
        station_ids=data.station_ids,
        metric=data.metric,
        operator=data.operator,
        threshold=data.threshold,
        duration=data.duration,
        level=AlarmLevel(data.level) if data.level else AlarmLevel.WARNING,
        alarm_template=data.alarm_template,
        notify_users=data.notify_users,
        auto_create_workorder=data.auto_create_workorder,
        workorder_priority=data.workorder_priority,
        enabled=data.enabled,
        silence_minutes=data.silence_minutes,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="create", module="alarms",
            target_id=str(rule.id), target_desc=f"创建告警规则:{rule.name[:30]}",
        )
    except Exception:
        pass
    return success_response(_serialize_rule(rule))

@router.put("/rules/{rule_id}")
def update_rule(
    rule_id: int,
    data: AlarmRuleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """更新告警规则（非 admin 限本 team 规则 + 本 team 站点）"""
    rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    assert_rule_write_access(db, rule, user)
    if data.station_ids is not None:
        assert_rule_station_ids_writable(db, data.station_ids, user)

    update_fields = data.model_dump(exclude_none=True)
    for field, value in update_fields.items():
        if field == 'level' and value:
            setattr(rule, field, AlarmLevel(value))
        elif hasattr(rule, field):
            setattr(rule, field, value)

    db.commit()
    db.refresh(rule)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="alarms",
            target_id=str(rule_id), target_desc=f"更新告警规则:{rule.name[:30]}",
        )
    except Exception:
        pass
    return success_response(_serialize_rule(rule))

@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """删除告警规则（非 admin 限本 team 规则）"""
    rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    assert_rule_write_access(db, rule, user)
    db.delete(rule)
    db.commit()
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="delete", module="alarms",
            target_id=str(rule_id), target_desc=f"删除告警规则:{rule_id}",
        )
    except Exception:
        pass
    return action_response(message="告警规则已删除")

@router.put("/rules/{rule_id}/toggle")
def toggle_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """启用/禁用告警规则（非 admin 限本 team 规则）"""
    rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    assert_rule_write_access(db, rule, user)
    rule.enabled = not rule.enabled
    db.commit()
    db.refresh(rule)
    return success_response(_serialize_rule(rule))

@router.post("/rules/{rule_id}/evaluate")
@limiter.limit("10/minute", key_func=_evaluate_limit_key)
def evaluate_rule(
    request: Request,
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """手动触发告警规则评估

    写端点 (可触发告警/工单/短信通知, 卡 2779d516): 要求 alarm:process 写权限
    + 用户维度限频, 防止越权/高频刷评估造成告警风暴。
    非 admin 限本 team 规则 (卡 960406a8)。
    """
    rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    assert_rule_write_access(db, rule, user)
    from app.services.alarm_rule_service import AlarmRuleEngine
    engine = AlarmRuleEngine()
    result = engine.evaluate_single_rule(rule_id, db)
    return success_response({
        "success": True,
        "rule_id": rule_id,
        "triggered": result.get('triggered', False),
        "alarm_id": result.get('alarm_id'),
        "message": result.get('message', '评估完成')
    })

@router.get("/stats/summary")
def get_alarm_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取告警统计

    移除原 ``cache`` —— 其 key 不含 user.team_id，跨用户同 key 会命中同一缓存串数据
    （与 stations.py 移除 @cached 同源）。
    """
    team_filter = None
    if not is_platform_admin(user):
        team_filter = Station.team_id == user.team_id

    # 使用 Core-level execute 避免 SQLAlchemy ORM 枚举转换异常
    status_stmt = select(Alarm.status, func.count(Alarm.id).label('cnt'))
    level_stmt = select(Alarm.level, func.count(Alarm.id).label('cnt'))
    if team_filter is not None:
        status_stmt = status_stmt.join(Station, Station.id == Alarm.station_id).where(team_filter)
        level_stmt = level_stmt.join(Station, Station.id == Alarm.station_id).where(team_filter)
    by_status_raw = db.execute(status_stmt.group_by(Alarm.status)).all()
    by_level_raw = db.execute(level_stmt.group_by(Alarm.level)).all()

    base = db.query(Alarm)
    if team_filter is not None:
        base = base.join(Station, Station.id == Alarm.station_id).filter(team_filter)
    today_count = base.filter(func.date(Alarm.created_at) == today_in_biz_tz()).count()
    active_count = base.filter(Alarm.status == AlarmStatus.ACTIVE).count()

    result = {
        "by_status": {_safe_enum_val(k, "unknown"): int(v) for k, v in by_status_raw},
        "by_level": {_safe_enum_val(k, "unknown"): int(v) for k, v in by_level_raw},
        "today_total": today_count,
        "active": active_count,
        "total": base.count(),
    }
    return success_response(result)


@router.get("/rule-logs")
def list_rule_logs(
    rule_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取告警规则触发日志（非 admin 经 station 归属过滤，卡 960406a8）"""
    query = db.query(AlarmRuleLog)
    if not is_platform_admin(user):
        query = query.join(Station, Station.id == AlarmRuleLog.station_id).filter(
            Station.team_id == user.team_id
        )
    if rule_id:
        query = query.filter(AlarmRuleLog.rule_id == rule_id)
    total = query.count()
    items = query.order_by(AlarmRuleLog.checked_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return paginated_response(items, total, page, page_size)


@router.get("/{alarm_id}")
def get_alarm(alarm_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取告警详情"""
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="告警不存在")
    assert_alarm_team_access(db, alarm_id, user)
    # 审计日志 (卡 3dd8954e: GET 详情本无写语义, 沿用既有 action=create 仅改归属为真实操作用户)
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="create", module="alarms",
            target_id=str(alarm.id), target_desc=f"创建告警:{alarm.content[:30] if alarm.content else ''}",
        )
    except Exception:
        pass
    return success_response(_serialize_alarm(alarm, db))

@router.get("/{alarm_id}/notifications")
def list_alarm_notifications(alarm_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取告警通知发送记录 (maint-platform-spec §2.1)

    返回该告警下所有渠道的通知发送结果，按发送时间倒序。
    """
    assert_alarm_team_access(db, alarm_id, user)
    records = db.query(AlarmNotification).filter(
        AlarmNotification.alarm_id == alarm_id
    ).order_by(
        AlarmNotification.sent_at.desc(), AlarmNotification.id.desc()
    ).all()
    return success_response([_serialize_alarm_notification(r) for r in records])


@router.put("/{alarm_id}/ack")
def acknowledge_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """确认告警"""
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="告警不存在")
    assert_alarm_team_access(db, alarm_id, user)
    alarm.status = AlarmStatus.ACKNOWLEDGED
    alarm.handled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alarm)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="create", module="alarms",
            target_id=str(alarm.id), target_desc=f"创建告警:{alarm.content[:30] if alarm.content else ''}",
        )
    except Exception:
        pass
    return success_response(_serialize_alarm(alarm, db))

@router.put("/{alarm_id}/resolve")
def resolve_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """解决告警"""
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="告警不存在")
    assert_alarm_team_access(db, alarm_id, user)
    alarm.status = AlarmStatus.RESOLVED
    alarm.handled_at = datetime.now(timezone.utc)
    alarm.cleared_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alarm)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="create", module="alarms",
            target_id=str(alarm.id), target_desc=f"创建告警:{alarm.content[:30] if alarm.content else ''}",
        )
    except Exception:
        pass
    return success_response(_serialize_alarm(alarm, db))

@router.put("/{alarm_id}/ignore")
def ignore_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """忽略告警"""
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="告警不存在")
    assert_alarm_team_access(db, alarm_id, user)
    alarm.status = AlarmStatus.IGNORED
    alarm.handled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alarm)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="create", module="alarms",
            target_id=str(alarm.id), target_desc=f"创建告警:{alarm.content[:30] if alarm.content else ''}",
        )
    except Exception:
        pass
    return success_response(_serialize_alarm(alarm, db))

class AlarmSimulate(BaseModel):
    """模拟告警请求体"""
    device_id: str
    alarm_type: str
    message: str
    level: Literal["info", "warning", "critical", "fatal"] = "warning"


@router.post("/simulate")
def simulate_alarm(
    data: AlarmSimulate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:process")),
):
    """模拟告警 - 创建告警记录写入DB"""
    dev_id = int(data.device_id) if data.device_id.isdigit() else 0
    if not is_platform_admin(user):
        dev = db.query(Device).filter(Device.id == dev_id).first()
        dev_team_id = (
            db.query(Station.team_id).filter(Station.id == dev.station_id).scalar()
            if dev and dev.station_id else None
        )
        if dev_team_id is None or user.team_id is None or dev_team_id != user.team_id:
            raise HTTPException(status_code=404, detail="设备不存在")
    alarm = Alarm(
        device_id=dev_id,
        alarm_type=data.alarm_type,
        level=AlarmLevel(data.level) if data.level else AlarmLevel.WARNING,
        content=data.message,
        status=AlarmStatus.ACTIVE,
    )
    db.add(alarm)
    db.commit()
    db.refresh(alarm)

    cache.delete("alarms:stats:summary")

    return success_response(_serialize_alarm(alarm, db))


@router.delete("/{alarm_id}")
def delete_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("alarm:delete")),
):
    """删除告警"""
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="告警不存在")
    assert_alarm_team_access(db, alarm_id, user)
    db.delete(alarm)
    db.commit()
    cache.delete("alarms:stats:summary")
    # 审计日志 (卡 eb0e1afd: 原 return 后死代码永不执行, 审计零落库, 前移至 return 前)
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="delete", module="alarms",
            target_id=str(alarm_id), target_desc=f"删除告警:{alarm_id}",
        )
    except Exception:
        pass
    return action_response(message="告警已删除")
