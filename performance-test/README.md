# 天链V3性能压测套件

## 概述
基于Locust的性能压测套件，用于评估天链V3系统在不同负载下的表现。

## 文件结构
```
performance-test/
├── locustfile.py          # Locust测试脚本
├── benchmark-config.yml   # 压测配置
├── run-benchmark.sh       # 执行脚本
├── performance-report-template.md  # 报告模板
└── README.md              # 本文档
```

## 使用方法

### 1. 安装依赖
```bash
pip install locust
```

### 2. 运行压测
```bash
# 默认运行所有场景
./run-benchmark.sh

# 指定目标URL
./run-benchmark.sh http://your-server:8000
```

### 3. 查看报告
报告生成在 `reports/` 目录下：
- `light-load-report.html` - 轻负载场景报告
- `medium-load-report.html` - 中等负载场景报告
- `heavy-load-report.html` - 高负载场景报告
- `stats.json` - 原始统计数据

## 测试场景

### 轻负载场景
- 用户数: 50
- 每秒新增: 10
- 持续时间: 5分钟
- 目标: 验证系统在正常负载下的表现

### 中等负载场景
- 用户数: 100
- 每秒新增: 20
- 持续时间: 5分钟
- 目标: 验证系统在中等负载下的稳定性

### 高负载场景
- 用户数: 200
- 每秒新增: 40
- 持续时间: 5分钟
- 目标: 发现系统瓶颈和极限

## API端点覆盖
测试覆盖以下关键API：
1. `/api/v1/auth/login` - 用户登录
2. `/api/v1/stations` - 充电站列表
3. `/api/v1/devices` - 设备列表
4. `/api/v1/alarms` - 告警列表
5. `/api/v1/workorders` - 工作单创建
6. `/api/v1/telemetry/latest` - 遥测数据
7. `/api/v1/energy/report` - 能耗报告

## 性能指标
- **响应时间**: 平均、P95、P99
- **错误率**: HTTP 5xx错误、超时错误
- **吞吐量**: 每秒请求数(RPS)
- **资源使用**: CPU、内存、网络、数据库连接

## 配置说明
见 `benchmark-config.yml` 文件，可调整：
- 压测持续时间
- 用户数量和增长速率
- 性能阈值
- 报告格式

## 生成报告
运行压测后，使用模板生成详细报告：
```bash
# 手动生成报告（需填充数据）
cp performance-report-template.md performance-report-$(date +%Y%m%d).md
```

## 注意事项
1. 压测前确保目标系统已启动
2. 建议在非生产环境执行
3. 监控系统资源使用情况
4. 根据结果调整配置和优化策略

## 自动化集成
可集成到CI/CD流水线，作为质量门禁的一部分。