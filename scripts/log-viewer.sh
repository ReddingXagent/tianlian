#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# 天链 V3 — 日志查看器
# 用法:
#   ./log-viewer.sh                 实时查看（tail -f）
#   ./log-viewer.sh --level ERROR   仅看 ERROR 级别
#   ./log-viewer.sh --level WARN    仅看 WARNING+ERROR
#   ./log-viewer.sh --module auth   按模块过滤
#   ./log-viewer.sh --stats         错误统计摘要
#   ./log-viewer.sh --errors        仅看 error 日志文件
#   ./log-viewer.sh --recent N      最近 N 行（默认 100）
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${PROJECT_DIR}/logs"
APP_LOG="${LOG_DIR}/tianlian-v3.log"
ERROR_LOG="${LOG_DIR}/tianlian-v3-error.log"

# ─── 颜色 ───
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
BOLD='\033[1m'
NC='\033[0m'

usage() {
    cat << 'EOF'
天链 V3 日志查看器

用法:
  ./log-viewer.sh [选项]

选项:
  --level LEVEL    按级别过滤: DEBUG | INFO | WARNING | ERROR | CRITICAL
  --module NAME    按模块过滤 (如 auth, alarms, devices)
  --errors         仅查看错误日志文件
  --recent N       查看最近 N 行 (默认 100)
  --stats          显示错误统计
  --follow, -f     实时跟踪 (tail -f)
  --help           显示此帮助

示例:
  ./log-viewer.sh                            实时查看所有日志
  ./log-viewer.sh --level ERROR              仅看 ERROR
  ./log-viewer.sh --module auth              仅看认证模块
  ./log-viewer.sh --level WARN --module main 认证模块的警告
  ./log-viewer.sh --errors --recent 50       最近 50 条错误
  ./log-viewer.sh --stats                    错误统计
EOF
}

# ─── 解析命令行 ───
LEVEL=""
MODULE=""
RECENT=100
FOLLOW=false
ERRORS_ONLY=false
STATS=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --level)
            LEVEL="${2^^}"
            shift 2
            ;;
        --module)
            MODULE="$2"
            shift 2
            ;;
        --errors)
            ERRORS_ONLY=true
            shift
            ;;
        --recent)
            RECENT="$2"
            shift 2
            ;;
        --follow|-f)
            FOLLOW=true
            shift
            ;;
        --stats)
            STATS=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# ─── 选择日志文件 ───
if $ERRORS_ONLY; then
    TARGET_LOG="$ERROR_LOG"
else
    TARGET_LOG="$APP_LOG"
fi

# ─── 检查日志是否存在 ───
if [[ ! -f "$TARGET_LOG" ]]; then
    echo -e "${YELLOW}日志文件不存在: $TARGET_LOG${NC}"
    echo "提示: 启动应用后日志会自动生成"
    exit 1
fi

# ─── 错误统计 ───
if $STATS; then
    echo -e "${BOLD}═════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  天链 V3 — 错误统计摘要${NC}"
    echo -e "${BOLD}═════════════════════════════════════════════════════${NC}"
    echo ""

    TOTAL_LINES=$(wc -l < "$APP_LOG" | tr -d ' ')
    echo -e "${GRAY}日志总行数: ${TOTAL_LINES}${NC}"

    echo ""
    echo -e "${BOLD}各级别分布:${NC}"
    echo "----------------------------------------"
    for lvl in DEBUG INFO WARNING ERROR CRITICAL; do
        count=$(grep -c "\"level\":\"${lvl}\"" "$APP_LOG" 2>/dev/null || echo 0)
        color=""
        case $lvl in
            DEBUG)   color="$GRAY" ;;
            INFO)    color="$GREEN" ;;
            WARNING) color="$YELLOW" ;;
            ERROR)   color="$RED" ;;
            CRITICAL) color="$RED" ;;
        esac
        printf "  ${color}%-10s${NC}: %s\n" "$lvl" "$count"
    done

    echo ""
    echo -e "${BOLD}ERROR 最近 10 条:${NC}"
    echo "----------------------------------------"
    grep '"level":"ERROR"' "$APP_LOG" | tail -10 | while IFS= read -r line; do
        ts=$(echo "$line" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('timestamp','-')[:19].replace('T',' '))" 2>/dev/null || echo "-")
        module=$(echo "$line" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('module','-'))" 2>/dev/null || echo "-")
        msg=$(echo "$line" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('message','-'))" 2>/dev/null || echo "-")
        printf "  ${GRAY}%s${NC} ${RED}%-20s${NC} %s\n" "$ts" "$module" "$msg"
    done

    echo ""
    echo -e "${BOLD}ERROR 按模块分布:${NC}"
    echo "----------------------------------------"
    grep '"level":"ERROR"' "$APP_LOG" | python3 -c "
import sys, json
from collections import Counter
modules = Counter()
for line in sys.stdin:
    try:
        d = json.loads(line)
        modules[d.get('module','-')] += 1
    except: pass
for mod, cnt in modules.most_common():
    print(f'  {mod:30s} {cnt}')
" 2>/dev/null

    exit 0
fi

# ─── 构建 jq 过滤器 ───
build_filter() {
    local filter="."

    if [[ -n "$LEVEL" ]]; then
        case "$LEVEL" in
            WARNING)
                filter="$filter | select(.level == \"WARNING\" or .level == \"ERROR\" or .level == \"CRITICAL\")"
                ;;
            *)
                filter="$filter | select(.level == \"${LEVEL}\")"
                ;;
        esac
    fi

    if [[ -n "$MODULE" ]]; then
        filter="$filter | select(.module | test(\"$MODULE\"; \"i\"))"
    fi

    echo "$filter"
}

FILTER=$(build_filter)

# ─── 格式化输出 ───
format_line() {
    python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        d = json.loads(line)
    except:
        print(line)
        continue
    ts = d.get('timestamp','-')[:19].replace('T',' ')

    lvl = d.get('level','-')
    colors = {'DEBUG':'36','INFO':'32','WARNING':'33','ERROR':'31','CRITICAL':'35'}
    c = colors.get(lvl, '0')
    lvl_str = f'\033[{c}m[{lvl:^7}]\033[0m'

    mod = f'\033[2m{d.get(\"module\",\"-\"):25s}\033[0m'

    msg = d.get('message','-')

    req = d.get('request_id','-')
    req_str = f'\033[90m[{req[:8]}]\033[0m ' if req and req != '-' else ''

    print(f'{ts} {lvl_str} {mod} {req_str}{msg}')
"
}

# ─── 执行 ───
if $FOLLOW; then
    echo -e "${GRAY}实时跟踪: $TARGET_LOG${NC}"
    echo -e "${GRAY}过滤条件: level=$LEVEL module=$MODULE${NC}"
    echo -e "${GRAY}按 Ctrl+C 退出${NC}"
    echo ""
    tail -f "$TARGET_LOG" | while IFS= read -r line; do
        # 用 python 做快速 JSON 过滤
        echo "$line" | python3 -c "
import sys, json
line = sys.stdin.readline().strip()
if not line: sys.exit(0)
try:
    d = json.loads(line)
except:
    print(line)
    sys.exit(0)
lvl = d.get('level','-')
mod = d.get('module','-')
" 2>/dev/null

        # 简单 grep 过滤
        MATCH=true
        if [[ -n "$LEVEL" ]]; then
            if [[ "$LEVEL" == "WARNING" ]]; then
                echo "$line" | grep -qE '"level":"(WARNING|ERROR|CRITICAL)"' || MATCH=false
            else
                echo "$line" | grep -q "\"level\":\"$LEVEL\"" || MATCH=false
            fi
        fi
        if [[ -n "$MODULE" ]]; then
            echo "$line" | grep -qi "\"module\":\"[^\"]*${MODULE}[^\"]*\"" || MATCH=false
        fi

        if $MATCH; then
            echo "$line" | format_line
        fi
    done
else
    # 只看最近 N 行
    if command -v jq &>/dev/null; then
        tail -"$RECENT" "$TARGET_LOG" | jq -r "$FILTER" | format_line
    else
        echo -e "${YELLOW}提示: 安装 jq 可获得更好的过滤体验 (brew install jq)${NC}"
        echo ""
        tail -"$RECENT" "$TARGET_LOG" | while IFS= read -r line; do
            # 简单 grep 过滤
            MATCH=true
            if [[ -n "$LEVEL" ]]; then
                if [[ "$LEVEL" == "WARNING" ]]; then
                    echo "$line" | grep -qE '"level":"(WARNING|ERROR|CRITICAL)"' || MATCH=false
                else
                    echo "$line" | grep -q "\"level\":\"$LEVEL\"" || MATCH=false
                fi
            fi
            if [[ -n "$MODULE" ]]; then
                echo "$line" | grep -qi "\"module\":\"[^\"]*${MODULE}[^\"]*\"" || MATCH=false
            fi

            if $MATCH; then
                echo "$line" | format_line
            fi
        done
    fi
fi