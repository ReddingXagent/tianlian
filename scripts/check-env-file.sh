#!/usr/bin/env bash
# F326: .env文件凭据语义多源对账守卫(部署守卫族第十四枚)
#
# 同一语义(.env凭据文件身份)的声明散布多源, 此前零断言(F295只覆盖目录段渲染一致性):
#   systemd unit   EnvironmentFile=.../.env   (basename与"-"前缀形态)
#   docker-compose env_file: .env             (容器侧凭据文件, 相对compose目录)
#   .gitignore     .env                       (凭据保护侧)
#
# 漂移后果(最恶形态=静默):
#   EnvironmentFile加"-"前缀 → 缺文件被systemd静默容忍, CLOUD_TOKEN等全键吃默认值,
#   云端认证失败时无人想到是env文件缺失;
#   unit侧basename改走(如env.production)而compose侧/.gitignore不同步 →
#   容器/宿主两模式读不同凭据文件, 排障结论互相矛盾;
#   basename改走后.gitignore仍只保护".env" → 新文件名的真实凭据被误commit泄密。
#
# 断言:
#   1. EnvironmentFile无"-"前缀(静默容忍缺失=禁)
#   2. EnvironmentFile basename == .env
#   3. docker-compose env_file basename == unit侧basename(两模式同一凭据文件)
#   4. .gitignore含精确".env"行(凭据保护与basename同名同步)
# 缺输入/提取空/不等均 exit 1 (F212不放行)。接入 make check(env-file-check) + CI check job。
set -euo pipefail
cd "$(dirname "$0")/.."

fail() { echo "❌ [check-env-file] $1" >&2; exit 1; }

DEPLOY_SH=deploy.sh
COMPOSE_YML=docker-compose.yml
GITIGNORE=.gitignore

[ -f "$DEPLOY_SH" ] || fail "缺输入: $DEPLOY_SH"
[ -f "$COMPOSE_YML" ] || fail "缺输入: $COMPOSE_YML"
[ -f "$GITIGNORE" ] || fail "缺输入: $GITIGNORE"

# unit模板路径取自 deploy.sh UNIT_FILE 默认值(F236已守卫三源同名), 不硬编码unit文件名
unit_template="systemd/$(basename "$(sed -n 's/^UNIT_FILE="\${TIANLIAN_UNIT_FILE:-\(.*\)}".*$/\1/p' "$DEPLOY_SH" | head -1)")"
[ -f "$unit_template" ] || fail "缺输入: $unit_template (由deploy.sh UNIT_FILE推导)"

# 源1: unit EnvironmentFile(取首个声明行)
ENVFILE_LINE="$(grep -m1 -E '^EnvironmentFile=' "$unit_template" || true)"
[ -n "$ENVFILE_LINE" ] || fail "提取空: $unit_template EnvironmentFile 声明"
ENVFILE_PATH="${ENVFILE_LINE#EnvironmentFile=}"
case "$ENVFILE_PATH" in
    -*) fail "EnvironmentFile带'-'前缀: 缺文件将被systemd静默容忍, 全键吃默认值(禁)" ;;
esac
ENVFILE_BASE="$(basename "$ENVFILE_PATH")"

# 源2: docker-compose env_file(取首个声明)
COMPOSE_ENVFILE="$(sed -n 's/^[[:space:]]*env_file:[[:space:]]*\(.*\)$/\1/p' "$COMPOSE_YML" | head -1 | tr -d '"')"
[ -n "$COMPOSE_ENVFILE" ] || fail "提取空: $COMPOSE_YML env_file 声明"
COMPOSE_BASE="$(basename "$COMPOSE_ENVFILE")"

# 源3: .gitignore 凭据保护条目(精确行匹配, 容忍尾随空白)
GITIGNORE_HIT="$(grep -cE '^\.env[[:space:]]*$' "$GITIGNORE" || true)"

echo "unit EnvironmentFile basename: $ENVFILE_BASE"
echo "compose env_file basename:     $COMPOSE_BASE"

fail=0
if [ "$ENVFILE_BASE" != ".env" ]; then
    echo "❌ EnvironmentFile basename($ENVFILE_BASE) != .env" >&2
    fail=1
fi
if [ "$COMPOSE_BASE" != "$ENVFILE_BASE" ]; then
    echo "❌ compose env_file basename($COMPOSE_BASE) != unit侧($ENVFILE_BASE): 容器/宿主两模式读不同凭据文件" >&2
    fail=1
fi
if [ "$GITIGNORE_HIT" -lt 1 ]; then
    echo "❌ .gitignore缺精确'.env'行: 真实凭据文件可能被误commit泄密" >&2
    fail=1
fi

[ "$fail" -eq 0 ] || exit 1
echo "✅ [check-env-file] .env凭据语义四源对账一致(无'-'前缀, basename两侧相等, gitignore保护在列)"
