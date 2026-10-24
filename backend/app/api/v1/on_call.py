# -*- coding: utf-8 -*-
"""
值班排班 & On-Call 轮换 API — Phase9 (#52)

功能:
- 值班规则 CRUD
- 排班表自动生成 & 手动调整
- 当前值班人员查询
- 交接班管理
- 值班日志 CRUD
- 值班统计报表

Phase47 性能优化:
- 消除 N+1 查询: 使用批量用户查询替代循环内逐条查询
- 使用 selectinload 预加载关联
- 为高频只读 API 添加 @cached 缓存
"""

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, and_

from app.core.database import get_db
from app.core.iso_utils import parse_iso8601_or_400
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import is_platform_admin, team_scope, assert_team_access
from app.models.on_call import OnCallRule, OnCallShift, OnCallLog
from app.models.user import User
from app.core.cache import cached, cache
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["值班排班管理"], dependencies=[Depends(require_write_permission("workorder:edit"))])


# ============ 时区兜底 (卡 cea77711, 与电价卡 9912ba63/通知卡 ac0a7aa7 同根) ============

# naive start_from 解释用的最后防线时区, 模块加载时构造一次。
_FALLBACK_ONCALL_TZ = ZoneInfo("Asia/Shanghai")


def _global_oncall_timezone_name() -> str:
    """读 settings.ONCALL_TIMEZONE, 取不到回退上海。settings 懒导入规避加载时序耦合。"""
    try:
        from app.core.config import settings
        name = getattr(settings, "ONCALL_TIMEZONE", None)
        if isinstance(name, str) and name.strip():
            return name
    except Exception:
        pass
    return "Asia/Shanghai"


def _get_oncall_tz() -> ZoneInfo:
    """解析 naive 排班起始时间的目标时区。坏值 (None/空串/非 str/非法 IANA 名) 回退上海, 永不抛。"""
    try:
        return ZoneInfo(_global_oncall_timezone_name())
    except Exception:
        return _FALLBACK_ONCALL_TZ


# ============ Pydantic Schemas ============

class OnCallRuleCreate(BaseModel):
    name: str = Field(..., description="规则名称")
    team_id: Optional[int] = Field(None, description="所属团队ID（admin 指定；团队级用户由服务端强制覆盖）")
    station_id: Optional[int] = Field(None, description="适用站点 (NULL=全局)")
    schedule_type: Literal["daily", "weekly", "monthly", "custom"] = Field(default="weekly", description="轮换类型")
    # 卡 cea77711: 长度/范围语义校验下沉到 create_rule 业务层返回明确 400 中文消息
    # (与同函数 "用户X不存在" 一致), 故此处不设 min_length/ge。
    rotation_order: list[int] = Field(..., description="轮换顺序 (用户ID列表, 至少1人)")
    _normalize_rotation_order = field_validator("rotation_order", mode="before")(lambda v: json.loads(v) if isinstance(v, str) else v)
    shift_duration_hours: int = Field(default=168, le=720, description="每班时长(小时), 必须>0")  # 卡 1abf2c01: 上界防 timedelta 溢出 500; 0/负仍走业务层 400
    overlap_minutes: int = Field(default=30, ge=0, description="交接班重叠分钟数")
    escalation_level: int = Field(default=2, ge=1, le=5, description="升级级别数")
    escalation_timeout_minutes: int = Field(default=30, ge=5, description="升级超时(分钟)")
    notify_methods: list[str] = Field(default_factory=lambda: ["app", "sms"], description="通知方式")
    auto_assign_workorders: bool = Field(default=True, description="自动分配告警工单")


class OnCallRuleUpdate(BaseModel):
    name: Optional[str] = None
    rotation_order: Optional[list[int]] = None
    shift_duration_hours: Optional[int] = Field(default=None, le=720)
    overlap_minutes: Optional[int] = None
    escalation_level: Optional[int] = None
    escalation_timeout_minutes: Optional[int] = None
    notify_methods: Optional[list[str]] = None
    auto_assign_workorders: Optional[bool] = None
    enabled: Optional[bool] = None


class ShiftManualCreate(BaseModel):
    rule_id: int = Field(..., description="规则ID")
    user_id: int = Field(..., description="值班人员ID")
    backup_user_id: Optional[int] = Field(None, description="备份值班人ID")
    start_time: str = Field(..., description="开始时间 ISO8601")
    end_time: str = Field(..., description="结束时间 ISO8601")


class HandoverRequest(BaseModel):
    shift_id: int = Field(..., description="班次ID")
    notes: str = Field(..., description="交接备注")
    user_id: int = Field(..., description="交班人ID")


class OnCallLogCreate(BaseModel):
    shift_id: int = Field(..., description="班次ID")
    user_id: int = Field(..., description="记录人ID")
    event_type: Literal["note", "alarm", "workorder", "handover", "escalation", "incident"] = Field(default="note", description="类型")
    content: str = Field(..., description="日志内容")
    alarm_id: Optional[int] = Field(None, description="关联告警ID")
    workorder_id: Optional[str] = Field(None, description="关联工单号")
    severity: str = Field(default="info", description="严重级别: info|warning|critical")


# ============ Helper Functions ============

def _batch_get_users(db: Session, user_ids: set) -> dict:
    """批量查询用户, 返回 {user_id: user_object} 字典"""
    if not user_ids:
        return {}
    ids = [uid for uid in user_ids if uid is not None]
    if not ids:
        return {}
    users = db.query(User).filter(User.id.in_(ids)).all()
    return {u.id: u for u in users}


def _generate_shifts_for_rule(db: Session, rule: OnCallRule, start_from: Optional[datetime] = None, num_cycles: int = 4):
    """根据规则自动生成排班"""
    now = start_from or datetime.now(timezone.utc)
    if now.tzinfo is None:
        # 卡 cea77711 (与电价卡 9912ba63/通知卡 ac0a7aa7 同根): naive 起始时间按本地时区
        # (默认 Asia/Shanghai) 解释再转 UTC 落库。旧实现 replace(tzinfo=utc) 把用户本地
        # 墙钟当 UTC, 上海用户传 09:00 被存成 UTC09:00 (=上海17:00), 班次整体错位 8h。
        now = now.replace(tzinfo=_get_oncall_tz()).astimezone(timezone.utc)

    order = rule.rotation_order
    duration = timedelta(hours=rule.shift_duration_hours)
    current = now
    shifts_to_create = []

    for cycle in range(num_cycles):
        for idx, user_id in enumerate(order):
            backup_idx = (idx + 1) % len(order)
            backup_user_id = order[backup_idx] if len(order) > 1 else None

            shifts_to_create.append(OnCallShift(
                rule_id=rule.id,
                user_id=user_id,
                backup_user_id=backup_user_id,
                start_time=current,
                end_time=current + duration,
                status="scheduled",
            ))
            current += duration

    db.bulk_save_objects(shifts_to_create)
    return len(shifts_to_create)


def _get_current_shift(db: Session, rule_id: int):
    """获取当前正在执行的班次"""
    now = datetime.now(timezone.utc)
    return db.query(OnCallShift).filter(
        and_(
            OnCallShift.rule_id == rule_id,
            OnCallShift.start_time <= now,
            OnCallShift.end_time >= now,
            OnCallShift.status.in_(["scheduled", "active"]),
        )
    ).order_by(OnCallShift.start_time.desc()).first()


# ============ 值班规则 API ============

@router.get("/rules", summary="获取值班规则列表")
def list_rules(
    enabled_only: bool = Query(True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 卡 占位: @cached 装饰在 endpoint 上时 kwargs 含 db/user 依赖对象, default=str 落成
    # 含内存地址的 key → 每次请求 key 不同, 缓存永不命中。改手写显式 key (含 team 维度)。
    try:
        tid = team_scope(user)
        cache_key = f"oncall:rules:{tid if tid is not None else 'all'}:{enabled_only}"
        if (cached_result := cache.get_json(cache_key)) is not None:
            return cached_result
    # ── Phase47: 使用 selectinload 预加载 shifts ──
        query = db.query(OnCallRule).options(
            selectinload(OnCallRule.shifts)
        )
        # 任务卡 708350b3: team_id 服务端强制——团队级用户仅见本 team 规则
        scope = team_scope(user)
        if scope is not None:
            query = query.filter(OnCallRule.team_id == scope)
        if enabled_only:
            query = query.filter(OnCallRule.enabled == True)

        rules = query.order_by(OnCallRule.created_at.desc()).all()

        # ── Phase47: 批量查询所有涉及的用户 ──
        all_user_ids = set()
        for r in rules:
            current_shift = _get_current_shift(db, r.id)
            if current_shift:
                all_user_ids.add(current_shift.user_id)
        users_map = _batch_get_users(db, all_user_ids)

        items = []
        for r in rules:
            # Phase47: 使用预加载的 shifts 计算总数, 避免 N+1 COUNT 查询
            total_shifts = len(r.shifts)
            upcoming_shifts = sum(1 for s in r.shifts if s.status == "scheduled")

            current_shift = _get_current_shift(db, r.id)
            current_user = None
            if current_shift:
                u = users_map.get(current_shift.user_id)
                current_user = {"id": u.id, "name": u.username} if u else None

            items.append({
                "id": r.id,
                "name": r.name,
                "team_id": r.team_id,
                "station_id": r.station_id,
                "schedule_type": r.schedule_type,
                "rotation_order": r.rotation_order,
                "shift_duration_hours": r.shift_duration_hours,
                "overlap_minutes": r.overlap_minutes,
                "escalation_level": r.escalation_level,
                "escalation_timeout_minutes": r.escalation_timeout_minutes,
                "notify_methods": r.notify_methods,
                "auto_assign_workorders": r.auto_assign_workorders,
                "enabled": r.enabled,
                "current_oncall": current_user,
                "total_shifts": total_shifts,
                "upcoming_shifts": upcoming_shifts,
            })
        result = {"total": len(items), "rules": items}
        cache.set_json(cache_key, result, expire=30)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_rules 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/rules/{rule_id}", summary="获取值班规则详情")
def get_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # ── Phase47: 使用 selectinload 预加载 shifts ──
    try:
        rule = db.query(OnCallRule).options(
            selectinload(OnCallRule.shifts)
        ).filter(OnCallRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")
        assert_team_access(user, rule.team_id)

        shifts = rule.shifts  # Phase47: 使用已加载的 shifts, 避免额外查询

        # ── Phase47: 批量查询用户 ──
        user_ids = set()
        for s in shifts:
            user_ids.add(s.user_id)
        users_map = _batch_get_users(db, user_ids)

        return {
            "rule": {
                "id": rule.id,
                "name": rule.name,
                "team_id": rule.team_id,
                "station_id": rule.station_id,
                "schedule_type": rule.schedule_type,
                "rotation_order": rule.rotation_order,
                "shift_duration_hours": rule.shift_duration_hours,
                "overlap_minutes": rule.overlap_minutes,
                "escalation_level": rule.escalation_level,
                "escalation_timeout_minutes": rule.escalation_timeout_minutes,
                "notify_methods": rule.notify_methods,
                "auto_assign_workorders": rule.auto_assign_workorders,
                "enabled": rule.enabled,
            },
            "shifts": [{
                "id": s.id,
                "user_id": s.user_id,
                "user": {"id": u.id, "name": u.username} if (u := users_map.get(s.user_id)) else None,
                "backup_user_id": s.backup_user_id,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "status": s.status,
                "handover_completed": s.handover_completed,
            } for s in shifts],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/rules", summary="创建值班规则")
def create_rule(
    req: OnCallRuleCreate,
    background_tasks=None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # ── Phase47: 批量验证用户存在 ──
    try:
        # 卡 cea77711: 业务层校验返回明确 400 中文消息 (schema 仅约束类型, 不约束长度/范围)
        if not req.rotation_order:
            raise HTTPException(status_code=400, detail="轮换顺序不能为空，至少需要 1 名值班人员")
        if req.shift_duration_hours <= 0:
            raise HTTPException(status_code=400, detail="每班时长必须大于 0 小时")

        user_ids = list(req.rotation_order)
        existing_users = db.query(User).filter(User.id.in_(user_ids)).all()
        existing_ids = {u.id for u in existing_users}
        for uid in user_ids:
            if uid not in existing_ids:
                raise HTTPException(status_code=400, detail=f"用户 {uid} 不存在")

        # 任务卡 708350b3: team_id 服务端强制——admin 用 body 指定，
        # 团队级用户锁本人 team（OnCallRule.team_id 非空，必须有归属）
        if is_platform_admin(user):
            team_id = req.team_id
        else:
            team_id = user.team_id
        if team_id is None:
            raise HTTPException(status_code=400, detail="值班规则必须归属某团队")

        rule = OnCallRule(
            name=req.name,
            team_id=team_id,
            station_id=req.station_id,
            schedule_type=req.schedule_type,
            rotation_order=req.rotation_order,
            shift_duration_hours=req.shift_duration_hours,
            overlap_minutes=req.overlap_minutes,
            escalation_level=req.escalation_level,
            escalation_timeout_minutes=req.escalation_timeout_minutes,
            notify_methods=req.notify_methods,
            auto_assign_workorders=req.auto_assign_workorders,
        )
        # 卡 cea77711: rule 与排班同事务——flush 取 rule.id (不 commit), 排班生成后单次 commit;
        # 生成中途抛错则整体回滚, 不留孤儿规则 (旧实现 rule 先 commit 再生成班次二次 commit)。
        db.add(rule)
        db.flush()

        # 自动生成排班
        count = _generate_shifts_for_rule(db, rule)
        db.commit()

        # Phase47: 失效缓存
        cache.delete_pattern("oncall:*")

        return {"message": "规则创建成功，已自动生成排班", "rule_id": rule.id, "shifts_generated": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/rules/{rule_id}", summary="更新值班规则")
def update_rule(
    rule_id: int,
    req: OnCallRuleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        rule = db.query(OnCallRule).filter(OnCallRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")
        assert_team_access(user, rule.team_id)

        update_data = req.model_dump(exclude_unset=True)
        # 卡 cea77711: OnCallRuleUpdate 无 schema 约束, 旧实现接受 0/负时长与空轮换,
        # 后续 regenerate 生成 0 班次或 0 时长班次 → _get_current_shift 永不命中 (值班表真空)。
        if "rotation_order" in update_data and not update_data["rotation_order"]:
            raise HTTPException(status_code=400, detail="轮换顺序不能为空，至少需要 1 名值班人员")
        if "shift_duration_hours" in update_data and update_data["shift_duration_hours"] <= 0:
            raise HTTPException(status_code=400, detail="每班时长必须大于 0 小时")

        for key, value in update_data.items():
            setattr(rule, key, value)

        db.commit()
        # Phase47: 失效缓存
        cache.delete_pattern("oncall:*")
        return {"message": "规则更新成功", "rule_id": rule_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/rules/{rule_id}", summary="删除值班规则")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        rule = db.query(OnCallRule).filter(OnCallRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")
        assert_team_access(user, rule.team_id)

        # 检查是否有未完成的班次
        active = db.query(func.count(OnCallShift.id)).filter(
            and_(OnCallShift.rule_id == rule_id, OnCallShift.status.in_(["scheduled", "active"]))
        ).scalar()
        if active > 0:
            raise HTTPException(status_code=400, detail=f"规则仍有 {active} 个未完成班次，无法删除")

        db.delete(rule)
        db.commit()
        # Phase47: 失效缓存
        cache.delete_pattern("oncall:*")
        return {"message": f"规则 {rule_id} 已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/rules/{rule_id}/generate-shifts", summary="重新生成排班")
def regenerate_shifts(
    rule_id: int,
    start_from: Optional[str] = Query(None, description="起始时间 ISO8601"),
    num_cycles: int = Query(4, ge=1, le=12, description="生成周期数"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        rule = db.query(OnCallRule).filter(OnCallRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")
        assert_team_access(user, rule.team_id)

        # 删除尚未开始的班次
        now = datetime.now(timezone.utc)
        deleted = db.query(OnCallShift).filter(
            and_(OnCallShift.rule_id == rule_id, OnCallShift.start_time > now, OnCallShift.status == "scheduled")
        ).delete()

        start = parse_iso8601_or_400(start_from) if start_from else None
        count = _generate_shifts_for_rule(db, rule, start_from=start, num_cycles=num_cycles)
        db.commit()

        # Phase47: 失效缓存
        cache.delete_pattern("oncall:*")
        return {"message": "排班重新生成成功", "deleted": deleted, "created": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("regenerate_shifts 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ============ 班次 API ============

@router.get("/shifts/current", summary="获取当前所有值班人员")
def get_current_shifts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 卡 占位: 手写显式 cache key 替代 @cached (依赖对象致 key 漂移, 见 list_rules 注释)
    try:
        tid = team_scope(user)
        cache_key = f"oncall:current_shifts:{tid if tid is not None else 'all'}"
        if (cached_result := cache.get_json(cache_key)) is not None:
            return cached_result
        now = datetime.now(timezone.utc)
        # ── Phase47: 预加载 rule 关系 ──
        query = db.query(OnCallShift).options(
            selectinload(OnCallShift.rule)
        ).join(OnCallRule).filter(
            and_(
                OnCallShift.start_time <= now,
                OnCallShift.end_time >= now,
                OnCallShift.status.in_(["scheduled", "active"]),
            )
        )
        # 任务卡 708350b3: team_id 服务端强制——团队级用户仅见本 team 当前值班
        scope = team_scope(user)
        if scope is not None:
            query = query.filter(OnCallRule.team_id == scope)

        shifts = query.all()

        # ── Phase47: 批量查询用户 ──
        user_ids = set()
        for s in shifts:
            user_ids.add(s.user_id)
            if s.backup_user_id:
                user_ids.add(s.backup_user_id)
        users_map = _batch_get_users(db, user_ids)

        items = []
        for s in shifts:
            primary = users_map.get(s.user_id)
            backup = users_map.get(s.backup_user_id) if s.backup_user_id else None
            # 卡 52beb2a7: DateTime 列不存 tz, 写入的 aware UTC 被剥离 tzinfo → 读出 naive,
            # 与 aware now 直接相减抛 TypeError 致端点 500。归一为 UTC aware 再算术
            # (start_time/end_time 实际即 UTC, 写入源恒为 datetime.now(timezone.utc))。
            end = s.end_time
            if end is not None and end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            items.append({
                "shift_id": s.id,
                "rule_id": s.rule_id,
                "rule_name": s.rule.name if s.rule else None,
                "primary": {"id": primary.id, "name": primary.username} if primary else None,
                "backup": {"id": backup.id, "name": backup.username} if backup else None,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "remaining_hours": round((end - now).total_seconds() / 3600, 1) if end else None,
                "handover_completed": s.handover_completed,
            })
        result = {"current_shifts": items}
        cache.set_json(cache_key, result, expire=30)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_current_shifts 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/shifts", summary="获取班次列表")
def list_shifts(
    rule_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    start: Optional[str] = Query(None, description="开始时间过滤 ISO8601"),
    end: Optional[str] = Query(None, description="结束时间过滤 ISO8601"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # ── Phase47: 预加载 rule 关系 ──
    try:
        query = db.query(OnCallShift).options(
            selectinload(OnCallShift.rule)
        ).join(OnCallRule)
        # 卡 占位 (缺陷1): 团队级用户仅见本 team 班次。OnCallShift 无 team_id,
        # 经 OnCallRule.team_id 过滤, 口径与 get_current_shifts 一致。
        scope = team_scope(user)
        if scope is not None:
            query = query.filter(OnCallRule.team_id == scope)
        if rule_id:
            query = query.filter(OnCallShift.rule_id == rule_id)
        if user_id:
            query = query.filter(OnCallShift.user_id == user_id)
        if status:
            query = query.filter(OnCallShift.status == status)
        if start:
            query = query.filter(OnCallShift.end_time >= parse_iso8601_or_400(start))
        if end:
            query = query.filter(OnCallShift.start_time <= parse_iso8601_or_400(end))

        total = query.count()
        shifts = query.order_by(OnCallShift.start_time.desc()).offset((page - 1) * page_size).limit(page_size).all()

        # ── Phase47: 一次性批量查询所有用户 ──
        user_ids = set()
        for s in shifts:
            user_ids.add(s.user_id)
            if s.backup_user_id:
                user_ids.add(s.backup_user_id)
        users_map = _batch_get_users(db, user_ids)

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "shifts": [{
                "id": s.id,
                "rule_id": s.rule_id,
                "rule_name": s.rule.name if s.rule else None,
                "user_id": s.user_id,
                "user": {"id": u.id, "name": u.username} if (u := users_map.get(s.user_id)) else None,
                "backup_user_id": s.backup_user_id,
                "backup_user": {"id": bu.id, "name": bu.username} if s.backup_user_id and (bu := users_map.get(s.backup_user_id)) else None,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "status": s.status,
                "handover_completed": s.handover_completed,
                "handover_notes": s.handover_notes,
            } for s in shifts],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_shifts 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/shifts", summary="手动创建班次")
def create_shift(
    req: ShiftManualCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        rule = db.query(OnCallRule).filter(OnCallRule.id == req.rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail=f"规则 {req.rule_id} 不存在")
        assert_team_access(user, rule.team_id)

        start = parse_iso8601_or_400(req.start_time)
        end = parse_iso8601_or_400(req.end_time)

        shift = OnCallShift(
            rule_id=req.rule_id,
            user_id=req.user_id,
            backup_user_id=req.backup_user_id,
            start_time=start,
            end_time=end,
            status="scheduled",
        )
        db.add(shift)
        db.commit()
        db.refresh(shift)

        # Phase47: 失效缓存
        cache.delete_pattern("oncall:*")

        return {"message": "班次创建成功", "shift_id": shift.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_shift 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/shifts/{shift_id}", summary="更新班次状态")
def update_shift(
    shift_id: int,
    status: str = Query(..., description="目标状态: scheduled|active|completed|cancelled|missed"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        shift = db.query(OnCallShift).filter(OnCallShift.id == shift_id).first()
        if not shift:
            raise HTTPException(status_code=404, detail=f"班次 {shift_id} 不存在")
        # 卡 6a7b8c9d (审计#6): 跨队班次篡改 — 经 rule 归属校验, 口径与 create_shift 一致
        if not shift.rule:
            raise HTTPException(status_code=404, detail=f"班次 {shift_id} 不存在")
        assert_team_access(user, shift.rule.team_id)

        # 卡 5b7308f3: 状态白名单校验，防任意串入库污染统计
        allowed_statuses = {"scheduled", "active", "completed", "cancelled", "missed"}
        if status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"无效状态 '{status}'，允许值: {sorted(allowed_statuses)}",
            )

        shift.status = status
        shift.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"message": "班次状态已更新", "shift_id": shift_id, "status": status}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_shift 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ============ 交接班 API ============

@router.post("/shifts/handover", summary="执行交接班")
def handover_shift(
    req: HandoverRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        shift = db.query(OnCallShift).filter(OnCallShift.id == req.shift_id).first()
        if not shift:
            raise HTTPException(status_code=404, detail=f"班次 {req.shift_id} 不存在")
        # 卡 6a7b8c9d (审计#6): 跨队班次交接 — 经 rule 归属校验
        if not shift.rule:
            raise HTTPException(status_code=404, detail=f"班次 {req.shift_id} 不存在")
        assert_team_access(user, shift.rule.team_id)

        # 卡 cea77711: 幂等守卫——已交接的班次拒绝重复/并发交接, 杜绝双交接日志。
        if shift.handover_completed:
            raise HTTPException(status_code=400, detail="该班次已完成交接，请勿重复交接")

        shift.handover_notes = req.notes
        shift.handover_completed = True
        shift.updated_at = datetime.now(timezone.utc)

        # 创建交接日志
        log = OnCallLog(
            shift_id=req.shift_id,
            user_id=req.user_id,
            event_type="handover",
            content=req.notes,
            severity="info",
        )
        db.add(log)
        db.commit()

        return {"message": "交接班完成", "shift_id": req.shift_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("handover_shift 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ============ 值班日志 API ============

@router.get("/logs", summary="获取值班日志")
def list_logs(
    shift_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        # 卡 6a7b8c9d (审计#6): 团队级用户仅见本队日志 — 日志无 team_id,
        # 经 shift→rule.team_id 过滤, 口径与 list_shifts 一致。
        query = db.query(OnCallLog).join(OnCallShift, OnCallLog.shift_id == OnCallShift.id).join(OnCallRule)
        scope = team_scope(user)
        if scope is not None:
            query = query.filter(OnCallRule.team_id == scope)
        if shift_id:
            query = query.filter(OnCallLog.shift_id == shift_id)
        if user_id:
            query = query.filter(OnCallLog.user_id == user_id)
        if event_type:
            query = query.filter(OnCallLog.event_type == event_type)

        total = query.count()
        logs = query.order_by(OnCallLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "logs": [{
                "id": l.id,
                "shift_id": l.shift_id,
                "user_id": l.user_id,
                "event_type": l.event_type,
                "content": l.content,
                "alarm_id": l.alarm_id,
                "workorder_id": l.workorder_id,
                "severity": l.severity,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            } for l in logs],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_logs 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/logs", summary="创建值班日志")
def create_log(
    req: OnCallLogCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        shift = db.query(OnCallShift).filter(OnCallShift.id == req.shift_id).first()
        if not shift:
            raise HTTPException(status_code=404, detail=f"班次 {req.shift_id} 不存在")
        # 卡 6a7b8c9d (审计#6): 跨队日志写入 — 经 rule 归属校验, 口径与 create_log 的班次读取一致
        if not shift.rule:
            raise HTTPException(status_code=404, detail=f"班次 {req.shift_id} 不存在")
        assert_team_access(user, shift.rule.team_id)

        log = OnCallLog(
            shift_id=req.shift_id,
            user_id=req.user_id,
            event_type=req.event_type,
            content=req.content,
            alarm_id=req.alarm_id,
            workorder_id=req.workorder_id,
            severity=req.severity,
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        return {"message": "日志创建成功", "log_id": log.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_log 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ============ 统计 API ============

@router.get("/stats", summary="值班统计报表")
def get_stats(
    days: int = Query(30, ge=1, le=365, description="统计最近N天"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 卡 占位: 手写显式 cache key 替代 @cached (依赖对象致 key 漂移, 见 list_rules 注释)
    try:
        tid = team_scope(user)
        cache_key = f"oncall:stats:{tid if tid is not None else 'all'}:{days}"
        if (cached_result := cache.get_json(cache_key)) is not None:
            return cached_result
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # 卡 占位 (缺陷1): 统计按 team 过滤。OnCallShift/OnCallLog 均无 team_id,
        # 统一经 OnCallShift.rule → OnCallRule.team_id 关联过滤, 口径与 list_shifts 一致;
        # OnCallLog 经 shift_id 关联到本 team 班次。
        scope = team_scope(user)
        team_shifts = db.query(OnCallShift.id).join(OnCallRule)
        if scope is not None:
            team_shifts = team_shifts.filter(OnCallRule.team_id == scope)
        team_shifts = team_shifts.filter(OnCallShift.start_time >= cutoff).subquery()
        team_shift_ids = db.query(team_shifts.c.id)

        # 班次统计
        total_shifts = team_shift_ids.count()
        completed_shifts = db.query(func.count(OnCallShift.id)).filter(
            and_(OnCallShift.id.in_(team_shift_ids), OnCallShift.status == "completed")
        ).scalar()
        missed_shifts = db.query(func.count(OnCallShift.id)).filter(
            and_(OnCallShift.id.in_(team_shift_ids), OnCallShift.status == "missed")
        ).scalar()

        # 交接统计
        handover_done = db.query(func.count(OnCallShift.id)).filter(
            and_(OnCallShift.id.in_(team_shift_ids), OnCallShift.handover_completed == True)
        ).scalar()

        # 日志统计 (经 shift_id 归属到本 team 班次)
        team_logs = db.query(OnCallLog).filter(
            and_(OnCallLog.shift_id.in_(team_shift_ids), OnCallLog.created_at >= cutoff)
        )
        total_logs = team_logs.count()
        by_event = team_logs.with_entities(OnCallLog.event_type, func.count(OnCallLog.id)).group_by(
            OnCallLog.event_type
        ).all()

        # ── Phase47: 批量查询用户 ──
        by_user = db.query(
            OnCallShift.user_id, func.count(OnCallShift.id)
        ).filter(OnCallShift.id.in_(team_shift_ids)).group_by(OnCallShift.user_id).all()

        user_ids = {uid for uid, _ in by_user}
        users_map = _batch_get_users(db, user_ids)

        result = {
            "period_days": days,
            "shifts": {
                "total": total_shifts,
                "completed": completed_shifts,
                "missed": missed_shifts,
                "completion_rate": round(completed_shifts / total_shifts * 100, 1) if total_shifts > 0 else 0,
            },
            "handover": {
                "completed": handover_done,
                "rate": round(handover_done / total_shifts * 100, 1) if total_shifts > 0 else 0,
            },
            "logs": {
                "total": total_logs,
                "by_event_type": dict(by_event),
            },
            "by_user": [{"user_id": uid, "name": users_map.get(uid).username if users_map.get(uid) else f"User-{uid}", "shift_count": count} for uid, count in by_user],
        }
        cache.set_json(cache_key, result, expire=60)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_stats 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
