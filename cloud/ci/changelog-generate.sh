#!/bin/bash
# CI 自动生成 Changelog 步骤
# 在 GitHub Actions 或手动部署时自动运行
# 用法: bash ci/changelog-generate.sh [--latest] [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*"; }

# ─── 步骤 ────────────────────────────────────────────────────

echo "🐵 天链V3 CI - Changelog 自动生成"
echo ""

# 1. 确保有 git 历史
if [ ! -d ".git" ]; then
    err "不在 Git 仓库中"
    exit 1
fi

# 2. 获取当前版本信息
LATEST_TAG=$(git tag -l --sort=-creatordate | grep '^v\d' | head -1 || echo "无版本标签")
BRANCH=$(git branch --show-current)
COMMIT_COUNT=$(git log --oneline | wc -l | tr -d ' ')

log "当前分支: ${BRANCH}"
log "最新版本标签: ${LATEST_TAG}"
log "总提交数: ${COMMIT_COUNT}"
echo ""

# 3. 生成 changelog
ARGS="${1:-}"
python3 scripts/generate-changelog.py ${ARGS}

# 4. 检查是否生成了 changelog
if [ -f "CHANGELOG.md" ]; then
    SIZE=$(wc -c < CHANGELOG.md | tr -d ' ')
    log "CHANGELOG.md 已生成 (${SIZE} 字符)"
    
    # 5. 显示最近变更摘要
    echo ""
    echo "📋 最近变更摘要:"
    head -40 CHANGELOG.md
else
    err "CHANGELOG.md 未生成"
    exit 1
fi

echo ""
log "=== Changelog 生成完成 ==="