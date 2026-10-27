#!/usr/bin/env python3
"""一次性迁移脚本：从备份SQLite恢复业务数据到PostgreSQL
用法: python3 migrate_sqlite_to_pg.py
"""
import os
import sqlite3
import sys
import psycopg2
import psycopg2.extras

SQLITE_PATH = "/opt/tianlian-cloud_backup_20260722_020231/backend/tianlian_v3.db"
# [卡439a1fcd] 从环境变量读取 PG 连接串, 不再硬编码明文凭证。
# 优先 DATABASE_URL (与 app/core/database.py 一致), 兼容 PG_DSN。
PG_DSN = os.getenv("DATABASE_URL") or os.getenv("PG_DSN")
if not PG_DSN:
    raise RuntimeError(
        "未配置 PG 连接串: 请设置 DATABASE_URL 或 PG_DSN 环境变量 "
        "(如 postgresql://user:password@host:5432/dbname)。原硬编码凭证已移除。"
    )

# 迁移顺序：先无FK依赖的表，再有FK依赖的表
TABLES = ["teams", "users", "stations", "devices", "work_orders", "alarms", "charging_orders"]

# 已知悬空FK：SQLite有但PG中引用表可能无数据 → 置NULL
DANGLING_FK_COLS = {
    "devices": ["gateway_id"],       # gateways表无数据
    "alarms": ["rule_id"],           # alarm_rules表无数据
    "work_orders": ["device_id"],    # 可能引用不存在的device
}


def get_pg_columns(pg_cur, table):
    """获取PG表的列名、数据类型、是否可空"""
    pg_cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = %s AND table_schema = 'public'
        ORDER BY ordinal_position
    """, (table,))
    return {row[0]: {"type": row[1], "nullable": row[2] == "YES", "default": row[3]} for row in pg_cur.fetchall()}


def get_sqlite_columns(sq_cur, table):
    """获取SQLite表的列名"""
    sq_cur.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in sq_cur.fetchall()]


def convert_value(val, pg_type):
    """SQLite→PG类型转换"""
    if val is None:
        return None
    # boolean: SQLite存0/1, PG要True/False
    if pg_type == "boolean":
        return bool(val)
    # integer/bigint: 确保是int
    if pg_type in ("integer", "bigint", "smallint"):
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    # numeric/float
    if pg_type in ("numeric", "double precision", "real"):
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    return val


def migrate_table(sq_cur, pg_conn, pg_cur, table):
    """迁移单张表"""
    pg_cols = get_pg_columns(pg_cur, table)
    sq_cols = get_sqlite_columns(sq_cur, table)

    if not pg_cols:
        print(f"  ⚠ PG中不存在表 {table}, 跳过")
        return 0
    if not sq_cols:
        print(f"  ⚠ SQLite中不存在表 {table}, 跳过")
        return 0

    # 取交集列（PG有且SQLite有的列）
    common_cols = [c for c in sq_cols if c in pg_cols]
    # 悬空FK列置NULL
    dangling = DANGLING_FK_COLS.get(table, [])

    # 读取SQLite数据
    sq_cur.execute(f"SELECT {', '.join(common_cols)} FROM {table}")
    rows = sq_cur.fetchall()

    if not rows:
        print(f"  {table}: 0行, 跳过")
        return 0

    # 构建INSERT ... ON CONFLICT DO NOTHING
    insert_cols = []
    for c in common_cols:
        if c in dangling:
            continue  # 悬空FK列不插入，让PG用默认值(NULL)
        insert_cols.append(c)

    col_list = ", ".join(insert_cols)
    placeholders = ", ".join(["%s"] * len(insert_cols))

    # 检测是否有id列（用于ON CONFLICT）
    has_id = "id" in insert_cols
    if has_id:
        sql = f'INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING'
    else:
        sql = f'INSERT INTO {table} ({col_list}) VALUES ({placeholders})'

    success = 0
    skipped = 0
    errors = 0

    for row in rows:
        # 构建值列表
        vals = []
        for i, c in enumerate(common_cols):
            if c in dangling:
                continue
            pg_type = pg_cols[c]["type"]
            vals.append(convert_value(row[i], pg_type))

        try:
            pg_cur.execute(sql, vals)
            if pg_cur.rowcount > 0:
                success += 1
            else:
                skipped += 1  # ON CONFLICT跳过
        except Exception as e:
            errors += 1
            print(f"  ✗ {table} 行错误: {e}")
            pg_conn.rollback()
            # 重试单行
            try:
                pg_cur.execute(sql, vals)
                if pg_cur.rowcount > 0:
                    success += 1
                    errors -= 1
            except Exception:
                pg_conn.rollback()

    pg_conn.commit()
    print(f"  ✓ {table}: {success} inserted, {skipped} skipped(conflict), {errors} errors")
    return success


def main():
    print(f"=== SQLite→PG 数据迁移 ===")
    print(f"SQLite: {SQLITE_PATH}")
    print(f"PG: {PG_DSN}")
    print()

    sq_conn = sqlite3.connect(SQLITE_PATH)
    sq_cur = sq_conn.cursor()

    pg_conn = psycopg2.connect(PG_DSN)
    pg_cur = pg_conn.cursor()

    total = 0
    for table in TABLES:
        print(f"[迁移] {table}...")
        count = migrate_table(sq_cur, pg_conn, pg_cur, table)
        total += count

    # 验证
    print(f"\n=== 验证 ===")
    for table in TABLES:
        pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
        cnt = pg_cur.fetchone()[0]
        print(f"  {table}: {cnt} rows")

    # 修复序列（确保id自增不冲突）
    print(f"\n=== 修复序列 ===")
    for table in TABLES:
        try:
            pg_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 0) + 1, false) FROM {table}")
            pg_conn.commit()
            print(f"  ✓ {table}_id_seq 已修复")
        except Exception as e:
            pg_conn.rollback()
            print(f"  ⚠ {table}: {e}")

    sq_conn.close()
    pg_conn.close()
    print(f"\n=== 迁移完成, 共插入 {total} 行 ===")


if __name__ == "__main__":
    main()