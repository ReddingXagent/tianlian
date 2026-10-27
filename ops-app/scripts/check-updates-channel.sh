#!/usr/bin/env bash
# OTA更新通道双源成对守卫 (F302)
# app.json expo.updates.url 是运行时 expo-updates 轮询的更新端点(执行侧),
# eas.json projectId 是 EAS 账号侧的项目锚点(eas init/eas update 写入的身份标识):
#   - 一侧真值一侧占位/缺失 = 半接线: 账号已接但 OTA 端点未更新(或反向),
#     更新包推往不存在的项目, 设备端静默永不收到更新(无报错, 只有"没有新版本")
#   - 两侧均占位/缺失 = 未接账号一致态(当前形态), 放行并显式输出状态
#   - 两侧均真值 = url 尾段 uuid 必须与 projectId 一致, 不一致即漂移
# 修改 OTA 接线基线时必须两侧同步
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

UPDATES_URL="$(node -p '(require("./app.json").expo.updates && require("./app.json").expo.updates.url) || ""')"
PROJECT_ID="$(node -p 'require("./eas.json").projectId || ""')"

# 占位形态识别: 脚手架模板残留(your-project-id/your-*)、尖括号待填、xxx/example/placeholder/todo
is_placeholder() {
  local v="$1"
  local seg
  seg="$(printf '%s' "$v" | sed 's|.*/||')"
  if printf '%s' "$seg" | grep -qiE '^(your[-_].*|<.*>|x{2,}|example.*|placeholder|todo.*)$'; then
    return 0
  fi
  return 1
}

URL_REAL=0
if [ -n "$UPDATES_URL" ] && ! is_placeholder "$UPDATES_URL"; then
  URL_REAL=1
fi
ID_REAL=0
if [ -n "$PROJECT_ID" ] && ! is_placeholder "$PROJECT_ID"; then
  ID_REAL=1
fi

# 形态1: 两侧均未接账号(占位/缺失) — 一致态放行, 显式输出防误读为已接线
if [ "$URL_REAL" = "0" ] && [ "$ID_REAL" = "0" ]; then
  echo "✅ OTA通道未接账号一致态: updates.url=\"${UPDATES_URL:-<缺>}\" ↔ eas.json projectId=\"${PROJECT_ID:-<缺>}\" (两侧均占位/缺失, 接账号时必须两侧同步)"
  exit 0
fi

# 形态2: 半接线 — 最恶漂移形态
if [ "$URL_REAL" = "0" ] && [ "$ID_REAL" = "1" ]; then
  echo "❌ OTA通道半接线: eas.json projectId=$PROJECT_ID 已接账号, 但 app.json updates.url 仍为占位/缺失 (当前: \"${UPDATES_URL:-<缺>}\")" >&2
  echo "   运行时 expo-updates 轮询占位端点, 设备端静默永不收到 OTA 更新" >&2
  echo "   处置: updates.url 更新为 https://u.expo.dev/$PROJECT_ID" >&2
  exit 1
fi
if [ "$URL_REAL" = "1" ] && [ "$ID_REAL" = "0" ]; then
  echo "❌ OTA通道半接线: app.json updates.url=$UPDATES_URL 已填真值, 但 eas.json 无 projectId 锚点 (当前: \"${PROJECT_ID:-<缺>}\")" >&2
  echo "   EAS 侧无项目身份, eas update 无锚点可推, OTA 通道形同虚设" >&2
  echo "   处置: eas init 接入账号写入 projectId, 或删除 updates.url 回退未接账号态" >&2
  exit 1
fi

# 形态3: 两侧均真值 — url尾段uuid必须==projectId
URL_SEG="$(printf '%s' "$UPDATES_URL" | sed 's|/$||; s|.*/||')"
if [ "$URL_SEG" != "$PROJECT_ID" ]; then
  echo "❌ OTA通道双源漂移: updates.url 尾段=$URL_SEG ↔ eas.json projectId=$PROJECT_ID 不一致" >&2
  echo "   更新包推往错误项目, 设备端静默永不收到更新" >&2
  echo "   处置: 两侧同步为同一 projectId" >&2
  exit 1
fi

echo "✅ OTA通道双源成对: updates.url=$UPDATES_URL ↔ eas.json projectId=$PROJECT_ID"
exit 0
