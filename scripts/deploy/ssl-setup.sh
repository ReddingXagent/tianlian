#!/bin/bash
# ─── 天链V3 SSL 证书一站式配置 ───
# 功能:
#   - 自签名证书 (适用于IP/内网)
#   - Let's Encrypt (适用于域名)
#   - Docker Compose 集成
#   - 自动续期
#
# 用法:
#   自签名: ./scripts/deploy/ssl-setup.sh --self-sign demo.example.com
#   Let's Encrypt: ./scripts/deploy/ssl-setup.sh --lets-encrypt tianlian.example.com
#   仅生成自签名: ./scripts/deploy/ssl-setup.sh --generate-certs demo.example.com

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

MODE="${1:-}"
TARGET="${2:-}"

show_usage() {
  echo "用法: $0 <mode> [target]"
  echo ""
  echo "模式:"
  echo "  --self-sign <host>       生成自签名证书 (适用于IP/内网)"
  echo "  --lets-encrypt <domain>  申请 Let's Encrypt 证书 (适用于公网域名)"
  echo "  --generate-certs <host>  仅生成自签名证书文件（不修改nginx配置）"
  echo "  --check                  检查证书状态"
  echo ""
  echo "示例:"
  echo "  $0 --self-sign demo.example.com"
  echo "  $0 --lets-encrypt tianlian.example.com"
  echo "  $0 --generate-certs localhost"
}

if [[ -z "$MODE" ]]; then
  show_usage
  exit 1
fi

check_deps() {
  if ! command -v openssl &>/dev/null; then
    log_error "openssl 未安装"
    exit 1
  fi
}

generate_self_signed() {
  local host="$1"
  local out_dir="${2:-./certbot/conf/live/tianlian}"

  mkdir -p "$out_dir"

  log_info "生成自签名证书: $host"

  openssl genrsa -out "$out_dir/ca.key" 2048 2>/dev/null
  openssl req -x509 -new -nodes \
    -key "$out_dir/ca.key" \
    -sha256 -days 3650 \
    -out "$out_dir/ca.crt" \
    -subj "/CN=TianLianV3-CA" 2>/dev/null

  openssl genrsa -out "$out_dir/privkey.pem" 2048 2>/dev/null

  if [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    openssl req -new \
      -key "$out_dir/privkey.pem" \
      -out "$out_dir/tianlian.csr" \
      -subj "/CN=$host" \
      -addext "subjectAltName=IP:$host" 2>/dev/null
  else
    openssl req -new \
      -key "$out_dir/privkey.pem" \
      -out "$out_dir/tianlian.csr" \
      -subj "/CN=$host" \
      -addext "subjectAltName=DNS:$host" 2>/dev/null
  fi

  openssl x509 -req \
    -in "$out_dir/tianlian.csr" \
    -CA "$out_dir/ca.crt" \
    -CAkey "$out_dir/ca.key" \
    -CAcreateserial \
    -out "$out_dir/fullchain.pem" \
    -days 365 -sha256 2>/dev/null

  ln -sf fullchain.pem "$out_dir/cert.pem" 2>/dev/null || true
  ln -sf fullchain.pem "$out_dir/chain.pem" 2>/dev/null || true

  chmod 600 "$out_dir/privkey.pem"
  chmod 644 "$out_dir/fullchain.pem"

  log_info "证书生成完成: $out_dir/"
  log_info "  fullchain.pem  完整证书链"
  log_info "  privkey.pem    私钥"
  log_info "  ca.crt         CA证书（导入浏览器可消除警告）"
}

request_lets_encrypt() {
  local domain="$1"

  if [[ "$domain" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    log_error "Let's Encrypt 不支持IP，请使用域名"
    echo "  使用自签名: $0 --self-sign $domain"
    exit 1
  fi

  log_info "申请 Let's Encrypt 证书: $domain"

  if ! command -v certbot &>/dev/null; then
    log_info "安装 certbot..."
    if command -v apt-get &>/dev/null; then
      sudo apt-get update -qq && sudo apt-get install -y -qq certbot python3-certbot-nginx
    elif command -v yum &>/dev/null; then
      sudo yum install -y certbot python3-certbot-nginx
    else
      pip install certbot certbot-nginx
    fi
  fi

  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q tianlian-nginx; then
    log_info "停止 nginx 容器 (certbot standalone)..."
    docker stop tianlian-nginx 2>/dev/null || true
  fi

  sudo certbot certonly --standalone \
    --non-interactive --agree-tos \
    --email "admin@${domain}" \
    -d "$domain" \
    --preferred-challenges http \
    || {
      log_error "证书申请失败"
      docker start tianlian-nginx 2>/dev/null || true
      exit 1
    }

  local le_live="/etc/letsencrypt/live/$domain"
  mkdir -p ./certbot/conf/live/tianlian/
  sudo cp "$le_live/fullchain.pem" ./certbot/conf/live/tianlian/fullchain.pem
  sudo cp "$le_live/privkey.pem" ./certbot/conf/live/tianlian/privkey.pem
  sudo cp "$le_live/chain.pem" ./certbot/conf/live/tianlian/chain.pem
  sudo chown "$(whoami)" ./certbot/conf/live/tianlian/*.pem 2>/dev/null || true

  log_info "Let's Encrypt 证书申请成功!"
  log_info "有效期: 90天"

  if ! crontab -l 2>/dev/null | grep -q "certbot renew"; then
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'cp /etc/letsencrypt/live/$domain/fullchain.pem ./certbot/conf/live/tianlian/ && docker restart tianlian-nginx 2>/dev/null || true'") | crontab -
    log_info "自动续期已配置 (每日 3:00)"
  fi

  docker start tianlian-nginx 2>/dev/null || true
}

check_certs() {
  log_info "检查证书状态..."

  if [[ -f "./certbot/conf/live/tianlian/fullchain.pem" ]]; then
    local expiry
    expiry=$(openssl x509 -enddate -noout -in ./certbot/conf/live/tianlian/fullchain.pem 2>/dev/null | cut -d= -f2)
    local subject
    subject=$(openssl x509 -subject -noout -in ./certbot/conf/live/tianlian/fullchain.pem 2>/dev/null | cut -d= -f2-)
    echo "  证书主题: $subject"
    echo "  过期时间: $expiry"

    local expiry_epoch
    expiry_epoch=$(date -jf "%b %d %T %Y %Z" "$expiry" +%s 2>/dev/null || date -d "$expiry" +%s 2>/dev/null || echo 0)
    local now_epoch=$(date +%s)
    local days_left=$(( (${expiry_epoch:-0} - now_epoch) / 86400 ))

    if [[ $days_left -lt 0 ]]; then
      log_error "证书已过期！"
    elif [[ $days_left -lt 30 ]]; then
      log_warn "证书将在 $days_left 天后过期"
    else
      log_info "证书有效，剩余 $days_left 天"
    fi
  else
    log_warn "未找到证书文件"
  fi

  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q tianlian-nginx; then
    log_info "nginx 容器运行中"
  else
    log_warn "nginx 容器未运行"
  fi
}

check_deps

case "$MODE" in
  --self-sign)
    if [[ -z "$TARGET" ]]; then
      log_error "请提供主机名或IP"
      exit 1
    fi
    generate_self_signed "$TARGET"
    check_certs
    ;;

  --lets-encrypt)
    if [[ -z "$TARGET" ]]; then
      log_error "请提供域名"
      exit 1
    fi
    request_lets_encrypt "$TARGET"
    check_certs
    ;;

  --generate-certs)
    if [[ -z "$TARGET" ]]; then
      TARGET="localhost"
    fi
    generate_self_signed "$TARGET"
    log_info "自签名证书已生成，请配置 nginx 使用"
    ;;

  --check)
    check_certs
    ;;

  *)
    show_usage
    exit 1
    ;;
esac

echo ""
log_info "Done."
