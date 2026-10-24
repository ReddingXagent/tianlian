#!/usr/bin/env bash
# ─── 天链V3 PostgreSQL 一键搭建脚本 ───
# 功能:
#   1. 检查/安装 PostgreSQL 客户端
#   2. 创建数据库用户
#   3. 创建数据库
#   4. 安装扩展 (uuid-ossp, pg_trgm)
#   5. 创建所有业务表 (通过 Python/SQLAlchemy)
#   6. 可选: 执行数据迁移

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ─── 默认配置 ───
: "${PG_HOST:=localhost}"
: "${PG_PORT:=5432}"
: "${PG_USER:=tianlian}"
: "${PG_PASSWORD:=tianlian123}"
: "${PG_DB:=tianlian_v3}"
: "${PG_SUPERUSER:=postgres}"
: "${PG_SUPERUSER_PASSWORD:=postgres}"
: "${RUN_MIGRATION:=no}"
: "${ENV_FILE:=$PROJECT_ROOT/docker/.env.pg}"

# ─── 颜色输出 ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
step()  { echo -e "\n${BLUE}═══ $* ═══${NC}"; }

# ─── 用法 ───
usage() {
    cat <<EOF
用法: ./setup-pg.sh [选项]

选项:
  --host HOST         PostgreSQL 主机 (默认: localhost)
  --port PORT         PostgreSQL 端口 (默认: 5432)
  --user USER         数据库用户 (默认: tianlian)
  --password PASS     数据库密码 (默认: tianlian123)
  --db DBNAME         数据库名 (默认: tianlian_v3)
  --superuser USER    超级用户 (默认: postgres)
  --migrate           搭建后执行 SQLite→PG 数据迁移
  --docker            针对 Docker Compose 环境 (host=db)

环境变量:
  PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DB
  PG_SUPERUSER, PG_SUPERUSER_PASSWORD
  RUN_MIGRATION=yes

示例:
  # 本地开发
  ./scripts/setup-pg.sh

  # Docker Compose 环境 + 数据迁移
  ./scripts/setup-pg.sh --docker --migrate

  # 自定义
  PG_HOST=192.168.1.100 PG_PASSWORD=MyPass ./scripts/setup-pg.sh
EOF
    exit 0
}

# ─── 解析参数 ───
PG_HOST_OVERRIDE="$PG_HOST"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)       PG_HOST_OVERRIDE="$2"; shift 2 ;;
        --port)       PG_PORT="$2"; shift 2 ;;
        --user)       PG_USER="$2"; shift 2 ;;
        --password)   PG_PASSWORD="$2"; shift 2 ;;
        --db)         PG_DB="$2"; shift 2 ;;
        --superuser)  PG_SUPERUSER="$2"; shift 2 ;;
        --migrate)    RUN_MIGRATION=yes; shift ;;
        --docker)     PG_HOST_OVERRIDE="db"; shift ;;
        --help|-h)    usage ;;
        *)            error "未知参数: $1"; usage ;;
    esac
done
PG_HOST="$PG_HOST_OVERRIDE"

# ─── 打印配置 ───
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     天链V3 PostgreSQL 一键搭建           ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Host:     $PG_HOST"
echo "║  Port:     $PG_PORT"
echo "║  User:     $PG_USER"
echo "║  DB:       $PG_DB"
echo "║  Migrate:  $RUN_MIGRATION"
echo "╚══════════════════════════════════════════╝"
echo ""

# ─── 检查 psql ───
if ! command -v psql &>/dev/null; then
    warn "psql 未安装，尝试安装..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install libpq && brew link --force libpq
    elif command -v apt-get &>/dev/null; then
        sudo apt-get update && sudo apt-get install -y postgresql-client
    elif command -v apk &>/dev/null; then
        apk add --no-cache postgresql-client
    else
        error "无法自动安装 psql，请手动安装 PostgreSQL 客户端"
        exit 1
    fi
fi

# ─── 导出密码环境变量 ───
export PGPASSWORD="$PG_SUPERUSER_PASSWORD"

# ─── 步骤 1: 测试超级用户连接 ───
step "1. 测试超级用户连接"
if psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d postgres -c "SELECT 1;" &>/dev/null; then
    info "✅ 连接成功 (用户: $PG_SUPERUSER)"
else
    error "❌ 无法连接 PostgreSQL ($PG_HOST:$PG_PORT, 用户: $PG_SUPERUSER)"
    error "请检查 PostgreSQL 是否已启动"
    exit 1
fi

# ─── 步骤 2: 创建数据库用户 ───
step "2. 创建数据库用户: $PG_USER"
USER_EXISTS=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d postgres -tAc \
    "SELECT 1 FROM pg_roles WHERE rolname='$PG_USER';" 2>/dev/null || echo "")

if [[ "$USER_EXISTS" == "1" ]]; then
    info "用户已存在，更新密码..."
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d postgres -c \
        "ALTER USER \"$PG_USER\" WITH PASSWORD '$PG_PASSWORD';" 2>/dev/null || \
        warn "密码更新失败(可能版本差异)"
else
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d postgres -c \
        "CREATE USER \"$PG_USER\" WITH PASSWORD '$PG_PASSWORD';" 2>/dev/null
    info "✅ 用户已创建"
fi

# ─── 步骤 3: 创建数据库 ───
step "3. 创建数据库: $PG_DB"
DB_EXISTS=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='$PG_DB';" 2>/dev/null || echo "")

if [[ "$DB_EXISTS" == "1" ]]; then
    info "数据库已存在，跳过创建"
else
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d postgres -c \
        "CREATE DATABASE \"$PG_DB\" OWNER \"$PG_USER\" ENCODING 'UTF8';"
    info "✅ 数据库已创建"
fi

# ─── 步骤 4: 授权 ───
step "4. 授权用户"
psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d "$PG_DB" <<SQL
GRANT ALL PRIVILEGES ON DATABASE "$PG_DB" TO "$PG_USER";
GRANT ALL ON SCHEMA public TO "$PG_USER";
SQL
info "✅ 授权完成"

# ─── 步骤 5: 安装扩展 ───
step "5. 安装 PostgreSQL 扩展"
psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d "$PG_DB" <<SQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
SQL
info "✅ 扩展已安装 (uuid-ossp, pg_trgm)"

# ─── 步骤 6: 创建表 (通过 Python) ───
step "6. 创建数据库表"

# 切换到项目后端目录
cd "$PROJECT_ROOT/backend"

# 检查 Python 环境
if [[ -d "venv" ]]; then
    PYTHON="venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

# 创建临时初始化脚本
TMP_INIT=$(mktemp /tmp/tianlian_init_pg.XXXXXX.py)
cat > "$TMP_INIT" <<'PYEOF'
import os
import sys
sys.path.insert(0, ".")

os.environ["DB_TYPE"] = "postgres"
os.environ["DATABASE_URL"] = os.getenv(
    "PG_INIT_URL",
    f"postgresql://{os.getenv('PG_USER','tianlian')}:{os.getenv('PG_PASSWORD','tianlian123')}@{os.getenv('PG_HOST','localhost')}:{os.getenv('PG_PORT','5432')}/{os.getenv('PG_DB','tianlian_v3')}"
)

from app.core.database import engine, Base
from app.models import *

print("正在创建数据库表...")
Base.metadata.create_all(bind=engine)
print("✅ 所有表已创建")

# 打印创建的表名
from sqlalchemy import inspect
inspector = inspect(engine)
tables = sorted(inspector.get_table_names())
for t in tables:
    print(f"  📦 {t}")
print(f"\n共 {len(tables)} 个表")
PYEOF

export PG_HOST PG_PORT PG_USER PG_PASSWORD PG_DB
$PYTHON "$TMP_INIT"
rm -f "$TMP_INIT"

# ─── 步骤 7: 生成 .env 文件 ───
step "7. 生成环境配置"

DATABASE_URL="postgresql://${PG_USER}:${PG_PASSWORD}@${PG_HOST}:${PG_PORT}/${PG_DB}"

# 确保目录存在
mkdir -p "$(dirname "$ENV_FILE")"

if [[ ! -f "$ENV_FILE" ]]; then
    cat > "$ENV_FILE" <<EOF
# 天链V3 生产环境配置 (PostgreSQL)
# 由 setup-pg.sh 自动生成

DB_TYPE=postgres
DATABASE_URL=$DATABASE_URL

# 连接池
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=3600
DB_POOL_PRE_PING=true
EOF
    info "✅ 已生成: $ENV_FILE"
else
    info "配置已存在: $ENV_FILE (跳过)"
fi

# ─── 步骤 8: 可选迁移 ───
step "8. 数据迁移"
if [[ "$RUN_MIGRATION" == "yes" ]]; then
    MIGRATE_SCRIPT="$PROJECT_ROOT/scripts/migrate_sqlite_to_pg.py"
    if [[ -f "$MIGRATE_SCRIPT" ]]; then
        info "执行数据迁移..."
        $PYTHON "$MIGRATE_SCRIPT" \
            --pg-host "$PG_HOST" --pg-port "$PG_PORT" \
            --pg-db "$PG_DB" --pg-user "$PG_USER" --pg-password "$PG_PASSWORD"
    else
        warn "迁移脚本不存在: $MIGRATE_SCRIPT"
    fi
else
    info "跳过 (使用 --migrate 参数启用)"
fi

# ─── 完成 ───
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ✅ PostgreSQL 搭建完成!                ║"
echo "╠══════════════════════════════════════════╣"
echo "║   数据库: $PG_DB"
echo "║   用户:   $PG_USER"
echo "║   连接:   $PG_HOST:$PG_PORT"
echo "║   配置:   $ENV_FILE"
echo "╠══════════════════════════════════════════╣"
echo "║   启动服务:                              ║"
echo "║   DB_TYPE=postgres uvicorn ...           ║"
echo "║   或 docker-compose up -d                ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 清理
unset PGPASSWORD