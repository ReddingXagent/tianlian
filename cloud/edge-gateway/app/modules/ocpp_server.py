"""
Module 2: OCPP WebSocket Server
- WebSocket OCPP 协议服务端
- 与充电桩通信（OCPP 1.6J）
- 支持 BootNotification, Heartbeat, StatusNotification 等
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Optional, Set
import websockets
from websockets.server import WebSocketServerProtocol
from app.core.config import config
from app.core.logging import logger
from app.modules.transaction_store import transaction_store


class OCPPChargePoint:
    """OCPP 充电桩连接"""

    def __init__(self, charge_point_id: str, websocket: WebSocketServerProtocol):
        self.charge_point_id = charge_point_id
        self.websocket = websocket
        self.connected_at = datetime.utcnow()
        self.last_heartbeat: Optional[datetime] = None
        self.vendor: Optional[str] = None
        self.model: Optional[str] = None
        self.status: str = "Available"
        self._message_id = 0

    def next_message_id(self) -> str:
        self._message_id += 1
        return str(self._message_id)

    def to_dict(self) -> dict:
        return {
            "charge_point_id": self.charge_point_id,
            "vendor": self.vendor,
            "model": self.model,
            "status": self.status,
            "connected_at": self.connected_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
        }


class OCPPServer:
    """OCPP WebSocket 服务端"""

    def __init__(self):
        self.ocpp_config = config.ocpp
        self._server: Optional[websockets.WebSocketServer] = None
        self._connections: Dict[str, OCPPChargePoint] = {}
        self._running = False

    @property
    def connections(self) -> Dict[str, OCPPChargePoint]:
        return self._connections

    async def handle_connection(self, websocket: WebSocketServerProtocol):
        """处理新的 WebSocket 连接"""
        charge_point_id = None

        try:
            async for raw_message in websocket:
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    logger.warning(f"无效的 JSON 消息: {raw_message[:200]}")
                    continue

                msg_type = message[0]  # 消息类型: 2=Request, 3=Response, 4=Error
                msg_id = message[1]
                action = message[2] if msg_type == 2 else None

                if msg_type == 2:  # CALL (Request)
                    charge_point_id = await self._handle_request(
                        websocket, charge_point_id, msg_id, action, message[3]
                    )
                elif msg_type == 3:  # CALLRESULT (Response)
                    logger.debug(f"收到 CALLRESULT [{msg_id}]")
                elif msg_type == 4:  # CALLERROR
                    logger.warning(f"收到 CALLERROR [{msg_id}]: {message[3]}")

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"充电桩连接关闭 [{charge_point_id}]")
        except Exception as e:
            logger.error(f"OCPP 连接异常: {e}")
        finally:
            if charge_point_id and charge_point_id in self._connections:
                cp = self._connections.pop(charge_point_id)
                logger.info(f"充电桩已断开 [{charge_point_id}], 连接时长: "
                           f"{(datetime.utcnow() - cp.connected_at).total_seconds():.0f}s")

    async def _handle_request(
        self,
        websocket: WebSocketServerProtocol,
        charge_point_id: Optional[str],
        msg_id: str,
        action: str,
        payload: dict,
    ) -> Optional[str]:
        """处理 OCPP 请求"""
        logger.debug(f"OCPP 请求: {action} from {charge_point_id}")

        if action == "BootNotification":
            return await self._handle_boot_notification(websocket, msg_id, payload)
        elif action == "Heartbeat":
            await self._handle_heartbeat(websocket, msg_id, charge_point_id)
        elif action == "StatusNotification":
            await self._handle_status_notification(charge_point_id, payload)
        elif action == "MeterValues":
            await self._handle_meter_values(charge_point_id, payload)
        elif action == "StartTransaction":
            await self._handle_start_transaction(websocket, msg_id, charge_point_id, payload)
        elif action == "StopTransaction":
            await self._handle_stop_transaction(websocket, msg_id, charge_point_id, payload)
        elif action == "Authorize":
            await self._handle_authorize(websocket, msg_id, payload)
        elif action == "DiagnosticsStatusNotification":
            await self._handle_diagnostics_status(charge_point_id, payload)
        elif action == "FirmwareStatusNotification":
            await self._handle_firmware_status(charge_point_id, payload)
        else:
            logger.info(f"未处理的 OCPP 动作: {action}")

        return charge_point_id

    async def _handle_boot_notification(
        self, websocket: WebSocketServerProtocol, msg_id: str, payload: dict
    ) -> str:
        """处理 BootNotification"""
        charge_point_id = payload.get("chargePointSerialNumber", payload.get("chargePointModel", "unknown"))
        vendor = payload.get("chargePointVendor", "unknown")
        model = payload.get("chargePointModel", "unknown")

        if charge_point_id in self._connections:
            # 已存在连接，替换
            old_cp = self._connections.pop(charge_point_id)
            logger.info(f"充电桩重连 [{charge_point_id}]")

        cp = OCPPChargePoint(charge_point_id, websocket)
        cp.vendor = vendor
        cp.model = model
        self._connections[charge_point_id] = cp

        # 响应 BootNotification
        response = [
            3,  # CALLRESULT
            msg_id,
            {
                "status": "Accepted",
                "currentTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "interval": self.ocpp_config.heartbeat_interval,
            },
        ]
        await websocket.send(json.dumps(response))

        logger.info(f"充电桩启动通知已接受 [{charge_point_id}] 厂商={vendor} 型号={model}")
        return charge_point_id

    async def _handle_heartbeat(
        self, websocket: WebSocketServerProtocol, msg_id: str, charge_point_id: Optional[str]
    ):
        """处理 Heartbeat"""
        response = [
            3,  # CALLRESULT
            msg_id,
            {"currentTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
        ]
        await websocket.send(json.dumps(response))

        if charge_point_id and charge_point_id in self._connections:
            self._connections[charge_point_id].last_heartbeat = datetime.utcnow()

    async def _handle_status_notification(self, charge_point_id: Optional[str], payload: dict):
        """处理 StatusNotification"""
        status = payload.get("status", "Unknown")
        connector_id = payload.get("connectorId", 0)
        error_code = payload.get("errorCode", "NoError")

        if charge_point_id and charge_point_id in self._connections:
            self._connections[charge_point_id].status = status

        logger.info(
            f"充电桩状态变更 [{charge_point_id}] "
            f"Connector={connector_id} Status={status} Error={error_code}"
        )

    async def _handle_meter_values(self, charge_point_id: Optional[str], payload: dict):
        """处理 MeterValues"""
        connector_id = payload.get("connectorId", 0)
        meter_values = payload.get("meterValue", [])

        for mv in meter_values:
            sampled_values = mv.get("sampledValue", [])
            for sv in sampled_values:
                logger.debug(
                    f"电表数据 [{charge_point_id}] Connector={connector_id} "
                    f"{sv.get('measurand', 'unknown')}={sv.get('value')} {sv.get('unit', '')}"
                )

    async def _handle_start_transaction(
        self, websocket: WebSocketServerProtocol, msg_id: str,
        charge_point_id: Optional[str], payload: dict
    ):
        """处理 StartTransaction"""
        connector_id = payload.get("connectorId", 0)
        id_tag = payload.get("idTag", "unknown")
        meter_start = payload.get("meterStart", 0)

        transaction_id = int(datetime.utcnow().timestamp())
        timestamp_start = datetime.utcnow().isoformat()

        logger.info(
            f"充电开始 [{charge_point_id}] Connector={connector_id} "
            f"IdTag={id_tag} MeterStart={meter_start}"
        )

        # 缓存 start 信息供 StopTransaction 组装 (内存 + sqlite 持久化)
        await transaction_store.record_start(
            transaction_id=transaction_id,
            charge_point_id=charge_point_id,
            connector_id=connector_id,
            id_tag=id_tag,
            meter_start=meter_start,
            timestamp_start=timestamp_start,
        )

        # 响应
        response = [
            3,  # CALLRESULT
            msg_id,
            {
                "transactionId": transaction_id,
                "idTagInfo": {"status": "Accepted"},
            },
        ]
        await websocket.send(json.dumps(response))

    async def _handle_stop_transaction(
        self, websocket: WebSocketServerProtocol, msg_id: str,
        charge_point_id: Optional[str], payload: dict
    ):
        """处理 StopTransaction"""
        transaction_id = payload.get("transactionId", 0)
        meter_stop = payload.get("meterStop", 0)
        reason = payload.get("reason", "Local")

        logger.info(
            f"充电停止 [{charge_point_id}] Transaction={transaction_id} "
            f"MeterStop={meter_stop} Reason={reason}"
        )

        # 组装完整充电会话 (查 start 缓存; 缺失不崩)
        session = await transaction_store.build_session(charge_point_id, payload)

        # 先回 Accepted, 不阻塞 OCPP 应答
        response = [
            3,  # CALLRESULT
            msg_id,
            {"idTagInfo": {"status": "Accepted"}},
        ]
        await websocket.send(json.dumps(response))

        # 再异步回传云端 (失败自动入 outbox 重传)
        asyncio.create_task(transaction_store.submit_session(session))

    async def _handle_authorize(
        self, websocket: WebSocketServerProtocol, msg_id: str, payload: dict
    ):
        """处理 Authorize"""
        id_tag = payload.get("idTag", "unknown")
        logger.info(f"授权请求 [{id_tag}]")

        response = [
            3,  # CALLRESULT
            msg_id,
            {"idTagInfo": {"status": "Accepted"}},
        ]
        await websocket.send(json.dumps(response))

    async def _handle_diagnostics_status(self, charge_point_id: Optional[str], payload: dict):
        """处理 DiagnosticsStatusNotification"""
        status = payload.get("status", "Unknown")
        logger.info(f"诊断状态 [{charge_point_id}]: {status}")

    async def _handle_firmware_status(self, charge_point_id: Optional[str], payload: dict):
        """处理 FirmwareStatusNotification"""
        status = payload.get("status", "Unknown")
        logger.info(f"固件状态 [{charge_point_id}]: {status}")

    async def send_remote_start(
        self, charge_point_id: str, id_tag: str, connector_id: int = 0
    ) -> bool:
        """远程启动充电"""
        cp = self._connections.get(charge_point_id)
        if not cp:
            logger.warning(f"充电桩不在线 [{charge_point_id}]")
            return False

        msg_id = cp.next_message_id()
        request = [
            2,  # CALL
            msg_id,
            "RemoteStartTransaction",
            {
                "connectorId": connector_id,
                "idTag": id_tag,
            },
        ]
        try:
            await cp.websocket.send(json.dumps(request))
            logger.info(f"远程启动充电 [{charge_point_id}] IdTag={id_tag}")
            return True
        except Exception as e:
            logger.error(f"远程启动失败 [{charge_point_id}]: {e}")
            return False

    async def send_remote_stop(self, charge_point_id: str, transaction_id: int) -> bool:
        """远程停止充电"""
        cp = self._connections.get(charge_point_id)
        if not cp:
            logger.warning(f"充电桩不在线 [{charge_point_id}]")
            return False

        msg_id = cp.next_message_id()
        request = [
            2,  # CALL
            msg_id,
            "RemoteStopTransaction",
            {"transactionId": transaction_id},
        ]
        try:
            await cp.websocket.send(json.dumps(request))
            logger.info(f"远程停止充电 [{charge_point_id}] Transaction={transaction_id}")
            return True
        except Exception as e:
            logger.error(f"远程停止失败 [{charge_point_id}]: {e}")
            return False

    async def send_reset(self, charge_point_id: str, reset_type: str = "Soft") -> bool:
        """发送重置命令"""
        cp = self._connections.get(charge_point_id)
        if not cp:
            logger.warning(f"充电桩不在线 [{charge_point_id}]")
            return False

        msg_id = cp.next_message_id()
        request = [
            2,  # CALL
            msg_id,
            "Reset",
            {"type": reset_type},
        ]
        try:
            await cp.websocket.send(json.dumps(request))
            logger.info(f"发送重置命令 [{charge_point_id}] Type={reset_type}")
            return True
        except Exception as e:
            logger.error(f"发送重置命令失败 [{charge_point_id}]: {e}")
            return False

    async def get_connected_charge_points(self) -> list:
        """获取已连接的充电桩列表"""
        return [cp.to_dict() for cp in self._connections.values()]

    async def start(self):
        """启动 OCPP 服务端"""
        if not self.ocpp_config.enabled:
            logger.info("OCPP 服务已禁用")
            return

        self._running = True
        self._server = await websockets.serve(
            self.handle_connection,
            self.ocpp_config.host,
            self.ocpp_config.port,
            max_size=2 ** 20,  # 1MB max message size
        )
        logger.info(
            f"OCPP WebSocket 服务已启动 [ws://{self.ocpp_config.host}:{self.ocpp_config.port}]"
        )

    async def stop(self):
        """停止 OCPP 服务端"""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # 关闭所有连接
        for cp in list(self._connections.values()):
            try:
                await cp.websocket.close()
            except Exception:
                pass
        self._connections.clear()
        logger.info("OCPP 服务已停止")


# 全局 OCPP 服务端
ocpp_server = OCPPServer()
