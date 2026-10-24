#!/bin/bash
# 天链V3 API冒烟测试 — 检查所有端点可达性
HOST="${1:-http://demo.example.com}"
FAIL=0; TOTAL=0

check() { TOTAL=$((TOTAL+1)); code=$(curl -m5 -so /dev/null -w "%{http_code}" "$HOST$1" 2>/dev/null); if [ "$code" = "200" ]; then echo "✅ $1 → $code"; else echo "❌ $1 → $code"; FAIL=$((FAIL+1)); fi; }
check_auth() { TOTAL=$((TOTAL+1)); code=$(curl -m5 -so /dev/null -w "%{http_code}" "$HOST$1" 2>/dev/null); case $code in 200|401) echo "✅ $1 → $code";; *) echo "❌ $1 → $code"; FAIL=$((FAIL+1));; esac; }

echo "=== 天链V3 API 冒烟测试 ==="
echo ""

# Public endpoints（enforce_auth 白名单，见 backend app.api.v1.auth.is_public_path）
check "/api/v1/health"
check_auth "/api/v1/knowledge"

# Auth-protected (200=ok, 401=expected) — teams/engineers 自 e132f8147 全局认证强制后不再公开
for ep in teams engineers users stations devices alarms "work-orders" "alarm-rules" "maintenance-records" roles gateways "report-mgmt"; do
  check_auth "/api/v1/$ep"
done

# POST-only
check_auth_post() { TOTAL=$((TOTAL+1)); code=$(curl -m5 -X POST -so /dev/null -w "%{http_code}" "$HOST$1" 2>/dev/null); case $code in 200|401|422) echo "✅ $1 → $code";; *) echo "❌ $1 → $code"; FAIL=$((FAIL+1));; esac; }

check_auth_post "/api/v1/auth/login"

echo ""
echo "---"
echo "结果: $((TOTAL-FAIL))/$TOTAL 通过"
[ $FAIL -gt 0 ] && echo "⚠️  $FAIL 个端点异常" || echo "✅ 全部正常"
exit $FAIL
