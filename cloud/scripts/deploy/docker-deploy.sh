#!/bin/bash
# ─── 天链V3 Docker一键部署到云服务器 ───
# 用法: ./scripts/deploy/docker-deploy.sh
# 前提: Docker + Docker Compose 已在云服务器安装

set -euo pipefail

SSH_HOST="demo.example.com"
SSH_USER="root"
REMOTE_DIR="/opt/tianlian-v3"

cd "$(dirname "$0")/../.."

echo "========================================"
echo "  天链V3 Docker 云部署"
echo "  目标: $SSH_HOST"
echo "========================================"

# 1. 远程目录准备
echo ""
echo "[1/4] 远程目录准备..."
ssh "${SSH_USER}@${SSH_HOST}" "mkdir -p ${REMOTE_DIR}/{backend,frontend/dist,nginx,scripts,data/{postgres,redis}}"

# 2. 传输配置文件和项目
echo ""
echo "[2/4] 传输文件到云服务器..."

# 核心配置文件
scp docker-compose.yml "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/"
scp docker-compose.monitoring.yml "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/"
scp nginx.prod.conf "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/"
scp .env.docker "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/.env"

# 监控配置
scp -r prometheus "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/"
scp -r alertmanager "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/"
scp -r grafana "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/"

# 后端
scp -r backend/app "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/backend/"
scp backend/requirements.txt "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/backend/"

# 前端构建
cd frontend
npm ci 2>/dev/null
npm run build
cd ..
scp -r frontend/dist/* "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/frontend/dist/"

# 3. 远程启动
echo ""
echo "[3/4] 启动服务..."
ssh "${SSH_USER}@${SSH_HOST}" "cd ${REMOTE_DIR} && docker-compose up -d --build"
sleep 5

# 4. 健康检查
echo ""
echo "[4/4] 健康检查..."
HEALTH=$(curl -sS -o /dev/null -w "%{http_code}" "http://${SSH_HOST}/api/v1/health" 2>/dev/null || echo "failed")

if [[ "$HEALTH" == "200" ]]; then
  echo "✅ 部署成功! 服务运行中"
  echo "   前端: http://${SSH_HOST}/"
  echo "   后端: http://${SSH_HOST}/api/v1/health"
else
  echo "⚠️  健康检查状态: $HEALTH (可能需要手动检查)"
  echo "   服务器: http://${SSH_HOST}/"
fi
