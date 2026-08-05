#!/usr/bin/env bash
# F308: pid文件写读对账守卫(部署守卫族第十二枚)
# 背景: 直跑模式(nohup)下进程pid靠仓库根 .pid 文件交接, 三处字面量声明:
#   写侧1: deploy.sh start_gateway `echo "$NEW_PID" > .pid`
#   读侧1: deploy.sh step6 停旧 `[ -f .pid ]` + `cat .pid`(pgrep未中时兜底)
#   读写侧2: scripts/watchdog.sh `PID_FILE="$REPO_DIR/.pid"`(取pid读 + 重启后写回)
# 任一侧单独改名/改目录段 → 全程无报错(最恶漂移=静默):
#   A. watchdog侧PID_FILE改名 → 重启写回的文件deploy.sh停旧永不读 →
#      pgrep同时失配(cmdline漂移)时旧进程漏kill → 双启撞端口/重启风暴(F217/F230同族后果);
#   B. deploy.sh写侧改名 → watchdog读旧名落空回退pgrep, pid交接链路静默失效,
#      排障时只见双启现象不见根因。
# 断言: 四提取点(deploy写/deploy读test/deploy读cat/watchdog PID_FILE basename)精确相等
#   + watchdog目录段==$REPO_DIR(与deploy.sh相对路径同基准)
#   + 活性断言: deploy写点≥1 / watchdog读点≥1 / watchdog写点≥1(防豁免吞断言)
#   缺输入/提取空/漂移均exit1(F212)。接入 make check(pid-file-check) + CI check job。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

fail=0

# 缺输入必须FAIL(F212铁律)
for f in deploy.sh scripts/watchdog.sh; do
    if [ ! -f "$f" ]; then
        echo "❌ 缺输入: $f 不存在"; exit 1
    fi
done

# 写侧1: deploy.sh `echo "$NEW_PID" > <name>`
deploy_write="$(sed -n 's/^.*echo "\$NEW_PID" > \([A-Za-z0-9._-]*\)$/\1/p' deploy.sh | head -1)"

# 读侧1a: deploy.sh `if … OLD_PID … [ -f <name> ]`(step6停旧兜底前置检查; OLD_PID锚定排除.env等他名[ -f ]行)
deploy_read_test="$(sed -n 's/^.*OLD_PID.*\[ -f \([A-Za-z0-9._-]*\) \].*$/\1/p' deploy.sh | head -1)"

# 读侧1b: deploy.sh `cat <name>`(step6停旧兜底读取)
deploy_read_cat="$(sed -n 's/^.*OLD_PID="\$(cat \([A-Za-z0-9._-]*\) .*$/\1/p' deploy.sh | head -1)"

# 读写侧2: watchdog.sh `PID_FILE="$REPO_DIR/<path>"`
watchdog_raw="$(sed -n 's|^PID_FILE="\$REPO_DIR/\(.*\)".*$|\1|p' scripts/watchdog.sh | head -1)"
watchdog_name="$(basename "${watchdog_raw:-/}")"
watchdog_dir_ok=0
case "${watchdog_raw:-}" in
    */*) watchdog_dir_ok=0 ;;   # 含目录段=漂移(应为仓库根直接子文件)
    *)  [ -n "$watchdog_raw" ] && watchdog_dir_ok=1 ;;
esac

# 提取空必须FAIL(F212)
for pair in "deploy.sh写侧:${deploy_write}" "deploy.sh读侧[test]:${deploy_read_test}" "deploy.sh读侧[cat]:${deploy_read_cat}" "watchdog.sh PID_FILE:${watchdog_name}"; do
    src="${pair%%:*}"; val="${pair#*:}"
    if [ -z "$val" ]; then
        echo "❌ 提取空: ${src} 未找到预期pid文件声明"; fail=1
    fi
done

if [ "$fail" -eq 0 ]; then
    if [ "$deploy_write" != "$deploy_read_test" ] || [ "$deploy_write" != "$deploy_read_cat" ] || [ "$deploy_write" != "$watchdog_name" ]; then
        echo "❌ pid文件名多源漂移(F308):"
        echo "   deploy.sh 写侧(echo > …):      ${deploy_write}"
        echo "   deploy.sh 读侧([ -f … ]):      ${deploy_read_test}"
        echo "   deploy.sh 读侧(cat …):         ${deploy_read_cat}"
        echo "   watchdog.sh PID_FILE basename: ${watchdog_name}"
        echo "   四源必须精确一致, 否则pid交接链路静默失效→旧进程漏kill双启撞端口(F217/F230同族)"
        fail=1
    fi
    if [ "$watchdog_dir_ok" -ne 1 ]; then
        echo "❌ watchdog PID_FILE目录段漂移(F308): '$watchdog_raw' 应为仓库根直接子文件(与deploy.sh相对路径同基准)"
        fail=1
    fi

    # 活性断言: 写读点存在(防豁免吞断言; 用提取名动态匹配, 合法改名不误伤)
    deploy_write_cnt="$(grep -cF "> ${deploy_write}" deploy.sh || true)"
    watchdog_read_cnt="$(grep -c '\[ -f "\$PID_FILE" \]' scripts/watchdog.sh || true)"
    watchdog_write_cnt="$(grep -c '> "\$PID_FILE"' scripts/watchdog.sh || true)"
    if [ "${deploy_write_cnt:-0}" -lt 1 ] || [ "${watchdog_read_cnt:-0}" -lt 1 ] || [ "${watchdog_write_cnt:-0}" -lt 1 ]; then
        echo "❌ 活性断言失败(F308): deploy写点=${deploy_write_cnt:-0} watchdog读点=${watchdog_read_cnt:-0} watchdog写点=${watchdog_write_cnt:-0} (各须≥1)"
        fail=1
    fi
fi

if [ "$fail" -ne 0 ]; then
    exit 1
fi

echo "✅ pid文件写读对账一致(F308): ${deploy_write} (deploy写1+读2 ↔ watchdog PID_FILE读1+写1, 目录段=仓库根)"
