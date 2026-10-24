# 天链V3 监控栈部署指南

> 基于 **Prometheus + Grafana** 的运维监控方案

---

## 📊 架构概览

```
┌─────────────┐     scrape /metrics     ┌──────────────┐    查询数据     ┌─────────────┐
│  天链V3      │ ◄──────────────────── │  Prometheus  │ ─────────────► │   Grafana    │
│  Backend     │     (15s interval)     │  :9090       │                │   :3000      │
│  :8000       │                        └──────────────┘                └─────────────┘
└─────────────┘                               │                                │
       │                                      │                                │
       │ 暴露 Prometheus 指标                  │ 持久化存储                      │ 可视化面板
       │ /metrics                              ▼                                ▼
       │                              ┌──────────────┐                ┌─────────────┐
       └──────────────────────────────│ prometheus_data│               │ grafana_data│
                                      │   (volume)    │               │   (volume)  │
                                      └──────────────┘                └─────────────┘
```

## 🚀 快速启动

### 前置条件

- Docker + Docker Compose
- 天链V3 后端服务已运行（`http://localhost:8000`）

### 启动步骤

```bash
# 1. 给启动脚本添加执行权限
chmod +x scripts/start-monitoring.sh

# 2. 一键启动监控栈
./scripts/start-monitoring.sh

# 3. 验证服务状态
docker compose -f docker-compose.monitoring.yml ps
```

### 手动启动

```bash
# 创建共享网络（如果不存在）
docker network create tianlian-network

# 启动
docker compose -f docker-compose.monitoring.yml up -d

# 查看日志
docker compose -f docker-compose.monitoring.yml logs -f
```

### 停止监控栈

```bash
# 停止但保留数据
docker compose -f docker-compose.monitoring.yml down

# 停止并删除数据
docker compose -f docker-compose.monitoring.yml down -v
```

---

## 📍 访问地址

| 服务 | 地址 | 默认账号 |
|------|------|---------|
| **Grafana** | http://localhost:3000 | admin / tianlian123 |
| **Prometheus** | http://localhost:9090 | 无需认证 |
| **后端指标** | http://localhost:8000/metrics | 无需认证 |

---

## 📊 监控面板说明

### 天链V3 运维监控面板（默认）

面板分为三个区域：

#### 1. API 性能监控
| 面板 | 指标 | 说明 |
|------|------|------|
| API 请求 QPS | `tianlian_http_requests_total` | Top 10 接口的每秒请求数 |
| API 延迟 P50/P95/P99 | `tianlian_http_request_duration_seconds` | 全局分位数延迟 |
| 错误率 (5xx) | 5xx / 总请求 * 100 | 服务器错误占比 |
| HTTP 状态码分布 | 按状态码分组的 QPS | 2xx/3xx/4xx/5xx 分布 |
| 当前处理中请求数 | `tianlian_http_requests_in_flight` | 并发处理数 |
| AI Token 消耗速率 | `tianlian_ai_tokens_used_total` | 5分钟内 Token 消耗 |

#### 2. 业务概览
| 面板 | 指标 | 说明 |
|------|------|------|
| 活跃告警 | `tianlian_active_alarms` | 当前未处理的告警数 |
| 设备在线率 | `devices_online / devices_total` | 设备在线百分比 |
| 在线设备 | `tianlian_devices_online` | 当前在线设备数 |
| 设备总数 | `tianlian_devices_total` | 注册设备总数 |
| 在线网关 | `tianlian_gateways_online` | 在线网关数 |
| 待处理工单 | `tianlian_workorders_pending` | 待处理工单数 |
| 今日工单统计 | created/completed | 今日创建 vs 完成 |
| 遥测数据处理速率 | `tianlian_telemetry_points_processed_total` | 实时处理速率 |
| 故障诊断速率 | `tianlian_diagnosis_total` | 诊断请求数 |

#### 3. 告警趋势
| 面板 | 说明 |
|------|------|
| 活跃告警趋势 | 活跃告警数随时间变化 |

---

## 🛠️ 自定义指标

### 在代码中暴露新指标

```python
from app.metrics import REGISTRY
from prometheus_client import Counter

# 创建新指标
MY_METRIC = Counter(
    "tianlian_custom_metric_total",
    "自定义指标描述",
    ["label1"],
    registry=REGISTRY,
)

# 使用
MY_METRIC.labels(label1="value").inc()
```

### 更新业务指标

后端定时任务应定期调用 `metrics.py` 中的更新函数：

```python
from app.metrics import update_alarm_metrics, update_device_metrics, update_workorder_metrics

# 在某处定时任务中调用
update_alarm_metrics(active_count=12)
update_device_metrics(online=95, total=100)
update_workorder_metrics(pending=5, created_today=23, completed_today=18)
```

---

## 📁 文件结构

```
tianlian-v3/
├── docker-compose.monitoring.yml         # 监控栈 Compose 配置
├── prometheus/
│   └── prometheus.yml                    # Prometheus 采集配置
├── grafana/
│   └── provisioning/
│       ├── dashboards/
│       │   ├── dashboard.json            # 天链V3 运维面板定义
│       │   └── dashboard-provider.yml    # 面板加载器配置
│       └── datasources/
│           └── prometheus.yml            # Prometheus 数据源配置
├── backend/app/
│   └── metrics.py                        # Prometheus 指标暴露模块
├── scripts/
│   └── start-monitoring.sh               # 一键启动脚本
└── docs/
    └── monitoring-guide.md               # 本文档
```

---

## 🔧 环境变量

在 `.env.docker` 或环境变量中配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GRAFANA_ADMIN_USER` | `admin` | Grafana 管理员用户名 |
| `GRAFANA_ADMIN_PASSWORD` | `tianlian123` | Grafana 管理员密码 |
| `GRAFANA_ROOT_URL` | `http://localhost:3000` | Grafana 外部访问 URL |

---

## 🔔 添加告警规则（可选）

在 `prometheus/` 下创建 `alerts.yml`，然后在 `prometheus.yml` 中取消注释 `rule_files`：

```yaml
groups:
  - name: tianlian
    rules:
      - alert: HighErrorRate
        expr: (sum(rate(tianlian_http_requests_total{status_code=~"5.."}[5m])) / sum(rate(tianlian_http_requests_total[5m]))) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "天链V3 错误率超过 5%"

      - alert: ManyActiveAlarms
        expr: tianlian_active_alarms > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "天链V3 活跃告警超过 100 条"

      - alert: LowDeviceOnlineRate
        expr: (tianlian_devices_online / tianlian_devices_total) < 0.8
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "天链V3 设备在线率低于 80%"
```

---

## 📈 数据保留

- **Prometheus**: 默认保留 30 天（可通过 `--storage.tsdb.retention.time` 调整）
- **Grafana**: 面板配置和数据源配置持久化在 volume 中

---

## ❓ 常见问题

### Q: 指标数据为空，Grafana 面板无数据？
1. 确认后端已启动并暴露 `/metrics` 端点
2. 检查 Prometheus Targets: http://localhost:9090/targets
3. 确认 backend 和 prometheus 在同一网络（docker-compose 使用 `extra_hosts` 解决）

### Q: 如何修改 Grafana 密码？
```bash
docker exec -it tianlian-grafana grafana-cli admin reset-admin-password <新密码>
```

### Q: 如何备份 Grafana 面板？
Grafana 面板定义在 `grafana/provisioning/dashboards/dashboard.json` 中，直接备份此文件即可。

### Q: 生产环境如何加固？
1. 修改默认 Grafana 密码
2. 使用 nginx 反向代理 + HTTPS
3. 限制 Grafana/Prometheus 端口仅内网访问
4. 启用 Prometheus 认证（如 basic auth）

---

*最后更新: 2026-05-18*