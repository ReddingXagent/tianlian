#!/bin/bash
# ======================================================================
# DEPRECATED (卡片 359c54c1): 本脚本为 V3 SQLite 时代遗物，对生产 PostgreSQL
# 架构已失效。生产 PG 备份/恢复请使用 scripts/backup-pg.sh（服务器端
# /opt/tianlian-cloud/scripts/backup-pg.sh，systemd timer tianlian-pg-backup）。
# ======================================================================
# 天链 V3 数据库备份脚本 - 完整版
# 功能：自动备份、压缩、清理旧备份、验证完整性

set -e

# 配置
DB_PATH="/opt/tianlian-v3/backend/tianlian_v3.db"
BACKUP_DIR="/opt/tianlian-v3/backups"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/tianlian_$TIMESTAMP.db.gz"
LOG_FILE="/var/log/tianlian/backup.log"

# 创建目录
mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname $LOG_FILE)"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 1. 检查数据库是否存在
if [ ! -f "$DB_PATH" ]; then
    log "❌ 数据库文件不存在: $DB_PATH"
    exit 1
fi

DB_SIZE=$(du -h "$DB_PATH" | cut -f1)
log "数据库大小: $DB_SIZE"

# 2. 验证数据库完整性
log "验证数据库完整性..."
sqlite3 "$DB_PATH" "PRAGMA integrity_check;" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    log "❌ 数据库完整性检查失败，备份中止"
    exit 1
fi
log "✅ 数据库完整性检查通过"

# 3. 创建备份
log "创建备份: $BACKUP_FILE"
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/tianlian_$TIMESTAMP.db'"
gzip "$BACKUP_DIR/tianlian_$TIMESTAMP.db"

if [ -f "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "✅ 备份完成 (大小: $BACKUP_SIZE)"
else
    log "❌ 备份文件未生成"
    exit 1
fi

# 4. 验证备份文件
log "验证备份文件完整性..."
gunzip -c "$BACKUP_FILE" | sqlite3 ":memory:" "PRAGMA integrity_check;" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    log "❌ 备份文件损坏"
    rm "$BACKUP_FILE"
    exit 1
fi
log "✅ 备份文件完整性验证通过"

# 5. 清理旧备份
log "清理 $RETENTION_DAYS 天前的旧备份..."
OLD_COUNT=$(find "$BACKUP_DIR" -name "tianlian_*.db.gz" -mtime +$RETENTION_DAYS | wc -l)
if [ "$OLD_COUNT" -gt 0 ]; then
    find "$BACKUP_DIR" -name "tianlian_*.db.gz" -mtime +$RETENTION_DAYS -delete
    log "✅ 已清理 $OLD_COUNT 个旧备份"
else
    log "无需清理旧备份"
fi

# 6. 统计当前备份
CURRENT_COUNT=$(ls -1 "$BACKUP_DIR"/tianlian_*.db.gz 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "当前备份总数: $CURRENT_COUNT (总大小: $TOTAL_SIZE)"

# 7. 创建最新备份符号链接（方便恢复）
ln -sf "$BACKUP_FILE" "$BACKUP_DIR/tianlian_latest.db.gz"
log "✅ 已更新最新备份链接"

# 8. 可选：同步到远程备份（如群辉NAS）
# rsync -avz "$BACKUP_DIR/" user@nas:/backup/tianlian/

log "========================================="
log "备份任务完成"
log "========================================="

exit 0