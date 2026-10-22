#!/usr/bin/env bash
# F379 测试套件活性守卫: jest收集套件数下限+路径域断言
# 动机: npm test脚本含--passWithNoTests, testMatch漂移致零收集时本地npm test静默exit0(F295族静默no-op);
# CI虽带--coverage有门限兜底, 但部分套件脱落(非全零)时覆盖率余量可能吞掉信号;
# 本守卫独立断言收集活性: 套件数≥54(基线F446上调; 原F372基线33自建守卫起即滞后实测54, 21套脱落盲区)且全部落在src/**/*.test.ts(x)合法域
set -e
cd "$(dirname "$0")/.."

MIN_SUITES=54

SUITES=$(npx jest --listTests 2>/dev/null) || { echo "❌ jest --listTests 执行失败(缺输入 F212)"; exit 1; }
COUNT=$(printf '%s\n' "$SUITES" | grep -c . || true)

if [ "$COUNT" -eq 0 ]; then
  echo "❌ 测试套件收集为零(--passWithNoTests静默放行形态, F295族)"
  exit 1
fi

if [ "$COUNT" -lt "$MIN_SUITES" ]; then
  echo "❌ 测试套件收集数异常: $COUNT < $MIN_SUITES (testMatch漂移或套件误删?)"
  exit 1
fi

BAD=$(printf '%s\n' "$SUITES" | grep -v 'src/.*\.test\.tsx\?$' || true)
if [ -n "$BAD" ]; then
  echo "❌ 收集到合法域外套件(必须src/**/*.test.ts|tsx):"
  printf '%s\n' "$BAD"
  exit 1
fi

echo "✅ 测试套件活性: $COUNT suites ≥ $MIN_SUITES, 全部落在src/**/*.test.ts(x)合法域"
