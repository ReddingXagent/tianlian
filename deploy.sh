#!/bin/bash
# 天链V3 边缘网关一键部署脚本
# 在树莓派上运行: bash deploy.sh
set -e

echo "=== 天链V3 边缘网关部署 ==="

# 配置
REPO_DIR="/home/tl/tianlian-v3-edge-gateway"
PYTHON="python3"
PORT=8080

# 1. 检查 Python
echo "[1/6] 检查环境..."
$PYTHON --version || { echo "需要 Python 3.10+"; exit 1; }

# 2. 安装依赖
echo "[2/6] 安装依赖..."
cd "$REPO_DIR"
$PYTHON -m pip install -q httpx uvicorn fastapi 2>/dev/null || {
    echo "依赖安装失败，尝试用户级安装..."
    $PYTHON -m pip install --user -q httpx uvicorn fastapi
}

# 3. 配置环境变量
echo "[3/6] 配置..."
cat > .env << 'ENVEOF'
# 天链V3边缘网关环境变量
CLOUD_BASE_URL=http://8.134.106.166
CLOUD_TOKEN=eyJhbG…Uzwg
GATEWAY_ID=GW-001
GATEWAY_NAME=RaspberryPi-Gateway
ENVEOF

# 4. 数据库迁移
echo "[4/6] 数据库迁移..."
$PYTHON migrate_db.py 2>/dev/null || echo "数据库已是最新或迁移跳过"

# 5. 停止旧服务
echo "[5/6] 停止旧服务..."
OLD_PID=$(pgrep -f "main.py" 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
    kill $OLD_PID 2>/dev/null || true
    sleep 2
fi

# 6. 启动服务
echo "[6/6] 启动边缘网关..."
nohup $PYTHON main.py > /tmp/tianlian-gateway.log 2>&1 &
NEW_PID=$!

sleep 3

# 验证
if kill -0 $NEW_PID 2>/dev/null; then
    echo ""
    echo "✅ 部署成功！PID: $NEW_PID"
    echo "   健康检查: http://$(hostname -I | awk '{print $1}'):$PORT/health"
    echo "   日志: /tmp/tianlian-gateway.log"
    # 快速验证
    sleep 1
    curl -s http://localhost:$PORT/health 2>/dev/null && echo "" || echo "⚠️ 健康检查失败，请查看日志"
else
    echo "❌ 启动失败，请查看日志:"
    cat /tmp/tianlian-gateway.log
    exit 1
fi