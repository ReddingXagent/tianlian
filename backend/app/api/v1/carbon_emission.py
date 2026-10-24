"""
碳排放管理 API - 车队碳减排追踪与核算

端点:
- GET  /api/v1/fleet/carbon/overview          碳减排概览(企业级)
- GET  /api/v1/fleet/carbon/details            碳减排明细(按时间/车辆)
- GET  /api/v1/fleet/carbon/reports            月度汇总报告
- POST /api/v1/fleet/carbon/reports/{id}/verify 审核月度报告
- GET  /api/v1/fleet/carbon/factors             排放因子列表
- POST /api/v1/fleet/carbon/factors             创建排放因子
- PUT  /api/v1/fleet/carbon/factors/{id}        更新排放因子
- DELETE /api/v1/fleet/carbon/factors/{id}      删除排放因子
- POST /api/v1/fleet/carbon/calculate            手动计算减排量
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import extract
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import (
    assert_enterprise_team_access,
    assert_vehicle_team_access,
    require_platform_admin,
)
from app.models.user import User
from app.models.carbon_emission import (
    CarbonEmissionFactor,
    CarbonReductionRecord,
    CarbonReductionSummary,
)
from app.models.enterprise_vehicle import EnterpriseVehicle

router = APIRouter(dependencies=[Depends(require_write_permission("report:manage"))])

# ─── 常量 ───
# 默认燃油车百公里油耗(L) -> 每kWh等效油耗
# 纯电每kWh约行驶7km, 燃油车百公里8L => 每kWh等效: 8/100*7 = 0.56 L/kWh
DEFAULT_FUEL_LITERS_PER_KWH = Decimal("0.56")
# 汽油碳排放系数: 2.1625 kgCO2/L (国标GB/T 32150)
GASOLINE_CO2_PER_LITER = Decimal("2.1625")
# 默认电网排放因子 (2022年全国平均值 kgCO2/kWh)
DEFAULT_GRID_FACTOR = Decimal("0.5703")


# ─── Pydantic 模型 ───

class FactorCreate(BaseModel):
    year: int = Field(..., ge=2000, le=2100, description="年份")
    region: str = Field("全国", max_length=50, description="区域")
    factor_type: str = Field(..., description="因子类型: grid-电网排放因子 / fuel-燃油基准")
    emission_factor: float = Field(..., gt=0, description="排放因子值")
    source: Optional[str] = Field(None, max_length=200, description="数据来源")


class FactorUpdate(BaseModel):
    year: Optional[int] = Field(None, ge=2000, le=2100)
    region: Optional[str] = Field(None, max_length=50)
    factor_type: Optional[str] = None
    emission_factor: Optional[float] = Field(None, gt=0)
    source: Optional[str] = None


class ReductionCalculate(BaseModel):
    """手动计算减排量请求"""
    vehicle_id: int = Field(..., description="车辆ID")
    record_date: str = Field(..., description="日期 YYYY-MM-DD")
    charge_energy_kwh: float = Field(..., gt=0, description="充电量(kWh)")


# ─── 减排计算核心 ───

def _get_grid_factor(db: Session, year: int, region: str = "全国") -> Decimal:
    """获取指定年份和区域的电网排放因子"""
    factor = db.query(CarbonEmissionFactor).filter(
        CarbonEmissionFactor.year == year,
        CarbonEmissionFactor.region == region,
        CarbonEmissionFactor.factor_type == "grid",
    ).first()
    if factor:
        return factor.emission_factor
    # fallback 到默认值
    return DEFAULT_GRID_FACTOR


def _get_fuel_factor(db: Session, year: int) -> Decimal:
    """获取燃油排放基准 (已转换为 kgCO2/kWh)"""
    factor = db.query(CarbonEmissionFactor).filter(
        CarbonEmissionFactor.year == year,
        CarbonEmissionFactor.factor_type == "fuel",
    ).first()
    if factor:
        return factor.emission_factor
    # 默认: 0.56 L/kWh * 2.1625 kgCO2/L = 1.211 kgCO2/kWh
    return DEFAULT_FUEL_LITERS_PER_KWH * GASOLINE_CO2_PER_LITER


def calculate_reduction(
    charge_kwh: Decimal,
    grid_factor: Decimal,
    fuel_factor: Decimal,
) -> tuple:
    """
    计算碳减排量和等效节油量

    减排 = (燃油基准排放 - 电网排放) × 充电量
    节油 = 充电量 × 默认等效油耗系数

    Returns: (carbon_reduction_kg, equivalent_fuel_saved_liters)
    """
    # 燃油车等效碳排放
    fuel_emission = fuel_factor * charge_kwh
    # 电力碳排放
    grid_emission = grid_factor * charge_kwh
    # 减排量
    reduction = fuel_emission - grid_emission
    if reduction < 0:
        reduction = Decimal("0")
    # 等效节油量
    fuel_saved = charge_kwh * DEFAULT_FUEL_LITERS_PER_KWH
    return reduction, fuel_saved


# ─── Helper ───

def _factor_to_dict(f: CarbonEmissionFactor) -> dict:
    return {
        "id": f.id,
        "year": f.year,
        "region": f.region,
        "factor_type": f.factor_type,
        "emission_factor": float(f.emission_factor) if f.emission_factor else 0.0,
        "source": f.source,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _record_to_dict(r: CarbonReductionRecord) -> dict:
    return {
        "id": r.id,
        "vehicle_id": r.vehicle_id,
        "enterprise_id": r.enterprise_id,
        "record_date": r.record_date.isoformat() if r.record_date else None,
        "charge_energy_kwh": float(r.charge_energy_kwh) if r.charge_energy_kwh else 0.0,
        "grid_factor": float(r.grid_factor) if r.grid_factor else 0.0,
        "fuel_factor": float(r.fuel_factor) if r.fuel_factor else 0.0,
        "carbon_reduction_kg": float(r.carbon_reduction_kg) if r.carbon_reduction_kg else 0.0,
        "equivalent_fuel_saved_liters": float(r.equivalent_fuel_saved_liters) if r.equivalent_fuel_saved_liters else 0.0,
    }


def _summary_to_dict(s: CarbonReductionSummary) -> dict:
    return {
        "id": s.id,
        "enterprise_id": s.enterprise_id,
        "report_year": s.report_year,
        "report_month": s.report_month,
        "total_charge_kwh": float(s.total_charge_kwh) if s.total_charge_kwh else 0.0,
        "total_reduction_kg": float(s.total_reduction_kg) if s.total_reduction_kg else 0.0,
        "total_fuel_saved_liters": float(s.total_fuel_saved_liters) if s.total_fuel_saved_liters else 0.0,
        "vehicle_count": s.vehicle_count,
        "verified": s.verified,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


# ─── API 端点 ───

@router.get("/carbon/overview", summary="碳减排概览")
def carbon_overview(
    enterprise_id: int = Query(..., description="企业ID"),
    year: Optional[int] = Query(None, description="年份(默认当前年)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取企业碳减排概览数据"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 企业碳概览；越权/不存在 → 404。
    # assert 返回 Enterprise ORM，复用替代手动查询+404。
    enterprise = assert_enterprise_team_access(db, enterprise_id, user)

    target_year = year or datetime.now(timezone.utc).year

    # 年度汇总
    records = db.query(CarbonReductionRecord).filter(
        CarbonReductionRecord.enterprise_id == enterprise_id,
        extract("year", CarbonReductionRecord.record_date) == target_year,
    ).all()

    total_charge = sum((r.charge_energy_kwh or Decimal("0")) for r in records)
    total_reduction = sum((r.carbon_reduction_kg or Decimal("0")) for r in records)
    total_fuel_saved = sum((r.equivalent_fuel_saved_liters or Decimal("0")) for r in records)
    vehicle_count = len(set(r.vehicle_id for r in records))

    # 月度趋势
    monthly = []
    for m in range(1, 13):
        month_records = [r for r in records if r.record_date and r.record_date.month == m]
        monthly.append({
            "month": m,
            "charge_kwh": float(sum((r.charge_energy_kwh or Decimal("0")) for r in month_records)),
            "reduction_kg": float(sum((r.carbon_reduction_kg or Decimal("0")) for r in month_records)),
        })

    return success_response({
        "enterprise": {
            "id": enterprise.id,
            "name": enterprise.name,
        },
        "year": target_year,
        "total_charge_kwh": float(total_charge),
        "total_reduction_kg": float(total_reduction),
        "total_fuel_saved_liters": float(total_fuel_saved),
        "vehicle_count": vehicle_count,
        "monthly_trend": monthly,
    })


@router.get("/carbon/details", summary="碳减排明细")
def carbon_details(
    enterprise_id: int = Query(..., description="企业ID"),
    vehicle_id: Optional[int] = Query(None, description="车辆ID筛选"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询碳减排明细记录"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 企业碳明细；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)

    q = db.query(CarbonReductionRecord).filter(
        CarbonReductionRecord.enterprise_id == enterprise_id
    )

    if vehicle_id:
        q = q.filter(CarbonReductionRecord.vehicle_id == vehicle_id)

    if start_date:
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d").date()
            q = q.filter(CarbonReductionRecord.record_date >= sd)
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date 格式错误, 需要 YYYY-MM-DD")

    if end_date:
        try:
            ed = datetime.strptime(end_date, "%Y-%m-%d").date()
            q = q.filter(CarbonReductionRecord.record_date <= ed)
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date 格式错误, 需要 YYYY-MM-DD")

    total = q.count()
    items = q.order_by(CarbonReductionRecord.record_date.desc()) \
        .offset((page - 1) * page_size) \
        .limit(page_size) \
        .all()

    return paginated_response(
        items=[_record_to_dict(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/carbon/reports", summary="月度碳减排报告")
def carbon_reports(
    enterprise_id: int = Query(..., description="企业ID"),
    year: Optional[int] = Query(None, description="年份"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取月度碳减排汇总报告"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 企业碳报告；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)

    target_year = year or datetime.now(timezone.utc).year

    q = db.query(CarbonReductionSummary).filter(
        CarbonReductionSummary.enterprise_id == enterprise_id,
        CarbonReductionSummary.report_year == target_year,
    ).order_by(CarbonReductionSummary.report_month)

    summaries = q.all()

    # 如果没有汇总数据, 自动从明细聚合
    if not summaries:
        summaries = _build_summary_from_records(db, enterprise_id, target_year)

    return success_response([_summary_to_dict(s) for s in summaries])


@router.post("/carbon/reports/{summary_id}/verify", summary="审核月度报告")
def verify_report(
    summary_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """审核(确认)月度碳减排报告"""
    summary = db.query(CarbonReductionSummary).filter(
        CarbonReductionSummary.id == summary_id
    ).first()
    if not summary:
        raise HTTPException(status_code=404, detail="报告不存在")
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可审核本 team 企业碳报告；越权 → 404。
    assert_enterprise_team_access(db, summary.enterprise_id, user)

    summary.verified = True
    db.commit()
    db.refresh(summary)
    return success_response(_summary_to_dict(summary), "报告已审核")


# ─── 排放因子 CRUD ───

@router.get("/carbon/factors", summary="排放因子列表")
def list_factors(
    year: Optional[int] = Query(None, description="年份筛选"),
    region: Optional[str] = Query(None, description="区域筛选"),
    factor_type: Optional[str] = Query(None, description="类型筛选: grid/fuel"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询碳排放因子列表"""
    # team scoping（任务卡 ab5c5f17）：排放因子为平台级知识库，无 team 归属；仅需登录。
    q = db.query(CarbonEmissionFactor)
    if year:
        q = q.filter(CarbonEmissionFactor.year == year)
    if region:
        q = q.filter(CarbonEmissionFactor.region == region)
    if factor_type:
        q = q.filter(CarbonEmissionFactor.factor_type == factor_type)

    total = q.count()
    items = q.order_by(CarbonEmissionFactor.year.desc()) \
        .offset((page - 1) * page_size) \
        .limit(page_size) \
        .all()

    return paginated_response(
        items=[_factor_to_dict(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/carbon/factors", summary="创建排放因子")
def create_factor(body: FactorCreate, user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    """创建碳排放因子（平台级知识库，仅平台 admin 可写）"""
    existing = db.query(CarbonEmissionFactor).filter(
        CarbonEmissionFactor.year == body.year,
        CarbonEmissionFactor.region == body.region,
        CarbonEmissionFactor.factor_type == body.factor_type,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该年份/区域/类型的排放因子已存在")

    factor = CarbonEmissionFactor(
        year=body.year,
        region=body.region,
        factor_type=body.factor_type,
        emission_factor=Decimal(str(body.emission_factor)),
        source=body.source,
    )
    db.add(factor)
    db.commit()
    db.refresh(factor)
    return success_response(_factor_to_dict(factor), "排放因子创建成功")


@router.put("/carbon/factors/{factor_id}", summary="更新排放因子")
def update_factor(factor_id: int, body: FactorUpdate, user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    """更新碳排放因子（平台级知识库，仅平台 admin 可写）"""
    factor = db.query(CarbonEmissionFactor).filter(
        CarbonEmissionFactor.id == factor_id
    ).first()
    if not factor:
        raise HTTPException(status_code=404, detail="排放因子不存在")

    if body.year is not None:
        factor.year = body.year
    if body.region is not None:
        factor.region = body.region
    if body.factor_type is not None:
        factor.factor_type = body.factor_type
    if body.emission_factor is not None:
        factor.emission_factor = Decimal(str(body.emission_factor))
    if body.source is not None:
        factor.source = body.source

    db.commit()
    db.refresh(factor)
    return success_response(_factor_to_dict(factor), "排放因子更新成功")


@router.delete("/carbon/factors/{factor_id}", summary="删除排放因子")
def delete_factor(factor_id: int, user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    """删除碳排放因子（平台级知识库，仅平台 admin 可写）"""
    factor = db.query(CarbonEmissionFactor).filter(
        CarbonEmissionFactor.id == factor_id
    ).first()
    if not factor:
        raise HTTPException(status_code=404, detail="排放因子不存在")

    db.delete(factor)
    db.commit()
    return success_response(None, "排放因子已删除")


# ─── 手动计算减排量 ───

@router.post("/carbon/calculate", summary="计算并记录减排量")
def calculate_and_store(body: ReductionCalculate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    手动计算单次充电的减排量并保存记录。
    公式: 减排量 = (燃油基准 - 电网因子) × 充电量
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可为本 team 车辆计算减排；越权/不存在 → 404。
    assert_vehicle_team_access(db, body.vehicle_id, user)

    vehicle = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.id == body.vehicle_id
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="车辆不存在")

    try:
        record_date_obj = datetime.strptime(body.record_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误, 需要 YYYY-MM-DD")

    year_val = record_date_obj.year
    charge_kwh = Decimal(str(body.charge_energy_kwh))
    grid_factor = _get_grid_factor(db, year_val)
    fuel_factor = _get_fuel_factor(db, year_val)

    reduction_kg, fuel_saved = calculate_reduction(charge_kwh, grid_factor, fuel_factor)

    record = CarbonReductionRecord(
        vehicle_id=body.vehicle_id,
        enterprise_id=vehicle.enterprise_id,
        record_date=record_date_obj,
        charge_energy_kwh=charge_kwh,
        grid_factor=grid_factor,
        fuel_factor=fuel_factor,
        carbon_reduction_kg=reduction_kg,
        equivalent_fuel_saved_liters=fuel_saved,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return success_response(_record_to_dict(record), "减排量计算完成")


# ─── 内部工具 ───

def _build_summary_from_records(
    db: Session,
    enterprise_id: int,
    year: int,
) -> List[CarbonReductionSummary]:
    """从明细记录聚合生成月度汇总 (不持久化, 仅用于查询时补全)"""
    records = db.query(CarbonReductionRecord).filter(
        CarbonReductionRecord.enterprise_id == enterprise_id,
        extract("year", CarbonReductionRecord.record_date) == year,
    ).all()

    monthly_map: dict = {}
    for r in records:
        month = r.record_date.month
        if month not in monthly_map:
            monthly_map[month] = {
                "charge": Decimal("0"),
                "reduction": Decimal("0"),
                "fuel_saved": Decimal("0"),
                "vehicles": set(),
            }
        monthly_map[month]["charge"] += r.charge_energy_kwh or Decimal("0")
        monthly_map[month]["reduction"] += r.carbon_reduction_kg or Decimal("0")
        monthly_map[month]["fuel_saved"] += r.equivalent_fuel_saved_liters or Decimal("0")
        monthly_map[month]["vehicles"].add(r.vehicle_id)

    result = []
    for month in sorted(monthly_map.keys()):
        d = monthly_map[month]
        result.append(CarbonReductionSummary(
            enterprise_id=enterprise_id,
            report_year=year,
            report_month=month,
            total_charge_kwh=d["charge"],
            total_reduction_kg=d["reduction"],
            total_fuel_saved_liters=d["fuel_saved"],
            vehicle_count=len(d["vehicles"]),
            verified=False,
        ))
    return result
