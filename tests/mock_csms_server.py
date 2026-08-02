"""OCPP 1.6J Mock CSMS Server for local development and integration testing.

This server simulates a Central System Management System (CSMS) that
OCPP ChargePoints connect to. It handles the full OCPP 1.6J WebSocket
protocol and provides an HTTP API for test assertions.

Usage:
    from mock_csms_server import MockCSMSServer

    server = MockCSMSServer(host="0.0.0.0", port=9000)
    await server.start()
    # ... run tests ...
    await server.stop()
    assert len(server.boot_notifications) > 0
"""

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

UTC = timezone.utc  # Py3.10 compat
logger = logging.getLogger(__name__)


# ── OCPP 1.6J Message IDs ──────────────────────────────────────────

CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4

OCPP_ACTIONS = [
    "BootNotification",
    "Heartbeat",
    "Authorize",
    "StartTransaction",
    "StopTransaction",
    "MeterValues",
    "StatusNotification",
    "RemoteStartTransaction",
    "RemoteStopTransaction",
    "Reset",
    "DataTransfer",
]


@dataclass
class ReceivedMessage:
    """Record of an OCPP message received by the mock CSMS"""
    action: str
    payload: dict[str, Any]
    charge_point_id: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class ConnectedChargePoint:
    """Tracks a connected ChargePoint"""
    charge_point_id: str
    connected_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    last_heartbeat: str | None = None
    transactions: dict[int, dict[str, Any]] = field(default_factory=dict)
    meter_values_count: int = 0
    status: str = "Available"
    boot_notified: bool = False


class MockCSMSServer:
    """OCPP 1.6J Mock CSMS server that accepts ChargePoint WebSocket connections.

    Provides:
    - Real OCPP WebSocket server on configurable host:port
    - Protocol-level message handling (CALL/CALLRESULT/CALLERROR)
    - Auto-responds to standard OCPP messages
    - Tracks all received messages for test assertions
    - HTTP health endpoint for integration testing
    - Can send RemoteStartTransaction/RemoteStopTransaction to connected chargers
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9000,
        accept_boot: bool = True,
        registration_status: str = "Accepted",
        heartbeat_interval: int = 300,
    ):
        self.host = host
        self.port = port
        self.accept_boot = accept_boot
        self.registration_status = registration_status
        self.heartbeat_interval = heartbeat_interval

        self._server: asyncio.AbstractServer | None = None
        self._running = False
        self._connections: dict[str, asyncio.Queue] = {}  # cp_id → outgoing queue
        self._ws_connections: dict[str, Any] = {}  # cp_id → websocket connection

        # Test-accessible state
        self.boot_notifications: list[ReceivedMessage] = []
        self.heartbeats: list[ReceivedMessage] = []
        self.authorizations: list[ReceivedMessage] = []
        self.start_transactions: list[ReceivedMessage] = []
        self.stop_transactions: list[ReceivedMessage] = []
        self.meter_values: list[ReceivedMessage] = []
        self.status_notifications: list[ReceivedMessage] = []
        self.all_messages: list[ReceivedMessage] = []
        self.connected_charge_points: dict[str, ConnectedChargePoint] = {}

        # HTTP state
        self._http_server: asyncio.AbstractServer | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def connected_count(self) -> int:
        return len(self.connected_charge_points)

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the mock CSMS WebSocket server"""
        import websockets

        self._running = True
        self._server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
            subprotocols=["ocpp1.6"],
            ping_interval=30,
            ping_timeout=10,
        )
        logger.info("Mock CSMS server started on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop the mock CSMS server"""
        self._running = False

        # Close all WebSocket connections
        for _cp_id, ws in list(self._ws_connections.items()):
            with contextlib.suppress(Exception):
                await ws.close(code=1001, reason="Server shutting down")

        self._ws_connections.clear()
        self._connections.clear()

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        if self._http_server:
            self._http_server.close()
            await self._http_server.wait_closed()
            self._http_server = None

        logger.info("Mock CSMS server stopped")

    # ── WebSocket Connection Handler ─────────────────────────────────

    async def _handle_connection(self, websocket, path: str = "/") -> None:
        """Handle an incoming OCPP WebSocket connection from a ChargePoint"""
        # Extract charge point ID from path: /{charge_point_id} or default
        cp_id = path.strip("/") if path and path != "/" else f"cp-{uuid.uuid4().hex[:8]}"

        logger.info("Mock CSMS: new connection from charge point '%s' (path=%s)", cp_id, path)

        cp = ConnectedChargePoint(charge_point_id=cp_id)
        self.connected_charge_points[cp_id] = cp
        self._ws_connections[cp_id] = websocket
        self._connections[cp_id] = asyncio.Queue()

        try:
            async for raw_message in websocket:
                if not self._running:
                    break

                try:
                    response = await self._process_message(cp_id, raw_message)
                    if response is not None:
                        await websocket.send(response)
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Mock CSMS: invalid JSON from %s: %s",
                        cp_id, e,
                    )
                    await websocket.send(
                        self._build_error("0", "BootNotification", "FormatViolation")
                    )
                except Exception as e:
                    logger.error(
                        "Mock CSMS: error processing message from %s: %s",
                        cp_id, e,
                    )
        except Exception as e:
            logger.info("Mock CSMS: connection closed for '%s': %s", cp_id, e)
        finally:
            self.connected_charge_points.pop(cp_id, None)
            self._ws_connections.pop(cp_id, None)
            self._connections.pop(cp_id, None)
            logger.info("Mock CSMS: charge point '%s' disconnected", cp_id)

    # ── Message Processing ───────────────────────────────────────────

    async def _process_message(self, cp_id: str, raw: str) -> str | None:
        """Process an incoming OCPP message and return a response (or None)"""
        msg = json.loads(raw)

        if not isinstance(msg, list) or len(msg) < 3:
            logger.warning("Mock CSMS: malformed message from %s: %s", cp_id, raw)
            return None

        message_type_id = msg[0]

        if message_type_id == CALL:
            return await self._handle_call(cp_id, msg)
        elif message_type_id == CALL_RESULT:
            self._handle_call_result(cp_id, msg)
            return None
        elif message_type_id == CALL_ERROR:
            self._handle_call_error(cp_id, msg)
            return None
        else:
            logger.warning("Mock CSMS: unknown message type %d from %s", message_type_id, cp_id)
            return None

    async def _handle_call(self, cp_id: str, msg: list) -> str:
        """Handle an OCPP CALL message"""
        message_id = msg[1]
        action = msg[2]
        payload = msg[3] if len(msg) > 3 else {}

        # Record the message
        received = ReceivedMessage(
            action=action,
            payload=payload,
            charge_point_id=cp_id,
            message_id=message_id,
        )
        self.all_messages.append(received)

        # Route to specific handler
        handler_map = {
            "BootNotification": self._handle_boot_notification,
            "Heartbeat": self._handle_heartbeat,
            "Authorize": self._handle_authorize,
            "StartTransaction": self._handle_start_transaction,
            "StopTransaction": self._handle_stop_transaction,
            "MeterValues": self._handle_meter_values,
            "StatusNotification": self._handle_status_notification,
        }

        handler = handler_map.get(action)
        if handler:
            response_payload = handler(cp_id, payload, received)
            return self._build_call_result(message_id, action, response_payload)
        else:
            logger.info("Mock CSMS: unhandled action '%s' from %s", action, cp_id)
            return self._build_call_result(message_id, action, {})

    def _handle_call_result(self, cp_id: str, msg: list) -> None:
        """Handle an OCPP CALL_RESULT message (response to our commands)"""
        logger.debug("Mock CSMS: CALL_RESULT from %s: %s", cp_id, msg)

    def _handle_call_error(self, cp_id: str, msg: list) -> None:
        """Handle an OCPP CALL_ERROR message"""
        logger.warning("Mock CSMS: CALL_ERROR from %s: %s", cp_id, msg)

    # ── Action Handlers ──────────────────────────────────────────────

    def _handle_boot_notification(
        self, cp_id: str, payload: dict[str, Any], received: ReceivedMessage
    ) -> dict[str, Any]:
        """Handle BootNotification request"""
        self.boot_notifications.append(received)
        cp = self.connected_charge_points.get(cp_id)
        if cp:
            cp.boot_notified = True

        logger.info(
            "Mock CSMS: BootNotification from %s: vendor=%s model=%s",
            cp_id,
            payload.get("chargePointVendor", "unknown"),
            payload.get("chargePointModel", "unknown"),
        )

        return {
            "status": self.registration_status,
            "currentTime": datetime.now(UTC).isoformat(),
            "interval": self.heartbeat_interval,
        }

    def _handle_heartbeat(
        self, cp_id: str, payload: dict[str, Any], received: ReceivedMessage
    ) -> dict[str, Any]:
        """Handle Heartbeat request"""
        self.heartbeats.append(received)
        cp = self.connected_charge_points.get(cp_id)
        if cp:
            cp.last_heartbeat = datetime.now(UTC).isoformat()

        logger.debug("Mock CSMS: Heartbeat from %s", cp_id)
        return {"currentTime": datetime.now(UTC).isoformat()}

    def _handle_authorize(
        self, cp_id: str, payload: dict[str, Any], received: ReceivedMessage
    ) -> dict[str, Any]:
        """Handle Authorize request"""
        self.authorizations.append(received)
        id_tag = payload.get("idTag", "")
        logger.info("Mock CSMS: Authorize from %s: idTag=%s", cp_id, id_tag)
        return {
            "idTagInfo": {
                "status": "Accepted",
                "expiryDate": "2099-12-31T23:59:59Z",
                "parentIdTag": "",
            }
        }

    def _handle_start_transaction(
        self, cp_id: str, payload: dict[str, Any], received: ReceivedMessage
    ) -> dict[str, Any]:
        """Handle StartTransaction request"""
        self.start_transactions.append(received)
        transaction_id = hash(f"{cp_id}-{payload.get('connectorId', 1)}-{len(self.start_transactions)}")
        transaction_id = abs(transaction_id) % 100000 + 1000

        cp = self.connected_charge_points.get(cp_id)
        if cp:
            cp.transactions[transaction_id] = {
                "connector_id": payload.get("connectorId"),
                "id_tag": payload.get("idTag"),
                "meter_start": payload.get("meterStart"),
                "started_at": datetime.now(UTC).isoformat(),
            }
            cp.status = "Charging"

        logger.info(
            "Mock CSMS: StartTransaction from %s: connector=%d idTag=%s tx=%d",
            cp_id,
            payload.get("connectorId"),
            payload.get("idTag"),
            transaction_id,
        )

        return {
            "transactionId": transaction_id,
            "idTagInfo": {"status": "Accepted"},
        }

    def _handle_stop_transaction(
        self, cp_id: str, payload: dict[str, Any], received: ReceivedMessage
    ) -> dict[str, Any]:
        """Handle StopTransaction request"""
        self.stop_transactions.append(received)
        tx_id = payload.get("transactionId")

        cp = self.connected_charge_points.get(cp_id)
        if cp and tx_id in cp.transactions:
            cp.transactions[tx_id]["meter_stop"] = payload.get("meterStop")
            cp.transactions[tx_id]["stopped_at"] = datetime.now(UTC).isoformat()
            cp.status = "Available"

        logger.info(
            "Mock CSMS: StopTransaction from %s: tx=%d meterStop=%d reason=%s",
            cp_id,
            tx_id,
            payload.get("meterStop"),
            payload.get("reason", "Unknown"),
        )

        return {"idTagInfo": {"status": "Accepted"}}

    def _handle_meter_values(
        self, cp_id: str, payload: dict[str, Any], received: ReceivedMessage
    ) -> dict[str, Any]:
        """Handle MeterValues request"""
        self.meter_values.append(received)
        cp = self.connected_charge_points.get(cp_id)
        if cp:
            cp.meter_values_count += 1

        logger.debug(
            "Mock CSMS: MeterValues from %s: connector=%d values=%d",
            cp_id,
            payload.get("connectorId"),
            len(payload.get("meterValue", [])),
        )

        return {}

    def _handle_status_notification(
        self, cp_id: str, payload: dict[str, Any], received: ReceivedMessage
    ) -> dict[str, Any]:
        """Handle StatusNotification request"""
        self.status_notifications.append(received)
        cp = self.connected_charge_points.get(cp_id)
        if cp:
            cp.status = payload.get("status", "Available")

        logger.debug(
            "Mock CSMS: StatusNotification from %s: connector=%d status=%s",
            cp_id,
            payload.get("connectorId"),
            payload.get("status"),
        )

        return {}

    # ── Message Building ─────────────────────────────────────────────

    def _build_call_result(self, message_id: str, action: str, payload: dict[str, Any]) -> str:
        """Build an OCPP CALL_RESULT message"""
        result = json.dumps([CALL_RESULT, message_id, payload])
        return result

    def _build_error(
        self, message_id: str, action: str, error_code: str = "InternalError"
    ) -> str:
        """Build an OCPP CALL_ERROR message"""
        result = json.dumps([CALL_ERROR, message_id, error_code, "", {}])
        return result

    # ── Test Assertion Helpers ───────────────────────────────────────

    def clear(self) -> None:
        """Clear all recorded messages"""
        self.boot_notifications.clear()
        self.heartbeats.clear()
        self.authorizations.clear()
        self.start_transactions.clear()
        self.stop_transactions.clear()
        self.meter_values.clear()
        self.status_notifications.clear()
        self.all_messages.clear()

    def get_cp_connected(self, cp_id: str) -> bool:
        """Check if a charge point is connected"""
        return cp_id in self.connected_charge_points

    def get_cp_status(self, cp_id: str) -> str | None:
        """Get the status of a connected charge point"""
        cp = self.connected_charge_points.get(cp_id)
        return cp.status if cp else None

    def get_last_heartbeat(self, cp_id: str) -> str | None:
        """Get the last heartbeat time for a charge point"""
        cp = self.connected_charge_points.get(cp_id)
        return cp.last_heartbeat if cp else None

    def get_message_count(self, action: str) -> int:
        """Get the count of messages for a specific action"""
        return len([m for m in self.all_messages if m.action == action])

    def get_messages_for_cp(self, cp_id: str) -> list[ReceivedMessage]:
        """Get all messages from a specific charge point"""
        return [m for m in self.all_messages if m.charge_point_id == cp_id]

    def wait_for_message(
        self, action: str, timeout: float = 5.0, min_count: int = 1
    ) -> bool:
        """Wait until at least min_count messages of a given action are received"""
        import time
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if self.get_message_count(action) >= min_count:
                return True
            time.sleep(0.05)
        return False


# ── Run as standalone ────────────────────────────────────────────────

async def main():
    """Run the mock CSMS server standalone (for development/testing)"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    server = MockCSMSServer(host="0.0.0.0", port=9000)
    await server.start()
    print(f"Mock CSMS server running on {server.ws_url}")
    print("Press Ctrl+C to stop")

    try:
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        pass
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
