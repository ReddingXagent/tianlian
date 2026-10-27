"""
碳减排自动聚合定时任务

- carbon_daily_aggregate: 每日凌晨2点，聚合昨日已完成充电订单 → carbon_reduction_records
- carbon_monthly_summary: 每月1日凌晨3点，聚合上月明细 → carbon_reduction_summary + IM推送

公式: 减排量 = (燃油基准 - 电网因子) × 充电量
"""
import asyncio
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from celery import shared_task
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.carbon_emission import (
    CarbonReductionRecord,
    CarbonReductionSummary,
)
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.enterprise import Enterprise
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.api.v1.carbon_emission import (
    calculate_reduction,
    _get_grid_factor,
    _get_fuel_factor,
)
from app.services.im_notify import im_notify_service
from app.tasks._soft_timeout import SoftTimeLimitExceeded  # 卡 411936df
from app.tasks.tz_utils import biz_day_bounds_utc_naive, today_in_biz_tz, yesterday_in_biz_tz

logger = logging.getLogger(__name__)


def aggregate_carbon_for_date(db: Session, target_date: str) -> Dict[str, Any]:
    """
    聚合指定日期的已完成充电订单 → carbon_reduction_records
    幂等键: vehicle_id + record_date
    """
    try:
        target = date.fromisoformat(target_date)
    except (ValueError, TypeError):
        return {"status": "error", "error": f"日期格式错误: {target_date}"}

    # 1. vehicle_id → enterprise_id 映射
    vehicle_map = dict(
        db.query(EnterpriseVehicle.id, EnterpriseVehicle.enterprise_id)
        .filter(EnterpriseVehicle.enterprise_id.isnot(None))
        .all()
    )
    if not vehicle_map:
        return {"status": "completed", "records_written": 0, "message": "无企业车辆"}

    vehicle_ids = list(vehicle_map.keys())

    # 2. 当日已完成订单 (业务日边界换算 UTC-naive, 与 end_time 落库口径对齐, 卡 f7422bbc)
    day_start, day_end = biz_day_bounds_utc_naive(target)

    orders = (
        db.query(ChargingOrder)
        .filter(
            ChargingOrder.vehicle_id.in_(vehicle_ids),
            ChargingOrder.order_status == OrderStatus.COMPLETED,
            ChargingOrder.charged_kwh > 0,
            ChargingOrder.end_time >= day_start,
            ChargingOrder.end_time < day_end,
        )
        .all()
    )

    if not orders:
        return {"status": "completed", "records_written": 0, "message": "当日无已完成订单"}

    # 3. 按车辆聚合
    vehicle_kwh: Dict[int, Decimal] = {}
    for o in orders:
        vid = o.vehicle_id
        kwh = Decimal(str(o.charged_kwh or 0))
        vehicle_kwh[vid] = vehicle_kwh.get(vid, Decimal("0")) + kwh

    # 4. 写入/更新 records
    year = target.year
    grid_factor = _get_grid_factor(db, year)
    fuel_factor = _get_fuel_factor(db, year)

    written = 0

    def _upsert_rows() -> None:
        """单轮 upsert (check-then-act), 卡 7ea84b57: 由唯一约束
        uq_crr_vehicle_date 支撑原子性 — 竞态撞约束 → rollback 重跑转纯覆盖。"""
        nonlocal written
        written = 0
        for vid, total_kwh in vehicle_kwh.items():
            ent_id = vehicle_map[vid]
            reduction_kg, fuel_saved = calculate_reduction(total_kwh, grid_factor, fuel_factor)

            existing = (
                db.query(CarbonReductionRecord)
                .filter(
                    CarbonReductionRecord.vehicle_id == vid,
                    CarbonReductionRecord.record_date == target,
                )
                .first()
            )

            if existing:
                existing.charge_energy_kwh = total_kwh
                existing.grid_factor = grid_factor
                existing.fuel_factor = fuel_factor
                existing.carbon_reduction_kg = reduction_kg
                existing.equivalent_fuel_saved_liters = fuel_saved
            else:
                db.add(CarbonReductionRecord(
                    vehicle_id=vid,
                    enterprise_id=ent_id,
                    record_date=target,
                    charge_energy_kwh=total_kwh,
                    grid_factor=grid_factor,
                    fuel_factor=fuel_factor,
                    carbon_reduction_kg=reduction_kg,
                    equivalent_fuel_saved_liters=fuel_saved,
                ))
            written += 1

    # 卡 7ea84b57: 并发 worker / acks_late 重投递 / 手动补算重跑时,
    # check-then-act 窗口内对手已落库同键行 → add 撞唯一约束,
    # rollback 后重跑一轮全命中覆盖分支 (范式同卡 9863018d)
    try:
        _upsert_rows()
        db.flush()
    except IntegrityError:
        db.rollback()
        _upsert_rows()
        db.flush()
    logger.info("[carbon] 日聚合: date=%s vehicles=%d orders=%d records=%d",
                target_date, len(vehicle_kwh), len(orders), written)
    return {"status": "completed", "records_written": written, "total_orders": len(orders), "date": target_date}


def build_carbon_monthly_summary(db: Session, year: int, month: int) -> Dict[str, Any]:
    """月度汇总，幂等键: enterprise_id + year + month"""
    rows = (
        db.query(
            CarbonReductionRecord.enterprise_id,
            func.sum(CarbonReductionRecord.charge_energy_kwh).label("total_kwh"),
            func.sum(CarbonReductionRecord.carbon_reduction_kg).label("total_reduction"),
            func.sum(CarbonReductionRecord.equivalent_fuel_saved_liters).label("total_fuel"),
            func.count(func.distinct(CarbonReductionRecord.vehicle_id)).label("vehicle_count"),
        )
        .filter(
            func.extract("year", CarbonReductionRecord.record_date) == year,
            func.extract("month", CarbonReductionRecord.record_date) == month,
        )
        .group_by(CarbonReductionRecord.enterprise_id)
        .all()
    )

    built = 0
    summaries = []

    def _upsert_rows() -> None:
        """单轮 upsert, 卡 7ea84b57: 撞 uq_crs_enterprise_year_month →
        rollback 重跑转纯覆盖, 防并发重投递致任务失败重试。"""
        nonlocal built
        built = 0
        for row in rows:
            ent_id = row.enterprise_id
            total_kwh = Decimal(str(row.total_kwh or 0))
            total_reduction = Decimal(str(row.total_reduction or 0))
            total_fuel = Decimal(str(row.total_fuel or 0))
            v_count = row.vehicle_count or 0

            existing = (
                db.query(CarbonReductionSummary)
                .filter(
                    CarbonReductionSummary.enterprise_id == ent_id,
                    CarbonReductionSummary.report_year == year,
                    CarbonReductionSummary.report_month == month,
                )
                .first()
            )

            if existing:
                existing.total_charge_kwh = total_kwh
                existing.total_reduction_kg = total_reduction
                existing.total_fuel_saved_liters = total_fuel
                existing.vehicle_count = v_count
            else:
                db.add(CarbonReductionSummary(
                    enterprise_id=ent_id, report_year=year, report_month=month,
                    total_charge_kwh=total_kwh, total_reduction_kg=total_reduction,
                    total_fuel_saved_liters=total_fuel, vehicle_count=v_count, verified=False,
                ))

            ent = db.query(Enterprise).filter(Enterprise.id == ent_id).first()
            summaries.append({
                "enterprise_id": ent_id, "enterprise_name": ent.name if ent else f"企业#{ent_id}",
                "report_year": year, "report_month": month,
                "total_charge_kwh": float(total_kwh), "total_reduction_kg": float(total_reduction),
                "total_fuel_saved_liters": float(total_fuel), "vehicle_count": v_count,
            })
            built += 1

    # 卡 7ea84b57: 同 aggregate_carbon_for_date 的 IntegrityError 兜底
    try:
        _upsert_rows()
        db.flush()
    except IntegrityError:
        db.rollback()
        _upsert_rows()
        db.flush()
    logger.info("[carbon] 月度汇总: %d-%02d enterprises=%d", year, month, built)
    return {"status": "completed", "summaries_built": built, "summaries": summaries}


def notify_carbon_monthly_report(summaries: List[Dict[str, Any]]) -> bool:
    """月度报告推送IM"""
    if not summaries:
        return False
    if not im_notify_service.webhook_url:
        logger.info("[carbon] IM webhook 未配置，跳过推送")
        return False

    lines = []
    for s in summaries:
        lines.append(
            f"**{s['enterprise_name']}** {s['report_year']}年{s['report_month']}月: "
            f"充电 {s['total_charge_kwh']:.1f} kWh, 减排 {s['total_reduction_kg']:.1f} kg CO₂, "
            f"节油 {s['total_fuel_saved_liters']:.1f} L, 车辆 {s['vehicle_count']} 辆"
        )

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "🌱 碳减排月度报告"}, "template": "green"},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}],
        },
    }

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(im_notify_service.send_webhook_message(card))
        loop.close()
        return result
    except SoftTimeLimitExceeded:
        raise
    except Exception as e:
        logger.warning("[carbon] IM推送失败: %s", e)
        return False


@shared_task(name="carbon.daily_aggregate", bind=True, max_retries=2, default_retry_delay=60)
def carbon_daily_aggregate(self, target_date: Optional[str] = None) -> Dict[str, Any]:
    """每日碳减排聚合"""
    if target_date is None:
        # 卡 c42ac99a: beat 按上海 02:00 触发 (= UTC 前日 18:00), date.today() 在 UTC
        # 容器取到前日 → 错算"上海前天"。改用业务时区昨日。
        target_date = yesterday_in_biz_tz().isoformat()
    logger.info("[carbon] 开始日聚合: %s", target_date)
    db = SessionLocal()
    try:
        result = aggregate_carbon_for_date(db, target_date)
        db.commit()
        return result
    except SoftTimeLimitExceeded:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error("[carbon] 日聚合失败: %s", e, exc_info=True)
        raise self.retry(exc=e)
    finally:
        db.close()


@shared_task(name="carbon.monthly_summary", bind=True, max_retries=2, default_retry_delay=60)
def carbon_monthly_summary(self, year: Optional[int] = None, month: Optional[int] = None) -> Dict[str, Any]:
    """每月碳减排汇总"""
    if year is None or month is None:
        # 卡 c42ac99a: beat 按上海每月1号 03:00 触发 (= UTC 上月末 19:00), date.today()
        # 在 UTC 容器取到上月末 → replace(day=1)-1d = 上上月 → 汇总上上月而非上月,
        # 每月固定错。改用业务时区 now 算上月: 月初任何时刻(含 UTC 上月末)都正确指向上月。
        today = today_in_biz_tz()
        last_month = today.replace(day=1) - timedelta(days=1)
        year, month = last_month.year, last_month.month
    logger.info("[carbon] 开始月度汇总: %d-%02d", year, month)
    db = SessionLocal()
    try:
        result = build_carbon_monthly_summary(db, year, month)
        db.commit()
        if result.get("summaries"):
            notify_carbon_monthly_report(result["summaries"])
        return result
    except SoftTimeLimitExceeded:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error("[carbon] 月度汇总失败: %s", e, exc_info=True)
        raise self.retry(exc=e)
    finally:
        db.close()
