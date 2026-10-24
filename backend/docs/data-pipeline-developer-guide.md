# 数据管道开发者指南 (Data Pipeline Developer Guide)

> 适用范围：`app/gateway/`（六协议适配器 + 注册中心 + 连接管理 + 健康探针 + 边缘缓存 + 模板加载）与 `app/parsers/`（解析流水线 + 字段标准化 + 设备 Schema）。
> 面向角色：需要接入新设备协议、排查数据采集链路、或扩展解析规则的 backend 开发者。
> 配套文档：`docs/api-changelog.md`（数据管道监控端点清单）、`docs/performance-optimization.md`（性能与缓存）。

---

## 一、架构总览

### 1.1 数据流图

天链 V3 的设备数据从现场协议到标准化对象，经过 **网关层（Gateway）→ 解析层（Parsers）** 两级管道：

```
                    ┌─────────────────────────────────────────────────────┐
   现场设备          │  Gateway 网关层 (app/gateway/)                        │
  ─────────────►    │                                                       │
  Modbus-RTU        │  ModbusRTUAdapter ─┐                                  │
  MQTT              │  MQTTAdapter       │  ProtocolRegistry (设备类型→协议)  │
  OCPP              │  OCPPAdapter       │  TemplateLoader (YAML 模板热加载) │
  REST              │  RESTAdapter       ├─► EdgeCache (TTL+LRU 边缘缓存)    │
  DLT645            │  DLT645Adapter     │  health_probe (吞吐/延迟/重连)     │
  IEC104            │  IEC104Client ─────┘                                  │
                    └───────────────┬───────────────────────────────────────┘
                                    │ async read_data(device_address)
                                    │ ▼ 返回 Dict[str, Any] 原始遥测
                    ┌───────────────▼───────────────────────────────────────┐
                    │  Parsers 解析层 (app/parsers/)                         │
                    │  create_pipeline(device_type, protocol)               │
                    │   ├─ step1 parse_fields   (Schema 缩放: raw*scale+off)│
                    │   ├─ step2 normalize      (时间对齐 + 数据清洗 drop)   │
                    │   └─ step3 add_metadata   (注入 device_type/protocol) │
                    └───────────────┬───────────────────────────────────────┘
                                    │ ▼ 标准化对象 Dict[str, Any]
                    ┌───────────────▼───────────────────────────────────────┐
                    │  下游：device_data_service → Telemetry 持久化 / 大屏   │
                    └───────────────────────────────────────────────────────┘
```

### 1.2 模块职责表

| 模块 | 文件 | 职责 |
|------|------|------|
| 适配器基类 | `app/gateway/base.py` | 定义 `DeviceAdapter` 抽象接口、`TelemetryPoint` 遥测点模型、生命周期方法 |
| 协议注册中心 | `app/gateway/registry.py` | 协议类型→适配器类、设备类型→协议类型两张映射；单例 + 自动扫描 |
| Modbus-RTU 适配器 | `app/gateway/modbus.py` | 串口 Modbus-RTU，寄存器/离散量读取 |
| MQTT 适配器 | `app/gateway/mqtt.py` | TCU 充电桩 MQTT 协议，含自动重连 |
| OCPP 适配器 | `app/gateway/ocpp.py` | OCPP 1.6 充电桩 WebSocket 协议 |
| REST 适配器 | `app/gateway/rest.py` | HTTP REST API 拉取 |
| DLT645 适配器 | `app/gateway/dlt645.py` | 电力计量 DLT645-2007 协议 |
| IEC104 客户端 | `app/gateway/iec104.py` | IEC 60870-5-104 远动协议 |
| 健康探针 | `app/gateway/health_probe.py` | 吞吐量/延迟/错误率统计、断连重连编排、告警回调 |
| 边缘缓存 | `app/gateway/edge_cache.py` | 本地遥测缓存，TTL + LRU + 命名实例池 |
| 模板加载器 | `app/gateway/template_loader.py` | YAML 设备模板解析、双索引、mtime 热重载 |
| 解析流水线 | `app/parsers/pipeline.py` | 编排解析步骤，串联 schema 解析→标准化→元信息 |
| 数据标准化器 | `app/parsers/normalizer.py` | 字段解析、时间对齐、异常值清洗、单位换算 |
| 基础 Schema | `app/parsers/base_schema.py` | `DeviceSchema`/`FieldSchema`/`DataType`/`Unit` |
| Modbus Schema | `app/parsers/modbus_schema.py` | EAHI5-20K 逆变器寄存器映射 + JSON schema 加载 |
| MQTT Schema | `app/parsers/mqtt_schema.py` | 充电桩遥测字段 + topic/message_type 约定 |

---

## 二、Gateway 网关层

### 2.1 设备适配器基类 `DeviceAdapter`（`base.py`）

所有协议适配器**必须继承** `DeviceAdapter`（`base.py:83`），并向后兼容别名 `ProtocolAdapter = DeviceAdapter`（`base.py:315`）。

**遥测点模型** `TelemetryPoint`（`base.py:36`）描述设备单个数据点的地址映射与解析参数：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `name` | str | — | 遥测点名（如 `grid_voltage_a`） |
| `address` | int | — | 寄存器/数据地址 |
| `point_type` | PointType | VOLTAGE | 数据类型枚举 |
| `scale` | float | 1.0 | 缩放因子：`实际值 = 原始值 × scale` |
| `unit` | str | "" | 单位 |
| `register_count` | int | 1 | 占用寄存器数（决定有符号位宽） |
| `is_signed` | bool | False | 是否有符号 |

`PointType`（`base.py:22`）取值：`VOLTAGE/CURRENT/POWER/ENERGY/FREQUENCY/TEMPERATURE/PERCENTAGE/STATUS/COUNTER/DURATION`。

**子类必须实现的 5 个抽象方法**：

| 方法 | 签名 | 说明 |
|------|------|------|
| `connect` | `async connect() -> bool` | 建立连接 |
| `disconnect` | `async disconnect() -> bool` | 断开连接 |
| `read_data` | `async read_data(device_address: int) -> Dict[str, Any]` | **数据上报入口**，返回含 `timestamp`+协议字段的字典 |
| `write_command` | `async write_command(device_address: int, command: Dict) -> bool` | 下发控制指令 |
| `parse_fault_code` | `parse_fault_code(raw_data: bytes) -> Optional[str]` | 同步解析故障码 |

**生命周期方法**（基类提供默认实现，可重载）：

```
__init__() → initialize() → connect() → read_data()/write_command() → disconnect() → shutdown()
                                                              ↑                          │
                                                              └──── reset() 重置 ◄────────┘
```

- `initialize()`（`base.py:114`）：默认置 `initialized=True`
- `shutdown()`（`base.py:128`）：先 `disconnect()` 再清空 `telemetry_points`
- `reset()`（`base.py:144`）：`shutdown() → initialize() → connect()`，用于故障恢复
- `health_check()`（`base.py:296`）：返回 `{protocol, connected, initialized, telemetry_points_count, status}`，`status` ∈ `healthy`/`disconnected`

> **连接状态**：基类用两个布尔标志 `self.connected` / `self.initialized` 表示，无独立 Enum。

### 2.2 协议注册中心 `ProtocolRegistry`（`registry.py`）

注册中心维护两张映射，采用**全局单例**（`registry.py:265` `_global_registry`，通过 `get_registry()` 获取）：

| 映射 | 含义 | 来源 |
|------|------|------|
| `_protocol_classes: Dict[str, Type]` | 协议类型 → 适配器类 | `register_protocol()` / `auto_discover()` |
| `_device_type_mapping: Dict[str, str]` | 设备类型 → 协议类型 | YAML 模板优先，硬编码兜底 |

**设备类型→协议映射的加载优先级**（`registry.py:44-60`）：
1. 首选从 YAML 模板动态加载（`TemplateLoader.list_device_types()`）
2. 模板为空时回退到硬编码兜底：

| 设备类型 | 协议 |
|---------|------|
| `inverter_eahi_20k` / `pcs_100kw` / `meter_three_phase` / `bms_lithium` | `modbus_rtu` |
| `charger_dc_60kw` | `mqtt` |
| `charger_dc_120kw` / `charger_ac_7kw` / `ev_charger_ocpp` | `ocpp` |

**核心 API**：

| 方法 | 说明 |
|------|------|
| `register_protocol(protocol_type, adapter_class)`（`registry.py:81`） | 注册适配器类，校验 `issubclass(adapter_class, ProtocolAdapter)` |
| `get_adapter(device_type, config)`（`registry.py:99`） | **工厂方法**：解析协议类型 → 实例化 `adapter_class(**config)` |
| `register_device_type` / `register_device_types_bulk` | 维护设备类型映射 |
| `auto_discover(package_path)`（`registry.py:178`） | `pkgutil` 扫描 gateway 包，自动注册带 `protocol_type` 类属性的子类 |
| `reload_templates(template_dir)` | YAML 模板 mtime 变更时热重载 |

> **`get_adapter()` 的协议解析顺序**：`config["protocol"]` 优先，否则查 `_device_type_mapping[device_type]`。**config dict 会被 `**config` 展开传入适配器 `__init__`，因此 dict 键名必须与构造参数名完全一致**。

**模块级便捷函数**（委托单例）：`get_registry()`、`register_protocol()`、`get_adapter()`、`reset_registry()`。

### 2.3 六大协议适配器

| 协议 type | 适配器类 | 构造参数（关键） | 数据上报方法 | 协议特有元素 |
|-----------|---------|-----------------|-------------|-------------|
| `modbus_rtu` | `ModbusRTUAdapter` | `port, baudrate, parity, stopbits, timeout_ms, retry_count, register_maps` | `read_data` / `read_telemetry` / `read_telemetry_by_map` | `RegisterMap` dataclass、功能码常量 `FC_READ_*`、默认映射 `DEFAULT_GRID/BATTERY/PV/TEMP_MAP` |
| `mqtt` | `MQTTAdapter` | `broker, port, client_id, qos, keepalive, tls_*, reconnect_*` + 3 个回调 | `read_data` / `read_telemetry` / `send_control` | 消息类型 `MSG_TELEMETRY=0x122001` 等、主题 `tcu/{addr}/report`·`control`、内置指数退避重连 |
| `rest` | `RESTAdapter` | `base_url, api_key, auth_type, timeout_seconds, retry_count` | `read_data` / `fetch_endpoint` / `post_endpoint` | `auth_type` ∈ `token/basic/oauth2` |
| `ocpp` | `OCPPAdapter` | `endpoint, charge_point_id, auth_token, heartbeat_interval, reconnect_*` | `read_data` / `send_meter_values` / `send_status_notification` | `OCPPAction`/`ChargePointStatus`/`RegistrationStatus` 常量、心跳任务 |
| `dlt645` | `DLT645Adapter` | `port, baudrate, data_bits, parity, stop_bits, meter_address, timeout_ms, retry_count` | `read_data` / `read_by_di` / `read_energy` / `read_instantaneous` | `DLT645Codec`（帧编解码，数据域 ±0x33）、`CMD_READ_DATA=0x11`、`DI_MAP` |
| `iec104` | `IEC104Client` | `host, port, common_address, originator_address, t0..t3_timeout, k_value, w_value, use_tls` | `read_data` / `read_analog_values` / `read_digital_values` / `general_interrogation` | `ASDUType`/`CauseOfTransmission` 枚举、`ASDUCodec` |

**各适配器要点**：

- **ModbusRTUAdapter**：`RegisterMap` 提供 `get_address_range()` 与 `get_contiguous_groups()`（16 寄存器间隔内合并批量读）。构造时通过 `_init_register_maps()` 同步进 `telemetry_points`。
- **MQTTAdapter**：消息类型常量 `MSG_TELEMETRY=0x122001` / `MSG_FAULT_REPORT=0x122006` / `MSG_CHARGE_STATUS=0x122002` / `MSG_CONTROL_SET=0x4000` / `MSG_CONTROL_RESET=0x4001` / `MSG_CONTROL_REBOOT=0x4002`；故障等级 `0x01..0x04` 对应 emergency→warning_general；自带 `_reconnect_loop` 自动重连。
- **OCPPAdapter**：`connect()` 发送 `BootNotification`，Accepted 后启动心跳；`write_command` 按 `command["action"]` 路由到 `remote_start/remote_stop/reset/change_availability`；`health_check` 重载追加 `registered/transaction_active/heartbeat_interval`。
- **DLT645Adapter**：`DLT645Codec` 实现 DLT645-2007 帧编解码（每字节 +0x33 编码、-0x33 解码、校验和、12 位 BCD 小端地址）；`read_data` 遍历整个 `DI_MAP`。
- **IEC104Client**：`ASDUCodec` 支持单点/双点/测量值（归一化/标度化/短浮点）/累计量解码；`read_data` 聚合 analog+digital+integrated。

> **已知边界**：`ModbusRTUAdapter` 的内部 IO 方法（`_read_registers`/`_read_discrete`/`_write_single_register`）当前返回**模拟值**，尚未对接真实串口；`RESTAdapter.__init__` 未调用 `super().__init__()`，故 `telemetry_points`/`initialized` 未初始化。接入真实硬件或扩展时需留意。

### 2.4 健康探针与吞吐监控（`health_probe.py`）

健康探针**不是定时器**——无内部循环，由外部按需调用。维护模块级全局指标 `_last_metrics`（`health_probe.py:20`）。

**指标采集**：

| 函数 | 说明 |
|------|------|
| `record_request(bytes_count=0, error=False, latency_ms=None)`（`health_probe.py:43`） | 每次请求累计：请求数/字节数/错误数/延迟（Phase33-Task3 新增 `latency_ms`） |
| `_reset_metrics()` | 清零（测试与冷启动） |

**健康检查**：

| 函数 | 返回字段 |
|------|---------|
| `async check_gateway_health()`（`health_probe.py:68`） | `protocols: {registered_count, registered, device_type_mappings}` + `throughput: {total_requests, total_errors, total_bytes, requests_per_sec, avg_latency_ms, error_rate_pct}` |
| `get_throughput_stats()`（`health_probe.py:96`） | 同上 + `uptime_seconds`（同步版本） |

**断连重连编排**（Phase33-Task3）：

```
monitor_and_reconnect(device_type, config, on_alert)
   │
   ├─ adapter 不存在        → on_alert(warning) + return reason="no_adapter"
   ├─ adapter.is_connected()→ return reason="already_connected"（不重连）
   └─ reconnect_adapter(..., max_retries=3, on_alert)
        指数退避 1s,2s,4s 反复 disconnect→sleep→connect
        全部失败 → on_alert(critical) + return reason="reconnect_failed"
```

`on_alert` 回调签名 `(device_type: str, message: str, level: str)`，由调用方注入真实告警实现（解耦告警后端）。

### 2.5 边缘缓存 `EdgeCache`（`edge_cache.py`）

本地遥测数据缓存，缓解网关断连与高频轮询。**工厂模式**——按名称维护全局缓存池 `_cache_instances`。

**特性**：

| 特性 | 实现 |
|------|------|
| 存储 | `OrderedDict[str, Tuple[float, Dict]]`，`time.monotonic()` 记时 |
| TTL 过期 | `ttl_seconds`（0=永不过期），`get`/`exists` 惰性删除，`expire_stale()` 主动清理 |
| LRU 淘汰 | `max_entries`（默认 1000），`popitem(last=False)` + `move_to_end` |
| 并发安全 | 所有读写经 `asyncio.Lock` |
| 防篡改 | `get` 返回 `data.copy()`，`put` 存副本 |

**公共 API**：`get` / `put` / `delete` / `exists` / `get_or_fetch`（未命中调 fetcher 回填）/ `read_batch` / `write_batch` / `clear` / `expire_stale` / `stats` / `size` / `keys`。

`stats()` 返回：`{name, size, max_entries, ttl_seconds, hits, misses, hit_rate_pct, writes, evictions, expirations}`。

**全局工厂**：`get_edge_cache(name="default", ttl_seconds=30.0, max_entries=1000)`（`edge_cache.py:316`），`reset_edge_caches()` 清空（测试用）。

### 2.6 模板加载器 `TemplateLoader`（`template_loader.py`）

扫描 `templates/*.yaml`，解析为 `DeviceTemplate` dataclass，提供**双索引**（按 `device_type` / 按 `category`）与基于 mtime 的热重载。

**模板必填字段**：`device_type` / `manufacturer` / `model` / `category` / `protocol`，其中 `category` 必须在 `{inverter, pcs, meter, charger, bms}` 中。

**当前模板清单**（`app/gateway/templates/`，共 11 个）：
`inverter_eahi_20k`、`inverter_huawei_sun2000`、`inverter_sungrow_sg250hx`、`pcs_100kw`、`meter_three_phase`、`bms_lithium`、`charger_dc_60kw`、`charger_starcharge_full`、`charger_teladian`、`dlt645_meter`、`iec104_rtu`。

**模板结构约定**：
- Modbus 类（inverter/pcs/meter/bms）：`connection` 含 `port/baudrate/slave_id`；`registers` 列表项含 `address/name/type/scale/unit`。
- MQTT 类（charger）：`connection` 含 `host/port/topic`（或 `topic_report/topic_control/qos/keepalive/tls_enabled`）。
- IEC104 类：`connection` 含 `host/port/common_address/originator_address/t0..t3_timeout/k_value/w_value/tls_*`；数据点字段为 `data_points`（含 `ioa/name/type/unit/scale/description`）。

**核心 API**：`load_all()`、`reload_if_changed()`（增量重载含删除检测）、`get_template(device_type)`、`get_by_category(category)`、`list_device_types()`、`register_template()`（内存注册）、`add_template_from_file()`、`validate_template_file()`（静态校验）。

---

## 三、Parsers 解析层

### 3.1 解析流水线 `ParsePipeline`（`pipeline.py`）

编排多个解析步骤形成完整流程。**外部入口**：`device_data_service` 通过 `create_pipeline(device_type, protocol)` 创建并 `await pipeline.execute(raw_data)`。

**`execute()` 串联机制**（`pipeline.py:62`）：
- `data = raw_data.copy()`，顺序遍历 `self.steps`，每步返回值赋给 `data`。
- 步骤同时支持同步与异步：通过 `step.__code__.co_flags & 0x80`（`CO_COROUTINE`）判定。
- **异常处理**：每步包在 `try/except`，失败仅 `logger.error`，**吞掉异常继续下一步**（不 raise、不 drop）。

**`build_default_pipeline()` 装配的默认阶段**（`pipeline.py:114`）：

| 步骤 | 函数 | 作用 |
|------|------|------|
| 加载 Schema（注册时立即执行） | `load_schema()` | `protocol=="modbus"` → `load_modbus_schema`；`"mqtt"` → `load_mqtt_schema`；其他 → 空 `DeviceSchema`。同时初始化 `DataNormalizer` |
| step1 字段解析 | `parse_fields_step` | 跳过 `timestamp`/`device_address`，其余 `schema.parse_value(name, raw) = raw×scale+offset` |
| step2 标准化 | `normalize_step` | 调用 `DataNormalizer.normalize(data)`（见 3.2） |
| step3 元信息 | `add_metadata_step` | 注入 `device_type`/`protocol`；缺 `timestamp` 填 `datetime.now()` |

> **已知行为**：`parse_fields_step` 与 `normalize` 内部各自调用一次 `schema.parse_value()`，同一字段被缩放两次。在自定义 pipeline 中按需调整步骤顺序可规避。

### 3.2 数据标准化器 `DataNormalizer`（`normalizer.py`）

将不同设备数据统一为标准格式。`normalize(raw_data)`（`normalizer.py:95`）内部三阶段：

| 阶段 | 处理 |
|------|------|
| 1. 字段解析 | `timestamp`/`device_address` 直通；其余有 schema 则 `schema.parse_value`，否则原样保留 |
| 2. 时间对齐 | `_align_time` → `timestamp.replace(microsecond=0)`（对齐到整秒） |
| 3. 数据清洗 | `_clean_data`（见下表） |

**`_clean_data` 清洗规则（全部为 drop，不发默认值、不 raise）**：

| 校验项 | 触发条件 | 处理 |
|--------|---------|------|
| 空值 | `value is None` | `warning` + 丢弃字段 |
| Schema 下限 | `min` 非 None 且 `value < min` | `warning` + 丢弃 |
| Schema 上限 | `max` 非 None 且 `value > max` | `warning` + 丢弃 |
| 负电压 | `field_name.endswith("_voltage") and value < 0` | `warning` + 丢弃 |
| 负功率（非总功率） | `field_name.endswith("_power") and "total" not in field_name and value < 0` | `warning` + 丢弃 |

`timestamp` / `device_address` 始终保留。

**单位换算 `convert_units`**（`normalizer.py:218`）：
- 类常量 `UNIT_CONVERSION_FACTORS`（`normalizer.py:46`）：键为 `(from, to)`，值为乘法因子；`None` 值走温度特殊公式。
- 覆盖功率/电压/电流/电能/时间/频率/温度的相互换算。
- `_convert_temperature` 支持 `°F↔°C`、`K↔°C`、`K↔°F`、`°F↔K`。

> **已知行为**：`convert_units`、`batch_normalize` 在默认管道主流程中**未被调用**，仅作为公共方法对外暴露；`schema.parse_value` 自身的范围检查只 `warning` 仍返回越界值，真正 drop 发生在 `_clean_data`。

### 3.3 设备 Schema

**`base_schema.py`** — 基础抽象：
- `DataType`（str, Enum）：`UINT16/UINT32/INT16/INT32/FLOAT/STRING/BOOL`
- `Unit`（str, Enum）：`VOLTAGE="V"`、`CURRENT="A"`、`POWER="kW"`、`ENERGY="kWh"`、`FREQUENCY="Hz"`、`TEMPERATURE="°C"`、`PERCENTAGE="%"`、`TIME="s"`、`NONE=""`
- `FieldSchema`（TypedDict）：`name/data_type/unit/scale/offset/min/max/description`
- `DeviceSchema.parse_value(field_name, raw)`：核心公式 **`actual = raw × scale + offset`**（`base_schema.py:178`），范围越界仅告警不修改返回值。

**`modbus_schema.py`** — Modbus 寄存器映射：
- `load_modbus_schema(device_type)`：`inverter_eahi_20k` 走内置 `load_inverter_schema()`，其余尝试 `_load_schema_json()`（从 `schemas/{device_type}.modbus.json` 加载，目录暂不存在则兜底空 schema）。
- 内置 `INVERTER_EAHI_20K_REGISTERS` 覆盖电网侧（0–10）、电池侧（100–104）、光伏侧（200–205）、温度（300–301）、电能（400–405）、运行状态（500–502）共 30+ 字段，全部 `uint16`。
- `INVERTER_FAULT_DISCRETE_ADDR`：离散量故障地址映射表（如 `0=grid_over_voltage_a`、`39=island_fault`、`126=bms_comm_fault`）。

**`mqtt_schema.py`** — MQTT Payload：
- `load_mqtt_schema(device_type)`：`charger_dc_60kw` 走 `load_charger_schema()`（强制 `scale=1.0, offset=0.0`），其余兜底空 schema。
- `CHARGER_TELEMETRY_FIELDS`：`charger_voltage/current/power/soc`、`gun_status/gun_temperature/internal_temperature`（消息类型 `0x122001`）。
- `get_topic(device_address, direction)`：`tcu/{addr}/report` 或 `tcu/{addr}/control`。
- `parse_message_type(msg_type)`：`0x122001=telemetry`、`0x122006=fault_report`、`0x122002=charge_status`、`0x4000=control_set`、`0x4001=control_reset`、`0x4002=control_reboot`。

---

## 四、新增协议适配器接入指南

### 步骤 1 — 创建适配器类

在 `app/gateway/` 下新建 `<proto>.py`，定义适配器类：

- **必须继承** `DeviceAdapter`（`.base`）或别名 `ProtocolAdapter`。
- **必须设置类属性** `protocol_type = "<proto_id>"`（`auto_discover` 用它作注册 key）。
- **可选**类属性 `device_type = "<some_device_type>"`（设置后 `auto_discover` 自动登记设备类型映射）。
- **构造器必须调用** `super().__init__()`（`rest.py` 是反例，未调用导致 `telemetry_points`/`initialized` 未初始化）。

### 步骤 2 — 实现 5 个抽象方法（签名严格按 `base.py`）

```python
async def connect(self) -> bool: ...
async def disconnect(self) -> bool: ...
async def read_data(self, device_address: int) -> Dict[str, Any]: ...   # 数据上报入口
async def write_command(self, device_address: int, command: Dict) -> bool: ...
def parse_fault_code(self, raw_data: bytes) -> Optional[str]: ...
```

`read_data` 返回的字典应包含 `timestamp` 与协议特定遥测字段，字段名与 parser schema 对齐（如 `grid_voltage_a`、`battery_soc`）。

可选覆盖：`initialize()` / `shutdown()` / `reset()` / `health_check()`。

### 步骤 3 — 注册到 registry（三选一）

| 方式 | 做法 | 适用 |
|------|------|------|
| 自动发现（推荐） | 文件放进 `app/gateway/`，`get_registry()` 首次调用时 `auto_discover()` 自动扫描注册 | 标准内置协议 |
| 手动注册 | `from app.gateway import register_protocol; register_protocol("<proto_id>", <Name>Adapter)` | 运行时插件 |
| YAML 模板 | 在 `templates/` 放模板，`device_type`+`protocol` 字段被 `TemplateLoader` 吸收进 `_device_type_mapping` | 生产部署 |

> `auto_discover` 排除 `__init__/base/registry/template_loader` 四个模块，扫描其余所有模块。

### 步骤 4 — 登记设备类型 → 协议映射（三选一）

- **方式 A**：适配器类定义 `device_type` 类属性，`auto_discover` 自动登记。
- **方式 B**：`registry.register_device_type("<device_type>", "<proto_id>")` 或 `register_device_types_bulk({...})`。
- **方式 C**：在 `templates/<device>.yaml` 定义（生产路径）。

### 步骤 5 — 数据流向下游

适配器**只暴露** `async read_data(device_address) -> Dict`，由外部调度调用：
- 采集后写回缓存：`edge_cache.put(key, data)` / `write_batch(entries)`。
- 上报指标：`health_probe.record_request(bytes_count, error, latency_ms)`。
- 下发指令：`write_command(device_address, command)`。

原始 dict 经 `create_pipeline(device_type, protocol).execute(raw_data)` 标准化后，交付 `device_data_service` 持久化。

### 最小示例（伪 Modbus 类适配器）

```python
# app/gateway/myproto.py
from typing import Dict, Any, Optional
from .base import DeviceAdapter

class MyProtoAdapter(DeviceAdapter):
    protocol_type = "myproto"
    device_type = "my_device_x"   # 可选；auto_discover 会自动登记映射

    def __init__(self, host: str, port: int = 502, timeout_ms: int = 3000):
        super().__init__()        # 必须调用
        self.host = host
        self.port = port
        self.timeout_ms = timeout_ms

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def disconnect(self) -> bool:
        self.connected = False
        return True

    async def read_data(self, device_address: int) -> Dict[str, Any]:
        # 返回原始遥测，字段名对齐 parser schema
        return {"device_address": device_address, "some_voltage": 2205}

    async def write_command(self, device_address: int, command: Dict) -> bool:
        return True

    def parse_fault_code(self, raw_data: bytes) -> Optional[str]:
        return None
```

放置后无需手动注册——下次 `get_registry()` 调用时自动发现。实例化：

```python
from app.gateway import get_adapter
adapter = get_adapter("my_device_x", {"host": "192.168.1.10", "port": 502})
data = await adapter.read_data(1)
```

---

## 五、端到端数据流详解

```
1. adapter.read_data(device_address)
   → Dict {timestamp, device_address, grid_voltage_a: 2205, ...}   原始整数值

2. create_pipeline("inverter_eahi_20k", "modbus")
   → build_default_pipeline() 装配 4 步，加载 INVERTER_EAHI_20K_REGISTERS schema

3. await pipeline.execute(raw_data)
   ├─ step1 parse_fields:  grid_voltage_a = 2205 × 0.1 + 0 = 220.5
   ├─ step2 normalize:     时间对齐(去微秒) + 清洗(过滤负电压/越界/空值)
   └─ step3 add_metadata:  注入 device_type/protocol/timestamp

4. 标准化对象 {grid_voltage_a: 220.5, device_type: "inverter_eahi_20k", ...}
   → device_data_service → Telemetry 持久化 / 大屏 / 告警
```

**关键约定**：
- 协议分派仅在 `ParsePipeline.load_schema()` 内通过字符串比较 `"modbus"`/`"mqtt"`；其他协议值落入空 Schema 分支（字段原样透传，不缩放）。
- 整条链路**无 `raise` 业务异常**：schema 找不到 → 空对象；字段未找到 → 原样返回；步骤异常 → 吞掉继续；清洗失败 → 字段 drop。

---

## 六、运维监控端点

数据管道通过 HTTP 端点暴露健康与吞吐指标，供运维大屏与告警系统消费。端点路由、请求/响应 schema 详见 **`docs/api-changelog.md`** 的「数据管道监控」章节，核心能力包括：

| 能力 | 后端函数 | 暴露数据 |
|------|---------|---------|
| 网关健康总览 | `check_gateway_health()` | 已注册协议数、设备类型映射、吞吐量、平均延迟、错误率 |
| 吞吐量统计 | `get_throughput_stats()` | 累计请求/错误/字节、每秒请求、平均延迟、uptime |
| 断连重连编排 | `monitor_and_reconnect()` | `attempted`/`reconnected`/`reason`，失败触发 `on_alert` 告警 |

---

## 七、已知边界行为与注意事项

| 项 | 说明 | 影响 |
|----|------|------|
| Modbus IO 模拟值 | `_read_registers`/`_read_discrete` 返回 `[0]*count`，未对接真实串口 | 真实硬件接入需补全 IO 层 |
| RESTAdapter 未调 super | `telemetry_points`/`initialized` 未初始化 | 扩展时留意，`health_check` 的 `telemetry_points_count` 可能异常 |
| normalize 双重缩放 | `parse_fields_step` 与 `normalize` 各调一次 `parse_value` | 自定义 pipeline 可调整步骤规避 |
| parse_value 越界不 drop | schema 范围检查仅 `warning` 仍返回越界值 | 真正过滤在 `_clean_data`，依赖字段名后缀（`_voltage`/`_power`） |
| convert_units 未接入主流程 | 单位换算仅在自定义调用时生效 | 默认管道不做单位统一换算 |
| schemas/ 目录缺失 | `_load_schema_json` 找不到 JSON，非内置 device_type 落到空 schema | 新设备需走内置 schema 或创建 JSON |
| 链路无业务异常 raise | schema/字段/步骤错误均静默处理 | 排查需看 logger.warning/error |

---

## 八、相关文件清单

| 文件 | 说明 |
|------|------|
| `app/gateway/__init__.py` | 包入口，自动注册 6 协议 |
| `app/gateway/base.py` | `DeviceAdapter` 抽象基类、`TelemetryPoint` |
| `app/gateway/registry.py` | `ProtocolRegistry` 单例 + 自动发现 |
| `app/gateway/{rest,modbus,mqtt,ocpp,dlt645,iec104}.py` | 六协议适配器 |
| `app/gateway/health_probe.py` | 吞吐监控 + 断连重连编排 |
| `app/gateway/edge_cache.py` | 边缘缓存（TTL+LRU） |
| `app/gateway/template_loader.py` | YAML 模板加载与热重载 |
| `app/gateway/templates/*.yaml` | 11 个设备模板 |
| `app/parsers/pipeline.py` | `ParsePipeline` 解析流水线 |
| `app/parsers/normalizer.py` | `DataNormalizer` 标准化与清洗 |
| `app/parsers/base_schema.py` | `DeviceSchema`/`FieldSchema` |
| `app/parsers/modbus_schema.py` | Modbus 寄存器映射 |
| `app/parsers/mqtt_schema.py` | MQTT 字段与 topic 约定 |
| `app/services/device_data_service.py` | 上游调用方，串联 adapter→pipeline |
| `docs/api-changelog.md` | 数据管道监控端点清单 |
