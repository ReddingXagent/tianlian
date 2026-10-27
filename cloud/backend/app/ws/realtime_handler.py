"""
实时数据处理函数
整合 websocket.py + websocket_realtime.py 的数据查询逻辑
"""
from datetime import datetime, timezone
from typing import Optional
import random

from sqlalchemy import func

from app.core import database as _db_module
from app.models.device import Device
from app.models.alarm import Alarm
from app.models.workorder import WorkOrder, WorkOrderStatus
from app.models.station import Station
from app.services.stats_service import (
    _device_team_filters,
    _alarm_team_filters,
    _workorder_team_filters,
)


class RealtimeDataHandler:
    """实时数据处理器

    聚合查询支持团队作用域 (卡 a579f89e): team_id=None (平台管理员) 不过滤保持
    全量; 团队级用户只看本 team 数据, 过滤复用 stats_service 卡 820cf187 的
    helper, 与 HTTP /stats/* team_scope 语义一致。
    """

    def get_dashboard_stats(self, team_id: Optional[int] = None) -> dict:
        """获取Dashboard统计数据"""
        db = _db_module.SessionLocal()
        try:
            dev_filters = _device_team_filters(db, team_id)
            wo_filters = _workorder_team_filters(db, team_id)
            station_scope = [] if team_id is None else [Station.team_id == team_id]

            # 设备统计 (SQL 聚合, 避免全表加载 — 卡8035bd65)
            device_total = db.query(func.count(Device.id)).filter(*dev_filters).scalar() or 0
            device_online = (
                db.query(func.count(Device.id))
                .filter(Device.status == "online", *dev_filters).scalar() or 0
            )
            device_offline = device_total - device_online

            # 站点统计
            station_total = (
                db.query(func.count(Station.id)).filter(*station_scope).scalar() or 0
            )
            station_normal = (
                db.query(func.count(Station.id))
                .filter(Station.status == "normal", *station_scope).scalar() or 0
            )

            # 告警统计 (critical 仅在 active 集合内统计)
            alarm_active = (
                db.query(func.count(Alarm.id))
                .filter(Alarm.status == "active", *_alarm_team_filters(db, team_id)).scalar() or 0
            )
            alarm_critical = (
                db.query(func.count(Alarm.id))
                .filter(
                    Alarm.status == "active", Alarm.level == "critical",
                    *_alarm_team_filters(db, team_id),
                )
                .scalar() or 0
            )

            # 工单统计 (SQL 聚合, 各状态独立 count)
            wo_pending = (
                db.query(func.count(WorkOrder.id))
                .filter(WorkOrder.status == WorkOrderStatus.PENDING, *wo_filters).scalar() or 0
            )
            wo_processing = (
                db.query(func.count(WorkOrder.id))
                .filter(WorkOrder.status == WorkOrderStatus.PROCESSING, *wo_filters).scalar() or 0
            )
            # today_completed 口径: 当日 UTC 零点后完成 (同 get_workorder_updates today_new — 卡51cdf2e4)
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            wo_completed_today = (
                db.query(func.count(WorkOrder.id))
                .filter(
                    WorkOrder.status == WorkOrderStatus.COMPLETED,
                    WorkOrder.finish_time >= today_start,
                    *wo_filters,
                ).scalar() or 0
            )

            # 平均健康度 (过滤 NULL)
            avg_health = (
                db.query(func.avg(Device.health_score))
                .filter(Device.health_score.isnot(None), *dev_filters).scalar()
            )
            if avg_health is None:
                avg_health = 100
            
            return {
                "devices": {
                    "total": device_total,
                    "online": device_online,
                    "offline": device_offline,
                    "online_rate": round(device_online / device_total * 100, 1) if device_total > 0 else 0,
                },
                "stations": {
                    "total": station_total,
                    "normal": station_normal,
                    "rate": round(station_normal / station_total * 100, 1) if station_total > 0 else 0,
                },
                "alarms": {
                    "active": alarm_active,
                    "critical": alarm_critical,
                },
                "workorders": {
                    "pending": wo_pending,
                    "processing": wo_processing,
                    "today_completed": wo_completed_today,
                },
                "health": {
                    "average": round(avg_health, 1),
                    "trend": "stable",
                },
                "update_time": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            db.close()
    
    def get_device_status(self, team_id: Optional[int] = None) -> list:
        """获取设备实时状态"""
        db = _db_module.SessionLocal()
        try:
            devices = (
                db.query(Device)
                .filter(*_device_team_filters(db, team_id))
                .limit(50).all()
            )
            return [
                {
                    "id": d.id,
                    "name": d.name,
                    "status": d.status.value,
                    "health_score": d.health_score or 100,
                    "last_update": datetime.now(timezone.utc).isoformat(),
                }
                for d in devices
            ]
        finally:
            db.close()
    
    def get_alarm_updates(self, team_id: Optional[int] = None) -> list:
        """获取告警更新"""
        db = _db_module.SessionLocal()
        try:
            alarms = (
                db.query(Alarm)
                .filter(Alarm.status == "active", *_alarm_team_filters(db, team_id))
                .limit(20).all()
            )
            return [
                {
                    "id": a.id,
                    "device_name": a.device.name if a.device else "未知设备",
                    "message": a.content,
                    "level": a.level.value,
                    "station": a.station.name if a.station else "未知站点",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                for a in alarms
            ]
        finally:
            db.close()
    
    def get_workorder_updates(self, team_id: Optional[int] = None) -> dict:
        """获取工单更新 (SQL 聚合, 避免样本截断 — 卡8fa84627)"""
        db = _db_module.SessionLocal()
        try:
            wo_filters = _workorder_team_filters(db, team_id)
            pending = (
                db.query(func.count(WorkOrder.id))
                .filter(WorkOrder.status == WorkOrderStatus.PENDING, *wo_filters).scalar() or 0
            )
            processing = (
                db.query(func.count(WorkOrder.id))
                .filter(WorkOrder.status == WorkOrderStatus.PROCESSING, *wo_filters).scalar() or 0
            )
            completed = (
                db.query(func.count(WorkOrder.id))
                .filter(WorkOrder.status == WorkOrderStatus.COMPLETED, *wo_filters).scalar() or 0
            )
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            today_new = (
                db.query(func.count(WorkOrder.id))
                .filter(WorkOrder.create_time >= today_start, *wo_filters).scalar() or 0
            )
            return {
                "pending": pending,
                "processing": processing,
                "completed": completed,
                "today_new": today_new,
            }
        finally:
            db.close()
    
    def get_power_generation_data(self) -> dict:
        """获取发电量数据(模拟)"""
        return {
            "current": random.randint(1000, 2000),
            "today": random.randint(5000, 10000),
            "month": random.randint(200000, 300000),
            "year": random.randint(1000000, 2000000),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    def get_station_summary(self, team_id: Optional[int] = None) -> dict:
        """获取站点概览"""
        db = _db_module.SessionLocal()
        try:
            station_scope = [] if team_id is None else [Station.team_id == team_id]
            station_total = (
                db.query(func.count(Station.id)).filter(*station_scope).scalar() or 0
            )
            station_normal = (
                db.query(func.count(Station.id))
                .filter(Station.status == "normal", *station_scope).scalar() or 0
            )
            station_warning = (
                db.query(func.count(Station.id))
                .filter(Station.status == "warning", *station_scope).scalar() or 0
            )
            station_offline = (
                db.query(func.count(Station.id))
                .filter(Station.status == "offline", *station_scope).scalar() or 0
            )
            return {
                "total": station_total,
                "normal": station_normal,
                "warning": station_warning,
                "offline": station_offline,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            db.close()