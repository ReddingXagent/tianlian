#!/usr/bin/env bash
# versionCode ↔ buildNumber 数值配对守卫 (F315, F224族 同语义双源值级)
# app.json expo.android.versionCode (int) 与 expo.ios.buildNumber (string/int) 是同一语义的双源:
#   - 两者都是"同一 app 版本的构建序号", Play/App Store 各自递增
#   - 发版必须两侧同步棘轮; 只改一侧 → 双平台二进制构建序号分叉,
#     排障/灰度对照失真 (最恶=静默: 两侧各自构建全过, 商店版本号对账时才暴露)
# F288 只断言两键存在性(合法正整数), 数值配对是盲区
# 归一化: buildNumber 可为数字字符串, 正则同形校验后精确相等; 双侧 ≥1 活性断言(F306, 防豁免吞断言)
# 缺输入不放行 (F212)
set -euo pipefail

cd "$(dirname "$0")/.."

APP="app.json"

if [ ! -f "$APP" ]; then
  echo "❌ 缺少输入文件: $APP (缺输入不放行)" >&2
  exit 1
fi

VERSION_CODE="$(node -p 'String(require("./app.json").expo.android?.versionCode ?? "")')"
BUILD_NUMBER="$(node -p 'String(require("./app.json").expo.ios?.buildNumber ?? "")')"

if [ -z "$VERSION_CODE" ]; then
  echo "❌ 缺输入不放行: app.json 缺 expo.android.versionCode, 无法对账构建序号 (F212)" >&2
  exit 1
fi
if [ -z "$BUILD_NUMBER" ]; then
  echo "❌ 缺输入不放行: app.json 缺 expo.ios.buildNumber, 无法对账构建序号 (F212)" >&2
  exit 1
fi

if ! [[ "$VERSION_CODE" =~ ^[1-9][0-9]*$ ]]; then
  echo "❌ expo.android.versionCode 非法: \"$VERSION_CODE\" (须为正整数)" >&2
  exit 1
fi
if ! [[ "$BUILD_NUMBER" =~ ^[1-9][0-9]*$ ]]; then
  echo "❌ expo.ios.buildNumber 非法: \"$BUILD_NUMBER\" (须为正整数或数字字符串)" >&2
  exit 1
fi

if [ "$VERSION_CODE" != "$BUILD_NUMBER" ]; then
  echo "❌ 构建序号漂移: android.versionCode=$VERSION_CODE vs ios.buildNumber=$BUILD_NUMBER" >&2
  echo "   两者是同一语义双源(构建序号), 发版时必须两侧同步棘轮, 否则双平台版本对账失真" >&2
  exit 1
fi

echo "✅ 构建序号配对一致: versionCode=$VERSION_CODE buildNumber=$BUILD_NUMBER"
