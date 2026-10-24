#!/bin/bash
# Git pre-push hook - 自动生成 changelog
# 安装: bash ci/changelog-hook-install.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"

# 检查推送的目标分支
while read local_ref local_sha remote_ref remote_sha; do
    BRANCH=$(echo "$remote_ref" | sed 's|refs/heads/||')
    
    # 仅在推送到稳定分支时自动生成 changelog
    if [[ "$BRANCH" == "stable-v3.0" || "$BRANCH" == "main" ]]; then
        echo "🐵 检测到推送到 ${BRANCH} 分支, 自动生成 changelog..."
        cd "$PROJECT_DIR"
        python3 scripts/generate-changelog.py --latest
        
        if [ -f "CHANGELOG.md" ]; then
            # 将 changelog 更新加入本次推送
            git add CHANGELOG.md
            git commit -m "docs: 自动更新 CHANGELOG.md" --no-verify || true
            echo "✅ CHANGELOG.md 已更新并提交"
        fi
    fi
done

exit 0