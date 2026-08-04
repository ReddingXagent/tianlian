#!/usr/bin/env bash
# 版本双源漂移守卫 (F224)
# package.json.version 与 app.json.expo.version 是同一语义的双源:
#   - app.json.expo.version 是发布 bundle 的唯一版本源 (EAS/商店展示)
#   - package.json.version 是 npm 侧版本
# 发版只改一处 → 漂移: 线上 bundle 版本与代码仓声明不符, 排障/灰度对照失真
# 本守卫断言两侧一致; 发版时两处同步修改
set -euo pipefail

cd "$(dirname "$0")/.."

PKG_VERSION="$(node -p 'require("./package.json").version')"
APP_VERSION="$(node -p 'require("./app.json").expo.version')"

if [ "$PKG_VERSION" != "$APP_VERSION" ]; then
  echo "❌ 版本漂移: package.json.version=$PKG_VERSION vs app.json.expo.version=$APP_VERSION" >&2
  echo "   发布 bundle 以 app.json 为准, 发版时必须两处同步修改" >&2
  exit 1
fi

echo "✅ 版本一致: $PKG_VERSION"
