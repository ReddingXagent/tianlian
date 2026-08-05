#!/usr/bin/env bash
# F287: Python 最低版本多源一致性守卫 (部署守卫族第九枚)
#
# 背景: 运行时最低 Python 版本 3.10 (Pi 生产环境) 散布在七类声明源, 零断言:
#   执行侧(权威): deploy.sh `[ "$PY_MINOR" -lt 10 ]` 预检
#   声明侧:
#     deploy.sh        "需要 Python 3.10+" / "< 3.10" 提示 (同文件双声明, F267族)
#     ci.yml           python-version: "3.10" (CI 运行时)
#     Dockerfile       FROM python:3.10-slim (容器运行时)
#     pyproject.toml   ruff target-version = "py310" (lint 基线)
#     DEPLOYMENT.md    "低于 3.10 告警"
#     README.md        "Python 3.10+" / "Python ≥ 3.10" / "ruff target pyXXX" 转述
#
# 漂移后果: 任一侧单独 bump (如 CI/Dockerfile 升 3.12 而 deploy.sh 仍 3.10) →
#   新解释器放行的 3.11+ 语法/标准库 (如 datetime.UTC, pyproject 已为此显式 ignore UP017)
#   在 Pi 3.10 运行时崩溃; README 转述漂移 (本轮实测撞 py313 旧数字) 误导部署者
#   装错解释器或误判 lint 基线。
#
# 断言: 七类源提取的 minor 版本集合全部相等; 缺输入/提取空/不一致均 exit 1 (F212不放行)。
# 接入 make check + CI。
set -euo pipefail
cd "$(dirname "$0")/.."

fail() { echo "❌ [check-python-version] $1" >&2; exit 1; }

CI=.github/workflows/ci.yml
DOCKERFILE=Dockerfile
PYPROJECT=pyproject.toml
DEPLOY_SH=deploy.sh
DEPLOY_MD=DEPLOYMENT.md
README=README.md

for f in "$CI" "$DOCKERFILE" "$PYPROJECT" "$DEPLOY_SH" "$DEPLOY_MD" "$README"; do
    [ -f "$f" ] || fail "缺输入: $f"
done

# 收集 "源名<TAB>minor" 对; $1=源名 $2=minor候选列表(每行一个)
pairs=""
collect() {
    local name="$1" vals="$2"
    [ -n "$vals" ] || fail "提取空: $name 未找到 Python 版本声明"
    while IFS= read -r v; do
        pairs="${pairs}${name}	${v}
"
    done <<< "$vals"
}

# ci.yml: python-version: "3.10" → minor
collect "$CI" "$(grep -oE 'python-version: *"?[0-9]+\.[0-9]+' "$CI" \
    | grep -oE '[0-9]+\.[0-9]+' | sed 's|^[0-9]*\.||' | sort -u)"

# Dockerfile: FROM ... python:3.10-slim → minor
collect "$DOCKERFILE" "$(grep -E '^FROM' "$DOCKERFILE" \
    | grep -oE 'python:[0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' \
    | sed 's|^[0-9]*\.||' | sort -u)"

# pyproject.toml: target-version = "py310" → 310 % 100 = minor
collect "$PYPROJECT" "$(grep -oE 'target-version *= *"py[0-9]+"' "$PYPROJECT" \
    | grep -oE '[0-9]+' | awk '{print $1 % 100}' | sort -u)"

# deploy.sh 执行侧(权威): [ "$PY_MINOR" -lt 10 ]
collect "$DEPLOY_SH(执行预检)" "$(grep -oE 'PY_MINOR" -lt [0-9]+' "$DEPLOY_SH" \
    | grep -oE '[0-9]+$' | sort -u)"

# deploy.sh 提示侧: "需要 Python 3.10+" / "< 3.10"
collect "$DEPLOY_SH(提示)" "$(grep -oE '(需要 Python|< )3\.[0-9]+' "$DEPLOY_SH" \
    | grep -oE '3\.[0-9]+$' | sed 's|^3\.||' | sort -u)"

# DEPLOYMENT.md: "低于 3.10 告警"
collect "$DEPLOY_MD" "$(grep -oE '低于 ?3\.[0-9]+' "$DEPLOY_MD" \
    | grep -oE '3\.[0-9]+' | sed 's|^3\.||' | sort -u)"

# README.md: "Python 3.10+" / "Python ≥ 3.10" + "py3NN" 转述(ruff target 声明)
readme_minors="$( { grep -oE 'Python (≥ ?)?3\.[0-9]+' "$README" \
        | grep -oE '3\.[0-9]+' | sed 's|^3\.||' || true; \
    grep -oE 'py3[0-9]{2}' "$README" | sed 's|^py3||' || true; } | sort -u)"
collect "$README" "$readme_minors"

# 全部 minor 必须相等
uniq_vals="$(printf '%s' "$pairs" | awk -F'\t' '{print $2}' | sort -u)"
uniq_count="$(printf '%s\n' "$uniq_vals" | grep -c . || true)"
if [ "$uniq_count" -ne 1 ]; then
    echo "❌ Python 版本多源漂移(F287): 各声明源 minor 不一致 → 新解释器放行高版本语法在Pi运行时崩溃/部署者被误导" >&2
    printf '%s' "$pairs" | awk -F'\t' '{print "   " $1 " → " $2}' >&2
    exit 1
fi

echo "✅ Python 版本多源一致(F287): ci.yml+Dockerfile+pyproject+deploy.sh(执行+提示)+DEPLOYMENT.md+README.md 共 $(printf '%s' "$pairs" | grep -c .) 处声明全部为 3.$(printf '%s\n' "$uniq_vals" | head -1)"
