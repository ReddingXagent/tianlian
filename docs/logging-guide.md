# 天链 V3 — 日志配置与使用指南

> 最后更新: 2026-05-18

## 概述

天链 V3 使用统一的结构化日志系统，基于 Python `logging` 标准库构建。日志输出为 **JSON 格式**，便于日志聚合、分析和搜索。

### 设计目标

- **结构化** — 每条日志都是标准 JSON，可直接导入 ELK/Loki/Datadog 等日志平台
- **可追溯** — 每个请求绑定唯一 `request_id`，端到端追踪调用链
- **零侵入** — 通过中间件自动注入，业务代码无需额外改动
- **自动轮转** — 按大小 50MB 自动切割，保留最近 5 个文件

---

## 日志位置

| 文件 | 用途 |
|------|------|
| `logs/tianlian-v3.log` | 所有级别日志（主文件） |
| `logs/tianlian-v3-error.log` | 仅 ERROR 及以上（独立文件） |
| `logs/tianlian-v3.log.1` ~ `.5` | 轮转备份 |

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 日志级别: DEBUG / INFO / WARNING / ERROR / CRITICAL |
| `DEBUG` | `true` | `true`=彩色控制台输出, `false`=纯 JSON 输出 |

```bash
# 开发环境 — 详细日志 + 彩色输出
export LOG_LEVEL=DEBUG
export DEBUG=true

# 生产环境 — 仅 JSON 输出
export LOG_LEVEL=INFO
export DEBUG=false
```

---

## JSON 字段说明

每条日志是一个 JSON 对象，包含以下字段：

```json
{
  "timestamp": "2026-05-18T10:30:45.123456+00:00",
  "level": "INFO",
  "module": "app.api.v1.auth",
  "message": "用户登录成功",
  "request_id": "a3f7dd2e1b4c5d6f",
  "user_id": "user_001",
  "method": "POST",
  "path": "/api/v1/auth/login",
  "status_code": 200,
  "duration_ms": 45.23,
  "client_ip": "192.168.1.100"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | string | ISO 8601 UTC 时间戳 |
| `level` | string | 日志级别 |
| `module` | string | 产生日志的 Python 模块 |
| `message` | string | 日志消息 |
| `request_id` | string | 请求唯一标识 (16 hex) |
| `user_id` | string | 用户 ID (如已认证) |
| `method` | string | HTTP 方法 |
| `path` | string | 请求路径 |
| `status_code` | int | HTTP 状态码 |
| `duration_ms` | float | 请求耗时（毫秒） |
| `client_ip` | string | 客户端 IP |
| `exception` | string | 异常堆栈 (仅 ERROR 时) |

---

## API 使用示例

### 在 Python 代码中写日志

```python
import logging

logger = logging.getLogger(__name__)

# 常规日志
logger.info("设备数据同步完成 count=%d", 42)
logger.warning("MQTT 连接超时 broker=%s", broker_url)
logger.error("数据库写入失败 table=%s error=%s", table, str(e))

# 带异常堆栈
try:
    risky_operation()
except Exception as e:
    logger.exception("操作失败")  # 自动附加堆栈
```

### 带请求上下文的日志

```python
from app.core.log_config import get_request_logger

def my_handler(request: Request):
    request_id = request.state.request_id
    user_id = getattr(request.state, "user_id", "-")

    logger = get_request_logger(__name__, request_id, user_id)
    logger.info("处理设备告警 device=%s", device_id)
    # JSON 输出自动包含 request_id + user_id
```

---

## 日志查看器

使用 `scripts/log-viewer.sh` 快速分析日志。

### 实时跟踪

```bash
# 实时查看所有日志
./scripts/log-viewer.sh --follow

# 实时查看 ERROR
./scripts/log-viewer.sh --follow --level ERROR

# 实时查看 auth 模块的 WARNING+
./scripts/log-viewer.sh --follow --level WARN --module auth
```

### 历史查看

```bash
# 最近 200 条
./scripts/log-viewer.sh --recent 200

# 最近 50 条错误
./scripts/log-viewer.sh --level ERROR --recent 50
```

### 错误统计

```bash
./scripts/log-viewer.sh --stats
```

输出示例:

```
═════════════════════════════════════════════════════
  天链 V3 — 错误统计摘要
═════════════════════════════════════════════════════

日志总行数: 15347

各级别分布:
----------------------------------------
  DEBUG     : 8942
  INFO      : 5201
  WARNING   : 856
  ERROR     : 342
  CRITICAL  : 6

ERROR 最近 10 条:
----------------------------------------
  2026-05-18 10:30:45 database.py  数据库连接超时

ERROR 按模块分布:
----------------------------------------
  app.api.v1.auth              45
  app.services.dispatch_engine 32
  app.core.database            18
```

---

## 日志分析

### 使用 jq 分析

```bash
# 统计 5 分钟内错误数
cat logs/tianlian-v3.log | jq 'select(.level=="ERROR")' | wc -l

# 查找慢请求 (>500ms)
cat logs/tianlian-v3.log | jq 'select(.duration_ms > 500)'

# 按状态码分组
cat logs/tianlian-v3.log | jq -r '.status_code' | sort | uniq -c | sort -rn

# 提取某个 request_id 的全链路日志
cat logs/tianlian-v3.log | jq 'select(.request_id == "a3f7dd2e1b4c5d6f")'
```

### 使用 grep 快速排查

```bash
# 搜索关键字
grep "数据库" logs/tianlian-v3.log

# 统计 404 数量
grep -c '"status_code":404' logs/tianlian-v3.log

# 今天的所有错误
grep "$(date +%Y-%m-%d)" logs/tianlian-v3.log | grep '"level":"ERROR"'
```

### 导入外部分析平台

JSON 格式可直接导入:

- **ELK (Elasticsearch + Logstash + Kibana)** — Filebeat 直接采集
- **Grafana Loki** — 使用 Promtail 采集
- **Datadog** — Agent 自动解析 JSON
- **ClickHouse** — `INSERT INTO logs FORMAT JSONEachRow`

---

## 生产环境配置

### Docker 环境

```dockerfile
ENV LOG_LEVEL=INFO
ENV DEBUG=false
```

日志通过 stdout 输出 JSON → Docker 日志驱动采集:

```yaml
# docker-compose.yml
services:
  backend:
    environment:
      - LOG_LEVEL=INFO
      - DEBUG=false
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
```

### systemd 环境

日志同时写入文件和控制台，journald 自动采集 stdout。

---

## 故障排查

### 日志文件未生成

1. 确认应用已启动: `ps aux | grep uvicorn`
2. 检查 `logs/` 目录权限: `ls -la logs/`
3. 检查 `LOG_LEVEL` 是否设置过高

### 日志过大

- 自动轮转: 单文件 >50MB 时自动切割
- 手动清理: `find logs/ -name "*.log.*" -mtime +7 -delete`
- 添加到 crontab 定期清理

### 日志丢失

- 检查 `RotatingFileHandler` backupCount=5 是否够用
- 生产环境建议使用外部日志采集（Filebeat/Promtail）而非依赖文件轮转