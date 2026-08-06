#!/usr/bin/env bash
# eas.json preview profile distribution:internal ↔ android.buildType:apk APK直装分发形态成对守卫 (F377, 构建守卫族第二十枚)
# 丁哥 2026-08-05 决策 (F25/F33 清零): 内部分发走 APK 直装/二维码 (充电站运维场景不上架商店)。
# preview profile 是 APK 直装分发通道, 由同文件内双键共同编码:
#   - distribution: "internal" → 内部分发形态 (非 store)
#   - android.buildType: "apk" → 产物为 APK (可扫码直装; app-bundle/AAB 无法直装)
# 两键是同一分发决策的双源, 只改一侧 → 分发形态静默分叉:
#   - 删/改 buildType → 产物默认回落 AAB, 二维码直装链路在装机时才暴露失败 (构建全过, F295 族最恶漂移)
#   - 改 distribution 为 store → preview 通道语义漂移, 与 APK 直装决策冲突
# F315 管构建序号配对 / F354 管跨平台身份, 本守卫管分发产物形态, 同文件内双源形态各管各语义
# 缺输入/提取空/任一键漂移 → exit 1 (F212 不放行)
set -euo pipefail

cd "$(dirname "$0")/.."

EAS="eas.json"

if [ ! -f "$EAS" ]; then
  echo "❌ 缺少输入文件: $EAS (缺输入不放行)" >&2
  exit 1
fi

DIST="$(node -p 'String(require("./eas.json").build?.preview?.distribution ?? "")')"
BTYPE="$(node -p 'String(require("./eas.json").build?.preview?.android?.buildType ?? "")')"

if [ -z "$DIST" ]; then
  echo "❌ 缺输入不放行: eas.json build.preview.distribution 未声明, 无法对账APK直装分发形态 (F212)" >&2
  echo "   处置: preview profile 显式声明 distribution=\"internal\" (F25/F33 内部分发决策)" >&2
  exit 1
fi
if [ -z "$BTYPE" ]; then
  echo "❌ 缺输入不放行: eas.json build.preview.android.buildType 未声明, 无法对账APK直装分发形态 (F212)" >&2
  echo "   处置: preview profile 显式声明 android.buildType=\"apk\" (AAB 无法扫码直装)" >&2
  exit 1
fi

if [ "$DIST" != "internal" ]; then
  echo "❌ 分发形态漂移: build.preview.distribution=$DIST, 期望 internal (F25/F33 APK直装决策)" >&2
  echo "   处置: preview 通道保持内部分发形态, 接商店账号时另行评估 production profile" >&2
  exit 1
fi
if [ "$BTYPE" != "apk" ]; then
  echo "❌ 分发产物漂移: build.preview.android.buildType=$BTYPE, 期望 apk" >&2
  echo "   AAB/app-bundle 产物无法扫码直装, 二维码直装链路静默失效(构建全过装机时才暴露)" >&2
  echo "   处置: 恢复 android.buildType=\"apk\" 与 distribution=\"internal\" 配对" >&2
  exit 1
fi

echo "✅ APK直装分发形态配对: preview distribution=$DIST ↔ android.buildType=$BTYPE (F25/F33 决策门禁)"
exit 0
