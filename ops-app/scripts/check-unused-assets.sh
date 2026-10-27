#!/usr/bin/env bash
# assets磁盘 ↔ 引用源 反向对账守卫 (F327, 第十六枚)
# assets/ 目录下每个文件必须被至少一个引用源引用:
#   - 引用源1: app.json 资产字段 (icon / favicon / splash.image / adaptiveIcon.foregroundImage / backgroundImage)
#   - 引用源2: 代码 require (require('...assets/xxx.png') 形态, 任意相对深度)
# 死资产 = 最恶漂移: 开发者误以为资产生效去修改它(如换图标), 而构建实际不读它,
# 发版后"图标没更新"排障失锚; 同时死资产静默增大仓库体积。
# (正向 引用→磁盘存在 已由 jest appConfig.test.ts 覆盖, 本守卫补反向 磁盘→引用)
# 缺输入不放行 (F212); 引用源提取空=提取逻辑失效不放行 (活性断言 F306)
set -euo pipefail

cd "$(dirname "$0")/.."

APP="app.json"
ASSETS_DIR="assets"

if [ ! -f "$APP" ]; then
  echo "❌ 缺少输入文件: $APP (缺输入不放行)" >&2
  exit 1
fi
if [ ! -d "$ASSETS_DIR" ]; then
  echo "❌ 缺少输入目录: $ASSETS_DIR (缺输入不放行)" >&2
  exit 1
fi

# 引用源1: app.json 资产字段 (归一化为 assets/xxx 相对路径)
APP_REFS="$(node -p '
  const expo = require("./app.json").expo || {};
  const paths = [];
  if (expo.icon) paths.push(expo.icon);
  if (expo.favicon) paths.push(expo.favicon);
  if (expo.splash && expo.splash.image) paths.push(expo.splash.image);
  const ai = (expo.android || {}).adaptiveIcon || {};
  if (ai.foregroundImage) paths.push(ai.foregroundImage);
  if (ai.backgroundImage) paths.push(ai.backgroundImage);
  paths.map((p) => p.replace(/^\.\//, "")).sort().join("\n");
')"
if [ -z "$APP_REFS" ]; then
  echo "❌ app.json 资产引用提取空: 提取逻辑失效或配置为空 (提取空不放行)" >&2
  exit 1
fi

# 引用源2: 代码 require (任意相对深度归一化为 assets/xxx)
CODE_REFS="$(grep -rhoE "require\(['\"][^'\"]*assets/[A-Za-z0-9_./-]+['\"]\)" src app 2>/dev/null \
  | sed -E "s/^require\(['\"]//; s/['\"]\)\$//; s|.*assets/|assets/|" | sort -u || true)"

REFS="$(printf '%s\n%s\n' "$APP_REFS" "$CODE_REFS" | grep -v '^$' | sort -u)"

# 反向对账: 磁盘每个文件必须被引用
FAIL=0
DISK_COUNT=0
while IFS= read -r f; do
  DISK_COUNT=$((DISK_COUNT + 1))
  if ! grep -qxF "$f" <<< "$REFS"; then
    echo "❌ 死资产: $f 无任何引用 (app.json 资产字段与代码 require 均未命中)" >&2
    FAIL=1
  fi
done < <(find "$ASSETS_DIR" -type f | sort)

if [ "$FAIL" -ne 0 ]; then
  echo "   处置: 纳入引用源(app.json 加字段 / 代码 require), 或确认无用后删除死资产" >&2
  exit 1
fi

echo "✅ assets磁盘 ↔ 引用源 反向对账通过: $DISK_COUNT 个资产文件全部被引用"
