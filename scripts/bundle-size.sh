#!/usr/bin/env bash
# bundle-size.sh — JS bundle 体积门控
# 用法: ./scripts/bundle-size.sh [android导出目录] [ios导出目录]
# 默认目录: /tmp/ops-export-android /tmp/ops-export-ios (见 Makefile export-* 目标)
# 基线 (2026-08): android 2.29MB / ios 2.29MB (hbc)
# 阈值: WARN_MB=2.75 (+20%), FAIL_MB=3.5; 超WARN警告, 超FAIL退出码1
set -euo pipefail

WARN_MB=${WARN_MB:-2.75}
FAIL_MB=${FAIL_MB:-3.5}
ANDROID_DIR=${1:-/tmp/ops-export-android}
IOS_DIR=${2:-/tmp/ops-export-ios}

check_one() {
  local platform=$1 dir=$2
  if [ ! -d "$dir" ]; then
    echo "[$platform] 跳过: $dir 不存在 (先跑 make export-$platform)"
    return 0
  fi
  local hbc
  hbc=$(find "$dir/_expo/static/js" -name '*.hbc' 2>/dev/null | head -1)
  if [ -z "$hbc" ]; then
    echo "[$platform] 未找到 .hbc bundle, 导出可能不完整 → FAIL"
    return 1
  fi
  local bytes mb
  bytes=$(stat -c%s "$hbc")
  mb=$(awk "BEGIN{printf \"%.2f\", $bytes/1048576}")
  local status="OK"
  local rc=0
  if awk "BEGIN{exit !($mb > $FAIL_MB)}"; then
    status="FAIL(>$FAIL_MB MB)"; rc=1
  elif awk "BEGIN{exit !($mb > $WARN_MB)}"; then
    status="WARN(>$WARN_MB MB)"
  fi
  echo "[$platform] $mb MB ($bytes B) — $status"
  return $rc
}

overall=0
check_one android "$ANDROID_DIR" || overall=1
check_one ios "$IOS_DIR" || overall=1
if [ $overall -eq 0 ]; then
  echo "bundle-size 门控通过 (WARN>${WARN_MB}MB, FAIL>${FAIL_MB}MB)"
fi
exit $overall
