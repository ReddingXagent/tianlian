#!/usr/bin/env bash
# F267: 数据持久化路径多源一致性守卫(SQLite DB路径 声明侧↔Docker持久化侧↔备份侧)
# 背景: SQLite DB路径五源分源维护零断言:
#   ① config.py dataclass默认值 db_path: str = "data/gateway.db" (声明侧权威源)
#   ② config.py os.getenv("STORAGE_DB_PATH", "...") fallback默认值 (同文件第二声明)
#   ③ Dockerfile WORKDIR + VOLUME (容器内持久化挂载点)
#   ④ docker-compose.yml volumes 命名卷挂载目标 (容器侧路径)
#   ⑤ deploy.sh 迁移前备份 data/backups/gateway.db.<ts>.bak (宿主机备份glob)
# 漂移后果: ①单独改路径(如迁storage/)→容器卷不再覆盖真实DB→容器重建数据
#   静默丢失(边缘设备最恶故障); ①≠②→env未设时两处默认值分叉; ⑤basename
#   漂移→备份/回滚glob永远匹配不到真实DB→回滚无备份可用。
# 本脚本: 断言 ①==②, WORKDIR+dirname(①)==③==④, dirname(①)==⑤目录前缀,
# basename(①)==⑤备份basename; 任一源缺输入/提取空/不一致均FAIL(exit 1, F212不放行)。
# 接入 make check + CI。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

CONFIG_PY="config.py"
DOCKERFILE="Dockerfile"
COMPOSE="docker-compose.yml"
DEPLOY_SH="deploy.sh"

fail() { echo "❌ $1"; exit 1; }

for f in "$CONFIG_PY" "$DOCKERFILE" "$COMPOSE" "$DEPLOY_SH"; do
    [ -f "$f" ] || fail "缺输入(F267): $f 不存在"
done

# 声明侧①: dataclass字段默认值 db_path: str = "<path>"
FIELD_DEFAULT="$(grep -oE 'db_path: *str *= *"[^"]+"' "$CONFIG_PY" \
    | sed -E 's|^db_path: *str *= *"([^"]+)"$|\1|' | head -1 || true)"
[ -n "$FIELD_DEFAULT" ] || fail "提取空(F267): config.py 未找到 db_path 字段默认值声明"

# 声明侧②: os.getenv("STORAGE_DB_PATH", "<default>") fallback默认值
ENV_DEFAULT="$(grep -oE 'os\.getenv\("STORAGE_DB_PATH", *"[^"]+"' "$CONFIG_PY" \
    | sed -E 's|^os\.getenv\("STORAGE_DB_PATH", *"([^"]+)"$|\1|' | head -1 || true)"
[ -n "$ENV_DEFAULT" ] || fail "提取空(F267): config.py 未找到 STORAGE_DB_PATH getenv默认值"

[ "$FIELD_DEFAULT" = "$ENV_DEFAULT" ] || fail "漂移(F267): config.py双声明分叉 — 字段默认($FIELD_DEFAULT) ≠ getenv默认($ENV_DEFAULT), env未设时行为取决于读取路径"

DB_REL="$FIELD_DEFAULT"
DB_BASE="$(basename "$DB_REL")"

# Docker侧③: WORKDIR + VOLUME
WORKDIR="$(grep -oE '^WORKDIR +\S+' "$DOCKERFILE" | awk '{print $2}' | head -1 || true)"
[ -n "$WORKDIR" ] || fail "提取空(F267): Dockerfile 未找到 WORKDIR"
VOLUME_PATH="$(grep -oE '^VOLUME +\["[^"]+"' "$DOCKERFILE" \
    | sed -E 's|^VOLUME +\["([^"]+)"$|\1|' | head -1 || true)"
[ -n "$VOLUME_PATH" ] || fail "提取空(F267): Dockerfile 未找到 VOLUME 声明"

case "$DB_REL" in
    /*) EXPECTED_CONTAINER="$DB_REL" ;;
    *)  EXPECTED_CONTAINER="$WORKDIR/$(dirname "$DB_REL")" ;;
esac

[ "$VOLUME_PATH" = "$EXPECTED_CONTAINER" ] || fail "漂移(F267): Dockerfile VOLUME($VOLUME_PATH) ≠ 声明侧推导($EXPECTED_CONTAINER, WORKDIR+dirname(db_path)) → 容器卷不覆盖真实DB, 重建即静默丢数据"

# Docker侧④: compose 命名卷挂载目标(容器侧路径, /app前缀过滤掉localtime等系统挂载)
COMPOSE_TARGETS="$(grep -oE '^\s*- +[A-Za-z0-9_.-]+:/[^: ]+' "$COMPOSE" \
    | sed -E 's|^\s*- +[A-Za-z0-9_.-]+:(/[^: ]+)$|\1|' | grep '^/app' | sort -u || true)"
[ -n "$COMPOSE_TARGETS" ] || fail "提取空(F267): docker-compose.yml 未找到 /app 下命名卷挂载"
COMPOSE_COUNT="$(printf '%s\n' "$COMPOSE_TARGETS" | wc -l)"
[ "$COMPOSE_COUNT" -eq 1 ] || fail "歧义(F267): docker-compose.yml /app下命名卷挂载≠1个: $(printf '%s' "$COMPOSE_TARGETS" | tr '\n' ' ')"

[ "$COMPOSE_TARGETS" = "$VOLUME_PATH" ] || fail "漂移(F267): compose挂载目标($COMPOSE_TARGETS) ≠ Dockerfile VOLUME($VOLUME_PATH) → 挂载点分叉, 持久化落空"

# 备份侧⑤: deploy.sh 备份glob <dir>/backups/<basename>.$TS.bak
BAK_LINE="$(grep -oE 'BAK="[A-Za-z0-9/_.-]+/backups/[A-Za-z0-9_.-]+\.\$TS' "$DEPLOY_SH" | head -1 || true)"
[ -n "$BAK_LINE" ] || fail "提取空(F267): deploy.sh 未找到 BAK=\"<dir>/backups/<name>.\$TS 备份glob"
BAK_DIR="$(printf '%s' "$BAK_LINE" | sed -E 's|^BAK="([^/]+)/backups/.*$|\1|')"
BAK_BASE="$(printf '%s' "$BAK_LINE" | sed -E 's|^BAK="[^"]+/backups/([A-Za-z0-9_.-]+)[.]\$TS$|\1|')"
[ -n "$BAK_DIR" ] && [ -n "$BAK_BASE" ] || fail "提取空(F267): deploy.sh 备份glob目录/basename解析失败"

[ "$BAK_DIR" = "$(dirname "$DB_REL")" ] || fail "漂移(F267): deploy.sh备份目录($BAK_DIR) ≠ 声明侧dirname($(dirname "$DB_REL")) → 备份写入位置与真实DB分叉"
[ "$BAK_BASE" = "$DB_BASE" ] || fail "漂移(F267): deploy.sh备份basename($BAK_BASE) ≠ 声明侧basename($DB_BASE) → 备份/回滚glob永远匹配不到真实DB"

echo "✅ [check-data-paths] 数据持久化路径五源一致: db=$DB_REL, 容器卷=$VOLUME_PATH(compose对齐), 备份=$BAK_DIR/backups/$BAK_BASE.*"
