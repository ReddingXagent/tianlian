#!/usr/bin/env bash
# Node 版本双源漂移守卫 (F237)
# engines.node(package.json) 与 CI setup-node 的 node-version 是同一语义的双源:
#   - engines.node 是本地/安装侧的最低版本门 (.npmrc engine-strict=true 时强制, F218)
#   - .github/workflows/*.yml 的 setup-node node-version 是 CI 实际运行的版本
# 只改一侧 → 漂移:
#   - engines 抬高而 CI 未跟上 → CI npm ci 直接 engine 报错, 或门限形同虚设
#   - CI 降级而 engines 未跟上 → 本地装不上依赖/行为与 CI 分叉
# 本守卫断言: 每个 workflow 的 node-version 主版本 >= engines.node 声明的最低主版本
# 修改 node 版本基线时必须两侧同步
set -euo pipefail

cd "$(dirname "$0")/.."

ENGINES_NODE="$(node -p 'require("./package.json").engines && require("./package.json").engines.node || ""')"
if [ -z "$ENGINES_NODE" ]; then
  echo "❌ package.json 未声明 engines.node, 无法对账 CI node-version (缺输入不放行)" >&2
  exit 1
fi

# 提取最低主版本: 兼容 >=20 / >=20.x / >=20.11.0 / ^20 / ~20.0 等前缀写法
ENGINES_MAJOR="$(node -p '
  const s = process.argv[1].trim();
  const m = s.match(/(\d+)/);
  if (!m) { console.error("engines.node 无法解析: " + s); process.exit(1); }
  m[1];
' "$ENGINES_NODE")"

WORKFLOWS="$(ls .github/workflows/*.yml .github/workflows/*.yaml 2>/dev/null || true)"
if [ -z "$WORKFLOWS" ]; then
  echo "❌ 未找到 .github/workflows/*.yml, 无法对账 CI node-version (缺输入不放行)" >&2
  exit 1
fi

# 收集全部 setup-node node-version 声明 (多 job 逐个对账)
CI_VERSIONS="$(grep -hE '^\s*node-version:' $WORKFLOWS | sed -E 's/^\s*node-version:\s*//; s/["'\'']//g' || true)"
if [ -z "$CI_VERSIONS" ]; then
  echo "❌ workflow 中未找到 node-version 声明, 无法对账 (缺输入不放行)" >&2
  exit 1
fi

FAIL=0
while IFS= read -r v; do
  [ -z "$v" ] && continue
  CI_MAJOR="$(node -p '
    const s = process.argv[1].trim();
    const m = s.match(/(\d+)/);
    if (!m) { console.error("node-version 无法解析: " + s); process.exit(1); }
    m[1];
  ' "$v")"
  if [ "$CI_MAJOR" -lt "$ENGINES_MAJOR" ]; then
    echo "❌ node 版本漂移: CI node-version=$v < engines.node=$ENGINES_NODE (最低主版本 $ENGINES_MAJOR)" >&2
    FAIL=1
  else
    echo "✅ CI node-version=$v ≥ engines.node=$ENGINES_NODE"
  fi
done <<< "$CI_VERSIONS"

if [ "$FAIL" -ne 0 ]; then
  echo "   engines.node 与 CI node-version 是同一语义双源, 修改 node 基线时两处同步" >&2
  exit 1
fi
