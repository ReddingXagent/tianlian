#!/bin/bash
# 天链 V3 性能监控脚本 - 完整版
# 功能：健康检查、性能指标、告警触发、日志记录

set -e

# 配置
API_BASE="http://demo.example.com/api/v1"
LOG_DIR="/var/log/tianlian"
ALERT_THRESHOLD_CPU=80
ALERT_THRESHOLD_MEM=90
ALERT_THRESHOLD_DISK=95

# 创建日志目录
mkdir -p "$LOG_DIR"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_DIR/monitor.log"
}

alert() {
    echo "${RED}[ALERT] $1${NC}" | tee -a "$LOG_DIR/alerts.log"
    # 可扩展：IM通知、邮件通知
    # curl -X POST "https://open.im.cn/open-apis/bot/v2/hook/xxx" -d '{"msg_type":"text","content":{"text":"$1"}}'
}

# 1. API健康检查
check_api_health() {
    log "检查API健康状态..."
    
    HEALTH=$(curl -s "$API_BASE/health")
    STATUS=$(echo "$HEALTH" | jq -r '.status' 2>/dev/null || echo "unknown")
    
    if [ "$STATUS" == "healthy" ]; then
        log "${GREEN}✅ API健康检查通过${NC}"
        return 0
    else
        alert "❌ API健康检查失败: $HEALTH"
        return 1
    fi
}

# 2. 数据库健康检查
check_database() {
    log "检查数据库连接..."
    
    DB_PATH="/opt/tianlian-v3/backend/tianlian_v3.db"
    if [ -f "$DB_PATH" ]; then
        SIZE=$(du -h "$DB_PATH" | cut -f1)
        log "${GREEN}✅ 数据库正常 (大小: $SIZE)${NC}"
        
        # 检查表完整性
        sqlite3 "$DB_PATH" "PRAGMA integrity_check;" > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            log "${GREEN}✅ 数据库完整性检查通过${NC}"
        else
            alert "❌ 数据库完整性检查失败"
        fi
    else
        alert "❌ 数据库文件不存在"
    fi
}

# 3. 系统性能监控
check_system_performance() {
    log "检查系统性能..."
    
    # CPU使用率
    CPU=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')
    log "CPU使用率: ${CPU}%"
    
    if [ "${CPU%.*}" -ge $ALERT_THRESHOLD_CPU ]; then
        alert "⚠️ CPU使用率过高: ${CPU}%"
    fi
    
    # 内存使用率
    MEM=$(free | grep Mem | awk '{print ($3/$2) * 100.0}')
    log "内存使用率: ${MEM}%"
    
    if [ "${MEM%.*}" -ge $ALERT_THRESHOLD_MEM ]; then
        alert "⚠️ 内存使用率过高: ${MEM}%"
    fi
    
    # 磁盘使用率
    DISK=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    log "磁盘使用率: ${DISK}%"
    
    if [ "$DISK" -ge $ALERT_THRESHOLD_DISK ]; then
        alert "⚠️ 磁盘使用率过高: ${DISK}%"
    fi
}

# 4. API响应时间监控
check_api_performance() {
    log "检查API响应时间..."
    
    # 关键API响应时间
    endpoints=(
        "/health"
        "/stations"
        "/devices"
        "/alarms"
    )
    
    for endpoint in "${endpoints[@]}"; do
        START=$(date +%s%3N)
        curl -s "$API_BASE$endpoint" > /dev/null
        END=$(date +%s%3N)
        DURATION=$((END - START))
        
        log "API $endpoint: ${DURATION}ms"
        
        if [ "$DURATION" -gt 1000 ]; then
            alert "⚠️ API响应过慢: $endpoint (${DURATION}ms)"
        fi
    done
}

# 5. 错误日志监控
check_error_logs() {
    log "检查错误日志..."
    
    ERROR_COUNT=$(grep -c "ERROR" "$LOG_DIR/*.log" 2>/dev/null || echo "0")
    
    if [ "$ERROR_COUNT" -gt 10 ]; then
        alert "⚠️ 错误日志过多: $ERROR_COUNT 条"
    else
        log "${GREEN}✅ 错误日志正常 ($ERROR_COUNT 条)${NC}"
    fi
}

# 6. WebSocket连接检查
check_websocket() {
    log "检查WebSocket连接..."
    
    # 检查WebSocket端口是否监听
    WS_PORT=$(netstat -tlnp 2>/dev/null | grep ":8000" | wc -l)
    
    if [ "$WS_PORT" -gt 0 ]; then
        log "${GREEN}✅ WebSocket服务正常监听${NC}"
    else
        alert "❌ WebSocket服务未监听"
    fi
}

# 7. 统计数据汇总
generate_stats() {
    log "生成监控统计..."
    
    STATS_FILE="$LOG_DIR/stats_$(date +%Y%m%d).json"
    
    cat > "$STATS_FILE" <<EOF
{
    "timestamp": "$(date -Iseconds)",
    "api_health": "$(curl -s $API_BASE/health | jq -r '.status')",
    "cpu_usage": "${CPU}",
    "memory_usage": "${MEM}",
    "disk_usage": "${DISK}",
    "uptime": "$(uptime -p)",
    "alerts_count": $(wc -l < "$LOG_DIR/alerts.log" 2>/dev/null || echo 0)
}
EOF
    
    log "${GREEN}✅ 统计数据已保存: $STATS_FILE${NC}"
}

# 主循环
main() {
    log "========================================="
    log "天链 V3 监控启动"
    log "========================================="
    
    check_api_health
    check_database
    check_system_performance
    check_api_performance
    check_error_logs
    check_websocket
    generate_stats
    
    log "========================================="
    log "监控完成"
    log "========================================="
}

# 定时执行模式
if [ "$1" == "--daemon" ]; then
    while true; do
        main
        sleep 300  # 5分钟检查一次
    done
else
    main
fi