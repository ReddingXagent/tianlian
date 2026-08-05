#!/usr/bin/env bash
# F261: 日志路径双源漂移守卫(logrotate轮转目标 ↔ 写侧日志文件名)
# 背景: nohup模式下日志写 gateway.log(deploy.sh 重定向 + watchdog LOG_FILE),
#   systemd/logrotate.conf 的轮转目标也是 gateway.log。任一侧单独改名 →
#   logrotate轮转的是不存在的路径(missingok静默跳过) → 真实日志无人轮转 →
#   Pi磁盘被日志写满(静默, 边缘设备最恶故障)。另: logrotate路径目录段与
#   unit WorkingDirectory 共用同一渲染占位符(/home/tl/tianlian-edge-gateway-v3),
#   目录段漂移 → make systemd-install 的sed渲染不到 → 装出去的logrotate仍指Pi默认路径。
# 本脚本断言: 轮转目标basename ↔ deploy.sh写侧basename ↔ watchdog写侧basename 三源一致,
#   且 logrotate目录段 == unit WorkingDirectory 默认值。缺输入/提取空/不等均exit1。
# F341: 声明源外全域字面量写读点扫描(见下方扫描段注释)。
# 接入 make check(log-paths-check) + CI check job。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

fail=0

# 缺输入必须FAIL(F212铁律)
for f in systemd/logrotate.conf deploy.sh scripts/watchdog.sh; do
    if [ ! -f "$f" ]; then
        echo "❌ 缺输入: $f 不存在"; exit 1
    fi
done

# 轮转目标: systemd/logrotate.conf 首个 ".../xxx.log {" 行
rotate_full="$(sed -n 's|^\(.*/[A-Za-z0-9._-]*\.log\)[[:space:]]*{.*$|\1|p' systemd/logrotate.conf | head -1)"
rotate_base="$(basename "${rotate_full:-/}" 2>/dev/null)"
rotate_dir="$(dirname "${rotate_full:-/}" 2>/dev/null)"

# 写侧源1: deploy.sh nohup重定向目标 "nohup ... > xxx.log 2>&1 &"
deploy_base="$(sed -n 's/^.*nohup .* > \([A-Za-z0-9._-]*\.log\).*$/\1/p' deploy.sh | head -1)"

# 写侧源2: scripts/watchdog.sh LOG_FILE="$REPO_DIR/xxx.log"
watchdog_base="$(sed -n 's|^LOG_FILE="\$REPO_DIR/\([A-Za-z0-9._-]*\.log\)".*$|\1|p' scripts/watchdog.sh | head -1)"

# unit模板路径取自 deploy.sh UNIT_FILE 默认值(F236已守卫三源同名), 不硬编码unit文件名
unit_template="systemd/$(basename "$(sed -n 's/^UNIT_FILE="\${TIANLIAN_UNIT_FILE:-\(.*\)}".*$/\1/p' deploy.sh | head -1)")"

# unit WorkingDirectory 默认值(渲染占位符对账)
unit_workdir="$(sed -n 's|^WorkingDirectory=\(.*\)$|\1|p' "$unit_template" | head -1)"

for pair in "systemd/logrotate.conf轮转目标:${rotate_full}" \
            "deploy.sh写侧:${deploy_base}" \
            "scripts/watchdog.sh写侧:${watchdog_base}" \
            "${unit_template} WorkingDirectory:${unit_workdir}"; do
    src="${pair%%:*}"; val="${pair#*:}"
    if [ -z "$val" ]; then
        echo "❌ 日志路径源提取失败: ${src} 未找到预期声明"; fail=1
    fi
done

if [ "$fail" -eq 0 ]; then
    if [ "$rotate_base" != "$deploy_base" ] || [ "$rotate_base" != "$watchdog_base" ]; then
        echo "❌ 日志路径双源漂移(F261):"
        echo "   logrotate轮转目标basename: ${rotate_base}"
        echo "   deploy.sh写侧basename:     ${deploy_base}"
        echo "   watchdog写侧basename:      ${watchdog_base}"
        echo "   三源必须一致, 否则轮转静默失效(missingok)→日志无限增长写满磁盘"
        fail=1
    fi
    if [ "$rotate_dir" != "$unit_workdir" ]; then
        echo "❌ logrotate目录段与unit WorkingDirectory漂移(F261):"
        echo "   logrotate目录段:      ${rotate_dir}"
        echo "   unit WorkingDirectory: ${unit_workdir}"
        echo "   两段必须同值(共用sed渲染占位符), 否则systemd-install渲染不到→装出的轮转仍指旧路径"
        fail=1
    fi
fi

# F341: 全域字面量日志写读点扫描(声明源外的绕过通道)
# F261原对账锚定三声明源(轮转目标/deploy nohup重定向/watchdog LOG_FILE声明),
# 代码内绕过声明的硬编码字面量是盲区(实证存量): watchdog.sh systemd退位消息直写
# ">> $REPO_DIR/gateway.log"(绕过下方LOG_FILE变量) + deploy.sh status/logs子命令
# tail读引用×2。漂移场景: 三声明源同步改名(F261全绿)而字面量漏同步→
# watchdog继续写旧文件名幻影日志(无人轮转) / tail永显"(无日志)"运维误判日志丢失。
# 扫描域: deploy.sh + scripts/*.sh(排除check-*守卫脚本——其regex/注释含.log字面量,
# 非行为写读); Makefile不入域(.tianlian-gateway.logrotate.rendered中间产物名含".log"
# 子串但非应用日志); 注释行剥除(文档提及非行为)。断言: 全部字面量basename==轮转目标。
f341_files="deploy.sh"
for f in scripts/*.sh; do
    case "$f" in scripts/check-*) continue ;; esac
    f341_files="$f341_files $f"
done

f341_found=0
for f in $f341_files; do
    if [ ! -f "$f" ]; then
        echo "❌ F341 缺输入: $f 不存在"; exit 1
    fi
    while IFS=: read -r lno tok; do
        [ -z "${tok:-}" ] && continue
        # 注释行(文档提及)剥除
        if sed -n "${lno}p" "$f" | grep -q '^[[:space:]]*#'; then
            continue
        fi
        f341_found=1
        if [ "$tok" != "$rotate_base" ]; then
            echo "❌ F341 字面量日志写读点漂移: $f:$lno → $tok (轮转目标: $rotate_base)"
            echo "   声明源外硬编码日志路径必须与轮转目标同名, 否则幻影日志无人轮转/tail读空"
            fail=1
        fi
    done < <(grep -noE '[A-Za-z0-9._-]+\.log' "$f" || true)
done

if [ "$f341_found" -eq 0 ]; then
    echo "❌ F341 全域字面量日志点提取为空: 扫描域 $f341_files"
    fail=1
fi

if [ "$fail" -ne 0 ]; then
    exit 1
fi
echo "✅ 日志路径全域一致: ${rotate_base}(轮转↔deploy↔watchdog声明三源+全域字面量写读点F341) 目录段=${rotate_dir}(↔unit WorkingDirectory)"
