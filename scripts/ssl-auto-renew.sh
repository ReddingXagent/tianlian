#!/bin/bash
# ─── 天链V3 SSL 自动续期守护脚本 (Phase9) ───
# 功能:
#   1. 扫描所有已注册的域名证书
#   2. 检查过期时间，提前 N 天自动续期
#   3. 续期后自动重载 Nginx
#   4. 发送通知 (IM/钉钉 webhook)
#   5. 记录续期日志
#
# 用法:
#   bash scripts/ssl-auto-renew.sh              # 执行续期检查
#   bash scripts/ssl-auto-renew.sh --dry-run    # 模拟运行（不实际续期）
#   bash scripts/ssl-auto-renew.sh --install-cron # 安装 crontab 任务
#
# Cron 安装:
#   每天凌晨 2:00 和 14:00 各检查一次
#   0 2,14 * * * root bash /opt/tianlian-cloud/scripts/ssl-auto-renew.sh >> /var/log/tianlian-ssl-renew.log 2>&1

set -euo pipefail

# ================= 配置 =================
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="/etc/letsencrypt/live"
LOG_FILE="/var/log/tianlian-ssl-renew.log"
NGINX_SSL_CONF="/etc/nginx/conf.d/default.conf"
RENEW_DAYS_THRESHOLD=30               # 默认提前 30 天续期
DRY_RUN=false
INSTALL_CRON=false
NOTIFY_WEBHOOK="${SSL_NOTIFY_WEBHOOK:-}"  # IM/钉钉 webhook URL

# 颜色
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()   { echo -e "${GREEN}[✓]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "${LOG_FILE}"; }
warn()  { echo -e "${YELLOW}[!]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "${LOG_FILE}"; }
err()   { echo -e "${RED}[✗]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "${LOG_FILE}" >&2; }
info()  { echo -e "${CYAN}[→]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "${LOG_FILE}"; }

# 确保日志目录存在
mkdir -p "$(dirname "${LOG_FILE}")" 2>/dev/null || true
touch "${LOG_FILE}" 2>/dev/null || true

# ================= 参数解析 =================
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)        DRY_RUN=true; shift ;;
        --install-cron)   INSTALL_CRON=true; shift ;;
        --threshold)
            if [ -z "${2:-}" ] || ! [[ "$2" =~ ^[0-9]+$ ]]; then
                echo "错误: --threshold 需要一个正整数参数" >&2
                exit 1
            fi
            RENEW_DAYS_THRESHOLD="$2"; shift 2
            ;;
        --help|-h)
            echo "用法: bash scripts/ssl-auto-renew.sh [选项]"
            echo "  --dry-run         模拟运行，不实际续期"
            echo "  --install-cron    安装 crontab 任务"
            echo "  --threshold <N>   提前 N 天续期 (默认 30)"
            exit 0
            ;;
        *)
            echo "未知参数: $1 (使用 --help 查看用法)" >&2
            exit 1
            ;;
    esac
done

# ================= 安装 Cron =================
if [ "$INSTALL_CRON" = true ]; then
    info "安装 SSL 自动续期 cron ..."
    cron_line="0 2,14 * * * root bash ${PROJECT_DIR}/scripts/ssl-auto-renew.sh >> ${LOG_FILE} 2>&1"
    cron_file="/etc/cron.d/tianlian-ssl-renew"
    
    if [ "$DRY_RUN" = true ]; then
        info "[DRY-RUN] 将创建 cron: ${cron_line}"
        exit 0
    fi
    
    echo "# 天链V3 SSL 自动续期 - 每天 02:00 和 14:00" | sudo tee "${cron_file}" > /dev/null
    echo "${cron_line}" | sudo tee -a "${cron_file}" > /dev/null
    sudo chmod 644 "${cron_file}"
    log "Cron 已安装: ${cron_file}"
    exit 0
fi

# ================= 前置检查 =================
if ! command -v certbot &>/dev/null; then
    warn "certbot 未安装，无法执行 SSL 续期"
    info "安装方法: apt-get install certbot python3-certbot-nginx"
    exit 1
fi

# 检查 certbot 是否有可用证书
cert_count=$(sudo ls -d "${CERT_DIR}/"*/ 2>/dev/null | wc -l || echo "0")
if [ "$cert_count" -eq 0 ]; then
    warn "没有找到任何 Let's Encrypt 证书"
    info "请先使用 scripts/ssl-setup.sh 申请第一个证书"
    exit 0
fi

info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "天链V3 SSL 自动续期检查"
info "证书目录: ${CERT_DIR}"
info "续期阈值: 提前 ${RENEW_DAYS_THRESHOLD} 天"
if [ "$DRY_RUN" = true ]; then
    warn "*** DRY-RUN 模式 ***"
fi
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ================= 扫描 & 续期 =================
renewed=0
skipped=0
failed=0
renewed_domains=""

for cert_path in "${CERT_DIR}/"*/; do
    domain=$(basename "${cert_path}")
    fullchain="${cert_path}fullchain.pem"
    
    if [ ! -f "${fullchain}" ]; then
        warn "证书文件不存在: ${fullchain}, 跳过"
        continue
    fi
    
    # 解析过期时间
    expire_date=$(openssl x509 -enddate -noout -in "${fullchain}" 2>/dev/null | cut -d= -f2)
    if [ -z "${expire_date}" ]; then
        err "无法解析证书过期时间: ${domain}"
        continue
    fi
    
    expire_epoch=$(date -d "${expire_date}" +%s 2>/dev/null || date -j -f "%b %d %H:%M:%S %Y %Z" "${expire_date}" +%s 2>/dev/null)
    now_epoch=$(date +%s)
    days_left=$(( (expire_epoch - now_epoch) / 86400 ))
    
    # 签发机构
    issuer=$(openssl x509 -issuer -noout -in "${fullchain}" 2>/dev/null | sed 's/issuer=//' | head -c 80)
    
    info "证书: ${domain}"
    info "  签发: ${issuer}"
    info "  过期: ${expire_date}"
    info "  剩余: ${days_left} 天"
    
    if [ "${days_left}" -le 0 ]; then
        err "  ❌ 证书已过期!"
        failed=$((failed + 1))
        # 已过期也尝试续期
    elif [ "${days_left}" -le "${RENEW_DAYS_THRESHOLD}" ]; then
        # 需要续期
        if [ "$DRY_RUN" = true ]; then
            warn "  [DRY-RUN] 将续期 (剩余 ${days_left} 天)"
            renewed=$((renewed + 1))
            renewed_domains="${renewed_domains} ${domain}"
            continue
        fi
        
        info "  🔄 开始续期..."
        # 用退出码判定成败 (certbot --quiet 成功时输出为空, 不能 grep 输出)
        renew_output=$(sudo certbot renew --cert-name "${domain}" --post-hook 'nginx -s reload' 2>&1) \
            && renew_rc=0 || renew_rc=$?

        if [ "${renew_rc}" -eq 0 ]; then
            log "  ✅ 续期成功: ${domain}"
            [ -n "${renew_output}" ] && info "  certbot 输出: ${renew_output}"
            renewed=$((renewed + 1))
            renewed_domains="${renewed_domains} ${domain}"
        else
            err "  ❌ 续期失败: ${domain} (exit=${renew_rc})"
            err "  ${renew_output}"
            failed=$((failed + 1))
        fi
    else
        info "  ✅ 正常 (剩余 ${days_left} 天 > ${RENEW_DAYS_THRESHOLD} 天阈值)"
        skipped=$((skipped + 1))
    fi
done

# ================= 汇总 =================
echo ""
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "续期检查完成"
info "  需续期/已续期: ${renewed}"
info "  跳过(正常):   ${skipped}"
info "  失败/过期:    ${failed}"
if [ -n "${renewed_domains}" ]; then
    info "  已续期域名:   ${renewed_domains}"
fi
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ================= 通知 =================
send_notification() {
    local msg="$1"
    if [ -z "${NOTIFY_WEBHOOK}" ]; then
        return
    fi
    
    # IM Webhook 格式
    curl -s -X POST "${NOTIFY_WEBHOOK}" \
        -H "Content-Type: application/json" \
        -d "{
            \"msg_type\": \"text\",
            \"content\": {
                \"text\": \"[天链V3] SSL 证书续期报告\\n${msg}\"
            }
        }" || warn "通知发送失败"
}

if [ "${renewed}" -gt 0 ] || [ "${failed}" -gt 0 ]; then
    notify_msg="自动续期检查完成\n  已续期: ${renewed} 个\n  失败: ${failed} 个\n  跳过: ${skipped} 个\n  域名: ${renewed_domains}"
    send_notification "${notify_msg}"
fi

# ================= 重载 Nginx =================
if [ "${renewed}" -gt 0 ] && [ "$DRY_RUN" = false ]; then
    info "重载 Nginx 使新证书生效..."
    sudo nginx -t 2>&1 | tee -a "${LOG_FILE}" && \
        sudo nginx -s reload 2>&1 | tee -a "${LOG_FILE}" && \
        log "Nginx 重载成功" || \
        err "Nginx 重载失败，请手动检查"
fi

exit 0
