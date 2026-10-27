#!/usr/bin/env python3
"""修复迁移v2：处理所有enum大小写+FK问题"""
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

# 所有enum映射：SQLite值 → PG值（小写）
ENUM_MAP = {
    "workorderstatus": {"ACCEPTED": "accepted", "COMPLETED": "completed", "PENDING": "pending", "PROCESSING": "processing"},
    "workordertype": {"REPAIR": "repair", "MAINTENANCE": "maintenance", "INSPECTION": "inspection", "UPGRADE": "upgrade"},
    "workorderlevel": {"WARNING": "warning", "INFO": "info", "CRITICAL": "critical"},
    "alarmlevel": {"WARNING": "warning", "INFO": "info", "CRITICAL": "critical", "FATAL": "fatal"},
    "alarmstatus": {"ACKNOWLEDGED": "acknowledged", "ACTIVE": "active", "RESOLVED": "resolved", "PROCESSING": "processing", "PROCESSED": "processed", "IGNORED": "ignored"},
}

# FK列：引用users表，不存在则置NULL
FK_USER_COLS = {"work_orders": ["creator_id", "assignee_id"]}


def get_pg_columns(pg_cur, table):
    pg_cur.execute("""
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_name = %s AND table_schema = 'public'
        ORDER BY ordinal_position
    """, (table,))
    return {r[0]: {"type": r[1], "udt": r[2]} for r in pg_cur.fetchall()}


def get_sqlite_columns(sq_cur, table):
    sq_cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in sq_cur.fetchall()]


def convert_value(val, col_info):
    if val is None:
        return None
    udt = col_info["udt"]
    if udt in ENUM_MAP:
        s = str(val)
        return ENUM_MAP[udt].get(s, s.lower() if s.isupper() else s)
    if col_info["type"] == "boolean":
        return bool(val)
    if col_info["type"] in ("integer", "bigint", "smallint"):
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    if col_info["type"] in ("numeric", "double precision", "real"):
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    return val


def migrate_table(sq_cur, pg_conn, pg_cur, table):
    pg_cols = get_pg_columns(pg_cur, table)
    sq_cols = get_sqlite_columns(sq_cur, table)
    common_cols = [c for c in sq_cols if c in pg_cols]
    fk_cols = FK_USER_COLS.get(table, [])

    sq_cur.execute(f"SELECT {', '.join(common_cols)} FROM {table}")
    rows = sq_cur.fetchall()
    if not rows:
        print(f"  {table}: 0行")
        return 0

    # 清空旧数据
    pg_cur.execute(f"DELETE FROM {table}")
    pg_conn.commit()

    # 构建INSERT（包含所有common_cols，FK列也包含但可能置NULL）
    col_list = ", ".join(common_cols)
    placeholders = ", ".join(["%s"] * len(common_cols))
    has_id = "id" in common_cols
    sql = f'INSERT INTO {table} ({col_list}) VALUES ({placeholders})'
    if has_id:
        sql += ' ON CONFLICT (id) DO NOTHING'

    # 预查有效user ids
    pg_cur.execute("SELECT id FROM users")
    valid_users = {r[0] for r in pg_cur.fetchall()}

    success = 0
    errors = 0
    for row in rows:
        vals = []
        for i, c in enumerate(common_cols):
            v = row[i]
            # FK列：引用不存在的user则置NULL
            if c in fk_cols and v is not None:
                try:
                    if int(v) not in valid_users:
                        v = None
                except (ValueError, TypeError):
                    v = None
            vals.append(convert_value(v, pg_cols[c]))

        try:
            pg_cur.execute(sql, vals)
            success += pg_cur.rowcount
        except Exception as e:
            errors += 1
            pg_conn.rollback()
            if errors <= 5:
                print(f"  ✗ err: {str(e).strip()[:120]}")

    pg_conn.commit()
    print(f"  ✓ {table}: {success} inserted, {errors} errors")
    return success


def main():
    print("=== 修复迁移v2: work_orders + alarms ===")
    sq = sqlite3.connect(SQLITE_PATH)
    sq_cur = sq.cursor()
    pg = psycopg2.connect(PG_DSN)
    pg_cur = pg.cursor()

    total = 0
    for t in ["work_orders", "alarms"]:
        print(f"\n[修复] {t}...")
        total += migrate_table(sq_cur, pg, pg_cur, t)

    print(f"\n=== 最终验证 ===")
    for t in ["teams", "users", "stations", "devices", "work_orders", "alarms", "charging_orders"]:
        pg_cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t}: {pg_cur.fetchone()[0]} rows")

    sq.close()
    pg.close()
    print(f"\n=== 完成, 插入 {total} 行 ===")


if __name__ == "__main__":
    main()