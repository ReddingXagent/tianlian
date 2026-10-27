#!/usr/bin/env bash
# engines.node 执行力双源漂移守卫
# package.json engines.node(声明侧) 与 .npmrc engine-strict=true(执行侧) 是同一门控的双源:
#   - engines.node 只是声明; npm 默认对 EBADENGINE 仅打 warning, 低版本 Node 照样安装
#   - .npmrc engine-strict=true 才使 npm ci/install 在低版本 Node 上直接失败 (F218 加严)
# 只改一侧 → 漂移, 且两侧分叉均为静默失效:
#   - engine-strict 被删/改 false 而 engines 仍在 → 门限形同虚设, 低版本 Node 静默装上依赖, 运行期才炸
#   - engines.node 被删而 engine-strict 仍在 → 死配置, engine-strict 无声明可执行 (F258 反向挡声明未引用)
# 本守卫断言两侧成对存在; 修改 node 版本门控基线时必须两侧同步
# 缺输入不放行 (F212)
set -euo pipefail

cd "$(dirname "$0")/.."

PKG="package.json"
NPMRC=".npmrc"

if [ ! -f "$PKG" ]; then
  echo "❌ 缺少输入文件: $PKG (缺输入不放行)" >&2
  exit 1
fi

ENGINES_NODE="$(node -p '(require("./package.json").engines && require("./package.json").engines.node) || ""')"
NPMRC_STRICT=""
if [ -f "$NPMRC" ]; then
  NPMRC_STRICT="$(grep -E '^\s*engine-strict\s*=\s*(true|"true")\s*$' "$NPMRC" || true)"
fi

if [ -n "$ENGINES_NODE" ] && [ -z "$NPMRC_STRICT" ]; then
  echo "❌ 门控静默失效: package.json 声明 engines.node=\"$ENGINES_NODE\" 但 .npmrc 缺少 engine-strict=true" >&2
  echo "   npm 默认对 EBADENGINE 仅 warning, 低版本 Node 仍会安装成功 → 运行期才炸" >&2
  echo "   处置: .npmrc 加 engine-strict=true (F218 加严), 或确认放弃引擎门控后同删 engines.node" >&2
  exit 1
fi

if [ -z "$ENGINES_NODE" ] && [ -n "$NPMRC_STRICT" ]; then
  echo "❌ 死配置: .npmrc 声明 engine-strict=true 但 package.json 未声明 engines.node (无声明可执行)" >&2
  echo "   处置: 补 engines.node 声明, 或同删 engine-strict (两侧成对存在)" >&2
  exit 1
fi

if [ -z "$ENGINES_NODE" ] && [ -z "$NPMRC_STRICT" ]; then
  echo "❌ 引擎门控整体缺失: engines.node 与 .npmrc engine-strict 均未声明 (缺输入不放行)" >&2
  echo "   RN/Expo 工程必须声明 engines.node + engine-strict=true, 否则低版本 Node 静默安装" >&2
  exit 1
fi

echo "✅ engines.node 执行力双源成对: engines.node=\"$ENGINES_NODE\" ↔ .npmrc engine-strict=true"
