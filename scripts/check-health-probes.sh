#!/usr/bin/env bash
# F280: 健康探测路径多源一致性守卫(F243/F249的路径侧补全)
#
# 背景: 存活探测路径 /health 的探测源有三处, 零断言:
#   声明侧(权威源): api/server.py @app.get("/health") 路由
#   探测侧:
#     deploy.sh      curl http://localhost:$PORT/health (部署成功判定/status子命令)
#     watchdog.sh    HEALTH_URL="http://localhost:${PORT}/health" (cron存活探测)
#     Dockerfile     HEALTHCHECK CMD curl -sf http://localhost:8080/health
# F243只覆盖 deploy.sh↔server.py 单向, watchdog/Dockerfile 探测路径是盲区;
# F249只覆盖端口侧, 路径侧无对账。
#
# 漂移后果: 服务端路由单独改名(如/healthz) →
#   watchdog curl 404(-f判失败) → 健康进程被判卡死 → kill循环反复重启;
#   Docker HEALTHCHECK 失败 → 容器判 unhealthy → restart:unless-stopped 重启循环;
#   deploy.sh 健康判定循环永不亮 → 健康服务被报部署失败。
# 探测侧单独改错 → 同果。
#
# 断言:
#   ① 三探测源路径集合各自 ⊆ server.py 声明路由集合;
#   ② watchdog ↔ Dockerfile 存活探测路径相等(同一存活语义必须单一源, F259);
# 缺输入/提取空/不一致均 exit 1 (F212不放行)。接入 make check + CI。
set -euo pipefail
cd "$(dirname "$0")/.."

fail() { echo "❌ [check-health-probes] $1" >&2; exit 1; }

SERVER_PY=api/server.py
DEPLOY_SH=deploy.sh
WATCHDOG=scripts/watchdog.sh
DOCKERFILE=Dockerfile

for f in "$SERVER_PY" "$DEPLOY_SH" "$WATCHDOG" "$DOCKERFILE"; do
    [ -f "$f" ] || fail "缺输入: $f"
done

# 声明侧: server.py 路由集合 (与F243同提取口径)
declared_routes="$(grep -oE '@app\.(get|post|put|delete|patch)\("[^"]+"' "$SERVER_PY" \
    | sed -E 's|^@app\.[a-z]+\("([^"]+)"$|\1|' | sort -u)"
[ -n "$declared_routes" ] || fail "提取空: $SERVER_PY 未找到 @app.<method>(\"...\") 路由声明"

# deploy.sh 探测路径 (与F243同口径: localhost:$PORT 探测URL, 展示行不含$PORT形态自然排除)
deploy_paths="$(grep -oE 'http://localhost:\$PORT/[A-Za-z0-9/_.-]+' "$DEPLOY_SH" \
    | sed 's|http://localhost:\$PORT||' | sort -u)"
[ -n "$deploy_paths" ] || fail "提取空: $DEPLOY_SH 未找到 http://localhost:\$PORT/... 探测URL"

# watchdog.sh 存活探测路径: HEALTH_URL="http://localhost:${PORT}/<path>"
watchdog_path="$(grep -oE 'HEALTH_URL="http://localhost:\$\{PORT\}/[A-Za-z0-9/_.-]+' "$WATCHDOG" \
    | sed -E 's|^HEALTH_URL="http://localhost:\$\{PORT\}||' | sort -u)"
[ -n "$watchdog_path" ] || fail "提取空: $WATCHDOG 未找到 HEALTH_URL=http://localhost:\${PORT}/..."

# Dockerfile HEALTHCHECK 探测路径: CMD curl -sf http://localhost:<port>/<path>
docker_path="$(grep -E '^[[:space:]]*CMD curl' "$DOCKERFILE" \
    | grep -oE 'http://localhost:[0-9]+/[A-Za-z0-9/_.-]+' \
    | sed -E 's|^http://localhost:[0-9]+||' | sort -u)"
[ -n "$docker_path" ] || fail "提取空: $DOCKERFILE 未找到 CMD curl http://localhost:<port>/... HEALTHCHECK"

fail_flag=0
check_subset() { # $1=源名 $2=路径集
    while IFS= read -r p; do
        if ! printf '%s\n' "$declared_routes" | grep -qxF "$p"; then
            echo "❌ 探测路径漂移(F280): $1 探测 $p 未在 $SERVER_PY 路由声明中 → 探测永不命中(kill循环/重启循环/部署判定失败)" >&2
            fail_flag=1
        fi
    done <<< "$2"
}
check_subset "$DEPLOY_SH" "$deploy_paths"
check_subset "$WATCHDOG" "$watchdog_path"
check_subset "$DOCKERFILE" "$docker_path"

# watchdog ↔ Dockerfile 同为存活探测语义, 路径必须单一源(F259同度量语义收敛)
if [ "$watchdog_path" != "$docker_path" ]; then
    echo "❌ 存活探测双源漂移(F280): watchdog=$watchdog_path ≠ Dockerfile=$docker_path (同一存活语义必须单源)" >&2
    fail_flag=1
fi

[ "$fail_flag" -eq 0 ] || exit 1
echo "✅ 健康探测路径多源一致(F280): deploy.sh($(printf '%s\n' "$deploy_paths" | wc -l)条)+watchdog+Dockerfile 探测路径均在路由声明中, watchdog↔Dockerfile存活路径相等"
