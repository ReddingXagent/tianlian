#!/usr/bin/env bash
# F249: API端口多源一致性守卫
#
# 同一语义(API监听端口)的声明散布多处, 零断言:
#   声明侧(权威源): config.py LocalAPIConfig.port 默认值 (api/server.py 实际 listen 端口)
#   探测/发布侧:
#     deploy.sh      PORT="${PORT:-N}"  (健康探测/端口释放/fuser kill/展示URL)
#     docker-compose.yml ports "N:N"    (容器端口映射)
#     Dockerfile     EXPOSE N           (镜像声明)
#     Dockerfile     HEALTHCHECK curl localhost:N (容器内健康探测)
# 任一侧单独改端口 → deploy.sh探测旧端口永不亮=健康服务被报部署失败;
# Docker HEALTHCHECK探测旧端口=容器被反复判不健康重启。
#
# 断言: 探测/发布侧各源 == 声明侧默认值 (缺输入/提取空/不等均 exit 1, F212不放行)
set -euo pipefail
cd "$(dirname "$0")/.."

fail() { echo "❌ [check-api-port] $1" >&2; exit 1; }

CONFIG_PY=config.py
DEPLOY_SH=deploy.sh
COMPOSE_YML=docker-compose.yml
DOCKERFILE=Dockerfile

[ -f "$CONFIG_PY" ] || fail "缺输入: $CONFIG_PY"
[ -f "$DEPLOY_SH" ] || fail "缺输入: $DEPLOY_SH"
[ -f "$COMPOSE_YML" ] || fail "缺输入: $COMPOSE_YML"
[ -f "$DOCKERFILE" ] || fail "缺输入: $DOCKERFILE"

# 声明侧: config.py LocalAPIConfig 类块内首个 port: int = N
DECL_PORT=$(awk '/^class LocalAPIConfig/ {inblk=1; next} /^class / {inblk=0} inblk && /port: int = [0-9]+/ {print; exit}' "$CONFIG_PY" \
  | grep -oE '[0-9]+' || true)
[ -n "$DECL_PORT" ] || fail "提取空: config.py LocalAPIConfig.port 默认值"

# 探测侧1: deploy.sh PORT 默认值
DEPLOY_PORT=$(grep -oE 'PORT="\$\{PORT:-[0-9]+\}"' "$DEPLOY_SH" | head -1 | grep -oE '[0-9]+' || true)
[ -n "$DEPLOY_PORT" ] || fail "提取空: deploy.sh PORT 默认值"

# 发布侧2: docker-compose ports 映射 "N:N" (容器侧须等于声明侧; 宿主侧映射也一并对账)
COMPOSE_PORTS=$(grep -oE '^[[:space:]]*- "?[0-9]+:[0-9]+"?' "$COMPOSE_YML" | head -1 | grep -oE '[0-9]+' || true)
[ -n "$COMPOSE_PORTS" ] || fail "提取空: docker-compose.yml ports 映射"
COMPOSE_HOST=$(echo "$COMPOSE_PORTS" | sed -n '1p')
COMPOSE_CTR=$(echo "$COMPOSE_PORTS" | sed -n '2p')

# 发布侧3: Dockerfile EXPOSE
EXPOSE_PORT=$(grep -oE '^EXPOSE [0-9]+' "$DOCKERFILE" | head -1 | grep -oE '[0-9]+' || true)
[ -n "$EXPOSE_PORT" ] || fail "提取空: Dockerfile EXPOSE 端口"

# 探测侧4: Dockerfile HEALTHCHECK curl localhost:N
HEALTH_PORT=$(grep -A2 'HEALTHCHECK' "$DOCKERFILE" | grep -oE 'localhost:[0-9]+' | head -1 | grep -oE '[0-9]+' || true)
[ -n "$HEALTH_PORT" ] || fail "提取空: Dockerfile HEALTHCHECK 探测端口"

echo "声明侧 config.py LocalAPIConfig.port = $DECL_PORT"
echo "  deploy.sh PORT默认               = $DEPLOY_PORT"
echo "  docker-compose ports             = $COMPOSE_HOST:$COMPOSE_CTR"
echo "  Dockerfile EXPOSE                = $EXPOSE_PORT"
echo "  Dockerfile HEALTHCHECK           = $HEALTH_PORT"

[ "$DEPLOY_PORT" = "$DECL_PORT" ] || fail "漂移: deploy.sh PORT($DEPLOY_PORT) ≠ config.py($DECL_PORT) → 部署健康探测永不亮"
[ "$COMPOSE_CTR" = "$DECL_PORT" ] || fail "漂移: docker-compose容器端口($COMPOSE_CTR) ≠ config.py($DECL_PORT) → 容器内服务不可达"
[ "$COMPOSE_HOST" = "$DECL_PORT" ] || fail "漂移: docker-compose宿主端口($COMPOSE_HOST) ≠ config.py($DECL_PORT) → 与deploy.sh/文档口径分叉"
[ "$EXPOSE_PORT" = "$DECL_PORT" ] || fail "漂移: Dockerfile EXPOSE($EXPOSE_PORT) ≠ config.py($DECL_PORT)"
[ "$HEALTH_PORT" = "$DECL_PORT" ] || fail "漂移: Dockerfile HEALTHCHECK($HEALTH_PORT) ≠ config.py($DECL_PORT) → 容器被反复判不健康"

echo "✅ [check-api-port] API端口五源一致($DECL_PORT): config.py/deploy.sh/compose/EXPOSE/HEALTHCHECK"
