# 天链V3性能压测报告

## 测试概况
- **测试时间**: {{test_date}}
- **测试版本**: {{version}}
- **测试环境**: {{environment}}
- **测试工具**: Locust {{locust_version}}
- **测试时长**: {{duration}}分钟

## 测试场景

### 1. 轻负载场景 (50用户)
- **并发用户数**: 50
- **每秒新增用户**: 10
- **目标响应时间**: < 500ms

**结果**:
- 总请求数: {{light_total_requests}}
- 平均响应时间: {{light_avg_response_time}}ms
- 95%响应时间: {{light_p95_response_time}}ms
- 99%响应时间: {{light_p99_response_time}}ms
- 错误率: {{light_failure_rate}}%
- 请求速率: {{light_rps}} RPS

### 2. 中等负载场景 (100用户)
- **并发用户数**: 100
- **每秒新增用户**: 20
- **目标响应时间**: < 800ms

**结果**:
- 总请求数: {{medium_total_requests}}
- 平均响应时间: {{medium_avg_response_time}}ms
- 95%响应时间: {{medium_p95_response_time}}ms
- 99%响应时间: {{medium_p99_response_time}}ms
- 错误率: {{medium_failure_rate}}%
- 请求速率: {{medium_rps}} RPS

### 3. 高负载场景 (200用户)
- **并发用户数**: 200
- **每秒新增用户**: 40
- **目标响应时间**: < 1500ms

**结果**:
- 总请求数: {{heavy_total_requests}}
- 平均响应时间: {{heavy_avg_response_time}}ms
- 95%响应时间: {{heavy_p95_response_time}}ms
- 99%响应时间: {{heavy_p99_response_time}}ms
- 错误率: {{heavy_failure_rate}}%
- 请求速率: {{heavy_rps}} RPS

## 性能瓶颈分析

### API端点性能排名
| 端点 | 平均响应时间 | 95%响应时间 | 错误率 | 请求数 |
|------|--------------|-------------|--------|--------|
| {{api_endpoints_table}} |

### 资源使用情况
- **CPU使用率**: {{cpu_usage}}
- **内存使用率**: {{memory_usage}}
- **网络I/O**: {{network_io}}
- **数据库连接数**: {{db_connections}}

## 关键发现

### ✅ 优点
1. {{strength_1}}
2. {{strength_2}}
3. {{strength_3}}

### ⚠️ 待优化项
1. {{improvement_1}}
2. {{improvement_2}}
3. {{improvement_3}}

### 🚨 严重问题
1. {{critical_issue_1}}
2. {{critical_issue_2}}

## 优化建议

### 短期优化 (1-2周)
1. {{short_term_1}}
2. {{short_term_2}}

### 中期优化 (1个月)
1. {{mid_term_1}}
2. {{mid_term_2}}

### 长期优化 (3个月+)
1. {{long_term_1}}
2. {{long_term_2}}

## 结论
{{conclusion}}

## 测试配置
```yaml
{{config_content}}
```

## 附件
- [轻负载报告](reports/light-load-report.html)
- [中等负载报告](reports/medium-load-report.html)
- [高负载报告](reports/heavy-load-report.html)
- [原始数据](reports/stats.json)