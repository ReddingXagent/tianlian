#!/usr/bin/env python3
"""修复迁移：处理enum大小写+FK问题，重跑work_orders和alarms"""
import os
import sqlite3
import psycopg2

SQLITE_PATH = "/opt/tianlian-cloud_backup_20260722_020231/backend/tianlian_v3.db"
# [卡439a1fcd] 从环境变量读取 PG 连接串, 不再硬编码明文凭证。
# 优先 DATABASE_URL (与 app/core/database.py 一致), 兼容 PG_DSN。
PG_DSN = os.getenv("DATABASE_URL") or os.getenv("PG_DSN")
if not PG_DSN:
    raise RuntimeError(
        "未配置 PG 连接串: 请设置 DATABASE_URL 或 PG_DSN 环境变量 "
        "(如 postgresql://user:password@host:5432/dbname)。原硬编码凭证已移除。"
    )

# enum值映射：SQLite大写 → PG小写
ENUM_MAP = {
    "workorderstatus": {"ACCEPTED": "accepted", "COMPLETED": "completed", "PENDING": "pending", "PROCESSING": "processing"},
    "workordertype": {"REPAIR": "repair", "MAINTENANCE": "maintenance", "INSPECTION": "inspection", "UPGRADE": "upgrade"},
    "workorderlevel": {"WARNING": "warning", "INFO": "info", "CRITICAL": "critical"},
    "alarmlevel": {"WARNING": "warning", "INFO": "info", "CRITICAL": "critical", "FATAL": "fatal"},
}

# FK列：如果引用的ID不存在则置NULL
FK_NULL_COLS = {
    "work_orders": ["creator_id", "assignee_id"],  # 999等不存在的用户
}


def get_pg_columns(pg_cur, table):
    pg_cur.execute("""
        SELECT column_name, data_type, udt_name, is_nullable
        FROM information_schema.columns
        WHERE table_name = %s AND table_schema = 'public'
        ORDER BY ordinal_position
    """, (table,))
    return {r[0]: {"type": r[1], "udt": r[2], "nullable": r[3] == "YES"} for r in pg_cur.fetchall()}


def get_sqlite_columns(sq_cur, table):
    sq_cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in sq_cur.fetchall()]


def convert_value(val, col_info, col_name, table):
    if val is None:
        return None
    udt = col_info["udt"]
    # enum类型：转小写
    if udt in ENUM_MAP:
        mapped = ENUM_MAP[udt].get(str(val))
        if mapped:
            return mapped
        # 已经是小写或PG原生值
        return str(val).lower() if str(val).isupper() else str(val)
    # boolean
    if col_info["type"] == "boolean":
        return bool(val)
    # integer
    if col_info["type"] in ("integer", "bigint", "smallint"):
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    # numeric
    if col_info["type"] in ("numeric", "double precision", "real"):
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    return val


def check_fk_exists(pg_cur, ref_table, ref_id):
    """检查FK引用的ID是否存在"""
    if ref_id is None:
        return True
    pg_cur.execute(f"SELECT 1 FROM {ref_table} WHERE id = %s", (ref_id,))
    return pg_cur.fetchone() is not None


def migrate_table(sq_cur, pg_conn, pg_cur, table):
    pg_cols = get_pg_columns(pg_cur, table)
    sq_cols = get_sqlite_columns(sq_cur, table)
    common_cols = [c for c in sq_cols if c in pg_cols]
    fk_null_cols = FK_NULL_COLS.get(table, [])

    sq_cur.execute(f"SELECT {', '.join(common_cols)} FROM {table}")
    rows = sq_cur.fetchall()
    if not rows:
        print(f"  {table}: 0行")
        return 0

    # 先清空已有数据（之前部分迁移的）
    pg_cur.execute(f"DELETE FROM {table}")
    pg_conn.commit()
    print(f"  已清空 {table} 旧数据")

    insert_cols = [c for c in common_cols if c not in fk_null_cols]
    col_list = ", ".join(insert_cols)
    placeholders = ", ".join(["%s"] * len(insert_cols))
    has_id = "id" in insert_cols
    sql = f'INSERT INTO {table} ({col_list}) VALUES ({placeholders})'
    if has_id:
        sql += ' ON CONFLICT (id) DO NOTHING'

    success = 0
    errors = 0
    for row in rows:
        vals = []
        for i, c in enumerate(common_cols):
            if c in fk_null_cols:
                # 检查FK是否存在，不存在则置NULL
                ref_table = "users"  # work_orders的creator_id/assignee_id都引用users
                if not check_fk_exists(pg_cur, ref_table, row[i]):
                    vals.append(None)
                    continue
            vals.append(convert_value(row[i], pg_cols[c], c, table))

        try:
            pg_cur.execute(sql, vals)
            success += pg_cur.rowcount
        except Exception as e:
            errors += 1
            pg_conn.rollback()
            if errors <= 3:
                print(f"  ✗ {table} err: {e}")
            elif errors == 4:
                print(f"  ... 后续错误省略")

    pg_conn.commit()
    print(f"  ✓ {table}: {success} inserted, {errors} errors")
    return success


def main():
    print("=== 修复迁移: work_orders + alarms ===")
    sq_conn = sqlite3.connect(SQLITE_PATH)
    sq_cur = sq_conn.cursor()
    pg_conn = psycopg2.connect(PG_DSN)
    pg_cur = pg_conn.cursor()

    total = 0
    for table in ["work_orders", "alarms"]:
        print(f"\n[修复] {table}...")
        total += migrate_table(sq_cur, pg_conn, pg_cur, table)

    # 验证
    print(f"\n=== 验证 ===")
    for table in ["teams", "users", "stations", "devices", "work_orders", "alarms", "charging_orders"]:
        pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {pg_cur.fetchone()[0]} rows")

    # 修复序列
    for table in ["work_orders", "alarms"]:
        try:
            pg_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 0) + 1, false) FROM {table}")
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()

    sq_conn.close()
    pg_conn.close()
    print(f"\n=== 修复完成, 共插入 {total} 行 ===")


if __name__ == "__main__":
    main()