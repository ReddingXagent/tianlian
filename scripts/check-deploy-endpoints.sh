#!/usr/bin/env bash
# F243: 部署探测端点一致性守卫(deploy.sh探测侧 ↔ api/server.py路由声明侧)
# 背景: deploy.sh 部署成功判定(HEALTH_OK循环)与 status 子命令探测
#   http://localhost:$PORT/health 与 /api/v1/status, 路由声明在 api/server.py
#   (@app.get(...) 装饰器)。两侧独立维护零断言 → 服务端路由单独改名 →
#   部署成功判定循环永远不亮(健康服务被报部署失败)/status子命令"不可达";
#   探测侧单独改错 → 同果。F236同族(部署同名源一致性): 探测依据必须对账声明源。
# 本脚本: 提取deploy.sh探测路径集合, 断言全部存在于server.py声明路由集合;
# 任一侧缺输入/提取空/不一致均FAIL(exit 1, F212不放行)。接入 make check + CI。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

DEPLOY_SH="deploy.sh"
SERVER_PY="api/server.py"

for f in "$DEPLOY_SH" "$SERVER_PY"; do
    if [ ! -f "$f" ]; then
        echo "❌ 缺输入(F243): $f 不存在"
        exit 1
    fi
done

# 提取探测路径: curl "http://localhost:$PORT/<path>" (排除$(hostname)展示行)
probe_paths="$(grep -oE 'http://localhost:\$PORT/[A-Za-z0-9/_.-]+' "$DEPLOY_SH" \
    | sed 's|http://localhost:\$PORT||' | sort -u)"
if [ -z "$probe_paths" ]; then
    echo "❌ 提取失败(F243): deploy.sh 未找到 http://localhost:\$PORT/... 探测URL"
    exit 1
fi

# 提取声明路由: @app.get("/path") / @app.post("/path") ...
declared_routes="$(grep -oE '@app\.(get|post|put|delete|patch)\("[^"]+"' "$SERVER_PY" \
    | sed -E 's|^@app\.[a-z]+\("([^"]+)"$|\1|' | sort -u)"
if [ -z "$declared_routes" ]; then
    echo "❌ 提取失败(F243): api/server.py 未找到 @app.<method>(\"...\") 路由声明"
    exit 1
fi

fail=0
while IFS= read -r p; do
    if ! printf '%s\n' "$declared_routes" | grep -qxF "$p"; then
        echo "❌ 探测端点漂移(F243): deploy.sh 探测 $p 未在 api/server.py 路由声明中 → 部署成功判定/status探测静默失效"
        fail=1
    fi
done <<< "$probe_paths"

if [ "$fail" -ne 0 ]; then
    echo "   deploy.sh探测集: $(printf '%s' "$probe_paths" | tr '\n' ' ')"
    echo "   server.py声明集: $(printf '%s' "$declared_routes" | tr '\n' ' ')"
    exit 1
fi

echo "✅ 部署探测端点一致(F243): $(printf '%s\n' "$probe_paths" | wc -l) 个探测路径均在路由声明中"
