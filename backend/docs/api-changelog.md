> ⚠️ 本 changelog 冻结于 Phase33（2026-06-03）。Phase33 后 API 变更以 docs/openapi.json 快照 + git log 为准。

# API Changelog — 天链 V3 后端

> 记录天链 V3 后端 API 变更，本文件聚焦**数据管道（Gateway / Parsers）相关端点**。
> 通用业务 API（设备/告警/工单等）变更不在此列。
> 配套文档：`docs/data-pipeline-developer-guide.md`（架构与接入指南）。

---

## 统一响应格式

所有端点响应经 `app/core/response.py:29 success_response(data, message)` 包裹：

```json
{
  "code": 200,
  "message": "success",
  "data": { ... },
  "timestamp": 1753500000
}
```

下文「响应字段」仅描述 `data` 部分。

---

## [Phase33-Task3] 数据管道监控与告警

- **commit**：`9f3d46ac0`（feat(gateway): Phase33-Task3 数据管道监控与告警）
- **路由文件**：`app/api/v1/health.py`（`health.router` 在 `app/api/v1/__init__.py:88` 注册时无额外 prefix，整体 `api_router` 在 `app/main.py:285` 以 `prefix="/api/v1"` 挂载）
- **后端实现**：`app/gateway/health_probe.py`

### 新增端点总览

| 方法 | 路径 | 文件:行 | 后端函数 | 说明 |
|------|------|---------|---------|------|
| GET | `/api/v1/gateway/health` | `app/api/v1/health.py:293` | `check_gateway_health()` | 网关健康探针：已注册协议 + 数据管道吞吐量 |
| GET | `/api/v1/pipeline/health` | `app/api/v1/health.py:271` | `check_gateway_health()` | 数据管道健康状态（与 gateway/health 共用实现，降级分支不同） |
| GET | `/api/v1/pipeline/stats` | `app/api/v1/health.py:286` | `get_throughput_stats()` | 数据管道吞吐量统计（含 uptime） |

### `GET /api/v1/gateway/health`

**用途**：返回所有已注册协议适配器清单与数据管道实时吞吐指标，供运维大屏与告警系统消费。

**响应 `data` 字段（成功）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `protocols.registered_count` | int | 已注册协议数 |
| `protocols.registered` | array | `[{type, adapter}]` 协议类型与适配器类名 |
| `protocols.device_type_mappings` | object | 设备类型 → 协议类型映射 |
| `throughput.total_requests` | int | 累计请求数 |
| `throughput.total_errors` | int | 累计错误数 |
| `throughput.total_bytes` | int | 累计字节数 |
| `throughput.requests_per_sec` | float | 每秒请求数 |
| `throughput.avg_latency_ms` | float | 平均延迟（毫秒） |
| `throughput.error_rate_pct` | float | 错误率（百分比） |

**降级响应**（`check_gateway_health()` 抛异常时）：`protocols` 计数归零、`throughput` 全 0，并附 `error: str`。

**示例**：

```json
{
  "code": 200, "message": "success",
  "data": {
    "protocols": {
      "registered_count": 3,
      "registered": [{"type": "modbus_rtu", "adapter": "ModbusRTUAdapter"}],
      "device_type_mappings": {"inverter_eahi_20k": "modbus_rtu"}
    },
    "throughput": {
      "total_requests": 1024, "total_errors": 3, "total_bytes": 204800,
      "requests_per_sec": 12.5, "avg_latency_ms": 35.2, "error_rate_pct": 0.29
    }
  },
  "timestamp": 1753500000
}
```

### `GET /api/v1/pipeline/health`

**用途**：数据管道健康状态，成功响应与 `gateway/health` 完全一致（均调用 `check_gateway_health()`）。

**降级响应差异**（异常时字段名不同于 `gateway/health`）：

| 字段 | 说明 |
|------|------|
| `gateways.total/healthy/unhealthy/details` | 网关状态汇总（降级时全 0 / 空） |
| `throughput.total_requests/total_errors/total_bytes/requests_per_sec` | 吞吐指标（注意此处用 `error_rate`，非 `error_rate_pct`） |
| `error` | 异常信息 |

> ⚠️ `pipeline/health` 与 `gateway/health` 成功响应相同，但**异常降级分支字段名不一致**（`gateways` vs `protocols`、`error_rate` vs `error_rate_pct`）。消费方需分别处理。

### `GET /api/v1/pipeline/stats`

**用途**：纯吞吐量统计，调用同步函数 `get_throughput_stats()`，无 try/except 包裹。

**响应 `data` 字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_requests` | int | 累计请求数 |
| `total_errors` | int | 累计错误数 |
| `total_bytes` | int | 累计字节数 |
| `requests_per_sec` | float | 每秒请求数 |
| `avg_latency_ms` | float | 平均延迟（毫秒） |
| `uptime_seconds` | int | 探针运行时长（秒） |
| `error_rate_pct` | float | 错误率（百分比） |

### 后端支撑变更（`health_probe.py`）

| 函数 | 变更 | 说明 |
|------|------|------|
| `record_request(bytes_count, error, latency_ms)` | 新增 `latency_ms` 参数 | 累计延迟用于计算 `avg_latency_ms`，向后兼容（默认 None） |
| `reconnect_adapter(device_type, config, max_retries, on_alert)` | 新增 `on_alert` 回调 | 指数退避（1s/2s/4s）重连失败触发 `on_alert(device_type, message, level)` |
| `monitor_and_reconnect(device_type, config, on_alert, max_retries)` | 新增编排函数 | 断连感知 → 自动重连 → 失败告警，返回 `{attempted, reconnected, reason}` |

### 内部编排函数（未通过 HTTP 暴露）

以下函数为内部编排逻辑，仅被 `tests/test_health_probe.py` 覆盖，**不对外提供 HTTP/WS 端点**：

- `monitor_and_reconnect()` — 断连重连编排入口
- `reconnect_adapter()` — 单适配器指数退避重连
- `record_request()` — 指标采集（由适配器/采集器内部调用）

告警通过 `on_alert` 回调以编程方式触发，非 WS 推送。

---

## [Phase33-Task4] 数据管道文档与集成测试

- **commit**：本次提交
- **文档**：新增 `docs/data-pipeline-developer-guide.md`（架构、协议接入指南、数据流图）
- **测试**：补充 `app/gateway/dlt645.py`、`app/gateway/iec104.py` 集成测试，使 `app/gateway/` 与 `app/parsers/` 模块覆盖率 ≥ 80%

---

## 易混淆端点说明

以下端点名称含 "gateway"，但**不属于数据管道监控**，消费时注意区分：

| 路径前缀 | 文件 | 用途 | 与数据管道关系 |
|---------|------|------|---------------|
| `/api/v1/gateways/*` | `app/api/v1/gateways.py` | 网关设备 / SN 码 / 固件升级 CRUD | 无关（设备资产管理） |
| `/api/v1/gateway/*`（oauth/token 等） | `app/api/gateway/api_gateway.py` | Phase11 开放 API 网关（OAuth2/限流） | 无关；且该 router **未被 include_router 挂载**，实际不对外提供服务 |
| `/api/v1/gateway/health`、`/api/v1/pipeline/*` | `app/api/v1/health.py` | **本 changelog 所述数据管道监控端点** | ✅ 数据管道 |

---

## 变更文件清单

| 文件 | 变更 |
|------|------|
| `app/api/v1/health.py` | 新增 `/gateway/health`、`/pipeline/health`、`/pipeline/stats` 端点 |
| `app/gateway/health_probe.py` | 新增 `latency_ms` 统计、`on_alert` 告警回调、`monitor_and_reconnect` 编排 |
| `docs/api-changelog.md` | 本文件 |
| `docs/data-pipeline-developer-guide.md` | 数据管道开发者指南 |
