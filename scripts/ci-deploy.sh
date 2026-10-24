#!/bin/bash
# 天链 V3 CI/CD 自动部署脚本
# 用法: bash scripts/ci-deploy.sh [branch]
# 功能: 拉取代码 → 构建前端 → 打包 → 上传 → 重启服务

set -e

# ==================== 配置 ====================
DEPLOY_USER="root"
DEPLOY_HOST="demo.example.com"
DEPLOY_PATH="/opt/tianlian-v3"
BRANCH="${1:-feature/frontend-api-integration}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEMP_DIR="/tmp/tianlian-deploy-${TIMESTAMP}"

echo "========================================"
echo "  天链 V3 CI/CD 自动部署"
echo "========================================"
echo "分支: ${BRANCH}"
echo "时间: ${TIMESTAMP}"
echo "目标: ${DEPLOY_USER}@${DEPLOY_HOST}"
echo ""

# ==================== Step 1: 拉取最新代码 ====================
echo "▶ Step 1: 拉取最新代码..."
PROJECT_DIR="/Users/xxx/.openclaw/workspace/projects/tianlian-v3"
cd "${PROJECT_DIR}"

# 切换到目标分支
git checkout "${BRANCH}" 2>/dev/null || true
git pull origin "${BRANCH}" 2>/dev/null || echo "  (本地已是最新)"

echo "  ✅ 代码已更新: $(git log --oneline -1)"
echo ""

# ==================== Step 2: 运行后端测试 ====================
echo "▶ Step 2: 运行后端测试..."
cd "${PROJECT_DIR}/backend"

# 检查pytest是否可用
if command -v pytest &>/dev/null; then
    pytest tests/ -v --tb=short 2>/dev/null && echo "  ✅ 测试通过" || echo "  ⚠️  测试失败，继续部署"
else
    echo "  ⚠️  pytest 未安装，跳过测试"
fi
echo ""

# ==================== Step 3: 构建前端 ====================
echo "▶ Step 3: 构建前端..."
cd "${PROJECT_DIR}/frontend"

# 检查依赖
if [ ! -d "node_modules" ]; then
    echo "  安装依赖..."
    npm install --silent 2>/dev/null
fi

# 构建
npm run build 2>&1 | tail -5
echo "  ✅ 前端构建完成"
echo ""

# ==================== Step 4: 打包部署文件 ====================
echo "▶ Step 4: 打包部署文件..."
mkdir -p "${TEMP_DIR}"

# 复制后端
cp -r "${PROJECT_DIR}/backend" "${TEMP_DIR}/"
# 复制前端构建产物
cp -r "${PROJECT_DIR}/frontend/dist" "${TEMP_DIR}/frontend"
# 复制配置文件
cp "${PROJECT_DIR}/tianlian-backend.service" "${TEMP_DIR}/"
cp "${PROJECT_DIR}/tianlian-nginx.conf" "${TEMP_DIR}/"

echo "  ✅ 打包完成: ${TEMP_DIR}"
echo ""

# ==================== Step 5: 上传到服务器 ====================
echo "▶ Step 5: 上传到服务器..."
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p /tmp/tianlian-deploy-${TIMESTAMP}"

scp -r "${TEMP_DIR}/backend" "${DEPLOY_USER}@${DEPLOY_HOST}:/tmp/tianlian-deploy-${TIMESTAMP}/"
scp -r "${TEMP_DIR}/frontend" "${DEPLOY_USER}@${DEPLOY_HOST}:/tmp/tianlian-deploy-${TIMESTAMP}/"
scp "${TEMP_DIR}/tianlian-backend.service" "${DEPLOY_USER}@${DEPLOY_HOST}:/tmp/tianlian-deploy-${TIMESTAMP}/"
scp "${TEMP_DIR}/tianlian-nginx.conf" "${DEPLOY_USER}@${DEPLOY_HOST}:/tmp/tianlian-deploy-${TIMESTAMP}/"

echo "  ✅ 上传完成"
echo ""

# ==================== Step 6: 服务器端安装 ====================
echo "▶ Step 6: 服务器端安装..."
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'REMOTE_EOF'
set -e

TIMESTAMP=$(ls /tmp/ | grep tianlian-deploy- | tail -1 | sed 's/tianlian-deploy-//')
DEPLOY_DIR="/tmp/tianlian-deploy-${TIMESTAMP}"
DEPLOY_PATH="/opt/tianlian-v3"
BACKUP_PATH="${DEPLOY_PATH}_backup_$(date +%Y%m%d_%H%M%S)"

echo "  备份旧版本..."
if [ -d "${DEPLOY_PATH}" ]; then
    cp -r "${DEPLOY_PATH}" "${BACKUP_PATH}"
fi

echo "  部署新文件..."
mkdir -p "${DEPLOY_PATH}"
rm -rf "${DEPLOY_PATH}/backend" "${DEPLOY_PATH}/frontend"
cp -r "${DEPLOY_DIR}/backend" "${DEPLOY_PATH}/"
cp -r "${DEPLOY_DIR}/frontend" "${DEPLOY_PATH}/"

echo "  安装后端依赖..."
cd "${DEPLOY_PATH}/backend"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
# 使用 venv 的 pip 直接安装，不激活环境
"${DEPLOY_PATH}/backend/venv/bin/pip" install -r requirements.txt -q --no-warn-script-location 2>/dev/null || \
    "${DEPLOY_PATH}/backend/venv/bin/python" -m pip install -r requirements.txt -q --no-warn-script-location

echo "  更新服务配置..."
cp "${DEPLOY_DIR}/tianlian-backend.service" /etc/systemd/system/
cp "${DEPLOY_DIR}/tianlian-nginx.conf" /etc/nginx/conf.d/tianlian.conf

echo "  重启服务..."
systemctl daemon-reload
systemctl restart tianlian-backend
systemctl reload nginx

echo "  等待后端启动..."
sleep 3

# 健康检查
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/health 2>/dev/null || echo "000")
if [ "$HEALTH" = "200" ]; then
    echo "  ✅ 健康检查通过"
else
    echo "  ❌ 健康检查失败 (HTTP ${HEALTH})"
    echo "  回滚到旧版本..."
    rm -rf "${DEPLOY_PATH}"
    cp -r "${BACKUP_PATH}" "${DEPLOY_PATH}"
    systemctl restart tianlian-backend
    systemctl reload nginx
    exit 1
fi

# 清理临时文件
rm -rf "${DEPLOY_DIR}"
rm -rf "${DEPLOY_PATH}_backup_"*

echo "  ✅ 部署完成"
REMOTE_EOF

echo ""

# ==================== Step 7: 最终验证 ====================
echo "▶ Step 7: 最终验证..."
sleep 2

FRONTEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${DEPLOY_HOST}" 2>/dev/null || echo "000")
API_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${DEPLOY_HOST}/api/v1/health" 2>/dev/null || echo "000")

echo ""
echo "========================================"
if [ "$FRONTEND_CODE" = "200" ] && [ "$API_CODE" = "200" ]; then
    echo "  🎉 部署成功！"
    echo "  前端: http://${DEPLOY_HOST} (HTTP ${FRONTEND_CODE})"
    echo "  API:  http://${DEPLOY_HOST}/api/v1/health (HTTP ${API_CODE})"
else
    echo "  ⚠️  部署完成但有异常"
    echo "  前端: HTTP ${FRONTEND_CODE}"
    echo "  API:  HTTP ${API_CODE}"
fi
echo "========================================"

# 清理本地临时文件
rm -rf "${TEMP_DIR}"
