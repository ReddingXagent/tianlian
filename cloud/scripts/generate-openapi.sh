#!/bin/bash
# =============================================================================
# 天链V3 - OpenAPI 文档自动生成脚本
# 从 FastAPI 后端导出 openapi.json
#
# 默认: in-process 导出（不连 DB、不触发 lifespan、~3s 出结果）
#   bash scripts/generate-openapi.sh
#
# 用法:
#   bash scripts/generate-openapi.sh               # in-process 导出 + 覆盖 docs/openapi.json
#   bash scripts/generate-openapi.sh --check       # 仅检查是否有变化（CI 用，有差异 exit 1）
#   bash scripts/generate-openapi.sh --diff        # 导出 + 输出变更详情
#   bash scripts/generate-openapi.sh --out PATH    # 导出到指定路径（不覆盖 docs）
#   bash scripts/generate-openapi.sh --server      # 起真实 uvicorn 全服导出（非默认，需可连 DB）
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
DOCS_DIR="${PROJECT_ROOT}/docs"
DOCS_OPENAPI="${DOCS_DIR}/openapi.json"
BACKEND_OPENAPI="${BACKEND_DIR}/openapi.json"
DEFAULT_OUT="/tmp/openapi_new.json"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }

# ─── 探测 Python 解释器: .venv 优先（活跃环境），venv fallback（陈旧，仅 .venv 缺失时） ───
PY_BIN=""
resolve_python() {
    if [ -x "${BACKEND_DIR}/.venv/bin/python" ]; then
        PY_BIN="${BACKEND_DIR}/.venv/bin/python"
    elif [ -x "${BACKEND_DIR}/venv/bin/python" ]; then
        warn "使用陈旧 venv/（建议改用 .venv 活跃环境）"
        PY_BIN="${BACKEND_DIR}/venv/bin/python"
    else
        err "未找到虚拟环境 (.venv / venv): ${BACKEND_DIR}"
        err "请先创建: cd backend && python3 -m venv .venv"
        exit 1
    fi
}

# ─── 清理函数（仅 --server 模式用） ───
BACKEND_PID=""
cleanup() {
    if [ -n "${BACKEND_PID:-}" ] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
        kill "${BACKEND_PID}" 2>/dev/null || true
        wait "${BACKEND_PID}" 2>/dev/null || true
        log "后端进程已停止 (PID: ${BACKEND_PID})"
    fi
}
trap cleanup EXIT INT TERM

# ─── 默认: in-process 导出（不连 DB、不触发 lifespan） ───
export_inprocess() {
    local OUT="$1"
    log "in-process 导出 OpenAPI（不连 DB）→ ${OUT}"
    cd "${BACKEND_DIR}"
    # app.openapi() 只基于路由 + Pydantic 模型生成 schema，不触发 lifespan/不连 DB
    "${PY_BIN}" -c '
import json, sys
from app.main import app
spec = app.openapi()
with open(sys.argv[1], "w") as f:
    json.dump(spec, f, ensure_ascii=False, indent=2)
print(len(spec.get("paths", {})))
' "${OUT}" || {
        err "in-process 导出失败"
        return 1
    }
}

# ─── 起真实 uvicorn 全服导出（非默认，需可连 DB；保留供真实路由中间件场景用） ───
export_server() {
    local OUT="$1"
    local BACKEND_PORT="${OPENAPI_GEN_PORT:-8765}"
    local TIMEOUT=30
    log "--server 模式: 启动 FastAPI 后端 (端口: ${BACKEND_PORT})..."
    cd "${BACKEND_DIR}"

    "${PY_BIN}" -m uvicorn app.main:app \
        --host 127.0.0.1 \
        --port "${BACKEND_PORT}" \
        --log-level error &
    BACKEND_PID=$!

    log "等待后端就绪..."
    local i
    for i in $(seq 1 "${TIMEOUT}"); do
        if curl -s "http://127.0.0.1:${BACKEND_PORT}/api/v1/health" > /dev/null 2>&1; then
            log "后端就绪 (${i}s)"
            break
        fi
        sleep 1
        if [ "${i}" -eq "${TIMEOUT}" ]; then
            err "后端启动超时 (${TIMEOUT}s) — 本地连不上生产 PG? 改用默认 in-process 模式"
            return 1
        fi
    done

    curl -s "http://127.0.0.1:${BACKEND_PORT}/openapi.json" -o "${OUT}" || {
        err "无法获取 OpenAPI 文档"
        return 1
    }
    if ! "${PY_BIN}" -c 'import json,sys; json.load(open(sys.argv[1]))' "${OUT}" 2>/dev/null; then
        err "导出的 JSON 格式无效"
        return 1
    fi
    log "已导出 → ${OUT}"
}

# ─── 统计信息 ───
report_stats() {
    local OUT="$1"
    local PATH_COUNT METHOD_COUNT
    read -r PATH_COUNT METHOD_COUNT < <("${PY_BIN}" -c '
import json, sys
d = json.load(open(sys.argv[1]))
p = d.get("paths", {})
print(len(p), sum(len(m) for m in p.values()))
' "${OUT}")
    echo "  API 路径数: ${PATH_COUNT}"
    echo "  API 方法数: ${METHOD_COUNT}"
    echo "  文件大小:   $(du -h "${OUT}" | cut -f1)"
}

# ─── 与 docs/openapi.json 规范化 diff，输出差异行数 ───
diff_against_docs() {
    local OUT="$1"
    if [ ! -f "${DOCS_OPENAPI}" ]; then
        echo "-1"   # 无旧版本可比较
        return 0
    fi
    local DIFF
    DIFF=$(diff \
        <("${PY_BIN}" -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), sort_keys=True, indent=2))' "${DOCS_OPENAPI}") \
        <("${PY_BIN}" -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), sort_keys=True, indent=2))' "${OUT}") \
        2>/dev/null || true)
    if [ -z "${DIFF}" ]; then
        echo "0"
    else
        echo "${DIFF}" | wc -l | tr -d ' '
    fi
}

# ─── 覆盖 docs + backend 的 openapi.json ───
cp_to_docs() {
    local OUT="$1"
    if [ "${OUT}" = "${DOCS_OPENAPI}" ]; then
        return 0   # --out 已直接指向 docs，无需再 cp
    fi
    mkdir -p "${DOCS_DIR}"
    cp "${OUT}" "${DOCS_OPENAPI}"
    cp "${OUT}" "${BACKEND_OPENAPI}"
    log "已覆盖: ${DOCS_OPENAPI}"
    log "已覆盖: ${BACKEND_OPENAPI}"
}

# ─── 主流程 ───
main() {
    local MODE="generate"
    local USE_SERVER=0
    local OUT="${DEFAULT_OUT}"

    while [ $# -gt 0 ]; do
        case "$1" in
            --check)  MODE="check" ;;
            --diff)   MODE="diff" ;;
            --server) USE_SERVER=1 ;;
            --out)    shift; OUT="$1" ;;
            -h|--help)
                sed -n '2,18p' "$0"
                exit 0
                ;;
            *) err "未知参数: $1"; exit 1 ;;
        esac
        shift
    done

    resolve_python

    echo ""
    echo "╔══════════════════════════════════════════════╗"
    echo "║     天链V3 OpenAPI 文档自动生成             ║"
    echo "╚══════════════════════════════════════════════╝"
    echo ""

    # 导出
    if [ "${USE_SERVER}" -eq 1 ]; then
        if ! export_server "${OUT}"; then
            err "全服导出失败，退出"
            exit 1
        fi
    else
        if ! export_inprocess "${OUT}"; then
            err "导出失败，退出"
            exit 1
        fi
    fi

    report_stats "${OUT}"

    local DIFF_LINES
    DIFF_LINES=$(diff_against_docs "${OUT}")

    case "${MODE}" in
        check)
            if [ "${DIFF_LINES}" = "-1" ]; then
                log "首次生成，无旧版本可比较"
            elif [ "${DIFF_LINES}" -gt 0 ]; then
                warn "⚠️  OpenAPI 文档与代码不一致（${DIFF_LINES} 行差异），请重新生成"
                exit 1
            else
                log "OpenAPI 文档与代码一致 ✓"
            fi
            ;;
        diff)
            if [ "${DIFF_LINES}" = "-1" ]; then
                log "首次生成，无旧版本可比较"
            elif [ "${DIFF_LINES}" -gt 0 ]; then
                warn "发现 ${DIFF_LINES} 行变更，详情:"
                diff \
                    <("${PY_BIN}" -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), sort_keys=True, indent=2))' "${DOCS_OPENAPI}") \
                    <("${PY_BIN}" -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), sort_keys=True, indent=2))' "${OUT}") \
                    | head -40 || true
            else
                log "无变更"
            fi
            cp_to_docs "${OUT}"
            ;;
        generate|*)
            if [ "${DIFF_LINES}" = "-1" ]; then
                log "首次生成"
                cp_to_docs "${OUT}"
            elif [ "${DIFF_LINES}" -gt 0 ]; then
                warn "检测到 ${DIFF_LINES} 行差异，核实后更新 docs/openapi.json"
                cp_to_docs "${OUT}"
            else
                log "与 docs/openapi.json 零差异，无需更新"
                # 仍刷新时间戳以保持生成痕迹
                cp_to_docs "${OUT}"
            fi
            ;;
    esac

    echo ""
    log "完成！"

    # 默认输出 /tmp/openapi_new.json 保留，供人工 diff 核实（--out 指定路径同理不删）
}

main "$@"
