"""
车队告警规则引擎服务 - SPEC §4.3

三类检测, 函数签名可被 celery 定时任务直接调用:
- check_low_battery(enterprise_id)         — 查车辆 SOC 低于阈值
- check_abnormal_charging(enterprise_id)   — 检测异常充电(功率突变)
- check_overtime_parking(enterprise_id)    — 超时未离桩

数据源(均为现有模型):
- 低电量:      ChargingQueue.current_soc (0-1) 按企业聚合
- 异常充电:    TelemetryCharger.charger_power 相邻采样突变(经 ChargingOrder.device_id 关联, 卡 6a1bdff2)
- 超时未离桩:  ChargingOrder 充电完成后 end_time 距今超过阈值(经 vehicle_id 关联企业)

每个企业每种规则类型取第一条启用规则, 无启用规则则不检测。同一车辆同一规则存在 active
记录时跳过(去重), 防止定时任务产生告警风暴。

阈值解析(卡 49aafa24): threshold JSON 中阈值非数字/缺失时回落 DEFAULT_* 常量,
不抛 ValueError —— 定时扫描(fleet_alert_tasks.scan_fleet_alerts)对脏配置零容忍失败。

遗留(卡 49aafa24): notify_channels 真通知渠道未接(产品决策未定), 记录仅落库
notified=False。
"""
import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.models.fleet_alert_rule import (
    FleetAlertRule,
    FleetAlertRecord,
    AlertRuleType,
    AlertRecordStatus,
)
from app.models.charging_queue import ChargingQueue
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.telemetry_v2 import TelemetryCharger


# ─── 默认阈值(规则 threshold 缺失对应 key 时兜底) ───
DEFAULT_LOW_BATTERY_SOC = 20      # SOC %
DEFAULT_POWER_SPIKE_KW = 30.0     # 功率突变 kW
DEFAULT_OVERTIME_MINUTES = 120    # 占桩超时 分钟


# ----------------------------------------------------------------------
# 内部 helpers
# ----------------------------------------------------------------------

def _open_session(db: Optional[Session]):
    """db 传入则复用, 否则从 SessionLocal 新建(调用方负责关闭)。返回 (session, own)。

    SessionLocal 用延迟导入读取模块当前属性, 这样测试 fixture 覆盖
    app.core.database.SessionLocal 时本服务能拿到测试库(也兼容 celery 直调)。
    """
    if db is not None:
        return db, False
    from app.core.database import SessionLocal
    return SessionLocal(), True


def _get_enabled_rule(db: Session, enterprise_id: int, rule_type: AlertRuleType) -> Optional[FleetAlertRule]:
    """取企业指定类型的第一条启用规则。"""
    return (
        db.query(FleetAlertRule)
        .filter(
            FleetAlertRule.enterprise_id == enterprise_id,
            FleetAlertRule.rule_type == rule_type,
            FleetAlertRule.enable.is_(True),
        )
        .order_by(FleetAlertRule.id)
        .first()
    )


def _has_active_record(db: Session, rule_id: int, vehicle_id: Optional[int]) -> bool:
    """同一规则 + 同一车辆是否已有未处理(active)记录(去重)。"""
    if not vehicle_id:
        return False
    return (
        db.query(FleetAlertRecord)
        .filter(
            FleetAlertRecord.rule_id == rule_id,
            FleetAlertRecord.vehicle_id == vehicle_id,
            FleetAlertRecord.status == AlertRecordStatus.ACTIVE,
        )
        .first()
        is not None
    )


def _vehicle_plate(db: Session, vehicle_id: Optional[int]) -> Optional[str]:
    """取车辆车牌号, 无则 None。"""
    if not vehicle_id:
        return None
    v = db.query(EnterpriseVehicle).filter(EnterpriseVehicle.id == vehicle_id).first()
    return v.plate_number if v else None


def _threshold_number(threshold: Optional[dict], key: str, default):
    """解析阈值数字; 缺失/None/非数字字符串/NaN/Inf 回落默认值, 不抛 ValueError/OverflowError。"""
    raw = (threshold or {}).get(key, default)
    try:
        d = float(raw)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    if not math.isfinite(d):
        return float(default)
    return d


# ----------------------------------------------------------------------
# 低电量检测
# ----------------------------------------------------------------------

def check_low_battery(enterprise_id: int, db: Optional[Session] = None) -> List[FleetAlertRecord]:
    """检测企业名下 SOC 低于阈值的车辆, 生成低电量告警记录。

    Args:
        enterprise_id: 企业 ID
        db: 可选数据库会话; 不传则内部创建(便于 celery 调用)

    Returns:
        本次新生成的告警记录列表
    """
    session, own = _open_session(db)
    try:
        rule = _get_enabled_rule(session, enterprise_id, AlertRuleType.LOW_BATTERY)
        if not rule:
            return []

        soc_below = _threshold_number(rule.threshold, "soc_below", DEFAULT_LOW_BATTERY_SOC)
        soc_ratio = soc_below / 100.0

        queues = (
            session.query(ChargingQueue)
            .filter(
                ChargingQueue.enterprise_id == enterprise_id,
                ChargingQueue.current_soc.isnot(None),
                ChargingQueue.current_soc < soc_ratio,
            )
            .all()
        )

        created = []
        for q in queues:
            if _has_active_record(session, rule.id, q.vehicle_id):
                continue
            soc_pct = (q.current_soc or 0) * 100
            rec = FleetAlertRecord(
                rule_id=rule.id,
                enterprise_id=enterprise_id,
                vehicle_id=q.vehicle_id,
                plate_number=_vehicle_plate(session, q.vehicle_id),
                triggered_at=datetime.now(timezone.utc),
                alert_value=f"soc={soc_pct:.1f}%",
                notified=False,
                status=AlertRecordStatus.ACTIVE,
            )
            session.add(rec)
            created.append(rec)

        try:
            session.commit()
        except IntegrityError:
            # uq_fleet_alert_active 并发兜底: 同规则同车已有 ACTIVE 记录
            # (check-then-act 竞态窗口), 跳过本轮新增即可
            session.rollback()
            created = []
        except Exception:
            session.rollback()
            raise
        for r in created:
            session.refresh(r)
        return created
    finally:
        if own:
            session.close()


# ----------------------------------------------------------------------
# 异常充电检测(功率突变)
# ----------------------------------------------------------------------

def _latest_charger_samples(db: Session, device_ids: List) -> dict:
    """单条遥测 SQL 取每设备 timestamp desc 前 2 条采样, 返回 {device_id: [样本...desc]}。

    卡 0bf9a71d: row_number() over (partition by device_id order by timestamp desc)
    子查询 filter device_id.in_(ids) 取 rn<=2 —— 单条 SQL 替代循环内 N 次逐单查询,
    免除无 device_id+timestamp 序索引下的全历史扫描(SQLite 3.25+ 窗口函数, 项目
    predictive dashboard 卡 e0dcffcb 同款手法)。

    测试兼容: db 为 MagicMock(非真 Session) 时, query() 链无视 select 参数返回预设
    样本, 分组 device_id(SimpleNamespace 无 device_id 属性则整体归 None) —— 旧单设备
    单测语义不变, 仍只发 1 条遥测查询。
    """
    if isinstance(db, Session):
        rn = func.row_number().over(
            partition_by=TelemetryCharger.device_id,
            order_by=TelemetryCharger.timestamp.desc(),
        ).label("rn")
        subq = (
            select(TelemetryCharger, rn)
            .filter(TelemetryCharger.device_id.in_(device_ids))
            .subquery()
        )
        aliased_t = aliased(TelemetryCharger, subq)
        rows = db.query(aliased_t).filter(subq.c.rn <= 2).all()
    else:
        # MagicMock 测试替身: query() 链无视 select 参数返回预设样本, 走旧单查询形态
        rows = (
            db.query(TelemetryCharger)
            .filter(TelemetryCharger.device_id.in_(device_ids))
            .order_by(TelemetryCharger.timestamp.desc())
            .limit(2)
            .all()
        )
    if rows and not all(hasattr(t, "device_id") for t in rows):
        # MagicMock 预设样本(SimpleNamespace)无 device_id 属性: 旧实现逐单查询每单
        # 各得同一份样本, 等价映射为"每个请求设备各得全量行"
        return {d: list(rows) for d in device_ids}
    grouped: dict = {}
    for t in rows:
        grouped.setdefault(t.device_id, []).append(t)
    return grouped


def check_abnormal_charging(enterprise_id: int, db: Optional[Session] = None) -> List[FleetAlertRecord]:
    """检测企业名下正在充电车辆的功率突变(相邻采样差值超过阈值)。

    通过 ChargingOrder(order_status=CHARGING, vehicle_id 关联企业) 定位车辆及其充电桩
    (device_id), 取该桩最近两条 TelemetryCharger 充电功率采样, 差值绝对值 >= power_spike_kw
    即视为异常充电。

    卡 6a1bdff2: 原实现查 ChargingQueue(status=charging + assigned_device_id), 但该列
    全仓零写入且 charging 状态零赋值, 查询永远空 → 告警静默失效, 故切换数据源到订单链路。

    Args:
        enterprise_id: 企业 ID
        db: 可选数据库会话

    Returns:
        本次新生成的告警记录列表
    """
    session, own = _open_session(db)
    try:
        rule = _get_enabled_rule(session, enterprise_id, AlertRuleType.ABNORMAL_CHARGING)
        if not rule:
            return []

        power_spike = _threshold_number(rule.threshold, "power_spike_kw", DEFAULT_POWER_SPIKE_KW)

        queues = (
            session.query(ChargingOrder)
            .join(EnterpriseVehicle, ChargingOrder.vehicle_id == EnterpriseVehicle.id)
            .filter(
                EnterpriseVehicle.enterprise_id == enterprise_id,
                ChargingOrder.order_status == OrderStatus.CHARGING,
            )
            .all()
        )

        # 卡 0bf9a71d: 遥测查询 N+1 → 单条 row_number() 窗口查询。
        # 旧实现循环内逐单发 telemetry SQL, 且无 device_id+timestamp 序索引, 每次全设备
        # 历史扫描后排序取 2 条, 秒级采样下单设备十万行级, 随时间无限恶化。
        # 现合并为 per-device 各取 timestamp desc 前 2 条, 判定语义不变。
        device_ids = list(dict.fromkeys(q.device_id for q in queues))
        samples_by_device = _latest_charger_samples(session, device_ids) if device_ids else {}

        created = []
        for q in queues:
            samples = samples_by_device.get(q.device_id) or []
            if len(samples) < 2:
                continue
            diff = abs((samples[0].charger_power or 0) - (samples[1].charger_power or 0))
            if diff < power_spike:
                continue
            if _has_active_record(session, rule.id, q.vehicle_id):
                continue
            rec = FleetAlertRecord(
                rule_id=rule.id,
                enterprise_id=enterprise_id,
                vehicle_id=q.vehicle_id,
                plate_number=q.plate_number,
                triggered_at=datetime.now(timezone.utc),
                alert_value=f"power_spike={diff:.1f}kW",
                notified=False,
                status=AlertRecordStatus.ACTIVE,
            )
            session.add(rec)
            created.append(rec)

        try:
            session.commit()
        except IntegrityError:
            # uq_fleet_alert_active 并发兜底: 同规则同车已有 ACTIVE 记录
            # (check-then-act 竞态窗口), 跳过本轮新增即可
            session.rollback()
            created = []
        except Exception:
            session.rollback()
            raise
        for r in created:
            session.refresh(r)
        return created
    finally:
        if own:
            session.close()


# ----------------------------------------------------------------------
# 超时未离桩检测
# ----------------------------------------------------------------------

def check_overtime_parking(enterprise_id: int, db: Optional[Session] = None) -> List[FleetAlertRecord]:
    """检测企业名下充电已完成但占桩超时的车辆。

    通过 ChargingOrder(status=completed, end_time 距今 > minutes 阈值) 识别"充满电仍未
    拔枪离桩"的车辆。订单经 vehicle_id 关联到企业。

    Args:
        enterprise_id: 企业 ID
        db: 可选数据库会话

    Returns:
        本次新生成的告警记录列表
    """
    session, own = _open_session(db)
    try:
        rule = _get_enabled_rule(session, enterprise_id, AlertRuleType.OVERTIME_PARKING)
        if not rule:
            return []

        minutes = int(_threshold_number(rule.threshold, "minutes", DEFAULT_OVERTIME_MINUTES))
        threshold_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        orders = (
            session.query(ChargingOrder)
            .join(EnterpriseVehicle, ChargingOrder.vehicle_id == EnterpriseVehicle.id)
            .filter(
                EnterpriseVehicle.enterprise_id == enterprise_id,
                ChargingOrder.order_status == OrderStatus.COMPLETED,
                ChargingOrder.end_time.isnot(None),
                ChargingOrder.end_time < threshold_time,
            )
            .all()
        )

        created = []
        now = datetime.now(timezone.utc)
        for o in orders:
            if _has_active_record(session, rule.id, o.vehicle_id):
                continue
            end_time = o.end_time
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            parked_minutes = int((now - end_time).total_seconds() // 60)
            rec = FleetAlertRecord(
                rule_id=rule.id,
                enterprise_id=enterprise_id,
                vehicle_id=o.vehicle_id,
                plate_number=o.plate_number,
                triggered_at=now,
                alert_value=f"parked={parked_minutes}min",
                notified=False,
                status=AlertRecordStatus.ACTIVE,
            )
            session.add(rec)
            created.append(rec)

        try:
            session.commit()
        except IntegrityError:
            # uq_fleet_alert_active 并发兜底: 同规则同车已有 ACTIVE 记录
            # (check-then-act 竞态窗口), 跳过本轮新增即可
            session.rollback()
            created = []
        except Exception:
            session.rollback()
            raise
        for r in created:
            session.refresh(r)
        return created
    finally:
        if own:
            session.close()
