"""
维护计划调度检查 - 到期/临近维护提醒
Phase: 维护计划自动提醒
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.tasks.tz_utils import today_in_biz_tz
from app.models.device import Device
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

logger = logging.getLogger(__name__)


class MaintenanceScheduleChecker:
    """维护计划到期检查器
    
    每天检查一次，对即将到期或已过期的维护计划生成告警通知。
    通知阈值：
    - overdue: 已超过 next_maintenance_date（过期）
    - soon: 距离 next_maintenance_date 不足 7 天（即将到期）
    - warning: 距离 next_maintenance_date 不足 14 天（临近）
    """

    def __init__(self):
        self.warning_days = 14
        self.soon_days = 7

    def check_maintenance_schedule(self, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """
        检查所有设备的维护计划，返回需要提醒的设备列表。
        
        规则：
        1. 有 next_maintenance_date 的设备，检查是否过期或即将到期
        2. 有 maintenance_interval_days + last_maintenance 但没有 next_maintenance 的设备，
           自动计算并设置 next_maintenance
        3. 创建对应的告警通知
        """
        should_close_db = db is None
        if db is None:
            db = SessionLocal()

        try:
            results = []
            today = today_in_biz_tz()

            # 获取所有设备（只检查有维护计划的）
            devices = db.query(Device).all()

            # 批量预查询所有活跃的维护告警（避免N+1）
            alarm_map = self._load_maintenance_alarms(db)

            for device in devices:
                try:
                    record = self._check_single_device(db, device, today, alarm_map)
                    if record:
                        results.append(record)
                except Exception as e:
                    logger.error("检查设备 %s 维护计划失败: %s", device.id, e)
                    continue

            if should_close_db:
                db.commit()

            logger.info(
                "[维护计划检查] 完成: 发现 %d 个需关注的设备 (overdue=%d, soon=%d, warning=%d)",
                len(results),
                sum(1 for r in results if r["status"] == "overdue"),
                sum(1 for r in results if r["status"] == "soon"),
                sum(1 for r in results if r["status"] == "warning"),
            )
            return results

        except Exception as e:
            if should_close_db:
                db.rollback()
            logger.error("[维护计划检查] 失败: %s", e, exc_info=True)
            raise
        finally:
            if should_close_db:
                db.close()

    def _load_maintenance_alarms(self, db: Session) -> dict:
        """批量加载所有活跃的维护告警，按 (device_id, alarm_type) 索引"""
        alarm_types = [f"maintenance_{s}" for s in ["overdue", "soon", "warning"]]
        alarms = db.query(Alarm).filter(
            Alarm.alarm_type.in_(alarm_types),
            Alarm.status.in_([AlarmStatus.ACTIVE, AlarmStatus.ACKNOWLEDGED]),
        ).all()
        alarm_map = {}
        for a in alarms:
            alarm_map[(a.device_id, a.alarm_type)] = a
        return alarm_map

    def _check_single_device(
        self, db: Session, device: Device, today: date,
        alarm_map: dict = None
    ) -> Optional[Dict[str, Any]]:
        """检查单个设备的维护计划"""
        # 自动计算 next_maintenance（如果没有设置但有周期和最后维护日期）
        if device.next_maintenance is None:
            if device.last_maintenance and device.maintenance_interval_days:
                device.next_maintenance = (
                    device.last_maintenance + timedelta(days=device.maintenance_interval_days)
                )
                logger.debug(
                    "自动设置设备 %s next_maintenance: %s",
                    device.id, device.next_maintenance,
                )
            else:
                return None  # 没有维护计划信息，跳过

        next_date = device.next_maintenance
        days_until = (next_date - today).days

        # 判断状态
        if days_until < 0:
            status = "overdue"
            level = AlarmLevel.WARNING
            description = (
                f"设备「{device.name}」维护已逾期 {-days_until} 天！"
                f"上次维护: {device.last_maintenance or '无记录'}，"
                f"计划维护日期: {next_date}，"
                f"请尽快安排维护。"
            )
        elif days_until <= self.soon_days:
            status = "soon"
            level = AlarmLevel.WARNING
            description = (
                f"设备「{device.name}」维护即将到期（距离 {next_date} 还有 {days_until} 天），"
                f"请安排维护计划。"
            )
        elif days_until <= self.warning_days:
            status = "warning"
            level = AlarmLevel.INFO
            description = (
                f"设备「{device.name}」维护临近（距离 {next_date} 还有 {days_until} 天），"
                f"请提前准备。"
            )
        else:
            return None  # 正常，不需要提醒

        # 检查是否已有相同类型的活跃告警（从预加载的 map 中查找，避免 N+1）
        alarm_type = f"maintenance_{status}"
        existing = alarm_map.get((device.id, alarm_type)) if alarm_map else None

        if not existing and alarm_map is None:
            # 兼容旧调用（无 alarm_map 时回退到逐个查询）
            existing = db.query(Alarm).filter(
                Alarm.device_id == device.id,
                Alarm.alarm_type == alarm_type,
                Alarm.status.in_([AlarmStatus.ACTIVE, AlarmStatus.ACKNOWLEDGED]),
            ).first()

        if existing:
            logger.debug("设备 %s 已有 %s 告警，跳过", device.id, status)
            return {
                "device_id": device.id,
                "name": device.name,
                "status": status,
                "days_until": days_until,
                "next_maintenance": str(next_date),
                "existing_alarm": True,
            }

        # 生成告警
        try:
            alarm = Alarm(
                device_id=device.id,
                station_id=device.station_id,
                alarm_type=alarm_type,
                level=level,
                content=description,
                status=AlarmStatus.ACTIVE,
            )
            db.add(alarm)
        except Exception as e:
            db.rollback()
            logger.error("创建设备 %s 维护提醒告警失败: %s", device.id, e)
            return None

        logger.info("创建维护提醒告警: device=%s, status=%s, days=%d", device.id, status, days_until)

        return {
            "device_id": device.id,
            "name": device.name,
            "status": status,
            "days_until": days_until,
            "next_maintenance": str(next_date),
            "alarm_level": level.value if level else None,
            "alarm_id": alarm.id,
        }

    def get_upcoming_maintenance(
        self, db: Optional[Session] = None,
        days_ahead: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        获取未来 N 天内需要维护的设备列表。
        不做告警判断，仅做查询统计。
        """
        should_close_db = db is None
        if db is None:
            db = SessionLocal()

        try:
            today = today_in_biz_tz()
            future_date = today + timedelta(days=days_ahead)

            devices = db.query(Device).filter(
                Device.next_maintenance.isnot(None),
                Device.next_maintenance <= future_date,
            ).order_by(Device.next_maintenance.asc()).all()

            results = []
            for device in devices:
                days_until = (device.next_maintenance - today).days
                status = (
                    "overdue" if days_until < 0
                    else "soon" if days_until <= self.soon_days
                    else "warning" if days_until <= self.warning_days
                    else "upcoming"
                )
                results.append({
                    "device_id": device.id,
                    "name": device.name,
                    "sn": device.sn,
                    "station_id": device.station_id,
                    "type": device.type.value if device.type else None,
                    "maintenance_interval_days": device.maintenance_interval_days,
                    "last_maintenance": str(device.last_maintenance) if device.last_maintenance else None,
                    "next_maintenance": str(device.next_maintenance),
                    "days_until": days_until,
                    "status": status,
                })

            return results

        finally:
            if should_close_db:
                db.close()


# 全局实例
maintenance_schedule_checker = MaintenanceScheduleChecker()
