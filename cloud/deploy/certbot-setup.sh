#!/bin/bash
# ============================================
# ⚠️ 已废弃 (DEPRECATED)
# 本脚本是 docker webroot 模式旧方案，与生产 systemd nginx 拓扑不符
# （生产为 systemd nginx + upstream 127.0.0.1:8080，无 docker 容器）。
# 权威入口是 scripts/ssl-setup.sh —— 请勿在本方案上继续开发。
# 保留仅为历史参考。
# ============================================
# 天链V3 - Certbot HTTPS 自动续期脚本
#
# 使用方式:
#   1. 首次申请: ./certbot-setup.sh init your-domain.com your@email.com
#   2. 手动续期: ./certbot-setup.sh renew
#   3. 添加到 crontab: 0 3 * * * /opt/tianlian-cloud/deploy/certbot-setup.sh renew >> /var/log/certbot-cron.log 2>&1
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============ 配置 ============
CERTBOT_IMAGE="certbot/certbot:latest"
WEBROOT_PATH="/var/www/certbot"
CERT_PATH="/etc/letsencrypt"
RSA_KEY_SIZE=4096

# ============ 首次申请证书 ============
init_cert() {
    local DOMAIN="${1:-}"
    local EMAIL="${2:-}"

    if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
        log_error "用法: $0 init <域名> <邮箱>"
        echo "  示例: $0 init tianlian.example.com admin@example.com"
        exit 1
    fi

    log_info "开始为 $DOMAIN 申请 Let's Encrypt 证书..."

    # 确保 nginx 在运行且 HTTP 80 端口可访问
    if ! docker ps --format '{{.Names}}' | grep -q 'tianlian-nginx'; then
        log_error "Nginx 容器未运行，请先启动 docker compose up -d nginx"
        exit 1
    fi

    # 确保 webroot 目录存在
    docker exec tianlian-nginx mkdir -p "$WEBROOT_PATH/.well-known/acme-challenge" 2>/dev/null || true

    # 首次申请 (webroot 模式，不需要停止 nginx)
    docker run --rm \
        -v "${PROJECT_DIR}/certbot/www:${WEBROOT_PATH}" \
        -v "${PROJECT_DIR}/certbot/conf:${CERT_PATH}" \
        "$CERTBOT_IMAGE" \
        certonly \
        --webroot \
        --webroot-path="${WEBROOT_PATH}" \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --rsa-key-size "$RSA_KEY_SIZE" \
        --force-renewal \
        -d "$DOMAIN"

    if [ $? -eq 0 ]; then
        log_info "✅ 证书申请成功！"
        log_info "证书位置: ${PROJECT_DIR}/certbot/conf/live/$DOMAIN/"
        log_info "请确保 nginx.prod.conf 中的 ssl_certificate 路径正确"
        log_info "重启 nginx: docker compose restart nginx"
    else
        log_error "证书申请失败，请检查域名解析和网络可达性"
        exit 1
    fi
}

# ============ 使用 DNS 验证申请通配符证书 ============
init_wildcard_cert() {
    local DOMAIN="${1:-}"
    local EMAIL="${2:-}"

    if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
        log_error "用法: $0 init-wildcard <域名> <邮箱>"
        echo "  示例: $0 init-wildcard example.com admin@example.com"
        exit 1
    fi

    log_info "为 *.$DOMAIN 和 $DOMAIN 申请通配符证书 (DNS 验证)..."

    docker run --rm \
        -v "${PROJECT_DIR}/certbot/conf:${CERT_PATH}" \
        "$CERTBOT_IMAGE" \
        certonly \
        --manual \
        --preferred-challenges dns \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --rsa-key-size "$RSA_KEY_SIZE" \
        -d "$DOMAIN" \
        -d "*.$DOMAIN"
}

# ============ 续期证书 (推荐用 cron 自动运行) ============
renew_cert() {
    log_info "检查证书续期..."

    # 检查 certbot/conf 是否存在
    if [ ! -d "${PROJECT_DIR}/certbot/conf/live" ]; then
        log_warn "未找到已申请的证书，跳过续期"
        return 0
    fi

    # 尝试续期
    docker run --rm \
        -v "${PROJECT_DIR}/certbot/conf:${CERT_PATH}" \
        -v "${PROJECT_DIR}/certbot/www:${WEBROOT_PATH}" \
        "$CERTBOT_IMAGE" \
        renew \
        --webroot \
        --webroot-path="${WEBROOT_PATH}" \
        --quiet

    local RENEW_EXIT=$?

    if [ $RENEW_EXIT -eq 0 ]; then
        # 检查是否有更新
        if docker run --rm \
            -v "${PROJECT_DIR}/certbot/conf:${CERT_PATH}" \
            "$CERTBOT_IMAGE" \
            certificates 2>/dev/null | grep -q "VALID"; then
            log_info "✅ 证书有效，无需续期"
        fi

        # 重载 nginx 使新证书生效
        if docker ps --format '{{.Names}}' | grep -q 'tianlian-nginx'; then
            log_info "重载 Nginx 配置..."
            docker exec tianlian-nginx nginx -s reload 2>/dev/null || \
            docker compose -f "${PROJECT_DIR}/docker-compose.yml" restart nginx
            log_info "✅ Nginx 已重载"
        fi
    else
        log_warn "证书续期未完成 (可能在有效期内)"
    fi
}

# ============ 查看证书状态 ============
status_cert() {
    if [ ! -d "${PROJECT_DIR}/certbot/conf/live" ]; then
        log_warn "未找到已申请的证书"
        return 0
    fi

    log_info "证书状态:"
    docker run --rm \
        -v "${PROJECT_DIR}/certbot/conf:${CERT_PATH}" \
        "$CERTBOT_IMAGE" \
        certificates
}

# ============ 安装 cronjob ============
install_cron() {
    local CRON_JOB="0 3 * * * cd ${PROJECT_DIR} && ${SCRIPT_DIR}/certbot-setup.sh renew >> /var/log/certbot-cron.log 2>&1"

    log_info "安装自动续期 cron 任务 (每日凌晨3点)..."

    # 检查是否已存在
    if crontab -l 2>/dev/null | grep -q "certbot-setup.sh"; then
        log_warn "certbot cron 已存在，跳过安装"
        return 0
    fi

    (crontab -l 2>/dev/null || true; echo "$CRON_JOB") | crontab -
    log_info "✅ cron 已安装"
    log_info "当前 crontab:"
    crontab -l | grep certbot
}

# ============ 主入口 ============
COMMAND="${1:-}"

case "$COMMAND" in
    init)
        init_cert "${2:-}" "${3:-}"
        ;;
    init-wildcard)
        init_wildcard_cert "${2:-}" "${3:-}"
        ;;
    renew)
        renew_cert
        ;;
    status)
        status_cert
        ;;
    install-cron)
        install_cron
        ;;
    *)
        echo "天链V3 - HTTPS 证书管理工具"
        echo ""
        echo "用法: $0 <命令> [参数]"
        echo ""
        echo "命令:"
        echo "  init <域名> <邮箱>      申请新证书 (HTTP webroot 验证)"
        echo "  init-wildcard <域名> <邮箱>  申请通配符证书 (DNS 验证)"
        echo "  renew                  检查并续期证书 (适合 cron)"
        echo "  status                 查看证书状态"
        echo "  install-cron           安装自动续期 cron 任务"
        echo ""
        echo "示例:"
        echo "  $0 init tianlian.example.com admin@example.com"
        echo "  $0 renew"
        exit 0
        ;;
esac
