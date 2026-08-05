#!/usr/bin/env bash
# .gitignore↔.easignore 敏感文件排除超集守卫 (F321, 构建守卫族第十五枚)
# .gitignore 声明的敏感文件排除模式 (.env / *.jks / *.keystore 凭据类) 必须被
# .easignore 完整覆盖 (F224同族双源对账形态, 这里语义是"超集"而非"相等"):
#   - EAS 云端构建按 .easignore 决定上传范围, 与 .gitignore 是两条独立管线
#   - 只改 .gitignore 新增敏感排除而 .easignore 不同步即漂移: 本地 git 不见的
#     凭据文件会被 EAS 原样上传云端构建集群, 无任何报错 (静默泄露, 最恶漂移形态)
# 活性断言 (F306): 本仓基线 .gitignore 声明全部三类敏感模式, 缺失=漂移或提取器盲区
# 缺输入不放行 (F212)
set -euo pipefail

cd "$(dirname "$0")/.."

GITIGNORE=".gitignore"
EASIGNORE=".easignore"

for f in "$GITIGNORE" "$EASIGNORE"; do
  if [ ! -f "$f" ]; then
    echo "❌ 缺少输入文件: $f (缺输入不放行)" >&2
    exit 1
  fi
done

# 凭据类敏感模式清单 (与 .gitignore 基线声明逐一对账)
SECRETS_PATTERNS=".env
*.jks
*.keystore"

fail=0

while IFS= read -r pat; do
  # 活性断言: .gitignore 基线必须声明该模式, 缺失=基线漂移或清单过期
  if ! grep -qxF "$pat" "$GITIGNORE"; then
    echo "❌ 敏感模式对账失败: $pat 在 $GITIGNORE 缺失 (本仓基线声明该模式, 缺失=漂移或提取器盲区)" >&2
    fail=1
    continue
  fi
  # 超集断言: .easignore 必须覆盖同一模式, 否则云端构建上传范围泄露
  if ! grep -qxF "$pat" "$EASIGNORE"; then
    echo "❌ .easignore 未覆盖敏感模式: $pat (.gitignore 已排除但 EAS 云端构建会上传该类文件)" >&2
    fail=1
  fi
done <<< "$SECRETS_PATTERNS"

if [ "$fail" -ne 0 ]; then
  exit 1
fi

echo "✅ .easignore 敏感排除超集对账通过: $(echo "$SECRETS_PATTERNS" | wc -l) 类凭据模式均被 .gitignore 声明且 .easignore 覆盖"
