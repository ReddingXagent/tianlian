"""
Module 4: 遥测上报
- 定时采集遥测数据
- 批量上报云端
- 数据聚合与压缩
"""
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.core.config import config
from app.core.http_client import cloud_client
from app.core.logging import logger
from app.modules.modbus_master import modbus_master
from app.modules.ocpp_server import ocpp_server


class TelemetryReporter:
    """遥测数据上报器"""

    def __init__(self):
        self.telemetry_config = config.telemetry
        self.cloud_config = config.cloud
        self._report_task: Optional[asyncio.Task] = None
        self._running = False
        self._buffer: List[Dict[str, Any]] = []
        self._total_reported: int = 0
        self._total_failed: int = 0

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_reported": self._total_reported,
            "total_failed": self._total_failed,
            "buffer_size": len(self._buffer),
        }

    async def collect_modbus_telemetry(self) -> List[Dict[str, Any]]:
        """从 Modbus 数据队列收集遥测数据"""
        records = []
        queue = modbus_master.data_queue

        # 非阻塞消费队列中的所有数据
        while not queue.empty():
            try:
                raw_data = queue.get_nowait()
                telemetry = self._transform_modbus_data(raw_data)
                if telemetry:
                    records.append(telemetry)
                queue.task_done()
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error(f"处理 Modbus 数据异常: {e}")

        return records

    def _transform_modbus_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将 Modbus 原始数据转换为遥测格式"""
        if not raw_data or not raw_data.get("connected"):
            return None

        registers = raw_data.get("registers", {})
        holding = registers.get("holding_0_49", [])
        input_regs = registers.get("input_0_49", [])
        coils = registers.get("coils_0_15", [])

        telemetry = {
            "device_id": raw_data["device_id"],
            "device_name": raw_data["device_name"],
            "timestamp": raw_data["timestamp"],
            "source": "modbus",
            "data": {},
        }

        # 解析保持寄存器（运行参数）
        if len(holding) >= 10:
            telemetry["data"].update({
                "run_mode": holding[0] if len(holding) > 0 else None,
                "system_status": holding[1] if len(holding) > 1 else None,
                "power_setpoint": holding[2] if len(holding) > 2 else None,
                "voltage_setpoint": holding[3] if len(holding) > 3 else None,
            })

        # 解析输入寄存器（测量值）
        if len(input_regs) >= 10:
            telemetry["data"].update({
                "voltage_a": input_regs[0] / 10.0 if len(input_regs) > 0 else None,
                "voltage_b": input_regs[1] / 10.0 if len(input_regs) > 1 else None,
                "voltage_c": input_regs[2] / 10.0 if len(input_regs) > 2 else None,
                "current_a": input_regs[3] / 100.0 if len(input_regs) > 3 else None,
                "current_b": input_regs[4] / 100.0 if len(input_regs) > 4 else None,
                "current_c": input_regs[5] / 100.0 if len(input_regs) > 5 else None,
                "power_total": input_regs[6] / 100.0 if len(input_regs) > 6 else None,
                "frequency": input_regs[7] / 100.0 if len(input_regs) > 7 else None,
                "power_factor": input_regs[8] / 1000.0 if len(input_regs) > 8 else None,
                "temperature": input_regs[9] / 10.0 if len(input_regs) > 9 else None,
            })

        # 解析线圈（状态位）
        if len(coils) >= 8:
            telemetry["data"].update({
                "running": bool(coils[0]) if len(coils) > 0 else None,
                "fault": bool(coils[1]) if len(coils) > 1 else None,
                "warning": bool(coils[2]) if len(coils) > 2 else None,
                "grid_connected": bool(coils[3]) if len(coils) > 3 else None,
            })

        return telemetry

    async def collect_ocpp_telemetry(self) -> List[Dict[str, Any]]:
        """从 OCPP 充电桩收集遥测数据"""
        records = []
        for cp_id, cp in ocpp_server.connections.items():
            records.append({
                "device_id": cp_id,
                "device_name": f"充电桩-{cp_id}",
                "timestamp": datetime.utcnow().isoformat(),
                "source": "ocpp",
                "data": {
                    "status": cp.status,
                    "vendor": cp.vendor,
                    "model": cp.model,
                    "connected_since": cp.connected_at.isoformat(),
                    "last_heartbeat": cp.last_heartbeat.isoformat() if cp.last_heartbeat else None,
                },
            })
        return records

    async def report_batch(self, records: List[Dict[str, Any]]) -> bool:
        """批量上报遥测数据"""
        if not records:
            return True

        payload = {
            "gateway_sn": config.gateway.sn,
            "records": records,
            "timestamp": datetime.utcnow().isoformat(),
        }

        for attempt in range(1, self.telemetry_config.max_retries + 1):
            result = await cloud_client.post(
                self.cloud_config.telemetry_endpoint,
                payload,
            )
            if result:
                self._total_reported += len(records)
                logger.debug(f"遥测上报成功: {len(records)} 条")
                return True

            logger.warning(f"遥测上报失败，{attempt}/{self.telemetry_config.max_retries} 次重试...")
            await asyncio.sleep(2 ** attempt)

        self._total_failed += len(records)
        logger.error(f"遥测上报失败，{len(records)} 条数据丢失")
        return False

    async def _report_loop(self):
        """上报循环"""
        logger.info(
            f"遥测上报循环已启动 [间隔: {self.telemetry_config.report_interval_seconds}s]"
        )
        while self._running:
            try:
                await asyncio.sleep(self.telemetry_config.report_interval_seconds)

                # 收集 Modbus 遥测
                modbus_records = await self.collect_modbus_telemetry()

                # 收集 OCPP 遥测
                ocpp_records = await self.collect_ocpp_telemetry()

                # 合并
                all_records = modbus_records + ocpp_records

                if all_records:
                    # 批量上报
                    for i in range(0, len(all_records), self.telemetry_config.batch_size):
                        batch = all_records[i:i + self.telemetry_config.batch_size]
                        success = await self.report_batch(batch)
                        if not success:
                            # 上报失败，放入离线缓存
                            self._buffer.extend(batch)
                            logger.warning(f"遥测数据已缓存，待重试: {len(batch)} 条")

            except asyncio.CancelledError:
                logger.info("遥测上报循环已停止")
                break
            except Exception as e:
                logger.error(f"遥测上报循环异常: {e}")

    async def flush_buffer(self) -> List[Dict[str, Any]]:
        """刷新缓冲区（供断网续传模块调用）"""
        if not self._buffer:
            return []

        records = self._buffer[:]
        self._buffer.clear()
        return records

    async def start(self):
        """启动遥测上报"""
        self._running = True
        self._report_task = asyncio.create_task(self._report_loop())

    async def stop(self):
        """停止遥测上报"""
        self._running = False
        if self._report_task:
            self._report_task.cancel()
            try:
                await self._report_task
            except asyncio.CancelledError:
                pass
            self._report_task = None
        logger.info("遥测上报已停止")


# 全局遥测上报器
telemetry_reporter = TelemetryReporter()
