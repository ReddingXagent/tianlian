"""
预测性维护异步任务
Phase 4 - 模型训练、预测等耗时操作
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from celery import shared_task
from sqlalchemy.orm import Session

from app.core.database import SessionLocal  # noqa: F401 兼容外部 monkeypatch (卡 a6e2e562)
from app.tasks._soft_timeout import SoftTimeLimitExceeded  # 卡 411936df
from app.core.config import settings
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.alarm import Alarm
from app.models.analytics import MLModel, PredictionAlert

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 数据保留/日志表清理 (卡 0364c10e)
# ═══════════════════════════════════════════════════════════════

# 资金/业务表白名单 —— 绝对禁止进入任何清理范围。
# charging_orders / settlements / reconciliations / invoices /
# enterprise_transactions / occupancy_events / payments 等承载资金
# 事实与法务凭证, 保留策略只能由财务/合规流程单独决策, 本任务永不触碰。
_PROTECTED_TABLES = frozenset({
    "charging_orders",
    "settlements",
    "reconciliations",
    "invoices",
    "enterprise_transactions",
    "occupancy_events",
    "payments",
    "refund_orders",
})


def _retention_tables() -> list:
    """构建保留清理表配置 [(model, 时间列, 保留天数, 表名)]。

    保留窗口优先读 settings(env 可覆盖), 默认值依据见 config.py 注释。
    """
    from app.models.notification import Notification
    from app.models.notification_config import NotificationLog
    from app.models.audit_log import AuditLog
    from app.models.device_control_log import DeviceControlLog
    from app.models.device_efficiency_log import DeviceEfficiencyLog
    from app.models.energy_strategy import EnergyFlowLog
    from app.models.alarm import AlarmRuleLog
    from app.models.on_call import OnCallLog
    from app.models.runbook_approval import RunbookApprovalLog

    return [
        (Notification, Notification.created_at, settings.RETENTION_NOTIFICATIONS_DAYS, "notifications"),
        (NotificationLog, NotificationLog.created_at, settings.RETENTION_NOTIFICATION_LOGS_DAYS, "notification_logs"),
        (DeviceControlLog, DeviceControlLog.created_at, settings.RETENTION_DEVICE_CONTROL_LOGS_DAYS, "device_control_logs"),
        (AuditLog, AuditLog.timestamp, settings.RETENTION_AUDIT_LOGS_DAYS, "audit_logs"),
        (DeviceEfficiencyLog, DeviceEfficiencyLog.created_at, settings.RETENTION_DEVICE_EFFICIENCY_LOGS_DAYS, "device_efficiency_logs"),
        (EnergyFlowLog, EnergyFlowLog.created_at, settings.RETENTION_ENERGY_FLOW_LOG_DAYS, "energy_flow_log"),
        (AlarmRuleLog, AlarmRuleLog.checked_at, settings.RETENTION_ALARM_RULE_LOGS_DAYS, "alarm_rule_logs"),
        (OnCallLog, OnCallLog.created_at, settings.RETENTION_ON_CALL_LOGS_DAYS, "on_call_logs"),
        (RunbookApprovalLog, RunbookApprovalLog.created_at, settings.RETENTION_RUNBOOK_APPROVAL_LOGS_DAYS, "runbook_approval_logs"),
    ]


def _delete_in_chunks(
    db: Session,
    model,
    time_col,
    cutoff,
    chunk_size: int,
    extra_filters: Optional[List] = None,
) -> int:
    """按 PK id range 分批删除 time_col < cutoff 的行, 每批独立 commit。

    避免单条大 DELETE 的大事务长锁 + WAL/表膨胀。返回累计删除数。
    删除条件保留时间过滤: id 区间 [first, last] 内可能夹带窗口内新行, 不可裸删区间。
    extra_filters: 额外过滤条件列表 (如 Alarm.status.in_(...)), 游标查询与
    实际 delete 两处同时套用 —— 未命中条件的行既不误删, 也不阻塞游标推进。
    """
    total = 0
    while True:
        first = (
            db.query(model.id)
            .filter(time_col < cutoff, *(extra_filters or []))
            .order_by(model.id)
            .first()
        )
        if first is None:
            break
        first_id = first[0]
        last = (
            db.query(model.id)
            .filter(time_col < cutoff, model.id >= first_id, *(extra_filters or []))
            .order_by(model.id)
            .offset(chunk_size - 1)
            .first()
        )
        last_id = last[0] if last is not None else first_id
        deleted = (
            db.query(model)
            .filter(
                model.id >= first_id,
                model.id <= last_id,
                time_col < cutoff,
                *(extra_filters or []),
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        total += deleted
        if deleted == 0:
            # 防御: 区间删除空转时强制推进下界, 避免理论死循环
            # (first_id 来自同过滤条件的游标查询, 此处套用同一组条件,
            #  不会误删不符合 extra_filters 的行)
            db.query(model).filter(
                model.id == first_id, time_col < cutoff, *(extra_filters or [])
            ).delete(synchronize_session=False)
            db.commit()
    return total


def _run_db_task(func):
    """统一的数据库任务包装器"""
    # 调用时解析 SessionLocal: 模块顶部 from-import 会在 conftest 运行时
    # override (app.core.database.SessionLocal = 测试库) 之前固化绑定,
    # 导致任务写错库。此处按调用时刻取值, 与 override 语义一致。
    from app.core.database import SessionLocal as _SessionLocal
    db = _SessionLocal()
    try:
        result = func(db)
        db.commit()
        return result
    except SoftTimeLimitExceeded:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error("异步任务执行失败: %s", e, exc_info=True)
        raise
    finally:
        db.close()


@shared_task(
    name="maintenance.train_model",
    bind=True,
    max_retries=1,
    soft_time_limit=300,
)
def train_model_task(
    self,
    model_name: str,
    model_type: str = "classification",
) -> Dict[str, Any]:
    """
    异步训练ML模型
    模拟训练过程（实际部署时替换为真实训练逻辑）
    """
    logger.info("[Celery] 开始训练模型: %s", model_name)

    def _execute(db: Session):
        import time
        time.sleep(5)  # 模拟训练耗时

        # 保存模型记录
        ml_model = MLModel(
            model_name=model_name,
            model_type=model_type,
            version=f"v{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
            performance_metrics={
                "accuracy": 0.92,
                "precision": 0.89,
                "recall": 0.91,
                "f1_score": 0.90,
            },
            is_active=True,
        )
        db.add(ml_model)

        return {
            "task_id": self.request.id,
            "model_name": model_name,
            "model_type": model_type,
            "version": ml_model.version,
            "status": "completed",
        }

    return _run_db_task(_execute)


@shared_task(
    name="maintenance.predict_faults",
    bind=True,
    max_retries=2,
)
def predict_faults_task(
    self,
    device_id: int,
    prediction_days: int = 7,
) -> Dict[str, Any]:
    """
    异步故障预测
    基于遥测数据进行异常预测
    """
    logger.info("[Celery] 开始故障预测, device_id=%s", device_id)

    def _execute(db: Session):
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            raise ValueError(f"设备 {device_id} 不存在")

        # prediction_days 驱动历史回看窗口与预测落点: cutoff 回看最近
        # prediction_days 天遥测; 预测落点在未来 prediction_days 窗口内 ——
        # warning(轻)落远端, critical(重)落近端(至少 1 天)。
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=prediction_days)
        warn_predicted_time = now + timedelta(days=prediction_days)
        crit_predicted_time = now + timedelta(days=max(1, prediction_days // 3))
        telemetry = (
            db.query(Telemetry)
            .filter(Telemetry.device_id == device_id, Telemetry.timestamp >= cutoff)
            .order_by(Telemetry.timestamp.desc())
            .limit(1000)
            .all()
        )

        predictions = []
        skipped = []

        def _has_recent_prediction(severity: str) -> bool:
            """同 device_id + alert_type + severity 是否已有未确认且 24h 内的告警。

            对齐 fleet_alert_service._has_active_record 的 active 去重标准:
            同规则(此处以 severity 区分温度/电池两类)+ 同对象存在未处理记录
            则跳过新建。severity 必须入键 —— 温度(warning)/电池(critical)共用
            alert_type='fault_prediction', 只按 type 去重会吞掉同轮另一分支。
            created_at 由 server_default=func.now() 生成, SQLite 存 naive 字符串,
            比较参数须同样 naive, 否则带 +00:00 后缀的字符串比较恒假。
            """
            return (
                db.query(PredictionAlert)
                .filter(
                    PredictionAlert.device_id == device_id,
                    PredictionAlert.alert_type == "fault_prediction",
                    PredictionAlert.severity == severity,
                    # 不用 is_(False): SQLite 下 server_default="false" 落成
                    # text 'false'(truthy), is_(False) 恒漏; isnot(True) 对
                    # False/0/'false'/NULL 均通过, PG 下语义等价。
                    PredictionAlert.acknowledged.isnot(True),
                    PredictionAlert.created_at
                    >= now.replace(tzinfo=None) - timedelta(hours=24),
                )
                .first()
                is not None
            )

        # 简化的异常检测逻辑
        if telemetry:
            temps = [t.battery_temperature for t in telemetry if t.battery_temperature is not None]
            socs = [t.battery_soc for t in telemetry if t.battery_soc is not None]

            if temps:
                avg_temp = sum(temps) / len(temps)
                if avg_temp > 45:
                    if _has_recent_prediction("warning"):
                        skipped.append({
                            "type": "temperature",
                            "reason": "同设备已存在未确认的温度偏高预测告警(24h内), 跳过新建",
                        })
                    else:
                        alert = PredictionAlert(
                            device_id=device_id,
                            alert_type="fault_prediction",
                            severity="warning",
                            predicted_time=warn_predicted_time,
                            confidence=0.75,
                            description=f"设备温度持续偏高(平均{avg_temp:.1f}°C)，可能存在散热问题",
                            suggested_action="检查散热系统，清洁风扇，检查温度传感器",
                        )
                        db.add(alert)
                        predictions.append({
                            "type": "temperature",
                            "severity": "warning",
                            "description": f"温度偏高: {avg_temp:.1f}°C",
                        })

            if socs:
                min_soc = min(socs)
                if min_soc < 20:
                    if _has_recent_prediction("critical"):
                        skipped.append({
                            "type": "battery",
                            "reason": "同设备已存在未确认的SOC过低预测告警(24h内), 跳过新建",
                        })
                    else:
                        alert = PredictionAlert(
                            device_id=device_id,
                            alert_type="fault_prediction",
                            severity="critical",
                            predicted_time=crit_predicted_time,
                            confidence=0.85,
                            description=f"电池SOC过低(最低{min_soc:.1f}%)，存在电池衰减风险",
                            suggested_action="检查电池健康度，考虑更换电池组",
                        )
                        db.add(alert)
                        predictions.append({
                            "type": "battery",
                            "severity": "critical",
                            "description": f"电池SOC过低: {min_soc:.1f}%",
                        })

        return {
            "task_id": self.request.id,
            "device_id": device_id,
            "prediction_count": len(predictions),
            "predictions": predictions,
            "skipped": skipped,
            "status": "completed",
        }

    return _run_db_task(_execute)


@shared_task(
    name="maintenance.cleanup_stale_pending_orders",
    bind=True,
    max_retries=1,
)
def cleanup_stale_pending_orders_task(
    self,
    timeout_minutes: int = 10,
) -> Dict[str, Any]:
    """
    批量清理超时 pending 订单 (卡 eb9f824b, 契约 §7.1)

    RemoteStart 下发后 charger 无 StartTransaction 确认的僵尸 pending 订单,
    会永久占用 connector 阻塞其他用户。beat 每 5 分钟调度一次兜底清理。
    """
    logger.info("[Celery] 开始清理超时 pending 订单, timeout_minutes=%s", timeout_minutes)

    def _execute(db: Session):
        from app.services.order_cleanup_service import cleanup_stale_pending_orders

        return cleanup_stale_pending_orders(db, timeout_minutes=timeout_minutes)

    return _run_db_task(_execute)


@shared_task(
    name="maintenance.cleanup_old_data",
    bind=True,
    max_retries=1,
)
def cleanup_old_data_task(
    self,
    days_old: int = 30,
) -> Dict[str, Any]:
    """
    清理旧数据
    删除超过指定天数的历史遥测数据和已处理的告警
    """
    # 数据安全守卫: days_old < 1 使 cutoff 落在 now 及未来, 会删除全量历史遥测。
    if days_old < 1:
        raise ValueError(
            f"days_old 必须 >= 1 (当前={days_old}); 0 或负数会删除全量历史数据"
        )
    logger.info("[Celery] 开始清理 %d 天前的旧数据", days_old)

    def _execute(db: Session):
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        chunk_size = settings.RETENTION_DELETE_CHUNK

        # 清理旧遥测数据 (分块删除, 对齐 _delete_in_chunks 范式, 卡 35e0ee7b)
        # 遗留说明: 旧 Telemetry 宽表在 V2 拆分后生产已停止写入 (0 行空表),
        # 此处删除逻辑保留是为兼容尚未切流的环境与历史数据; 实际增长压力
        # 在下方 V2 三张专表 (卡 515cfc13)。迁移链不动 (卡 06158913 决策)。
        deleted_telemetry = _delete_in_chunks(
            db, Telemetry, Telemetry.timestamp, cutoff_date, chunk_size
        )

        # V2 拆分表遥测留存 (卡 515cfc13): 生产写入已切至 telemetry_pv/
        # telemetry_battery/telemetry_charger, 旧逻辑只删空表导致留存落空。
        from app.models.telemetry_v2 import (
            TelemetryPV,
            TelemetryBattery,
            TelemetryCharger,
        )

        deleted_telemetry_v2: Dict[str, int] = {}
        for model in (TelemetryPV, TelemetryBattery, TelemetryCharger):
            deleted_telemetry_v2[model.__tablename__] = _delete_in_chunks(
                db, model, model.timestamp, cutoff_date, chunk_size
            )

        # 清理已处理的告警(保留未处理告警)
        deleted_alarms = _delete_in_chunks(
            db, Alarm, Alarm.created_at, cutoff_date, chunk_size,
            extra_filters=[Alarm.status.in_(["resolved", "closed", "acknowledged"])],
        )
        
        logger.info(
            "[Celery] 已清理 %d 条旧表遥测, %d 条告警, V2 遥测 %s",
            deleted_telemetry, deleted_alarms, deleted_telemetry_v2,
        )

        return {
            "task_id": self.request.id,
            "days_old": days_old,
            "deleted_telemetry": deleted_telemetry,
            "deleted_telemetry_v2": deleted_telemetry_v2,
            "deleted_alarms": deleted_alarms,
            "status": "completed",
        }

    return _run_db_task(_execute)


@shared_task(
    name="maintenance.batch_predict_faults",
    bind=True,
    max_retries=1,
)
def batch_predict_faults_task(
    self,
    station_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    批量故障预测
    对所有设备或指定站点的设备执行故障预测
    """
    logger.info("[Celery] 开始批量故障预测, station_id=%s", station_id)

    def _execute(db: Session):
        query = db.query(Device)
        if station_id:
            query = query.filter(Device.station_id == station_id)
        
        devices = query.all()
        results = []
        
        for device in devices:
            try:
                # 调用单个设备的故障预测任务。
                # 注: __wrapped__ 是 bound method (self 已绑到 task proxy),
                # 不可再传 predict_faults_task 作首参 —— 否则该实参落到 device_id
                # 形参位, device.id 落到 prediction_days, 与关键字 prediction_days=7
                # 冲突 → TypeError(multiple values for 'prediction_days'),
                # 导致批量预测每个设备都抛异常走 except, 批量预测功能全失效。
                task_result = predict_faults_task.__wrapped__(
                    device.id,
                    prediction_days=7,
                )
                results.append(task_result)
            except SoftTimeLimitExceeded:
                raise
            except Exception as e:
                logger.error("设备 %s 预测失败: %s", device.id, e)
                results.append({
                    "device_id": device.id,
                    "error": str(e),
                    "status": "failed",
                })
        
        return {
            "task_id": self.request.id,
            "total_devices": len(devices),
            "results": results,
            "status": "completed",
        }

    return _run_db_task(_execute)


@shared_task(
    name="maintenance.cleanup_retention_logs",
    bind=True,
    max_retries=1,
)
def cleanup_retention_logs_task(
    self,
    overrides: Optional[Dict[str, int]] = None,
    chunk_size: Optional[int] = None,
) -> Dict[str, Any]:
    """数据保留清理: 高增长日志表按窗口过期 (卡 0364c10e)

    只清日志/流水类表 (notifications / *_logs / energy_flow_log 等),
    资金/业务表 (charging_orders/settlements/invoices 等) 永不在清理范围
    (见 _PROTECTED_TABLES 白名单断言)。

    overrides: {表名: 天数} 可按调用覆盖单表窗口 (测试/手动运维用)。
    返回 {表名: 删除行数} 汇总, 供监控告警。
    """
    overrides = overrides or {}
    if chunk_size is None:
        chunk_size = settings.RETENTION_DELETE_CHUNK
    if chunk_size < 1:
        raise ValueError(f"chunk_size 必须 >= 1 (当前={chunk_size})")

    tables = _retention_tables()

    # 数据安全守卫: 白名单表绝不允许被本任务清理 (模型表名硬断言)
    for model, _tc, _days, name in tables:
        if model.__tablename__ in _PROTECTED_TABLES:
            raise RuntimeError(f"保护表 {name} 泄漏进清理范围, 拒绝执行")

    # days_old < 1 守卫: 0/负数窗口会使 cutoff 落在 now 及未来 → 删全量
    for model, _tc, days, name in tables:
        effective = overrides.get(name, days)
        if effective < 1:
            raise ValueError(
                f"表 {name} 保留天数必须 >= 1 (当前={effective}); 0 或负数会删除全量数据"
            )

    logger.info("[Celery] 开始数据保留清理, chunk_size=%d", chunk_size)

    def _execute(db: Session):
        now = datetime.now(timezone.utc)
        summary: Dict[str, int] = {}
        for model, time_col, days, name in tables:
            effective_days = overrides.get(name, days)
            cutoff = now - timedelta(days=effective_days)
            deleted = _delete_in_chunks(db, model, time_col, cutoff, chunk_size)
            summary[name] = deleted
            if deleted:
                logger.info(
                    "[Celery] 保留清理 %s: 窗口=%dd, 删除=%d", name, effective_days, deleted
                )
        return {
            "task_id": self.request.id,
            "deleted": summary,
            "chunk_size": chunk_size,
            "status": "completed",
        }

    return _run_db_task(_execute)
