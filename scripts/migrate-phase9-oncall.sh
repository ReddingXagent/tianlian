#!/usr/bin/env bash
# Phase9 #52 - 值班排班系统数据库迁移
# 执行: bash scripts/migrate-phase9-oncall.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_PATH="${SCRIPT_DIR}/../tianlian_v3.db"

if [ ! -f "$DB_PATH" ]; then
  echo "❌ 数据库文件不存在: $DB_PATH"
  exit 1
fi

echo "📋 Phase9 #52 - 值班排班系统数据库迁移"
echo "📍 数据库: $DB_PATH"

# 检查表是否已存在
EXISTING=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='on_call_rules';" 2>/dev/null || true)

if [ -n "$EXISTING" ]; then
  echo "⚠️  on_call_rules 表已存在，跳过创建"
else
  echo "✅ 创建 on_call_rules 表..."
  sqlite3 "$DB_PATH" <<'SQL'
CREATE TABLE IF NOT EXISTS on_call_rules (
  id INTEGER PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  team_id INTEGER NOT NULL,
  station_id INTEGER,
  schedule_type VARCHAR(32) DEFAULT 'weekly',
  rotation_order JSON NOT NULL,
  shift_duration_hours INTEGER DEFAULT 168,
  overlap_minutes INTEGER DEFAULT 30,
  escalation_level INTEGER DEFAULT 2,
  escalation_timeout_minutes INTEGER DEFAULT 30,
  notify_methods JSON DEFAULT '["app","sms"]',
  auto_assign_workorders BOOLEAN DEFAULT 1,
  enabled BOOLEAN DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (team_id) REFERENCES teams(id),
  FOREIGN KEY (station_id) REFERENCES stations(id)
);
SQL
  echo "✅ on_call_rules 创建完成"
fi

EXISTING=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='on_call_shifts';" 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
  echo "⚠️  on_call_shifts 表已存在，跳过创建"
else
  echo "✅ 创建 on_call_shifts 表..."
  sqlite3 "$DB_PATH" <<'SQL'
CREATE TABLE IF NOT EXISTS on_call_shifts (
  id INTEGER PRIMARY KEY,
  rule_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  backup_user_id INTEGER,
  start_time TIMESTAMP NOT NULL,
  end_time TIMESTAMP NOT NULL,
  status VARCHAR(32) DEFAULT 'scheduled',
  handover_notes TEXT,
  handover_completed BOOLEAN DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rule_id) REFERENCES on_call_rules(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (backup_user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_oncall_shifts_rule_id ON on_call_shifts(rule_id);
CREATE INDEX IF NOT EXISTS idx_oncall_shifts_user_id ON on_call_shifts(user_id);
CREATE INDEX IF NOT EXISTS idx_oncall_shifts_start_time ON on_call_shifts(start_time);
SQL
  echo "✅ on_call_shifts 创建完成"
fi

EXISTING=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='on_call_logs';" 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
  echo "⚠️  on_call_logs 表已存在，跳过创建"
else
  echo "✅ 创建 on_call_logs 表..."
  sqlite3 "$DB_PATH" <<'SQL'
CREATE TABLE IF NOT EXISTS on_call_logs (
  id INTEGER PRIMARY KEY,
  shift_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  event_type VARCHAR(32) DEFAULT 'note',
  content TEXT NOT NULL,
  alarm_id INTEGER,
  workorder_id VARCHAR(50),
  severity VARCHAR(32) DEFAULT 'info',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (shift_id) REFERENCES on_call_shifts(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (alarm_id) REFERENCES alarms(id)
);
CREATE INDEX IF NOT EXISTS idx_oncall_logs_shift_id ON on_call_logs(shift_id);
SQL
  echo "✅ on_call_logs 创建完成"
fi

echo ""
echo "🎉 Phase9 #52 数据库迁移完成!"
echo ""
echo "📊 表结构验证:"
sqlite3 "$DB_PATH" ".tables on_call*" 2>/dev/null
echo ""
echo "📋 表详情:"
sqlite3 "$DB_PATH" "SELECT 'on_call_rules: ' || COUNT(*) || ' 条记录' FROM on_call_rules;"
sqlite3 "$DB_PATH" "SELECT 'on_call_shifts: ' || COUNT(*) || ' 条记录' FROM on_call_shifts;"
sqlite3 "$DB_PATH" "SELECT 'on_call_logs: ' || COUNT(*) || ' 条记录' FROM on_call_logs;"
