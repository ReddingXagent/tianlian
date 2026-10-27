#!/usr/bin/env bash
# ======================================================================
# DEPRECATED (卡片 359c54c1): 本脚本为 V3 SQLite 时代遗物，对生产 PostgreSQL
# 架构已失效。生产 PG 备份/恢复请使用 scripts/backup-pg.sh（服务器端
# /opt/tianlian-cloud/scripts/backup-pg.sh，systemd timer tianlian-pg-backup）。
# ======================================================================
# ═══════════════════════════════════════════════════════════════
# 天链 V3 — 备份状态报告
# 功能:
#   1. 检查最近备份状态
#   2. 上次成功备份时间
#   3. 备份文件大小
#   4. 备份完整性
# 用法:
#   ./backup-report.sh            标准报告
#   ./backup-report.sh --json     JSON 格式输出
#   ./backup-report.sh --nas      包含 NAS 状态
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"
BACKUP_ROOT="${PROJECT_DIR}/backups"
DB_PATH="${BACKEND_DIR}/tianlian_v3.db"
LOG_FILE="${BACKUP_ROOT}/backup.log"

# NAS 配置
NAS_HOST="192.168.1.100"
NAS_PORT="22"
NAS_USER="nas-admin"
NAS_BACKUP_DIR="/volume1/homes/nas-admin/backups/tianlian-v3"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

# ─── 颜色 ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'
GRAY='\033[0;90m'

JSON_OUT=false
INCLUDE_NAS=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --json) JSON_OUT=true; shift ;;
        --nas) INCLUDE_NAS=true; shift ;;
        --help|-h)
            echo "用法: $0 [--json] [--nas]"
            exit 0
            ;;
        *) shift ;;
    esac
done

# ═══ 收集数据 ═══
NOW=$(date +%s)

# 本地备份
LOCAL_BACKUPS=()
LOCAL_SIZES=()
LOCAL_TIMES=()
LOCAL_LATEST=""
LOCAL_LATEST_SIZE=""
LOCAL_LATEST_TIME=""
LOCAL_LATEST_AGE=""
LOCAL_COUNT=0
LOCAL_TOTAL_KB=0

if ls "${BACKUP_ROOT}"/tianlian-v3-backup-*.tar.gz &>/dev/null; then
    for f in $(ls -1t "${BACKUP_ROOT}"/tianlian-v3-backup-*.tar.gz 2>/dev/null); do
        size_bytes=$(stat -f%z "$f" 2>/dev/null || echo 0)
        size_kb=$((size_bytes / 1024))
        LOCAL_TOTAL_KB=$((LOCAL_TOTAL_KB + size_kb))
        LOCAL_COUNT=$((LOCAL_COUNT + 1))

        if [ -z "$LOCAL_LATEST" ]; then
            LOCAL_LATEST="$f"
            LOCAL_LATEST_SIZE="$size_kb"
            mtime=$(stat -f%m "$f" 2>/dev/null || echo 0)
            LOCAL_LATEST_TIME=$(date -r "$mtime" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "unknown")
            age_sec=$((NOW - mtime))
            if [ $age_sec -lt 60 ]; then
                LOCAL_LATEST_AGE="${age_sec}秒前"
            elif [ $age_sec -lt 3600 ]; then
                LOCAL_LATEST_AGE="$((age_sec / 60))分钟前"
            elif [ $age_sec -lt 86400 ]; then
                LOCAL_LATEST_AGE="$((age_sec / 3600))小时前"
            else
                LOCAL_LATEST_AGE="$((age_sec / 86400))天前"
            fi
        fi
    done
fi

# 备份完整性
LOCAL_INTEGRITY="unknown"
if [ -f "$LOCAL_LATEST" ]; then
    if tar -tzf "$LOCAL_LATEST" > /dev/null 2>&1; then
        LOCAL_INTEGRITY="pass"
    else
        LOCAL_INTEGRITY="fail"
    fi
fi

# 数据库状态
DB_EXISTS=false
DB_SIZE=""
DB_TABLES=0
DB_INTEGRITY="unknown"
if [ -f "$DB_PATH" ]; then
    DB_EXISTS=true
    DB_SIZE=$(du -h "$DB_PATH" | cut -f1 2>/dev/null || echo "unknown")
    DB_TABLES=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo 0)
    if sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
        DB_INTEGRITY="pass"
    else
        DB_INTEGRITY="fail"
    fi
fi

# 备份日志最后一条
LAST_LOG_LINE=""
if [ -f "$LOG_FILE" ]; then
    LAST_LOG_LINE=$(tail -1 "$LOG_FILE" 2>/dev/null || echo "")
fi

# NAS 状态
NAS_REACHABLE=false
NAS_LATEST=""
NAS_LATEST_SIZE=""
NAS_COUNT=0
if $INCLUDE_NAS; then
    if sshpass -p '@Tianlian6688' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" "echo ok" 2>/dev/null; then
        NAS_REACHABLE=true
        NAS_LATEST=$(sshpass -p '@Tianlian6688' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" \
            "ls -1t ${NAS_BACKUP_DIR}/tianlian-v3-backup-*.tar.gz 2>/dev/null | head -1" 2>/dev/null || echo "")
        if [ -n "$NAS_LATEST" ]; then
            NAS_LATEST_SIZE=$(sshpass -p '@Tianlian6688' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" \
                "du -h ${NAS_LATEST} | cut -f1" 2>/dev/null || echo "unknown")
            NAS_COUNT=$(sshpass -p '@Tianlian6688' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" \
                "ls -1 ${NAS_BACKUP_DIR}/tianlian-v3-backup-*.tar.gz 2>/dev/null | wc -l" | tr -d ' ')
        fi
    fi
fi

# ═══ 输出 ═══
if $JSON_OUT; then
    cat << EOFJSON
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "database": {
        "exists": $DB_EXISTS,
        "size": "$DB_SIZE",
        "tables": $DB_TABLES,
        "integrity": "$DB_INTEGRITY"
    },
    "backups": {
        "local": {
            "count": $LOCAL_COUNT,
            "total_kb": $LOCAL_TOTAL_KB,
            "latest": "$(basename "$LOCAL_LATEST" 2>/dev/null || echo 'none')",
            "latest_size_kb": ${LOCAL_LATEST_SIZE:-0},
            "latest_time": "$LOCAL_LATEST_TIME",
            "latest_age": "$LOCAL_LATEST_AGE",
            "integrity": "$LOCAL_INTEGRITY"
        },
        "nas": {
            "reachable": $NAS_REACHABLE,
            "count": ${NAS_COUNT:-0},
            "latest": "$(basename "$NAS_LATEST" 2>/dev/null || echo 'none')",
            "latest_size": "$NAS_LATEST_SIZE"
        }
    },
    "last_log": "$LAST_LOG_LINE"
}
EOFJSON
    exit 0
fi

# ═══ 格式化报告 ═══
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║  天链 V3 — 备份状态报告                            ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GRAY}报告时间: $(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
echo ""

# ── 数据库状态 ──
echo -e "${BOLD}📊 数据库状态${NC}"
echo "──────────────────────────────────────────"
if $DB_EXISTS; then
    echo -e "  文件:       ${DB_PATH}"
    echo -e "  大小:       ${DB_SIZE}"
    echo -e "  表数量:     ${DB_TABLES}"
    if [ "$DB_INTEGRITY" = "pass" ]; then
        echo -e "  完整性:     ${GREEN}✅ 正常${NC}"
    else
        echo -e "  完整性:     ${RED}❌ 异常${NC}"
    fi
else
    echo -e "  ${RED}数据库文件不存在${NC}"
fi
echo ""

# ── 备份状态 ──
echo -e "${BOLD}📦 本地备份${NC}"
echo "──────────────────────────────────────────"

if [ "$LOCAL_COUNT" -eq 0 ]; then
    echo -e "  ${YELLOW}⚠️  无本地备份${NC}"
else
    echo -e "  备份总数:   ${LOCAL_COUNT}"
    echo -e "  总大小:     $((LOCAL_TOTAL_KB / 1024)) MB"
    echo -e "  备份目录:   ${BACKUP_ROOT}"
    echo ""
    echo -e "  最新备份:   $(basename "$LOCAL_LATEST")"
    echo -e "  大小:       ${LOCAL_LATEST_SIZE} KB"
    echo -e "  时间:       ${LOCAL_LATEST_TIME} (${LOCAL_LATEST_AGE})"

    if [ "$LOCAL_INTEGRITY" = "pass" ]; then
        echo -e "  完整性:     ${GREEN}✅ 正常${NC}"
    elif [ "$LOCAL_INTEGRITY" = "fail" ]; then
        echo -e "  完整性:     ${RED}❌ 损坏${NC}"
    else
        echo -e "  完整性:     ${GRAY}未检查${NC}"
    fi

    # 备份健康度
    mtime=$(stat -f%m "$LOCAL_LATEST" 2>/dev/null || echo 0)
    age_hours=$(( (NOW - mtime) / 3600 ))
    echo -n "  健康状态:   "
    if [ $age_hours -lt 24 ]; then
        echo -e "${GREEN}🟢 健康 (24小时内)${NC}"
    elif [ $age_hours -lt 72 ]; then
        echo -e "${YELLOW}🟡 需要关注 (${age_hours}小时前)${NC}"
    else
        echo -e "${RED}🔴 过期 (${age_hours}小时前)${NC}"
    fi
fi
echo ""

# ── NAS 状态 ──
if $INCLUDE_NAS; then
    echo -e "${BOLD}🌐 NAS 备份 (${NAS_HOST})${NC}"
    echo "──────────────────────────────────────────"

    if $NAS_REACHABLE; then
        echo -e "  连接状态:   ${GREEN}✅ 可达${NC}"
        echo -e "  备份总数:   ${NAS_COUNT:-0}"
        if [ -n "$NAS_LATEST" ]; then
            echo -e "  最新备份:   $(basename "$NAS_LATEST")"
            echo -e "  大小:       ${NAS_LATEST_SIZE}"
        else
            echo -e "  ${YELLOW}NAS 无备份${NC}"
        fi
    else
        echo -e "  连接状态:   ${RED}❌ 不可达${NC}"
    fi
    echo ""
fi

# ── 最近活动 ──
echo -e "${BOLD}📝 最近备份日志 (最后 5 条)${NC}"
echo "──────────────────────────────────────────"
if [ -f "$LOG_FILE" ]; then
    tail -5 "$LOG_FILE" 2>/dev/null | while IFS= read -r line; do
        echo "  ${GRAY}${line}${NC}"
    done
else
    echo -e "  ${GRAY}无日志文件${NC}"
fi
echo ""

# ── Crontab 提示 ──
echo -e "${BOLD}⏰ 定时备份配置建议${NC}"
echo "──────────────────────────────────────────"
echo -e "  添加到 crontab:"
echo -e "  ${CYAN}# 每天凌晨 3 点自动备份${NC}"
echo -e "  ${CYAN}0 3 * * * ${SCRIPT_DIR}/auto-backup.sh >> ${BACKUP_ROOT}/cron.log 2>&1${NC}"
echo ""
echo -e "  当前 crontab 中的备份任务:"
crontab -l 2>/dev/null | grep -i "auto-backup\|tianlian" || echo -e "  ${GRAY}(未配置)${NC}"
echo ""

echo -e "${GREEN}${BOLD}✅ 报告完成${NC}"
echo ""