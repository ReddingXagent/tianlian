"""
设备数据服务 - 统一的数据查询接口

提供实时数据、历史数据、健康数据的查询接口。
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.telemetry import Telemetry
from app.gateway import get_adapter
from app.parsers import create_pipeline

logger = logging.getLogger(__name__)


class DeviceDataService:
    """
    设备数据服务
    
    功能：
        - 实时数据采集
        - 历史数据查询
        - 健康状态查询
        - 数据统计分析
    
    Example:
        >>> service = DeviceDataService(db)
        >>> realtime_data = await service.get_realtime_data(device_id=1)
        >>> history_data = service.get_history_data(device_id=1, hours=24)
    """
    
    def __init__(self, db: Session):
        """
        初始化设备数据服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
    
    async def get_realtime_data(self, device_id: int) -> Dict[str, Any]:
        """
        获取实时数据
        
        Args:
            device_id: 设备ID
            
        Returns:
            Dict[str, Any]: 实时数据
            
        Note:
            通过协议适配器实时采集数据
        """
        try:
            # 1. 查询设备
            device = self.db.query(Device).filter(Device.id == device_id).first()

            if not device:
                logger.error("设备不存在: ID=%s", device_id)
                return {"error": "设备不存在"}

            # 2. 获取适配器
            device_type = device.device_type
            config = device.comm_config or {}

            # 补充默认配置
            if device.protocol_type:
                config["protocol"] = device.protocol_type.value
            if device.device_address:
                config["device_address"] = device.device_address

            adapter = get_adapter(device_type, config)

            if not adapter:
                logger.error("无法获取适配器: device_type=%s", device_type)
                return {"error": "适配器不可用"}

            # 3. 采集数据
            raw_data = await adapter.read_data(config.get("device_address", 1))

            # 4. 解析数据
            pipeline = create_pipeline(device_type, config.get("protocol", "unknown"))
            parsed_data = await pipeline.execute(raw_data)

            logger.info("实时数据采集成功: 设备%s", device_id)
            return parsed_data
        except Exception:
            logger.exception("实时数据采集失败 device_id=%s", device_id)
            return {"error": "服务内部错误，请稍后重试"}
    
    def get_history_data(
        self,
        device_id: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        获取历史数据
        
        Args:
            device_id: 设备ID
            start_time: 开始时间（可选）
            end_time: 结束时间（可选）
            hours: 时间范围（小时，默认24）
            
        Returns:
            List[Dict[str, Any]]: 历史数据列表
            
        Note:
            从数据库查询历史遥测数据
        """
        try:
            # 计算时间范围
            if not end_time:
                end_time = datetime.now(timezone.utc)

            if not start_time:
                start_time = end_time - timedelta(hours=hours)

            # 查询遥测数据
            telemetry_records = (
                self.db.query(Telemetry)
                .filter(
                    Telemetry.device_id == device_id,
                    Telemetry.timestamp >= start_time,
                    Telemetry.timestamp <= end_time
                )
                .order_by(Telemetry.timestamp.desc())
                .all()
            )

            # 转换为字典列表
            history_data = [
                {
                    "timestamp": record.timestamp,
                    "data": record.data,
                    "device_id": record.device_id,
                }
                for record in telemetry_records
            ]

            logger.info("查询历史数据: 设备%s, %d 条记录", device_id, len(history_data))
            return history_data
        except Exception:
            logger.exception("查询历史数据失败 device_id=%s", device_id)
            return []
    
    def get_health_status(self, device_id: int) -> Dict[str, Any]:
        """
        获取健康状态
        
        Args:
            device_id: 设备ID
            
        Returns:
            Dict[str, Any]: 健康状态信息
            
        Note:
            包含健康度评分、最后心跳时间、故障状态等
        """
        try:
            # 查询设备
            device = self.db.query(Device).filter(Device.id == device_id).first()

            if not device:
                return {"error": "设备不存在"}

            # 构建健康状态
            health_status = {
                "device_id": device_id,
                "device_name": device.name,
                "status": device.status.value if device.status else "unknown",
                "health_score": device.health_score or 100.0,
                "last_heartbeat": device.last_heartbeat,
                "total_run_hours": device.total_run_hours or 0,
                "is_online": device.status == "online" if device.status else False,
                "timestamp": datetime.now(timezone.utc),
            }

            return health_status
        except Exception:
            logger.exception("查询健康状态失败 device_id=%s", device_id)
            return {}
    
    def get_statistics(
        self,
        device_id: int,
        metric: str = "power",
        aggregation: str = "avg",
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        获取统计数据
        
        Args:
            device_id: 设备ID
            metric: 统计指标（power/voltage/current/temperature）
            aggregation: 聚合方式（avg/max/min/sum）
            hours: 时间范围（小时）
            
        Returns:
            Dict[str, Any]: 统计结果
            
        Note:
            对历史数据进行统计分析
        """
        try:
            # 获取历史数据
            history_data = self.get_history_data(device_id, hours=hours)

            if not history_data:
                return {"error": "无历史数据"}

            # 提取指标值
            values = []
            for record in history_data:
                data = record.get("data", {})
                # 跳过 None: 遥测缺失值(传感器离线/字段未上报)不能参与聚合,
                # 否则 sum([10, None, 30]) 抛 TypeError
                if metric in data and data[metric] is not None:
                    values.append(data[metric])

            if not values:
                return {"error": f"无指标数据: {metric}"}

            # 计算统计值
            if aggregation == "avg":
                result = sum(values) / len(values)
            elif aggregation == "max":
                result = max(values)
            elif aggregation == "min":
                result = min(values)
            elif aggregation == "sum":
                result = sum(values)
            else:
                return {"error": f"未知的聚合方式: {aggregation}"}

            statistics = {
                "device_id": device_id,
                "metric": metric,
                "aggregation": aggregation,
                "value": result,
                "count": len(values),
                "hours": hours,
                "timestamp": datetime.now(timezone.utc),
            }

            return statistics
        except Exception:
            logger.exception("查询统计数据失败 device_id=%s", device_id)
            return {}