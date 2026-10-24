"""
设备健康度评估服务
提供 0-100 健康度评分 + 健康/亚健康/故障三态判断
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.device import Device, DeviceHealthRecord
from app.services.health_engine import health_engine


class HealthService:
    """设备健康度评估服务"""
    
    # 三态阈值
    THRESHOLD_HEALTHY = 80      # >=80 健康
    THRESHOLD_SUBHEALTHY = 50   # 50-79 亚健康
    # <50 故障
    
    def __init__(self):
        pass

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        """安全转 int: 非数值(None/字符串等)回退 default, 不抛"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_health_status(self, score: float) -> str:
        """根据分数判断健康状态(超出 [0,100] 视为异常数据, 归最低档)"""
        if score < 0 or score > 100:
            return "faulty"
        if score >= self.THRESHOLD_HEALTHY:
            return "healthy"
        elif score >= self.THRESHOLD_SUBHEALTHY:
            return "sub_healthy"
        else:
            return "faulty"
    
    def get_health_status_display(self, score: float) -> str:
        """获取中文状态显示"""
        status = self.get_health_status(score)
        mapping = {
            "healthy": "健康",
            "sub_healthy": "亚健康",
            "faulty": "故障",
        }
        return mapping.get(status, "未知")
    
    def calculate_device_health(
        self, 
        device: Device, 
        device_data: Dict[str, Any],
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        计算设备健康度
        
        Args:
            device: 设备对象
            device_data: 设备实时数据
            db: 数据库会话（可选，用于保存记录）
        
        Returns:
            包含总分、维度分、状态、检测时间的字典
        """
        # 使用 health_engine 计算
        total_score, dimension_scores = health_engine.calculate_health_score(
            device_data, device_type=device.type.value if device.type else None
        )
        
        # 判断状态
        status = self.get_health_status(total_score)
        status_display = self.get_health_status_display(total_score)
        
        result = {
            "device_id": device.id,
            "device_code": device.code,
            "device_name": device.name,
            "device_type": device.type.value if device.type else "unknown",
            "health_score": round(total_score, 2),
            "health_status": status,
            "health_status_display": status_display,
            "dimension_scores": dimension_scores,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # 如果提供了数据库会话，更新设备并保存记录
        if db is not None:
            device.health_score = round(total_score, 2)
            device.last_health_check = datetime.now(timezone.utc)

            # 记录健康度历史 (维度分安全转 int, 容错非数值)
            record = DeviceHealthRecord(
                device_id=device.id,
                electrical_safe_score=self._safe_int(dimension_scores.get('electrical', 0)),
                thermal_score=self._safe_int(dimension_scores.get('thermal', 0)),
                comm_score=self._safe_int(dimension_scores.get('communication', 0)),
                power_quality_score=self._safe_int(dimension_scores.get('power_quality', 0)),
                mechanical_score=self._safe_int(dimension_scores.get('mechanical', 0)),
                total_score=round(total_score, 2),
            )
            try:
                db.add(record)
                db.commit()
                db.refresh(device)
            except Exception:
                # 持久化失败(约束/连接等): 回滚, 不让健康度计算整体崩溃
                db.rollback()

        return result
    
    def get_device_health(self, device_id: int, db: Session) -> Dict[str, Any]:
        """
        获取单个设备的健康度（从数据库读取最新记录或实时计算）
        
        Args:
            device_id: 设备 ID
            db: 数据库会话
        
        Returns:
            健康度详情字典
        """
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return None
        
        # 获取最新的健康度记录
        latest_record = db.query(DeviceHealthRecord).filter(
            DeviceHealthRecord.device_id == device_id
        ).order_by(DeviceHealthRecord.created_at.desc()).first()
        
        if latest_record:
            # 从历史记录构建维度分数
            dimension_scores = {
                "electrical": latest_record.electrical_safe_score,
                "thermal": latest_record.thermal_score,
                "communication": latest_record.comm_score,
                "power_quality": latest_record.power_quality_score,
                "mechanical": latest_record.mechanical_score,
            }
            total_score = latest_record.total_score
            checked_at = latest_record.created_at.isoformat() if latest_record.created_at else datetime.now(timezone.utc).isoformat()
        else:
            # 没有历史记录，使用设备当前的 health_score
            total_score = device.health_score or 100.0
            dimension_scores = {}
            checked_at = datetime.now(timezone.utc).isoformat()
        
        status = self.get_health_status(total_score)
        status_display = self.get_health_status_display(total_score)
        
        return {
            "device_id": device.id,
            "device_code": device.code,
            "device_name": device.name,
            "device_type": device.type.value if device.type else "unknown",
            "health_score": total_score,
            "health_status": status,
            "health_status_display": status_display,
            "dimension_scores": dimension_scores,
            "checked_at": checked_at,
            "last_health_check": device.last_health_check.isoformat() if device.last_health_check else None,
        }
    
    def get_all_devices_health(
        self, db: Session, limit: Optional[int] = None, offset: int = 0
    ) -> list:
        """获取所有设备的健康度概览(batch优化,避免N+1查询; 支持分页 limit/offset)"""
        query = db.query(Device)
        if limit is not None:
            query = query.limit(limit).offset(offset)
        devices = query.all()
        if not devices:
            return []

        # 批量获取每个设备的最新健康记录（一次查询替代N次查询）
        device_ids = [d.id for d in devices]
        subq = db.query(
            DeviceHealthRecord.device_id,
            func.max(DeviceHealthRecord.created_at).label('max_created_at')
        ).filter(
            DeviceHealthRecord.device_id.in_(device_ids)
        ).group_by(DeviceHealthRecord.device_id).subquery()

        # DISTINCT: 防止同 device 同 created_at 多条记录导致 JOIN 产生重复行
        latest_records = db.query(DeviceHealthRecord).join(
            subq,
            and_(
                DeviceHealthRecord.device_id == subq.c.device_id,
                DeviceHealthRecord.created_at == subq.c.max_created_at
            )
        ).distinct().all()
        records_by_device = {r.device_id: r for r in latest_records}

        results = []
        for device in devices:
            latest_record = records_by_device.get(device.id)
            if latest_record:
                total_score = latest_record.total_score
                checked_at = latest_record.created_at.isoformat() if latest_record.created_at else datetime.now(timezone.utc).isoformat()
            else:
                total_score = device.health_score or 100.0
                checked_at = datetime.now(timezone.utc).isoformat()
            
            results.append({
                "device_id": device.id,
                "device_code": device.code,
                "device_name": device.name,
                "device_type": device.type.value if device.type else "unknown",
                "health_score": total_score,
                "health_status": self.get_health_status(total_score),
                "health_status_display": self.get_health_status_display(total_score),
                "checked_at": checked_at,
                "last_health_check": device.last_health_check.isoformat() if device.last_health_check else None,
            })
        
        return results


# 单例
health_service = HealthService()