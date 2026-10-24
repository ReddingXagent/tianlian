#!/bin/bash
# ─── 天链V3 CI部署脚本 ───
# 用法: ./scripts/deploy/ci-deploy.sh [branch]
set -euo pipefail

BRANCH="${1:-feature/frontend-api-integration}"
SSH_HOST="demo.example.com"
SSH_USER="root"
REMOTE_DIR="/opt/tianlian-v3"

cd "$(dirname "$0")/../.."

echo "========================================"
echo "  天链V3 自动部署脚本"
echo "  分支: $BRANCH"
echo "  目标: $SSH_HOST:$REMOTE_DIR"
echo "========================================"

# 1. 检查分支
echo ""
echo "[1/5] 检查分支..."
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
  echo "⚠️  当前分支: $CURRENT_BRANCH, 目标分支: $BRANCH"
  git checkout "$BRANCH"
fi

# 2. 构建前端
echo ""
echo "[2/5] 构建前端..."
cd frontend
npm ci
npm run build
cd ..

echo "✅ 前端构建完成: frontend/dist/"

# 3. 压缩传输
echo ""
echo "[3/5] 打包传输..."
DEPLOY_FILE="deploy-$(date '+%Y%m%d-%H%M%S').tar.gz"
tar czf "$DEPLOY_FILE" \
  backend/app \
  frontend/dist \
  docker-compose.yml \
  docker-compose.monitoring.yml \
  nginx.prod.conf \
  prometheus \
  alertmanager \
  grafana \
  loki \
  promtail \
  scripts

scp "$DEPLOY_FILE" "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/"
rm "$DEPLOY_FILE"

echo "✅ 传输完成: $DEPLOY_FILE"

# 4. 远程部署
echo ""
echo "[4/5] 远程部署..."
ssh "${SSH_USER}@${SSH_HOST}" << 'REMOTE'
  cd /opt/tianlian-v3
  
  # 解压
  LATEST_TAR=$(ls -t deploy-*.tar.gz 2>/dev/null | head -1)
  if [[ -z "$LATEST_TAR" ]]; then
    echo "❌ 未找到部署包"
    exit 1
  fi
  
  echo "解压: $LATEST_TAR"
  tar xzf "$LATEST_TAR"
  rm "$LATEST_TAR"
  
  # 重建/重启服务
  docker-compose down
  docker-compose up -d --build
  
  echo "✅ 服务已重启"
REMOTE

# 5. 健康检查
echo ""
echo "[5/5] 健康检查..."
sleep 5
curl -sS -o /dev/null -w "%{http_code}" "http://${SSH_HOST}/" && echo " — 前端 ✅" || echo " — 前端 ❌"
curl -sS -o /dev/null -w "%{http_code}" "http://${SSH_HOST}/api/v1/health" && echo " — 后端 ✅" || echo " — 后端 ❌"

echo ""
echo "========================================"
echo "  ✅ 部署完成"
echo "  http://${SSH_HOST}"
echo "========================================"
