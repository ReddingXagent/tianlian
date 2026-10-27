#!/usr/bin/env bash
# 环境变量双源漂移守卫 (F256, F255模式自edge-gateway移植):
# 读取侧: 运行时代码 process.env.EXPO_PUBLIC_* 键 (权威源: 代码实际读什么)
# 模板侧: .env.example 键清单 (部署者照抄模板)
# 断言1: 双向对账 — 代码读了模板没登记=漏配静默吃默认值(F255同型), 模板残留代码不读的键=死键误导
# 断言2: 代码内联fallback字面量 == .env.example对应值 (同语义双源: env未设置时bundle烤入fallback,
#         EXPO_PUBLIC_*在expo export构建期内联, 构建时未设env→fallback即生产值, 两侧单独改任一侧即漂移)
# 缺输入/提取空/不等均exit1 (F212不放行)
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

ENV_EXAMPLE=".env.example"
if [ ! -f "$ENV_EXAMPLE" ]; then
  echo "FAIL: $ENV_EXAMPLE 不存在(缺输入不放行, F212)"
  exit 1
fi

# 模板侧键/值 (跳过注释与空行)
template_keys=$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_EXAMPLE" | cut -d= -f1 | sort -u)
if [ -z "$template_keys" ]; then
  echo "FAIL: $ENV_EXAMPLE 未提取到有效键"
  exit 1
fi

# 读取侧: 运行时src代码(排除__tests__), EXPO_PUBLIC_*为Expo构建期内联前缀
code_files=$(find src -type f \( -name '*.ts' -o -name '*.tsx' \) ! -path '*__tests__*')
if [ -z "$code_files" ]; then
  echo "FAIL: 未找到运行时代码文件"
  exit 1
fi
# shellcheck disable=SC2086
code_keys=$(grep -hoE 'process\.env\.EXPO_PUBLIC_[A-Z0-9_]+' $code_files \
  | sed 's/^process\.env\.//' | sort -u)
if [ -z "$code_keys" ]; then
  echo "FAIL: 运行时代码未提取到 process.env.EXPO_PUBLIC_* 读取"
  exit 1
fi

fail=0

# 断言1a: 代码读取键 ⊆ 模板键
while IFS= read -r k; do
  if ! grep -qx "$k" <<<"$template_keys"; then
    echo "FAIL: 代码读取 $k 但 $ENV_EXAMPLE 未登记 (部署者漏配→静默吃代码默认值)"
    fail=1
  fi
done <<<"$code_keys"

# 断言1b: 模板键 ⊆ 代码读取键 (死键)
while IFS= read -r k; do
  if ! grep -qx "$k" <<<"$code_keys"; then
    echo "FAIL: $ENV_EXAMPLE 中 $k 代码未读取 (死键误导)"
    fail=1
  fi
done <<<"$template_keys"

# 断言2: 内联fallback字面量 == 模板值
while IFS= read -r k; do
  # shellcheck disable=SC2086
  code_line=$(grep -h "process\.env\.$k" $code_files | head -1)
  fb=$(grep -oE "(\|\||\?\?) *'[^']*'" <<<"$code_line" | head -1 \
    | sed -E "s/^(\|\||\?\?) *'//; s/'\$//" || true)
  [ -n "$fb" ] || continue  # 无内联fallback的键不做值对账
  tv=$(grep -E "^$k=" "$ENV_EXAMPLE" | head -1 | cut -d= -f2-)
  if [ "$fb" != "$tv" ]; then
    echo "FAIL: $k fallback与模板值漂移 — 代码fallback='$fb' vs $ENV_EXAMPLE='$tv'"
    fail=1
  fi
done <<<"$code_keys"

if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "OK: env键双源一致 ($(wc -l <<<"$code_keys" | tr -d ' ')键, fallback值对账通过)"
