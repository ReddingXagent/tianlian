"""
司机考勤/工时管理 API - fleet-platform-spec §4.3 规划表

挂载前缀 /fleet/attendance (见 api/v1/__init__.py), 实际路径:
- POST /api/v1/fleet/attendance/batch        批量录入(按月, upsert)
- GET  /api/v1/fleet/attendance              考勤查询(driver_id + month)
- GET  /api/v1/fleet/attendance/summary      月度汇总(总工时/出勤率)
- PUT  /api/v1/fleet/attendance/{id}         修正单条考勤
"""
from typing import List, Literal, Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import assert_driver_team_access
from app.models.user import User
from app.models.fleet_driver_attendance import FleetDriverAttendance

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_write_permission("fleet:manage"))])

VALID_SHIFT_TYPES = {"day", "night", "rest"}
VALID_STATUSES = {"normal", "late", "absent"}


# ─── Schemas ───

class AttendanceItem(BaseModel):
    date: str = Field(..., description="考勤日期 YYYY-MM-DD")
    shift_type: Literal["day", "night", "rest"] = Field("day", description="班次: day/night/rest")
    hours: float = Field(0.0, ge=0.0, description="工时(小时)")
    status: Literal["normal", "late", "absent"] = Field("normal", description="状态: normal/late/absent")
    remark: Optional[str] = None


class BatchImportRequest(BaseModel):
    driver_id: int
    month: str = Field(..., description="考勤月份 YYYY-MM")
    records: List[AttendanceItem]


class AttendanceUpdateRequest(BaseModel):
    shift_type: Optional[Literal["day", "night", "rest"]] = None
    hours: Optional[float] = Field(None, ge=0.0)
    status: Optional[Literal["normal", "late", "absent"]] = None
    remark: Optional[str] = None


# ─── Helpers ───

def _attendance_to_dict(a: FleetDriverAttendance) -> dict:
    return {
        "id": a.id,
        "driver_id": a.driver_id,
        "date": a.date,
        "shift_type": a.shift_type,
        "hours": a.hours if a.hours is not None else 0.0,
        "status": a.status,
        "remark": a.remark,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _validate_enum(value: str, valid: set, field: str) -> str:
    if value not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"无效的{field}: {value}, 允许 {sorted(valid)}",
        )
    return value


def _validate_month(month: str) -> None:
    """月份格式校验 YYYY-MM。"""
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="month 格式无效, 需 YYYY-MM")


# ─── Endpoints ───
# 注意: /batch 与 /summary 为固定路径, 须在 "" 与 "/{id}" 之前注册, 避免被路径参数吞掉。

@router.post("/batch", summary="批量录入考勤(按月, upsert)")
def batch_import(
    data: BatchImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    按月批量录入司机考勤:
    - 已存在 (driver_id, date) 记录则更新, 否则新建
    - 返回 created/updated 计数
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可录入本 team 司机考勤；越权/不存在 → 404。
    assert_driver_team_access(db, data.driver_id, user)

    # 卡 0e7deb3d 性能优化：原实现逐条查 existing（N 条记录 = N 条 SQL），
    # 改为一次 IN 查询取回本批所有 date 的已有记录建 {date: record}，再分流 update/insert。
    # 循环内同步更新 map 以等价处理"同批重复 date"（原逐条查 + autoflush 的行为）。
    created = 0
    updated = 0
    for item in data.records:
        _validate_enum(item.shift_type, VALID_SHIFT_TYPES, "班次")
        _validate_enum(item.status, VALID_STATUSES, "状态")

    dates = [item.date for item in data.records]
    existing_map: dict = {}
    if dates:
        rows = db.query(FleetDriverAttendance).filter(
            FleetDriverAttendance.driver_id == data.driver_id,
            FleetDriverAttendance.date.in_(dates),
        ).all()
        existing_map = {r.date: r for r in rows}

    for item in data.records:
        existing = existing_map.get(item.date)
        if existing:
            existing.shift_type = item.shift_type
            existing.hours = item.hours
            existing.status = item.status
            existing.remark = item.remark
            updated += 1
        else:
            new_rec = FleetDriverAttendance(
                driver_id=data.driver_id,
                date=item.date,
                shift_type=item.shift_type,
                hours=item.hours,
                status=item.status,
                remark=item.remark,
            )
            db.add(new_rec)
            existing_map[item.date] = new_rec  # 同批重复 date 后续走 update，等价原 autoflush
            created += 1

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("考勤批量录入冲突 driver_id=%s", data.driver_id)
        raise HTTPException(status_code=409, detail="考勤记录写入冲突")
    except Exception:
        db.rollback()
        logger.exception("考勤批量录入失败 driver_id=%s", data.driver_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return success_response({
        "driver_id": data.driver_id,
        "month": data.month,
        "created": created,
        "updated": updated,
        "total": created + updated,
    }, message="考勤批量录入成功")


@router.get("/summary", summary="月度考勤汇总(总工时/出勤率)")
def attendance_summary(
    driver_id: int = Query(..., gt=0, description="司机ID"),
    month: str = Query(..., description="考勤月份 YYYY-MM"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    月度考勤汇总:
    - total_hours 总工时(含休息日工时, 通常为0)
    - 各状态天数: rest 班次单独统计为 rest_days, 其余按 status 计 normal/late/absent
    - attendance_rate 出勤率 = (normal+late) / (normal+late+absent); 无应出勤记录时为 0.0
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可汇总本 team 司机考勤；越权/不存在 → 404。
    assert_driver_team_access(db, driver_id, user)
    _validate_month(month)

    rows = db.query(FleetDriverAttendance).filter(
        FleetDriverAttendance.driver_id == driver_id,
        FleetDriverAttendance.date.like(f"{month}-%"),
    ).all()

    total_hours = sum((r.hours or 0.0) for r in rows)
    counts = {"normal": 0, "late": 0, "absent": 0}
    rest_days = 0
    for r in rows:
        if r.shift_type == "rest":
            rest_days += 1
        elif r.status in counts:
            counts[r.status] += 1

    present = counts["normal"] + counts["late"]
    should_attend = present + counts["absent"]
    attendance_rate = round(present / should_attend, 4) if should_attend > 0 else 0.0

    return success_response({
        "driver_id": driver_id,
        "month": month,
        "total_days": len(rows),
        "total_hours": round(total_hours, 2),
        "normal_days": counts["normal"],
        "late_days": counts["late"],
        "absent_days": counts["absent"],
        "rest_days": rest_days,
        "attendance_rate": attendance_rate,
    })


@router.get("", summary="查询司机考勤(按司机+月份)")
def list_attendance(
    driver_id: int = Query(..., gt=0, description="司机ID"),
    month: str = Query(..., description="考勤月份 YYYY-MM"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询指定司机某月考勤记录列表, 按日期升序。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 司机考勤；越权/不存在 → 404。
    assert_driver_team_access(db, driver_id, user)
    _validate_month(month)

    query = db.query(FleetDriverAttendance).filter(
        FleetDriverAttendance.driver_id == driver_id,
        FleetDriverAttendance.date.like(f"{month}-%"),
    ).order_by(FleetDriverAttendance.date.asc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response(
        [_attendance_to_dict(a) for a in items],
        total,
        page,
        page_size,
        message=f"共 {total} 条考勤记录",
    )


@router.put("/{attendance_id}", summary="修正单条考勤")
def update_attendance(
    attendance_id: int,
    data: AttendanceUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """修正单条考勤记录, 仅覆盖传入字段。"""
    record = db.query(FleetDriverAttendance).filter(
        FleetDriverAttendance.id == attendance_id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="考勤记录不存在")
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可修正本 team 司机考勤；越权 → 404。
    assert_driver_team_access(db, record.driver_id, user)

    if data.shift_type is not None:
        _validate_enum(data.shift_type, VALID_SHIFT_TYPES, "班次")
        record.shift_type = data.shift_type
    if data.hours is not None:
        record.hours = data.hours
    if data.status is not None:
        _validate_enum(data.status, VALID_STATUSES, "状态")
        record.status = data.status
    if data.remark is not None:
        record.remark = data.remark

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("考勤修正冲突 attendance_id=%s", attendance_id)
        raise HTTPException(status_code=409, detail="考勤记录写入冲突")
    except Exception:
        db.rollback()
        logger.exception("考勤修正失败 attendance_id=%s", attendance_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(record)
    return success_response(_attendance_to_dict(record), message="考勤修正成功")
