#!/usr/bin/env bash
# app.json品牌色双源漂移守卫 (F309, 构建守卫族第十三枚)
# splash.backgroundColor(启动屏背景) 与 android.adaptiveIcon.backgroundColor
# (Android启动器图标背景) 是同一品牌色的同文件内双源声明(F224同族形态):
#   - 只改一侧即漂移: 启动屏品牌蓝而图标背景另一色, 用户从启动屏进入主屏
#     观感断裂, 且无任何构建/运行时报错(纯视觉静默漂移)
#   - 本仓基线两侧均声明品牌色, 任一侧缺失视为漂移或提取器盲区(F306活性断言)
# 比较前归一化小写(hex色大小写等价); 缺输入不放行 (F212)
set -euo pipefail

cd "$(dirname "$0")/.."

APP="app.json"

if [ ! -f "$APP" ]; then
  echo "❌ 缺少输入文件: $APP (缺输入不放行)" >&2
  exit 1
fi

SPLASH_BG="$(node -p '((require("./app.json").expo.splash || {}).backgroundColor) || ""')"
ADAPTIVE_BG="$(node -p '(((require("./app.json").expo.android || {}).adaptiveIcon || {}).backgroundColor) || ""')"

# 活性断言: 本仓基线两侧均声明品牌色, 缺失即漂移或提取器盲区(F306形态)
if [ -z "$SPLASH_BG" ]; then
  echo "❌ 品牌色双源漂移: splash.backgroundColor 缺失 (本仓基线声明品牌色, 缺失=漂移或提取器盲区)" >&2
  exit 1
fi
if [ -z "$ADAPTIVE_BG" ]; then
  echo "❌ 品牌色双源漂移: android.adaptiveIcon.backgroundColor 缺失 (本仓基线声明品牌色, 缺失=漂移或提取器盲区)" >&2
  exit 1
fi

SPLASH_NORM="$(printf '%s' "$SPLASH_BG" | tr '[:upper:]' '[:lower:]')"
ADAPTIVE_NORM="$(printf '%s' "$ADAPTIVE_BG" | tr '[:upper:]' '[:lower:]')"

if [ "$SPLASH_NORM" != "$ADAPTIVE_NORM" ]; then
  echo "❌ 品牌色双源漂移: splash.backgroundColor=$SPLASH_BG ↔ android.adaptiveIcon.backgroundColor=$ADAPTIVE_BG 不一致" >&2
  echo "   启动屏与Android启动器图标背景品牌色分叉, 纯视觉静默漂移无报错" >&2
  echo "   处置: 两侧同步为同一品牌色" >&2
  exit 1
fi

echo "✅ 品牌色双源一致: splash.backgroundColor=$SPLASH_BG ↔ android.adaptiveIcon.backgroundColor=$ADAPTIVE_BG"
exit 0
