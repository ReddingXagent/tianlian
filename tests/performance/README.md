# 天链V3 性能压测

## 快速开始

```bash
# 安装 Locust
pip install locust

# 启动压测 (本地测试后端)
locust -f tests/performance/locustfile.py --host=http://localhost:8000

# 启动压测 (云端)
locust -f tests/performance/locustfile.py --host=http://demo.example.com
```

打开 http://localhost:8089 → 设置并发数 → 开始压测

## 常用命令

```bash
# 无界面命令行模式 (100用户, 每秒启动10个, 持续60秒)
locust -f tests/performance/locustfile.py --host=http://demo.example.com \
  --headless -u 100 -r 10 --run-time 60s

# 输出CSV报告
locust -f tests/performance/locustfile.py --host=http://demo.example.com \
  --headless -u 50 -r 5 --run-time 30s --csv=results/perf-report

# 仅测试特定标签
locust -f tests/performance/locustfile.py --host=http://demo.example.com \
  --tags dashboard,health
```

## 测试场景

| 标签 | 接口 | 权重 | 说明 |
|------|------|------|------|
| health | /api/v1/health | 1 | 健康检查 |
| devices | /api/v1/devices | 3+1 | 设备列表+详情 |
| stations | /api/v1/stations | 2 | 站点列表 |
| alarms | /api/v1/alarms | 2+1 | 告警列表+统计 |
| workorders | /api/v1/workorders | 2 | 工单列表 |
| telemetry | /api/v1/telemetry/recent | 1 | 遥测数据 |
| dashboard | /api/v1/dashboard/stats | 1 | 仪表盘 |
| reports | /api/v1/reports | 1 | 报表 |
| knowledge | /api/v1/knowledge/search | 1 | 知识库搜索 |
| monitor | /api/v1/monitor/services | 1 | 服务监控 |

## 性能基准

| 指标 | 期望值 | 警告阈值 | 临界值 |
|------|--------|---------|--------|
| 响应时间 (p50) | <200ms | >500ms | >1000ms |
| 响应时间 (p95) | <500ms | >1000ms | >2000ms |
| 响应时间 (p99) | <1000ms | >2000ms | >5000ms |
| 错误率 | <0.1% | >1% | >5% |
| 吞吐量 | >100 RPS | <50 RPS | <20 RPS |
