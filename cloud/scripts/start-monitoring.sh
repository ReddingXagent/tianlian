#!/usr/bin/env bash
# ─── 天链V3 监控栈启动脚本 ───
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $*"; }

# ─── 检查依赖 ───
check_prerequisites() {
    log_step "检查前置依赖..."

    if ! command -v docker &>/dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi

    if ! docker compose version &>/dev/null && ! docker-compose version &>/dev/null; then
        log_error "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi

    # 选择 compose 命令
    if docker compose version &>/dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi

    log_info "依赖检查通过 ✓"
}

# ─── 检查配置文件 ───
check_config_files() {
    log_step "检查配置文件..."

    local files=(
        "$PROJECT_DIR/docker-compose.monitoring.yml"
        "$PROJECT_DIR/prometheus/prometheus.yml"
        "$PROJECT_DIR/grafana/provisioning/datasources/prometheus.yml"
        "$PROJECT_DIR/grafana/provisioning/dashboards/dashboard.json"
        "$PROJECT_DIR/grafana/provisioning/dashboards/dashboard-provider.yml"
    )

    local missing=0
    for f in "${files[@]}"; do
        if [[ ! -f "$f" ]]; then
            log_error "缺少配置文件: $f"
            missing=$((missing + 1))
        fi
    done

    if [[ $missing -gt 0 ]]; then
        log_error "共缺少 $missing 个配置文件，请检查完整性"
        exit 1
    fi

    log_info "配置文件检查通过 ✓"
}

# ─── 启动监控栈 ───
start_monitoring() {
    log_step "启动监控栈..."
    cd "$PROJECT_DIR"

    # 确保 tianlian-network 存在
    if ! docker network inspect tianlian-network &>/dev/null; then
        log_warn "创建共享网络 tianlian-network..."
        docker network create tianlian-network
    fi

    $COMPOSE_CMD -f docker-compose.monitoring.yml up -d

    log_info "监控容器已启动"
}

# ─── 等待服务就绪 ───
wait_for_services() {
    log_step "等待服务就绪..."

    local max_wait=60
    local waited=0

    # 等待 Prometheus
    while [[ $waited -lt $max_wait ]]; do
        if curl -sf http://localhost:9090/-/healthy &>/dev/null; then
            log_info "Prometheus 已就绪 ✓"
            break
        fi
        sleep 2
        waited=$((waited + 2))
    done

    if [[ $waited -ge $max_wait ]]; then
        log_warn "Prometheus 启动超时，请手动检查"
    fi

    # 等待 Grafana
    waited=0
    while [[ $waited -lt $max_wait ]]; do
        if curl -sf http://localhost:3000/api/health &>/dev/null; then
            log_info "Grafana 已就绪 ✓"
            break
        fi
        sleep 2
        waited=$((waited + 2))
    done

    if [[ $waited -ge $max_wait ]]; then
        log_warn "Grafana 启动超时，请手动检查"
    fi
}

# ─── 检查服务状态 ───
check_status() {
    log_step "检查服务状态..."
    cd "$PROJECT_DIR"

    $COMPOSE_CMD -f docker-compose.monitoring.yml ps
}

# ─── 输出访问地址 ───
print_urls() {
    echo ""
    echo "============================================"
    echo "  🐵 天链V3 监控栈已启动"
    echo "============================================"
    echo ""
    echo -e "  ${GREEN}Grafana 面板:${NC}   http://localhost:3000"
    echo -e "  ${GREEN}Prometheus:${NC}    http://localhost:9090"
    echo ""
    echo -e "  ${YELLOW}Grafana 登录信息:${NC}"
    echo "    用户名: admin"
    echo "    密码:   tianlian123 (默认，请及时修改)"
    echo ""
    echo -e "  ${GREEN}默认面板:${NC} 天链V3 运维监控面板"
    echo ""
    echo "============================================"
}

# ─── 主流程 ───
main() {
    echo ""
    echo "============================================"
    echo "  天链V3 监控栈部署"
    echo "  Prometheus + Grafana"
    echo "============================================"
    echo ""

    check_prerequisites
    check_config_files
    start_monitoring
    wait_for_services
    check_status
    print_urls

    log_info "监控栈部署完成！🐵"
}

main "$@"