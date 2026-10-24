# 🔬 天链V3 模拟器文档

> 光储充一体化运维系统设备模拟器 — 支持无真实现场设备时的全链路开发与测试

---

## 📋 概述

天链V3模拟器提供多协议设备数据仿真能力，使开发者可以在无真实现场设备的情况下，完整运行和测试整个运维系统。模拟器覆盖以下能力：

| 能力 | 描述 | 状态 |
|------|------|------|
| **Modbus-RTU 模拟** | 储能逆变器 / PCS / 电表 | ✅ |
| **MQTT 模拟** | 直流充电桩 (国标协议V2.2.0) | ✅ |
| **REST 模拟** | HTTP API 设备 (光伏气象站等) | ✅ |
| **OCPP 模拟** | 充电桩 OCPP 1.6J | ✅ |
| **DLT645 模拟** | 多功能电能表(国网/南网) | ✅ |
| **IEC104 模拟** | 电力远动规约 RTU | ✅ |
| **故障注入引擎** | 7场景 + 自动随机模式 | ✅ |
| **批量并发** | 100+ 设备并发模拟 + 故障注入 | ✅ |

---

## 🏗 架构

```
┌─────────────────────────────────────────────────────┐
│                   模拟器服务层                        │
│  ┌──────────────┬──────────────┬──────────────────┐ │
│  │ Modbus       │ MQTT         │ DLT645/IEC104    │ │
│  │ Inverter/PCS │ Charger      │ Meter / RTU      │ │
│  └──────┬───────┴──────┬───────┴────────┬─────────┘ │
│         │              │                │           │
│  ┌──────▼──────────────▼────────────────▼─────────┐ │
│  │           故障注入引擎 (FaultEngine)            │ │
│  │  timeout / value_error / disconnect / noise     │ │
│  │  partial_loss / random_drift / device_offline   │ │
│  └──────────────────────┬─────────────────────────┘ │
│                         │                            │
│  ┌──────────────────────▼─────────────────────────┐ │
│  │         数据采集层 (DataCollectionManager)       │ │
│  └──────────────────────┬─────────────────────────┘ │
│                         │                            │
│  ┌──────────────────────▼─────────────────────────┐ │
│  │     WebSocket 推送 → 前端实时监控大屏            │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## 📂 文件索引

| 文件 | 用途 |
|------|------|
| `app/services/modbus_mqtt_simulator.py` | Modbus + MQTT 核心模拟器 |
| `app/services/device_log_simulator.py` | 设备日志/事件模拟器 |
| `app/gateway/modbus.py` | Modbus-RTU 协议适配器 + 寄存器映射 |
| `app/gateway/mqtt.py` | MQTT 协议适配器 (TLS + 断线重连) |
| `app/gateway/rest.py` | REST 协议适配器 |
| `app/gateway/ocpp.py` | OCPP 协议适配器 |
| `app/gateway/templates/` | 设备模板 (YAML 配置) |
| `app/gateway/dlt645.py` | DLT645-2007 电能表协议适配器 |
| `app/gateway/iec104.py` | IEC60870-5-104 远动协议适配器 |
| `tests/test_simulator.py` | 模拟器单元测试 |
| `tests/test_simulator_integration.py` | 模拟器集成测试 |

---

## 🚀 快速开始

### 环境要求

```bash
# Python 3.10+
pip install -r requirements.txt

# 可选：用于真实串口测试
# pip install pyserial pymodbus
```

### 运行模拟器

```python
# 方式1: Python 脚本直接使用
import asyncio
from app.services.modbus_mqtt_simulator import ModbusSimulator, MQTTSimulator

async def demo():
    # 创建 Modbus 逆变器模拟器
    inverter = ModbusSimulator(device_type="inverter", address=1)
    await inverter.connect()
    data = await inverter.read_data()
    print(f"逆变器遥测: {data}")
    
    # 创建 MQTT 充电桩模拟器
    charger = MQTTSimulator(charger_id="C001")
    await charger.connect()
    data = await charger.read_data()
    print(f"充电桩遥测: {data}")

asyncio.run(demo())
```

```bash
# 方式2: 命令行直接运行
cd backend
python -m app.services.modbus_mqtt_simulator
```

### 运行测试

```bash
# 运行所有模拟器测试
cd backend
pytest tests/test_simulator.py -v

# 运行集成测试
pytest tests/test_simulator_integration.py -v

# 运行完整测试套件
pytest tests/ -x --tb=short 2>&1 | tail -20
```

---

## 🔌 协议适配器配置示例

### Modbus-RTU 配置

Modbus-RTU 是最常见的工业设备通信协议，适用于储能逆变器、PCS（功率转换系统）和智能电表。

#### 基本配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `port` | str | `/dev/ttyUSB0` | 串口设备路径 |
| `baudrate` | int | `9600` | 波特率 |
| `databits` | int | `8` | 数据位 |
| `parity` | str | `none` | 校验位 (none/odd/even) |
| `stopbits` | int | `1` | 停止位 |
| `timeout_ms` | int | `3000` | 超时时间 (毫秒) |
| `retry_count` | int | `2` | 重试次数 |

#### YAML 配置文件示例

```yaml
# backend/app/gateway/templates/inverter_eahi_20k.yaml
device_type: inverter_eahi_20k
manufacturer: EAHI
model: 20K-TL3
category: inverter
protocol: modbus_rtu
connection:
  port: /dev/ttyUSB0
  baudrate: 9600
  slave_id: 1
registers:
  - address: 40001
    name: grid_voltage_a
    type: uint16
    scale: 0.1
    unit: V
  - address: 40002
    name: grid_current_a
    type: uint16
    scale: 0.1
    unit: A
  - address: 40003
    name: grid_power
    type: uint16
    scale: 0.01
    unit: kW
  - address: 40004
    name: dc_voltage
    type: uint16
    scale: 0.1
    unit: V
```

```yaml
# backend/app/gateway/templates/pcs_100kw.yaml
device_type: pcs_100kw
manufacturer: Sinexcel
model: PCS100K
category: pcs
protocol: modbus_rtu
connection:
  port: /dev/ttyUSB0
  baudrate: 9600
  slave_id: 2
registers:
  - address: 40100
    name: active_power
    type: int16
    scale: 0.1
    unit: kW
  - address: 40101
    name: reactive_power
    type: int16
    scale: 0.1
    unit: kvar
  - address: 40102
    name: battery_voltage
    type: uint16
    scale: 0.1
    unit: V
  - address: 40103
    name: battery_current
    type: int16
    scale: 0.1
    unit: A
```

#### 代码方式注册

```python
from app.gateway import ModbusRTUAdapter, RegisterMap
from app.gateway.base import TelemetryPoint, PointType

# 创建适配器
adapter = ModbusRTUAdapter(
    port="/dev/ttyUSB0",
    baudrate=9600,
    timeout_ms=3000,
    retry_count=2,
)

# 自定义寄存器映射
custom_map = RegisterMap(
    points=[
        TelemetryPoint("grid_voltage_a", 0, PointType.VOLTAGE, 0.1, "V", "A相电压"),
        TelemetryPoint("grid_power_total", 10, PointType.POWER, 0.1, "kW", "总有功功率"),
    ],
    description="自定义映射"
)
adapter.set_register_maps({"custom": custom_map})

# 连接并读取
await adapter.connect()
data = await adapter.read_data(device_address=1)
```

### MQTT 配置

MQTT 协议用于直流充电桩等需要远程通信的设备。

#### 基本配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `broker` | str | `mqtt.example.com` | MQTT Broker 地址 |
| `port` | int | `1883` | Broker 端口 |
| `client_id` | str | `gateway_001` | 客户端ID |
| `qos` | int | `1` | QoS 等级 (0/1/2) |
| `keepalive` | int | `60` | 心跳间隔 (秒) |
| `tls_enabled` | bool | `False` | 启用 TLS/SSL |
| `reconnect_enabled` | bool | `True` | 自动重连 |
| `reconnect_max_attempts` | int | `10` | 最大重连次数 |

#### TLS 安全配置

```python
from app.gateway import MQTTAdapter

# TLS 安全连接
adapter = MQTTAdapter(
    broker="mqtt.prod.example.com",
    port=8883,
    client_id="gateway_prod_001",
    tls_enabled=True,
    tls_ca_cert="/etc/ssl/certs/ca-bundle.crt",
    tls_client_cert="/etc/ssl/certs/client.crt",
    tls_client_key="/etc/ssl/private/client.key",
    on_connect_callback=on_connected,
    on_disconnect_callback=on_disconnected,
    on_message_callback=on_message_received,
)
await adapter.initialize()
await adapter.connect()

# 订阅设备
await adapter.subscribe_device("TCU001")

# 读取遥测
data = await adapter.read_telemetry("TCU001")
print(f"充电桩数据: {data}")
```

### DLT645 配置 (国标电能表)

DLT645-2007 是中国国家电网公司发布的多功能电能表通信协议。

#### 协议特性

| 特性 | 说明 |
|------|------|
| **物理层** | RS-485 串口 |
| **通信速率** | 1200~9600 bps |
| **帧格式** | 固定长度帧 (主站请求+从站应答) |
| **地址编码** | 12位 BCD 码 (6字节) |
| **数据标识** | 4字节 DI0-DI3 (数据标识编码) |
| **功能** | 读数据 / 写数据 / 广播校时 / 冻结命令 |

#### YAML 配置文件

```yaml
# backend/app/gateway/templates/dlt645_meter.yaml
device_type: dlt645_meter
manufacturer: Wasion
model: DTSD341
category: meter
protocol: dlt645
connection:
  port: /dev/ttyUSB1
  baudrate: 2400
  data_bits: 8
  parity: even
  stop_bits: 1
  meter_address: "000101000001"  # 12位BCD表号
data_points:
  - di_code: "00000000"
    name: combined_active_energy_total
    unit: kWh
    scale: 0.01
  - di_code: "00010000"
    name: combined_active_energy_t1
    unit: kWh
    scale: 0.01
  - di_code: "00020000"
    name: combined_active_energy_t2
    unit: kWh
    scale: 0.01
  - di_code: "00030000"
    name: combined_active_energy_t3
    unit: kWh
    scale: 0.01
  - di_code: "00040000"
    name: combined_active_energy_t4
    unit: kWh
    scale: 0.01
  - di_code: "02010100"
    name: voltage_a
    unit: V
    scale: 0.1
  - di_code: "02010200"
    name: voltage_b
    unit: V
    scale: 0.1
  - di_code: "02010300"
    name: voltage_c
    unit: V
    scale: 0.1
  - di_code: "02020100"
    name: current_a
    unit: A
    scale: 0.001
  - di_code: "02020200"
    name: current_b
    unit: A
    scale: 0.001
  - di_code: "02020300"
    name: current_c
    unit: A
    scale: 0.001
  - di_code: "02030000"
    name: active_power_total
    unit: kW
    scale: 0.0001
  - di_code: "02800002"
    name: power_factor_total
    unit: ""
    scale: 0.001
  - di_code: "02060000"
    name: grid_frequency
    unit: Hz
    scale: 0.01
```

#### 代码方式使用

```python
from app.gateway.dlt645 import DLT645Adapter, DLT645Codec

# 创建编解码器
codec = DLT645Codec()

# 创建适配器
adapter = DLT645Adapter(
    port="/dev/ttyUSB1",
    baudrate=2400,
    meter_address="000101000001",
    timeout_ms=5000,
)

await adapter.connect()

# 读取电能数据
data = await adapter.read_data(device_address=0)
print(f"DLT645电表数据: {data}")

# 读取指定数据标识
voltage = await adapter.read_by_di("02010100")  # A相电压
current = await adapter.read_by_di("02020100")  # A相电流
energy = await adapter.read_by_di("00000000")   # 组合有功总电能
```

#### DLT645 帧编解码

```python
from app.gateway.dlt645 import DLT645Codec

codec = DLT645Codec()

# 编码读取请求帧
frame = codec.encode_read_request(
    meter_address="000101000001",
    di_code="02010100"  # A相电压
)
print(f"请求帧 (hex): {frame.hex()}")

# 解码响应帧
response_data = codec.decode_response(frame)
print(f"解码结果: {response_data}")
```

### IEC104 配置 (电力远动)

IEC60870-5-104 是电力系统远动通信协议，用于调度中心与变电站 RTU 之间的数据传输。

#### 协议特性

| 特性 | 说明 |
|------|------|
| **传输层** | TCP/IP (端口 2404) |
| **帧格式** | APCI (应用规约控制信息) + ASDU (应用服务数据单元) |
| **ASDU 类型** | M_SP_NA(1), M_ME_NA(9), M_ME_NB(11), C_SC_NA(45) 等 |
| **传输原因** | 周期(1)/背景扫描(2)/突发(3)/初始化(4)/请求(5) |
| **信息体地址** | 3字节 (0-16777215) |
| **品质描述** | QDS 品质描述符 (无效/非当前/取代/溢出) |

#### YAML 配置文件

```yaml
# backend/app/gateway/templates/iec104_rtu.yaml
device_type: iec104_rtu
manufacturer: NARI
model: NSS201
category: rtu
protocol: iec104
connection:
  host: 192.168.10.50
  port: 2404
  common_address: 1
  originator_address: 10
  t0_timeout: 30    # 连接建立超时 (秒)
  t1_timeout: 15    # 发送/确认超时 (秒)
  t2_timeout: 10    # 确认超时 (秒)
  t3_timeout: 20    # 测试帧超时 (秒)
  k_value: 12       # 最大未确认发送数
  w_value: 8         # 最大未确认接收数
data_points:
  # 遥测 (M_ME_NA - 归一化测量值)
  - ioa: 4001
    name: bus_voltage_a
    type: normalized
    unit: V
    scale: 220.0
  - ioa: 4002
    name: bus_voltage_b
    type: normalized
    unit: V
    scale: 220.0
  - ioa: 4003
    name: bus_voltage_c
    type: normalized
    unit: V
    scale: 220.0
  # 遥信 (M_SP_NA - 单点信息)
  - ioa: 1001
    name: breaker_cb101_status
    type: single_point
  - ioa: 1002
    name: disconnector_ds101_status
    type: single_point
  - ioa: 1010
    name: protection_relay_operated
    type: single_point
  # 遥测 (M_ME_NB - 标度化测量值)
  - ioa: 5001
    name: active_power_total
    type: scaled
    unit: MW
    scale: 100.0
  - ioa: 5002
    name: reactive_power_total
    type: scaled
    unit: Mvar
    scale: 100.0
  # 累计量 (M_IT_NA)
  - ioa: 8001
    name: energy_import
    type: integrated
    unit: MWh
  - ioa: 8002
    name: energy_export
    type: integrated
    unit: MWh
```

#### 代码方式使用

```python
from app.gateway.iec104 import IEC104Client, ASDUCodec

# TLS 安全连接 (生产环境推荐)
client = IEC104Client(
    host="192.168.10.50",
    port=2404,
    common_address=1,
    use_tls=True,
    tls_ca_cert="/etc/ssl/certs/ca-bundle.crt",
)

await client.connect()

# 总召唤
await client.general_interrogation()

# 读取遥测数据
analog_data = await client.read_analog_values()
print(f"模拟量: {analog_data}")

# 读取遥信数据
digital_data = await client.read_digital_values()
print(f"数字量: {digital_data}")

# 发送遥控命令 (断路器分闸)
await client.send_command(
    ioa=6001,  # 断路器控制点
    value=True  # True=合闸, False=分闸
)

await client.disconnect()
```

#### ASDU 编解码

```python
from app.gateway.iec104 import ASDUCodec

codec = ASDUCodec()

# 编码总召唤命令
asdu = codec.encode_general_interrogation(
    common_address=1,
    cause_of_transmission=6  # 激活
)

# 解码模拟量遥测响应
response = codec.decode_asdu(asdu_bytes)
print(f"解码: {response}")
```

### REST 配置 (光伏气象站)

```python
from app.gateway.rest import RESTAdapter

adapter = RESTAdapter(
    base_url="http://192.168.1.200/api/v1",
    auth_type="api_key",
    api_key="sk-xxxx",
    timeout=30,
)

await adapter.connect()
data = await adapter.read_data(device_address=0)
print(f"气象站数据: {data}")
```

### OCPP 配置 (充电桩)

```python
from app.gateway.ocpp import OCPPAdapter

adapter = OCPPAdapter(
    charge_point_id="CP001",
    ws_url="ws://ocpp-server.example.com:8080/steve/websocket/CentralSystemService/CP001",
    auth_enabled=True,
    auth_password="secure_password",
)

await adapter.connect()
data = await adapter.read_data(device_address=0)
print(f"OCPP充电桩数据: {data}")
```

---

## 🛡️ 故障注入引擎

故障注入引擎用于模拟真实运行环境中的各类故障场景，验证系统的鲁棒性和告警处理能力。

### 7 种故障场景

| 场景 | 故障类型 | 描述 | 触发概率 |
|------|----------|------|----------|
| 1 | `timeout` | 模拟设备通信超时 | 10% |
| 2 | `value_error` | 返回异常数值 (NaN/Inf) | 5% |
| 3 | `disconnect` | 模拟设备断连 | 5% |
| 4 | `noise` | 数据添加随机噪声 | 20% |
| 5 | `partial_loss` | 部分遥测点数据丢失 | 15% |
| 6 | `random_drift` | 遥测值随机漂移 (传感器老化) | 10% |
| 7 | `device_offline` | 设备完全离线 | 3% |
| — | `auto_random` | 自动随机组合多种故障 | — |

### 使用方式

```python
from app.gateway.faults import FaultEngine, FaultScenario

# 创建故障引擎
engine = FaultEngine()

# 手动注入指定故障
result = engine.inject_scenario(FaultScenario.TIMEOUT)
print(f"注入结果: {result}")

# 手动参数覆盖
result = engine.inject_scenario(
    FaultScenario.VALUE_ERROR,
    params={"probability": 0.3, "error_types": ["nan", "inf", "negative"]}
)

# 自动随机模式 (推荐用于压力测试)
engine.enable_auto_random(interval_seconds=30)

# 在数据采集时应用故障效果
data = await adapter.read_data(device_address=1)
corrupted_data = engine.apply_faults(data)

# 检查是否有活跃故障
if engine.has_active_fault():
    print(f"活跃故障: {engine.active_faults}")

# 清除所有故障
engine.clear_all()
```

### 故障注入配置

```python
# 自定义故障配置
engine = FaultEngine(config={
    "timeout": {"probability": 0.15, "duration_ms": 5000},
    "disconnect": {"probability": 0.08, "recovery_ms": 30000},
    "noise": {"probability": 0.25, "amplitude": 0.05},
    "partial_loss": {"probability": 0.12, "loss_rate": 0.3},
    "random_drift": {"probability": 0.10, "drift_rate": 0.02},
    "device_offline": {"probability": 0.02, "offline_duration_s": 120},
})
```

---

## 📊 批量并发场景测试

模拟器支持大规模并发设备模拟，用于压力测试和性能验证。

```python
import asyncio
from app.services.modbus_mqtt_simulator import ModbusSimulator, MQTTSimulator
from app.gateway.faults import FaultEngine

async def batch_simulate():
    """100+ 设备并发模拟"""
    fault_engine = FaultEngine()
    fault_engine.enable_auto_random(interval_seconds=60)
    
    tasks = []
    
    # 50台逆变器
    for i in range(1, 51):
        sim = ModbusSimulator(device_type="inverter", address=i)
        tasks.append(sim.connect())
    
    # 30台PCS
    for i in range(1, 31):
        sim = ModbusSimulator(device_type="pcs", address=100 + i)
        tasks.append(sim.connect())
    
    # 20台充电桩
    for i in range(1, 21):
        sim = MQTTSimulator(charger_id=f"C{i:03d}")
        tasks.append(sim.connect())
    
    await asyncio.gather(*tasks)
    print("100台设备全部就绪")

asyncio.run(batch_simulate())
```

---

## 🧪 集成测试

```bash
# 运行模拟器集成测试
cd backend
pytest tests/test_simulator_integration.py -v

# 预期输出 (示例)
# test_all_simulators_init .................... PASSED
# test_modbus_normal_read .................... PASSED
# test_mqtt_normal_read ...................... PASSED
# test_dlt645_normal_read .................... PASSED
# test_iec104_normal_read .................... PASSED
# test_fault_injection_timeout ............... PASSED
# test_fault_injection_value_error ........... PASSED
# test_data_collector_with_simulators ........ PASSED
# test_concurrent_batch 100 devices .......... PASSED
# test_full_pipeline_modbus_to_api ........... PASSED
```

---

## 🔧 设备模板

所有设备模板位于 `app/gateway/templates/` 目录下：

| 模板文件 | 设备 | 协议 |
|----------|------|------|
| `inverter_eahi_20k.yaml` | EAHI 20K-TL3 逆变器 | Modbus-RTU |
| `inverter_sungrow_sg250hx.yaml` | Sungrow SG250HX 逆变器 | Modbus-RTU |
| `inverter_huawei_sun2000.yaml` | 华为 SUN2000 逆变器 | Modbus-RTU |
| `pcs_100kw.yaml` | Sinexcel PCS100K 功率转换 | Modbus-RTU |
| `bms_lithium.yaml` | CATL BMS 锂电池管理系统 | Modbus-RTU |
| `meter_three_phase.yaml` | Acrel ADL3000 三相电表 | Modbus-RTU |
| `charger_dc_60kw.yaml` | StarCharge DCL060 直流充电桩 | MQTT |
| `charger_teladian.yaml` | Teladian 直流充电桩 | MQTT |
| `dlt645_meter.yaml` | Wasion DTSD341 电能表 | DLT645 |
| `iec104_rtu.yaml` | NARI NSS201 远动RTU | IEC104 |

加载模板：

```python
from app.gateway.template_loader import get_template_loader

loader = get_template_loader()
template = loader.load("inverter_sungrow_sg250hx")
print(f"设备: {template.manufacturer} {template.model}")
print(f"协议: {template.protocol}")
print(f"寄存器: {len(template.registers)} 个")
```

---

## 📖 更多资源

- [ARCHITECTURE.md](../ARCHITECTURE.md) - 系统整体架构
- [DEPLOYMENT.md](../DEPLOYMENT.md) - 部署指南
- [USER_MANUAL.md](../USER_MANUAL.md) - 用户手册
- [SPEC.md](../SPEC.md) - 技术规格说明

---

*最后更新: 2026-06-24*
