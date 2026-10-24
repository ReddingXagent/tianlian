"""
Phase5-16: 性能索引迁移脚本
添加缺失的数据库索引以加速高频查询
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import SessionLocal
from sqlalchemy import text

INDEXES = [
    # alarms: 按 status 过滤 (dashboard, alarm list, stats)
    "CREATE INDEX IF NOT EXISTS idx_alarms_status ON alarms (status)",
    # alarms: 按 created_at 范围查询 (alarm stats, trends)
    "CREATE INDEX IF NOT EXISTS idx_alarms_created_at ON alarms (created_at)",
    # alarms: 复合索引 status + created_at (最常用: 活跃告警按时间排序)
    "CREATE INDEX IF NOT EXISTS idx_alarms_status_created ON alarms (status, created_at)",
    # alarms: 复合索引 station_id + status (站点维度告警统计)
    "CREATE INDEX IF NOT EXISTS idx_alarms_station_status ON alarms (station_id, status)",

    # work_orders: 按 status 过滤 (dashboard, order list, stats)
    "CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders (status)",
    # work_orders: 按 create_time 范围查询 (stats, trends)
    "CREATE INDEX IF NOT EXISTS idx_work_orders_create_time ON work_orders (create_time)",
    # work_orders: 按 finish_time 查询 (today_completed)
    "CREATE INDEX IF NOT EXISTS idx_work_orders_finish_time ON work_orders (finish_time)",
    # work_orders: 复合索引 assignee_id + status (工程师工单查询)
    "CREATE INDEX IF NOT EXISTS idx_work_orders_assignee_status ON work_orders (assignee_id, status)",
    # work_orders: 复合索引 station_id + status (站点维度)
    "CREATE INDEX IF NOT EXISTS idx_work_orders_station_status ON work_orders (station_id, status)",

    # devices: 按 status 过滤 (高频: dashboard 设备统计)
    "CREATE INDEX IF NOT EXISTS idx_devices_status ON devices (status)",
    # devices: 复合索引 station_id + status (站点设备概览)
    "CREATE INDEX IF NOT EXISTS idx_devices_station_status ON devices (station_id, status)",

    # stations: 按 status 过滤 (dashboard)
    "CREATE INDEX IF NOT EXISTS idx_stations_status ON stations (status)",

    # telemetry_data: device_id + timestamp 复合 (设备遥测历史)
    "CREATE INDEX IF NOT EXISTS idx_telemetry_device_ts ON telemetry_data (device_id, timestamp)",

    # users: 按 role 过滤 (工程师绩效查询)
    "CREATE INDEX IF NOT EXISTS idx_users_role ON users (role)",

    # device_efficiency_logs: 按 log_date 范围查询
    "CREATE INDEX IF NOT EXISTS idx_device_eff_log_date ON device_efficiency_logs (log_date)",
]

REMOVE_DUPLICATES = [
    # 清理可能存在的命名冲突索引
    "DROP INDEX IF EXISTS idx_workorder_status",
    "DROP INDEX IF EXISTS idx_alarm_status",
    "DROP INDEX IF EXISTS idx_device_status",
    "DROP INDEX IF EXISTS idx_station_status",
]

def run():
    db = SessionLocal()
    try:
        print("Phase5-16: 添加性能索引...")
        
        # 清理旧索引
        for sql in REMOVE_DUPLICATES:
            try:
                db.execute(text(sql))
            except Exception:
                pass
        db.commit()

        # 创建新索引
        created = 0
        for sql in INDEXES:
            try:
                db.execute(text(sql))
                created += 1
                print(f"  ✅ {sql.split('ON')[1].strip().split('(')[0].strip()}")
            except Exception as e:
                print(f"  ⚠️  跳过: {str(e)[:80]}")

        db.commit()
        print(f"\n共创建 {created}/{len(INDEXES)} 个索引")

        # 验证: 列出所有新增索引
        print("\n--- 验证: 新增索引 ---")
        result = db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_%' ORDER BY name"
        ))
        idx_list = [row[0] for row in result]
        print(f"数据库共 {len(idx_list)} 个前缀索引: {', '.join(sorted(idx_list)[-20:])}")

    finally:
        db.close()

if __name__ == "__main__":
    run()