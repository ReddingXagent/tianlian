"""
设备控制服务 - 统一的指令下发接口

提供设备控制、参数设置、复位重启等指令下发接口。
"""
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging
import json

from sqlalchemy.orm import Session

from app.models.device import Device
from app.gateway import get_adapter

logger = logging.getLogger(__name__)


class DeviceControlService:
    """
    设备控制服务
    
    功能：
        - 控制指令下发
        - 参数设置
        - 复位重启
        - 指令记录
    
    Example:
        >>> service = DeviceControlService(db)
        >>> result = await service.send_control(device_id=1, command={"register": 1024, "value": 0x01})
    """
    
    def __init__(self, db: Session):
        """
        初始化设备控制服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
    
    async def send_control(self, device_id: int, command: Dict) -> Dict[str, Any]:
        """
        发送控制指令
        
        Args:
            device_id: 设备ID
            command: 控制指令字典
            
        Returns:
            Dict[str, Any]: 执行结果
            
        Example:
            >>> result = await service.send_control(1, {"register": 1024, "value": 0x01})
        """
        # 1. 查询设备
        device = self.db.query(Device).filter(Device.id == device_id).first()
        
        if not device:
            logger.error("设备不存在: ID=%s", device_id)
            return {"success": False, "error": "设备不存在"}
        
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
            return {"success": False, "error": "适配器不可用"}
        
        # 3. 发送指令
        try:
            success = await adapter.write_command(config.get("device_address", 1), command)
            
            if success:
                logger.info("控制指令下发成功: 设备%s, 命令%s", device_id, command)
                return {
                    "success": True,
                    "device_id": device_id,
                    "command": command,
                    "timestamp": datetime.now(timezone.utc),
                }
            else:
                logger.error("控制指令下发失败: 设备%s", device_id)
                return {"success": False, "error": "指令下发失败"}
                
        except Exception as e:
            logger.error("控制指令下发异常: %s", e)
            return {"success": False, "error": "服务内部错误，请稍后重试"}
    
    async def reset_device(self, device_id: int, reset_type: str = "soft") -> Dict[str, Any]:
        """
        复位设备
        
        Args:
            device_id: 设备ID
            reset_type: 复位类型（soft=软件复位, hard=重启）
            
        Returns:
            Dict[str, Any]: 执行结果
            
        Note:
            Modbus复位寄存器：1024
                - 0x01: 软件复位
                - 0x02: 重启
        """
        # 构建复位指令
        if reset_type == "soft":
            command = {"register": 1024, "value": 0x01, "type": "reset_soft"}
        elif reset_type == "hard":
            command = {"register": 1024, "value": 0x02, "type": "reset_hard"}
        else:
            return {"success": False, "error": f"未知的复位类型: {reset_type}"}
        
        result = await self.send_control(device_id, command)
        return result
    
    async def set_parameter(
        self,
        device_id: int,
        parameter: str,
        value: Any
    ) -> Dict[str, Any]:
        """
        设置参数
        
        Args:
            device_id: 设备ID
            parameter: 参数名称（如 "power_limit", "voltage_threshold"）
            value: 参数值
            
        Returns:
            Dict[str, Any]: 执行结果
            
        Note:
            Modbus参数寄存器：1026-1035
        """
        # 参数映射（示例）
        parameter_map = {
            "power_limit": 1026,
            "voltage_threshold_high": 1027,
            "voltage_threshold_low": 1028,
            "frequency_threshold": 1029,
        }
        
        register = parameter_map.get(parameter)
        
        if not register:
            return {"success": False, "error": f"未知的参数: {parameter}"}
        
        command = {"register": register, "value": value, "type": "param_set"}
        
        result = await self.send_control(device_id, command)
        return result
    
    async def emergency_stop(self, device_id: int) -> Dict[str, Any]:
        """
        急停（紧急停机）
        
        Args:
            device_id: 设备ID
            
        Returns:
            Dict[str, Any]: 执行结果
            
        Note:
            紧急停机指令，立即停止设备运行
        """
        # 急停寄存器：1025
        command = {"register": 1025, "value": 0x01, "type": "emergency_stop"}
        
        result = await self.send_control(device_id, command)
        
        # 更新设备状态
        if result["success"]:
            device = self.db.query(Device).filter(Device.id == device_id).first()
            if device:
                device.status = "maintenance"
                try:
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                    raise
                logger.info("设备急停成功: 设备%s", device_id)
        
        return result
    
    def get_control_history(
        self,
        device_id: int,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取控制历史
        
        Args:
            device_id: 设备ID
            limit: 记录数量限制
            
        Returns:
            List[Dict[str, Any]]: 控制历史记录
            
        Note:
            从操作日志查询控制指令历史
        """
        try:
            # 尝试从 OperationLog 模型查询
            from app.models.operation_log import OperationLog
            logs = (
                self.db.query(OperationLog)
                .filter(
                    OperationLog.resource_type == "device",
                    OperationLog.resource_id == str(device_id),
                    OperationLog.action.in_(["control", "reset", "param_set", "emergency_stop"]),
                )
                .order_by(OperationLog.created_at.desc())
                .limit(limit)
                .all()
            )

            history = []
            for log in logs:
                history.append({
                    "id": log.id,
                    "device_id": device_id,
                    "action": log.action,
                    "detail": log.detail,
                    "operator": log.operator,
                    "operator_id": log.user_id,
                    "result": log.result,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                })
            return history

        except ImportError:
            # OperationLog 模型尚不存在——回退到 Device 模型字段
            logger.warning("OperationLog 模型不可用，回退到 Device.control_log")
        except Exception as e:
            logger.error("查询控制历史失败: %s", e)

        # 兜底：查询 Device 模型的 control_log JSON 字段
        try:
            device = self.db.query(Device).filter(Device.id == device_id).first()
            if device and hasattr(device, 'control_log') and device.control_log:
                data = device.control_log
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    return data[:limit]
        except Exception as e:
            logger.warning("回退查询 control_log 失败: %s", e)

        logger.warning("控制历史查询无数据: 设备%s", device_id)
        return []