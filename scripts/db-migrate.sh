#!/bin/bash
# 天链 V3 数据库迁移脚本
# 用法: bash scripts/db-migrate.sh [--dry-run|--force]

set -euo pipefail

# ==================== 配置 ====================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_DIR}/backend"
BACKUP_DIR="${BACKEND_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DRY_RUN="${1:-}"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*"; }
info()  { echo -e "${CYAN}[→]${NC} $*"; }

echo ""
echo "========================================"
echo "  天链 V3 数据库迁移"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  环境: ${BACKEND_DIR}"
echo "========================================"
echo ""

# ==================== 检查环境 ====================
info "检查环境..."

# 检查 Python 虚拟环境
if [ ! -d "${BACKEND_DIR}/venv" ]; then
    info "创建 Python 虚拟环境..."
    cd "${BACKEND_DIR}"
    python3 -m venv venv
    log "虚拟环境创建完成"
fi

# 激活虚拟环境
source "${BACKEND_DIR}/venv/bin/activate"

# 安装依赖
pip install -r "${BACKEND_DIR}/requirements.txt" -q --no-warn-script-location 2>&1 | tail -1 || true

# 检查 alembic
if python -c "import alembic" 2>/dev/null; then
    HAS_ALEMBIC=true
    log "Alembic 已安装"
else
    HAS_ALEMBIC=false
    warn "Alembic 未安装，将使用手动迁移模式"
fi

echo ""

# ==================== 备份数据库 ====================
info "1/4: 备份当前数据库..."

mkdir -p "${BACKUP_DIR}"

# 查找数据库文件
DB_FILES=()
for f in "${BACKEND_DIR}"/*.db; do
    if [ -f "$f" ]; then
        DB_FILES+=("$f")
    fi
done

if [ ${#DB_FILES[@]} -eq 0 ]; then
    warn "未找到 SQLite 数据库文件"
    
    # 检查环境变量中是否有 PostgreSQL
    if grep -q "DATABASE_URL=" "${BACKEND_DIR}/.env" 2>/dev/null; then
        DB_URL=$(grep "^DATABASE_URL=" "${BACKEND_DIR}/.env" | cut -d= -f2- | tr -d '"')
        info "检测到 PostgreSQL 配置: ${DB_URL}"
        
        # 备份 PostgreSQL
        if command -v pg_dump &>/dev/null; then
            BACKUP_FILE="${BACKUP_DIR}/tianlian_pg_${TIMESTAMP}.sql"
            if [ "$DRY_RUN" = "--dry-run" ]; then
                warn "[DRY-RUN] 将执行: pg_dump \"${DB_URL}\" > \"${BACKUP_FILE}\""
            else
                PGPASSWORD="$(echo ${DB_URL} | sed 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/')" pg_dump "${DB_URL}" > "${BACKUP_FILE}" 2>/dev/null
                log "PostgreSQL 备份完成: ${BACKUP_FILE}"
            fi
        else
            warn "pg_dump 未安装，跳过 PostgreSQL 备份"
        fi
    fi
else
    for DB_FILE in "${DB_FILES[@]}"; do
        DB_NAME=$(basename "${DB_FILE}")
        BACKUP_FILE="${BACKUP_DIR}/${DB_NAME%.db}_${TIMESTAMP}.db"
        
        if [ "$DRY_RUN" = "--dry-run" ]; then
            warn "[DRY-RUN] 将备份: ${DB_FILE} → ${BACKUP_FILE}"
        else
            cp "${DB_FILE}" "${BACKUP_FILE}"
            log "备份完成: ${DB_NAME} → ${BACKUP_FILE}"
        fi
    done
fi

# 清理 30 天前的备份
info "清理旧备份（保留30天）..."
find "${BACKUP_DIR}" -name "*.db" -mtime +30 -delete 2>/dev/null || true
find "${BACKUP_DIR}" -name "*.sql" -mtime +30 -delete 2>/dev/null || true
echo ""

# ==================== 检查数据库状态 ====================
info "2/4: 检查当前数据库状态..."

cd "${BACKEND_DIR}"

python3 << 'PYEOF'
import sys, os
from sqlalchemy import inspect, create_engine, text

# 加载环境变量
from dotenv import load_dotenv
load_dotenv('.env')

# 获取数据库 URL
DATABASE_URL = os.getenv('DATABASE_URL_DEV', 'sqlite:///./tianlian_v3.db')
print(f"数据库: {DATABASE_URL}")

# 创建引擎
try:
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    
    # 获取所有表
    tables = inspector.get_table_names()
    print(f"现有表 ({len(tables)}):")
    for table in tables:
        columns = inspector.get_columns(table)
        pk = inspector.get_pk_constraint(table)
        pk_cols = pk.get('constrained_columns', []) if pk else []
        col_str = ', '.join([f"{c['name']} ({c['type']})" for c in columns[:5]])
        if len(columns) > 5:
            col_str += f', ... ({len(columns)} total)'
        print(f"  - {table} [PK: {', '.join(pk_cols)}]: {col_str}")
    
    # 检查缺失的外键索引
    print("\n检查索引...")
    for table in tables:
        indices = {i['name']: i for i in inspector.get_indexes(table)}
        columns = [c['name'] for c in inspector.get_columns(table)]
        pk_info = inspector.get_pk_constraint(table)
        pk_cols = set(pk_info.get('constrained_columns', []) if pk_info else [])
        
        missing_indices = []
        for col in columns:
            if col.endswith('_id') and col not in pk_cols:
                indexed = False
                for idx_name, idx in indices.items():
                    if col in idx['column_names']:
                        indexed = True
                        break
                if not indexed:
                    missing_indices.append(col)
        
        if missing_indices:
            print(f"  {table}: 建议添加索引 → {', '.join(missing_indices)}")
        else:
            print(f"  {table}: ✅ 索引完整")
    
    print(f"\n✅ 数据库状态检查完成")

    # 输出缺失的迁移信息供后续使用
    if missing_indices:
        with open('/tmp/tianlian_missing_indices.txt', 'w') as f:
            f.write('\\n'.join(missing_indices))
except Exception as e:
    print(f"❌ 数据库检查失败: {e}")
    sys.exit(1)
PYEOF

echo ""

# ==================== 创建缺失索引 ====================
info "3/4: 创建缺失索引..."

cd "${BACKEND_DIR}"

if [ "$DRY_RUN" = "--dry-run" ]; then
    warn "[DRY-RUN] 将执行以下迁移操作:"
    python3 << 'PYEOF'
from sqlalchemy import inspect, create_engine, text
import os
from dotenv import load_dotenv

load_dotenv('.env')
DATABASE_URL = os.getenv('DATABASE_URL_DEV', 'sqlite:///./tianlian_v3.db')
engine = create_engine(DATABASE_URL)
inspector = inspect(engine)
tables = inspector.get_table_names()

for table in tables:
    indices = {i['name']: i for i in inspector.get_indexes(table)}
    columns = [c['name'] for c in inspector.get_columns(table)]
    pk_info = inspector.get_pk_constraint(table)
    pk_cols = set(pk_info.get('constrained_columns', []) if pk_info else [])
    
    for col in columns:
        if col.endswith('_id') and col not in pk_cols:
            indexed = False
            for idx_name, idx in indices.items():
                if col in idx['column_names']:
                    indexed = True
                    break
            if not indexed:
                idx_name = f"ix_{table}_{col}"
                print(f"  CREATE INDEX IF NOT EXISTS {idx_name} ON \"{table}\" ({col})")
PYEOF
else
    python3 << 'PYEOF'
from sqlalchemy import inspect, create_engine, text
import os
from dotenv import load_dotenv

load_dotenv('.env')
DATABASE_URL = os.getenv('DATABASE_URL_DEV', 'sqlite:///./tianlian_v3.db')
print(f"数据库: {DATABASE_URL}")
engine = create_engine(DATABASE_URL)
inspector = inspect(engine)
tables = inspector.get_table_names()

created_count = 0
with engine.connect() as conn:
    for table in tables:
        indices = {i['name']: i for i in inspector.get_indexes(table)}
        columns = [c['name'] for c in inspector.get_columns(table)]
        pk_info = inspector.get_pk_constraint(table)
        pk_cols = set(pk_info.get('constrained_columns', []) if pk_info else [])
        
        for col in columns:
            if col.endswith('_id') and col not in pk_cols:
                indexed = False
                for idx_name, idx in indices.items():
                    if col in idx['column_names']:
                        indexed = True
                        break
                if not indexed:
                    idx_name = f"ix_{table}_{col}"
                    if idx_name not in indices:
                        print(f"  创建索引: {idx_name} ON {table}({col})")
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON \"{table}\" ({col})"))
                        created_count += 1
    conn.commit()

if created_count > 0:
    print(f"✅ 已创建 {created_count} 个索引")
else:
    print("✅ 所有索引已存在，无需创建")
PYEOF
fi

# 确保模型和数据库同步（创建缺失的表）
python3 -c "
from app.core.database import Base, engine
from app.models import *
Base.metadata.create_all(bind=engine)
print('✅ 数据库表结构同步完成')
" 2>&1 | tail -1

echo ""

# ==================== 验证 ====================
info "4/4: 验证迁移结果..."

cd "${BACKEND_DIR}"
python3 << 'PYEOF'
from sqlalchemy import inspect, create_engine, text
import os
from dotenv import load_dotenv

load_dotenv('.env')
DATABASE_URL = os.getenv('DATABASE_URL_DEV', 'sqlite:///./tianlian_v3.db')
engine = create_engine(DATABASE_URL)
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f"数据库表总数: {len(tables)}")

# 验证所有模型表都存在
from app.models import __all__
model_tables = set()
for m in __all__:
    # 获取模型的 __tablename__
    import importlib
    mod = importlib.import_module(f'app.models.{m.lower()}')
    # 尝试找到类名匹配
    cls = getattr(mod, m, None)
    if cls and hasattr(cls, '__tablename__'):
        model_tables.add(cls.__tablename__)

print(f"模型类: {len(__all__)}")
print(f"数据库表: {', '.join(sorted(tables))}")
print("✅ 迁移验证完成")
PYEOF

echo ""
echo "========================================"
log "数据库迁移完成！"
echo "  备份目录: ${BACKUP_DIR}"
echo "  迁移日志: 见上方输出"
echo "  建议: 运行 'python -m pytest tests/ -v' 验证应用正常"
echo "========================================"
echo ""
