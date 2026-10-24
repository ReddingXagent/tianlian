#!/usr/bin/env bash
# 统一数据库迁移脚本 - 修复云端SQLite缺失的表和列
# 解决: stations.tenant_id 列不存在导致500错误
# 执行: bash scripts/migrate-fix-cloud-db.sh

set -e

echo "🔧 天链V3 云端数据库迁移 - 修复缺失表/列"
echo "================================================"

# 云端数据库位置
DB_PATH="${1:-/app/data/tianlian.db}"

if [ ! -f "$DB_PATH" ]; then
  echo "❌ 数据库文件不存在: $DB_PATH"
  exit 1
fi

echo "📍 数据库: $DB_PATH"

# 备份
cp "$DB_PATH" "${DB_PATH}.bak.$(date +%Y%m%d%H%M%S)"
echo "✅ 备份完成"

# ============ 1. 创建 tenants 表（如果不存在） ============
echo ""
echo "📋 检查 tenants 表..."
TENANTS_EXISTS=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='tenants';" 2>/dev/null || true)

if [ -n "$TENANTS_EXISTS" ]; then
  echo "  ✅ tenants 表已存在"
else
  echo "  🆕 创建 tenants 表..."
  sqlite3 "$DB_PATH" <<'SQL'
CREATE TABLE IF NOT EXISTS tenants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(100) NOT NULL,
  code VARCHAR(50) NOT NULL UNIQUE,
  description TEXT,
  contact_name VARCHAR(50),
  contact_phone VARCHAR(20),
  contact_email VARCHAR(100),
  status VARCHAR(20) DEFAULT 'active',
  plan VARCHAR(20) DEFAULT 'basic',
  max_stations INTEGER DEFAULT 10,
  max_devices INTEGER DEFAULT 100,
  max_users INTEGER DEFAULT 20,
  settings TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME
);
INSERT OR IGNORE INTO tenants (id, name, code, status, plan) VALUES (1, '默认租户', 'default', 'active', 'enterprise');
SQL
  echo "  ✅ tenants 表创建完成"
fi

# ============ 2. 给 stations 添加 tenant_id 列（如果缺失） ============
echo ""
echo "📋 检查 stations.tenant_id 列..."
STATION_COLS=$(sqlite3 "$DB_PATH" "PRAGMA table_info(stations);" 2>/dev/null || true)
TENANT_ID_EXISTS=$(echo "$STATION_COLS" | grep "tenant_id" || true)

if [ -n "$TENANT_ID_EXISTS" ]; then
  echo "  ✅ stations.tenant_id 列已存在"
else
  echo "  🆕 添加 stations.tenant_id 列..."
  sqlite3 "$DB_PATH" "ALTER TABLE stations ADD COLUMN tenant_id INTEGER REFERENCES tenants(id);"
  echo "  ✅ stations.tenant_id 列添加完成"
fi

# ============ 3. 给 users 添加 tenant_id 列（如果缺失） ============
echo ""
echo "📋 检查 users.tenant_id 列..."
USER_COLS=$(sqlite3 "$DB_PATH" "PRAGMA table_info(users);" 2>/dev/null || true)
USER_TENANT_ID=$(echo "$USER_COLS" | grep "tenant_id" || true)

if [ -n "$USER_TENANT_ID" ]; then
  echo "  ✅ users.tenant_id 列已存在"
else
  echo "  🆕 添加 users.tenant_id 列..."
  sqlite3 "$DB_PATH" "ALTER TABLE users ADD COLUMN tenant_id INTEGER REFERENCES tenants(id);"
  echo "  ✅ users.tenant_id 列添加完成"
fi

# ============ 4. 创建 api_keys 表（如果不存在） ============
echo ""
echo "📋 检查 api_keys 表..."
API_KEYS_EXISTS=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys';" 2>/dev/null || true)

if [ -n "$API_KEYS_EXISTS" ]; then
  echo "  ✅ api_keys 表已存在"
else
  echo "  🆕 创建 api_keys 表..."
  sqlite3 "$DB_PATH" <<'SQL'
CREATE TABLE IF NOT EXISTS api_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(100) NOT NULL,
  key_hash VARCHAR(255) NOT NULL UNIQUE,
  prefix VARCHAR(20) NOT NULL,
  tenant_id INTEGER REFERENCES tenants(id),
  user_id INTEGER REFERENCES users(id),
  permissions TEXT,
  is_active INTEGER DEFAULT 1,
  last_used_at DATETIME,
  expires_at DATETIME,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
SQL
  echo "  ✅ api_keys 表创建完成"
fi

# ============ 5. 创建 on_call 相关表 ============
echo ""
echo "📋 检查 on_call_rules 表..."
ONCALL_EXISTS=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='on_call_rules';" 2>/dev/null || true)

if [ -n "$ONCALL_EXISTS" ]; then
  echo "  ✅ on_call_rules 表已存在"
else
  echo "  🆕 创建 on_call 相关表..."
  sqlite3 "$DB_PATH" <<'SQL'
CREATE TABLE IF NOT EXISTS on_call_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(100) NOT NULL,
  team_id INTEGER NOT NULL,
  station_id INTEGER,
  rotation_type VARCHAR(20) DEFAULT 'daily',
  rotation_period INTEGER DEFAULT 1,
  start_date DATE NOT NULL,
  end_date DATE,
  is_active INTEGER DEFAULT 1,
  escalation_minutes INTEGER DEFAULT 30,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS on_call_shifts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id INTEGER NOT NULL REFERENCES on_call_rules(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  station_id INTEGER,
  shift_start DATETIME NOT NULL,
  shift_end DATETIME NOT NULL,
  status VARCHAR(20) DEFAULT 'scheduled',
  handover_notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS on_call_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  shift_id INTEGER REFERENCES on_call_shifts(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  station_id INTEGER,
  log_type VARCHAR(50) NOT NULL,
  content TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
SQL
  echo "  ✅ on_call 相关表创建完成"
fi

# ============ 6. 创建 ssl_certificates 表 ============
echo ""
echo "📋 检查 ssl_certificates 表..."
SSL_EXISTS=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='ssl_certificates';" 2>/dev/null || true)

if [ -n "$SSL_EXISTS" ]; then
  echo "  ✅ ssl_certificates 表已存在"
else
  echo "  🆕 创建 ssl_certificates 表..."
  sqlite3 "$DB_PATH" <<'SQL'
CREATE TABLE IF NOT EXISTS ssl_certificates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain VARCHAR(255) NOT NULL UNIQUE,
  issuer VARCHAR(255),
  issued_at DATETIME,
  expires_at DATETIME NOT NULL,
  auto_renew INTEGER DEFAULT 0,
  cert_path VARCHAR(500),
  key_path VARCHAR(500),
  status VARCHAR(20) DEFAULT 'active',
  last_renewed_at DATETIME,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME
);
SQL
  echo "  ✅ ssl_certificates 表创建完成"
fi

# ============ 7. 创建 digital_twin 相关表 ============
echo ""
echo "📋 检查 digital_twin_models 表..."
DT_EXISTS=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='digital_twin_models';" 2>/dev/null || true)

if [ -n "$DT_EXISTS" ]; then
  echo "  ✅ digital_twin 相关表已存在"
else
  echo "  🆕 创建 digital_twin 相关表..."
  sqlite3 "$DB_PATH" <<'SQL'
CREATE TABLE IF NOT EXISTS digital_twin_models (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(100) NOT NULL,
  model_type VARCHAR(50) NOT NULL,
  station_id INTEGER REFERENCES stations(id),
  config TEXT,
  version VARCHAR(20) DEFAULT '1.0',
  is_active INTEGER DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS digital_twin_scenes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(100) NOT NULL,
  scene_type VARCHAR(50) NOT NULL,
  station_id INTEGER REFERENCES stations(id),
  layout TEXT,
  config TEXT,
  is_active INTEGER DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS digital_twin_data_points (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scene_id INTEGER NOT NULL REFERENCES digital_twin_scenes(id),
  device_id INTEGER REFERENCES devices(id),
  point_type VARCHAR(50) NOT NULL,
  position TEXT,
  config TEXT,
  is_active INTEGER DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
SQL
  echo "  ✅ digital_twin 相关表创建完成"
fi

# ============ 8. 创建 alarm_notices 表 ============
echo ""
echo "📋 检查 alarm_notices 表..."
NOTICES_EXISTS=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='alarm_notices';" 2>/dev/null || true)

if [ -n "$NOTICES_EXISTS" ]; then
  echo "  ✅ alarm_notices 表已存在"
else
  echo "  🆕 创建 alarm_notices 表..."
  sqlite3 "$DB_PATH" <<'SQL'
CREATE TABLE IF NOT EXISTS alarm_notices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alarm_id INTEGER,
  device_id INTEGER,
  station_id INTEGER,
  content TEXT NOT NULL,
  level VARCHAR(20) NOT NULL,
  status VARCHAR(20) DEFAULT 'unread',
  alarm_type VARCHAR(50),
  fault_code VARCHAR(50),
  fault_source VARCHAR(100),
  trigger_metric VARCHAR(100),
  trigger_value FLOAT,
  handle_desc TEXT,
  handled_by INTEGER,
  handled_at DATETIME,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
SQL
  echo "  ✅ alarm_notices 表创建完成"
fi

# ============ 验证 ============
echo ""
echo "================================================"
echo "📊 数据库表清单:"
sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;" | while read -r table; do
  count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM \"$table\";" 2>/dev/null || echo "?")
  printf "  %-30s %s 行\n" "$table" "$count"
done

echo ""
echo "✅ 迁移完成！"
