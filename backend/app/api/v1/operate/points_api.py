"""
积分管理 API - P0 运营核心补齐
POST   /api/v1/operate/points          — 创建积分规则
GET    /api/v1/operate/points          — 积分规则列表
GET    /api/v1/operate/points/{id}     — 积分规则详情
PUT    /api/v1/operate/points/{id}     — 更新积分规则
DELETE /api/v1/operate/points/{id}     — 删除积分规则
GET    /api/v1/operate/points/records  — 积分流水记录
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.points import PointsRule, PointsRecord, PointsRuleType, PointsRecordType
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import require_platform_admin, is_platform_admin

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

# ── Pydantic Schemas ──

class PointsRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    rule_type: PointsRuleType = PointsRuleType.CHARGE
    points: int = Field(..., ge=0)
    unit: Optional[str] = None
    daily_limit: Optional[int] = Field(None, ge=0)
    weekly_limit: Optional[int] = Field(None, ge=0)
    total_limit: Optional[int] = Field(None, ge=0)
    applicable_user_types: Optional[str] = None
    min_amount: Optional[float] = Field(None, ge=0)
    points_expire_days: Optional[int] = Field(None, ge=1)
    is_active: bool = True
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None

    @model_validator(mode="after")
    def _validate_time_window(self):
        # 生效窗口交叉校验：两者都传时 end_time 必须 >= start_time（422）
        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time 必须晚于或等于 start_time")
        return self

class PointsRuleUpdate(BaseModel):
    name: Optional[str] = None
    rule_type: Optional[PointsRuleType] = None
    points: Optional[int] = Field(None, ge=0)
    unit: Optional[str] = None
    daily_limit: Optional[int] = Field(None, ge=0)
    weekly_limit: Optional[int] = Field(None, ge=0)
    total_limit: Optional[int] = Field(None, ge=0)
    applicable_user_types: Optional[str] = None
    min_amount: Optional[float] = Field(None, ge=0)
    points_expire_days: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None

    @model_validator(mode="after")
    def _validate_time_window(self):
        # 部分更新：仅当本次请求两者都传时校验相对关系（卡b10e33d8）
        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time 必须晚于或等于 start_time")
        return self

class PointsRecordCreate(BaseModel):
    """运营手动发放/调整积分流水。

    PointsRecord 无业务自动写入点(充电/签到等场景未接线), 此 schema 供运营补录/
    赠送/调整积分。balance_after 未显式传入时由 balance_before + points 推导。
    """
    user_id: int
    record_type: PointsRecordType = PointsRecordType.EARN
    points: int
    rule_id: Optional[int] = None
    user_type: Optional[str] = None
    balance_before: int = Field(0, ge=0)
    balance_after: Optional[int] = None
    order_id: Optional[int] = None
    description: Optional[str] = None
    expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _validate_points_semantics(self):
        # 语义守卫（卡b10e33d8）：
        # - EARN 为正向获得类流水，points 必须 > 0；
        # - REDEEM/EXPIRE 为扣减类，points 允许负值；
        # - ADJUST 双向调整不限制符号；
        # - 无论是否显式传入 balance_after，扣减后余额不得为负（无 service 层，schema 层兜底）。
        if self.record_type == PointsRecordType.EARN and self.points <= 0:
            raise ValueError("earn 类型流水 points 必须大于 0")
        derived_after = self.balance_after if self.balance_after is not None else self.balance_before + self.points
        if derived_after < 0:
            raise ValueError("扣减后余额(balance_after)不得为负")
        return self

# ── PointsRule CRUD ──

@router.post("/points", summary="创建积分规则")
def create_points_rule(body: PointsRuleCreate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = PointsRule(**body.model_dump())
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return success_response({"id": obj.id, "name": obj.name}, "积分规则创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_points_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/points", summary="积分规则列表")
def list_points_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    rule_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(PointsRule)
        if is_active is not None:
            q = q.filter(PointsRule.is_active == is_active)
        if rule_type:
            q = q.filter(PointsRule.rule_type == rule_type)
        total = q.count()
        items = q.order_by(PointsRule.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        data = [{c.name: str(getattr(i, c.name)) if isinstance(getattr(i, c.name), datetime) else getattr(i, c.name) for c in i.__table__.columns} for i in items]
        return paginated_response(data, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_points_rules 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ── 积分流水记录 ──

@router.post("/points/records", summary="手动发放/调整积分流水")
def create_points_record(body: PointsRecordCreate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        data = body.model_dump()
        if data.get("balance_after") is None:
            data["balance_after"] = data.get("balance_before", 0) + data["points"]
        obj = PointsRecord(**data)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return success_response({"id": obj.id}, "积分流水创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_points_record 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/points/records", summary="积分流水记录")
def points_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    record_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        q = db.query(PointsRecord)
        # team scoping（任务卡 ab5c5f17）：积分规则为平台级配置（读对登录用户可见）；
        # 积分流水按用户归属过滤，非 admin 仅返回本 team 用户的流水（经 user→team）。
        if not is_platform_admin(user):
            q = q.join(User, PointsRecord.user_id == User.id).filter(User.team_id == user.team_id)
        if user_id is not None:
            q = q.filter(PointsRecord.user_id == user_id)
        if record_type:
            q = q.filter(PointsRecord.record_type == record_type)
        total = q.count()
        items = q.order_by(PointsRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        data = [{c.name: str(getattr(i, c.name)) if isinstance(getattr(i, c.name), datetime) else getattr(i, c.name) for c in i.__table__.columns} for i in items]
        return paginated_response(data, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("points_records 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ── 积分统计 ──

@router.get("/points/stats", summary="积分统计")
def points_stats(db: Session = Depends(get_db)):
    try:
        total_rules = db.query(func.count(PointsRule.id)).scalar() or 0
        active_rules = db.query(func.count(PointsRule.id)).filter(PointsRule.is_active == True).scalar() or 0
        total_earned = db.query(func.coalesce(func.sum(PointsRecord.points), 0)).filter(PointsRecord.points > 0).scalar() or 0
        total_records = db.query(func.count(PointsRecord.id)).scalar() or 0

        return success_response({
            "total_rules": total_rules,
            "active_rules": active_rules,
            "total_earned": int(total_earned),
            "total_records": total_records,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("points_stats 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ── 积分规则 CRUD（by id，放在 records/stats 之后避免路由冲突）──

@router.get("/points/{rule_id}", summary="积分规则详情")
def get_points_rule(rule_id: int, db: Session = Depends(get_db)):
    try:
        obj = db.query(PointsRule).filter(PointsRule.id == rule_id).first()
        if not obj:
            raise HTTPException(404, "积分规则不存在")
        return success_response({c.name: str(getattr(obj, c.name)) if isinstance(getattr(obj, c.name), datetime) else getattr(obj, c.name) for c in obj.__table__.columns})
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_points_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/points/{rule_id}", summary="更新积分规则")
def update_points_rule(rule_id: int, body: PointsRuleUpdate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = db.query(PointsRule).filter(PointsRule.id == rule_id).first()
        if not obj:
            raise HTTPException(404, "积分规则不存在")
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(obj, k, v)
        db.commit()
        db.refresh(obj)
        return success_response({"id": obj.id, "name": obj.name}, "更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_points_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/points/{rule_id}", summary="删除积分规则")
def delete_points_rule(rule_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = db.query(PointsRule).filter(PointsRule.id == rule_id).first()
        if not obj:
            raise HTTPException(404, "积分规则不存在")
        db.delete(obj)
        db.commit()
        return success_response(None, "已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_points_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})