#!/usr/bin/env bash
# 未使用依赖守卫 (F262) — 构建维度死依赖门控
# package.json dependencies(生产依赖) 每项必须满足三种使用形态之一, 否则为死依赖:
#   1. 代码 import/require 引用 (src/**, App.tsx, 根级配置js — git ls-files ts/tsx/js, 排除 scripts/)
#   2. app.json expo.plugins 配置插件引用 (expo-* 原生配置型: 零代码import, 构建期config plugin注入原生配置)
#   3. 运行时隐式原生依赖白名单 (native bridge自动链接型: 如react-navigation的react-native-screens, 零代码import)
# 死依赖危害: 安装体积/原生构建面/audit攻击面增大 + 依赖树误导(升级评审为不存在的依赖花时间)
# RN仓未使用依赖识别两类型 = config plugin + 原生桥 (F224摸底固化)
# 只守 dependencies 不守 devDependencies: dev侧由工具链配置(babel/eslint/jest/tsconfig)消费, 静态口径噪音大;
# 生产依赖直接进bundle与原生工程, 口径清晰零误报
# 缺输入不放行 / 提取空不放行 (F212)
set -euo pipefail

cd "$(dirname "$0")/.."

PKG="package.json"
APPJSON="app.json"

for f in "$PKG" "$APPJSON"; do
  if [ ! -f "$f" ]; then
    echo "❌ 缺少输入文件: $f (缺输入不放行)" >&2
    exit 1
  fi
done

# 生产依赖全集 (声明侧/权威源)
DEPS="$(node -p 'Object.keys(require("./package.json").dependencies || {}).sort().join("\n")')"
if [ -z "$DEPS" ]; then
  echo "❌ package.json 无 dependencies, 无法对账 (提取空不放行)" >&2
  exit 1
fi

# 使用形态2: app.json expo.plugins 引用集 (插件项可为 "name" 或 ["name", opts])
PLUGINS="$(node -p '(require("./app.json").expo.plugins || []).map(x => Array.isArray(x) ? x[0] : x).join("\n")')"

# 使用形态3: 运行时隐式原生依赖白名单 — dep=原因 (每项必须带原因, 禁空条目)
ALLOWLIST="react-native-screens=@react-navigation运行时原生桥(enableScreens由navigation自动初始化, 零代码import, 移除=导航运行期崩溃);expo=Expo框架CLI/运行时(经package.json scripts的expo start/export等命令消费, 零代码import, 移除=工程不可运行);@expo/metro-runtime=expo web运行时(async-chunk/import.meta注册, app.json platforms含web后由expo/metro隐式消费, 零代码import, 移除=web调试通道崩溃, 352972c);react-dom=web平台DOM渲染宿主(react-native-web的peer运行时, 零代码import, 移除=web构建崩溃, 352972c);react-native-web=RN转Web别名层(app.json platforms含web后由expo模块别名隐式消费, 零代码import, 移除=web构建崩溃, 352972c)"

# 使用形态1的检索文件集: 全部受版控 ts/tsx/js, 排除 scripts/ (守卫脚本自身含dep字面量会自引用误报)
FILES="$(git ls-files '*.ts' '*.tsx' '*.js' | grep -v '^scripts/' || true)"
if [ -z "$FILES" ]; then
  echo "❌ git ls-files 未提取到任何源码文件 (提取空不放行)" >&2
  exit 1
fi

unused=""
while IFS= read -r dep; do
  [ -z "$dep" ] && continue

  # 形态1: 代码 import/require (含子路径 dep/xxx)
  # shellcheck disable=SC2086
  if printf '%s\n' $FILES | xargs grep -lE "(from|require\()[ '\"]*${dep}(['\"/])" >/dev/null 2>&1; then
    continue
  fi

  # 形态2: app.json plugins 配置插件引用
  if printf '%s\n' "$PLUGINS" | grep -qxF "$dep"; then
    continue
  fi

  # 形态3: 运行时隐式白名单
  if printf '%s\n' "$ALLOWLIST" | tr ';' '\n' | grep -q "^${dep}="; then
    continue
  fi

  unused="${unused}${dep}\n"
done <<< "$DEPS"

if [ -n "$unused" ]; then
  echo "❌ 发现未使用生产依赖 (零代码import + 零plugins引用 + 不在隐式白名单):" >&2
  printf "$unused" >&2
  echo "   处置: 确认无用→npm uninstall 移除; 属配置插件→登记app.json plugins; 属原生桥隐式依赖→白名单加原因" >&2
  exit 1
fi

echo "✅ 未使用依赖守卫: $(printf '%s\n' "$DEPS" | wc -l) 个生产依赖全部有使用形态 (import/plugins/隐式白名单)"
