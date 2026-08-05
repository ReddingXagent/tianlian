#!/usr/bin/env bash
# app.json expo.plugins ↔ package.json 依赖 双源成对守卫 (F296, 第十一枚)
# app.json expo.plugins 是 config plugin 的声明侧(prebuild/export 时按名加载插件),
# package.json dependencies+devDependencies 是供给侧(插件包必须真实安装):
#   - 声明了 plugin 而依赖缺失 → expo 加载 config plugin 静默跳过/延迟到 prebuild 才崩,
#     插件承载的原生配置(权限声明/AndroidManifest/Info.plist 注入)整体缺失, 上架/运行时才暴露
#   - 插件名写错(拼写漂移) 与依赖缺失同型, 一并拦截
# 反向(dep 存在但未声明 plugin)不做断言: expo-status-bar 等组件型包无需 config plugin,
# 反向检查存在合法豁免形态, 强断言会误报
# 插件条目形态: string 或 [name, props] 数组; 未识别形态 loud fail
# 缺输入不放行 (F212)
set -euo pipefail

cd "$(dirname "$0")/.."

APP="app.json"
PKG="package.json"

if [ ! -f "$APP" ]; then
  echo "❌ 缺少输入文件: $APP (缺输入不放行)" >&2
  exit 1
fi
if [ ! -f "$PKG" ]; then
  echo "❌ 缺少输入文件: $PKG (缺输入不放行)" >&2
  exit 1
fi

PLUGINS_RAW="$(node -p 'JSON.stringify(require("./app.json").expo.plugins ?? null)')"
if [ "$PLUGINS_RAW" = "null" ]; then
  echo "❌ app.json 缺 expo.plugins 声明: 插件清单形态不明, 无法对账 (缺输入不放行)" >&2
  echo "   处置: 显式声明 expo.plugins (无插件时声明空数组 [])" >&2
  exit 1
fi

# 归一化插件名清单: string → 自身; [name, props] → 首元素; 其他形态 loud fail
PLUGIN_NAMES="$(node -e '
const plugins = require("./app.json").expo.plugins ?? [];
if (!Array.isArray(plugins)) { console.error("❌ expo.plugins 非数组形态: " + typeof plugins + " (未识别形态 loud fail)"); process.exit(1); }
for (const p of plugins) {
  if (typeof p === "string") { console.log(p); }
  else if (Array.isArray(p) && typeof p[0] === "string") { console.log(p[0]); }
  else { console.error("❌ expo.plugins 未识别条目形态: " + JSON.stringify(p) + " (仅支持 string 或 [name, props], loud fail)"); process.exit(1); }
}
')"

DEP_KEYS="$(node -e '
const p = require("./package.json");
for (const k of Object.keys({ ...p.dependencies, ...p.devDependencies })) console.log(k);
')"

MISSING=0
COUNT=0
while IFS= read -r name; do
  [ -z "$name" ] && continue
  COUNT=$((COUNT + 1))
  if ! grep -qxF "$name" <<< "$DEP_KEYS"; then
    echo "❌ 执行力缺失: expo.plugins 声明 \"$name\" 但 package.json dependencies/devDependencies 均无此依赖" >&2
    echo "   config plugin 加载无源, 插件承载的原生配置静默缺失, prebuild/上架/运行时才暴露" >&2
    echo "   处置: npx expo install $name 补齐依赖, 或从 expo.plugins 移除声明 (声明侧↔供给侧必须成对)" >&2
    MISSING=$((MISSING + 1))
  fi
done <<< "$PLUGIN_NAMES"

if [ "$MISSING" -gt 0 ]; then
  echo "❌ expo.plugins ↔ package.json 依赖对账失败: $MISSING/$COUNT 个插件声明无依赖供给" >&2
  exit 1
fi

echo "✅ expo.plugins ↔ package.json 依赖对账通过: $COUNT 个插件声明全部有依赖供给 (声明侧↔供给侧成对)"
