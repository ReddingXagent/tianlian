"""
网关协议兼容性测试 - Modbus/OCPP/MQTT 协议兼容 + 边缘缓存

测试内容：
    - ModbusRTUAdapter 协议兼容性（寄存器映射、批量读取、故障诊断）
    - OCPPAdapter 协议兼容性（1.6J 消息流、交易生命周期、远程控制）
    - MQTTAdapter 协议兼容性（TLS/重连、故障等级、回调）
    - EdgeCache 边缘缓存（TTL、LRU、批量操作、统计）
    - 协议互操作性（注册中心自动发现、跨协议路由）
    - 向后兼容性（ProtocolAdapter 别名、旧测试仍通过）

Author: TianLian V3 Team
"""
import pytest
import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.gateway import (
    DeviceAdapter,
    ProtocolAdapter,
    ModbusRTUAdapter,
    MQTTAdapter,
    OCPPAdapter,
    RESTAdapter,
    ProtocolRegistry,
    get_registry,
    register_protocol,
    get_adapter,
    TelemetryPoint,
    PointType,
    RegisterMap,
    EdgeCache,
    get_edge_cache,
    reset_edge_caches,
)


# ====================================================================
# ModbusRTU 协议兼容性测试
# ====================================================================

class TestModbusProtocolCompatibility:
    """Modbus-RTU 协议兼容性测试"""

    # ── 初始化兼容性 ──

    def test_init_with_all_params(self):
        """测试完整参数初始化"""
        adapter = ModbusRTUAdapter(
            port="/dev/ttyUSB1",
            baudrate=19200,
            databits=8,
            parity="even",
            stopbits=2,
            timeout_ms=5000,
            retry_count=3,
        )
        assert adapter.port == "/dev/ttyUSB1"
        assert adapter.baudrate == 19200
        assert adapter.databits == 8
        assert adapter.parity == "even"
        assert adapter.stopbits == 2
        assert adapter.timeout_ms == 5000
        assert adapter.retry_count == 3

    def test_init_with_minimal_params(self):
        """测试最小参数初始化（默认值）"""
        adapter = ModbusRTUAdapter()
        assert adapter.port == "/dev/ttyUSB0"
        assert adapter.baudrate == 9600
        assert adapter.databits == 8
        assert adapter.parity == "none"
        assert adapter.stopbits == 1
        assert adapter.timeout_ms == 3000
        assert adapter.retry_count == 2

    # ── 寄存器映射兼容性 ──

    def test_grid_register_map_structure(self):
        """测试电网侧寄存器映射结构"""
        adapter = ModbusRTUAdapter()
        grid_map = adapter.register_maps["grid"]
        assert grid_map.description == "电网侧遥测"
        assert len(grid_map.points) == 11
        assert grid_map.points[0].name == "grid_voltage_a"
        assert grid_map.points[-1].name == "grid_power_total"

    def test_battery_register_map_structure(self):
        """测试电池侧寄存器映射结构"""
        adapter = ModbusRTUAdapter()
        battery_map = adapter.register_maps["battery"]
        assert battery_map.description == "电池侧遥测"
        assert len(battery_map.points) == 5
        assert any(p.name == "battery_soc" for p in battery_map.points)
        assert any(p.name == "battery_soh" for p in battery_map.points)

    def test_pv_register_map_structure(self):
        """测试光伏侧寄存器映射结构"""
        adapter = ModbusRTUAdapter()
        pv_map = adapter.register_maps["pv"]
        assert pv_map.description == "光伏侧遥测"
        assert len(pv_map.points) == 6
        assert any(p.name == "pv1_power" for p in pv_map.points)
        assert any(p.name == "pv2_power" for p in pv_map.points)

    def test_temperature_register_map_structure(self):
        """测试温度寄存器映射结构"""
        adapter = ModbusRTUAdapter()
        temp_map = adapter.register_maps["temperature"]
        assert temp_map.description == "温度遥测"
        assert len(temp_map.points) == 2
        assert any(p.name == "internal_temperature" for p in temp_map.points)

    def test_register_map_telemetry_sync(self):
        """测试寄存器映射同步到遥测点"""
        adapter = ModbusRTUAdapter()
        # 所有寄存器映射的遥测点应同步到 telemetry_points
        total_points = sum(len(rm.points) for rm in adapter.register_maps.values())
        assert len(adapter.telemetry_points) == total_points

    def test_register_map_address_range_calculation(self):
        """测试地址范围计算"""
        points = [
            TelemetryPoint("v1", 10, scale=1.0),
            TelemetryPoint("v2", 25, scale=1.0),
        ]
        reg_map = RegisterMap(points=points, description="test")
        start, count = reg_map.get_address_range()
        assert start == 10
        assert count == 16  # 25+1-10

    def test_register_map_empty(self):
        """测试空寄存器映射"""
        reg_map = RegisterMap(points=[], description="empty")
        start, count = reg_map.get_address_range()
        assert start == 0
        assert count == 0
        assert reg_map.get_contiguous_groups() == []

    def test_register_map_single_point(self):
        """测试单点寄存器映射"""
        points = [TelemetryPoint("single", 42, scale=1.0)]
        reg_map = RegisterMap(points=points, description="single")
        start, count = reg_map.get_address_range()
        assert start == 42
        assert count == 1
        groups = reg_map.get_contiguous_groups()
        assert len(groups) == 1
        assert len(groups[0]) == 1

    def test_register_map_contiguous_groups_with_gap(self):
        """测试有间隔的连续地址分组"""
        points = [
            TelemetryPoint("a", 0, scale=1.0),
            TelemetryPoint("b", 1, scale=1.0),
            TelemetryPoint("c", 2, scale=1.0),
            TelemetryPoint("d", 50, scale=1.0),  # 大间隔
            TelemetryPoint("e", 51, scale=1.0),
        ]
        reg_map = RegisterMap(points=points, description="gapped")
        groups = reg_map.get_contiguous_groups()
        assert len(groups) == 2
        assert len(groups[0]) == 3  # a, b, c
        assert len(groups[1]) == 2  # d, e

    # ── 数据解析兼容性 ──

    def test_parse_voltage_typical(self):
        """测试典型电压值解析"""
        adapter = ModbusRTUAdapter()
        assert adapter._parse_voltage(2205) == 220.5
        assert adapter._parse_voltage(3800) == 380.0
        assert adapter._parse_voltage(0) == 0.0

    def test_parse_current_typical(self):
        """测试典型电流值解析"""
        adapter = ModbusRTUAdapter()
        assert adapter._parse_current(500) == 5.0
        assert adapter._parse_current(1500) == 15.0
        assert adapter._parse_current(0) == 0.0

    def test_parse_power_typical(self):
        """测试典型功率值解析"""
        adapter = ModbusRTUAdapter()
        assert adapter._parse_power(1000) == 100.0
        assert adapter._parse_power(5000) == 500.0

    def test_parse_frequency_typical(self):
        """测试典型频率值解析"""
        adapter = ModbusRTUAdapter()
        assert adapter._parse_frequency(5000) == 50.0
        assert adapter._parse_frequency(6000) == 60.0

    # ── 功能码常量 ──

    def test_function_codes(self):
        """测试 Modbus 功能码常量"""
        assert ModbusRTUAdapter.FC_READ_DISCRETE == 0x02
        assert ModbusRTUAdapter.FC_READ_HOLDING == 0x03
        assert ModbusRTUAdapter.FC_READ_INPUT == 0x04
        assert ModbusRTUAdapter.FC_WRITE_SINGLE == 0x06
        assert ModbusRTUAdapter.FC_WRITE_MULTIPLE == 0x10

    # ── 生命周期兼容性 ──

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """测试完整生命周期"""
        adapter = ModbusRTUAdapter()
        assert not adapter.is_initialized()
        assert not adapter.is_connected()

        # init -> connect -> read -> write -> disconnect -> shutdown
        await adapter.initialize()
        assert adapter.is_initialized()

        await adapter.connect()
        assert adapter.is_connected()

        data = await adapter.read_data(1)
        assert "timestamp" in data

        result = await adapter.write_command(1, {"register": 1024, "value": 0x01})
        assert result is True

        await adapter.disconnect()
        assert not adapter.is_connected()

        await adapter.shutdown()
        assert not adapter.is_initialized()

    @pytest.mark.asyncio
    async def test_reset_cycle(self):
        """测试重置周期"""
        adapter = ModbusRTUAdapter()
        await adapter.initialize()
        await adapter.connect()

        result = await adapter.reset()
        assert result is True
        assert adapter.is_connected()
        assert adapter.is_initialized()

    # ── 遥测点管理 ──

    def test_register_telemetry_points(self):
        """测试动态注册遥测点"""
        adapter = ModbusRTUAdapter()
        initial_count = len(adapter.telemetry_points)

        new_points = [
            TelemetryPoint("custom_voltage", 500, PointType.VOLTAGE, 0.1, "V"),
            TelemetryPoint("custom_current", 501, PointType.CURRENT, 0.01, "A"),
        ]
        adapter.register_telemetry_points(new_points)

        assert len(adapter.telemetry_points) == initial_count + 2
        assert "custom_voltage" in adapter.telemetry_points

    def test_parse_telemetry_value_with_signed(self):
        """测试有符号遥测值解析"""
        adapter = ModbusRTUAdapter()
        adapter.register_telemetry_points([
            TelemetryPoint("signed_val", 0, scale=0.1, is_signed=True),
        ])
        # 0xFFFF = -1, -1 * 0.1 = -0.1
        value = adapter.parse_telemetry_value("signed_val", 0xFFFF)
        assert value == -0.1


# ====================================================================
# OCPP 1.6J 协议兼容性测试
# ====================================================================

class TestOCPPProtocolCompatibility:
    """OCPP 1.6J 协议兼容性测试"""

    # ── 消息类型常量 ──

    def test_message_type_constants(self):
        """测试 OCPP 消息类型常量"""
        from app.gateway.ocpp import OCPPMessageType
        assert OCPPMessageType.CALL == 2
        assert OCPPMessageType.CALL_RESULT == 3
        assert OCPPMessageType.CALL_ERROR == 4

    def test_action_constants(self):
        """测试 OCPP 动作常量"""
        from app.gateway.ocpp import OCPPAction
        assert OCPPAction.BOOT_NOTIFICATION == "BootNotification"
        assert OCPPAction.HEARTBEAT == "Heartbeat"
        assert OCPPAction.AUTHORIZE == "Authorize"
        assert OCPPAction.START_TRANSACTION == "StartTransaction"
        assert OCPPAction.STOP_TRANSACTION == "StopTransaction"
        assert OCPPAction.METER_VALUES == "MeterValues"
        assert OCPPAction.STATUS_NOTIFICATION == "StatusNotification"

    def test_charge_point_status_constants(self):
        """测试充电桩状态常量"""
        from app.gateway.ocpp import ChargePointStatus
        assert ChargePointStatus.AVAILABLE == "Available"
        assert ChargePointStatus.CHARGING == "Charging"
        assert ChargePointStatus.FAULTED == "Faulted"

    def test_registration_status_constants(self):
        """测试注册状态常量"""
        from app.gateway.ocpp import RegistrationStatus
        assert RegistrationStatus.ACCEPTED == "Accepted"
        assert RegistrationStatus.PENDING == "Pending"
        assert RegistrationStatus.REJECTED == "Rejected"

    # ── 初始化兼容性 ──

    def test_init_with_full_params(self):
        """测试完整参数初始化"""
        adapter = OCPPAdapter(
            endpoint="wss://csms.example.com/ocpp/1.6",
            charge_point_id="CP-TEST-001",
            auth_token="token-abc123",
            heartbeat_interval=120,
            reconnect_enabled=True,
            max_reconnect_attempts=5,
            base_reconnect_delay=2.0,
        )
        assert adapter.charge_point_id == "CP-TEST-001"
        assert adapter.heartbeat_interval == 120
        assert adapter.reconnect_enabled is True
        assert adapter.max_reconnect_attempts == 5

    def test_init_defaults(self):
        """测试默认初始化参数"""
        adapter = OCPPAdapter()
        assert adapter.charge_point_id == "CP001"
        assert adapter.heartbeat_interval == 60
        assert adapter.reconnect_enabled is True
        assert adapter.max_reconnect_attempts == 10

    # ── 消息流兼容性 ──

    @pytest.mark.asyncio
    async def test_full_charging_session(self):
        """测试完整充电会话流程"""
        adapter = OCPPAdapter(charge_point_id="CP-TEST")
        await adapter.initialize()
        await adapter.connect()

        # 1. 已注册
        assert adapter.is_registered()

        # 2. 授权
        auth = await adapter.send_authorize("RFID-TEST-001")
        assert auth["idTagInfo"]["status"] == "Accepted"

        # 3. 开始交易
        start = await adapter.start_transaction(1, "RFID-TEST-001", meter_start=1000)
        assert start["transactionId"] == 10001
        assert adapter.get_transaction_id() == 10001

        # 4. 上报计量数据
        meter = await adapter.send_meter_values(1, 10001, [
            {"value": "1500", "measurand": "Energy.Active.Import.Register"},
            {"value": "220.0", "measurand": "Voltage"},
            {"value": "30.0", "measurand": "Current.Import"},
        ])
        assert meter == {}

        # 5. 状态通知
        status = await adapter.send_status_notification(1, "Charging")
        assert status == {}

        # 6. 结束交易
        stop = await adapter.stop_transaction(10001, 2000, reason="Local")
        assert stop["idTagInfo"]["status"] == "Accepted"
        assert adapter.get_transaction_id() is None

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_boot_notification_custom_params(self):
        """测试自定义 BootNotification 参数"""
        adapter = OCPPAdapter()
        result = await adapter.send_boot_notification(
            charge_point_model="DC-120kW-Pro",
            charge_point_vendor="Tianlian Energy",
            firmware_version="2.1.0",
        )
        assert result["status"] == "Accepted"
        assert "currentTime" in result
        assert result["interval"] > 0

    @pytest.mark.asyncio
    async def test_data_transfer(self):
        """测试 DataTransfer 自定义消息"""
        adapter = OCPPAdapter()
        result = await adapter.send_data_transfer(
            vendor_id="Tianlian",
            message_id="GetBatteryInfo",
            data={"battery_id": "BAT-001"},
        )
        assert result["status"] == "Accepted"

    # ── 远程控制兼容性 ──

    @pytest.mark.asyncio
    async def test_remote_control_flow(self):
        """测试远程控制流程"""
        adapter = OCPPAdapter()
        await adapter.connect()

        # 远程启动
        assert await adapter.remote_start_transaction("RFID-REMOTE", 2) is True

        # 远程停止
        assert await adapter.remote_stop_transaction(10001) is True

        # 远程重启
        assert await adapter.reset("Hard") is True

        # 变更可用性
        assert await adapter.change_availability(1, "Inoperative") is True

    @pytest.mark.asyncio
    async def test_write_command_routing(self):
        """测试 write_command 指令路由"""
        adapter = OCPPAdapter()
        await adapter.connect()

        # remote_start
        assert await adapter.write_command(1, {"action": "remote_start", "id_tag": "TAG1"}) is True

        # remote_stop
        assert await adapter.write_command(1, {"action": "remote_stop", "transaction_id": 10001}) is True

        # reset
        assert await adapter.write_command(1, {"action": "reset", "reset_type": "Soft"}) is True

        # change_availability
        assert await adapter.write_command(1, {"action": "change_availability", "availability": "Operative"}) is True

        # unknown action
        assert await adapter.write_command(1, {"action": "invalid_action"}) is False

    # ── 状态查询兼容性 ──

    def test_get_ocpp_info_structure(self):
        """测试 OCPP 信息结构"""
        adapter = OCPPAdapter(charge_point_id="CP-INFO")
        info = adapter.get_ocpp_info()
        assert info["charge_point_id"] == "CP-INFO"
        assert info["version"] == "1.6-J"
        assert info["protocol"] == "ocpp"
        assert "endpoint" in info
        assert "registered" in info
        assert "transaction_active" in info
        assert "heartbeat_interval" in info

    @pytest.mark.asyncio
    async def test_health_check_structure(self):
        """测试健康检查结构"""
        adapter = OCPPAdapter()
        await adapter.connect()
        health = await adapter.health_check()
        assert health["protocol"] == "ocpp"
        assert health["connected"] is True
        assert health["registered"] is True
        assert health["transaction_active"] is False

    # ── 断开清理兼容性 ──

    @pytest.mark.asyncio
    async def test_disconnect_cleanup(self):
        """测试断开连接后状态清理"""
        adapter = OCPPAdapter()
        await adapter.connect()
        await adapter.start_transaction(1, "TAG")
        assert adapter.get_transaction_id() is not None

        await adapter.disconnect()
        assert not adapter.is_connected()
        assert not adapter.is_registered()

    @pytest.mark.asyncio
    async def test_shutdown_full_cleanup(self):
        """测试完全关闭后状态"""
        adapter = OCPPAdapter()
        await adapter.initialize()
        await adapter.connect()

        await adapter.shutdown()
        assert not adapter.is_initialized()
        assert not adapter.is_connected()
        assert not adapter.is_registered()


# ====================================================================
# MQTT 协议兼容性测试
# ====================================================================

class TestMQTTProtocolCompatibility:
    """MQTT 3.1.1 协议兼容性测试"""

    # ── 消息类型常量 ──

    def test_message_type_constants(self):
        """测试 MQTT 消息类型常量"""
        assert MQTTAdapter.MSG_TELEMETRY == 0x122001
        assert MQTTAdapter.MSG_FAULT_REPORT == 0x122006
        assert MQTTAdapter.MSG_CHARGE_STATUS == 0x122002
        assert MQTTAdapter.MSG_CONTROL_SET == 0x4000
        assert MQTTAdapter.MSG_CONTROL_RESET == 0x4001
        assert MQTTAdapter.MSG_CONTROL_REBOOT == 0x4002

    # ── TLS 兼容性 ──

    def test_tls_disabled_by_default(self):
        """测试默认禁用 TLS"""
        adapter = MQTTAdapter()
        assert adapter.tls_enabled is False
        assert adapter.port == 1883

    def test_tls_enabled_port_switch(self):
        """测试 TLS 启用后端口自动切换"""
        adapter = MQTTAdapter(tls_enabled=True)
        assert adapter.tls_enabled is True
        assert adapter.port == 8883

    def test_tls_explicit_port(self):
        """测试 TLS 显式端口"""
        adapter = MQTTAdapter(tls_enabled=True, port=8884)
        assert adapter.port == 8884

    def test_tls_with_certs(self):
        """测试 TLS 证书配置"""
        adapter = MQTTAdapter(
            tls_enabled=True,
            tls_ca_cert="/path/to/ca.pem",
            tls_client_cert="/path/to/client.pem",
            tls_client_key="/path/to/client.key",
        )
        assert adapter.tls_ca_cert == "/path/to/ca.pem"
        assert adapter.tls_client_cert == "/path/to/client.pem"
        assert adapter.tls_client_key == "/path/to/client.key"

    def test_tls_insecure_mode(self):
        """测试 TLS 不安全模式（仅测试）"""
        adapter = MQTTAdapter(tls_enabled=True, tls_insecure=True)
        assert adapter.tls_insecure is True

    def test_tls_info_structure(self):
        """测试 TLS 信息结构"""
        adapter = MQTTAdapter(tls_enabled=True, tls_ca_cert="/path/ca.pem")
        info = adapter.get_tls_info()
        assert info["enabled"] is True
        assert info["ca_cert"] is True
        assert info["client_cert"] is False
        assert info["insecure"] is False

    def test_ssl_context_building(self):
        """测试 SSL 上下文构建"""
        adapter = MQTTAdapter(tls_enabled=True)
        ctx = adapter._build_ssl_context()
        assert ctx is not None

    def test_ssl_context_disabled(self):
        """测试 TLS 禁用时不构建 SSL 上下文"""
        adapter = MQTTAdapter(tls_enabled=False)
        ctx = adapter._build_ssl_context()
        assert ctx is None

    # ── 重连兼容性 ──

    def test_reconnect_defaults(self):
        """测试默认重连配置"""
        adapter = MQTTAdapter()
        assert adapter.reconnect_enabled is True
        assert adapter.reconnect_max_attempts == 10
        assert adapter.reconnect_base_delay == 1.0
        assert adapter.reconnect_max_delay == 60.0

    def test_reconnect_custom(self):
        """测试自定义重连配置"""
        adapter = MQTTAdapter(
            reconnect_enabled=True,
            reconnect_max_attempts=5,
            reconnect_base_delay=2.0,
            reconnect_max_delay=30.0,
        )
        assert adapter.reconnect_max_attempts == 5
        assert adapter.reconnect_base_delay == 2.0
        assert adapter.reconnect_max_delay == 30.0

    def test_reconnect_disabled(self):
        """测试禁用重连"""
        adapter = MQTTAdapter(reconnect_enabled=False)
        assert adapter.reconnect_enabled is False

    def test_reconnect_status_structure(self):
        """测试重连状态结构"""
        adapter = MQTTAdapter()
        status = adapter.get_reconnect_status()
        assert status["enabled"] is True
        assert status["reconnecting"] is False
        assert status["attempts"] == 0
        assert status["max_attempts"] == 10

    # ── 故障等级解析 ──

    def test_fault_level_emergency(self):
        """测试紧急故障等级"""
        adapter = MQTTAdapter()
        assert adapter._parse_fault_level(0x01) == "emergency"

    def test_fault_level_serious(self):
        """测试严重故障等级"""
        adapter = MQTTAdapter()
        assert adapter._parse_fault_level(0x02) == "serious"

    def test_fault_level_warning_serious(self):
        """测试严重告警等级"""
        adapter = MQTTAdapter()
        assert adapter._parse_fault_level(0x03) == "warning_serious"

    def test_fault_level_warning_general(self):
        """测试一般告警等级"""
        adapter = MQTTAdapter()
        assert adapter._parse_fault_level(0x04) == "warning_general"

    def test_fault_level_unknown(self):
        """测试未知故障等级"""
        adapter = MQTTAdapter()
        assert adapter._parse_fault_level(0xFF) == "unknown"

    # ── 故障消息解析 ──

    def test_parse_fault_message(self):
        """测试故障消息解析"""
        adapter = MQTTAdapter()
        message = {
            "message_type": 0x122006,
            "tcu_address": "TCU001",
            "sequence_no": 12345,
            "fault_level": 0x01,
            "fault_code": 0x7E,
            "fault_detail": ["过温保护触发"],
            "timestamp": "2025-06-22T10:00:00",
        }
        result = adapter.parse_fault_message(message)
        assert result["message_type"] == 0x122006
        assert result["tcu_address"] == "TCU001"
        assert result["fault_level"] == "emergency"
        assert result["fault_code"] == "0x007E"
        assert len(result["fault_detail"]) == 1

    # ── 订阅管理 ──

    @pytest.mark.asyncio
    async def test_subscribe_device(self):
        """测试订阅设备主题"""
        adapter = MQTTAdapter()
        await adapter.connect()
        result = await adapter.subscribe_device("TCU001")
        assert result is True

    @pytest.mark.asyncio
    async def test_subscribe_multiple_devices(self):
        """测试订阅多个设备"""
        adapter = MQTTAdapter()
        await adapter.connect()
        await adapter.subscribe_device("TCU001")
        await adapter.subscribe_device("TCU002")
        await adapter.subscribe_device("TCU003")
        assert len(adapter._subscriptions) == 3

    # ── 回调兼容性 ──

    @pytest.mark.asyncio
    async def test_connect_callback(self):
        """测试连接回调"""
        on_connect = AsyncMock()
        adapter = MQTTAdapter(on_connect_callback=on_connect)
        await adapter.connect()
        on_connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_callback(self):
        """测试断连回调"""
        on_disconnect = AsyncMock()
        adapter = MQTTAdapter(on_disconnect_callback=on_disconnect)
        await adapter.connect()
        await adapter.disconnect()
        on_disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_disconnect_triggers_reconnect(self):
        """测试断连触发重连"""
        adapter = MQTTAdapter(reconnect_enabled=True)
        await adapter.connect()
        await adapter.on_disconnect()
        assert not adapter.is_connected()

    # ── 遥测数据结构 ──

    @pytest.mark.asyncio
    async def test_read_telemetry_structure(self):
        """测试遥测数据结构"""
        adapter = MQTTAdapter()
        await adapter.connect()
        data = await adapter.read_telemetry("TCU001")
        assert data["tcu_address"] == "TCU001"
        assert "charger_voltage" in data
        assert "charger_current" in data
        assert "charger_power" in data
        assert "charger_soc" in data
        assert "gun_status" in data
        assert "gun_temperature" in data
        assert "timestamp" in data

    # ── 生命周期 ──

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """测试完整生命周期"""
        adapter = MQTTAdapter()
        await adapter.initialize()
        assert adapter.is_initialized()

        await adapter.connect()
        assert adapter.is_connected()

        data = await adapter.read_data(1)
        assert "tcu_address" in data

        result = await adapter.write_command(1, {"action": "set_power", "value": 60})
        assert result is True

        await adapter.disconnect()
        assert not adapter.is_connected()


# ====================================================================
# EdgeCache 边缘缓存测试
# ====================================================================

class TestEdgeCache:
    """边缘缓存机制测试"""

    # ── 基本读写 ──

    @pytest.mark.asyncio
    async def test_put_and_get(self):
        """测试基本写入和读取"""
        cache = EdgeCache(ttl_seconds=60)
        await cache.put("device:1", {"voltage": 220.5, "current": 10.0})
        data = await cache.get("device:1")
        assert data is not None
        assert data["voltage"] == 220.5
        assert data["current"] == 10.0

    @pytest.mark.asyncio
    async def test_get_miss(self):
        """测试缓存未命中"""
        cache = EdgeCache()
        data = await cache.get("nonexistent")
        assert data is None

    @pytest.mark.asyncio
    async def test_get_returns_copy(self):
        """测试 get 返回副本（防止外部修改）"""
        cache = EdgeCache()
        await cache.put("key", {"value": 42})
        data = await cache.get("key")
        data["value"] = 99  # 修改副本
        original = await cache.get("key")
        assert original["value"] == 42  # 原数据不变

    # ── TTL 过期 ──

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        """测试 TTL 过期"""
        cache = EdgeCache(ttl_seconds=0.1)
        await cache.put("key", {"data": "test"})

        # 立即获取应命中
        data = await cache.get("key")
        assert data is not None

        # 等待过期
        await asyncio.sleep(0.15)
        data = await cache.get("key")
        assert data is None

    @pytest.mark.asyncio
    async def test_ttl_zero_no_expiry(self):
        """测试 TTL=0 永不过期"""
        cache = EdgeCache(ttl_seconds=0)
        await cache.put("key", {"data": "test"})
        await asyncio.sleep(0.1)
        data = await cache.get("key")
        assert data is not None

    # ── LRU 淘汰 ──

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """测试 LRU 淘汰策略"""
        cache = EdgeCache(max_entries=3)

        await cache.put("a", {"val": 1})
        await cache.put("b", {"val": 2})
        await cache.put("c", {"val": 3})

        # 访问 a 使其成为最近使用
        await cache.get("a")

        # 插入 d 应淘汰 b（最久未使用）
        await cache.put("d", {"val": 4})

        assert await cache.get("a") is not None  # 最近访问，保留
        assert await cache.get("b") is None      # 最久未用，淘汰
        assert await cache.get("c") is not None  # 保留
        assert await cache.get("d") is not None  # 新插入

    @pytest.mark.asyncio
    async def test_lru_update_on_get(self):
        """测试 get 更新 LRU 顺序"""
        cache = EdgeCache(max_entries=2)
        await cache.put("a", {"val": 1})
        await cache.put("b", {"val": 2})

        # 访问 a
        await cache.get("a")

        # 插入 c 应淘汰 b
        await cache.put("c", {"val": 3})

        assert await cache.get("a") is not None
        assert await cache.get("b") is None
        assert await cache.get("c") is not None

    # ── 批量操作 ──

    @pytest.mark.asyncio
    async def test_write_batch(self):
        """测试批量写入"""
        cache = EdgeCache()
        entries = {
            "device:1": {"voltage": 220},
            "device:2": {"voltage": 380},
            "device:3": {"voltage": 110},
        }
        await cache.write_batch(entries)
        assert cache.size() == 3

    @pytest.mark.asyncio
    async def test_read_batch(self):
        """测试批量读取"""
        cache = EdgeCache()
        await cache.put("a", {"val": 1})
        await cache.put("b", {"val": 2})
        await cache.put("c", {"val": 3})

        results = await cache.read_batch(["a", "b", "nonexistent"])
        assert results["a"]["val"] == 1
        assert results["b"]["val"] == 2
        assert results["nonexistent"] is None

    # ── 存在性检查 ──

    @pytest.mark.asyncio
    async def test_exists(self):
        """测试存在性检查"""
        cache = EdgeCache(ttl_seconds=60)
        await cache.put("key", {"data": "test"})
        assert await cache.exists("key") is True
        assert await cache.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_exists_expired(self):
        """测试过期条目的存在性检查"""
        cache = EdgeCache(ttl_seconds=0.1)
        await cache.put("key", {"data": "test"})
        await asyncio.sleep(0.15)
        assert await cache.exists("key") is False

    # ── 删除操作 ──

    @pytest.mark.asyncio
    async def test_delete(self):
        """测试删除条目"""
        cache = EdgeCache()
        await cache.put("key", {"data": "test"})
        assert await cache.delete("key") is True
        assert await cache.get("key") is None
        assert await cache.delete("key") is False  # 重复删除

    # ── 清空操作 ──

    @pytest.mark.asyncio
    async def test_clear(self):
        """测试清空缓存"""
        cache = EdgeCache()
        await cache.put("a", {"val": 1})
        await cache.put("b", {"val": 2})
        count = await cache.clear()
        assert count == 2
        assert cache.size() == 0

    # ── 过期清理 ──

    @pytest.mark.asyncio
    async def test_expire_stale(self):
        """测试主动清理过期条目"""
        cache = EdgeCache(ttl_seconds=0.1)
        await cache.put("a", {"val": 1})
        await cache.put("b", {"val": 2})
        await asyncio.sleep(0.15)

        count = await cache.expire_stale()
        assert count == 2
        assert cache.size() == 0

    @pytest.mark.asyncio
    async def test_expire_stale_no_ttl(self):
        """测试无 TTL 时 expire_stale 返回 0"""
        cache = EdgeCache(ttl_seconds=0)
        await cache.put("a", {"val": 1})
        count = await cache.expire_stale()
        assert count == 0

    # ── get_or_fetch ──

    @pytest.mark.asyncio
    async def test_get_or_fetch_hit(self):
        """测试 get_or_fetch 缓存命中"""
        cache = EdgeCache()
        await cache.put("key", {"cached": True})

        mock_fetcher = AsyncMock(return_value={"fetched": True})
        data = await cache.get_or_fetch("key", mock_fetcher, "arg1")

        assert data["cached"] is True
        mock_fetcher.assert_not_called()  # 不应调用 fetcher

    @pytest.mark.asyncio
    async def test_get_or_fetch_miss(self):
        """测试 get_or_fetch 缓存未命中"""
        cache = EdgeCache()

        mock_fetcher = AsyncMock(return_value={"fetched": True})
        data = await cache.get_or_fetch("key", mock_fetcher, "arg1")

        assert data["fetched"] is True
        mock_fetcher.assert_awaited_once_with("arg1")

        # 第二次应命中缓存
        data2 = await cache.get_or_fetch("key", mock_fetcher)
        assert data2["fetched"] is True
        mock_fetcher.assert_awaited_once()  # 仍只调用一次

    @pytest.mark.asyncio
    async def test_get_or_fetch_fetcher_error(self):
        """测试 fetcher 异常时返回 None"""
        cache = EdgeCache()

        async def failing_fetcher():
            raise RuntimeError("fetch failed")

        data = await cache.get_or_fetch("key", failing_fetcher)
        assert data is None

    # ── 统计信息 ──

    @pytest.mark.asyncio
    async def test_stats_initial(self):
        """测试初始统计"""
        cache = EdgeCache(name="test_cache", ttl_seconds=30, max_entries=500)
        stats = cache.stats()
        assert stats["name"] == "test_cache"
        assert stats["size"] == 0
        assert stats["max_entries"] == 500
        assert stats["ttl_seconds"] == 30
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_stats_after_operations(self):
        """测试操作后统计"""
        cache = EdgeCache()
        await cache.put("a", {"val": 1})
        await cache.put("b", {"val": 2})

        await cache.get("a")  # hit
        await cache.get("a")  # hit
        await cache.get("c")  # miss

        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["writes"] == 2
        assert stats["hit_rate_pct"] == pytest.approx(66.67, abs=0.1)

    @pytest.mark.asyncio
    async def test_stats_evictions(self):
        """测试淘汰统计"""
        cache = EdgeCache(max_entries=2)
        await cache.put("a", {"val": 1})
        await cache.put("b", {"val": 2})
        await cache.put("c", {"val": 3})  # 淘汰 a

        stats = cache.stats()
        assert stats["evictions"] == 1

    # ── 工具方法 ──

    @pytest.mark.asyncio
    async def test_size(self):
        """测试 size 方法"""
        cache = EdgeCache()
        assert cache.size() == 0
        await cache.put("a", {"val": 1})
        assert cache.size() == 1

    @pytest.mark.asyncio
    async def test_keys(self):
        """测试 keys 方法"""
        cache = EdgeCache()
        await cache.put("a", {"val": 1})
        await cache.put("b", {"val": 2})
        keys = cache.keys()
        assert "a" in keys
        assert "b" in keys
        assert len(keys) == 2

    # ── 全局实例工厂 ──

    def test_get_edge_cache_singleton(self):
        """测试全局缓存实例工厂"""
        reset_edge_caches()
        cache1 = get_edge_cache("test", ttl_seconds=10)
        cache2 = get_edge_cache("test", ttl_seconds=20)
        assert cache1 is cache2  # 同名返回同一实例

    def test_get_edge_cache_different_names(self):
        """测试不同名称的缓存实例"""
        reset_edge_caches()
        cache1 = get_edge_cache("cache_a")
        cache2 = get_edge_cache("cache_b")
        assert cache1 is not cache2

    # ── 并发安全 ──

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """测试并发访问安全性"""
        cache = EdgeCache(max_entries=100)

        async def writer(start, count):
            for i in range(start, start + count):
                await cache.put(f"key:{i}", {"val": i})

        async def reader():
            for _ in range(50):
                await cache.get("key:0")

        # 并发写入和读取
        await asyncio.gather(
            writer(0, 50),
            writer(50, 50),
            reader(),
        )

        assert cache.size() == 100


# ====================================================================
# 协议互操作性测试
# ====================================================================

class TestProtocolInteroperability:
    """协议互操作性测试"""

    def test_registry_auto_discover_all_protocols(self):
        """测试自动发现所有协议"""
        registry = ProtocolRegistry()
        registry.auto_discover()

        protocols = registry.list_protocols()
        assert "modbus_rtu" in protocols
        assert "mqtt" in protocols
        assert "rest" in protocols
        assert "ocpp" in protocols

    def test_device_type_to_protocol_routing(self):
        """测试设备类型到协议的路由"""
        registry = ProtocolRegistry()
        registry.auto_discover()

        # 储能逆变器 → Modbus (from YAML templates)
        assert registry.get_protocol_for_device_type("inverter_eahi_20k") == "modbus_rtu"
        # PCS → Modbus (from YAML templates)
        assert registry.get_protocol_for_device_type("pcs_100kw") == "modbus_rtu"
        # 直流充电桩 → MQTT (from YAML templates)
        assert registry.get_protocol_for_device_type("charger_dc_60kw") == "mqtt"
        # 电表 → Modbus (from YAML templates)
        assert registry.get_protocol_for_device_type("meter_three_phase") == "modbus_rtu"
        # BMS → Modbus (from YAML templates)
        assert registry.get_protocol_for_device_type("bms_lithium") == "modbus_rtu"

    def test_get_adapter_for_each_protocol(self):
        """测试为每种协议获取适配器"""
        registry = ProtocolRegistry()
        registry.auto_discover()

        # Modbus 适配器
        modbus = registry.get_adapter("inverter_eahi_20k", {"port": "/dev/ttyUSB0"})
        assert modbus is not None
        assert modbus.protocol_type == "modbus_rtu"

        # MQTT 适配器
        mqtt = registry.get_adapter("charger_dc_60kw", {"broker": "mqtt://test"})
        assert mqtt is not None
        assert mqtt.protocol_type == "mqtt"

        # OCPP 适配器 - 通过注册设备类型后获取
        registry.register_device_type("test_ocpp_device", "ocpp")
        ocpp = registry.get_adapter("test_ocpp_device", {"endpoint": "wss://test"})
        assert ocpp is not None
        assert ocpp.protocol_type == "ocpp"

    def test_get_adapter_unknown_device_type(self):
        """测试未知设备类型返回 None"""
        registry = ProtocolRegistry()
        adapter = registry.get_adapter("unknown_device_type", {})
        assert adapter is None

    def test_get_adapter_with_protocol_override(self):
        """测试配置中的 protocol 字段覆盖设备类型映射"""
        registry = ProtocolRegistry()
        registry.auto_discover()

        # 通过 register_device_type 注册 OCPP 设备类型
        registry.register_device_type("test_ocpp_override", "ocpp")

        # 设备类型映射到 ocpp，config 中不传 protocol 字段
        adapter = registry.get_adapter("test_ocpp_override", {
            "endpoint": "wss://test",
            "charge_point_id": "CP-TEST",
        })
        assert adapter is not None
        assert adapter.protocol_type == "ocpp"

    def test_has_adapter_for_all_protocols(self):
        """测试所有协议类型都已注册"""
        registry = ProtocolRegistry()
        registry.auto_discover()

        assert registry.has_adapter("modbus_rtu")
        assert registry.has_adapter("mqtt")
        assert registry.has_adapter("rest")
        assert registry.has_adapter("ocpp")

    def test_bulk_register_device_types(self):
        """测试批量注册设备类型"""
        registry = ProtocolRegistry()
        registry.register_device_types_bulk({
            "sensor_temp": "modbus_rtu",
            "sensor_humidity": "modbus_rtu",
            "actuator_relay": "mqtt",
        })
        assert registry.get_protocol_for_device_type("sensor_temp") == "modbus_rtu"
        assert registry.get_protocol_for_device_type("actuator_relay") == "mqtt"

    def test_cross_protocol_telemetry_points(self):
        """测试跨协议遥测点定义"""
        # 不同协议的遥测点应独立
        modbus = ModbusRTUAdapter()
        mqtt = MQTTAdapter()

        # Modbus 有 grid_voltage_a
        assert "grid_voltage_a" in modbus.telemetry_points
        # MQTT 没有 grid_voltage_a
        assert "grid_voltage_a" not in mqtt.telemetry_points


# ====================================================================
# 向后兼容性测试
# ====================================================================

class TestBackwardCompatibility:
    """向后兼容性测试"""

    def test_protocol_adapter_alias(self):
        """测试 ProtocolAdapter 别名"""
        from app.gateway.base import ProtocolAdapter as PA
        from app.gateway.base import DeviceAdapter as DA
        assert PA is DA

    def test_old_import_paths(self):
        """测试旧导入路径仍然有效"""
        from app.gateway import ProtocolAdapter
        from app.gateway import DeviceAdapter
        assert ProtocolAdapter is DeviceAdapter

    def test_all_subclasses_are_device_adapters(self):
        """测试所有适配器都是 DeviceAdapter 子类"""
        assert issubclass(ModbusRTUAdapter, DeviceAdapter)
        assert issubclass(MQTTAdapter, DeviceAdapter)
        assert issubclass(OCPPAdapter, DeviceAdapter)
        assert issubclass(RESTAdapter, DeviceAdapter)

    def test_all_adapters_have_protocol_type(self):
        """测试所有适配器都有 protocol_type"""
        assert ModbusRTUAdapter.protocol_type == "modbus_rtu"
        assert MQTTAdapter.protocol_type == "mqtt"
        assert OCPPAdapter.protocol_type == "ocpp"
        assert RESTAdapter.protocol_type == "rest"

    def test_old_test_gateway_still_works(self):
        """测试旧 test_gateway.py 中的 MockAdapter 模式仍可用"""
        class MockAdapter(DeviceAdapter):
            protocol_type = "mock"

            async def connect(self) -> bool:
                self.connected = True
                return True

            async def disconnect(self) -> bool:
                self.connected = False
                return True

            async def read_data(self, device_address: int) -> dict:
                return {"test": "data"}

            async def write_command(self, device_address: int, command: dict) -> bool:
                return True

            def parse_fault_code(self, raw_data: bytes) -> str:
                return "0x00"

        adapter = MockAdapter()
        assert adapter.protocol_type == "mock"
        assert not adapter.is_connected()

    def test_telemetry_point_backward_compat(self):
        """测试 TelemetryPoint 向后兼容"""
        # 旧代码使用方式
        point = TelemetryPoint("test", 0)
        assert point.name == "test"
        assert point.address == 0
        assert point.scale == 1.0
        assert point.unit == ""
        assert point.description == ""

    def test_point_type_enum_values(self):
        """测试 PointType 枚举值不变"""
        assert PointType.VOLTAGE.value == "voltage"
        assert PointType.CURRENT.value == "current"
        assert PointType.POWER.value == "power"
        assert PointType.ENERGY.value == "energy"
        assert PointType.FREQUENCY.value == "frequency"
        assert PointType.TEMPERATURE.value == "temperature"
        assert PointType.PERCENTAGE.value == "percentage"
        assert PointType.STATUS.value == "status"
        assert PointType.COUNTER.value == "counter"
        assert PointType.DURATION.value == "duration"
