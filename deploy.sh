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
# v5 (2026-08-04 自驱部署轮):
#   - fix: rollback 语义bug — `git revert $REV` 只撤销单个commit, 与"回滚到REV"
#     语义不符(落后N个commit时只撤1个, 其余N-1个坏提交仍在) → 改
#     `git revert ${REV}..HEAD` 撤销目标好版本之后的全部提交, 工作区=REV状态;
#     增加 无效commit/REV即HEAD/revert冲突(自动abort) 三重防护
# v6 (2026-08-04 自驱部署轮, 冲突路径实测):
#   - fix: rollback stash黑洞 — v5先 stash 脏改动再revert, 但失败路径声称"恢复现场"
#     却不pop stash(用户未提交改动看似丢失), 成功路径也不提stash去向 →
#     记录stash计数, 失败时自动 git stash pop 真正恢复现场, 成功时提示 stash@{0}
#   - fix: revert失败提示只说"冲突", 实际范围含merge commit时(无-m)也会失败 →
#     提示补merge commit场景与手动处理指引
# v7 (2026-08-04 自驱部署轮):
#   - fix: 步骤5迁移脚本真缺口 — migrate_db.py 只补 cloud_synced/priority 两列,
#     旧schema库缺 cached_at/retry_count/synced 时迁移后仍不全, 运行时查询即
#     "no such column" 崩; 实测对比(旧schema临时库两脚本各跑+幂等复跑)确认
#     db_migration.py 全量补齐且幂等 → 切换 migrate_db.py→db_migration.py
# v8 (2026-08-04 自驱部署轮):
#   - fix: 步骤5迁移失败黑洞 — 旧写法 `2>/dev/null || echo` 吞掉真失败(db_migration.py
#     失败exit 1), 带病继续 → 杀旧服务起新代码, 旧schema库运行时"no such column"崩
#     → 迁移失败即中止部署(此时旧服务未停, 零影响)
#   - 新增: 迁移前自动备份 data/gateway.db → data/backups/gateway.db.<时间戳>.bak
#     (同秒重跑追加后缀不覆盖旧备份; 仅保留最近5份), 回滚/坏迁移后可用新子命令
#     restore-db 恢复
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

# F217: systemd模式探测 — unit已安装(make systemd-install)时, 停/启必须走systemctl:
# pgrep+kill后Restart=always会在5秒内复活进程, 再nohup双启→端口竞争/重启风暴;
# restore-db同理须停unit, 否则复活进程立即写回刚恢复的库。
# TIANLIAN_UNIT_FILE可环境变量覆盖(测试钩子, 生产默认Pi路径)。
UNIT_FILE="${TIANLIAN_UNIT_FILE:-/etc/systemd/system/tianlian-gateway.service}"
SYSTEMD_MODE=false
if [ -f "$UNIT_FILE" ]; then
    SYSTEMD_MODE=true
fi

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
    if ! git rev-parse --verify "$REV^{commit}" >/dev/null 2>&1; then
        echo "❌ 无效commit: $REV"; exit 1
    fi
    RANGE="${REV}..HEAD"
    N=$(git rev-list --count "$RANGE" 2>/dev/null || echo 0)
    if [ "$N" -eq 0 ]; then
        echo "ℹ️ $REV 就是当前HEAD, 无需回滚"; exit 0
    fi
    echo "回滚到: $REV (revert其后 $N 个提交)"
    git rev-list --oneline "$RANGE" | sed 's/^/  revert: /'
    # 脏工作区先stash(revert需干净树); 记录计数以判断是否真的产生了stash
    STASH_CNT_BEFORE=$(git stash list | wc -l)
    git stash --include-untracked 2>/dev/null || true
    STASH_CNT_AFTER=$(git stash list | wc -l)
    STASHED=false
    if [ "$STASH_CNT_AFTER" -gt "$STASH_CNT_BEFORE" ]; then STASHED=true; fi
    if ! git revert --no-commit "$RANGE"; then
        git revert --abort 2>/dev/null || true
        if [ "$STASHED" = true ]; then
            if git stash pop 2>/dev/null; then
                echo "ℹ️ 回滚前的未提交改动已恢复(stash pop)"
            else
                echo "⚠️ stash恢复失败, 请手动: git stash pop"
            fi
        fi
        echo "❌ revert失败(冲突, 或范围含merge commit需-m), 已自动中止并恢复现场"
        echo "   如范围含merge commit, 需手动逐段: git revert -m 1 <merge-hash> ..."
        exit 1
    fi
    echo "已 revert $REV 之后的 $N 个提交, 工作区已等于 $REV 状态(改动已暂存未提交)"
    if [ "$STASHED" = true ]; then
        echo "ℹ️ 回滚前的未提交改动保存在 stash@{0}(回滚需干净工作区)"
        echo "   如需找回: git stash pop (注意: 可能与回滚后状态冲突)"
    fi
    echo "重新部署验证: bash deploy.sh"
    echo "确认无误后: git commit -m 'rollback to $REV' && git push origin master"
    exit 0
fi

# 子命令: restore-db (恢复迁移前备份; 默认用最新一份)
if [ "$1" = "restore-db" ]; then
    echo "=== 天链V3 边缘网关数据库恢复 ==="
    cd "$REPO_DIR"
    DB_FILE="data/gateway.db"
    LATEST="$(ls -1t data/backups/gateway.db.*.bak 2>/dev/null | head -1 || true)"
    BAK="${2:-$LATEST}"
    if [ -z "$BAK" ]; then
        echo "❌ data/backups/ 下无 gateway.db 备份"; exit 1
    fi
    if [ ! -f "$BAK" ]; then
        echo "❌ 备份不存在: $BAK"; exit 1
    fi
    echo "恢复源: $BAK → $DB_FILE"
    # 先停服务防止写库(sqlite写锁/覆盖)
    if [ "$SYSTEMD_MODE" = true ]; then
        # F217: systemd下必须停unit — pgrep+kill会被Restart=always在5秒内复活,
        # 与cp恢复竞速, 复活进程立即写回旧连接致恢复无效
        if ! sudo systemctl stop tianlian-gateway; then
            echo "❌ systemd服务停止失败(需sudo权限操作systemctl)"; exit 1
        fi
        echo "已停止网关(systemd unit)"
    else
        OLD_PID=$(pgrep -f "$REPO_DIR/main.py" 2>/dev/null || true)
        if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
            kill "$OLD_PID" 2>/dev/null || true
            sleep 2
            if kill -0 "$OLD_PID" 2>/dev/null; then
                kill -9 "$OLD_PID" 2>/dev/null || true
            fi
            echo "已停止网关(PID $OLD_PID)"
        fi
    fi
    mkdir -p data
    cp "$BAK" "$DB_FILE"
    if [ "$SYSTEMD_MODE" = true ]; then
        sudo systemctl start tianlian-gateway
        echo "✅ 已恢复数据库并重启服务(systemd模式, 日志: journalctl -u tianlian-gateway)"
    else
        echo "✅ 已恢复数据库。重启服务: bash deploy.sh"
    fi
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

# 5. 数据库迁移(用 db_migration.py 全量schema对齐版; 旧 migrate_db.py 只补
#    cloud_synced/priority 两列, 会漏 cached_at/retry_count/synced 致旧库运行时报错)
#    v8: 迁移前自动备份(保留最近5份) + 失败即中止(此时旧服务未停, 零影响);
#    db_migration.py 幂等, 成功恒exit 0, 真失败exit 1 — 不允许吞错
echo "[5/7] 数据库迁移..."
DB_FILE="data/gateway.db"
if [ -f "$DB_FILE" ]; then
    mkdir -p data/backups
    TS=$(date +%Y%m%d%H%M%S)
    BAK="data/backups/gateway.db.$TS.bak"
    # 同秒重跑防碰撞: 目标已存在则追加 -1/-2 后缀, 绝不覆盖旧备份
    SUFFIX=1
    while [ -f "$BAK" ]; do
        BAK="data/backups/gateway.db.$TS-$SUFFIX.bak"
        SUFFIX=$((SUFFIX + 1))
    done
    if cp "$DB_FILE" "$BAK"; then
        echo "已备份: $BAK"
    else
        echo "❌ 数据库备份失败, 中止部署(宁可不部署不可无退路)"; exit 1
    fi
    # 只保留最近5份备份
    ls -1t data/backups/gateway.db.*.bak 2>/dev/null | tail -n +6 | xargs -r rm -f
fi
if ! $PYTHON db_migration.py; then
    echo "❌ 迁移失败, 中止部署(旧服务未受影响; 如需恢复: bash deploy.sh restore-db)"
    exit 1
fi

# 6. 停止旧服务(systemd模式停unit; 直跑模式精确匹配本目录 main.py)
echo "[6/7] 停止旧服务..."
if [ "$SYSTEMD_MODE" = true ]; then
    # F217: pgrep+kill会被Restart=always在5秒内复活, 与步骤7 nohup双启撞端口
    if ! sudo systemctl stop tianlian-gateway; then
        echo "❌ systemd服务停止失败"; exit 1
    fi
else
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

# 7. 启动服务(systemd模式委托unit, EnvironmentFile自载.env; 直跑模式加载.env到环境变量)
echo "[7/7] 启动边缘网关..."
if [ "$SYSTEMD_MODE" != true ] && [ -f .env ]; then
    set -a
    . .env
    set +a
fi
start_gateway() {
    if [ "$SYSTEMD_MODE" = true ]; then
        # F217: systemd模式绝不nohup双启(端口竞争/重启风暴)
        if ! sudo systemctl start tianlian-gateway; then
            echo "❌ systemd启动失败(systemctl start)"; exit 1
        fi
        NEW_PID="$(systemctl show -p MainPID --value tianlian-gateway 2>/dev/null || echo 0)"
    else
        # 绝对路径启动: 进程 cmdline 含完整路径, pgrep -f "$REPO_DIR/main.py" 才能精确匹配
        nohup $PYTHON "$REPO_DIR/main.py" > gateway.log 2>&1 &
        NEW_PID=$!
        echo "$NEW_PID" > .pid
    fi
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
    if [ "$SYSTEMD_MODE" = true ]; then
        echo "   日志: journalctl -u tianlian-gateway -f (systemd模式, 无gateway.log)"
    else
        echo "   日志: $REPO_DIR/gateway.log"
    fi
    sleep 1
    curl -s -m 5 "http://localhost:$PORT/health" 2>/dev/null && echo "" || echo "⚠️ 健康检查失败, 请查看日志"

    # 检测 systemd 可用性并给出迁移建议(已在systemd模式则无需提示)
    if [ "$SYSTEMD_MODE" != true ] && systemctl is-system-running >/dev/null 2>&1; then
        if [ ! -f "$UNIT_FILE" ]; then
            echo ""
            echo "💡 建议: 安装 systemd 服务实现开机自启+崩溃重启"
            echo "   make systemd-install   # 路径自动适配当前仓库目录(F211)"
            echo "   详见: systemd/README.md"
        fi
    fi

    # 日志轮转提示
    if [ ! -f /etc/logrotate.d/tianlian-gateway ]; then
        echo ""
        echo "💡 建议: 安装日志轮转防磁盘占满"
        echo "   make systemd-install   # 一并安装logrotate配置, 路径自动适配(F211)"
    fi
else
    echo "❌ 启动失败, 日志最后20行:"
    tail -20 gateway.log
    exit 1
fi
