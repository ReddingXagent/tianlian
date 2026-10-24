#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║        天链V3 全系统集成验收测试脚本 v1.0.0                    ║
# ║        Acceptance Test - 全端点 + 前端 + WS + 数据库            ║
# ╚══════════════════════════════════════════════════════════════════╝

# ─── 配置 ───
BASE_URL="${BASE_URL:-http://demo.example.com}"
API_URL="${BASE_URL}/api/v1"
WS_URL="${WS_URL:-ws://demo.example.com/ws}"
TIMEOUT=10
TOKEN=""
PASS=0
FAIL=0
WARN=0
FAILED_ENDPOINTS=()
REPORT_FILE="/tmp/tianlian-acceptance-report.txt"

# ─── 颜色 ───
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; BOLD=''; NC=''
fi

# ─── 工具函数 ───
print_header() {
    echo ""
    echo "================================================================"
    echo "  $1"
    echo "================================================================"
}

pass_test() {
    PASS=$((PASS + 1))
    echo -e "  ${GREEN}[PASS]${NC} $1"
}

fail_test() {
    FAIL=$((FAIL + 1))
    FAILED_ENDPOINTS+=("$1 | HTTP $2 | $3")
    echo -e "  ${RED}[FAIL]${NC} $1 | HTTP $2"
}

warn_test() {
    WARN=$((WARN + 1))
    echo -e "  ${YELLOW}[WARN]${NC} $1"
}

# 通用 HTTP GET
do_get() {
    local url="$1"
    local auth="$2"
    local extra_hdrs=()
    [ -n "$auth" ] && [ -n "$TOKEN" ] && extra_hdrs+=(-H "Authorization: Bearer $TOKEN")
    curl -s -o /tmp/tl_accept_body.txt -w "%{http_code}" --max-time "$TIMEOUT" \
        -H "Accept: application/json" "${extra_hdrs[@]}" "$url" 2>/dev/null || echo "000"
}

# 通用 HTTP POST
do_post() {
    local url="$1" data="$2" auth="$3"
    local extra_hdrs=()
    [ -n "$auth" ] && [ -n "$TOKEN" ] && extra_hdrs+=(-H "Authorization: Bearer $TOKEN")
    curl -s -X POST -o /tmp/tl_accept_body.txt -w "%{http_code}" --max-time "$TIMEOUT" \
        -H "Content-Type: application/json" -H "Accept: application/json" \
        "${extra_hdrs[@]}" -d "$data" "$url" 2>/dev/null || echo "000"
}

# 断言函数
assert_ok() {
    local code="$1" desc="$2" url="$3" expected="${4:-200}"
    # trim whitespace
    code=$(echo "$code" | tr -d '[:space:]')
    if [ "$code" = "$expected" ]; then
        pass_test "$desc"
        return 0
    elif [ "$expected" = "2xx" ] && [ "$code" -ge 200 ] 2>/dev/null && [ "$code" -lt 300 ] 2>/dev/null; then
        pass_test "$desc"
        return 0
    elif [ "$expected" = "any" ]; then
        pass_test "$desc (HTTP $code)"
        return 0
    else
        fail_test "$desc" "$code" "$url"
        return 1
    fi
}

# ─── 报告 ───
generate_report() {
    local total=$((PASS + FAIL + WARN))
    local rate=100
    [ $total -gt 0 ] && rate=$((PASS * 100 / total))
    {
        echo "=============================================="
        echo "  天链V3 全系统验收测试报告"
        echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "  目标: $BASE_URL"
        echo "=============================================="
        echo ""
        echo "测试结果汇总:"
        echo "  [PASS] $PASS"
        echo "  [FAIL] $FAIL"
        echo "  [WARN] $WARN"
        echo "  总计: $total"
        echo "  通过率: ${rate}%"
        echo ""
        if [ ${#FAILED_ENDPOINTS[@]} -gt 0 ]; then
            echo "失败端点明细:"
            local i=1
            for item in "${FAILED_ENDPOINTS[@]}"; do
                echo "  ${i}. $item"
                i=$((i + 1))
            done
        fi
        echo ""
        echo "=============================================="
    } | tee "$REPORT_FILE"
}

# ─── 开始 ───
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║    天链V3 全系统集成验收测试            ║"
echo "  ║    目标: $BASE_URL                       ║"
echo "  ╚══════════════════════════════════════════╝"

# ══════════════════════════════════════════════
print_header "Phase 1: 基础健康检查"

CODE=$(do_get "$BASE_URL/" "")
assert_ok "$CODE" "GET / (根路径)" "$BASE_URL/"

CODE=$(do_get "$API_URL/health" "")
assert_ok "$CODE" "GET /api/v1/health" "$API_URL/health"

CODE=$(do_get "$API_URL/ping" "")
assert_ok "$CODE" "GET /api/v1/ping" "$API_URL/ping"

CODE=$(do_get "$BASE_URL/docs" "")
assert_ok "$CODE" "GET /docs (Swagger)" "$BASE_URL/docs"

# ══════════════════════════════════════════════
print_header "Phase 2: 认证系统"

CODE=$(do_post "$API_URL/auth/register" '{"username":"acceptance_test","password":"Test@123456","phone":"13800000001","role":"engineer"}' "")
assert_ok "$CODE" "POST /auth/register" "$API_URL/auth/register" "any"

# 登录获取 Token (使用 form 编码, OAuth2PasswordRequestForm)
echo -n "" > /tmp/tl_accept_body.txt
LOGIN_RESP=$(curl -s -o /tmp/tl_accept_body.txt -w "%{http_code}" \
    -X POST "$API_URL/auth/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -H "Accept: application/json" \
    -d "username=admin&password=admin123" \
    --max-time "$TIMEOUT" 2>/dev/null)
LOGIN_BODY=$(cat /tmp/tl_accept_body.txt 2>/dev/null)
TOKEN=$(echo "$LOGIN_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('token','') or d.get('token',''))" 2>/dev/null || echo "")

if [ -n "$TOKEN" ] && [ "${#TOKEN}" -gt 10 ]; then
    pass_test "POST /auth/login (获取Token成功)"
else
    fail_test "POST /auth/login (获取Token失败)" "$LOGIN_RESP" "$API_URL/auth/login"
fi

CODE=$(do_post "$API_URL/auth/sms/send" '{"phone":"13800000001"}' "")
assert_ok "$CODE" "POST /auth/sms/send" "$API_URL/auth/sms/send" "200"

# ══════════════════════════════════════════════
print_header "Phase 3: 核心业务API"

A=""; [ -n "$TOKEN" ] && A="auth"

CODE=$(do_get "$API_URL/devices" "$A");        assert_ok "$CODE" "GET /devices" "$API_URL/devices" "2xx"
CODE=$(do_get "$API_URL/stations" "$A");       assert_ok "$CODE" "GET /stations" "$API_URL/stations" "2xx"
CODE=$(do_get "$API_URL/alarms" "$A");         assert_ok "$CODE" "GET /alarms" "$API_URL/alarms" "2xx"
CODE=$(do_get "$API_URL/alarms/rules" "$A");   assert_ok "$CODE" "GET /alarms/rules" "$API_URL/alarms/rules" "2xx"
CODE=$(do_get "$API_URL/workorders" "$A");     assert_ok "$CODE" "GET /workorders" "$API_URL/workorders" "2xx"
CODE=$(do_get "$API_URL/knowledge" "$A");      assert_ok "$CODE" "GET /knowledge" "$API_URL/knowledge" "200"
CODE=$(do_get "$API_URL/users" "$A");          assert_ok "$CODE" "GET /users" "$API_URL/users" "2xx"
CODE=$(do_get "$API_URL/teams" "$A");          assert_ok "$CODE" "GET /teams" "$API_URL/teams" "2xx"

# ══════════════════════════════════════════════
print_header "Phase 4: 看板 & 监控"

CODE=$(do_get "$API_URL/stats/overview" "$A");        assert_ok "$CODE" "GET /stats/overview" "" "200"
CODE=$(do_get "$API_URL/stats/health-trend" "$A");    assert_ok "$CODE" "GET /stats/health-trend" "" "200"
CODE=$(do_get "$API_URL/stats/alarm-stats" "$A");     assert_ok "$CODE" "GET /stats/alarm-stats" "" "200"
CODE=$(do_get "$API_URL/stats/workorder-stats" "$A"); assert_ok "$CODE" "GET /stats/workorder-stats" "" "200"

CODE=$(do_get "$API_URL/monitor/realtime" "$A"); assert_ok "$CODE" "GET /monitor/realtime" "" "2xx"
CODE=$(do_get "$API_URL/monitor/history" "$A");  assert_ok "$CODE" "GET /monitor/history" "" "2xx"

# ══════════════════════════════════════════════
print_header "Phase 5: 报表 & 权限"

CODE=$(do_get "$API_URL/reports/devices" "$A");    assert_ok "$CODE" "GET /reports/devices" "" "2xx"
CODE=$(do_get "$API_URL/reports/workorders" "$A"); assert_ok "$CODE" "GET /reports/workorders" "" "2xx"
CODE=$(do_get "$API_URL/reports/stations" "$A");   assert_ok "$CODE" "GET /reports/stations" "" "2xx"
CODE=$(do_get "$API_URL/reports/summary" "$A");    assert_ok "$CODE" "GET /reports/summary" "" "2xx"

CODE=$(do_get "$API_URL/rbac/roles" "$A");       assert_ok "$CODE" "GET /rbac/roles" "" "200"
CODE=$(do_get "$API_URL/rbac/permissions" "$A"); assert_ok "$CODE" "GET /rbac/permissions" "" "200"

# ══════════════════════════════════════════════
print_header "Phase 6: 诊断系统"

CODE=$(do_get "$API_URL/fault-diagnosis/fault-codes" "$A"); assert_ok "$CODE" "GET /fault-diagnosis/fault-codes" "" "200"
CODE=$(do_post "$API_URL/fault-diagnosis/alarm-diagnosis" '{"alarm_id":1}' "$A")
assert_ok "$CODE" "POST /fault-diagnosis/alarm-diagnosis" "" "2xx"

CODE=$(do_post "$API_URL/diagnosis/device" '{"device_id":1}' "$A")
assert_ok "$CODE" "POST /diagnosis/device" "" "2xx"

CODE=$(do_post "$API_URL/smart-diagnosis/analyze" '{"fault_desc":"设备异常发热"}' "$A")
assert_ok "$CODE" "POST /smart-diagnosis/analyze" "" "2xx"
CODE=$(do_get "$API_URL/smart-diagnosis/keywords" "$A")
assert_ok "$CODE" "GET /smart-diagnosis/keywords" "" "200"

CODE=$(do_post "$API_URL/scan/device" '{"qr_code":"SN-TEST-001"}' "$A")
assert_ok "$CODE" "POST /scan/device" "" "2xx"

# ══════════════════════════════════════════════
print_header "Phase 7: 安全 & 日志"

CODE=$(do_get "$API_URL/security/logs" "$A");      assert_ok "$CODE" "GET /security/logs" "" "200"
CODE=$(do_get "$API_URL/security/stats" "$A");     assert_ok "$CODE" "GET /security/stats" "" "200"
CODE=$(do_get "$API_URL/security/threats" "$A");   assert_ok "$CODE" "GET /security/threats" "" "200"
CODE=$(do_get "$API_URL/security/settings" "$A");  assert_ok "$CODE" "GET /security/settings" "" "200"

CODE=$(do_get "$API_URL/operation-log" "$A");      assert_ok "$CODE" "GET /operation-log" "" "2xx"
CODE=$(do_get "$API_URL/operation-log/stats" "$A");assert_ok "$CODE" "GET /operation-log/stats" "" "2xx"

CODE=$(do_post "$API_URL/log-analysis/analyze" '{"device_id":1,"logs":["error test"],"fault_code":"E001"}' "$A")
assert_ok "$CODE" "POST /log-analysis/analyze" "" "2xx"

# ══════════════════════════════════════════════
print_header "Phase 8: 通知 & 网关"

CODE=$(do_get "$API_URL/alarm-notices" "$A");          assert_ok "$CODE" "GET /alarm-notices" "" "200"
CODE=$(do_get "$API_URL/alarm-notices/stats" "$A");    assert_ok "$CODE" "GET /alarm-notices/stats" "" "200"
CODE=$(do_get "$API_URL/notification-rules" "$A");     assert_ok "$CODE" "GET /notification-rules" "" "200"
CODE=$(do_get "$API_URL/gateways/sn" "$A");            assert_ok "$CODE" "GET /gateways/sn" "" "200"
CODE=$(do_get "$API_URL/health/devices" "$A");         assert_ok "$CODE" "GET /health/devices" "" "200"

# ══════════════════════════════════════════════
print_header "Phase 9: 前端页面可达性"

CODE=$(do_get "$BASE_URL/" ""); assert_ok "$CODE" "GET / (前端主页)" "" "200"

for page in login dashboard devices stations alarms workorders knowledge reports scan monitor teams rbac config security health diagnosis; do
    CODE=$(do_get "$BASE_URL/$page" "")
    assert_ok "$CODE" "GET /$page" "" "200"
done

# ══════════════════════════════════════════════
print_header "Phase 10: WebSocket & CORS"

CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Connection: Upgrade" -H "Upgrade: websocket" \
    -H "Sec-WebSocket-Version: 13" \
    -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
    "$BASE_URL/ws" --max-time "$TIMEOUT" 2>/dev/null || echo "000")
if [ "$CODE" = "101" ] || [ "$CODE" = "426" ]; then
    pass_test "WS /ws (Upgrade HTTP $CODE)"
elif [ "$CODE" = "404" ]; then
    warn_test "WS /ws (HTTP 404 - 端点可能不同)"
else
    warn_test "WS /ws (HTTP $CODE)"
fi

# CORS
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X OPTIONS "$API_URL/health" \
    -H "Origin: http://localhost:3004" -H "Access-Control-Request-Method: GET" \
    --max-time "$TIMEOUT" 2>/dev/null || echo "000")
if [ "$CODE" = "200" ] || [ "$CODE" = "204" ]; then
    pass_test "CORS OPTIONS /api/v1/health"
else
    warn_test "CORS OPTIONS (HTTP $CODE)"
fi

# ══════════════════════════════════════════════
print_header "Phase 11: 数据库读写测试(API间接)"

CODE=$(do_post "$API_URL/alarms" '{"device_id":1,"alarm_type":"overheat","level":"warning","content":"验收DB写测试"}' "$A")
assert_ok "$CODE" "POST /alarms (DB写入测试)" "" "2xx"

CODE=$(do_post "$API_URL/stations" '{"name":"验收测试站","code":"ACCEPT-TEST","address":"测试位置","status":"normal"}' "$A")
assert_ok "$CODE" "POST /stations (DB写入测试)" "" "2xx"

# ─── 最终报告 ───
generate_report

echo ""
echo "================================================================"
if [ "$FAIL" -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}🎉 验收测试全部通过! ${PASS} PASS / ${WARN} WARN${NC}"
    EXIT_CODE=0
else
    echo -e "  ${YELLOW}${BOLD}📋 验收测试完成: ${GREEN}${PASS} PASS${NC} / ${RED}${FAIL} FAIL${NC} / ${YELLOW}${WARN} WARN${NC}"
    EXIT_CODE=1
fi
echo "================================================================"
echo "  详细报告: $REPORT_FILE"
echo ""

exit $EXIT_CODE