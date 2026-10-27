#!/usr/bin/env bash
# ─── 天链V3 SQLite → PostgreSQL 数据迁移脚本 ───
# 用法: ./scripts/migrate-to-postgres.sh
# 要求: Python 3, pip, sqlite3, psql 客户端

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"

# ─── 配置 ───
SQLITE_DB="${SQLITE_DB:-$BACKEND_DIR/tianlian_v3.db}"
PG_URL="${PG_URL:-postgresql://tianlian:tianlian123@localhost:5432/tianlian_v3}"
TEMP_DIR="$PROJECT_DIR/tmp/migration_$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$PROJECT_DIR/backups/migration_$(date +%Y%m%d_%H%M%S)"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ─── 前置检查 ───
check_prerequisites() {
    log_info "检查前置条件..."
    
    if [ ! -f "$SQLITE_DB" ]; then
        log_error "SQLite 数据库不存在: $SQLITE_DB"
        exit 1
    fi

    if ! command -v sqlite3 &>/dev/null; then
        log_error "未安装 sqlite3，请先安装: brew install sqlite"
        exit 1
    fi

    if ! command -v python3 &>/dev/null; then
        log_error "未安装 python3"
        exit 1
    fi

    # 检查 psycopg2
    python3 -c "import psycopg2" 2>/dev/null || {
        log_warn "未安装 psycopg2-binary，正在安装..."
        pip install psycopg2-binary
    }

    log_info "前置条件检查通过 ✓"
}

# ─── 备份 SQLite 数据库 ───
backup_sqlite() {
    log_info "备份 SQLite 数据库..."
    mkdir -p "$BACKUP_DIR"
    cp "$SQLITE_DB" "$BACKUP_DIR/tianlian_v3.db"
    log_info "备份完成: $BACKUP_DIR/tianlian_v3.db"
}

# ─── 导出 SQLite 数据为 SQL ───
export_sqlite() {
    log_info "从 SQLite 导出数据..."
    mkdir -p "$TEMP_DIR"

    # 导出 schema + data
    sqlite3 "$SQLITE_DB" .dump > "$TEMP_DIR/sqlite_dump.sql"
    
    # 获取所有表名
    sqlite3 "$SQLITE_DB" ".tables" | tr ' ' '\n' | grep -v '^$' > "$TEMP_DIR/tables.txt"
    
    # 记录每个表的行数
    while IFS= read -r table; do
        local count
        count=$(sqlite3 "$SQLITE_DB" "SELECT COUNT(*) FROM \"$table\";")
        echo "$table:$count" >> "$TEMP_DIR/sqlite_counts.txt"
        log_info "  $table: $count 行"
    done < "$TEMP_DIR/tables.txt"

    log_info "SQLite 导出完成 → $TEMP_DIR/sqlite_dump.sql"
}

# ─── 转换 SQLite SQL 为 PostgreSQL 兼容 SQL ───
convert_to_pg() {
    log_info "转换 SQLite SQL → PostgreSQL 兼容格式..."
    
    cp "$TEMP_DIR/sqlite_dump.sql" "$TEMP_DIR/pg_import.sql"
    
    # 1. 移除 SQLite PRAGMA 语句
    sed -i '' '/^PRAGMA/d' "$TEMP_DIR/pg_import.sql"
    
    # 2. 类型转换: INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
    #    处理表定义中的 AUTOINCREMENT
    sed -i '' 's/INTEGER PRIMARY KEY AUTOINCREMENT/SERIAL PRIMARY KEY/g' "$TEMP_DIR/pg_import.sql"
    sed -i '' 's/INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT/SERIAL PRIMARY KEY/g' "$TEMP_DIR/pg_import.sql"
    
    # 3. 移除 "sqlite_sequence" 表
    sed -i '' '/CREATE TABLE sqlite_sequence/d' "$TEMP_DIR/pg_import.sql"
    
    # 4. BOOLEAN 转换: SQLite 存 0/1 → PostgreSQL BOOLEAN 字段用 TRUE/FALSE
    #    这个依赖具体 schema，Python 脚本处理更准确
    sed -i '' 's/\"BOOLEAN\"/\"BOOLEAN\"/Ig' "$TEMP_DIR/pg_import.sql" 2>/dev/null || true
    
    # 5. 处理引号：SQLite 双引号标识符 → PostgreSQL 保留
    #    (PostgreSQL 也支持双引号)
    
    # 6. 移除 rowid 引用
    sed -i '' 's/rowid/SERIAL/g' "$TEMP_DIR/pg_import.sql"
    
    # 7. PostgreSQL 不支持 DATETIME 类型，改为 TIMESTAMP
    sed -i '' 's/DATETIME/TIMESTAMP/g' "$TEMP_DIR/pg_import.sql"
    
    log_info "SQL 转换完成 → $TEMP_DIR/pg_import.sql"
}

# ─── Python 辅助: 使用 SQLAlchemy 迁移 ───
migrate_via_sqlalchemy() {
    log_info "使用 SQLAlchemy 执行数据迁移..."
    
    python3 - "$SQLITE_DB" "$PG_URL" "$TEMP_DIR" << 'PYEOF'
import sys
import sqlite3
import psycopg2
from urllib.parse import urlparse

sqlite_path = sys.argv[1]
pg_url = sys.argv[2]
temp_dir = sys.argv[3]

# 解析 PostgreSQL URL
parsed = urlparse(pg_url)
pg_config = {
    'host': parsed.hostname,
    'port': parsed.port or 5432,
    'dbname': parsed.path.lstrip('/'),
    'user': parsed.username,
    'password': parsed.password,
}

def pg_connect():
    return psycopg2.connect(**pg_config)

# 连接数据库
sqlite_conn = sqlite3.connect(sqlite_path)
sqlite_conn.row_factory = sqlite3.Row
sqlite_cur = sqlite_conn.cursor()

pg_conn = pg_connect()
pg_conn.autocommit = False
pg_cur = pg_conn.cursor()

# 获取所有用户表
sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_prisma%' ORDER BY name;")
tables = [row[0] for row in sqlite_cur.fetchall()]

# 获取所有表名并排序（参考外键依赖，先导入无外键的表）
# 简化处理：先禁用外键检查，导入后再启用
pg_cur.execute("SET session_replication_role = 'replica';")

# SQLite → PostgreSQL 类型映射
TYPE_MAP = {
    'INTEGER': 'INTEGER',
    'INT': 'INTEGER',
    'TEXT': 'TEXT',
    'VARCHAR': 'VARCHAR',
    'FLOAT': 'FLOAT',
    'REAL': 'FLOAT',
    'DOUBLE': 'DOUBLE PRECISION',
    'BOOLEAN': 'BOOLEAN',
    'BOOL': 'BOOLEAN',
    'BLOB': 'BYTEA',
    'DATETIME': 'TIMESTAMP',
    'TIMESTAMP': 'TIMESTAMP',
    'DATE': 'DATE',
    'TIME': 'TIME',
    'JSON': 'JSONB',
}

def convert_sqlite_type(sqlite_type):
    """将 SQLite 类型转换为 PostgreSQL 类型"""
    upper = sqlite_type.upper().split('(')[0].strip()
    return TYPE_MAP.get(upper, 'TEXT')

def sanitize_value(col_name, col_type, value):
    """清理值以兼容 PostgreSQL"""
    if value is None:
        return None
    upper_type = col_type.upper() if col_type else 'TEXT'
    
    # BOOLEAN: SQLite 存 0/1 → PostgreSQL 用 True/False
    if 'BOOL' in upper_type:
        if isinstance(value, int):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ('1', 'true', 't', 'yes', 'y')
        return bool(value)
    
    # BLOB → 十六进制
    if upper_type == 'BLOB' and isinstance(value, bytes):
        return value
    
    return value

total_migrated = 0
errors = []

for table in tables:
    try:
        # 获取列信息
        sqlite_cur.execute(f'PRAGMA table_info("{table}")')
        columns = sqlite_cur.fetchall()
        col_names = [col[1] for col in columns]  # name
        col_types = [col[2] for col in columns]  # type
        
        # 获取数据
        sqlite_cur.execute(f'SELECT * FROM "{table}"')
        rows = sqlite_cur.fetchall()
        
        if not rows:
            print(f"  {table}: 0 行 (跳过)")
            continue
        
        # 构建 INSERT 语句
        placeholders = ', '.join(['%s'] * len(col_names))
        quoted_names = ', '.join([f'"{name}"' for name in col_names])
        insert_sql = f'INSERT INTO "{table}" ({quoted_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
        
        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            pg_values = []
            for row in batch:
                values = []
                for j, val in enumerate(row):
                    values.append(sanitize_value(col_names[j], col_types[j], val))
                pg_values.append(tuple(values))
            
            psycopg2.extras.execute_values(pg_cur, insert_sql.replace('%s', '%s'), pg_values)
        
        pg_conn.commit()
        total_migrated += len(rows)
        print(f"  {table}: {len(rows)} 行 ✓")
        
    except Exception as e:
        errors.append(f"{table}: {e}")
        pg_conn.rollback()
        print(f"  {table}: 错误 - {e}")
        # 继续处理其他表

# 重新启对键检查
pg_cur.execute("SET session_replication_role = 'origin';")
pg_conn.commit()

# 更新序列（对于 SERIAL 主键列）
pg_cur.execute("""
    SELECT 'SELECT SETVAL(' ||
           quote_literal(quote_ident(PGT.schemaname) || '.' || quote_ident(S.relname)) ||
           ', COALESCE(MAX(' || quote_ident(C.attname) || '), 1)) FROM ' ||
           quote_ident(PGT.schemaname) || '.' || quote_ident(T.relname) || ';'
    FROM pg_class AS S,
         pg_depend AS D,
         pg_class AS T,
         pg_attribute AS C,
         pg_tables AS PGT
    WHERE S.relkind = 'S'
      AND S.oid = D.objid
      AND D.refobjid = T.oid
      AND D.refobjid = C.attrelid
      AND D.refobjsubid = C.attnum
      AND T.relname = PGT.tablename
    ORDER BY S.relname;
""")
seq_updates = pg_cur.fetchall()
if seq_updates:
    for (sql,) in seq_updates:
        try:
            pg_cur.execute(sql)
        except Exception:
            pass
pg_conn.commit()

# 清理
sqlite_cur.close()
sqlite_conn.close()
pg_cur.close()
pg_conn.close()

print(f"\n总计迁移: {total_migrated} 行")
for err in errors:
    print(f"  错误: {err}")

# 写入状态文件
with open(f"{temp_dir}/migration_status.txt", 'w') as f:
    f.write(f"total_rows={total_migrated}\n")
    f.write(f"errors={len(errors)}\n")
    for err in errors:
        f.write(f"error={err}\n")
PYEOF
    
    log_info "SQLAlchemy 迁移完成"
}

# ─── 验证数据一致性 ───
verify_migration() {
    log_info "验证数据一致性..."
    
    sqlite3 "$SQLITE_DB" ".tables" | tr ' ' '\n' | grep -v '^$' > "$TEMP_DIR/tables.txt"
    
    local mismatch=0
    while IFS= read -r table; do
        local sqlite_count pg_count
        sqlite_count=$(sqlite3 "$SQLITE_DB" "SELECT COUNT(*) FROM \"$table\";")
        
        # 提取 PG 连接信息
        pg_count=$(python3 -c "
import psycopg2
from urllib.parse import urlparse
u = urlparse('$PG_URL')
conn = psycopg2.connect(host=u.hostname, port=u.port or 5432, dbname=u.path.lstrip('/'), user=u.username, password=u.password)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM \"${table}\"')
print(cur.fetchone()[0])
conn.close()
" 2>/dev/null || echo "N/A")
        
        if [ "$sqlite_count" != "$pg_count" ]; then
            log_warn "  $table: SQLite=$sqlite_count vs PG=$pg_count ✗"
            mismatch=$((mismatch + 1))
        else
            log_info "  $table: $sqlite_count = $pg_count ✓"
        fi
    done < "$TEMP_DIR/tables.txt"
    
    if [ "$mismatch" -gt 0 ]; then
        log_error "存在 $mismatch 个表行数不一致！请检查迁移日志。"
        return 1
    else
        log_info "数据一致性验证通过 ✓"
        return 0
    fi
}

# ─── 回滚方案 ───
show_rollback_instructions() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  回滚方法"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  如需回滚到 SQLite:"
    echo ""
    echo "  1. 修改 .env 文件:"
    echo "     DB_TYPE=sqlite"
    echo ""
    echo "  2. 重启服务:"
    echo "     docker-compose down && docker-compose up -d"
    echo ""
    echo "  3. SQLite 备份位于:"
    echo "     $BACKUP_DIR/tianlian_v3.db"
    echo ""
    echo "  4. 如需恢复备份:"
    echo "     cp $BACKUP_DIR/tianlian_v3.db $SQLITE_DB"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ─── 主流程 ───
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║   天链V3 SQLite → PostgreSQL 数据迁移              ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    log_info "SQLite: $SQLITE_DB"
    log_info "PostgreSQL: $PG_URL"
    echo ""
    
    # 确认
    read -r -p "确认开始迁移？(y/N) " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "已取消。"
        exit 0
    fi
    
    # 步骤
    check_prerequisites
    backup_sqlite
    migrate_via_sqlalchemy
    verify_migration || true
    show_rollback_instructions
    
    echo ""
    log_info "迁移完成！请将 .env 中 DB_TYPE 改为 postgres 后重启服务。"
    log_info "临时文件: $TEMP_DIR"
    log_info "备份文件: $BACKUP_DIR"
}

main "$@"