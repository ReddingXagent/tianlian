#!/bin/bash
# ─── 天链V3 域名自动管理脚本 (Phase9) ───
# 功能:
#   1. 添加/删除/列出受管域名
#   2. 验证域名 DNS 解析是否正确
#   3. 检查域名 HTTPS 状态
#   4. 生成 Nginx 配置片段
#
# 用法:
#   bash scripts/domain-manage.sh add example.com                    # 添加域名
#   bash scripts/domain-manage.sh remove example.com                 # 删除域名
#   bash scripts/domain-manage.sh list                               # 列出所有域名
#   bash scripts/domain-manage.sh check example.com                  # 检查域名状态
#   bash scripts/domain-manage.sh check-all                          # 检查所有域名
#   bash scripts/domain-manage.sh generate-nginx example.com          # 生成 Nginx 配置

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN_FILE="${PROJECT_DIR}/.domains"   # 受管域名列表
CERT_DIR="/etc/letsencrypt/live"
EMAIL="${SSL_EMAIL:-admin@tianlian.com}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*" >&2; }
info()  { echo -e "${CYAN}[→]${NC} $*"; }

# 确保域名文件存在
touch "${DOMAIN_FILE}" 2>/dev/null || true

# ================= 命令 =================

cmd_add() {
    local domain="$1"
    
    if grep -q "^${domain}$" "${DOMAIN_FILE}" 2>/dev/null; then
        warn "域名 ${domain} 已在受管列表中"
        return 0
    fi
    
    echo "${domain}" >> "${DOMAIN_FILE}"
    log "域名已添加: ${domain}"
    
    # DNS 验证
    info "验证 DNS 解析..."
    local resolved_ip
    resolved_ip=$(dig +short "${domain}" 2>/dev/null | head -1 || echo "")
    
    if [ -n "${resolved_ip}" ]; then
        log "DNS 解析: ${domain} → ${resolved_ip}"
    else
        warn "DNS 解析失败: ${domain} 无法解析"
        info "请确保域名已正确指向服务器 IP"
    fi
}

cmd_remove() {
    local domain="$1"
    
    if ! grep -q "^${domain}$" "${DOMAIN_FILE}" 2>/dev/null; then
        warn "域名 ${domain} 不在受管列表中"
        return 0
    fi
    
    # 删除域名 (保留空行)
    grep -v "^${domain}$" "${DOMAIN_FILE}" > "${DOMAIN_FILE}.tmp" || true
    mv "${DOMAIN_FILE}.tmp" "${DOMAIN_FILE}"
    
    log "域名已移除: ${domain}"
    info "如需同时删除证书，请运行: sudo certbot delete --cert-name ${domain}"
}

cmd_list() {
    if [ ! -s "${DOMAIN_FILE}" ]; then
        info "受管域名列表为空"
        return 0
    fi
    
    echo ""
    echo "受管域名列表:"
    echo "────────────────────────────────────────────────"
    
    while IFS= read -r domain; do
        [ -z "${domain}" ] && continue
        
        # 证书状态
        local cert_status="❌ 无证书"
        if [ -d "${CERT_DIR}/${domain}" ]; then
            local fullchain="${CERT_DIR}/${domain}/fullchain.pem"
            if [ -f "${fullchain}" ]; then
                local expire_date
                expire_date=$(openssl x509 -enddate -noout -in "${fullchain}" 2>/dev/null | cut -d= -f2 || echo "unknown")
                local days_left="?"
                if [ "${expire_date}" != "unknown" ]; then
                    local expire_epoch
                    expire_epoch=$(date -d "${expire_date}" +%s 2>/dev/null || echo "0")
                    local now_epoch
                    now_epoch=$(date +%s)
                    days_left=$(( (expire_epoch - now_epoch) / 86400 ))
                fi
                cert_status="✅ 有效 (${expire_date}, ${days_left}天)"
            fi
        fi
        
        # DNS 解析
        local dns_ip
        dns_ip=$(dig +short "${domain}" 2>/dev/null | head -1 || echo "N/A")
        
        printf "  %-30s DNS: %-15s  %s\n" "${domain}" "${dns_ip:-N/A}" "${cert_status}"
    done < "${DOMAIN_FILE}"
    
    echo "────────────────────────────────────────────────"
    echo ""
    echo "总计: $(grep -c . "${DOMAIN_FILE}" 2>/dev/null || echo 0) 个域名"
}

cmd_check() {
    local domain="$1"
    
    info "检查域名: ${domain}"
    echo ""
    
    # DNS
    info "1. DNS 解析"
    local dns_ip
    dns_ip=$(dig +short "${domain}" 2>/dev/null | head -1 || echo "N/A")
    if [ "${dns_ip}" != "N/A" ]; then
        log "   ${domain} → ${dns_ip}"
    else
        err "   无法解析"
    fi
    
    # HTTP
    info "2. HTTP 访问"
    local http_code
    http_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "http://${domain}" 2>/dev/null || echo "000")
    if [ "${http_code}" != "000" ]; then
        log "   HTTP → ${http_code}"
    else
        err "   HTTP 无法访问"
    fi
    
    # HTTPS
    info "3. HTTPS 访问"
    local https_code
    https_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "https://${domain}" 2>/dev/null || echo "000")
    if [ "${https_code}" != "000" ]; then
        log "   HTTPS → ${https_code}"
    else
        err "   HTTPS 无法访问"
    fi
    
    # 证书信息
    info "4. SSL 证书"
    if [ -d "${CERT_DIR}/${domain}" ]; then
        local fullchain="${CERT_DIR}/${domain}/fullchain.pem"
        if [ -f "${fullchain}" ]; then
            openssl x509 -in "${fullchain}" -noout -subject -issuer -dates 2>/dev/null | sed 's/^/   /'
        fi
    else
        warn "   无本地证书"
    fi
    
    echo ""
}

cmd_check_all() {
    info "检查所有受管域名..."
    echo ""
    
    if [ ! -s "${DOMAIN_FILE}" ]; then
        info "没有受管域名"
        return 0
    fi
    
    while IFS= read -r domain; do
        [ -z "${domain}" ] && continue
        cmd_check "${domain}"
    done < "${DOMAIN_FILE}"
}

cmd_generate_nginx() {
    local domain="$1"
    local conf_file="/tmp/nginx-ssl-${domain}.conf"
    
    info "为 ${domain} 生成 Nginx SSL 配置..."
    
    cat > "${conf_file}" << NGINX
# HTTP → HTTPS 重定向
server {
    listen 80;
    listen [::]:80;
    server_name ${domain};

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

# HTTPS 主服务
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${domain};

    ssl_certificate     /etc/letsencrypt/live/${domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${domain}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;

    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    client_max_body_size 10M;

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/javascript application/javascript application/json;

    # API 代理
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    # 前端
    location / {
        proxy_pass http://localhost:3004;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
NGINX

    log "配置已生成: ${conf_file}"
    echo ""
    info "安装步骤:"
    info "  1. sudo cp ${conf_file} /etc/nginx/conf.d/${domain}.conf"
    info "  2. sudo nginx -t"
    info "  3. sudo nginx -s reload"
}

# ================= 主流程 =================
usage() {
    cat << EOF
天链V3 域名自动管理 (Phase9)

用法: bash scripts/domain-manage.sh <命令> [参数]

命令:
  add <domain>        添加受管域名
  remove <domain>     移除受管域名
  list                列出所有受管域名
  check <domain>      检查单个域名状态
  check-all           检查所有域名
  generate-nginx <domain>  生成 Nginx SSL 配置

示例:
  bash scripts/domain-manage.sh add ops.example.com
  bash scripts/domain-manage.sh list
  bash scripts/domain-manage.sh check ops.example.com
  bash scripts/domain-manage.sh check-all
EOF
    exit 0
}

case "${1:-}" in
    add)            [ -z "${2:-}" ] && usage; cmd_add "$2" ;;
    remove)         [ -z "${2:-}" ] && usage; cmd_remove "$2" ;;
    list)           cmd_list ;;
    check)          [ -z "${2:-}" ] && usage; cmd_check "$2" ;;
    check-all)      cmd_check_all ;;
    generate-nginx) [ -z "${2:-}" ] && usage; cmd_generate_nginx "$2" ;;
    *)              usage ;;
esac
