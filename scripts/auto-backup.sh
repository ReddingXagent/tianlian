#!/usr/bin/env bash
# ======================================================================
# DEPRECATED (卡片 359c54c1): 本脚本为 V3 SQLite 时代遗物，对生产 PostgreSQL
# 架构已失效。生产 PG 备份/恢复请使用 scripts/backup-pg.sh（服务器端
# /opt/tianlian-cloud/scripts/backup-pg.sh，systemd timer tianlian-pg-backup）。
# ======================================================================
# ═══════════════════════════════════════════════════════════════
# 天链 V3 — 自动化备份脚本
# 功能:
#   1. 数据库备份 (sqlite3 .dump)
#   2. 配置文件备份 (.env, openclaw.json 关键配置)
#   3. 上传到 NAS (192.168.1.100)
#   4. 保留最近 7 天备份
#   5. 备份完整性验证
# 用法:
#   ./auto-backup.sh           完整备份
#   ./auto-backup.sh --db-only 仅备份数据库
#   ./auto-backup.sh --dry-run 模拟运行
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ─── 环境变量检查 ───
NAS_PASS="${NAS_PASSWORD:-}"
if [ -z "$NAS_PASS" ]; then
    echo "❌ 错误: 环境变量 NAS_PASSWORD 未设置" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"

# ─── 配置 ───
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT="${PROJECT_DIR}/backups"
BACKUP_NAME="tianlian-v3-backup-${TIMESTAMP}"
BACKUP_DIR="${BACKUP_ROOT}/${BACKUP_NAME}"
BACKUP_ARCHIVE="${BACKUP_ROOT}/${BACKUP_NAME}.tar.gz"
RETENTION_DAYS=7
LOG_FILE="${BACKUP_ROOT}/backup.log"

# NAS 配置
NAS_HOST="192.168.1.100"
NAS_PORT="22"
NAS_USER="nas-admin"
NAS_BACKUP_DIR="/volume1/homes/nas-admin/backups/tianlian-v3"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

# 数据库文件
DB_PATH="${BACKEND_DIR}/tianlian_v3.db"

# 配置文件列表
CONFIG_FILES=(
    "${BACKEND_DIR}/.env"
    "${PROJECT_DIR}/.env"
    "${PROJECT_DIR}/scripts/sync-config.json"
)

# ─── 颜色 ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# ─── 标志 ───
DB_ONLY=false
DRY_RUN=false

# ─── 参数解析 ───
while [[ $# -gt 0 ]]; do
    case "$1" in
        --db-only) DB_ONLY=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help|-h)
            echo "用法: $0 [--db-only] [--dry-run]"
            exit 0
            ;;
        *) echo -e "${RED}未知参数: $1${NC}"; exit 1 ;;
    esac
done

# ─── 日志函数 ───
log() {
    local level="$1"; shift
    local color=""
    case "$level" in
        INFO)  color="$GREEN" ;;
        WARN)  color="$YELLOW" ;;
        ERROR) color="$RED" ;;
    esac
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] $*"
    echo -e "${color}${msg}${NC}"
    echo "$msg" >> "$LOG_FILE"
}

# ─── 清理函数 ───
cleanup() {
    if [ -d "$BACKUP_DIR" ] && [ "${KEEP_DIR:-0}" != "1" ]; then
        rm -rf "$BACKUP_DIR"
    fi
}
trap cleanup EXIT

# ─── 创建目录 ───
mkdir -p "$BACKUP_ROOT"
mkdir -p "$BACKUP_DIR"

# ─── 开始备份 ───
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║  天链 V3 备份 — ${TIMESTAMP}                     ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

log INFO "开始备份任务 backup_id=${BACKUP_NAME}"

# ═══ Step 1: 备份数据库 ═══
log INFO "Step 1/5: 备份数据库..."

if [ ! -f "$DB_PATH" ]; then
    log WARN "数据库文件不存在: ${DB_PATH}，跳过数据库备份"
else
    DB_SIZE=$(du -h "$DB_PATH" | cut -f1)
    log INFO "数据库文件大小: ${DB_SIZE}"

    # 完整性检查
    if sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
        log INFO "数据库完整性检查通过"
    else
        log ERROR "数据库完整性检查失败！"
        sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>&1 | tee -a "$LOG_FILE"
    fi

    # sqlite3 dump
    if $DRY_RUN; then
        log INFO "[DRY-RUN] 将执行: sqlite3 ${DB_PATH} .dump > ${BACKUP_DIR}/database.sql"
    else
        sqlite3 "$DB_PATH" ".dump" > "${BACKUP_DIR}/database.sql" 2>>"$LOG_FILE"
        DUMP_SIZE=$(du -h "${BACKUP_DIR}/database.sql" | cut -f1)
        log INFO "数据库导出完成 size=${DUMP_SIZE}"
    fi
fi

# ═══ Step 2: 备份配置文件 ═══
if ! $DB_ONLY; then
    log INFO "Step 2/5: 备份配置文件..."

    CONFIG_BACKUP_DIR="${BACKUP_DIR}/config"
    mkdir -p "$CONFIG_BACKUP_DIR"

    # 复制 .env
    for cfg in "${CONFIG_FILES[@]}"; do
        if [ -f "$cfg" ]; then
            if $DRY_RUN; then
                log INFO "[DRY-RUN] 将复制: ${cfg} → ${CONFIG_BACKUP_DIR}/"
            else
                cp "$cfg" "$CONFIG_BACKUP_DIR/$(basename "$cfg")"
                log INFO "已备份: $(basename "$cfg")"
            fi
        else
            log WARN "配置文件不存在: ${cfg}"
        fi
    done

    # 项目关键信息
    if ! $DRY_RUN; then
        cat > "${BACKUP_DIR}/backup-meta.json" << EOFMETA
{
    "backup_id": "${BACKUP_NAME}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "project": "tianlian-v3",
    "git_commit": "$(cd "$PROJECT_DIR" && git rev-parse HEAD 2>/dev/null || echo 'unknown')",
    "git_branch": "$(cd "$PROJECT_DIR" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')",
    "db_size": "$(du -h "$DB_PATH" 2>/dev/null | cut -f1 || echo 'N/A')",
    "backup_size": "N/A"
}
EOFMETA
    fi
fi

# ═══ Step 3: 打包压缩 ═══
log INFO "Step 3/5: 打包压缩..."

if $DRY_RUN; then
    log INFO "[DRY-RUN] 将打包: ${BACKUP_DIR} → ${BACKUP_ARCHIVE}"
else
    cd "$BACKUP_ROOT"
    tar -czf "$BACKUP_ARCHIVE" "$BACKUP_NAME" 2>>"$LOG_FILE"

    if [ -f "$BACKUP_ARCHIVE" ]; then
        ARCHIVE_SIZE=$(du -h "$BACKUP_ARCHIVE" | cut -f1)
        log INFO "打包完成 size=${ARCHIVE_SIZE}"

        # 更新 meta
        python3 -c "
import json
with open('${BACKUP_DIR}/backup-meta.json') as f:
    meta = json.load(f)
meta['backup_size'] = '${ARCHIVE_SIZE}'
with open('${BACKUP_DIR}/backup-meta.json', 'w') as f:
    json.dump(meta, f, indent=2)
" 2>/dev/null || true

        # 更新最新链接
        ln -sf "$BACKUP_ARCHIVE" "${BACKUP_ROOT}/tianlian-v3-latest.tar.gz"
    else
        log ERROR "打包失败！"
        exit 1
    fi
fi

# ═══ Step 4: 上传到 NAS ═══
log INFO "Step 4/5: 上传到 NAS (${NAS_HOST})..."

if $DRY_RUN; then
    log INFO "[DRY-RUN] 将上传: ${BACKUP_ARCHIVE} → ${NAS_USER}@${NAS_HOST}:${NAS_BACKUP_DIR}/"
else
    # 检查 NAS 是否可达
    if sshpass -p '$NAS_PASS' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" "echo ok" 2>/dev/null; then
        log INFO "NAS 连接成功"

        # 创建远程目录
        sshpass -p '$NAS_PASS' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" \
            "mkdir -p ${NAS_BACKUP_DIR}" 2>>"$LOG_FILE"

        # 上传
        if sshpass -p '$NAS_PASS' scp $SSH_OPTS -P "$NAS_PORT" \
            "$BACKUP_ARCHIVE" "${NAS_USER}@${NAS_HOST}:${NAS_BACKUP_DIR}/" 2>>"$LOG_FILE"; then
            log INFO "NAS 上传完成"

            # 上传 latest 链接
            sshpass -p '$NAS_PASS' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" \
                "cd ${NAS_BACKUP_DIR} && ln -sf $(basename "$BACKUP_ARCHIVE") tianlian-v3-latest.tar.gz" 2>/dev/null || true
        else
            log ERROR "NAS 上传失败！"
        fi
    else
        log WARN "NAS 不可达，跳过上传"
    fi
fi

# ═══ Step 5: 清理旧备份 ═══
log INFO "Step 5/5: 清理 ${RETENTION_DAYS} 天前的旧备份..."

if $DRY_RUN; then
    log INFO "[DRY-RUN] 将删除 ${RETENTION_DAYS} 天前的本地备份"
else
    # 本地清理
    OLD_LOCAL=$(find "$BACKUP_ROOT" -name "tianlian-v3-backup-*.tar.gz" -mtime +$RETENTION_DAYS 2>/dev/null | wc -l | tr -d ' ')
    if [ "$OLD_LOCAL" -gt 0 ]; then
        find "$BACKUP_ROOT" -name "tianlian-v3-backup-*.tar.gz" -mtime +$RETENTION_DAYS -delete
        log INFO "本地清理完成 deleted=${OLD_LOCAL}"
    else
        log INFO "本地无需清理"
    fi

    # 远程清理
    if sshpass -p '$NAS_PASS' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" "echo ok" 2>/dev/null; then
        OLD_REMOTE=$(sshpass -p '$NAS_PASS' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" \
            "find ${NAS_BACKUP_DIR} -name 'tianlian-v3-backup-*.tar.gz' -mtime +${RETENTION_DAYS} 2>/dev/null | wc -l" | tr -d ' ')
        if [ "${OLD_REMOTE:-0}" -gt 0 ]; then
            sshpass -p '$NAS_PASS' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" \
                "find ${NAS_BACKUP_DIR} -name 'tianlian-v3-backup-*.tar.gz' -mtime +${RETENTION_DAYS} -delete" 2>>"$LOG_FILE"
            log INFO "NAS 清理完成 deleted=${OLD_REMOTE}"
        else
            log INFO "NAS 无需清理"
        fi
    fi
fi

# ═══ 备份完整性验证 ═══
log INFO "验证备份完整性..."

if ! $DRY_RUN && [ -f "$BACKUP_ARCHIVE" ]; then
    if tar -tzf "$BACKUP_ARCHIVE" > /dev/null 2>&1; then
        FILE_COUNT=$(tar -tzf "$BACKUP_ARCHIVE" | wc -l | tr -d ' ')
        log INFO "备份验证通过 files=${FILE_COUNT}"
    else
        log ERROR "备份文件损坏！"
        exit 1
    fi
fi

# ═══ 统计 ═══
if ! $DRY_RUN; then
    TOTAL_BACKUPS=$(ls -1 "${BACKUP_ROOT}"/tianlian-v3-backup-*.tar.gz 2>/dev/null | wc -l | tr -d ' ')
    TOTAL_SIZE=$(du -sh "$BACKUP_ROOT" 2>/dev/null | cut -f1)
    log INFO "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log INFO "备份任务完成"
    log INFO "  本地备份数: ${TOTAL_BACKUPS}"
    log INFO "  本地总大小: ${TOTAL_SIZE}"
    log INFO "  本次备份:   ${BACKUP_NAME}.tar.gz"
    log INFO "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

echo ""
echo -e "${GREEN}${BOLD}✅ 备份完成${NC}"
echo ""

# 保留临时目录（归档时已打包）
KEEP_DIR=0

exit 0