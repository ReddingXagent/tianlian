#!/usr/bin/env bash
# eas.json构建期env ↔ .env.example模板 双源对账守卫 (F342, 构建族第十八枚)
# 读取侧: eas.json build.*.env 声明 (EAS云端构建期注入, EXPO_PUBLIC_*同样烤入bundle)
# 模板侧: .env.example 键值清单 (部署者照抄模板, 本地构建env来源)
# 漂移后果: EAS云端构建与本地构建内联env不一致 — 同一份代码两个构建产物行为漂移,
#           且部署者照模板配本地env与云端产物静默分叉(F295同族静默no-op最恶漂移)
# 不变量A: eas.json各profile env中 EXPO_PUBLIC_* 键 ⊆ .env.example 键清单 (键登记)
# 不变量B: 已登记键值级对账 — eas.json值 == .env.example值 (F256值级对账语义第三源扩展:
#          F256管代码fallback↔模板双源, 本守卫管eas.json云端注入↔模板双源)
# 非EXPO_PUBLIC_*键(构建凭据类, 走EAS secrets)不要求登记模板——登记会与F256死键断言冲突
# 基线守卫先行: 当前三profile env均为空(零命中), 门禁防未来env注入欠账(F330同形态)
# 缺输入/提取异常/集合越界/值漂移均exit1 (F212不放行)
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

EAS_JSON="eas.json"
ENV_EXAMPLE=".env.example"

for f in "$EAS_JSON" "$ENV_EXAMPLE"; do
  if [ ! -f "$f" ]; then
    echo "FAIL: $f 不存在(缺输入不放行, F212)"
    exit 1
  fi
done

# 模板侧键值 (跳过注释与空行)
template_pairs=$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_EXAMPLE" || true)
template_keys=$(printf '%s\n' "$template_pairs" | grep -E '^[A-Za-z_]' | cut -d= -f1 | sort -u || true)
if [ -z "$template_keys" ]; then
  echo "FAIL: $ENV_EXAMPLE 未提取到有效键"
  exit 1
fi

# 读取侧: eas.json build.*.env 全部键值对 (profile名透传用于报错定位)
# 提取空是合法态(基线零命中, F330守卫先行形态) — 不FAIL
eas_env_lines=$(node -e '
  const fs = require("fs");
  let cfg;
  try {
    cfg = JSON.parse(fs.readFileSync("eas.json", "utf8"));
  } catch (e) {
    console.error("PARSE_FAIL");
    process.exit(3);
  }
  const build = cfg.build || {};
  for (const [profile, body] of Object.entries(build)) {
    const env = (body && body.env) || {};
    for (const [k, v] of Object.entries(env)) {
      if (typeof v !== "string") { console.error("PARSE_FAIL"); process.exit(3); }
      console.log(profile + "\t" + k + "\t" + v);
    }
  }
') || {
  rc=$?
  if [ "$rc" -eq 3 ]; then
    echo "FAIL: $EAS_JSON 解析失败或env值非字符串"
    exit 1
  fi
  echo "FAIL: $EAS_JSON 提取异常(exit $rc)"
  exit 1
}

fail=0

while IFS=$'\t' read -r profile k v; do
  [ -n "$k" ] || continue
  case "$k" in
    EXPO_PUBLIC_*) ;;
    *) continue ;;  # 构建凭据类走EAS secrets, 不要求登记模板(与F256死键断言边界互斥)
  esac
  # 不变量A: 键登记
  if ! grep -qx "$k" <<<"$template_keys"; then
    echo "FAIL: eas.json build.$profile.env 声明 $k 但 $ENV_EXAMPLE 未登记 (云端内联env绕过部署者模板→本地/云端构建静默分叉)"
    fail=1
    continue
  fi
  # 不变量B: 值级对账
  tv=$(grep -E "^$k=" "$ENV_EXAMPLE" | head -1 | cut -d= -f2-)
  if [ "$v" != "$tv" ]; then
    echo "FAIL: $k 值漂移 — eas.json build.$profile.env='$v' vs $ENV_EXAMPLE='$tv'"
    fail=1
  fi
done <<<"$eas_env_lines"

if [ "$fail" -ne 0 ]; then
  exit 1
fi

count=$(printf '%s\n' "$eas_env_lines" | grep -c $'\tEXPO_PUBLIC_' || true)
echo "OK: eas.json env↔$ENV_EXAMPLE 对账通过 (EXPO_PUBLIC_*注入键 $count 枚, 基线空=守卫先行)"
