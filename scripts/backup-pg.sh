#!/bin/bash
# 天链生产 PostgreSQL 备份脚本（卡片 359c54c1-8fdc-4cb7-84bd-6273eca5c5c6）
# 运行位置：生产服务器（systemd oneshot: tianlian-pg-backup.service）
# 连接信息从 /opt/tianlian-cloud/backend/.env 的 DATABASE_URL 解析，
# 绝不硬编码连接串/密码，绝不写日志。
# 产物：/var/backups/tianlian-pg/tianlian_YYYYmmdd_HHMMSS.dump（pg_dump -Fc 自带压缩）
# 校验：sha256 追加至 /var/log/tianlian/backup.log；保留 14 天。

set -euo pipefail

ENV_FILE="/opt/tianlian-cloud/backend/.env"
BACKUP_DIR="/var/backups/tianlian-pg"
LOG_FILE="/var/log/tianlian/backup.log"
RETENTION_DAYS=14
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/tianlian_${STAMP}.dump"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE" >&2
}

# --- 解析 DATABASE_URL（postgresql://user:pass@host:port/dbname?params） ---
if [[ ! -r "$ENV_FILE" ]]; then
    log "FATAL: env file not readable: $ENV_FILE"
    exit 1
fi
DB_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\"'"'"'')"
if [[ -z "$DB_URL" ]]; then
    log "FATAL: DATABASE_URL not found in $ENV_FILE"
    exit 1
fi

# 用 pg_dump 原生 URI 支持，密码经 PGPASSWORD 传递，避免落入 ps/cmdline
PG_USER="$(echo "$DB_URL" | sed -E 's#^[a-z+]+://([^:/@]+)(:([^@/]*))?@.*#\1#')"
PG_PASS="$(echo "$DB_URL" | sed -E 's#^[a-z+]+://([^:/@]+)(:([^@/]*))?@.*#\3#')"
PG_HOST="$(echo "$DB_URL" | sed -E 's#^[a-z+]+://[^@]*@([^:/]+).*#\1#')"
PG_PORT="$(echo "$DB_URL" | sed -E 's#^[a-z+]+://[^@]*@[^:/]+:([0-9]+).*#\1#')"
PG_DBNAME="$(echo "$DB_URL" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"
PG_PORT="${PG_PORT:-5432}"

if [[ -z "$PG_USER" || -z "$PG_DBNAME" ]]; then
    log "FATAL: failed to parse DATABASE_URL"
    exit 1
fi

mkdir -p "$BACKUP_DIR" "$(dirname "$LOG_FILE")"
export PGPASSWORD="$PG_PASS"

log "START backup db=$PG_DBNAME host=$PG_HOST port=$PG_PORT"

# --- 备份（-Fc 自定义压缩格式，支持 pg_restore 并行/选择性恢复） ---
if ! pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DBNAME" -Fc -f "$BACKUP_FILE"; then
    log "FATAL: pg_dump failed"
    rm -f "$BACKUP_FILE"
    unset PGPASSWORD
    exit 1
fi
unset PGPASSWORD

if [[ ! -s "$BACKUP_FILE" ]]; then
    log "FATAL: backup file empty: $BACKUP_FILE"
    exit 1
fi

# --- 完整性校验：sha256 + pg_restore --list 可读 ---
SHA="$(sha256sum "$BACKUP_FILE" | awk '{print $1}')"
if ! pg_restore --list "$BACKUP_FILE" > /dev/null 2>&1; then
    log "FATAL: pg_restore --list failed, backup corrupt: $BACKUP_FILE"
    exit 1
fi
SIZE="$(du -h "$BACKUP_FILE" | cut -f1)"
log "OK file=$BACKUP_FILE size=$SIZE sha256=$SHA"

# --- 保留策略：清理 14 天前旧备份 ---
DELETED="$(find "$BACKUP_DIR" -name 'tianlian_*.dump' -mtime +$((RETENTION_DAYS - 1)) -print -delete | wc -l)"
log "CLEANUP removed=$DELETED retention_days=$RETENTION_DAYS"

log "DONE"
exit 0
