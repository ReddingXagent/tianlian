# API 参考 — 天链V3 边缘网关本地 API

> 基础地址: `http://<gateway-ip>:8080`  
> 版本: 0.2.0  
> 所有端点免认证（本地调试用途），CORS 全放通。

## 健康检查

### `GET /health`

轻量探活，适用于负载均衡 / Kubernetes liveness。

**响应 200:**
```json
{
  "status": "healthy",
  "gateway": "tianlian-v3-edge",
  "timestamp": 1722720000.123
}
```

---

## 网关状态

### `GET /api/v1/status`

网关运行时状态摘要。

**响应 200:**
```json
{
  "uptime_seconds": 3600.5,
  "uptime_formatted": "1h 0m 0s",
  "device_count": 2,
  "cache_size": 42,
  "cache_max": 10000
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `uptime_seconds` | float | 启动至今秒数 |
| `uptime_formatted` | string | 人类可读时长（如 `2d 3h 15m 4s`） |
| `device_count` | int | 当前连接设备数 |
| `cache_size` | int | SQLite 缓存未同步条目数 |
| `cache_max` | int | 缓存上限（达上限后丢弃最旧条目） |

---

## 最新遥测

### `GET /api/v1/telemetry/latest`

所有设备的最新遥测快照。

**响应 200:**
```json
{
  "count": 2,
  "telemetry": {
    "CHARGER-001": {
      "power": 22.5,
      "voltage": 380.2,
      "current": 59.2,
      "temperature": 42.3,
      "energy": 15.8,
      "status": "charging",
      "timestamp": "2026-08-03T13:20:00Z"
    },
    "MODBUS-001": {
      "power": 0.0,
      "voltage": 380.1,
      "current": 0.0,
      "temperature": 25.0,
      "status": "idle",
      "timestamp": "2026-08-03T13:19:55Z"
    }
  }
}
```

---

## 设备列表

### `GET /api/v1/devices`

已连接设备摘要列表。

**响应 200:**
```json
{
  "count": 2,
  "devices": [
    {
      "device_id": "CHARGER-001",
      "last_seen": "2026-08-03T13:20:00Z",
      "status": "charging",
      "power_kw": 22.5,
      "voltage_v": 380.2,
      "temperature_c": 42.3
    }
  ]
}
```

---

## 缓存统计

### `GET /api/v1/cache/stats`

SQLite 断网缓存统计。

**响应 200:**
```json
{
  "unsynced_count": 12,
  "total_count": 8530,
  "max_cache_size": 10000,
  "max_retries": 5,
  "db_path": "data/gateway.db"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `unsynced_count` | int | 尚未成功上传的条目数（遥测+告警合计） |
| `total_count` | int | 缓存表总行数（含已同步未清理） |
| `max_cache_size` | int | 容量上限 |
| `max_retries` | int | 单条目最大重试次数 |
| `db_path` | string | SQLite 文件路径 |

---

## 调试仪表盘

### `GET /api/v1/dashboard`

聚合端点 — 一次请求返回所有关键监控数据。

**响应 200:**
```json
{
  "status": "healthy",
  "gateway": "tianlian-v3-edge",
  "uptime_seconds": 3600.5,
  "uptime_formatted": "1h 0m 0s",
  "device_count": 2,
  "devices": [ /* 同 /api/v1/devices */ ],
  "telemetry": {
    "latest": { /* 同 /api/v1/telemetry/latest */ },
    "total": 5230,
    "rate_per_sec": 1.45
  },
  "alarms": {
    "total": 3,
    "rate_per_sec": 0.0008
  },
  "cloud": {
    "push_total": 5200,
    "push_failures": 30,
    "success_rate": 0.9942,
    "last_push": "2026-08-03T13:19:50Z"
  },
  "cache": { /* 同 /api/v1/cache/stats 的内层结构 */ },
  "timestamp": 1722720000.123
}
```

---

## 性能指标

### `GET /api/v1/perf`

运行时性能指标，适合接入 Prometheus / Grafana。

**响应 200:**
```json
{
  "uptime_seconds": 3600.5,
  "device_count": 2,
  "throughput": {
    "telemetry_total": 5230,
    "telemetry_rate_per_sec": 1.45,
    "alarm_total": 3,
    "alarm_rate_per_sec": 0.0008
  },
  "cloud": {
    "push_total": 5200,
    "push_failures": 30,
    "success_rate": 0.9942,
    "last_push": "2026-08-03T13:19:50Z"
  },
  "cache": {
    "telemetry": { "total": 8500, "unsynced": 10 },
    "alarms": { "total": 30, "unsynced": 2 }
  },
  "timestamp": 1722720000.123
}
```

---

## 模拟端点（调试）

### `POST /api/v1/simulate/telemetry`

手动注入一条遥测数据，走完整管道（缓存 + MQTT + 云端缓冲）。

**请求体:**
```json
{
  "device_type": "ocpp",
  "power": 30.0,
  "voltage": 380.0,
  "current": 78.9,
  "temperature": 45.0,
  "energy": null,
  "status": "charging"
}
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `device_type` | string | `"ocpp"` | `"ocpp"` 或 `"modbus"` |
| `power` | float | 0.0 | 功率 (kW) |
| `voltage` | float | 380.0 | 电压 (V) |
| `current` | float | 0.0 | 电流 (A) |
| `temperature` | float | 25.0 | 温度 (°C) |
| `energy` | float\|null | null | 累计电量 (kWh)，null=不更新 |
| `status` | string | `"normal"` | 设备状态标识 |

**响应 200:**
```json
{
  "status": "injected",
  "device_type": "ocpp",
  "telemetry": { /* 完整遥测点 */ }
}
```

**错误 400:** OCPP/Modbus adapter 不可用（未初始化）。

---

### `POST /api/v1/simulate/alarm`

手动触发一条告警，走完整管道（MQTT + 云端缓冲）。

**请求体:**
```json
{
  "device_type": "ocpp",
  "alarm_type": "over_temperature",
  "message": "手动测试告警"
}
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `device_type` | string | `"ocpp"` | `"ocpp"` 或 `"modbus"` |
| `alarm_type` | string | `"test_alarm"` | 告警类型标识 |
| `message` | string | `"Manual test alarm"` | 告警描述 |

**响应 200:**
```json
{
  "status": "triggered",
  "device_type": "ocpp",
  "alarm_type": "over_temperature",
  "message": "手动测试告警"
}
```

---

## curl 快速验证

```bash
# 健康检查
curl http://localhost:8080/health

# 网关状态
curl http://localhost:8080/api/v1/status

# 注入模拟遥测
curl -X POST http://localhost:8080/api/v1/simulate/telemetry \
  -H "Content-Type: application/json" \
  -d '{"device_type":"ocpp","power":22.5,"status":"charging"}'

# 触发模拟告警
curl -X POST http://localhost:8080/api/v1/simulate/alarm \
  -H "Content-Type: application/json" \
  -d '{"alarm_type":"test","message":"hello"}'

# 查看仪表盘
curl http://localhost:8080/api/v1/dashboard | python -m json.tool
```
