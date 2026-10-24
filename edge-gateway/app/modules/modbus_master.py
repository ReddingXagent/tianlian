"""
Module 3: Modbus TCP Master
- Modbus TCP 主站
- 采集设备数据（逆变器、电表、PCS等）
- 支持多设备并发轮询
"""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
from app.core.config import config, ModbusDevice
from app.core.logging import logger


class ModbusDeviceConnection:
    """Modbus 设备连接"""

    def __init__(self, device_config: ModbusDevice):
        self.config = device_config
        self.client: Optional[AsyncModbusTcpClient] = None
        self.connected: bool = False
        self.last_read: Optional[datetime] = None
        self.last_data: Dict[str, Any] = {}
        self.error_count: int = 0

    async def connect(self) -> bool:
        """连接设备"""
        try:
            self.client = AsyncModbusTcpClient(
                host=self.config.host,
                port=self.config.port,
                timeout=config.modbus.timeout_seconds,
            )
            self.connected = await self.client.connect()
            if self.connected:
                logger.info(f"Modbus 设备已连接 [{self.config.name}] {self.config.host}:{self.config.port}")
            else:
                logger.warning(f"Modbus 设备连接失败 [{self.config.name}] {self.config.host}:{self.config.port}")
            return self.connected
        except Exception as e:
            logger.error(f"Modbus 设备连接异常 [{self.config.name}]: {e}")
            self.connected = False
            return False

    async def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.close()
            self.connected = False
            logger.info(f"Modbus 设备已断开 [{self.config.name}]")

    async def read_holding_registers(
        self, address: int, count: int, slave: Optional[int] = None
    ) -> Optional[List[int]]:
        """读取保持寄存器"""
        if not self.connected or not self.client:
            return None

        unit = slave or self.config.unit_id
        try:
            result = await self.client.read_holding_registers(
                address=address, count=count, slave=unit
            )
            if result.isError():
                logger.warning(f"读取寄存器失败 [{self.config.name}] addr={address}: {result}")
                self.error_count += 1
                return None
            self.error_count = 0
            return result.registers
        except ModbusException as e:
            logger.error(f"Modbus 异常 [{self.config.name}]: {e}")
            self.error_count += 1
            return None
        except Exception as e:
            logger.error(f"读取寄存器异常 [{self.config.name}]: {e}")
            self.error_count += 1
            return None

    async def read_input_registers(
        self, address: int, count: int, slave: Optional[int] = None
    ) -> Optional[List[int]]:
        """读取输入寄存器"""
        if not self.connected or not self.client:
            return None

        unit = slave or self.config.unit_id
        try:
            result = await self.client.read_input_registers(
                address=address, count=count, slave=unit
            )
            if result.isError():
                logger.warning(f"读取输入寄存器失败 [{self.config.name}] addr={address}")
                self.error_count += 1
                return None
            self.error_count = 0
            return result.registers
        except Exception as e:
            logger.error(f"读取输入寄存器异常 [{self.config.name}]: {e}")
            self.error_count += 1
            return None

    async def read_coils(
        self, address: int, count: int, slave: Optional[int] = None
    ) -> Optional[List[bool]]:
        """读取线圈"""
        if not self.connected or not self.client:
            return None

        unit = slave or self.config.unit_id
        try:
            result = await self.client.read_coils(
                address=address, count=count, slave=unit
            )
            if result.isError():
                self.error_count += 1
                return None
            self.error_count = 0
            return result.bits
        except Exception as e:
            logger.error(f"读取线圈异常 [{self.config.name}]: {e}")
            self.error_count += 1
            return None


class ModbusMaster:
    """Modbus TCP 主站管理器"""

    def __init__(self):
        self.modbus_config = config.modbus
        self._devices: Dict[str, ModbusDeviceConnection] = {}
        self._poll_task: Optional[asyncio.Task] = None
        self._data_queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    @property
    def data_queue(self) -> asyncio.Queue:
        """数据队列，供遥测模块消费"""
        return self._data_queue

    @property
    def devices(self) -> Dict[str, ModbusDeviceConnection]:
        return self._devices

    async def connect_all(self):
        """连接所有设备"""
        for device_config in self.modbus_config.devices:
            conn = ModbusDeviceConnection(device_config)
            self._devices[device_config.name] = conn
            await conn.connect()

        connected = sum(1 for d in self._devices.values() if d.connected)
        logger.info(f"Modbus 设备连接完成: {connected}/{len(self._devices)} 在线")

    async def _poll_device(self, device: ModbusDeviceConnection) -> Dict[str, Any]:
        """轮询单个设备"""
        data = {
            "device_name": device.config.name,
            "device_id": device.config.device_id,
            "host": device.config.host,
            "timestamp": datetime.utcnow().isoformat(),
            "connected": device.connected,
            "registers": {},
            "error_count": device.error_count,
        }

        if not device.connected:
            # 尝试重连
            if device.error_count < config.modbus.retry_count:
                await device.connect()
            return data

        # 读取常用寄存器区域
        # 保持寄存器 0-49: 运行参数
        hr = await device.read_holding_registers(0, 50)
        if hr:
            data["registers"]["holding_0_49"] = hr

        # 输入寄存器 0-49: 测量值
        ir = await device.read_input_registers(0, 50)
        if ir:
            data["registers"]["input_0_49"] = ir

        # 线圈 0-15: 状态位
        coils = await device.read_coils(0, 16)
        if coils:
            data["registers"]["coils_0_15"] = [int(c) for c in coils]

        device.last_read = datetime.utcnow()
        device.last_data = data

        return data

    async def _poll_loop(self):
        """轮询循环"""
        logger.info(
            f"Modbus 轮询循环已启动 [间隔: {self.modbus_config.poll_interval_seconds}s]"
        )
        while self._running:
            try:
                tasks = []
                for device in self._devices.values():
                    tasks.append(self._poll_device(device))

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"轮询异常: {result}")
                    elif result:
                        # 推送到数据队列
                        await self._data_queue.put(result)

                await asyncio.sleep(self.modbus_config.poll_interval_seconds)

            except asyncio.CancelledError:
                logger.info("Modbus 轮询循环已停止")
                break
            except Exception as e:
                logger.error(f"Modbus 轮询循环异常: {e}")
                await asyncio.sleep(1)

    async def start(self):
        """启动 Modbus 主站"""
        if not self.modbus_config.enabled:
            logger.info("Modbus 已禁用")
            return

        self._running = True
        await self.connect_all()
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        """停止 Modbus 主站"""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        # 断开所有设备
        for device in self._devices.values():
            await device.disconnect()
        self._devices.clear()
        logger.info("Modbus 主站已停止")

    async def get_device_status(self) -> List[Dict[str, Any]]:
        """获取所有设备状态"""
        status = []
        for device in self._devices.values():
            status.append({
                "name": device.config.name,
                "host": device.config.host,
                "connected": device.connected,
                "error_count": device.error_count,
                "last_read": device.last_read.isoformat() if device.last_read else None,
                "last_data": device.last_data,
            })
        return status


# 全局 Modbus 主站
modbus_master = ModbusMaster()
