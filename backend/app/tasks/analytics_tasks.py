"""
运维数据分析异步任务
Phase 4 - 耗时的分析操作转为异步执行
"""
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional

from celery import shared_task
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.telemetry import Telemetry
from app.models.alarm import Alarm
from app.models.analytics import AnalyticsResult
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.charging_queue import ChargingQueue
from app.models.order_fee_item import RefundRecord, RefundStatus
from app.models.spec_tables import RevenueDaily, StationDailyMetric
from app.tasks.tz_utils import biz_day_bounds_utc_naive, parse_dt_in_biz_tz, yesterday_in_biz_tz


logger = logging.getLogger(__name__)


def _run_db_task(func):
    """统一的数据库任务包装器"""
    db = SessionLocal()
    try:
        result = func(db)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        logger.error("异步任务执行失败: %s", e, exc_info=True)
        raise
    finally:
        db.close()


def _fetch_existing_analytics(
    db: Session, device_id: int, analysis_type: str
) -> Optional[AnalyticsResult]:
    """按幂等键 (device_id, analysis_type) 查现有分析结果行。"""
    return (
        db.query(AnalyticsResult)
        .filter(
            AnalyticsResult.device_id == device_id,
            AnalyticsResult.analysis_type == analysis_type,
        )
        .first()
    )


def _persist_analytics_results(db: Session, rows: List[Dict[str, Any]]) -> None:
    """(device_id, analysis_type) 单行覆盖 upsert (卡 77184280)。

    唯一约束 uq_ar_device_type 支撑的原子幂等, 对齐 settlement/_fetch_existing
    范式 (卡 97c83af9): 整批 check-then-act, 撞约束 → rollback 后重跑一轮,
    此时竞态对手行已落库, 全部命中覆盖分支。整批而非行级兜底: 行级 rollback
    会丢掉同批先行插入 (efficiency 多设备场景)。
    """
    def _upsert_rows() -> None:
        for r in rows:
            existing = _fetch_existing_analytics(db, r["device_id"], r["analysis_type"])
            if existing:
                existing.result_json = r["result_json"]
                existing.confidence = r["confidence"]
                existing.valid_until = r["valid_until"]
                existing.generated_at = datetime.now(timezone.utc)
            else:
                db.add(AnalyticsResult(**r))
        db.flush()

    try:
        _upsert_rows()
    except IntegrityError:
        db.rollback()
        _upsert_rows()


@shared_task(
    name="analytics.health_score",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def calculate_health_score_task(
    self,
    device_id: int,
    days: int = 7,
) -> Dict[str, Any]:
    """
    异步计算设备健康度评分
    耗时操作，适合异步执行
    """
    logger.info("[Celery] 开始计算设备 %s 健康度评分", device_id)

    def _execute(db: Session):
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            raise ValueError(f"设备 {device_id} 不存在")

        # 获取遥测数据
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        telemetry_data = (
            db.query(Telemetry)
            .filter(Telemetry.device_id == device_id, Telemetry.timestamp >= cutoff)
            .order_by(Telemetry.timestamp.desc())
            .all()
        )

        # 获取告警数据
        alarm_data = (
            db.query(Alarm)
            .filter(Alarm.device_id == device_id, Alarm.created_at >= cutoff)
            .all()
        )

        # 简化评分计算
        scores = {}
        total_score = 0.0

        # 电池健康评分
        if telemetry_data:
            soc_values = [t.battery_soc for t in telemetry_data if t.battery_soc is not None]
            if soc_values:
                avg_soc = sum(soc_values) / len(soc_values)
                scores["battery"] = min(100, avg_soc * 1.2)
            else:
                scores["battery"] = 70.0
        else:
            scores["battery"] = 50.0

        # 温度评分
        if telemetry_data:
            temps = [t.ambient_temperature for t in telemetry_data if t.ambient_temperature is not None]
            if temps:
                avg_temp = sum(temps) / len(temps)
                scores["temperature"] = max(0, 100 - abs(avg_temp - 25) * 3)
            else:
                scores["temperature"] = 70.0
        else:
            scores["temperature"] = 50.0

        # 告警评分
        alarm_count = len(alarm_data)
        critical_count = sum(1 for a in alarm_data if a.level in ["critical", "严重"])
        scores["alarm"] = max(0, 100 - alarm_count * 5 - critical_count * 15)

        total_score = sum(scores.values()) / len(scores) if scores else 0
        risk_level = "low" if total_score >= 80 else "medium" if total_score >= 60 else "high" if total_score >= 40 else "critical"

        # 卡 77184280: 单行覆盖 upsert, 重试/重投递不再插新行致表膨胀
        _persist_analytics_results(db, [dict(
            device_id=device_id,
            analysis_type="health_score",
            result_json={
                "overall_score": round(total_score, 1),
                "score_breakdown": {k: round(v, 1) for k, v in scores.items()},
                "risk_level": risk_level,
                "data_points": len(telemetry_data),
                "alarm_count": alarm_count,
            },
            confidence=0.85 if telemetry_data else 0.3,
            valid_until=datetime.now(timezone.utc) + timedelta(hours=6),
        )])

        return {
            "task_id": self.request.id,
            "device_id": device_id,
            "overall_score": round(total_score, 1),
            "risk_level": risk_level,
            "status": "completed",
        }

    return _run_db_task(_execute)


@shared_task(
    name="analytics.efficiency_analysis",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def analyze_efficiency_task(
    self,
    device_ids: Optional[list] = None,
    station_id: Optional[int] = None,
    start_date: str = None,
    end_date: str = None,
) -> Dict[str, Any]:
    """
    异步能效分析
    """
    logger.info("[Celery] 开始能效分析, device_ids=%s, station_id=%s", device_ids, station_id)

    def _execute(db: Session):
        query = db.query(Device)
        if device_ids:
            query = query.filter(Device.id.in_(device_ids))
        if station_id:
            query = query.filter(Device.station_id == station_id)

        devices = query.all()
        if not devices:
            raise ValueError("未找到匹配的设备")

        # 卡 c42ac99a: naive fromisoformat 产 naive datetime, 与默认分支 datetime.now(timezone.utc)
        # aware 混比 → start<=timestamp<=end 直接 TypeError 崩任务。改用 parse_dt_in_biz_tz
        # 把 naive 串按业务时区解释成 aware (aware 输入原样尊重)。
        start = parse_dt_in_biz_tz(start_date) if start_date else datetime.now(timezone.utc) - timedelta(days=30)
        end = parse_dt_in_biz_tz(end_date) if end_date else datetime.now(timezone.utc)

        total_energy = 0.0
        device_results = []
        # 卡 77184280: 分析行先收集, 循环外整批 upsert (行级 IntegrityError
        # 兜底会 rollback 丢同批先行, 见 _persist_analytics_results)
        pending_results: List[Dict[str, Any]] = []

        for device in devices:
            telemetry = (
                db.query(Telemetry)
                .filter(
                    Telemetry.device_id == device.id,
                    Telemetry.timestamp >= start,
                    Telemetry.timestamp <= end,
                )
                # 卡 010f4894: kwh_values[-1]-[0] 依赖时间序, 无 ORDER BY 时 PG 行序
                # 无保证, 行序错乱会被 max(0.0,...) 静默钳 0。显式按时间升序。
                .order_by(Telemetry.timestamp.asc())
                .all()
            )

            # 卡 36c6b919: 废弃假值算法
            # - 能耗: 优先 Telemetry.charger_kwh 累计列差值 (末-首, kWh 真实口径);
            #   无该列时回退同步端点口径 avg(grid_power_total)×时长, 不再把瞬时
            #   charger_power (kW) 直接累加当 kWh。
            # - 效率: 复用同步端点 _calculate_device_efficiency, 按设备类型
            #   (inverter/charger/battery/general) 分派真实算法。
            kwh_values = [t.charger_kwh for t in telemetry if t.charger_kwh is not None]
            if kwh_values:
                energy = max(0.0, kwh_values[-1] - kwh_values[0])
            else:
                grid_values = [t.grid_power_total for t in telemetry if t.grid_power_total is not None]
                avg_power = sum(grid_values) / len(grid_values) if grid_values else 0.0
                hours = max(0.0, (end - start).total_seconds() / 3600)
                energy = avg_power * hours
            total_energy += energy

            # 函数内延迟导入: efficiency.py 依赖链经 operate 包回引本模块 (revenue_stats
            # 导入 build_revenue_daily), 模块级导入会形成环。
            from app.api.v1.analytics.efficiency import _calculate_device_efficiency

            efficiency = _calculate_device_efficiency(telemetry, device)
            device_results.append({
                "device_id": device.id,
                "device_name": device.name,
                "energy_kwh": round(energy, 2),
                "efficiency": round(efficiency, 1),
            })

            # 保存分析结果 (循环外统一 upsert)
            pending_results.append(dict(
                device_id=device.id,
                analysis_type="efficiency",
                result_json={
                    "energy_kwh": round(energy, 2),
                    "efficiency": round(efficiency, 1),
                    "data_points": len(telemetry),
                },
                confidence=0.8 if telemetry else 0.2,
                valid_until=datetime.now(timezone.utc) + timedelta(hours=12),
            ))

        _persist_analytics_results(db, pending_results)

        avg_eff = sum(d["efficiency"] for d in device_results) / len(device_results) if device_results else 0

        return {
            "task_id": self.request.id,
            "total_devices": len(devices),
            "total_energy_kwh": round(total_energy, 2),
            "avg_efficiency": round(avg_eff, 1),
            "breakdown": device_results,
            "status": "completed",
        }

    return _run_db_task(_execute)


@shared_task(
    name="analytics.batch_health_report",
    bind=True,
    max_retries=1,
)
def batch_health_report_task(self, station_id: Optional[int] = None) -> Dict[str, Any]:
    """
    批量生成设备健康报告
    通常在定时任务中调用
    """
    logger.info("[Celery] 批量生成健康报告, station_id=%s", station_id)

    def _execute(db: Session):
        query = db.query(Device)
        if station_id:
            query = query.filter(Device.station_id == station_id)

        devices = query.all()
        results = []

        for device in devices:
            # 复用健康度计算逻辑
            # __wrapped__ 是已绑定 self 的 bound method(签名 device_id, days=7),
            # 不可再传 task proxy 作首参, 否则 days 重复赋值 → TypeError
            task_result = calculate_health_score_task.__wrapped__(
                device.id,
                days=7,
            )
            results.append(task_result)

        return {
            "task_id": self.request.id,
            "total_devices": len(devices),
            "results": results,
            "status": "completed",
        }

    return _run_db_task(_execute)


# ═══════════════════════════════════════════════════════════════════
# 运营日报聚合 (revenue_daily + station_daily_metrics)
# ═══════════════════════════════════════════════════════════════════
# 与 settlement_tasks 同口径: order_status=COMPLETED 且 end_time 落在当日 [day_start, day_end)。
# 退款取自 refund_records(REFUNDED, refunded_at 当日), 经订单回溯 station/user_type 归属。

# 充电桩设备类型(枪数/在线统计仅计入充电桩, 排除逆变器/储能等)
_CHARGER_TYPES = (DeviceType.CHARGER_DC, DeviceType.CHARGER_AC, DeviceType.V2G_CHARGER)
# 在线可用状态
_ONLINE_STATUSES = (DeviceStatus.ONLINE, DeviceStatus.CHARGING)
_MINUTES_PER_DAY = 1440


def _user_type_value(ut) -> Optional[str]:
    """ChargingOrder.user_type 枚举 → 小写字符串; None 透传。"""
    if ut is None:
        return None
    return ut.value if hasattr(ut, "value") else str(ut)


def _parse_target_date(target_date: str) -> Optional[date]:
    try:
        return date.fromisoformat(target_date)
    except (ValueError, TypeError):
        return None


def _day_bounds(target: date):
    """返回当日 [day_start, day_end) 半开区间 (业务日边界换算 UTC-naive, 卡 f7422bbc)。

    与 naive-UTC 落库口径对齐: end_time / refunded_at 统一 naive-UTC, 窗口须是
    "上海日" 对应的 UTC 区间, 否则上海 00:00-08:00 的数据错归前一日。
    """
    return biz_day_bounds_utc_naive(target)


def _day_marker(target: date) -> datetime:
    """record_date 落库标记 (naive 午夜)。窗口换算 UTC-naive 后, 幂等键/前端日期过滤
    (revenue_stats 按 naive 日期串比较) 不能跟着变前一日 16:00, 单独保留 naive 午夜。"""
    return datetime.combine(target, datetime.min.time())


def _iter_target_dates(target_date: Optional[str], end_date: Optional[str]) -> List[str]:
    """解析 [target_date, end_date] 闭区间日期列表。

    - target_date 缺省取昨日(凌晨调度补前一天数据)
    - end_date 缺省=单日; end<start 时钳制到 start
    - 非法日期返回 []
    """
    # 卡 c42ac99a: beat 按上海凌晨触发 (revenue 02:30 / station 02:40), date.today()
    # 在 UTC 容器取到前日 → 错算"上海前天"。改用业务时区昨日。
    start = _parse_target_date(target_date) if target_date else yesterday_in_biz_tz()
    if start is None:
        return []
    end = _parse_target_date(end_date) if end_date else start
    if end is None or end < start:
        end = start
    days, cur = [], start
    while cur <= end:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def build_revenue_daily(db: Session, target_date: str) -> Dict[str, Any]:
    """
    聚合指定日期已完成订单 → revenue_daily

    粒度: (record_date, station_id, user_type), 按 station+user_type 分组。
    幂等: 该复合键重跑覆盖更新; 当日无订单时清理历史残留行。
    """
    target = _parse_target_date(target_date)
    if target is None:
        return {"status": "error", "error": f"日期格式错误: {target_date}"}
    day_start, day_end = _day_bounds(target)
    day_marker = _day_marker(target)

    # 1) 按站点+用户类型聚合已完成订单
    rows = (
        db.query(
            ChargingOrder.station_id,
            ChargingOrder.user_type,
            func.count(ChargingOrder.id).label("orders_count"),
            func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("energy_kwh"),
            func.coalesce(func.sum(ChargingOrder.electricity_fee), 0).label("charge_fee"),
            func.coalesce(func.sum(ChargingOrder.service_fee), 0).label("service_fee"),
            func.coalesce(func.sum(ChargingOrder.parking_fee), 0).label("parking_fee"),
            func.coalesce(func.sum(ChargingOrder.occupancy_fee), 0).label("occupancy_fee"),
            func.coalesce(func.sum(ChargingOrder.reservation_fee), 0).label("reservation_fee"),
            func.coalesce(func.sum(ChargingOrder.total_amount), 0).label("total_revenue"),
            func.coalesce(func.sum(ChargingOrder.paid_amount), 0).label("paid_revenue"),
        )
        .filter(
            ChargingOrder.order_status == OrderStatus.COMPLETED,
            ChargingOrder.end_time >= day_start,
            ChargingOrder.end_time < day_end,
        )
        .group_by(ChargingOrder.station_id, ChargingOrder.user_type)
        .all()
    )

    if not rows:
        db.query(RevenueDaily).filter(RevenueDaily.record_date == day_marker).delete(
            synchronize_session=False
        )
        return {"status": "completed", "message": "当日无已完成订单",
                "orders": 0, "date": target_date}

    # 2) 退款归属: refund_records(REFUNDED, refunded_at 当日) join 订单取 station/user_type
    refund_rows = (
        db.query(
            ChargingOrder.station_id,
            ChargingOrder.user_type,
            func.coalesce(func.sum(RefundRecord.refund_amount), 0).label("refund_amount"),
        )
        .join(RefundRecord, RefundRecord.order_id == ChargingOrder.id)
        .filter(
            RefundRecord.status == RefundStatus.REFUNDED,
            RefundRecord.refunded_at >= day_start,
            RefundRecord.refunded_at < day_end,
        )
        .group_by(ChargingOrder.station_id, ChargingOrder.user_type)
        .all()
    )
    refund_map = {
        (r.station_id, _user_type_value(r.user_type)): Decimal(str(r.refund_amount or 0))
        for r in refund_rows
    }

    written = 0

    def _upsert_rows() -> None:
        """单轮 upsert: 查到覆盖, 查不到插入。并发 worker 竞态时由外层捕获
        IntegrityError 后重跑一轮 (此时竞态对手已落库, 全部命中覆盖分支)。"""
        nonlocal written
        written = 0
        for r in rows:
            ut = _user_type_value(r.user_type)
            values = dict(
                orders_count=r.orders_count,
                energy_kwh=Decimal(str(r.energy_kwh or 0)),
                charge_fee=Decimal(str(r.charge_fee or 0)),
                service_fee=Decimal(str(r.service_fee or 0)),
                parking_fee=Decimal(str(r.parking_fee or 0)),
                occupancy_fee=Decimal(str(r.occupancy_fee or 0)),
                reservation_fee=Decimal(str(r.reservation_fee or 0)),
                total_revenue=Decimal(str(r.total_revenue or 0)),
                paid_revenue=Decimal(str(r.paid_revenue or 0)),
                refund_amount=refund_map.get((r.station_id, ut), Decimal("0")),
            )
            ut_filter = RevenueDaily.user_type.is_(None) if ut is None else RevenueDaily.user_type == ut
            existing = (
                db.query(RevenueDaily)
                .filter(
                    RevenueDaily.record_date == day_marker,
                    RevenueDaily.station_id == r.station_id,
                    ut_filter,
                )
                .first()
            )
            if existing:
                for k, v in values.items():
                    setattr(existing, k, v)
            else:
                db.add(RevenueDaily(
                    record_date=day_marker, station_id=r.station_id, user_type=ut, **values,
                ))
            written += 1

    # 卡 9863018d: 唯一约束 uq_rev_date_station_utype 支撑的原子 upsert。
    # check-then-act 竞态 (并发 worker / acks_late 重投递) 撞约束 → rollback
    # 后重跑一轮转纯覆盖语义, 消除重复行 → revenue_stats sum 双倍计算。
    try:
        _upsert_rows()
        db.flush()
    except IntegrityError:
        db.rollback()
        _upsert_rows()
        db.flush()
    total_orders = sum(r.orders_count or 0 for r in rows)
    logger.info("[analytics] revenue_daily: date=%s groups=%d orders=%d",
                target_date, written, total_orders)
    return {"status": "completed", "date": target_date,
            "groups": written, "orders": total_orders}


def build_station_daily_metrics(db: Session, target_date: str) -> Dict[str, Any]:
    """
    聚合指定日期单站运营指标 → station_daily_metrics

    粒度: (station_id, record_date); 仅有当日已完成订单的站点生成行。
    指标定义:
      - active_users/new_users: 当日该站去重下单用户 / 其中首次在该站下单者
      - utilization_rate(%): 当日充电总时长 / (充电枪总数 × 1440min) × 100, 上限100
      - idle_ratio(%): 100 - utilization_rate (互补)
      - online_devices: 充电桩中状态 ONLINE/CHARGING 的数量
      - avg_charge_duration(min): 当日已完成订单 duration_minutes 均值
      - avg_wait_time(min): 当日该站 charging_queue 记录 estimated_wait_minutes 均值
    幂等: (station_id, record_date) 重跑覆盖; 当日无订单清理残留。
    """
    target = _parse_target_date(target_date)
    if target is None:
        return {"status": "error", "error": f"日期格式错误: {target_date}"}
    day_start, day_end = _day_bounds(target)
    day_marker = _day_marker(target)

    # 1) 按站点聚合订单指标 (sum 时长, 均值在 Python 层算避免精度损失)
    order_rows = (
        db.query(
            ChargingOrder.station_id,
            func.count(ChargingOrder.id).label("orders_count"),
            func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("energy_kwh"),
            func.coalesce(func.sum(ChargingOrder.paid_amount), 0).label("revenue"),
            func.coalesce(func.sum(ChargingOrder.duration_minutes), 0).label("total_duration"),
        )
        .filter(
            ChargingOrder.order_status == OrderStatus.COMPLETED,
            ChargingOrder.end_time >= day_start,
            ChargingOrder.end_time < day_end,
        )
        .group_by(ChargingOrder.station_id)
        .all()
    )

    if not order_rows:
        db.query(StationDailyMetric).filter(
            StationDailyMetric.record_date == day_marker
        ).delete(synchronize_session=False)
        return {"status": "completed", "message": "当日无已完成订单",
                "stations": 0, "date": target_date}

    station_ids = [r.station_id for r in order_rows]

    # 2) 当日下单用户 (去重)
    today_pairs = (
        db.query(ChargingOrder.station_id, ChargingOrder.user_id)
        .filter(
            ChargingOrder.order_status == OrderStatus.COMPLETED,
            ChargingOrder.end_time >= day_start,
            ChargingOrder.end_time < day_end,
            ChargingOrder.user_id.isnot(None),
        )
        .all()
    )
    today_users = defaultdict(set)
    for sid, uid in today_pairs:
        today_users[sid].add(uid)

    # 该站历史用户(end_time < day_start): 用于判定"新增"
    prior_pairs = (
        db.query(ChargingOrder.station_id, ChargingOrder.user_id)
        .filter(
            ChargingOrder.order_status == OrderStatus.COMPLETED,
            ChargingOrder.end_time < day_start,
            ChargingOrder.station_id.in_(station_ids),
            ChargingOrder.user_id.isnot(None),
        )
        .all()
    )
    prior_users = defaultdict(set)
    for sid, uid in prior_pairs:
        prior_users[sid].add(uid)

    # 3) 充电枪总数
    gun_rows = (
        db.query(Device.station_id, func.coalesce(func.sum(Device.gun_count), 0).label("guns"))
        .filter(Device.type.in_(_CHARGER_TYPES), Device.station_id.in_(station_ids))
        .group_by(Device.station_id)
        .all()
    )
    guns = {g.station_id: (g.guns or 0) for g in gun_rows}

    # 4) 在线充电桩数
    online_rows = (
        db.query(Device.station_id, func.count(Device.id).label("cnt"))
        .filter(
            Device.type.in_(_CHARGER_TYPES),
            Device.status.in_(_ONLINE_STATUSES),
            Device.station_id.in_(station_ids),
        )
        .group_by(Device.station_id)
        .all()
    )
    online = {o.station_id: o.cnt for o in online_rows}

    # 5) 平均等待时长 (charging_queue 当日入队)
    wait_rows = (
        db.query(
            ChargingQueue.station_id,
            func.coalesce(func.avg(ChargingQueue.estimated_wait_minutes), 0).label("avg_wait"),
        )
        .filter(
            ChargingQueue.arrival_time >= day_start,
            ChargingQueue.arrival_time < day_end,
            ChargingQueue.station_id.in_(station_ids),
        )
        .group_by(ChargingQueue.station_id)
        .all()
    )
    wait = {w.station_id: (w.avg_wait or 0) for w in wait_rows}

    written = 0

    def _upsert_rows() -> None:
        """单轮 upsert, 语义同 build_revenue_daily (卡 9863018d)。"""
        nonlocal written
        written = 0
        for r in order_rows:
            station_id = r.station_id
            oc = r.orders_count or 0
            t_users = today_users.get(station_id, set())
            p_users = prior_users.get(station_id, set())

            total_duration = float(Decimal(str(r.total_duration or 0)))
            avg_duration = total_duration / oc if oc else 0.0

            gun_count = guns.get(station_id, 0) or 0
            if gun_count > 0:
                utilization = min(100.0, (total_duration / (gun_count * _MINUTES_PER_DAY)) * 100.0)
            else:
                utilization = 0.0
            utilization = round(utilization, 2)
            idle_ratio = round(max(0.0, 100.0 - utilization), 2)

            values = dict(
                active_users=len(t_users),
                new_users=len(t_users - p_users),
                orders_count=oc,
                energy_kwh=Decimal(str(r.energy_kwh or 0)),
                revenue=Decimal(str(r.revenue or 0)),
                utilization_rate=Decimal(str(utilization)),
                avg_charge_duration=int(round(avg_duration)),
                avg_wait_time=int(round(float(wait.get(station_id, 0) or 0))),
                online_devices=online.get(station_id, 0),
                idle_ratio=Decimal(str(idle_ratio)),
            )

            existing = (
                db.query(StationDailyMetric)
                .filter(
                    StationDailyMetric.station_id == station_id,
                    StationDailyMetric.record_date == day_marker,
                )
                .first()
            )
            if existing:
                for k, v in values.items():
                    setattr(existing, k, v)
            else:
                db.add(StationDailyMetric(
                    station_id=station_id, record_date=day_marker, **values,
                ))
            written += 1

    # 卡 9863018d: 唯一约束 uq_sdm_station_date 支撑的原子 upsert, 语义同
    # build_revenue_daily — 竞态撞约束 → rollback 重跑一轮转纯覆盖。
    try:
        _upsert_rows()
        db.flush()
    except IntegrityError:
        db.rollback()
        _upsert_rows()
        db.flush()
    logger.info("[analytics] station_daily_metrics: date=%s stations=%d",
                target_date, written)
    return {"status": "completed", "date": target_date, "stations": written}


@shared_task(name="analytics.aggregate_revenue_daily", bind=True,
             max_retries=2, default_retry_delay=60)
def aggregate_revenue_daily_task(
    self, target_date: Optional[str] = None, end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    每日营收聚合任务(revenue_daily)

    - 凌晨 beat 调度: 无参 → 补前一天
    - 手动补算: 传 target_date(单日) 或 target_date+end_date(闭区间)
    """
    dates = _iter_target_dates(target_date, end_date)
    logger.info("[analytics] aggregate_revenue_daily: dates=%s", dates)
    db = SessionLocal()
    results: List[Dict[str, Any]] = []
    try:
        for d in dates:
            results.append(build_revenue_daily(db, d))
            db.commit()
        return results
    except Exception as e:
        db.rollback()
        logger.error("[analytics] revenue_daily 聚合失败: %s", e, exc_info=True)
        raise self.retry(exc=e)
    finally:
        db.close()


@shared_task(name="analytics.aggregate_station_daily_metrics", bind=True,
             max_retries=2, default_retry_delay=60)
def aggregate_station_daily_metrics_task(
    self, target_date: Optional[str] = None, end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    每日站点运营指标聚合任务(station_daily_metrics)

    - 凌晨 beat 调度: 无参 → 补前一天
    - 手动补算: 传 target_date(单日) 或 target_date+end_date(闭区间)
    """
    dates = _iter_target_dates(target_date, end_date)
    logger.info("[analytics] aggregate_station_daily_metrics: dates=%s", dates)
    db = SessionLocal()
    results: List[Dict[str, Any]] = []
    try:
        for d in dates:
            results.append(build_station_daily_metrics(db, d))
            db.commit()
        return results
    except Exception as e:
        db.rollback()
        logger.error("[analytics] station_daily_metrics 聚合失败: %s", e, exc_info=True)
        raise self.retry(exc=e)
    finally:
        db.close()
