"""光储充能量策略 REST API — P1-4 (任务卡 P1-4)

对齐预研文档《光储充能量策略-实现预研.md》§3 端点清单, prefix=/energy-strategy:

A. 策略配置 (station_energy_strategy)
   - GET    /strategies              列表 (按 user.team_id 隔离)
   - GET    /strategies/{station_id} 单站策略详情
   - PUT    /strategies/{station_id} 更新策略配置 (energy:strategy:edit)

B. 模板管理 (energy_price_template + energy_price_period)
   - GET    /price-templates                       模板列表
   - GET    /price-templates/by-province/{province} 当前生效模板(含时段明细)
   - POST   /price-templates                       新建模板版本 (energy:price:edit)
   - PUT    /price-templates/{id}                  更新生效区间/开关 (energy:price:edit)

C. 调度计划 (energy_dispatch_plan)
   - GET    /plans/{station_id}  当日计划曲线
   - GET    /plans/current       当前团队最新窗口计划

D. 能量流水 (energy_flow_log, 对齐 energy_report.py 风格)
   - GET    /flow     能量流时序 (15min)
   - GET    /savings  套利/省电费汇总

权限: router 级 get_current_user 强制认证 + 取 user.team_id;
      写端点叠加 require_permission("energy:*:edit"), admin/super_admin 直通,
      其余角色查 ROLE_PERMISSIONS_MATRIX (energy:* 权限点预留, 矩阵补齐后自动生效)。
团队隔离: 列表/详情按 user.team_id 过滤, 跨团队资源 404 (不暴露存在性)。
"""
import logging
import re
from datetime import date, time as dt_time, datetime
from typing import Optional, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.tasks.tz_utils import today_in_biz_tz
from app.models.energy_strategy import (
    EnergyPriceTemplate,
    EnergyPricePeriod,
    StationEnergyStrategy,
    EnergyDispatchPlan,
    EnergyFlowLog,
)
from app.models.pricing_v2 import PeriodType
from app.models.station import Station
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

_ADMIN_ROLES = ("admin", "super_admin")


# ═══════════════════════════════════════════════════════════════
# Pydantic Schemas
# ═══════════════════════════════════════════════════════════════

class PeriodCreate(BaseModel):
    period_type: str = Field(..., description="peak/shoulder/flat/valley")
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    purchase_price: float = Field(..., ge=0)
    # float_ratio 现状（卡b10e33d8 调研）：仅落库(EnergyStrategyPeriod.float_ratio)与
    # 序列化展示，全仓无电价计算消费点，故暂不加数值边界；一旦接入价格计算，
    # 需补边界（如 ge=-1, le=10）防止极端比例污染电价。
    float_ratio: Optional[float] = None


class PriceTemplateCreate(BaseModel):
    province: str = Field(..., min_length=1, max_length=50)
    version: int = Field(1, ge=1)
    effective_from: str = Field(..., description="YYYY-MM-DD")
    effective_until: Optional[str] = None
    season_start_month: Optional[int] = Field(None, ge=1, le=12)
    season_end_month: Optional[int] = Field(None, ge=1, le=12)
    allow_export_to_grid: bool = False
    is_two_part_tariff: bool = False
    is_active: bool = True
    team_id: Optional[int] = None  # 仅 admin 可指定; 非 admin 强制绑本团队
    periods: list[PeriodCreate] = Field(default_factory=list)


class PriceTemplateUpdate(BaseModel):
    effective_until: Optional[str] = None
    season_start_month: Optional[int] = Field(None, ge=1, le=12)
    season_end_month: Optional[int] = Field(None, ge=1, le=12)
    allow_export_to_grid: Optional[bool] = None
    is_two_part_tariff: Optional[bool] = None
    is_active: Optional[bool] = None


class StrategyUpdate(BaseModel):
    price_template_id: Optional[int] = None
    scenario_preset: Optional[str] = None
    transformer_capacity_kva: Optional[float] = None
    pv_capacity_kw: Optional[float] = None
    ess_capacity_kwh: Optional[float] = None
    declared_demand_kw: Optional[float] = None
    strategy_config: Optional[dict[str, Any]] = None
    energy_flow_priority: Optional[dict[str, Any]] = None
    soc_floor: Optional[float] = Field(None, ge=0, le=1)
    soc_reserve_min: Optional[float] = None
    soc_reserve_max: Optional[float] = None
    max_daily_cycles: Optional[int] = None
    is_active: Optional[bool] = None


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _role(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else user.role


def _team_filter(user: User) -> Optional[int]:
    """admin/super_admin → None (不过滤); 团队级用户 → user.team_id。"""
    return None if _role(user) in _ADMIN_ROLES else user.team_id


def _assert_team(resource_team_id: Optional[int], user: User) -> None:
    """跨团队访问 → 404 (不暴露资源存在性)。admin 直通。"""
    if _role(user) in _ADMIN_ROLES:
        return
    if resource_team_id is None or user.team_id is None or resource_team_id != user.team_id:
        raise HTTPException(404, "策略不存在")


def _parse_time(s: Optional[str]) -> Optional[dt_time]:
    if not s:
        return None
    h, m = s.split(":")
    return dt_time(int(h), int(m))


def _parse_date(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


# 严格 YYYY-MM-DD (4-2-2 补零) — 供 date_from/date_to 查询参数校验 (卡 1e168cb3)。
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date_bound_or_400(value: str, *, end_of_day: bool = False) -> datetime:
    """严格校验 YYYY-MM-DD 日期串, 返回当日下界(00:00:00)/上界(23:59:59) datetime。

    date_from/date_to 应为纯日期; 旧拼接式 ``datetime.fromisoformat(value + " 00:00:00")``
    对带时间/非法日历串抛 ``ValueError`` 冒泡 500, 且对 ``"2026-08-08T12:00:00"`` 类
    输入产生语义错乱。此处正则锁 4-2-2 补零格式 + ``strptime`` 锁日历合法性, 坏值显式 400。
    """
    if not _DATE_ONLY_RE.match(value):
        raise HTTPException(400, f"日期格式无效: {value} (需 YYYY-MM-DD)")
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, f"非法日期: {value} (需 YYYY-MM-DD)")
    return datetime.combine(d, dt_time(23, 59, 59) if end_of_day else dt_time(0, 0, 0))


def _fmt_time(t: Optional[dt_time]) -> Optional[str]:
    return t.strftime("%H:%M") if t else None


def _fmt_date(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _fmt_dt(dt: Any) -> Optional[str]:
    return dt.isoformat() if dt else None


def _template_to_dict(o: EnergyPriceTemplate) -> dict:
    return {
        "id": o.id,
        "province": o.province,
        "version": o.version,
        "effective_from": _fmt_date(o.effective_from),
        "effective_until": _fmt_date(o.effective_until),
        "season_start_month": o.season_start_month,
        "season_end_month": o.season_end_month,
        "allow_export_to_grid": o.allow_export_to_grid,
        "is_two_part_tariff": o.is_two_part_tariff,
        "is_active": o.is_active,
        "team_id": o.team_id,
        "created_at": _fmt_dt(o.created_at),
        "updated_at": _fmt_dt(o.updated_at),
    }


def _period_to_dict(o: EnergyPricePeriod) -> dict:
    return {
        "id": o.id,
        "template_id": o.template_id,
        "period_type": o.period_type.value if o.period_type else None,
        "start_time": _fmt_time(o.start_time),
        "end_time": _fmt_time(o.end_time),
        "purchase_price": float(o.purchase_price) if o.purchase_price is not None else 0.0,
        "float_ratio": float(o.float_ratio) if o.float_ratio is not None else None,
    }


def _strategy_to_dict(o: StationEnergyStrategy) -> dict:
    return {
        "id": o.id,
        "station_id": o.station_id,
        "team_id": o.team_id,
        "price_template_id": o.price_template_id,
        "scenario_preset": o.scenario_preset,
        "transformer_capacity_kva": o.transformer_capacity_kva,
        "pv_capacity_kw": o.pv_capacity_kw,
        "ess_capacity_kwh": o.ess_capacity_kwh,
        "declared_demand_kw": o.declared_demand_kw,
        "strategy_config": o.strategy_config,
        "energy_flow_priority": o.energy_flow_priority,
        "soc_floor": o.soc_floor,
        "soc_reserve_min": o.soc_reserve_min,
        "soc_reserve_max": o.soc_reserve_max,
        "max_daily_cycles": o.max_daily_cycles,
        "is_active": o.is_active,
        "created_at": _fmt_dt(o.created_at),
        "updated_at": _fmt_dt(o.updated_at),
    }


def _plan_to_dict(o: EnergyDispatchPlan) -> dict:
    return {
        "id": o.id,
        "station_id": o.station_id,
        "team_id": o.team_id,
        "window_start": _fmt_dt(o.window_start),
        "window_end": _fmt_dt(o.window_end),
        "price_template_id": o.price_template_id,
        "pv_setpoint_kw": o.pv_setpoint_kw,
        "ess_charge_kw": o.ess_charge_kw,
        "ess_discharge_kw": o.ess_discharge_kw,
        "grid_purchase_kw": o.grid_purchase_kw,
        "grid_export_kw": o.grid_export_kw,
        "available_power_budget_kw": o.available_power_budget_kw,
        "winning_strategies": o.winning_strategies,
        "decision_reason": o.decision_reason,
        "created_at": _fmt_dt(o.created_at),
    }


def _flow_to_dict(o: EnergyFlowLog) -> dict:
    return {
        "id": o.id,
        "station_id": o.station_id,
        "team_id": o.team_id,
        "window_start": _fmt_dt(o.window_start),
        "pv_generation_kwh": o.pv_generation_kwh,
        "pv_self_consumed_kwh": o.pv_self_consumed_kwh,
        "ess_charge_kwh": o.ess_charge_kwh,
        "ess_discharge_kwh": o.ess_discharge_kwh,
        "grid_purchase_kwh": o.grid_purchase_kwh,
        "grid_export_kwh": o.grid_export_kwh,
        "charger_load_kwh": o.charger_load_kwh,
        "soc_snapshot": o.soc_snapshot,
        "cost_saving_yuan": float(o.cost_saving_yuan) if o.cost_saving_yuan is not None else 0.0,
        "created_at": _fmt_dt(o.created_at),
    }


# ═══════════════════════════════════════════════════════════════
# A. 策略配置
# ═══════════════════════════════════════════════════════════════

@router.get("/strategies")
def list_strategies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """场站策略列表 (按 user.team_id 隔离)。"""
    q = db.query(StationEnergyStrategy)
    tid = _team_filter(user)
    if tid is not None:
        q = q.filter(StationEnergyStrategy.team_id == tid)
    total = q.count()
    items = q.order_by(StationEnergyStrategy.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_strategy_to_dict(i) for i in items], total, page, page_size)


@router.get("/strategies/{station_id}")
def get_strategy(
    station_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """单站策略详情 (跨团队 404)。"""
    o = db.query(StationEnergyStrategy) \
        .filter(StationEnergyStrategy.station_id == station_id).first()
    if not o:
        raise HTTPException(404, "策略不存在")
    _assert_team(o.team_id, user)
    return success_response(_strategy_to_dict(o))


@router.put("/strategies/{station_id}")
def update_strategy(
    station_id: int,
    body: StrategyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("energy:strategy:edit")),
):
    """更新策略配置 (energy:strategy:edit, 跨团队 404)。"""
    o = db.query(StationEnergyStrategy) \
        .filter(StationEnergyStrategy.station_id == station_id).first()
    if not o:
        raise HTTPException(404, "策略不存在")
    _assert_team(o.team_id, user)

    for f in (
        "price_template_id", "scenario_preset", "transformer_capacity_kva",
        "pv_capacity_kw", "ess_capacity_kwh", "declared_demand_kw",
        "strategy_config", "energy_flow_priority",
        "soc_floor", "soc_reserve_min", "soc_reserve_max",
        "max_daily_cycles", "is_active",
    ):
        v = getattr(body, f)
        if v is not None:
            setattr(o, f, v)
    try:
        db.commit()
        db.refresh(o)
    except Exception:
        db.rollback()
        logger.exception("更新场站策略失败 station_id=%s", station_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return success_response(_strategy_to_dict(o), "策略更新成功")


# ═══════════════════════════════════════════════════════════════
# B. 模板管理
# ═══════════════════════════════════════════════════════════════

@router.get("/price-templates")
def list_price_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    province: Optional[str] = Query(None),
    version: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """购电价模板列表 (团队级用户可见平台级 + 本团队级)。"""
    q = db.query(EnergyPriceTemplate)
    tid = _team_filter(user)
    if tid is not None:
        q = q.filter(or_(
            EnergyPriceTemplate.team_id == tid,
            EnergyPriceTemplate.team_id.is_(None),
        ))
    if province:
        q = q.filter(EnergyPriceTemplate.province == province)
    if version is not None:
        q = q.filter(EnergyPriceTemplate.version == version)
    if is_active is not None:
        q = q.filter(EnergyPriceTemplate.is_active == is_active)
    total = q.count()
    items = q.order_by(EnergyPriceTemplate.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_template_to_dict(i) for i in items], total, page, page_size)


@router.get("/price-templates/by-province/{province}")
def price_template_by_province(
    province: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按省份取当前生效模板 (含时段明细); 取最高版本。"""
    today = today_in_biz_tz()
    q = db.query(EnergyPriceTemplate).filter(
        EnergyPriceTemplate.province == province,
        EnergyPriceTemplate.is_active == True,  # noqa: E712
        EnergyPriceTemplate.effective_from <= today,
        or_(
            EnergyPriceTemplate.effective_until.is_(None),
            EnergyPriceTemplate.effective_until >= today,
        ),
    )
    tid = _team_filter(user)
    if tid is not None:
        q = q.filter(or_(
            EnergyPriceTemplate.team_id == tid,
            EnergyPriceTemplate.team_id.is_(None),
        ))
    tpl = q.order_by(EnergyPriceTemplate.version.desc()).first()
    if not tpl:
        raise HTTPException(404, f"未找到省份 {province} 的生效模板")
    periods = db.query(EnergyPricePeriod) \
        .filter(EnergyPricePeriod.template_id == tpl.id).all()
    data = _template_to_dict(tpl)
    data["periods"] = [_period_to_dict(p) for p in periods]
    return success_response(data)


@router.post("/price-templates")
def create_price_template(
    body: PriceTemplateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("energy:price:edit")),
):
    """新建模板版本 + 时段明细 (energy:price:edit)。

    非 admin 创建的模板强制绑定 user.team_id; admin 可建平台级(team_id=NULL)
    或指定 team_id。
    """
    # 校验时段类型
    for p in body.periods:
        try:
            PeriodType(p.period_type)
        except ValueError:
            raise HTTPException(400, f"无效的时段类型: {p.period_type}")

    team_id = body.team_id if _role(user) in _ADMIN_ROLES else user.team_id
    tpl = EnergyPriceTemplate(
        province=body.province,
        version=body.version,
        effective_from=_parse_date(body.effective_from),
        effective_until=_parse_date(body.effective_until),
        season_start_month=body.season_start_month,
        season_end_month=body.season_end_month,
        allow_export_to_grid=body.allow_export_to_grid,
        is_two_part_tariff=body.is_two_part_tariff,
        is_active=body.is_active,
        team_id=team_id,
    )
    try:
        db.add(tpl)
        db.commit()
        db.refresh(tpl)
        for p in body.periods:
            db.add(EnergyPricePeriod(
                template_id=tpl.id,
                period_type=PeriodType(p.period_type),
                start_time=_parse_time(p.start_time),
                end_time=_parse_time(p.end_time),
                purchase_price=p.purchase_price,
                float_ratio=p.float_ratio,
            ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("创建购电价模板失败 province=%s version=%s", body.province, body.version)
        raise HTTPException(status_code=500, detail="内部错误")
    return success_response(_template_to_dict(tpl), "模板创建成功")


@router.put("/price-templates/{template_id}")
def update_price_template(
    template_id: int,
    body: PriceTemplateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission("energy:price:edit")),
):
    """更新模板生效区间/开关 (energy:price:edit)。"""
    o = db.query(EnergyPriceTemplate) \
        .filter(EnergyPriceTemplate.id == template_id).first()
    if not o:
        raise HTTPException(404, "模板不存在")
    # 团队级用户仅可改本团队模板 (平台级模板只读)
    tid = _team_filter(user)
    if tid is not None and o.team_id is not None and o.team_id != tid:
        raise HTTPException(404, "模板不存在")

    if body.effective_until is not None:
        o.effective_until = _parse_date(body.effective_until)
    if body.season_start_month is not None:
        o.season_start_month = body.season_start_month
    if body.season_end_month is not None:
        o.season_end_month = body.season_end_month
    if body.allow_export_to_grid is not None:
        o.allow_export_to_grid = body.allow_export_to_grid
    if body.is_two_part_tariff is not None:
        o.is_two_part_tariff = body.is_two_part_tariff
    if body.is_active is not None:
        o.is_active = body.is_active
    try:
        db.commit()
        db.refresh(o)
    except Exception:
        db.rollback()
        logger.exception("更新购电价模板失败 template_id=%s", template_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return success_response(_template_to_dict(o), "模板更新成功")


# ═══════════════════════════════════════════════════════════════
# C. 调度计划
# ═══════════════════════════════════════════════════════════════
# 注意: /plans/current 必须在 /plans/{station_id} 之前注册,
# 否则 "current" 会被 int path 参数匹配并 422。

@router.get("/plans/current")
def current_plan(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前用户团队最新窗口计划 (无计划 → 404)。"""
    q = db.query(EnergyDispatchPlan)
    tid = _team_filter(user)
    if tid is not None:
        q = q.filter(EnergyDispatchPlan.team_id == tid)
    plan = q.order_by(EnergyDispatchPlan.window_start.desc(),
                      EnergyDispatchPlan.id.desc()).first()
    if not plan:
        raise HTTPException(404, "当前无调度计划")
    return success_response(_plan_to_dict(plan))


@router.get("/plans/{station_id}")
def plans_by_station(
    station_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """指定场站的调度计划列表 (跨团队 404)。"""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(404, "场站不存在")
    _assert_team(station.team_id, user)

    q = db.query(EnergyDispatchPlan) \
        .filter(EnergyDispatchPlan.station_id == station_id)
    total = q.count()
    items = q.order_by(EnergyDispatchPlan.window_start.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_plan_to_dict(i) for i in items], total, page, page_size)


# ═══════════════════════════════════════════════════════════════
# D. 能量流水
# ═══════════════════════════════════════════════════════════════

@router.get("/flow")
def list_flow(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    station_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """能量流水时序 (按 user.team_id 隔离)。"""
    q = db.query(EnergyFlowLog)
    tid = _team_filter(user)
    if tid is not None:
        q = q.filter(EnergyFlowLog.team_id == tid)
    if station_id is not None:
        q = q.filter(EnergyFlowLog.station_id == station_id)
    if date_from:
        q = q.filter(EnergyFlowLog.window_start >= _date_bound_or_400(date_from))
    if date_to:
        q = q.filter(EnergyFlowLog.window_start < _date_bound_or_400(date_to, end_of_day=True))
    total = q.count()
    items = q.order_by(EnergyFlowLog.window_start.desc(),
                       EnergyFlowLog.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_flow_to_dict(i) for i in items], total, page, page_size)


@router.get("/savings")
def savings(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """套利/省电费汇总 (按 user.team_id 聚合 cost_saving_yuan)。"""
    q = db.query(EnergyFlowLog)
    tid = _team_filter(user)
    if tid is not None:
        q = q.filter(EnergyFlowLog.team_id == tid)
    if date_from:
        q = q.filter(EnergyFlowLog.window_start >= _date_bound_or_400(date_from))
    if date_to:
        q = q.filter(EnergyFlowLog.window_start < _date_bound_or_400(date_to, end_of_day=True))
    rows = q.all()
    total = sum(float(r.cost_saving_yuan or 0) for r in rows)
    return success_response({
        "total_saving_yuan": round(total, 2),
        "window_count": len(rows),
    })
