#!/usr/bin/env bash
# check-ci-parity.sh — 实际CI门控链 ↔ make ci-local 本地模拟双源漂移守卫
#
# 背景: Makefile ci-local 定位"模拟 CI 全流程", .github/workflows/ci.yml 是实际CI门控链,
#   两者分文件维护同一语义(全量检查跑哪些门控)零断言。
# 漂移后果: ①CI新增门控未同步ci-local → 本地全绿≠CI绿(本地漏测, 隐性)
#           ②ci-local多出门控 → 本地白跑/误严(显性但噪音)
# 不变量: 归一化后的 CI run门控集合 == ci-local 递归展开门控集合。
# 归一化规则:
#   npm run X ...   → X
#   npm test ...    → test   (--ci/--reporters 等参数差不改门控语义, 归一为同一门控)
#   ./scripts/X.sh  → scripts/X.sh (参数剥除)
#   npm ci          → 基础设施步骤, 不计门控
#   其他未识别形态  → exit 1 (宁可 loud fail 不可静默漏计, F212 同族)
# 缺输入/提取空/集合不等 → exit 1
set -euo pipefail
cd "$(dirname "$0")/.."

CI=".github/workflows/ci.yml"
MK="Makefile"

[ -f "$CI" ] || { echo "❌ 缺输入: $CI 不存在"; exit 1; }
[ -f "$MK" ] || { echo "❌ 缺输入: $MK 不存在"; exit 1; }

# 归一化一条 run 命令(已剥 "- run:" 前缀); 未识别形态输出 UNKNOWN
norm_step() {
  local line="$1"
  case "$line" in
    "npm ci") echo "" ;;
    "npm run "*) echo "${line#npm run }" | awk '{print $1}' ;;
    "npm test"*) echo "test" ;;
    "./scripts/"*) echo "${line%% *}" | sed 's|^\./||' ;;
    *) echo "UNKNOWN" ;;
  esac
}

# ---- CI侧: 提取所有 "- run:" 步骤 ----
ci_gates=""
while IFS= read -r step; do
  g=$(norm_step "$step")
  if [ "$g" = "UNKNOWN" ]; then
    echo "❌ CI 出现未识别门控形态(归一化规则需扩展): $step"; exit 1
  fi
  [ -n "$g" ] && ci_gates+="$g"$'\n'
done < <(sed -nE 's/^[[:space:]]*- run:[[:space:]]*//p' "$CI")
[ -n "$ci_gates" ] || { echo "❌ CI 门控提取为空: $CI"; exit 1; }
ci_gates=$(printf '%s' "$ci_gates" | sort -u)

# ---- Makefile侧: 从 ci-local 递归展开 ----
mk_prereqs() {  # target → 前置目标列表(剥尾注释)
  sed -nE "s/^$1:([^#]*).*$/\1/p" "$MK" | tr ' ' '\n' | grep -v '^$' || true
}
mk_recipe() {   # target → 首条配方行(聚合目标无配方返回空)
  awk -v t="$1" '
    $0 ~ "^"t":" { found=1; next }
    found && /^\t/ { sub(/^\t/,""); print; exit }
    found && /^[^\t[:space:]]/ { exit }
  ' "$MK"
}

mk_gates=""
queue=(ci-local)
seen=" "
ci_local_found=0
while [ ${#queue[@]} -gt 0 ]; do
  t="${queue[0]}"
  queue=("${queue[@]:1}")
  case "$seen" in *" $t "*) continue ;; esac
  seen+="$t "
  [ "$t" = "ci-local" ] && ci_local_found=1
  recipe=$(mk_recipe "$t")
  if [ -n "$recipe" ]; then
    g=$(norm_step "$recipe")
    if [ "$g" = "UNKNOWN" ]; then
      echo "❌ Makefile 目标 $t 配方为未识别门控形态(归一化规则需扩展): $recipe"; exit 1
    fi
    [ -n "$g" ] && mk_gates+="$g"$'\n'
  else
    prereqs=$(mk_prereqs "$t" | tr '\n' ' ')
    if [ -z "${prereqs// /}" ]; then
      echo "❌ Makefile 目标 $t 既无配方也无前置, 无法展开"; exit 1
    fi
    read -ra ps <<< "$prereqs"
    queue+=("${ps[@]}")
  fi
done
[ "$ci_local_found" = "1" ] || { echo "❌ Makefile 缺少 ci-local 目标"; exit 1; }
[ -n "$mk_gates" ] || { echo "❌ ci-local 门控展开为空"; exit 1; }
mk_gates=$(printf '%s' "$mk_gates" | sort -u)

# ---- 对账 ----
only_ci=$(comm -23 <(echo "$ci_gates") <(echo "$mk_gates"))
only_mk=$(comm -13 <(echo "$ci_gates") <(echo "$mk_gates"))
if [ -n "$only_ci" ] || [ -n "$only_mk" ]; then
  echo "❌ CI门控链 ↔ ci-local 漂移:"
  [ -n "$only_ci" ] && { echo "  CI有/ci-local无: $(echo "$only_ci" | tr '\n' ' ')"; }
  [ -n "$only_mk" ] && { echo "  ci-local有/CI无: $(echo "$only_mk" | tr '\n' ' ')"; }
  exit 1
fi
echo "✅ CI门控链 ↔ ci-local 一致 ($(echo "$ci_gates" | grep -c .) 门控: $(echo "$ci_gates" | tr '\n' ' '))"
