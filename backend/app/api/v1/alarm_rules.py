#!/usr/bin/env python3
"""
告警规则配置 API — 阈值设置/通知人配置 (SPEC 第7章)

独立的告警规则 CRUD 端点，前缀 /api/v1/alarm-rules
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Literal, Optional
import logging
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.alarm import AlarmRule, AlarmLevel
from app.models.station import Station
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin
from app.middleware.permission import require_permission
from app.core.response import success_response, paginated_response, action_response

router = APIRouter(dependencies=[Depends(get_current_user)])

from app.core.rate_limit import limiter


def _evaluate_limit_key(request: Request) -> str:
    """evaluate 按用户维度限流 key (卡 2779d516)。

    同 app/api/v1/alarms.py::_evaluate_limit_key (slowapi key_func 先于依赖注入,
    解 token sub 取用户标识, 失败回退 real IP)。
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


logger = logging.getLogger(__name__)

# ============================
# Pydantic 请求/响应模型
# ============================

class AlarmRuleCreate(BaseModel):
    """创建告警规则"""
    name: str = Field(..., max_length=100)
    description: Optional[str] = ""
    device_type: Optional[str] = ""
    device_ids: Optional[list] = None
    station_ids: Optional[list] = None
    metric: str = Field(..., max_length=50)
    operator: Literal[">", "<", ">=", "<=", "==", "!="] = ">"
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
    """更新告警规则（所有字段可选）"""
    name: Optional[str] = Field(None, max_length=100)
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


# ============================
# 辅助函数
# ============================

def _serialize_rule(rule: AlarmRule) -> dict:
    """将 AlarmRule ORM 对象序列化为 dict"""
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
        'level': rule.level.value if rule.level else 'warning',
        'alarm_template': rule.alarm_template,
        'notify_users': rule.notify_users,
        'auto_create_workorder': rule.auto_create_workorder,
        'workorder_priority': rule.workorder_priority,
        'enabled': rule.enabled,
        'silence_minutes': rule.silence_minutes,
        'created_at': rule.created_at.isoformat() if rule.created_at else None,
        'updated_at': rule.updated_at.isoformat() if rule.updated_at else None,
    }


# ============================
# Team scope 辅助（卡 960406a8，供 alarms.py 重复端点族复用）
# ============================

def _user_team_station_ids(db: Session, user: User) -> set:
    """用户所属 team 的站点 id 集合（admin 不调用此函数）。"""
    return {
        sid for (sid,) in db.query(Station.id).filter(Station.team_id == user.team_id).all()
    }


def _rule_readable(rule: AlarmRule, team_station_ids: set) -> bool:
    """读可见性：平台级规则（空 station_ids）或与本 team 站点有交集。"""
    rule_station_ids = rule.station_ids or []
    return not rule_station_ids or bool(set(rule_station_ids) & team_station_ids)


def apply_rule_list_scope(query, db: Session, user: User):
    """列表查询作用域过滤：admin 全量；非 admin 只见平台级 + 本 team 站点规则。

    station_ids 是 JSON 列，SQL 无法精确做交集 → 拉全量 id 后在 Python 侧
    过滤（规则量级为配置数据，可接受）。
    """
    if is_platform_admin(user):
        return query
    team_ids = _user_team_station_ids(db, user)
    all_rules = query.all()
    visible = [r.id for r in all_rules if _rule_readable(r, team_ids)]
    from app.models.alarm import AlarmRule as _AR
    return query.filter(_AR.id.in_(visible))


def assert_rule_write_access(db: Session, rule: AlarmRule, user: User) -> None:
    """写操作归属校验：admin 豁免；非 admin 目标规则须全部站点 ⊆ 本 team。

    平台级（空 station_ids）或含他队站点 → 404（不泄露存在）。
    """
    if is_platform_admin(user):
        return
    rule_station_ids = rule.station_ids or []
    if not rule_station_ids:
        # 平台级规则（空 station_ids 影响所有站）保留给 admin
        raise HTTPException(status_code=404, detail="告警规则不存在")
    team_ids = _user_team_station_ids(db, user)
    if not set(rule_station_ids) <= team_ids:
        raise HTTPException(status_code=404, detail="告警规则不存在")


def assert_rule_station_ids_writable(db: Session, station_ids: Optional[list], user: User) -> None:
    """创建/更新时提交的 station_ids 校验：非 admin 禁止平台级（空）与他队站点。

    空 station_ids → 403（平台级规则保留给 admin）；含他队站点 → 404。
    """
    if is_platform_admin(user):
        return
    if not station_ids:
        # 平台级规则保留给 admin; 用 404 而非 403, 与 RBAC 契约
        # (403 专属权限不足) 及「不泄露存在」语义保持一致
        raise HTTPException(status_code=404, detail="告警规则不存在")
    team_ids = _user_team_station_ids(db, user)
    if not set(station_ids) <= team_ids:
        raise HTTPException(status_code=404, detail="站点不存在")


# ============================
# CRUD 端点
# ============================

@router.get("")
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


@router.get("/{rule_id}")
def get_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取单个告警规则详情（非 admin 限平台级 + 本 team 站点规则）"""
    rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    if not is_platform_admin(user) and not _rule_readable(rule, _user_team_station_ids(db, user)):
        raise HTTPException(status_code=404, detail="告警规则不存在")
    return success_response(_serialize_rule(rule))


@router.post("")
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("告警规则创建冲突 name=%s", data.name)
        raise HTTPException(status_code=409, detail="告警规则写入冲突")
    except Exception:
        db.rollback()
        logger.exception("告警规则创建失败 name=%s", data.name)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(rule)
    return success_response(_serialize_rule(rule))


@router.put("/{rule_id}")
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

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("告警规则更新冲突 rule_id=%s", rule_id)
        raise HTTPException(status_code=409, detail="告警规则写入冲突")
    except Exception:
        db.rollback()
        logger.exception("告警规则更新失败 rule_id=%s", rule_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(rule)
    return success_response(_serialize_rule(rule))


@router.delete("/{rule_id}")
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
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("告警规则删除失败 rule_id=%s", rule_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return action_response(message="告警规则已删除")


@router.put("/{rule_id}/toggle")
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
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("告警规则切换失败 rule_id=%s", rule_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(rule)
    return success_response(_serialize_rule(rule))


@router.post("/{rule_id}/evaluate")
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
    + 用户维度限频 (与 /alarms/rules/{id}/evaluate 重复端点同步加固)。
    非 admin 限本 team 规则 (卡 960406a8)。
    """
    rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
    if rule is not None:
        # 规则存在才做归属校验; 不存在的 id 沿用 engine 既有契约
        # (返回 triggered=False 的 200, 见 TestEvaluate)
        assert_rule_write_access(db, rule, user)
    from app.services.alarm_rule_service import AlarmRuleEngine
    try:
        engine = AlarmRuleEngine()
        result = engine.evaluate_single_rule(rule_id, db)
    except Exception:
        logger.exception("告警规则评估失败 rule_id=%s", rule_id)
        raise HTTPException(status_code=500, detail="告警规则评估失败")
    return success_response({
        "success": True,
        "rule_id": rule_id,
        "triggered": result.get('triggered', False),
        "alarm_id": result.get('alarm_id'),
        "message": result.get('message', '评估完成'),
    })
