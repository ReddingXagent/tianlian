#!/usr/bin/env bash
# app.json android.package ↔ ios.bundleIdentifier 跨平台身份一致性守卫 (F354, 构建守卫族第十九枚)
# android.package (Play Store 应用身份) 与 ios.bundleIdentifier (App Store 应用身份) 是同一语义的双源:
#   - 两者都代表"这个 App 的唯一身份标识", 各平台商店/推送/OAuth/深度链接 均以此为锚
#   - 只改一侧 → 双平台身份分叉: 同一 App 在 Android/iOS 被识别为不同应用,
#     推送通知凭证/ OAuth 回调 URI / 深度链接 schema 各平台静默失效
#     (构建全过, 运行时才暴露, 排障失锚 — F224 同族静默漂移最恶形态)
# F309 品牌色守卫管"视觉双源一致", 本守卫管"身份双源一致", 同文件内双源形态
# 当前基线两侧均 "com.tianlian.operator"; 域名反转格式(REV-DNS)是跨平台惯例
# 缺输入/提取空/不一致 → exit 1 (F212 不放行)
set -euo pipefail

cd "$(dirname "$0")/.."

APP="app.json"

if [ ! -f "$APP" ]; then
  echo "❌ 缺少输入文件: $APP (缺输入不放行)" >&2
  exit 1
fi

ANDROID_PKG="$(node -p 'String(require("./app.json").expo.android?.package ?? "")')"
IOS_BID="$(node -p 'String(require("./app.json").expo.ios?.bundleIdentifier ?? "")')"

if [ -z "$ANDROID_PKG" ]; then
  echo "❌ 缺输入不放行: app.json 缺 expo.android.package, 无法对账跨平台身份 (F212)" >&2
  echo "   处置: 显式声明 android.package (REV-DNS 格式, 如 com.tianlian.operator)" >&2
  exit 1
fi
if [ -z "$IOS_BID" ]; then
  echo "❌ 缺输入不放行: app.json 缺 expo.ios.bundleIdentifier, 无法对账跨平台身份 (F212)" >&2
  echo "   处置: 显式声明 ios.bundleIdentifier (REV-DNS 格式, 如 com.tianlian.operator)" >&2
  exit 1
fi

if [ "$ANDROID_PKG" != "$IOS_BID" ]; then
  echo "❌ 跨平台身份漂移: android.package=$ANDROID_PKG ↔ ios.bundleIdentifier=$IOS_BID 不一致" >&2
  echo "   双平台 App 身份分叉, 推送/OAuth/深度链接各平台静默失效(构建全过运行时才暴露)" >&2
  echo "   处置: 两侧同步为同一 REV-DNS 身份标识" >&2
  exit 1
fi

echo "✅ 跨平台身份一致: android.package=$ANDROID_PKG ↔ ios.bundleIdentifier=$IOS_BID"
exit 0
