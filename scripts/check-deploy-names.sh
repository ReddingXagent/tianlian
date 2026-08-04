#!/usr/bin/env bash
# F236: 部署同名源一致性守卫(unit/logrotate安装名三源/双源对账)
# 背景: SYSTEMD_MODE探测(F217/F230)依赖 deploy.sh/watchdog.sh 的 UNIT_FILE 默认值
#   与 Makefile systemd-install 实际安装路径**精确同名**。三处任一被单独改名 →
#   unit已装但探测失配 → 退位守卫整体失效(kill+nohup撞systemd Restart=always重启风暴)。
# logrotate同理: Makefile安装名 vs deploy.sh部署尾提示探测名漂移 → 提示误报/漏报。
# 本脚本对账三源unit路径 + 双源logrotate路径, 不一致即FAIL, 接入 make check + CI。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

fail=0

extract_unit_default() { # <script> → 提取 UNIT_FILE="${TIANLIAN_UNIT_FILE:-<路径>}" 中的默认路径
    sed -n 's/^UNIT_FILE="\${TIANLIAN_UNIT_FILE:-\(.*\)}".*$/\1/p' "$1" | head -1
}

unit_deploy="$(extract_unit_default deploy.sh)"
unit_watchdog="$(extract_unit_default scripts/watchdog.sh)"
unit_makefile="$(sed -n 's|^[[:space:]]*sudo cp .* \(\/etc/systemd/system/[^ ]*\)$|\1|p' Makefile | head -1)"

for pair in "deploy.sh:${unit_deploy}" "scripts/watchdog.sh:${unit_watchdog}" "Makefile:${unit_makefile}"; do
    src="${pair%%:*}"; val="${pair#*:}"
    if [ -z "$val" ]; then
        echo "❌ unit源提取失败: ${src} 未找到预期声明(deploy/watchdog: UNIT_FILE=\"\${TIANLIAN_UNIT_FILE:-...}\" / Makefile: sudo cp ... /etc/systemd/system/...)"; fail=1
    fi
done

if [ "$fail" -eq 0 ]; then
    if [ "$unit_deploy" != "$unit_watchdog" ] || [ "$unit_deploy" != "$unit_makefile" ]; then
        echo "❌ systemd unit安装名三源漂移(F236):"
        echo "   deploy.sh UNIT_FILE默认:        ${unit_deploy}"
        echo "   scripts/watchdog.sh UNIT_FILE默认: ${unit_watchdog}"
        echo "   Makefile systemd-install安装路径: ${unit_makefile}"
        echo "   三源必须精确一致, 否则SYSTEMD_MODE探测失配→退位守卫失效(F217/F230)"
        fail=1
    fi

    unit_base="$(basename "$unit_deploy")"
    if [ ! -f "systemd/${unit_base}" ]; then
        echo "❌ unit模板缺失: systemd/${unit_base} 不存在(与安装名basename对齐)"; fail=1
    fi
fi

logrotate_makefile="$(sed -n 's|^[[:space:]]*sudo cp .* \(\/etc/logrotate.d/[^ ]*\)$|\1|p' Makefile | head -1)"
logrotate_deploy="$(grep -o '/etc/logrotate.d/[A-Za-z0-9._-]*' deploy.sh | head -1)"

if [ -z "$logrotate_makefile" ] || [ -z "$logrotate_deploy" ]; then
    echo "❌ logrotate源提取失败: Makefile='${logrotate_makefile}' deploy.sh='${logrotate_deploy}'"; fail=1
elif [ "$logrotate_makefile" != "$logrotate_deploy" ]; then
    echo "❌ logrotate安装名双源漂移(F236): Makefile安装→${logrotate_makefile} vs deploy.sh探测→${logrotate_deploy}"; fail=1
fi

if [ "$fail" -ne 0 ]; then
    exit 1
fi
echo "✅ 部署同名源一致: unit=${unit_deploy}(三源) logrotate=${logrotate_makefile}(双源)"
