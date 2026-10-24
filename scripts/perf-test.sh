#!/usr/bin/env bash
# ============================================================================
# 天链V3 后端性能测试脚本
# 使用 Apache Bench (ab) 和 Python requests 进行多个并发级别测试
# ============================================================================
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
RESULT_DIR="$(cd "$(dirname "$0")/.." && pwd)/perf-results"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RESULT_FILE="${RESULT_DIR}/${TIMESTAMP}.json"

mkdir -p "$RESULT_DIR"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
title() { echo -e "\n${CYAN}═══════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}═══════════════════════════════════════════${NC}"; }

# 检查依赖
check_deps() {
    local missing=0
    
    if ! command -v ab &>/dev/null; then
        warn "ab (Apache Bench) 未安装，部分测试将使用Python替代"
        warn "macOS: brew install httpd  (自带 ab)"
        warn "Ubuntu: apt-get install apache2-utils"
    fi
    
    if ! python3 -c "import requests" &>/dev/null; then
        error "Python requests 库未安装，请执行: pip3 install requests"
        missing=1
    fi
    
    if [ "$missing" -eq 1 ]; then
        exit 1
    fi
}

# 获取登录Token
get_token() {
    local resp
    resp=$(curl -s -X POST "${BASE_URL}/api/v1/auth/login" \
        -d "username=admin&password=admin123" \
        -H "Content-Type: application/x-www-form-urlencoded")
    
    local token
    token=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('token',''))" 2>/dev/null || echo "")
    
    if [ -z "$token" ]; then
        error "获取Token失败: $resp"
        return 1
    fi
    echo "$token"
}

# Python-based 性能测试 (精确计时)
python_perf_test() {
    local name="$1"
    local url="$2"
    local concurrency="$3"
    local total_requests="$4"
    local token="$5"
    
    python3 <<-PYEOF
import requests
import time
import json
import statistics
import sys

url = "${url}"
concurrency = ${concurrency}
total = ${total_requests}
token = "${token}"

headers = {"Authorization": f"Bearer {token}"}
times = []
errors = 0
status_codes = {}

for i in range(total):
    start = time.perf_counter()
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times.append(elapsed)
        code = resp.status_code
        status_codes[code] = status_codes.get(code, 0) + 1
        if code >= 400:
            errors += 1
    except Exception as e:
        errors += 1
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

times.sort()
n = len(times)
p50 = times[int(n * 0.50)] if n > 0 else 0
p95 = times[int(n * 0.95)] if n > 0 else 0
p99 = times[int(n * 0.99)] if n > 0 else 0
avg = statistics.mean(times) if times else 0
total_time = sum(times)
qps = (total / (total_time / 1000)) if total_time > 0 else 0

result = {
    "name": "${name}",
    "url": url,
    "concurrency": concurrency,
    "total_requests": total,
    "avg_ms": round(avg, 2),
    "p50_ms": round(p50, 2),
    "p95_ms": round(p95, 2),
    "p99_ms": round(p99, 2),
    "qps": round(qps, 2),
    "errors": errors,
    "error_rate": round(errors/total*100, 2) if total > 0 else 0,
    "status_codes": status_codes
}
print(json.dumps(result))
PYEOF
}

# Apache Bench 性能测试 (如果有)
ab_perf_test() {
    local name="$1"
    local url="$2"
    local concurrency="$3"
    local total_requests="$4"
    local token="$5"
    
    if ! command -v ab &>/dev/null; then
        echo "null"
        return
    fi
    
    # ab 不支持 Bearer token 头直接，用 curl 先测试
    local temp_result
    temp_result=$(ab -n "$total_requests" -c "$concurrency" \
        -H "Authorization: Bearer ${token}" \
        -s 30 \
        "$url" 2>&1)
    
    # 解析 ab 输出
    python3 <<-PYEOF
import re, json

output = """${temp_result//\`/\//\\/\\/}"""
result = {}

# 提取关键指标
m = re.search(r'Requests per second:\s+([\d.]+)', output)
result['qps'] = float(m.group(1)) if m else 0

m = re.search(r'Time per request:\s+([\d.]+)\[ms\]', output)
result['avg_ms'] = float(m.group(1)) if m else 0

m = re.search(r'Total transferred:\s+(\d+)', output)
result['total_bytes'] = int(m.group(1)) if m else 0

m = re.search(r'Failed requests:\s+(\d+)', output)
result['failed'] = int(m.group(1)) if m else 0

m = re.search(r'Total:\s+(\d+)\s+(\d+)', output)
if m:
    result['total_time_ms'] = int(m.group(2))

result['name'] = "${name}"
result['url'] = "$url"
result['concurrency'] = ${concurrency}
result['total_requests'] = ${total_requests}

print(json.dumps(result))
PYEOF
}

# ============================================================================
# 主测试流程
# ============================================================================

main() {
    check_deps
    
    title "天链V3 后端性能测试"
    echo "  服务器: ${BASE_URL}"
    echo "  时间  : $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  结果  : ${RESULT_FILE}"
    
    # Step 1: Health Check (无需认证)
    title "[1/4] 健康检查 - /api/v1/health"
    local health_result
    health_result=$(python_perf_test "health" "${BASE_URL}/api/v1/health" 50 200 "")
    echo "$health_result" | python3 -m json.tool
    local health_qps
    health_qps=$(echo "$health_result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('qps',0))")
    
    # 获取Token
    title "[2/4] 获取认证Token"
    local token
    token=$(get_token) || { error "无法获取Token，终止测试"; exit 1; }
    info "Token获取成功 (前20位): ${token:0:20}..."
    
    # Step 2: Auth Login (POST)
    title "[3/4] 性能测试"
    
    # 测试配置
    local endpoints=(
        "auth_login|${BASE_URL}/api/v1/auth/login|POST"
        "stations_list|${BASE_URL}/api/v1/stations|GET"
        "alarms_list|${BASE_URL}/api/v1/alarms|GET"
        "workorders_list|${BASE_URL}/api/v1/workorders|GET"
    )
    
    local concurrency_levels=(10 50 100)
    local results=()
    
    for endpoint in "${endpoints[@]}"; do
        IFS='|' read -r name url method <<< "$endpoint"
        
        for conc in "${concurrency_levels[@]}"; do
            info "测试 ${name} (并发=${conc})"
            
            if [ "$method" = "POST" ]; then
                # POST 请求使用 Python
                local result
                result=$(python3 <<-PYEOF
import requests, time, json, statistics

url = "${url}"
concurrency = ${conc}
total = 200
token = "${token}"

headers = {"Authorization": f"Bearer {token}"}
times = []
errors = 0
status_codes = {}

# POST login 特殊处理
for i in range(total):
    start = time.perf_counter()
    try:
        if "${name}" == "auth_login":
            resp = requests.post(url, data="username=admin&password=admin123", headers={"Content-Type": "application/x-www-form-urlencoded"})
        else:
            resp = requests.get(url, headers=headers, timeout=30)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
        code = resp.status_code
        status_codes[code] = status_codes.get(code, 0) + 1
        if code >= 400:
            errors += 1
    except Exception as e:
        errors += 1
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

times.sort()
n = len(times)
p50 = times[int(n * 0.50)] if n > 0 else 0
p95 = times[int(n * 0.95)] if n > 0 else 0
p99 = times[int(n * 0.99)] if n > 0 else 0
avg = statistics.mean(times) if times else 0
total_time = sum(times)
qps = (total / (total_time / 1000)) if total_time > 0 else 0

print(json.dumps({
    "name": "${name}",
    "url": url,
    "concurrency": ${conc},
    "total_requests": total,
    "avg_ms": round(avg, 2),
    "p50_ms": round(p50, 2),
    "p95_ms": round(p95, 2),
    "p99_ms": round(p99, 2),
    "qps": round(qps, 2),
    "errors": errors,
    "error_rate": round(errors/total*100, 2) if total > 0 else 0,
    "status_codes": status_codes
}))
PYEOF
)
            else
                local result
                result=$(python_perf_test "$name" "$url" "$conc" 200 "$token")
            fi
            
            results+=("$result")
            echo "$result" | python3 -m json.tool 2>/dev/null
        done
    done
    
    # Step 4: 压力测试 - 并发100持续30秒
    title "[4/4] 压力测试 (并发100, 持续30秒)"
    local stress_result
    stress_result=$(python3 <<-'PYEOF'
import requests, time, json, statistics, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

urls = {
    "health": "http://localhost:8080/api/v1/health",
    "stations": "http://localhost:8080/api/v1/stations",
    "alarms": "http://localhost:8080/api/v1/alarms",
    "workorders": "http://localhost:8080/api/v1/workorders",
}

token = ""
try:
    r = requests.post("http://localhost:8080/api/v1/auth/login", data="username=admin&password=admin123")
    data = r.json()
    token = data.get("data", {}).get("token", "")
except:
    pass

headers = {"Authorization": f"Bearer {token}"} if token else {}
results = {k: [] for k in urls}
error_count = 0
request_count = 0
lock = threading.Lock()
stop = False

def worker(key, url):
    global request_count, error_count, stop
    while not stop:
        start = time.perf_counter()
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            elapsed = (time.perf_counter() - start) * 1000
            with lock:
                results[key].append({"t": elapsed, "code": resp.status_code})
                request_count += 1
                if resp.status_code >= 400:
                    error_count += 1
        except:
            with lock:
                error_count += 1
                request_count += 1

# 每条URL 25个并发线程 ≈ 100并发
threads = []
for key, url in urls.items():
    for _ in range(25):
        t = threading.Thread(target=worker, args=(key, url), daemon=True)
        threads.append(t)
        t.start()

time.sleep(30)
stop = True
for t in threads:
    t.join()

# 汇总
overall_times = []
for key, vals in results.items():
    for v in vals:
        overall_times.append(v["t"])

overall_times.sort()
n = len(overall_times)
p50 = overall_times[int(n * 0.5)] if n else 0
p95 = overall_times[int(n * 0.95)] if n else 0
p99 = overall_times[int(n * 0.99)] if n else 0
avg = statistics.mean(overall_times) if overall_times else 0
total_sum = sum(overall_times)

print(json.dumps({
    "name": "stress_test_30s",
    "description": "并发100, 持续30秒, 4个端点轮流请求",
    "total_requests": request_count,
    "duration_seconds": 30,
    "qps": round(request_count / 30, 2) if request_count > 0 else 0,
    "avg_ms": round(avg, 2),
    "p50_ms": round(p50, 2),
    "p95_ms": round(p95, 2),
    "p99_ms": round(p99, 2),
    "errors": error_count,
    "error_rate": round(error_count / request_count * 100, 2) if request_count > 0 else 0,
    "endpoint_breakdown": {k: {
        "count": len(results[k]),
        "avg_ms": round(statistics.mean([v["t"] for v in results[k]]), 2) if results[k] else 0
    } for k, v in results.items()}
}))
PYEOF
)
    
    echo "$stress_result" | python3 -m json.tool 2>/dev/null
    results+=("$stress_result")
    
    # 组装最终结果
    title "保存测试结果"
    
    python3 <<-PYEOF
import json, sys

results_json = {
    "test_info": {
        "tool": "perf-test.sh",
        "timestamp": "${TIMESTAMP}",
        "base_url": "${BASE_URL}",
        "app": "天链V3 光储充运维系统",
        "backend": "FastAPI + SQLite"
    },
    "tests": []
}

for r_raw in ${results[@]}; do
    try:
        r = json.loads(r_raw)
        if isinstance(r, dict):
            results_json["tests"].append(r)
    except:
        pass

with open("${RESULT_FILE}", "w") as f:
    json.dump(results_json, f, indent=2, ensure_ascii=False)

print(f"测试结果已保存到: ${RESULT_FILE}")
print(f"共 {len(results_json['tests'])} 个测试项")
PYEOF
}

main "$@"