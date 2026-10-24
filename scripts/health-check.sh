#!/usr/bin/env bash
# ─── 天链V3 全面健康检查脚本 ───
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
PASS="✓"; FAIL="✗"; WARN="!"

# 配置 (可通过环境变量覆盖)
API_URL="${API_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3004}"
NGINX_URL="${NGINX_URL:-http://localhost:80}"
TIMEOUT="${TIMEOUT:-5}"
EXIT_CODE=0

pass() { echo -e "  ${GREEN}${PASS}${NC} $*"; }
fail() { echo -e "  ${RED}${FAIL}${NC} $*"; EXIT_CODE=1; }
warn() { echo -e "  ${YELLOW}${WARN}${NC} $*"; }
info() { echo -e "  ${BLUE}→${NC} $*"; }

# ============ Section: System ============
check_system() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🏥 天链V3 全面健康检查"
    echo "   $(date '+%Y-%m-%d %H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    echo ""
    echo "── 📊 系统资源 ──"

    # 磁盘
    local disk_usage
    disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    info "磁盘使用率: ${disk_usage}%"
    if [ "${disk_usage}" -gt 90 ]; then
        fail "磁盘空间不足 (<10% 剩余)"
    elif [ "${disk_usage}" -gt 80 ]; then
        warn "磁盘空间偏低"
    else
        pass "磁盘空间正常"
    fi

    # 内存
    if command -v free >/dev/null 2>&1; then
        local mem_used mem_total mem_pct
        mem_used=$(free -m | awk '/Mem:/ {print $3}')
        mem_total=$(free -m | awk '/Mem:/ {print $2}')
        mem_pct=$((mem_used * 100 / mem_total))
        info "内存: ${mem_used}MB / ${mem_total}MB (${mem_pct}%)"
        if [ "${mem_pct}" -gt 90 ]; then
            fail "内存不足"
        elif [ "${mem_pct}" -gt 80 ]; then
            warn "内存偏高"
        else
            pass "内存正常"
        fi
    fi

    # CPU load
    if command -v sysctl >/dev/null 2>&1; then
        # macOS
        local cpu_count cpu_load
        cpu_count=$(sysctl -n hw.ncpu 2>/dev/null || echo "1")
        cpu_load=$(uptime | awk -F'load averages:' '{print $2}' | awk '{print $1}' 2>/dev/null || echo "N/A")
        info "CPU 核心: ${cpu_count}, Load: ${cpu_load}"
    elif command -v nproc >/dev/null 2>&1; then
        local cpu_count cpu_load
        cpu_count=$(nproc)
        cpu_load=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' 2>/dev/null || echo "N/A")
        info "CPU 核心: ${cpu_count}, Load: ${cpu_load}"
    fi

    # Uptime
    info "运行时间: $(uptime | sed 's/.*up //' | sed 's/,.*//')"
}

# ============ Section: Docker ============
check_docker() {
    echo ""
    echo "── 🐳 Docker 容器 ──"

    if ! command -v docker >/dev/null 2>&1; then
        warn "Docker 未安装, 跳过容器检查"
        return
    fi

    local containers
    containers=(tianlian-postgres tianlian-redis tianlian-backend tianlian-frontend tianlian-nginx)

    for c in "${containers[@]}"; do
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${c}$"; then
            local status health
            status=$(docker inspect --format='{{.State.Status}}' "$c" 2>/dev/null || echo "unknown")
            health=$(docker inspect --format='{{.State.Health.Status}}' "$c" 2>/dev/null || echo "N/A")
            local uptime_str
            uptime_str=$(docker inspect --format='{{.State.StartedAt}}' "$c" 2>/dev/null | cut -d'T' -f1,2 | cut -d'.' -f1 || echo "N/A")
            if [ "$health" = "healthy" ] || [ "$health" = "N/A" ]; then
                pass "${c} → ${status} (health: ${health})"
            else
                fail "${c} → ${status} (health: ${health})"
            fi
        elif docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${c}$"; then
            fail "${c} → 已停止"
        else
            warn "${c} → 未运行"
        fi
    done
}

# ============ Section: Database ============
check_database() {
    echo ""
    echo "── 🗄️ 数据库连接 ──"

    # PostgreSQL
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "tianlian-postgres"; then
        if docker exec tianlian-postgres pg_isready -U tianlian 2>/dev/null; then
            pass "PostgreSQL 连接正常"
        else
            fail "PostgreSQL 连接失败"
        fi
    else
        warn "PostgreSQL 容器未运行"
    fi

    # SQLite (本地)
    if [ -f "$(dirname "$0")/../backend/tianlian.db" ]; then
        if sqlite3 "$(dirname "$0")/../backend/tianlian.db" "SELECT 1;" 2>/dev/null; then
            pass "SQLite (tianlian.db) 正常"
        else
            fail "SQLite (tianlian.db) 异常"
        fi
    else
        warn "SQLite (tianlian.db) 不存在"
    fi

    if [ -f "$(dirname "$0")/../backend/tianlian_v3.db" ]; then
        if sqlite3 "$(dirname "$0")/../backend/tianlian_v3.db" "SELECT 1;" 2>/dev/null; then
            pass "SQLite (tianlian_v3.db) 正常"
        else
            fail "SQLite (tianlian_v3.db) 异常"
        fi
    fi
}

# ============ Section: API ============
check_api() {
    echo ""
    echo "── 🌐 API 服务 ──"

    # Health endpoint
    local api_code api_body
    api_code=$(curl -s -o /tmp/tianlian-health.json -w '%{http_code}' \
        --connect-timeout "${TIMEOUT}" "${API_URL}/api/v1/health" 2>/dev/null || echo "000")
    api_body=$(cat /tmp/tianlian-health.json 2>/dev/null || echo "{}")

    if [ "$api_code" = "200" ]; then
        pass "API /health → HTTP ${api_code}"
    else
        fail "API /health → HTTP ${api_code}"
    fi

    # 解析响应
    local app_name app_version db_status
    app_name=$(echo "$api_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('app','?'))" 2>/dev/null || echo "?")
    app_version=$(echo "$api_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('version','?'))" 2>/dev/null || echo "?")
    [ -n "$app_name" ] && info "应用: ${app_name} v${app_version}"

    # Auth endpoint
    local auth_code
    auth_code=$(curl -s -o /dev/null -w '%{http_code}' \
        --connect-timeout "${TIMEOUT}" "${API_URL}/api/v1/auth/login" \
        -X POST -H 'Content-Type: application/json' -d '{"username":"test","password":"test"}' 2>/dev/null || echo "000")
    if [ "$auth_code" = "401" ]; then
        pass "Auth /login → HTTP ${auth_code} (预期的认证失败)"
    elif [ "$auth_code" = "200" ]; then
        warn "Auth /login → HTTP ${auth_code} (测试账号居然登录成功?!)"
    else
        warn "Auth /login → HTTP ${auth_code}"
    fi
}

# ============ Section: Frontend ============
check_frontend() {
    echo ""
    echo "── 🖥️ 前端服务 ──"

    local fe_code
    fe_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout "${TIMEOUT}" "${FRONTEND_URL}" 2>/dev/null || echo "000")

    if [ "$fe_code" = "200" ]; then
        pass "前端 → HTTP ${fe_code}"
    elif [ "$fe_code" = "000" ]; then
        warn "前端不可达 (检查容器状态)"
    else
        fail "前端 → HTTP ${fe_code}"
    fi

    # Nginx 入口
    local nginx_code
    nginx_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout "${TIMEOUT}" "${NGINX_URL}" 2>/dev/null || echo "000")

    if [ "$nginx_code" = "200" ]; then
        pass "Nginx 入口 → HTTP ${nginx_code}"
    elif [ "$nginx_code" = "000" ]; then
        warn "Nginx 入口不可达 (可能未启用 --profile full)"
    else
        warn "Nginx 入口 → HTTP ${nginx_code}"
    fi
}

# ============ Section: Redis ============
check_redis() {
    echo ""
    echo "── 📦 Redis 缓存 ──"

    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "tianlian-redis"; then
        local redis_pong
        redis_pong=$(docker exec tianlian-redis redis-cli ping 2>/dev/null || echo "FAIL")
        if [ "$redis_pong" = "PONG" ]; then
            pass "Redis → PONG"

            # 内存使用
            local redis_mem
            redis_mem=$(docker exec tianlian-redis redis-cli INFO memory 2>/dev/null | grep "used_memory_human" | cut -d: -f2 | tr -d '\r' || echo "?")
            info "Redis 内存: ${redis_mem}"

            # 连接数
            local redis_clients
            redis_clients=$(docker exec tianlian-redis redis-cli INFO clients 2>/dev/null | grep "connected_clients" | cut -d: -f2 | tr -d '\r' || echo "?")
            info "Redis 连接数: ${redis_clients}"
        else
            fail "Redis PING 失败"
        fi
    else
        warn "Redis 容器未运行"
    fi
}

# ============ Section: Summary ============
print_summary() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [ "${EXIT_CODE}" -eq 0 ]; then
        echo -e "${GREEN}✅ 全部健康检查通过${NC}"
    else
        echo -e "${RED}❌ 存在异常项, 请检查以上标红项目${NC}"
    fi

    echo ""
    echo "── 📋 快速命令 ──"
    echo "  容器状态:    docker compose -f docker-compose.yml ps"
    echo "  查看日志:    docker compose -f docker-compose.yml logs -f --tail=50"
    echo "  API 文档:    ${API_URL}/docs"
    echo "  OpenAPI:     ${API_URL}/openapi.json"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ================= 主流程 =================
main() {
    check_system
    check_docker
    check_database
    check_api
    check_frontend
    check_redis
    print_summary
    exit "${EXIT_CODE}"
}

main "$@"