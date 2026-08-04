#!/usr/bin/env bash
# bundle-size.sh — JS bundle 体积门控
# 用法: ./scripts/bundle-size.sh [android导出目录] [ios导出目录]
# 默认目录: /tmp/ops-export-android /tmp/ops-export-ios (见 Makefile export-* 目标)
# 基线 (2026-08-04): android 2.19MB / ios 2.18MB (hbc, 实测)
# 注: 按 <dir>/_expo/static/js/<platform>/ 定位平台子目录, 同目录双平台(如dist/)也能正确区分
# 阈值: WARN_MB=2.75 (+20%), FAIL_MB=3.5; 超WARN警告, 超FAIL退出码1
# 缺目录语义 (F212): check_one 返回2=目录缺失; 单平台缺失也FAIL(门控要求双平台齐验,
#   防"只导出了一个平台就静默通过"的漏测); 双缺同样FAIL
set -euo pipefail

WARN_MB=${WARN_MB:-2.75}
FAIL_MB=${FAIL_MB:-3.5}
ANDROID_DIR=${1:-/tmp/ops-export-android}
IOS_DIR=${2:-/tmp/ops-export-ios}

check_one() {
  local platform=$1 dir=$2
  if [ ! -d "$dir" ]; then
    echo "[$platform] 缺失: $dir 不存在 (先跑 make export-$platform)"
    return 2
  fi
  local hbc
  hbc=$(find "$dir/_expo/static/js/$platform" -name '*.hbc' 2>/dev/null | head -1)
  if [ -z "$hbc" ]; then
    # 兼容旧导出布局(无平台子目录): 仅当目录内只有一个hbc时才允许兜底
    local fallback
    fallback=$(find "$dir/_expo/static/js" -name '*.hbc' 2>/dev/null)
    if [ "$(echo "$fallback" | grep -c .)" = "1" ]; then
      hbc=$fallback
    else
      echo "[$platform] 未在 $dir/_expo/static/js/$platform 找到 .hbc bundle, 导出可能不完整 → FAIL"
      return 1
    fi
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
missing=0
rc_a=0; check_one android "$ANDROID_DIR" || rc_a=$?
rc_i=0; check_one ios "$IOS_DIR" || rc_i=$?
if [ $rc_a -eq 1 ]; then overall=1; fi
if [ $rc_i -eq 1 ]; then overall=1; fi
if [ $rc_a -eq 2 ]; then missing=$((missing+1)); fi
if [ $rc_i -eq 2 ]; then missing=$((missing+1)); fi
if [ $missing -eq 2 ]; then
  echo "两个导出目录都不存在 → 门控无对象可测, FAIL (先跑 make export-android export-ios)"
  overall=1
elif [ $missing -eq 1 ]; then
  echo "仅一个平台有导出目录 → 门控不完整, FAIL (F212: 双平台齐验, 防单平台静默漏测; 先补齐 make export-android export-ios)"
  overall=1
fi
if [ $overall -eq 0 ]; then
  echo "bundle-size 门控通过 (WARN>${WARN_MB}MB, FAIL>${FAIL_MB}MB)"
fi
exit $overall
