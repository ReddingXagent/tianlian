#!/usr/bin/env bash
# ─── 天链V3 SSL 证书配置脚本 (Let's Encrypt + certbot) ───
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }

# ================= 配置 =================
# 必须显式提供 (Let's Encrypt 不为 IP 发证; 无默认邮箱)
DOMAINS="${DOMAINS:-}"                             # 域名列表, 空格分隔: "example.com www.example.com"
EMAIL="${EMAIL:-}"                                 # Let's Encrypt 通知邮箱
CERT_DIR="/etc/letsencrypt/live"                  # 证书存储路径
NGINX_SSL_CONF="/etc/nginx/conf.d/default.conf"   # Nginx HTTPS 配置
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="${STAGING:-0}"                           # 1=使用 Let's Encrypt staging 环境测试

usage() {
    cat << 'EOF'
天链V3 SSL 证书配置 (Let's Encrypt + certbot)

用法: bash scripts/ssl-setup.sh [选项]

环境变量:
  DOMAINS    域名 (空格分隔), 必填 (Let's Encrypt 不为 IP 发证)
  EMAIL      Let's Encrypt 通知邮箱, 必填
  STAGING    设为 1 使用测试环境 (避免频率限制)

示例:
  # 申请证书
  DOMAINS="example.com www.example.com" EMAIL="admin@example.com" bash scripts/ssl-setup.sh

  # 先测试 (staging环境)
  STAGING=1 DOMAINS="example.com" bash scripts/ssl-setup.sh

  # 仅续期
  bash scripts/ssl-setup.sh --renew-only

  # 安装自动续期 cron
  bash scripts/ssl-setup.sh --install-cron
EOF
    exit 0
}

# ================= 参数 =================
case "${1:-}" in
    --help|-h)   usage ;;
    --renew-only) RENEW_ONLY=true ;;
    --install-cron) INSTALL_CRON=true ;;
    *) RENEW_ONLY=false; INSTALL_CRON=false ;;
esac

# 未显式提供 DOMAINS/EMAIL 时拒绝执行 (--renew-only/--install-cron/--help 不强制)
if [ "${RENEW_ONLY:-false}" = false ] && [ "${INSTALL_CRON:-false}" = false ]; then
    if [ -z "${DOMAINS}" ] || [ -z "${EMAIL}" ]; then
        err "缺少必填配置: DOMAINS 和 EMAIL 必须通过环境变量显式提供"
        err "  DOMAINS 不能是 IP (Let's Encrypt 不为 IP 发证)"
        err "示例: DOMAINS=\"youpengda.com\" EMAIL=\"admin@youpengda.com\" bash scripts/ssl-setup.sh"
        err "查看用法: bash scripts/ssl-setup.sh --help"
        exit 1
    fi
fi

# ================= 安装 certbot =================
install_certbot() {
    log "检查 certbot ..."
    if command -v certbot >/dev/null 2>&1; then
        log "certbot 已安装: $(certbot --version | head -1)"
        return 0
    fi

    log "安装 certbot ..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq certbot python3-certbot-nginx
    elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y epel-release
        sudo yum install -y certbot python3-certbot-nginx
    elif command -v apk >/dev/null 2>&1; then
        sudo apk add certbot certbot-nginx
    else
        err "无法自动安装 certbot, 请手动安装: https://certbot.eff.org/"
        exit 1
    fi
    log "certbot 安装完成"
}

# ================= 申请证书 =================
request_cert() {
    log "申请 SSL 证书..."

    local certbot_args=(
        certonly --nginx
        --non-interactive
        --agree-tos
        --email "${EMAIL}"
    )

    if [ "${STAGING}" = "1" ]; then
        certbot_args+=(--staging)
        warn "使用 staging 环境 (测试证书)"
    fi

    # 构建域名参数
    for domain in ${DOMAINS}; do
        certbot_args+=(-d "${domain}")
    done

    log "域名: ${DOMAINS}"
    log "执行 certbot (这可能需要几分钟)..."
    sudo certbot "${certbot_args[@]}" || {
        err "证书申请失败"
        echo ""
        echo "常见问题:"
        echo "  1. 域名必须正确解析到本机 IP"
        echo "  2. 80端口必须开放 (Let's Encrypt HTTP验证)"
        echo "  3. 如果失败, 可先用 STAGING=1 测试"
        echo ""
        echo "手动测试命令:"
        echo "  sudo certbot certonly --nginx -d ${DOMAINS%% *} --staging"
        exit 1
    }

    log "证书申请成功!"
    log "证书路径: ${CERT_DIR}/$(echo ${DOMAINS} | awk '{print $1}')/"
}

# ================= 部署 SSL Nginx 配置 =================
deploy_ssl_nginx() {
    local first_domain
    first_domain=$(echo "${DOMAINS}" | awk '{print $1}')

    log "部署 HTTPS Nginx 配置..."

    # 替换证书路径中的域名占位符
    if [ -f "${PROJECT_DIR}/nginx.ssl.conf" ]; then
        local ssl_conf="/tmp/nginx-ssl-${first_domain}.conf"
        cp "${PROJECT_DIR}/nginx.ssl.conf" "${ssl_conf}"

        # 替换域名占位符
        sed -i '' "s|\${DOMAIN}|${first_domain}|g" "${ssl_conf}" 2>/dev/null || \
            sed -i "s|\${DOMAIN}|${first_domain}|g" "${ssl_conf}"

        # 应用配置
        sudo cp "${ssl_conf}" "${NGINX_SSL_CONF}"
        rm -f "${ssl_conf}"
        log "SSL Nginx 配置已部署到: ${NGINX_SSL_CONF}"
    else
        warn "nginx.ssl.conf 不存在, 跳过 Nginx 配置部署"
    fi

    # 测试 Nginx 配置
    log "测试 Nginx 配置..."
    sudo nginx -t || {
        err "Nginx 配置错误, 请检查 ${NGINX_SSL_CONF}"
        exit 1
    }

    # 重载 Nginx
    log "重载 Nginx..."
    sudo nginx -s reload || sudo systemctl reload nginx

    log "HTTPS Nginx 配置已生效"
}

# ================= 自动续期 =================
setup_auto_renew() {
    log "配置自动续期..."

    # 创建 certbot 续期 cron (每天凌晨2点检查)
    local cron_line="0 2 * * * root certbot renew --quiet --post-hook 'nginx -s reload'"
    local cron_file="/etc/cron.d/certbot-renew"

    echo "${cron_line}" | sudo tee "${cron_file}" > /dev/null
    sudo chmod 644 "${cron_file}"
    log "自动续期 cron 已创建: ${cron_file}"

    # 立即测试续期
    log "测试续期 (dry-run)..."
    sudo certbot renew --dry-run || warn "dry-run 测试有警告 (可能正常)"
}

# ================= 仅续期 =================
do_renew() {
    log "检查证书续期..."
    sudo certbot renew --quiet --post-hook 'nginx -s reload'
    log "续期检查完成"
    sudo certbot certificates
}

# ================= 仅安装 Cron =================
do_install_cron() {
    setup_auto_renew
    log "Cron 安装完成"
}

# ================= 主流程 =================
main() {
    # 仅续期模式
    if "${RENEW_ONLY:-false}"; then
        do_renew
        exit 0
    fi

    # 仅安装 cron 模式
    if "${INSTALL_CRON:-false}"; then
        do_install_cron
        exit 0
    fi

    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "天链V3 SSL 配置 (Let's Encrypt)"
    log "域名: ${DOMAINS}"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    install_certbot
    request_cert
    deploy_ssl_nginx
    setup_auto_renew

    echo ""
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "SSL 配置完成!"
    log "  HTTPS: https://${DOMAINS%% *}"
    log "  证书路径: ${CERT_DIR}/${DOMAINS%% *}/"
    log "  续期 cron: 每天凌晨 2:00 自动检查"
    log ""
    log "验证 HTTPS: curl -I https://${DOMAINS%% *}"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

main "$@"