#!/usr/bin/env bash
# 守卫接线三源一致性守卫 (F250)
# 每个 check:* 守卫脚本的接线是三份独立声明:
#   - package.json scripts 的 check:* 键 (声明侧/权威源: 守卫存在性)
#   - Makefile check 链 (本地全量检查入口, 经 *-check target 委托 npm run check:*)
#   - .github/workflows/ci.yml check job (CI 侧 npm run check:* 步骤)
# 只改一侧 → 漂移:
#   - 新增 check:* 脚本但未接 CI/Makefile → 守卫存在但永不执行 (假门控, F186教训)
#   - CI/Makefile 引用已删除的 check:* → 门禁直接报错或静默缺环
# 本守卫断言: 三侧 check:* 集合完全相等 (双向对账)
# 新增/删除守卫脚本时必须三处同步 (本守卫自身也在对账范围内, 守卫的失效条件也要门控 F236)
set -euo pipefail

cd "$(dirname "$0")/.."

PKG="package.json"
MAKEFILE="Makefile"
CI=".github/workflows/ci.yml"

for f in "$PKG" "$MAKEFILE" "$CI"; do
  if [ ! -f "$f" ]; then
    echo "❌ 缺少输入文件: $f (缺输入不放行)" >&2
    exit 1
  fi
done

# 源1: package.json scripts 中全部 check:* 键 (声明侧)
PKG_CHECKS="$(node -p '
  const s = require("./package.json").scripts || {};
  Object.keys(s).filter(k => k.startsWith("check:")).sort().join("\n");
')"
if [ -z "$PKG_CHECKS" ]; then
  echo "❌ package.json 未声明任何 check:* 脚本, 无法对账 (提取空不放行)" >&2
  exit 1
fi

# 源2: Makefile check 链 — check: 目标的依赖 target 中委托 npm run check:* 的那些
# (check: 链声明在文件后部而 target 定义在前, 须 END 块两阶段解析, 单遍顺序扫描会空提取)
MAKEFILE_CHECKS="$(awk '
  /^[A-Za-z0-9_.-]+:/ { tgt = $1; sub(/:.*$/, "", tgt) }
  /^\tnpm run check:/ { if (tgt != "") body[tgt] = $0 }
  /^check:/ { checklist = $0 }
  END {
    if (checklist == "") exit 0
    line = checklist
    sub(/^check:[ \t]*/, "", line)
    sub(/[ \t]*##.*/, "", line)
    n = split(line, deps, /[ \t]+/)
    for (i = 1; i <= n; i++) {
      if (deps[i] in body) {
        cmd = body[deps[i]]
        sub(/^[ \t]*npm run /, "", cmd)
        sub(/[ \t].*/, "", cmd)
        print cmd
      }
    }
  }
' "$MAKEFILE" | sort -u)"
if [ -z "$MAKEFILE_CHECKS" ]; then
  echo "❌ Makefile check 链未提取到任何 check:* 委托, 无法对账 (提取空不放行)" >&2
  exit 1
fi

# 源3: CI ci.yml 中全部 npm run check:* 步骤
CI_CHECKS="$(grep -oE 'npm run check:[A-Za-z0-9_-]+' "$CI" | awk '{print $3}' | sort -u || true)"
if [ -z "$CI_CHECKS" ]; then
  echo "❌ ci.yml 未提取到任何 npm run check:* 步骤, 无法对账 (提取空不放行)" >&2
  exit 1
fi

FAIL=0

# 双向对账: 声明侧 ↔ Makefile 侧
while IFS= read -r k; do
  if ! grep -qxF "$k" <<< "$MAKEFILE_CHECKS"; then
    echo "❌ 守卫接线漂移: $k 已在 package.json 声明但未接入 Makefile check 链" >&2
    FAIL=1
  fi
done <<< "$PKG_CHECKS"
while IFS= read -r k; do
  if ! grep -qxF "$k" <<< "$PKG_CHECKS"; then
    echo "❌ 守卫接线漂移: Makefile check 链引用 $k 但 package.json 无此脚本 (悬空引用)" >&2
    FAIL=1
  fi
done <<< "$MAKEFILE_CHECKS"

# 双向对账: 声明侧 ↔ CI 侧
while IFS= read -r k; do
  if ! grep -qxF "$k" <<< "$CI_CHECKS"; then
    echo "❌ 守卫接线漂移: $k 已在 package.json 声明但未接入 CI check job" >&2
    FAIL=1
  fi
done <<< "$PKG_CHECKS"
while IFS= read -r k; do
  if ! grep -qxF "$k" <<< "$PKG_CHECKS"; then
    echo "❌ 守卫接线漂移: CI 引用 $k 但 package.json 无此脚本 (悬空引用)" >&2
    FAIL=1
  fi
done <<< "$CI_CHECKS"

if [ "$FAIL" -ne 0 ]; then
  echo "   check:* 守卫接线是三源声明(package.json/Makefile/CI), 新增/删除守卫时三处同步" >&2
  exit 1
fi

COUNT="$(grep -c . <<< "$PKG_CHECKS")"
echo "✅ 守卫接线三源一致: $COUNT 个 check:* 守卫全部接入 Makefile check 链 + CI check job"
