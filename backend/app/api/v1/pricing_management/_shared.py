"""定价管理 V2 API 共享定义（拆分自原 pricing_management.py）。

存放跨子模块复用的模块级对象：logger、router 级鉴权依赖、日期/时间解析与格式化
helper、以及 6 类定价 CRUD 与订单估算的 Pydantic schema。各定价资源端点拆分到
同包各子模块，均从本模块导入所需 schema 与 helper。
"""
import logging
from datetime import date, datetime, time as dt_time
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.v1.auth import require_role


logger = logging.getLogger("app.api.v1.pricing_management")


# 定价管理 router 级鉴权依赖（原 pricing_management.py 顶层 router 的 dependencies）
_ROUTER_DEPENDENCIES = [Depends(require_role("admin"))]


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _parse_time(s: Optional[str]) -> Optional[dt_time]:
    if not s:
        return None
    try:
        h, m = s.split(":")
        return dt_time(int(h), int(m))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400, detail=f"时间格式非法, 需 HH:MM: {s!r}"
        )


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400, detail=f"日期格式非法, 需 YYYY-MM-DD: {s!r}"
        )


def _fmt_time(t: Optional[dt_time]) -> Optional[str]:
    return t.strftime("%H:%M") if t else None


def _fmt_date(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# ═══════════════════════════════════════════════════════════════
# 生效期重叠校验 (卡 a311a5b0, 缺陷1 上游预防)
# ═══════════════════════════════════════════════════════════════

def assert_no_effective_overlap(
    db: Session,
    model,
    dims: dict,
    effective: date,
    expire: Optional[date],
    *,
    item_id: Optional[int] = None,
    label: str,
) -> None:
    """同维度生效期重叠校验: 同业务维度键下, 新/改行的 ``[effective, expire]`` 区间
    不得与既有 ``is_active`` 行相交 —— 否则下游 ``.first()`` 选取不确定(财务 P2) → 409。

    Args:
        dims: 维度键 ``{列对象: 值}`` (同维度才比较, 如 station_id(+slot_id/user_type))。
        effective / expire: 新/改行生效期; ``expire=None`` 视为开放区间(到 +∞)。
        item_id: 更新场景排除自身(避免自身行误判为冲突)。
        label: 资源中文名, 用于 409 message。

    仅与 ``is_active`` 行比较: 失效行不参与定价 ``.first()`` 选取, 不算冲突。
    """
    q = db.query(model).filter(model.is_active.is_(True))
    for col, val in dims.items():
        q = q.filter(col == val)
    if item_id is not None:
        q = q.filter(model.id != item_id)
    # 区间相交充要条件: existing.effective <= new.expire(新区间有上界时)
    #                AND new.effective <= existing.expire(existing 开放区间视为 +∞)
    if expire is not None:
        q = q.filter(model.effective_date <= expire)
    q = q.filter(or_(model.expire_date.is_(None), effective <= model.expire_date))
    conflict = q.first()
    if conflict:
        raise HTTPException(
            409, f"{label}生效期与既有定价(id={conflict.id})重叠, 请先失效旧定价"
        )


# ═══════════════════════════════════════════════════════════════
# Pydantic Schemas
# ═══════════════════════════════════════════════════════════════

# ─── Time Slot Definitions ───

class TimeSlotCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    period_type: str = Field(..., description="peak/shoulder/flat/valley")
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class TimeSlotUpdate(BaseModel):
    name: Optional[str] = None
    period_type: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


# ─── Energy Prices ───

class EnergyPriceCreate(BaseModel):
    station_id: int
    slot_id: int
    price_per_kwh: float = Field(..., ge=0)
    effective_date: str = Field(..., description="YYYY-MM-DD")
    expire_date: Optional[str] = None
    is_active: bool = True


class EnergyPriceUpdate(BaseModel):
    station_id: Optional[int] = None
    slot_id: Optional[int] = None
    price_per_kwh: Optional[float] = Field(None, ge=0)
    effective_date: Optional[str] = None
    expire_date: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Service Fee Prices ───

class ServiceFeeCreate(BaseModel):
    station_id: int
    user_type: str = Field(..., description="app/card/vin/interconnect/enterprise")
    fee_type: str = Field(..., description="fixed/percent")
    fee_value: float = Field(..., ge=0)
    effective_date: str
    expire_date: Optional[str] = None
    is_active: bool = True


class ServiceFeeUpdate(BaseModel):
    station_id: Optional[int] = None
    user_type: Optional[str] = None
    fee_type: Optional[str] = None
    fee_value: Optional[float] = Field(None, ge=0)
    effective_date: Optional[str] = None
    expire_date: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Parking Prices ───

class ParkingPriceCreate(BaseModel):
    station_id: int
    free_minutes: int = Field(0, ge=0)
    hourly_rate: float = Field(..., ge=0)
    daily_cap: Optional[float] = None
    enable_night_rate: bool = False
    night_rate: Optional[float] = Field(None, ge=0)
    night_start: Optional[str] = None
    night_end: Optional[str] = None
    effective_date: str
    expire_date: Optional[str] = None
    is_active: bool = True


class ParkingPriceUpdate(BaseModel):
    station_id: Optional[int] = None
    free_minutes: Optional[int] = None
    hourly_rate: Optional[float] = Field(None, ge=0)
    daily_cap: Optional[float] = None
    enable_night_rate: Optional[bool] = None
    night_rate: Optional[float] = Field(None, ge=0)
    night_start: Optional[str] = None
    night_end: Optional[str] = None
    effective_date: Optional[str] = None
    expire_date: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Occupancy Fee Prices ───

class OccupancyFeeCreate(BaseModel):
    station_id: int
    grace_minutes: int = Field(15, ge=0)
    rate_per_minute: float = Field(..., ge=0)
    max_fee: Optional[float] = Field(None, ge=0)
    effective_date: str
    expire_date: Optional[str] = None
    is_active: bool = True


class OccupancyFeeUpdate(BaseModel):
    station_id: Optional[int] = None
    grace_minutes: Optional[int] = None
    rate_per_minute: Optional[float] = Field(None, ge=0)
    max_fee: Optional[float] = Field(None, ge=0)
    effective_date: Optional[str] = None
    expire_date: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Reservation Fee Prices ───

class ReservationFeeCreate(BaseModel):
    station_id: int
    deposit_amount: float = Field(0, ge=0)
    reservation_policy: str = Field(..., description="slot_based/flat")
    fee_amount: float = Field(0, ge=0)
    no_show_penalty: float = Field(0, ge=0)
    effective_date: str
    expire_date: Optional[str] = None
    is_active: bool = True


class ReservationFeeUpdate(BaseModel):
    station_id: Optional[int] = None
    deposit_amount: Optional[float] = Field(None, ge=0)
    reservation_policy: Optional[str] = None
    fee_amount: Optional[float] = Field(None, ge=0)
    no_show_penalty: Optional[float] = Field(None, ge=0)
    effective_date: Optional[str] = None
    expire_date: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Order Estimate ───

class OrderEstimateRequest(BaseModel):
    station_id: int
    user_type: str = "app"
    energy_kwh: float = Field(..., ge=0)
    charging_minutes: int = Field(0, ge=0)
    parking_minutes: int = Field(0, ge=0)
    occupancy_minutes: int = Field(0, ge=0)
    # 停车开始时刻(卡 c13ac16b): aware/naive-UTC 均接受; 缺省取当前时刻。
    # 夜间费率分摊需要, 与实收路径 occupancy_fee_service 同口径。
    parking_start: Optional[datetime] = None
