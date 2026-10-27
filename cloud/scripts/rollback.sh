#!/usr/bin/env bash
# ─── 天链V3 一键回滚脚本 ───
# 功能: 列出可用备份 → 选择目标版本 → 回滚代码+数据库
# 用法: bash scripts/rollback.sh [--to-version VERSION] [--list] [--list-backups]
set -euo pipefail

# ================= 配置 =================
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
ENV_FILE="${PROJECT_DIR}/.env.prod"
COMPOSE_CMD="docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE}"
BACKUP_DIR="${PROJECT_DIR}/backups"
VERSION_FILE="${PROJECT_DIR}/VERSION"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/api/v1/health}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ================= 颜色输出 =================
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }
info() { echo -e "${CYAN}[→]${NC} $*"; }

# ================= 参数解析 =================
ACTION="rollback"
TARGET_VERSION=""

usage() {
    cat << 'EOF'
天链V3 一键回滚脚本

用法: bash scripts/rollback.sh [选项]

选项:
  --list, -l            列出所有可用备份
  --list-backups        列出所有备份详情
  --to-version VERSION  回滚到指定版本
  --help, -h            显示帮助信息

如果不指定版本, 默认回滚到最新备份。

示例:
  bash scripts/rollback.sh                  # 回滚到最新备份
  bash scripts/rollback.sh --list           # 列出所有备份
  bash scripts/rollback.sh --to-version 1.0.0  # 回滚到指定版本
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --list|-l)          ACTION="list"; shift ;;
        --list-backups)     ACTION="list-backups"; shift ;;
        --to-version)       TARGET_VERSION="$2"; shift 2 ;;
        --help|-h)          usage ;;
        *) err "未知参数: $1"; usage ;;
    esac
done

# ================= 工具函数 =================

require_cmd() {
    for cmd in "$@"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            err "缺少命令: $cmd"
            exit 1
        fi
    done
}

health_check() {
    local retries=${1:-30}
    local interval=${2:-2}

    info "健康检查 [最多 ${retries} 次 × ${interval}s]..."
    for i in $(seq 1 "$retries"); do
        local code
        code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "${HEALTH_URL}" 2>/dev/null || echo "000")
        if [ "$code" = "200" ]; then
            log "服务就绪 (${i}/${retries})"
            return 0
        fi
        printf "  [%2d/%2d] HTTP %s\r" "$i" "$retries" "$code" >&2
        sleep "$interval"
    done
    echo ""
    err "健康检查失败 (超时)"
    return 1
}

# ================= 列出备份 =================

list_backups() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  天链V3 可用备份列表"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [ ! -d "${BACKUP_DIR}" ]; then
        info "备份目录不存在: ${BACKUP_DIR}"
        exit 0
    fi

    local count=0
    local backup_dirs
    backup_dirs=$(ls -dt "${BACKUP_DIR}"/deploy-* 2>/dev/null || true)

    if [ -z "${backup_dirs}" ]; then
        warn "没有找到备份"
        exit 0
    fi

    echo "  序号 | 版本 | 备份时间 | 大小 | 内容"
    echo "  ─────┼──────┼──────────┼──────┼──────"

    local idx=0
    for dir in ${backup_dirs}; do
        idx=$((idx + 1))
        local dirname
        dirname=$(basename "${dir}")

        local ver="?"
        [ -f "${dir}/version.txt" ] && ver=$(cat "${dir}/version.txt")

        local size
        size=$(du -sh "${dir}" 2>/dev/null | awk '{print $1}')

        local has_sql=""
        [ "$(find "${dir}" -name 'postgres-*.sql' 2>/dev/null | wc -l)" -gt 0 ] && has_sql="${has_sql} PG"
        [ "$(find "${dir}" -name '*.db' 2>/dev/null | wc -l)" -gt 0 ] && has_sql="${has_sql} SQLite"
        [ -z "${has_sql}" ] && has_sql=" (无数据库)"

        echo "  ${idx}    | ${ver} | ${dirname#deploy-} | ${size} |${has_sql}"
    done

    echo ""
    echo "  共 ${idx} 个备份"
    echo "  备份目录: ${BACKUP_DIR}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

list_backups_detail() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  天链V3 备份详情"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ -f "${BACKUP_DIR}/backup-index.log" ]; then
        echo ""
        echo "── 备份历史 ──"
        cat "${BACKUP_DIR}/backup-index.log"
    fi

    list_backups

    echo ""
    echo "── 目录结构 ──"
    for dir in $(ls -dt "${BACKUP_DIR}"/deploy-* 2>/dev/null); do
        echo ""
        echo "  $(basename "${dir}")/"
        ls -la "${dir}" 2>/dev/null | tail -n +2 | while IFS= read -r line; do
            echo "    ${line}"
        done
    done
}

# ================= 选择备份 =================

select_backup() {
    if [ -n "${TARGET_VERSION}" ]; then
        local match
        match=$(ls -dt "${BACKUP_DIR}/deploy-${TARGET_VERSION}-"* 2>/dev/null | head -1)
        if [ -z "${match}" ]; then
            err "未找到版本 ${TARGET_VERSION} 的备份"
            warn "可用备份:"
            list_backups
            exit 1
        fi
        echo "${match}"
        return
    fi

    # 默认最新
    local latest
    latest=$(ls -dt "${BACKUP_DIR}"/deploy-* 2>/dev/null | head -1)
    if [ -z "${latest}" ]; then
        err "没有找到备份文件, 无法回滚"
        exit 1
    fi
    echo "${latest}"
}

# ================= 回滚函数 =================

do_rollback() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  天链V3 一键回滚"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    require_cmd docker curl

    local target_backup
    target_backup=$(select_backup)
    local backup_name
    backup_name=$(basename "${target_backup}")

    local backup_version
    backup_version=$(cat "${target_backup}/version.txt" 2>/dev/null || echo "unknown")
    local current_version
    current_version=$(cat "${VERSION_FILE}" 2>/dev/null || echo "unknown")

    warn "当前版本: ${current_version}"
    warn "回滚目标: ${backup_version} (${backup_name})"
    echo ""

    # 确认
    if [ -z "${TARGET_VERSION}" ]; then
        # 交互式确认 (如果没有指定版本)
        echo -n "确认回滚? [y/N] "
        read -r confirmation
        if [[ ! "${confirmation}" =~ ^[Yy]$ ]]; then
            info "回滚已取消"
            exit 0
        fi
    else
        warn "回滚到指定版本, 10秒后自动执行..."
        sleep 3
    fi

    log "开始回滚..."

    # Step 1: 备份当前状态 (安全网)
    info "Step 1/8: 备份当前状态..."
    local pre_rollback_dir="${BACKUP_DIR}/pre-rollback-${TIMESTAMP}"
    mkdir -p "${pre_rollback_dir}"

    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^tianlian-postgres$"; then
        docker exec tianlian-postgres pg_dump -U "${DB_USER:-tianlian}" "${DB_NAME:-tianlian_v3}" \
            > "${pre_rollback_dir}/pre-rollback-pg.sql" 2>/dev/null || warn "pg_dump 失败"
    fi

    if [ -f "backend/tianlian_v3.db" ]; then
        cp "backend/tianlian_v3.db" "${pre_rollback_dir}/tianlian_v3.db"
    fi

    echo "${CURRENT_VERSION:-unknown}" > "${pre_rollback_dir}/version.txt"
    log "当前状态已备份到 ${pre_rollback_dir}"

    # Step 2: 停止服务
    info "Step 2/8: 停止服务..."
    $COMPOSE_CMD down --remove-orphans 2>/dev/null || true
    log "服务已停止"

    # Step 3: 恢复代码版本
    info "Step 3/8: 恢复代码版本..."
    local commit_file="${target_backup}/git-commit.txt"
    if [ -f "${commit_file}" ]; then
        local rollback_commit
        rollback_commit=$(cat "${commit_file}")
        info "Git commit: ${rollback_commit}"
        if git rev-parse --git-dir >/dev/null 2>&1; then
            git stash 2>/dev/null || true
            if git checkout "${rollback_commit}" 2>/dev/null; then
                log "代码已回退到 ${rollback_commit}"
            else
                warn "Git 回退失败, 使用当前代码"
            fi
        else
            warn "不在 Git 仓库, 跳过代码回退"
        fi
    else
        warn "备份中没有 commit 记录, 跳过代码回退"
    fi

    # Step 4: 启动核心服务
    info "Step 4/8: 启动核心服务..."
    $COMPOSE_CMD up -d db redis
    sleep 5
    log "核心服务已启动"

    # Step 5: 恢复数据库
    info "Step 5/8: 恢复数据库..."

    # 先启动后端 (用于执行 alembic)
    $COMPOSE_CMD up -d backend
    sleep 5

    # Alembic 降级
    local backup_alembic="${target_backup}/alembic-current.txt"
    if [ -f "${backup_alembic}" ]; then
        local target_revision
        target_revision=$(head -1 "${backup_alembic}" | awk '{print $1}' 2>/dev/null || echo "")
        if [ -n "${target_revision}" ]; then
            info "Alembic 降级到: ${target_revision}"
            docker exec tianlian-backend bash -c "cd /app && alembic downgrade ${target_revision}" 2>/dev/null && \
                log "Alembic 降级成功" || warn "Alembic 降级失败"
        fi
    fi

    # 恢复 PostgreSQL 数据
    local pg_dump
    pg_dump=$(find "${target_backup}" -name 'postgres-*.sql' 2>/dev/null | head -1)
    if [ -n "${pg_dump}" ] && [ -s "${pg_dump}" ]; then
        info "恢复 PostgreSQL 数据..."
        cat "${pg_dump}" | docker exec -i tianlian-postgres psql -U "${DB_USER:-tianlian}" "${DB_NAME:-tianlian_v3}" 2>/dev/null || warn "恢复有警告"
        log "PostgreSQL 数据恢复完成"
    fi

    # 恢复 SQLite
    local sqlite_backup
    sqlite_backup=$(find "${target_backup}" -name '*.db' 2>/dev/null | head -1)
    if [ -n "${sqlite_backup}" ]; then
        cp "${sqlite_backup}" "backend/tianlian_v3.db" 2>/dev/null && log "SQLite 数据恢复完成" || warn "SQLite 恢复失败"
    fi

    # Step 6: 重新构建和启动应用
    info "Step 6/8: 构建并启动应用..."
    $COMPOSE_CMD build --no-cache backend frontend
    $COMPOSE_CMD up -d backend frontend
    log "应用服务已启动"

    # Step 7: 健康检查
    info "Step 7/8: 健康检查..."
    if health_check 40 3; then
        log "健康检查通过"
    else
        err "健康检查失败, 请手动检查: docker compose logs backend"
        exit 1
    fi

    # Step 8: 启动监控和 Nginx
    info "Step 8/8: 启动附加服务..."
    $COMPOSE_CMD up -d prometheus grafana 2>/dev/null || true
    log "监控服务已启动"
    $COMPOSE_CMD up -d nginx 2>/dev/null || true
    log "Nginx 入口已启动"

    # 更新 VERSION
    echo "${backup_version}" > "${VERSION_FILE}"
    log "VERSION 恢复为: ${backup_version}"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "回滚成功! 版本: ${current_version} → ${backup_version}"
    info "  访问: http://localhost:80"
    info "  API:  http://localhost:8000"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ================= 主流程 =================

main() {
    case "${ACTION}" in
        list)          list_backups ;;
        list-backups)  list_backups_detail ;;
        rollback)      do_rollback ;;
        *)             err "未知操作"; exit 1 ;;
    esac
}

main "$@"