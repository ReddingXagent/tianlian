#!/bin/bash
# 天链V3 边缘网关一键部署脚本
# 在树莓派上运行: bash deploy.sh
#
# v2 (2026-07-31 自驱部署验证轮, 树莓派192.168.31.10实测修):
#   - fix: REPO_DIR 旧值 /home/tl/tianlian-v3-edge-gateway 在Pi上不存在(实际是
#     tianlian-edge-gateway-v3), cd失败+set -e 使脚本第2步即死 → 改为自动探测
#   - fix: 依赖安装只装 httpx/uvicorn/fastapi 3个, 缺 ocpp/pymodbus/paho-mqtt/
#     aiosqlite 等11个 → 全新部署import即崩 → 改为 pip install -r requirements.txt
#   - fix: 步骤3无条件覆写 .env 且硬编码已过期token(尾PUzwg), 会冲掉正确配置
#     (云端07-24已重签token) → 改为 .env 存在即保留, 缺失才生成模板(不含真token)
#   - 新增: .git 存在时 git fetch+ff-only 同步(兼容 remote 名 synology/origin),
#     失败不阻塞(Pi→NAS 无免密时降级为部署当前代码)
#   - 改进: pgrep 精确匹配本目录 main.py; 日志写 gateway.log(Pi现状); .pid 记录
# v3 (2026-08-01 自驱部署验证轮):
#   - fix: 步骤6杀旧进程后端口8080未完全释放→新服务uvicorn bind失败SystemExit
#     增加端口等待释放循环(最多10秒), 确保bind前端口可用
#   - fix: 步骤7启动后只等3秒, 改为轮询健康检查(最多15秒)
#   - fix: 首次启动失败时自动重试一次(等待2秒后)
# v4 (2026-08-04 自驱部署轮):
#   - fix: status子命令 pgrep -f 'main.py' 匹配过宽(会命中任意目录的main.py) →
#     改用 "$REPO_DIR/main.py" 精确匹配; REPO_DIR探测提前到子命令之前
#   - fix: 启动用相对路径 main.py → cmdline 不含路径, step6/watchdog 的
#     pgrep "$REPO_DIR/main.py" 永不命中(杀旧靠.pid/fuser兑底) → 改绝对路径启动
#   - 新增: Python 版本预检(<3.10 告警不阻断)
set -e

# 配置: 仓库目录自动探测(脚本所在目录优先, 回退Pi实际路径)
# 注意: 必须在子命令前探测, status/rollback 依赖 REPO_DIR 做精确进程匹配
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/main.py" ]; then
    REPO_DIR="$SCRIPT_DIR"
elif [ -d /home/tl/tianlian-edge-gateway-v3 ]; then
    REPO_DIR=/home/tl/tianlian-edge-gateway-v3
else
    echo "❌ 未找到仓库目录(需含 main.py)"; exit 1
fi
PYTHON="python3"
PORT="${PORT:-8080}"

# 子命令: rollback
if [ "$1" = "rollback" ]; then
    echo "=== 天链V3 边缘网关回滚 ==="
    cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    echo "最近5次提交:"
    git log --oneline -5
    echo ""
    if [ -z "$2" ]; then
        echo "用法: bash deploy.sh rollback <commit-hash>"
        echo "例如: bash deploy.sh rollback abc1234"
        exit 0
    fi
    REV="$2"
    echo "回滚到: $REV"
    git stash --include-untracked 2>/dev/null || true
    git revert --no-commit "$REV"
    echo "已 revert $REV"
    echo "重新部署: bash deploy.sh"
    echo "推送远程: git push origin master"
    exit 0
fi

# 子命令: status
if [ "$1" = "status" ]; then
    echo "=== 天链V3 边缘网关状态 ==="
    PID="$(pgrep -f "$REPO_DIR/main.py" 2>/dev/null || echo '未运行')"
    echo "PID: $PID"
    curl -s -m 3 "http://localhost:$PORT/health" 2>/dev/null && echo "" || echo "健康检查: 不可达"
    curl -s -m 3 "http://localhost:$PORT/api/v1/status" 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "状态API: 不可达"
    echo "日志最后10行:"
    tail -10 "$REPO_DIR/gateway.log" 2>/dev/null || echo "(无日志)"
    exit 0
fi

echo "=== 天链V3 边缘网关部署 === ($REPO_DIR)"

# 1. 检查 Python
echo "[1/7] 检查环境..."
$PYTHON --version || { echo "需要 Python 3.10+"; exit 1; }
PY_VER=$($PYTHON -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")
PY_MAJOR=${PY_VER%%.*}; PY_MINOR=${PY_VER#*.}
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "⚠️ Python $PY_VER < 3.10 (README要求3.10+), 继续部署但可能有兼容问题"
fi

cd "$REPO_DIR"

# 2. 同步代码(失败不阻塞)
echo "[2/7] 同步代码..."
if [ -d .git ]; then
    REMOTE=$(git remote | grep -E '^(synology|origin)$' | head -1 || true)
    if [ -n "$REMOTE" ] && git fetch "$REMOTE" 2>/dev/null; then
        if git merge --ff-only "$REMOTE/master" 2>/dev/null; then
            echo "已同步: $(git rev-parse --short HEAD)"
        else
            echo "⚠️ ff合并失败(本地有分叉?), 部署当前代码"
        fi
    else
        echo "⚠️ fetch失败(检查NAS免密), 部署当前代码"
    fi
else
    echo "非git仓库, 跳过同步"
fi

# 3. 安装依赖(requirements.txt 全量)
echo "[3/7] 安装依赖..."
$PYTHON -m pip install -q -r requirements.txt 2>/dev/null || {
    echo "系统级安装失败, 尝试 --user..."
    $PYTHON -m pip install --user -q -r requirements.txt
}

# 4. 环境变量(绝不覆写已有 .env)
echo "[4/7] 配置..."
if [ -f .env ]; then
    echo ".env 已存在, 保留不动"
else
    cat > .env << 'ENVEOF'
# 天链V3边缘网关环境变量(模板, 填好token再启动)
CLOUD_BASE_URL=http://8.134.106.166
CLOUD_TOKEN=*** 云端签发长期token, user=edge_gateway_telemetry>
GATEWAY_ID=GW-001
GATEWAY_NAME=RaspberryPi-Gateway
ENVEOF
    echo "⚠️ 已生成 .env 模板, 启动前必须填写 CLOUD_TOKEN"
fi

# 5. 数据库迁移
echo "[5/7] 数据库迁移..."
$PYTHON migrate_db.py 2>/dev/null || echo "数据库已是最新或迁移跳过"

# 6. 停止旧服务(精确匹配本目录 main.py)
echo "[6/7] 停止旧服务..."
OLD_PID=$(pgrep -f "$REPO_DIR/main.py" 2>/dev/null || true)
if [ -z "$OLD_PID" ] && [ -f .pid ]; then
    OLD_PID="$(cat .pid 2>/dev/null || true)"
fi
if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 2
    # 确保进程终止
    if kill -0 "$OLD_PID" 2>/dev/null; then
        kill -9 "$OLD_PID" 2>/dev/null || true
        sleep 1
    fi
fi

# 等待端口释放(最多10秒)
WAIT_CNT=0
while [ $WAIT_CNT -lt 10 ]; do
    if ! ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
        break
    fi
    echo "等待端口 $PORT 释放... ($((WAIT_CNT + 1))/10)"
    sleep 1
    WAIT_CNT=$((WAIT_CNT + 1))
done
if [ $WAIT_CNT -ge 10 ]; then
    echo "⚠️ 端口 $PORT 仍未释放, 强制fuser kill"
    fuser -k "${PORT}/tcp" 2>/dev/null || true
    sleep 2
fi

# 7. 启动服务(加载.env到环境变量)
echo "[7/7] 启动边缘网关..."
if [ -f .env ]; then
    set -a
    . .env
    set +a
fi
start_gateway() {
    # 绝对路径启动: 进程 cmdline 含完整路径, pgrep -f "$REPO_DIR/main.py" 才能精确匹配
    nohup $PYTHON "$REPO_DIR/main.py" > gateway.log 2>&1 &
    NEW_PID=$!
    echo "$NEW_PID" > .pid
}

start_gateway

# 轮询健康检查(最多15秒)
HEALTH_OK=false
for i in $(seq 1 15); do
    sleep 1
    if ! kill -0 "$NEW_PID" 2>/dev/null; then
        echo "⚠️ 进程退出(第1次), 等待2秒重试..."
        if [ $i -le 5 ]; then
            sleep 2
            start_gateway
            continue
        else
            break
        fi
    fi
    if curl -s -m 2 "http://localhost:$PORT/health" >/dev/null 2>&1; then
        HEALTH_OK=true
        break
    fi
done

# 验证
if [ "$HEALTH_OK" = true ] && kill -0 "$NEW_PID" 2>/dev/null; then
    echo ""
    echo "✅ 部署成功! PID: $NEW_PID"
    echo "   健康检查: http://$(hostname -I | awk '{print $1}'):$PORT/health"
    echo "   运行状态: http://localhost:$PORT/api/v1/status"
    echo "   日志: $REPO_DIR/gateway.log"
    sleep 1
    curl -s -m 5 "http://localhost:$PORT/health" 2>/dev/null && echo "" || echo "⚠️ 健康检查失败, 请查看日志"

    # 检测 systemd 可用性并给出迁移建议
    if systemctl is-system-running >/dev/null 2>&1; then
        if [ ! -f /etc/systemd/system/tianlian-gateway.service ]; then
            echo ""
            echo "💡 建议: 安装 systemd 服务实现开机自启+崩溃重启"
            echo "   sudo cp systemd/tianlian-gateway.service /etc/systemd/system/"
            echo "   sudo systemctl daemon-reload && sudo systemctl enable tianlian-gateway"
            echo "   详见: systemd/README.md"
        else
            echo ""
            echo "ℹ️ systemd 服务已安装, 建议用 systemctl 管理:"
            echo "   sudo systemctl restart tianlian-gateway"
        fi
    fi

    # 日志轮转提示
    if [ ! -f /etc/logrotate.d/tianlian-gateway ]; then
        echo ""
        echo "💡 建议: 安装日志轮转防磁盘占满"
        echo "   sudo cp systemd/logrotate.conf /etc/logrotate.d/tianlian-gateway"
    fi
else
    echo "❌ 启动失败, 日志最后20行:"
    tail -20 gateway.log
    exit 1
fi
