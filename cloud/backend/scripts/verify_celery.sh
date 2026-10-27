#!/bin/bash
# Phase 12 - Celery Worker 验证脚本
# 用途: 验证Celery Worker正常运行并能执行异步任务

set -e

API_BASE="http://localhost:8000/api/v1"

echo "===== Celery Worker 验证 ====="

# 1. 检查Worker状态
echo "1. 检查Worker状态..."
STATUS=$(curl -s ${API_BASE}/tasks/status)
echo "$STATUS" | python3 -m json.tool

WORKER_STATUS=$(echo "$STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin)['data']['status'])")

if [ "$WORKER_STATUS" != "running" ]; then
    echo "❌ Celery Worker未运行: $WORKER_STATUS"
    echo "请先启动Worker: sudo systemctl start celery-worker"
    exit 1
fi

echo "✅ Celery Worker运行正常"

# 2. 检查可用任务类型
echo ""
echo "2. 检查可用任务类型..."
curl -s ${API_BASE}/tasks/types | python3 -m json.tool

# 3. 提交测试任务 (健康评分)
echo ""
echo "3. 提交测试任务: health_score..."
TASK_RESPONSE=$(curl -s -X POST ${API_BASE}/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{"task_type":"health_score","params":{"device_id":1,"days":7}}')

echo "$TASK_RESPONSE" | python3 -m json.tool

TASK_ID=$(echo "$TASK_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['data']['task_id'])")

if [ -z "$TASK_ID" ]; then
    echo "❌ 任务提交失败"
    exit 1
fi

echo "✅ 任务已提交: $TASK_ID"

# 4. 等待任务完成
echo ""
echo "4. 等待任务完成..."
for i in {1..30}; do
    RESULT=$(curl -s ${API_BASE}/tasks/result/${TASK_ID})
    STATUS=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['data']['status'])")
    
    if [ "$STATUS" == "SUCCESS" ]; then
        echo "✅ 任务执行成功"
        echo "$RESULT" | python3 -m json.tool
        exit 0
    elif [ "$STATUS" == "FAILURE" ]; then
        echo "❌ 任务执行失败"
        echo "$RESULT" | python3 -m json.tool
        exit 1
    fi
    
    echo "[$i/30] 任务状态: $STATUS, 等待中..."
    sleep 2
done

echo "⚠️ 任务超时(60秒)"
exit 1