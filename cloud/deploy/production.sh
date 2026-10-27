#!/bin/bash
# 天链 V3 生产环境部署脚本

set -e

# 配置变量
PROJECT_NAME="tianlian-v3"
BACKEND_DIR="../backend"
FRONTEND_DIR="../frontend"
SERVER_USER="ubuntu"
SERVER_HOST="your-server-ip"
SERVER_DIR="/opt/tianlian"
DOMAIN="tianlian.yourdomain.com"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== 天链 V3 生产环境部署 ===${NC}"

# 1. 准备服务器
echo -e "\n${YELLOW}1. 服务器准备${NC}"
echo "- 创建系统用户: tianlian"
echo "- 安装 PostgreSQL 15"
echo "- 安装 Redis"
echo "- 安装 Nginx"
echo "- 配置防火墙"

# 2. 数据库设置
echo -e "\n${YELLOW}2. 数据库设置${NC}"
echo "- 创建数据库: tianlian_v3"
echo "- 创建用户: tianlian"
echo "- 运行迁移: alembic upgrade head"

# 3. 后端部署
echo -e "\n${YELLOW}3. 后端部署${NC}"
echo "- 复制后端代码到服务器"
echo "- 安装 Python 依赖"
echo "- 配置 .env (生产环境)"
echo "- 安装 Gunicorn + Nginx"
echo "- 启动服务: systemctl start tianlian-api"

# 4. 前端部署
echo -e "\n${YELLOW}4. 前端部署${NC}"
echo "- 构建: npm run build"
echo "- 复制到 Nginx 目录"
echo "- 配置 HTTPS (Let's Encrypt)"

# 5. 移动端构建说明
echo -e "\n${YELLOW}5. 移动端 (iOS)${NC}"
echo "- 需要 macOS + Xcode 完整版"
echo "- 运行: npx expo prebuild --platform ios"
echo "- 运行: xcodebuild -workspace ios/app.xcworkspace"
echo "- 或者使用 EAS: npx eas build"

# 完成
echo -e "\n${GREEN}=== 部署完成 ===${NC}"
echo "访问地址: https://$DOMAIN"
echo "API地址: https://$DOMAIN/api/v1"
