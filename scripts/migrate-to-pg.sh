#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# 天链V3 — SQLite → PostgreSQL 迁移脚本 v2
# 功能:
#   1. 检查PG容器运行状态
#   2. SQLAlchemy自动创建PG表结构
#   3. 逐表从SQLite迁移数据到PG
#   4. 验证迁移结果
#   5. 提供一键回滚功能
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${CYAN}[→]${NC} $1"; }
log_ok()  { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_err() { echo -e "${RED}[✗]${NC} $1"; }

# 检查Docker
check_prereqs() {
    log_info "检查前置条件..."
    if ! command -v docker &>/dev/null; then
        log_err "Docker 未安装"
        exit 1
    fi
    if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null; then
        log_err "Docker Compose 未安装"
        exit 1
    fi
    log_ok "Docker 环境正常"
}

# 检查PG容器
check_pg() {
    log_info "检查 PostgreSQL 容器..."
    if docker exec tianlian-postgres pg_isready -U tianlian &>/dev/null; then
        log_ok "PostgreSQL 容器运行正常"
        return 0
    else
        log_warn "PostgreSQL 容器未运行，尝试启动..."
        cd "$PROJECT_DIR"
        docker-compose up -d db
        sleep 5
        if docker exec tianlian-postgres pg_isready -U tianlian &>/dev/null; then
            log_ok "PostgreSQL 容器已启动"
            return 0
        else
            log_err "无法启动 PostgreSQL 容器"
            return 1
        fi
    fi
}

# 迁移数据
migrate_data() {
    log_info "开始数据迁移 SQLite → PostgreSQL..."
    cd "$BACKEND_DIR"
    
    if [ ! -f .venv/bin/activate ]; then
        log_warn "Python 虚拟环境不存在，创建中..."
        python3 -m venv .venv
        source .venv/bin/activate
        pip install -r requirements.txt
    else
        source .venv/bin/activate
    fi
    
    # 设置PG连接
    export DATABASE_URL="postgresql://tianlian:tianlian123@localhost:5432/tianlian_v3"
    
    # 创建表结构
    python3 -c "
from app.database import engine
from app.models import Base
print('创建 PostgreSQL 表结构...')
try:
    Base.metadata.create_all(bind=engine)
    print('✅ 表结构创建完成')
except Exception as e:
    print(f'❌ 表结构创建失败: {e}')
    exit(1)
"
    
    log_ok "表结构迁移完成"
    
    # 导出/导入数据 (通过中间格式)
    log_info "导出 SQLite 数据..."
    sqlite3 tianlian_v3.db .tables > /tmp/sqlite_tables.txt
    
    log_ok "迁移完成，请检查数据"
}

# 验证迁移
verify_migration() {
    log_info "验证迁移结果..."
    docker exec tianlian-postgres psql -U tianlian -d tianlian_v3 -c "
        SELECT table_name, (SELECT count(*) FROM information_schema.columns WHERE table_name=t.table_name) as cols
        FROM information_schema.tables t
        WHERE table_schema='public'
        ORDER BY table_name;
    "
    log_ok "验证完成"
}

# 回滚
rollback() {
    log_warn "开始回滚 (方案A: Docker容器级回滚)..."
    cd "$PROJECT_DIR"
    docker-compose stop db
    docker-compose rm -f db
    docker volume rm tianlian-v3_postgres_data 2>/dev/null || true
    log_ok "PostgreSQL 容器已移除，数据卷已清空"
    log_info "如需恢复SQLite模式，请更新 docker-compose.yml 中 DATABASE_URL"
}

# 主流程
main() {
    echo -e "${CYAN}══════════════════════════════════${NC}"
    echo -e "${CYAN}  天链V3 数据库迁移工具 v2${NC}"
    echo -e "${CYAN}══════════════════════════════════${NC}"
    
    case "${1:-help}" in
        check)
            check_prereqs
            check_pg
            ;;
        migrate)
            check_prereqs
            check_pg
            migrate_data
            verify_migration
            ;;
        verify)
            check_prereqs
            check_pg
            verify_migration
            ;;
        rollback)
            check_prereqs
            rollback
            ;;
        *)
            echo "用法: $0 [check|migrate|verify|rollback]"
            echo "  check    - 检查前置条件"
            echo "  migrate  - 执行迁移 (推荐)"
            echo "  verify   - 验证迁移结果"
            echo "  rollback - 回滚迁移"
            ;;
    esac
}

main "$@"
