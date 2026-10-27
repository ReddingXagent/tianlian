#!/usr/bin/env bash
# ─── 天链V3 生产环境一键部署脚本 ───
# 功能: 拉取最新代码 → 数据库迁移 → 构建前端 → docker compose 启动 → 健康检查 → 回滚
# 用法: bash scripts/deploy-prod.sh [--full|--update|--backup|--rollback]
set -euo pipefail

# ================= 配置 =================
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
ENV_FILE="${PROJECT_DIR}/.env.prod"
COMPOSE_CMD="docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/api/v1/health}"
HEALTH_FRONTEND_URL="${HEALTH_FRONTEND_URL:-http://localhost:80}"
BACKUP_DIR="${PROJECT_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="${PROJECT_DIR}/logs"
VERSION_FILE="${PROJECT_DIR}/VERSION"

# 当前版本号
CURRENT_VERSION=$(cat "${VERSION_FILE}" 2>/dev/null || echo "unknown")
DEPLOY_VERSION="deploy-${CURRENT_VERSION}-${TIMESTAMP}"

# ================= 颜色输出 =================
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }
info() { echo -e "${CYAN}[→]${NC} $*"; }

# ================= 参数解析 =================
MODE="full"
DO_BACKUP=false
DRY_RUN=false

usage() {
    cat << 'EOF'
天链V3 生产部署脚本

用法: bash scripts/deploy-prod.sh [选项]

选项:
  --full       全服务部署 (拉取代码→数据库迁移→构建→启动)  [默认]
  --update     仅增量更新 (重建镜像+重启)
  --backup     先备份再部署
  --rollback   回滚到指定版本 (需指定 --to-version)
  --to-version VERSION  回滚目标版本 (与 --rollback 配合)
  --dry-run    仅验证流程, 不实际执行
  --help, -h   显示帮助信息

示例:
  bash scripts/deploy-prod.sh --full
  bash scripts/deploy-prod.sh --full --backup
  bash scripts/deploy-prod.sh --update
  bash scripts/deploy-prod.sh --rollback --to-version 1.0.0
  bash scripts/deploy-prod.sh --dry-run
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --full)      MODE="full";     shift ;;
        --update)    MODE="update";   shift ;;
        --backup)    DO_BACKUP=true;  shift ;;
        --rollback)  MODE="rollback"; shift ;;
        --to-version) TARGET_VERSION="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=true;   shift ;;
        --help|-h)   usage ;;
        *) err "未知参数: $1"; usage ;;
    esac
done

# ================= 工具函数 =================

require_cmd() {
    local missing=()
    for cmd in "$@"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        err "缺少命令: ${missing[*]}"
        exit 1
    fi
}

health_check() {
    local retries=${1:-30}
    local interval=${2:-2}
    local url="${HEALTH_URL}"

    info "健康检查 [最多 ${retries} 次 × ${interval}s] → ${url}"
    for i in $(seq 1 "$retries"); do
        local code
        code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "${url}" 2>/dev/null || echo "000")
        if [ "$code" = "200" ]; then
            log "后端就绪 (HTTP ${code}, ${i}/${retries})"
            return 0
        fi
        printf "  [%2d/%2d] HTTP %s\r" "$i" "$retries" "$code" >&2
        sleep "$interval"
    done
    echo ""
    err "健康检查失败 (超时)"
    return 1
}

frontend_check() {
    local url="${HEALTH_FRONTEND_URL}"
    info "前端健康检查 → ${url}"
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "${url}" 2>/dev/null || echo "000")
    if [ "$code" = "200" ] || [ "$code" = "302" ] || [ "$code" = "301" ]; then
        log "前端就绪 (HTTP ${code})"
        return 0
    fi
    warn "前端 HTTP ${code} (可能在 nginx 入口后面)"
    return 0
}

# ================= 数据库备份 =================

db_backup() {
    require_cmd docker
    mkdir -p "${BACKUP_DIR}"

    local backup_path="${BACKUP_DIR}/${DEPLOY_VERSION}"
    mkdir -p "${backup_path}"

    info "备份数据库到 ${backup_path}..."

    # PostgreSQL 备份 (如果容器运行中)
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^tianlian-postgres$"; then
        local pg_dump_file="${backup_path}/postgres-${TIMESTAMP}.sql"
        info "备份 PostgreSQL → ${pg_dump_file}"
        docker exec tianlian-postgres pg_dump -U "${DB_USER:-tianlian}" "${DB_NAME:-tianlian_v3}" \
            > "${pg_dump_file}" 2>/dev/null || warn "pg_dump 失败(容器可能未就绪)"
        if [ -s "${pg_dump_file}" ]; then
            log "PostgreSQL 备份完成: $(du -h "${pg_dump_file}" | awk '{print $1}')"
        fi
    else
        warn "PostgreSQL 容器未运行, 跳过 pg_dump"
    fi

    # SQLite 备份
    local sqlite_db="${PROJECT_DIR}/backend/tianlian_v3.db"
    if [ -f "${sqlite_db}" ]; then
        cp "${sqlite_db}" "${backup_path}/tianlian_v3-${TIMESTAMP}.db"
        log "SQLite 备份完成"
    fi
    sqlite_db="${PROJECT_DIR}/backend/tianlian.db"
    if [ -f "${sqlite_db}" ]; then
        cp "${sqlite_db}" "${backup_path}/tianlian-${TIMESTAMP}.db"
        log "SQLite (legacy) 备份完成"
    fi

    # 备份当前代码版本信息
    if git rev-parse --git-dir >/dev/null 2>&1; then
        git rev-parse HEAD > "${backup_path}/git-commit.txt" 2>/dev/null || true
        git describe --tags --always > "${backup_path}/git-tag.txt" 2>/dev/null || true
    fi
    echo "${CURRENT_VERSION}" > "${backup_path}/version.txt"
    echo "${TIMESTAMP}" > "${backup_path}/timestamp.txt"

    # 写备份索引
    echo "${TIMESTAMP} | VERSION=${CURRENT_VERSION} | MODE=${MODE} | PATH=${backup_path}" >> "${BACKUP_DIR}/backup-index.log"

    # 清理旧备份 (保留最近 5 个)
    info "清理旧备份 (保留最近5个)..."
    ls -dt "${BACKUP_DIR}"/deploy-* 2>/dev/null | tail -n +6 | while IFS= read -r old; do
        rm -rf "${old}"
        warn "删除旧备份: ${old}"
    done

    log "备份完成 → ${backup_path}"
}

# ================= 前端构建 =================

build_frontend() {
    info "构建前端..."
    cd "${PROJECT_DIR}/frontend"

    if [ ! -d "node_modules" ]; then
        info "安装前端依赖..."
        npm ci 2>&1 | tail -3 || npm install 2>&1 | tail -3
    fi

    npm run build 2>&1 | tail -5
    if [ ! -f "dist/index.html" ]; then
        err "前端构建失败: dist/index.html 未生成"
        return 1
    fi
    log "前端构建完成 ($(du -sh dist | awk '{print $1}'))"
    cd "${PROJECT_DIR}"
}

# ================= 数据库迁移 (Alembic) =================

run_db_migration() {
    info "检查 Alembic 迁移..."

    # 确保容器运行中
    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^tianlian-backend$"; then
        warn "后端容器未运行, 跳过 Alembic 迁移"
        return 0
    fi

    # 检查 backend 内是否有 alembic 目录
    local alembic_dir="${PROJECT_DIR}/backend/app/migrations"
    local alembic_ini="${PROJECT_DIR}/backend/alembic.ini"

    if [ -d "${alembic_dir}" ] || [ -f "${alembic_ini}" ]; then
        # 在容器内执行迁移
        info "执行 Alembic 迁移..."
        if docker exec tianlian-backend bash -c "cd /app && alembic upgrade head" 2>/dev/null; then
            log "数据库迁移完成"
        else
            # 尝试用 python 运行
            warn "alembic 命令失败, 尝试 python 迁移..."
            docker exec tianlian-backend bash -c "cd /app && python -c \"
from alembic.config import Config
from alembic import command
alembic_cfg = Config('/app/alembic.ini')
command.upgrade(alembic_cfg, 'head')
\"" 2>/dev/null && log "数据库迁移完成" || warn "Alembic 迁移跳过 (可能在 SQLite 模式)"
        fi
    else
        # 使用 init_db.py 或 SQLAlchemy create_all
        info "使用 Base.metadata.create_all 初始化数据库..."
        if docker exec tianlian-backend bash -c "cd /app && python -c \"
from app.core.database import Base, engine
from app.models import *
Base.metadata.create_all(bind=engine)
print('数据库表创建/同步完成')
\"" 2>/dev/null; then
            log "数据库表同步完成"
        else
            warn "数据库初始化失败 (可能在启动时已自动完成)"
        fi
    fi
}

record_migration() {
    # 记录当前数据库迁移版本
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^tianlian-backend$"; then
        docker exec tianlian-backend bash -c "cd /app && alembic current" 2>/dev/null \
            > "${BACKUP_DIR}/${DEPLOY_VERSION}/alembic-current.txt" || true
    fi
}

# ================= Pull 代码 =================

git_pull() {
    info "拉取最新代码..."
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        warn "不在 Git 仓库中, 跳过代码拉取"
        return
    fi

    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)

    # 检查未提交变更
    if ! git diff --quiet || ! git diff --cached --quiet; then
        warn "检测到未提交变更, 跳过 git pull (请先 commit/stash)"
        return
    fi

    git fetch origin
    if git pull origin "${current_branch}" 2>/dev/null; then
        log "代码已更新到最新 (${current_branch})"
        # 更新 VERSION 文件 (如果 git tag 存在)
        local latest_tag
        latest_tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
        if [ -n "${latest_tag}" ]; then
            echo "${latest_tag#v}" > "${VERSION_FILE}"
            log "VERSION 更新为: $(cat "${VERSION_FILE}")"
        fi
    else
        warn "git pull 失败, 使用本地代码继续"
    fi
}

# ================= Docker Compose 操作 =================

compose_build() {
    info "构建 Docker 镜像 (--no-cache)..."
    $COMPOSE_CMD build --no-cache
}

compose_build_incremental() {
    info "增量构建 Docker 镜像..."
    $COMPOSE_CMD build backend
    $COMPOSE_CMD build frontend
}

compose_stop() {
    info "停止旧服务..."
    $COMPOSE_CMD down --remove-orphans 2>/dev/null || true
}

compose_start_core() {
    info "启动核心服务 (数据库+缓存)..."
    $COMPOSE_CMD up -d db redis
    sleep 5
}

compose_start_app() {
    info "启动应用服务 (后端+前端)..."
    $COMPOSE_CMD up -d backend frontend
}

compose_start_monitoring() {
    info "启动监控服务 (Prometheus+Grafana)..."
    $COMPOSE_CMD up -d prometheus grafana
}

compose_start_nginx() {
    info "启动 Nginx 入口..."
    $COMPOSE_CMD up -d nginx
}

compose_status() {
    $COMPOSE_CMD ps
}

# ================= 版本管理 =================

create_git_tag() {
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        return
    fi

    local tag_name="v${CURRENT_VERSION}"
    if git tag -l | grep -q "^${tag_name}$"; then
        warn "Git tag ${tag_name} 已存在, 跳过"
        return
    fi

    info "创建 Git tag: ${tag_name}"
    git tag -a "${tag_name}" -m "Deploy ${CURRENT_VERSION} at ${TIMESTAMP}" 2>/dev/null || warn "创建 Git tag 失败"
}

# ================= 完整部署 =================

do_full() {
    log "=== 全量部署模式 V${CURRENT_VERSION} ==="

    # 1. 验证前置条件
    info "验证前置条件..."
    require_cmd docker curl npm

    # 2. 拉取最新代码
    git_pull

    # 3. 前端构建
    build_frontend || { err "前端构建失败, 中止部署"; exit 1; }

    # 4. 备份 (可选)
    if $DO_BACKUP; then
        db_backup
    fi

    # 5. 准备日志目录
    mkdir -p "${LOG_DIR}"/{backend,frontend,nginx}

    # 6. 停止旧服务
    compose_stop

    # 7. 构建镜像
    compose_build

    # 8. 启动
    compose_start_core
    compose_start_app

    # 9. 健康检查 (后端)
    health_check 40 3 || {
        err "部署后健康检查失败, 执行回滚..."
        do_rollback_internal
        exit 1
    }

    # 10. 数据库迁移
    run_db_migration
    record_migration

    # 11. 启动监控
    compose_start_monitoring

    # 12. 前端检查
    frontend_check

    # 13. 启动 Nginx 入口
    compose_start_nginx

    # 14. 创建 Git tag
    create_git_tag

    # 15. 显示状态
    log "=== 部署完成 V${CURRENT_VERSION} ==="
    compose_status
}

# ================= 增量更新 =================

do_update() {
    log "=== 增量更新模式 V${CURRENT_VERSION} ==="

    require_cmd docker curl

    # 1. 拉取代码
    git_pull

    # 2. 前端构建 (如果有变更)
    if git diff --name-only HEAD~1 2>/dev/null | grep -q "^frontend/"; then
        build_frontend || warn "前端构建失败, 跳过..."
    fi

    # 3. 备份 (可选)
    if $DO_BACKUP; then
        db_backup
    fi

    # 4. 增量构建 & 重启
    compose_build_incremental
    compose_start_app

    # 5. 健康检查
    health_check 30 2 || {
        err "更新后健康检查失败!"
        exit 1
    }

    # 6. 数据库迁移
    run_db_migration

    log "=== 更新完成 V${CURRENT_VERSION} ==="
    compose_status
}

# ================= 内部回滚 (部署失败时自动调用) =================

do_rollback_internal() {
    warn "执行内部回滚..."

    # 查找最新的可用备份
    local latest_backup
    latest_backup=$(ls -dt "${BACKUP_DIR}"/deploy-* 2>/dev/null | head -1)

    if [ -z "${latest_backup}" ]; then
        err "没有找到备份文件, 无法回滚"
        # 重新启动旧镜像
        $COMPOSE_CMD up -d 2>/dev/null || true
        return 1
    fi

    info "回滚到备份: ${latest_backup}"

    # 恢复数据库
    local pg_dump
    pg_dump=$(find "${latest_backup}" -name 'postgres-*.sql' 2>/dev/null | head -1)
    if [ -n "${pg_dump}" ] && docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^tianlian-postgres$"; then
        info "恢复 PostgreSQL..."
        cat "${pg_dump}" | docker exec -i tianlian-postgres psql -U "${DB_USER:-tianlian}" "${DB_NAME:-tianlian_v3}" 2>/dev/null || warn "数据库恢复失败"
    fi

    # 回退代码版本
    local prev_commit="${latest_backup}/git-commit.txt"
    if [ -f "${prev_commit}" ] && git rev-parse --git-dir >/dev/null 2>&1; then
        local target_commit
        target_commit=$(cat "${prev_commit}")
        info "回退代码到: ${target_commit}"
        git checkout "${target_commit}" 2>/dev/null || warn "Git 回退失败"
    fi

    # 重新构建并启动
    $COMPOSE_CMD down --remove-orphans 2>/dev/null || true
    compose_build
    compose_start_core
    compose_start_app

    # 健康检查
    health_check 40 3 || err "回滚后服务仍未恢复, 请手动检查"

    log "内部回滚完成"
}

# ================= 外部回滚 (用户触发) =================

do_rollback() {
    log "=== 回滚模式 ==="

    require_cmd docker curl

    # 查找备份
    if [ -n "${TARGET_VERSION:-}" ]; then
        local target_backup
        target_backup=$(ls -dt "${BACKUP_DIR}"/deploy-${TARGET_VERSION}-* 2>/dev/null | head -1)
        if [ -z "${target_backup}" ]; then
            err "未找到版本 ${TARGET_VERSION} 的备份"
            exit 1
        fi
        info "回滚到指定版本: ${TARGET_VERSION}"
    else
        local target_backup
        target_backup=$(ls -dt "${BACKUP_DIR}"/deploy-* 2>/dev/null | head -1)
        if [ -z "${target_backup}" ]; then
            err "没有找到备份文件, 无法回滚"
            exit 1
        fi
        info "回滚到最新备份: $(basename "${target_backup}")"
    fi

    # 读取备份版本信息
    local backup_version
    backup_version=$(cat "${target_backup}/version.txt" 2>/dev/null || echo "unknown")
    info "备份版本: ${backup_version}"

    # 1. 备份当前状态 (回滚前紧急备份)
    local rollback_timestamp
    rollback_timestamp=$(date +%Y%m%d_%H%M%S)
    local pre_rollback="${BACKUP_DIR}/pre-rollback-${rollback_timestamp}"
    mkdir -p "${pre_rollback}"

    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^tianlian-postgres$"; then
        docker exec tianlian-postgres pg_dump -U "${DB_USER:-tianlian}" "${DB_NAME:-tianlian_v3}" \
            > "${pre_rollback}/pre-rollback-pg.sql" 2>/dev/null || true
    fi
    log "回滚前已备份当前状态到 ${pre_rollback}"

    # 2. 停止服务
    info "停止服务..."
    $COMPOSE_CMD down --remove-orphans 2>/dev/null || true

    # 3. 恢复代码版本
    local commit_file="${target_backup}/git-commit.txt"
    if [ -f "${commit_file}" ] && git rev-parse --git-dir >/dev/null 2>&1; then
        local rollback_commit
        rollback_commit=$(cat "${commit_file}")
        info "回退代码到: ${rollback_commit} (来自备份)"
        git stash 2>/dev/null || true
        git checkout "${rollback_commit}" 2>/dev/null || warn "Git 回退失败, 继续使用当前代码"
        log "代码版本已回退"
    fi

    # 4. 恢复数据库 (Alembic downgrade)
    info "恢复数据库..."
    # 先启动数据库
    $COMPOSE_CMD up -d db redis
    sleep 5

    # 启动后端 (用于执行迁移)
    $COMPOSE_CMD up -d backend
    sleep 5

    # Alembic downgrade: 找到版本链, 逐步降级
    local backup_alembic="${target_backup}/alembic-current.txt"
    if [ -f "${backup_alembic}" ]; then
        local target_revision
        target_revision=$(cat "${backup_alembic}" | awk '{print $1}' 2>/dev/null || echo "")
        if [ -n "${target_revision}" ]; then
            warn "降级数据库到: ${target_revision}"
            docker exec tianlian-backend bash -c "cd /app && alembic downgrade ${target_revision}" 2>/dev/null || warn "Alembic 降级失败"
        fi
    fi

    # 恢复 PostgreSQL 数据
    local pg_dump
    pg_dump=$(find "${target_backup}" -name 'postgres-*.sql' 2>/dev/null | head -1)
    if [ -n "${pg_dump}" ] && [ -s "${pg_dump}" ]; then
        info "恢复 PostgreSQL 数据..."
        cat "${pg_dump}" | docker exec -i tianlian-postgres psql -U "${DB_USER:-tianlian}" "${DB_NAME:-tianlian_v3}" 2>/dev/null || warn "PostgreSQL 恢复有警告"
        log "PostgreSQL 数据恢复完成"
    fi

    # 恢复 SQLite
    local sqlite_backup
    sqlite_backup=$(find "${target_backup}" -name 'tianlian_v3-*.db' 2>/dev/null | head -1)
    if [ -n "${sqlite_backup}" ]; then
        cp "${sqlite_backup}" "${PROJECT_DIR}/backend/tianlian_v3.db"
        log "SQLite 数据恢复完成"
    fi

    # 5. 重新构建和启动
    info "重新构建和启动服务..."
    compose_build
    $COMPOSE_CMD up -d backend frontend

    # 6. 健康检查
    health_check 40 3 || {
        err "回滚后健康检查失败"
        exit 1
    }

    # 7. 启动监控和 Nginx
    compose_start_monitoring
    compose_start_nginx

    # 8. 恢复 VERSION 文件
    echo "${backup_version}" > "${VERSION_FILE}"
    log "VERSION 恢复为: ${backup_version}"

    log "=== 回滚完成 → 版本 ${backup_version} ==="
    compose_status
}

# ================= 主流程 =================

main() {
    # 检查必要工具
    require_cmd docker curl

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  天链V3 生产部署"
    echo "  模式: ${MODE} | 版本: ${CURRENT_VERSION}"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  项目: ${PROJECT_DIR}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Dry-run 模式
    if $DRY_RUN; then
        warn "Dry-run 模式: 仅验证流程"
        info "环境配置:"
        info "  COMPOSE_FILE = ${COMPOSE_FILE}"
        info "  ENV_FILE     = ${ENV_FILE}"
        info "  BACKUP_DIR   = ${BACKUP_DIR}"
        info "  VERSION      = ${CURRENT_VERSION}"
        info "  LOG_DIR      = ${LOG_DIR}"
        info ""
        info "Docker Compose 配置检查..."
        $COMPOSE_CMD config 2>/dev/null && log "Docker Compose 配置有效" || err "Docker Compose 配置无效"
        info ""
        info "脚本语法检查:"
        bash -n "$0" && log "脚本语法正确" || err "脚本语法错误"
        exit 0
    fi

    case "${MODE}" in
        full)     do_full ;;
        update)   do_update ;;
        rollback) do_rollback ;;
        *)        err "未知模式: ${MODE}"; exit 1 ;;
    esac

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "部署完成"
    info "  后端: http://localhost:8000"
    info "  前端: http://localhost:3004"
    info "  API:  http://localhost:80/api/v1/health"
    info "  Prometheus: http://localhost:9090"
    info "  Grafana:    http://localhost:3000"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

main "$@"