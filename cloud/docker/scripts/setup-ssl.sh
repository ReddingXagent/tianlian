#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  天链V3 - HTTPS 证书安装脚本 (Let's Encrypt + Nginx)
# ═══════════════════════════════════════════════════════════════
# 用法:
#   chmod +x docker/scripts/setup-ssl.sh
#   export DOMAIN=tianlian.example.com
#   export EMAIL=admin@example.com
#   sudo ./docker/scripts/setup-ssl.sh
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ─── 颜色 ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ─── 帮助 ───
usage() {
    echo "用法: $0 [选项]"
    echo "选项:"
    echo "  -d, --domain DOMAIN     必需: 域名 (如 tianlian.example.com)"
    echo "  -e, --email EMAIL       必需: 邮箱 (Let's Encrypt 通知)"
    echo "  -s, --staging           使用 staging 环境测试 (避免被限)"
    echo "  -h, --help              显示帮助"
    exit 1
}

# ─── 解析参数 ───
STAGING=false
DOMAIN=""
EMAIL=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--domain) DOMAIN="$2"; shift 2 ;;
        -e|--email) EMAIL="$2"; shift 2 ;;
        -s|--staging) STAGING=true; shift ;;
        -h|--help) usage ;;
        *) echo -e "${RED}未知参数: $1${NC}"; usage ;;
    esac
done

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
    echo -e "${RED}错误: 必须提供 --domain 和 --email${NC}"
    usage
fi

# ─── 检查依赖 ───
command -v docker >/dev/null 2>&1 || { echo -e "${RED}错误: 需要 Docker${NC}"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo -e "${RED}错误: 需要 docker compose${NC}"; exit 1; }

echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  天链V3 - HTTPS 证书安装${NC}"
echo -e "${GREEN}  域名: ${DOMAIN}${NC}"
echo -e "${GREEN}  邮箱: ${EMAIL}${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"

# ─── 步骤1: 创建 Nginx SSL 配置 ───
echo -e "\n${YELLOW}[1/5] 创建 Nginx SSL 配置...${NC}"

NGINX_SSL_DIR="/etc/nginx/ssl"
mkdir -p "${NGINX_SSL_DIR}"

cat > "${NGINX_SSL_DIR}/tianlian-ssl.conf" << 'NGINXEOF'
# ─── 天链V3 Nginx SSL 配置 (由 setup-ssl.sh 生成) ───

# HTTP → HTTPS 重定向
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name _;

    # SSL 证书 (由 certbot 管理)
    ssl_certificate     /etc/letsencrypt/live/__DOMAIN__/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/__DOMAIN__/privkey.pem;

    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    # 其他安全头
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 前端静态文件
    root /usr/share/nginx/html;
    index index.html;

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json application/xml image/svg+xml;

    # 静态资源缓存
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API 代理
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
    }

    # WebSocket 代理
    location /ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400s;
    }

    # SPA 路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # .well-known (Let's Encrypt)
    location /.well-known/ {
        root /usr/share/nginx/html;
    }

    # 禁止隐藏文件
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
NGINXEOF

# 替换域名占位符
sed -i "s/__DOMAIN__/${DOMAIN}/g" "${NGINX_SSL_DIR}/tianlian-ssl.conf"

echo -e "${GREEN}  ✓ SSL 配置已创建: ${NGINX_SSL_DIR}/tianlian-ssl.conf${NC}"

# ─── 步骤2: DNS 验证 ───
echo -e "\n${YELLOW}[2/5] 验证 DNS 解析...${NC}"
SERVER_IP=$(curl -s http://checkip.amazonaws.com 2>/dev/null || curl -s https://api.ipify.org 2>/dev/null || echo "unknown")
DOMAIN_IP=$(dig +short "${DOMAIN}" 2>/dev/null || host "${DOMAIN}" 2>/dev/null | grep "has address" | awk '{print $4}' || echo "unknown")

echo "  服务器 IP: ${SERVER_IP}"
echo "  域名 ${DOMAIN} → ${DOMAIN_IP}"

if [[ "$DOMAIN_IP" != "$SERVER_IP" && "$SERVER_IP" != "unknown" && "$DOMAIN_IP" != "unknown" ]]; then
    echo -e "${RED}  ⚠ 域名 ${DOMAIN} 未指向本服务器 (${SERVER_IP})${NC}"
    echo -e "${RED}  请先在 DNS 管理面板添加 A 记录: ${DOMAIN} → ${SERVER_IP}${NC}"
    echo -e "${YELLOW}  是否继续? (y/N)${NC}"
    read -r continue_anyway
    if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
        echo "已取消"
        exit 1
    fi
fi
echo -e "${GREEN}  ✓ DNS 验证通过${NC}"

# ─── 步骤3: 确保服务运行 ───
echo -e "\n${YELLOW}[3/5] 启动服务 (HTTP 模式, Let's Encrypt 验证需要)...${NC}"
docker compose up -d frontend
echo -e "${GREEN}  ✓ 服务已启动${NC}"

# ─── 步骤4: 获取证书 ───
echo -e "\n${YELLOW}[4/5] 使用 Certbot 获取证书...${NC}"

CERTBOT_CMD="certonly --webroot --webroot-path=/usr/share/nginx/html \
    --domain ${DOMAIN} \
    --email ${EMAIL} \
    --agree-tos \
    --non-interactive"

if [[ "$STAGING" == true ]]; then
    echo "  使用 staging 环境..."
    CERTBOT_CMD="${CERTBOT_CMD} --staging"
fi

docker run --rm \
    --network tianlian_tianlian-net \
    -v "${NGINX_SSL_DIR}/../letsencrypt:/etc/letsencrypt" \
    -v frontend_html:/usr/share/nginx/html \
    certbot/certbot ${CERTBOT_CMD}

echo -e "${GREEN}  ✓ 证书已获取${NC}"

# ─── 步骤5: 重启 Nginx 加载 SSL ───
echo -e "\n${YELLOW}[5/5] 重启前端 Nginx 加载 SSL 配置...${NC}"

# 复制 SSL 配置到 Nginx
docker cp "${NGINX_SSL_DIR}/tianlian-ssl.conf" tianlian-frontend:/etc/nginx/conf.d/default.conf
docker exec tianlian-frontend nginx -s reload

echo -e "\n${GREEN}══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ HTTPS 部署完成!${NC}"
echo -e "${GREEN}  访问: https://${DOMAIN}${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo ""
echo "证书自动续期 (crontab):"
echo "  0 0 * * * docker run --rm --network tianlian_tianlian-net -v /etc/letsencrypt:/etc/letsencrypt -v tianlian-frontend:/usr/share/nginx/html certbot/certbot renew && docker exec tianlian-frontend nginx -s reload"