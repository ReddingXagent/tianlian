#!/bin/bash
# 性能压测执行脚本

echo "=== 天链V3性能压测脚本 ==="

# 检查环境
if ! command -v locust &> /dev/null; then
    echo "安装Locust..."
    pip install locust
fi

# 创建报告目录
mkdir -p reports

# 设置基础URL
BASE_URL=${1:-http://localhost:8000}

echo "压测目标: $BASE_URL"
echo "持续时间: 5分钟"

# 执行轻负载场景
echo "=== 场景1: 轻负载 (50用户) ==="
locust -f locustfile.py --host $BASE_URL --users 50 --spawn-rate 10 --run-time 5m --headless --html reports/light-load-report.html

# 执行中等负载场景
echo "=== 场景2: 中等负载 (100用户) ==="
locust -f locustfile.py --host $BASE_URL --users 100 --spawn-rate 20 --run-time 5m --headless --html reports/medium-load-report.html

# 执行高负载场景
echo "=== 场景3: 高负载 (200用户) ==="
locust -f locustfile.py --host $BASE_URL --users 200 --spawn-rate 40 --run-time 5m --headless --html reports/heavy-load-report.html

echo "=== 压测完成 ==="
echo "报告生成: reports/*.html"
echo "JSON数据: reports/stats.json"

# 汇总报告
echo "汇总性能指标..."
locust -f locustfile.py --host $BASE_URL --users 50 --spawn-rate 10 --run-time 1m --headless --json reports/stats.json