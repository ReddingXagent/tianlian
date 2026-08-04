#!/bin/bash
# 天链V3 边缘网关 — 看门狗脚本
# 用途: 在无 systemd 的环境下（如裸跑 nohup），定时检测网关存活并自动重启
# 使用: crontab -e → */2 * * * * /path/to/watchdog.sh
# 或:   nohup ./watchdog.sh --loop > /dev/null 2>&1 &
#
# 原理:
#   1. curl /health，HTTP 200 = 存活
#   2. 失败 → 检查进程 → 进程死了则重启
#   3. 进程活着但 /health 不响应（卡死）→ kill 后重启
#   4. 连续 3 次重启失败 → 告警日志，放弃本轮

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"  # scripts/ 的上一级=仓库根

# F205: flock互斥 — cron单次模式下恢复窗口(~75s=3次×健康等待+RESTART_DELAY)可能跨cron触发周期,
# 无锁时两个实例并发重启: 双启gateway, 后启者覆盖.pid致先启进程成孤儿(占着端口但pid失联),
# 且后来者端口冲突反复失败. 拿不到锁=另一实例正在恢复, 直接跳过本轮.
exec 9>"$REPO_DIR/.watchdog.lock"
if ! flock -n 9; then
    exit 0
fi

PORT="${PORT:-8080}"
HEALTH_URL="http://localhost:${PORT}/health"
PID_FILE="$REPO_DIR/.pid"
LOG_FILE="$REPO_DIR/gateway.log"
MAX_RESTART_ATTEMPTS=3
RESTART_DELAY=5

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [watchdog] $*" >> "$LOG_FILE"; }

# 检查健康
check_health() {
    curl -sf -m 5 "$HEALTH_URL" >/dev/null 2>&1
}

# 获取当前 PID
get_pid() {
    if [ -f "$PID_FILE" ]; then
        local p; p=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
            echo "$p"; return 0
        fi
    fi
    # 回退: pgrep
    pgrep -f "$REPO_DIR/main.py" 2>/dev/null | head -1 || true
}

# 停止进程
stop_process() {
    local pid="$1"
    [ -z "$pid" ] && return 0
    kill "$pid" 2>/dev/null || true
    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
        sleep 1
    fi
    log "已停止 PID $pid"
}

# 启动网关
start_gateway() {
    cd "$REPO_DIR"
    # 加载 .env
    if [ -f .env ]; then set -a; . .env; set +a; fi
    # 绝对路径启动: cmdline 含完整路径, get_pid 的 pgrep 才能精确匹配
    nohup python3 "$REPO_DIR/main.py" >> "$LOG_FILE" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"
    log "已启动 PID $new_pid"
    # 等待健康
    for i in $(seq 1 15); do
        sleep 1
        if check_health; then
            log "健康检查通过"
            return 0
        fi
        if ! kill -0 "$new_pid" 2>/dev/null; then
            log "❌ 进程退出"
            return 1
        fi
    done
    log "❌ 健康检查超时"
    return 1
}

# 主逻辑
main() {
    local current_pid; current_pid=$(get_pid)

    # 健康 → 无事发生
    if check_health; then
        exit 0
    fi

    log "⚠️ 健康检查失败，尝试恢复..."

    # 进程存活但不响应 → 强杀
    if [ -n "$current_pid" ]; then
        log "进程 $current_pid 存活但不响应，强制重启"
        stop_process "$current_pid"
    fi

    # 等端口释放
    for i in $(seq 1 5); do
        ss -tlnp 2>/dev/null | grep -q ":${PORT} " || break
        sleep 1
    done

    # 重试
    local attempt=0
    while [ $attempt -lt $MAX_RESTART_ATTEMPTS ]; do
        attempt=$((attempt + 1))
        log "重启尝试 $attempt/$MAX_RESTART_ATTEMPTS"
        if start_gateway; then
            log "✅ 恢复成功"
            exit 0
        fi
        sleep "$RESTART_DELAY"
    done

    log "❌ 连续 ${MAX_RESTART_ATTEMPTS} 次重启失败，放弃 — 请人工介入"
    exit 1
}

# --loop 模式：常驻循环（适合 nohup 后台运行）
if [ "${1:-}" = "--loop" ]; then
    log "看门狗启动 (--loop 模式, 间隔 60s)"
    while true; do
        main || true
        sleep 60
    done
else
    # 单次模式（适合 crontab）
    main
fi
