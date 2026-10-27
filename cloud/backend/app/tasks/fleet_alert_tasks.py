"""车队告警规则引擎定时扫描任务 (卡 49aafa24)

fleet_alert_service 三类检测 (低电量/异常充电/超时占桩) 此前零生产调用方 —
beat/task/API 均无, 企业配置的告警规则永不触发。本模块补齐生产接线:

- scan_fleet_alerts: beat 每 5 分钟调度, 枚举所有"存在启用规则"的企业
  (distinct enterprise_id), 逐企业跑三类检测。单企业异常隔离
  (per-enterprise try/except + logger.exception + 继续), 一个企业炸不拖垮
  整轮扫描。
"""
import logging
from typing import Any, Dict, List

from celery import shared_task

from app.models.fleet_alert_rule import FleetAlertRule, AlertRuleType
from app.tasks._soft_timeout import SoftTimeLimitExceeded  # 卡 411936df

logger = logging.getLogger(__name__)


def _enabled_enterprise_ids(db) -> List[int]:
    """所有存在启用规则的企业 ID (distinct)。"""
    rows = (
        db.query(FleetAlertRule.enterprise_id)
        .filter(FleetAlertRule.enable.is_(True))
        .distinct()
        .all()
    )
    return sorted(r[0] for r in rows)


@shared_task(
    name="fleet.scan_fleet_alerts",
    bind=True,
    max_retries=1,
)
def scan_fleet_alerts_task(self) -> Dict[str, Any]:
    """全量企业车队告警扫描: 逐企业跑三类检测, 单企业异常隔离。"""
    logger.info("[Celery] 开始车队告警扫描")
    # SessionLocal 懒取模块属性: 测试 fixture override app.core.database.SessionLocal
    # 时拿到测试库 (与 fleet_alert_service._open_session 同模式)
    import app.core.database as db_module
    db = db_module.SessionLocal()
    try:
        enterprise_ids = _enabled_enterprise_ids(db)
    finally:
        db.close()

    from app.services import fleet_alert_service as svc
    checks = {
        AlertRuleType.LOW_BATTERY.value: svc.check_low_battery,
        AlertRuleType.ABNORMAL_CHARGING.value: svc.check_abnormal_charging,
        AlertRuleType.OVERTIME_PARKING.value: svc.check_overtime_parking,
    }

    created_count = 0
    errors: List[Dict[str, Any]] = []
    for enterprise_id in enterprise_ids:
        # 单企业异常隔离: check 内部自带 commit/rollback, 抛错只影响本企业
        for kind, check in checks.items():
            try:
                created_count += len(check(enterprise_id))
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:
                logger.exception(
                    "[Celery] 车队告警检测失败 enterprise=%s check=%s: %s",
                    enterprise_id, kind, exc,
                )
                errors.append({
                    "enterprise_id": enterprise_id,
                    "check": kind,
                    "error": str(exc),
                })

    if errors:
        logger.warning(
            "[Celery] 车队告警扫描完成: %d 企业, 新增 %d 条, %d 个失败",
            len(enterprise_ids), created_count, len(errors),
        )
    else:
        logger.info(
            "[Celery] 车队告警扫描完成: %d 企业, 新增 %d 条",
            len(enterprise_ids), created_count,
        )

    return {
        "task_id": self.request.id,
        "enterprises": len(enterprise_ids),
        "created": created_count,
        "errors": errors,
        "status": "completed_with_errors" if errors else "completed",
    }
