#!/usr/bin/env bash
# ======================================================================
# DEPRECATED (卡片 359c54c1): 本脚本为 V3 SQLite 时代遗物，对生产 PostgreSQL
# 架构已失效。生产 PG 备份/恢复请使用 scripts/backup-pg.sh（服务器端
# /opt/tianlian-cloud/scripts/backup-pg.sh，systemd timer tianlian-pg-backup）。
# ======================================================================
# ═══════════════════════════════════════════════════════════════
# 天链 V3 — 从备份恢复
# 功能:
#   1. 列出可用备份
#   2. 恢复前自动备份当前状态（安全网）
#   3. 从指定备份恢复数据库
#   4. 验证恢复结果
# 用法:
#   ./restore-from-backup.sh                 交互式选择备份
#   ./restore-from-backup.sh --list          列出所有可用备份
#   ./restore-from-backup.sh --file FILE     从指定文件恢复
#   ./restore-from-backup.sh --latest        从最新备份恢复
#   ./restore-from-backup.sh --nas-latest    从 NAS 最新备份恢复
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
BACKUP_ROOT="${PROJECT_DIR}/backups"
DB_PATH="${BACKEND_DIR}/tianlian_v3.db"

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

MODE="interactive"
TARGET_FILE=""

# ─── 参数解析 ───
while [[ $# -gt 0 ]]; do
    case "$1" in
        --list|-l)
            MODE="list"
            shift
            ;;
        --file|-f)
            MODE="file"
            TARGET_FILE="$2"
            shift 2
            ;;
        --latest)
            MODE="latest"
            shift
            ;;
        --nas-latest)
            MODE="nas-latest"
            shift
            ;;
        --help|-h)
            echo "用法: $0 [--list|--file FILE|--latest|--nas-latest]"
            exit 0
            ;;
        *)
            echo -e "${RED}未知参数: $1${NC}"
            exit 1
            ;;
    esac
done

# ─── 日志 ───
log() {
    echo -e "[$(date '+%H:%M:%S')] $1"
}

# ═══ 列出备份 ═══
list_backups() {
    echo ""
    echo -e "${BOLD}本地备份:${NC}"
    echo "──────────────────────────────────────────"
    local idx=1
    local backups=()

    if ls "${BACKUP_ROOT}"/tianlian-v3-backup-*.tar.gz &>/dev/null; then
        for f in $(ls -1t "${BACKUP_ROOT}"/tianlian-v3-backup-*.tar.gz 2>/dev/null); do
            local size=$(du -h "$f" | cut -f1)
            local date_str=$(echo "$f" | grep -oE '[0-9]{8}_[0-9]{6}')
            printf "  [%2d] %-50s %8s\n" "$idx" "$(basename "$f")" "$size"
            backups+=("$f")
            ((idx++))
        done
    else
        echo "  (无本地备份)"
    fi
    echo ""

    # NAS 备份
    echo -e "${BOLD}NAS 备份 (${NAS_HOST}):${NC}"
    echo "──────────────────────────────────────────"
    if sshpass -p '$NAS_PASS' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" \
        "ls -1t ${NAS_BACKUP_DIR}/tianlian-v3-backup-*.tar.gz 2>/dev/null || echo ''" 2>/dev/null | while IFS= read -r f; do
        [ -z "$f" ] && continue
        local basename=$(basename "$f")
        printf "  [  ] %s\n" "$basename"
    done
    echo ""
}

# ═══ 安全网：恢复前备份当前状态 ═══
safety_backup() {
    local safety_name="pre-restore-$(date +%Y%m%d_%H%M%S)"
    local safety_dir="${BACKUP_ROOT}/${safety_name}"

    echo ""
    echo -e "${YELLOW}${BOLD}⚠️  正在创建恢复前安全备份...${NC}"

    mkdir -p "$safety_dir"

    # 备份数据库
    if [ -f "$DB_PATH" ]; then
        sqlite3 "$DB_PATH" ".dump" > "${safety_dir}/database.sql" 2>/dev/null
    fi

    # 备份配置
    if [ -f "${BACKEND_DIR}/.env" ]; then
        cp "${BACKEND_DIR}/.env" "${safety_dir}/.env"
    fi

    cd "$BACKUP_ROOT"
    tar -czf "${safety_name}.tar.gz" "$safety_name" 2>/dev/null
    rm -rf "$safety_dir"

    echo -e "${GREEN}✅ 安全备份已创建: ${safety_name}.tar.gz${NC}"
    echo ""
}

# ═══ 执行恢复 ═══
restore_from_archive() {
    local archive="$1"
    local work_dir="${BACKUP_ROOT}/restore-tmp-$$"

    echo ""
    echo -e "${BOLD}恢复源: ${archive}${NC}"

    # 解压
    mkdir -p "$work_dir"
    tar -xzf "$archive" -C "$work_dir" 2>/dev/null

    # 找到 database.sql
    local sql_file=$(find "$work_dir" -name "database.sql" -type f 2>/dev/null | head -1)

    if [ -z "$sql_file" ]; then
        echo -e "${RED}❌ 备份中未找到 database.sql${NC}"
        rm -rf "$work_dir"
        return 1
    fi

    echo "发现数据库文件: $(basename "$(dirname "$sql_file")")/database.sql ($(du -h "$sql_file" | cut -f1))"

    # 确认
    echo ""
    echo -e "${YELLOW}${BOLD}⚠️  即将覆盖当前数据库: ${DB_PATH}${NC}"
    echo -n "确认恢复? (输入 YES 确认): "
    read -r confirm

    if [ "$confirm" != "YES" ]; then
        echo "已取消恢复"
        rm -rf "$work_dir"
        return 0
    fi

    # 创建安全备份
    safety_backup

    # 恢复数据库
    echo ""
    echo -e "${CYAN}正在恢复数据库...${NC}"

    # 删除旧数据库
    if [ -f "$DB_PATH" ]; then
        rm -f "${DB_PATH}-old"
        mv "$DB_PATH" "${DB_PATH}-old"
    fi

    # 从 SQL dump 重建数据库
    if sqlite3 "$DB_PATH" < "$sql_file" 2>/dev/null; then
        echo -e "${GREEN}✅ 数据库恢复完成${NC}"
        rm -f "${DB_PATH}-old"
    else
        echo -e "${RED}❌ 数据库恢复失败！尝试回滚...${NC}"
        if [ -f "${DB_PATH}-old" ]; then
            mv "${DB_PATH}-old" "$DB_PATH"
            echo -e "${YELLOW}已回滚到恢复前状态${NC}"
        fi
        rm -rf "$work_dir"
        return 1
    fi

    # 验证
    echo ""
    echo "验证恢复结果..."
    if sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
        TABLE_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null)
        echo -e "${GREEN}✅ 数据库完整性验证通过 (${TABLE_COUNT} 张表)${NC}"
    else
        echo -e "${RED}⚠️  数据库完整性检查异常${NC}"
        sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>/dev/null
    fi

    # 清理
    rm -rf "$work_dir"
    echo ""
    echo -e "${GREEN}${BOLD}✅ 恢复完成${NC}"
    echo ""
    echo -e "${YELLOW}提示: 请重启后端服务以使用恢复后的数据库${NC}"
}

# ═══ 主流程 ═══
case "$MODE" in
    list)
        list_backups
        exit 0
        ;;

    latest)
        LATEST=$(ls -1t "${BACKUP_ROOT}"/tianlian-v3-backup-*.tar.gz 2>/dev/null | head -1)
        if [ -z "$LATEST" ]; then
            echo -e "${RED}❌ 无本地备份${NC}"
            exit 1
        fi
        restore_from_archive "$LATEST"
        ;;

    file)
        if [ ! -f "$TARGET_FILE" ]; then
            echo -e "${RED}❌ 文件不存在: ${TARGET_FILE}${NC}"
            exit 1
        fi
        restore_from_archive "$TARGET_FILE"
        ;;

    nas-latest)
        echo "从 NAS 下载最新备份..."
        NAS_LATEST=$(sshpass -p '$NAS_PASS' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" \
            "ls -1t ${NAS_BACKUP_DIR}/tianlian-v3-backup-*.tar.gz 2>/dev/null | head -1" 2>/dev/null)
        if [ -z "$NAS_LATEST" ]; then
            echo -e "${RED}❌ NAS 无备份${NC}"
            exit 1
        fi

        LOCAL_COPY="${BACKUP_ROOT}/nas-$(basename "$NAS_LATEST")"
        echo "下载: ${NAS_LATEST}"
        sshpass -p '$NAS_PASS' scp $SSH_OPTS -P "$NAS_PORT" \
            "${NAS_USER}@${NAS_HOST}:${NAS_LATEST}" "$LOCAL_COPY" 2>/dev/null

        if [ -f "$LOCAL_COPY" ]; then
            echo -e "${GREEN}✅ 下载完成${NC}"
            restore_from_archive "$LOCAL_COPY"
        else
            echo -e "${RED}❌ 下载失败${NC}"
            exit 1
        fi
        ;;

    interactive)
        echo ""
        echo -e "${BOLD}${CYAN}天链 V3 — 备份恢复${NC}"
        list_backups

        echo -n "选择恢复来源 [1-N 本地 / n-NAS最新 / q 退出]: "
        read -r choice

        case "$choice" in
            q|Q|quit) echo "已取消"; exit 0 ;;
            n|N|nas)
                MODE="nas-latest"
                ;;
            *)
                if [[ "$choice" =~ ^[0-9]+$ ]]; then
                    TARGET_FILE=$(ls -1t "${BACKUP_ROOT}"/tianlian-v3-backup-*.tar.gz 2>/dev/null | sed -n "${choice}p")
                    if [ -z "$TARGET_FILE" ]; then
                        echo -e "${RED}❌ 无效选择${NC}"
                        exit 1
                    fi
                    restore_from_archive "$TARGET_FILE"
                else
                    echo -e "${RED}❌ 无效输入${NC}"
                    exit 1
                fi
                ;;
        esac

        # 如果选择了 nas-latest，执行对应流程
        if [ "$MODE" = "nas-latest" ]; then
            echo "从 NAS 下载最新备份..."
            NAS_LATEST=$(sshpass -p '$NAS_PASS' ssh $SSH_OPTS -p "$NAS_PORT" "${NAS_USER}@${NAS_HOST}" \
                "ls -1t ${NAS_BACKUP_DIR}/tianlian-v3-backup-*.tar.gz 2>/dev/null | head -1" 2>/dev/null)
            if [ -z "$NAS_LATEST" ]; then
                echo -e "${RED}❌ NAS 无备份${NC}"
                exit 1
            fi

            LOCAL_COPY="${BACKUP_ROOT}/nas-$(basename "$NAS_LATEST")"
            echo "下载: ${NAS_LATEST}"
            sshpass -p '$NAS_PASS' scp $SSH_OPTS -P "$NAS_PORT" \
                "${NAS_USER}@${NAS_HOST}:${NAS_LATEST}" "$LOCAL_COPY" 2>/dev/null

            if [ -f "$LOCAL_COPY" ]; then
                echo -e "${GREEN}✅ 下载完成${NC}"
                restore_from_archive "$LOCAL_COPY"
            else
                echo -e "${RED}❌ 下载失败${NC}"
                exit 1
            fi
        fi
        ;;
esac