#!/bin/bash
# ─── 天链V3 HTTPS自签名证书生成 ───
# 适用于纯IP场景（如demo.example.com）

set -euo pipefail

HOST="${1:-demo.example.com}"
SSL_DIR="/etc/nginx/ssl"

echo "📦 生成自签名 HTTPS 证书: $HOST"
echo ""

# 1. 创建目录
mkdir -p "$SSL_DIR"

# 2. 生成CA密钥
openssl genrsa -out "$SSL_DIR/ca.key" 2048 2>/dev/null
openssl req -x509 -new -nodes -key "$SSL_DIR/ca.key" -sha256 -days 3650 \
  -out "$SSL_DIR/ca.crt" \
  -subj "/CN=TianLianCA"

# 3. 生成服务器密钥
openssl genrsa -out "$SSL_DIR/tianlian.key" 2048 2>/dev/null

# 4. 生成证书签名请求
openssl req -new -key "$SSL_DIR/tianlian.key" \
  -out "$SSL_DIR/tianlian.csr" \
  -subj "/CN=$HOST" \
  -addext "subjectAltName=IP:$HOST"

# 5. 用CA签名
openssl x509 -req -in "$SSL_DIR/tianlian.csr" \
  -CA "$SSL_DIR/ca.crt" -CAkey "$SSL_DIR/ca.key" -CAcreateserial \
  -out "$SSL_DIR/tianlian.crt" -days 365 -sha256

# 6. 设置权限
chmod 600 "$SSL_DIR/tianlian.key"
chmod 644 "$SSL_DIR/tianlian.crt"

echo "✅ 证书生成完成!"
echo "   证书: $SSL_DIR/tianlian.crt"
echo "   密钥: $SSL_DIR/tianlian.key"
echo ""
echo "⚠️  浏览器会显示不安全（自签名证书特性）"
echo "   将CA证书导入信任列表即可消除警告:"
echo "   CA证书: $SSL_DIR/ca.crt"
echo ""

# 7. 检查nginx配置是否需要更新 HTTPS 块
NGINX_CONF="/etc/nginx/nginx.conf"
if grep -q "listen 443 ssl" "$NGINX_CONF" 2>/dev/null; then
  echo "✅ Nginx 已配置 HTTPS"
else
  echo "⚠️  Nginx 需要添加 HTTPS 配置，请编辑: $NGINX_CONF"
  echo ""
  echo "示例配置:"
  echo 'server {'
  echo '    listen 443 ssl http2;'
  echo "    server_name $HOST;"
  echo '    ssl_certificate /etc/nginx/ssl/tianlian.crt;'
  echo '    ssl_certificate_key /etc/nginx/ssl/tianlian.key;'
  echo '    ...'
  echo '}'
fi
