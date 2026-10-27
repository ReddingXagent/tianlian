#!/bin/bash
# Phase10 数字孪生可视化 - 数据库迁移脚本
# 创建数字孪生相关表结构

set -e

echo "🚀 开始 Phase10 数字孪生可视化数据库迁移..."

# 定义SQL文件路径
SQL_FILE="/tmp/phase10_digital_twin_migration.sql"

cat > "$SQL_FILE" << 'EOF'
-- Phase10 数字孪生可视化数据库迁移
-- 创建数字孪生相关表结构

-- 1. 创建数字孪生设备配置表
CREATE TABLE IF NOT EXISTS digital_twin_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL UNIQUE,
    
    -- 3D模型类型
    model_type TEXT NOT NULL CHECK (
        model_type IN (
            'solar_inverter',     -- 光伏逆变器
            'battery_inverter',   -- 储能逆变器
            'pcs',                -- 储能变流器
            'battery_rack',       -- 电池柜
            'charger_dc',         -- 直流充电桩
            'charger_ac',         -- 交流充电桩
            'gateway',            -- 网关
            'meter',              -- 电表
            'transformer',        -- 变压器
            'panel'               -- 配电盘
        )
    ),
    
    -- 3D变换参数
    scale_x REAL DEFAULT 1.0,
    scale_y REAL DEFAULT 1.0,
    scale_z REAL DEFAULT 1.0,
    position_x REAL DEFAULT 0.0,
    position_y REAL DEFAULT 0.0,
    position_z REAL DEFAULT 0.0,
    rotation_x REAL DEFAULT 0.0,
    rotation_y REAL DEFAULT 0.0,
    rotation_z REAL DEFAULT 0.0,
    
    -- 材质颜色
    color_primary TEXT DEFAULT '#1890ff',
    color_secondary TEXT DEFAULT '#52c41a',
    color_accent TEXT DEFAULT '#faad14',
    
    -- 动画配置 (JSON)
    animations TEXT DEFAULT '{}',
    
    -- 状态映射配置 (JSON)
    status_mapping TEXT DEFAULT '{}',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 外键约束
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    
    -- 索引
    UNIQUE(device_id)
);

-- 2. 创建数字孪生场景配置表
CREATE TABLE IF NOT EXISTS digital_twin_scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    
    -- 场景配置 (JSON)
    scene_config TEXT NOT NULL DEFAULT '{
        "camera": {
            "position": [0, 10, 15],
            "fov": 50,
            "near": 0.1,
            "far": 1000
        },
        "lights": [
            {
                "type": "ambient",
                "color": "#ffffff",
                "intensity": 0.5
            },
            {
                "type": "directional",
                "position": [5, 10, 5],
                "color": "#ffffff",
                "intensity": 0.8
            }
        ],
        "grid": {
            "enabled": true,
            "size": 50,
            "divisions": 50,
            "colorCenterLine": "#666666",
            "colorGrid": "#444444"
        },
        "axes": {
            "enabled": true,
            "size": 5
        },
        "ground": {
            "enabled": true,
            "color": "#333333",
            "opacity": 0.8
        }
    }',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 外键约束
    FOREIGN KEY (station_id) REFERENCES stations(id) ON DELETE CASCADE,
    
    -- 索引
    UNIQUE(station_id, name)
);

-- 3. 创建触发器：更新updated_at时间戳
CREATE TRIGGER IF NOT EXISTS update_digital_twin_devices_updated_at
AFTER UPDATE ON digital_twin_devices
FOR EACH ROW
BEGIN
    UPDATE digital_twin_devices SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_digital_twin_scenes_updated_at
AFTER UPDATE ON digital_twin_scenes
FOR EACH ROW
BEGIN
    UPDATE digital_twin_scenes SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- 4. 为现有设备创建默认的数字孪生配置
-- 光伏逆变器
INSERT OR IGNORE INTO digital_twin_devices (device_id, model_type)
SELECT id, 'solar_inverter'
FROM devices 
WHERE type = 'pv_inverter';

-- 储能逆变器/储能变流器
INSERT OR IGNORE INTO digital_twin_devices (device_id, model_type)
SELECT id, 'battery_inverter'
FROM devices 
WHERE type IN ('battery_inverter', 'pcs');

-- 电池柜
INSERT OR IGNORE INTO digital_twin_devices (device_id, model_type)
SELECT id, 'battery_rack'
FROM devices 
WHERE type = 'battery';

-- 直流充电桩
INSERT OR IGNORE INTO digital_twin_devices (device_id, model_type)
SELECT id, 'charger_dc'
FROM devices 
WHERE type = 'charger_dc';

-- 交流充电桩
INSERT OR IGNORE INTO digital_twin_devices (device_id, model_type)
SELECT id, 'charger_ac'
FROM devices 
WHERE type = 'charger_ac';

-- 网关
INSERT OR IGNORE INTO digital_twin_devices (device_id, model_type)
SELECT id, 'gateway'
FROM devices 
WHERE type = 'gateway';

-- 电表
INSERT OR IGNORE INTO digital_twin_devices (device_id, model_type)
SELECT id, 'meter'
FROM devices 
WHERE type = 'meter';

-- 5. 为每个站点创建默认场景配置
INSERT OR IGNORE INTO digital_twin_scenes (station_id, name)
SELECT id, 'default'
FROM stations;

EOF

# 执行SQL迁移
echo "📝 执行SQL迁移..."
DB_PATH="$HOME/.openclaw/workspace/projects/tianlian-v3/backend/tianlian_v3.db"
sqlite3 "$DB_PATH" < "$SQL_FILE"

# 检查迁移结果
echo "🔍 检查迁移结果..."
sqlite3 "$DB_PATH" << 'SQL_CHECK'
.tables
.schema digital_twin_devices
.schema digital_twin_scenes
SELECT COUNT(*) as device_count FROM digital_twin_devices;
SELECT COUNT(*) as scene_count FROM digital_twin_scenes;
SQL_CHECK

echo "✅ Phase10 数字孪生数据库迁移完成！"
echo ""
echo "📊 迁移统计："
echo "   - digital_twin_devices: $(sqlite3 "$DB_PATH" 'SELECT COUNT(*) FROM digital_twin_devices;') 条记录"
echo "   - digital_twin_scenes: $(sqlite3 "$DB_PATH" 'SELECT COUNT(*) FROM digital_twin_scenes;') 条记录"

# 清理临时文件
rm -f "$SQL_FILE"