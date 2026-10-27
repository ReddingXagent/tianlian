#!/usr/bin/env bash
# assets体积上限守卫 (F334, F327死资产反向对账的同源进阶):
# F327管"磁盘⊆引用"(死资产), 本守卫管"体积不膨胀"(构建产物体积防线):
#   运维App走APK直装/二维码分发(F25/F33决策), 无商店侧体积审查兜底,
#   资产膨胀直接进APK与OTA差分包 → 单文件/总体积上限是唯一门禁。
# 断言1: assets/下每个文件 ≤ MAX_SINGLE_KB (512KB)
# 断言2: assets/总体积 ≤ MAX_TOTAL_KB (2048KB)
# 当前基线: splash 48KB / icon 12KB / adaptive-icon 12KB / 合计65KB(du -sk含目录块=76), 余量充足=守卫先行(F330形态)
# 缺输入(assets/不存在)/提取空/超限均exit1 (F212不放行)
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

MAX_SINGLE_KB=512
MAX_TOTAL_KB=2048
ASSETS_DIR="assets"

if [ ! -d "$ASSETS_DIR" ]; then
  echo "❌ FAIL: $ASSETS_DIR/ 目录不存在 (缺输入不放行, F212)" >&2
  exit 1
fi

# 枚举磁盘侧全部文件(不限扩展名: 字体/lottie json等未来资产同样进包)
files=$(find "$ASSETS_DIR" -type f)
if [ -z "$files" ]; then
  echo "❌ FAIL: $ASSETS_DIR/ 下未找到任何文件 (提取空不放行)" >&2
  exit 1
fi

fail=0
total_kb=0
while IFS= read -r f; do
  size_kb=$(( ( $(stat -c%s "$f") + 1023 ) / 1024 ))  # 向上取整KB
  total_kb=$(( total_kb + size_kb ))
  if [ "$size_kb" -gt "$MAX_SINGLE_KB" ]; then
    echo "❌ 单文件超限: $f ${size_kb}KB > ${MAX_SINGLE_KB}KB上限" >&2
    fail=1
  fi
done <<< "$files"

if [ "$total_kb" -gt "$MAX_TOTAL_KB" ]; then
  echo "❌ 总体积超限: ${total_kb}KB > ${MAX_TOTAL_KB}KB上限" >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "❌ assets体积上限守卫未通过 (单文件≤${MAX_SINGLE_KB}KB, 总≤${MAX_TOTAL_KB}KB)" >&2
  exit 1
fi

echo "✅ assets体积上限守卫通过: $(echo "$files" | wc -l)个文件, 总${total_kb}KB (单文件≤${MAX_SINGLE_KB}KB, 总≤${MAX_TOTAL_KB}KB)"
