#!/usr/bin/env bash
# eas.json appVersionSource ↔ app.json versionCode/buildNumber 双源成对守卫 (F288)
# eas.json cli.appVersionSource="local" 声明"版本号由本地 app.json 管理"(声明侧),
# app.json expo.android.versionCode / expo.ios.buildNumber 才是 EAS 构建实际读取的执行源(执行侧):
#   - 声明 local 而 app.json 缺 versionCode/buildNumber → 本地版本管理形同虚设,
#     Play/App Store 递增版本号无锚点, 首次上架/后续提交静默撞车 (F282 同型: 声明侧↔执行侧必须成对)
#   - appVersionSource 改 remote 时版本号由 EAS 服务端管理, 本地声明不再必需 (合法替代形态, 放行)
# 修改版本号管理基线时必须两侧同步
# 缺输入不放行 (F212)
set -euo pipefail

cd "$(dirname "$0")/.."

EAS="eas.json"
APP="app.json"

if [ ! -f "$EAS" ]; then
  echo "❌ 缺少输入文件: $EAS (缺输入不放行)" >&2
  exit 1
fi
if [ ! -f "$APP" ]; then
  echo "❌ 缺少输入文件: $APP (缺输入不放行)" >&2
  exit 1
fi

VERSION_SOURCE="$(node -p '(require("./eas.json").cli && require("./eas.json").cli.appVersionSource) || ""')"
if [ -z "$VERSION_SOURCE" ]; then
  echo "❌ eas.json 未声明 cli.appVersionSource: 版本管理形态不明, 无法对账 (缺输入不放行)" >&2
  echo "   处置: 显式声明 cli.appVersionSource (local=本地 app.json 管理 / remote=EAS 服务端管理)" >&2
  exit 1
fi

if [ "$VERSION_SOURCE" = "local" ]; then
  VERSION_CODE="$(node -p 'String(require("./app.json").expo.android?.versionCode ?? "")')"
  BUILD_NUMBER="$(node -p 'String(require("./app.json").expo.ios?.buildNumber ?? "")')"

  if ! [[ "$VERSION_CODE" =~ ^[1-9][0-9]*$ ]]; then
    echo "❌ 执行力缺失: appVersionSource=local 但 app.json 缺合法 expo.android.versionCode (当前: \"${VERSION_CODE:-<空>}\")" >&2
    echo "   EAS 本地版本管理无 Android 版本号锚点, Play 上架/更新必撞递增约束" >&2
    echo "   处置: app.json expo.android.versionCode 补正整数, 与 version 同步棘轮" >&2
    exit 1
  fi
  if ! [[ "$BUILD_NUMBER" =~ ^[1-9][0-9]*$ ]]; then
    echo "❌ 执行力缺失: appVersionSource=local 但 app.json 缺合法 expo.ios.buildNumber (当前: \"${BUILD_NUMBER:-<空>}\")" >&2
    echo "   EAS 本地版本管理无 iOS 构建号锚点, App Store 上架/更新必撞递增约束" >&2
    echo "   处置: app.json expo.ios.buildNumber 补正整数, 与 version 同步棘轮" >&2
    exit 1
  fi
  echo "✅ appVersionSource 双源成对: eas.json appVersionSource=local ↔ app.json versionCode=$VERSION_CODE + buildNumber=$BUILD_NUMBER"
  exit 0
fi

if [ "$VERSION_SOURCE" = "remote" ]; then
  echo "✅ appVersionSource=remote: 版本号由 EAS 服务端管理, 本地 versionCode/buildNumber 声明非必需"
  exit 0
fi

echo "❌ 未识别的 appVersionSource: \"$VERSION_SOURCE\" (仅支持 local/remote, 未识别形态 loud fail)" >&2
exit 1
