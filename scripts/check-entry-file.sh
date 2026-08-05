#!/usr/bin/env bash
# F273: 入口文件多源一致性守卫(启动/探测/进程匹配全部声明源对账)
# 背景: 入口文件名 main.py 分源散布于六类声明:
#   ① systemd unit ExecStart        ② Dockerfile CMD
#   ③ Makefile run 目标              ④ watchdog.sh nohup启动
#   ⑤ deploy.sh 探测/启动            ⑥ pgrep -f "$REPO_DIR/<入口>" 进程匹配模式×4
# 漂移后果: 任一侧单独改入口文件名(如 main.py→app.py)——
#   pgrep模式未同步 → 杀旧进程永不命中→双启撞端口 / status误报"未运行"(静默);
#   unit/Dockerfile未同步 → 服务重启即失败; 探测未同步 → REPO_DIR探测失败部署中止。
# 本脚本对账全部声明源 + 文件实存, 任一提取空/不等/缺文件即FAIL, 接入 make check + CI。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

fail=0
declare -A SRC

SRC[unit]="$(sed -n 's|^ExecStart=/usr/bin/python3 \(.*\.py\)$|\1|p' systemd/tianlian-gateway.service | head -1 || true)"
SRC[dockerfile]="$(sed -n 's|^CMD \["python3", "\(.*\.py\)"\]$|\1|p' Dockerfile | head -1 || true)"
SRC[makefile]="$(sed -n 's|^\t\$(PYTHON) \(.*\.py\)$|\1|p' Makefile | head -1 || true)"
SRC[watchdog_start]="$(sed -n 's|.*nohup python3 "\$REPO_DIR/\(.*\.py\)".*|\1|p' scripts/watchdog.sh | head -1 || true)"
SRC[deploy_probe]="$(sed -n 's|^if \[ -f "\$SCRIPT_DIR/\(.*\.py\)" \]; then$|\1|p' deploy.sh | head -1 || true)"
SRC[deploy_start]="$(sed -n 's|.*nohup \$PYTHON "\$REPO_DIR/\(.*\.py\)".*|\1|p' deploy.sh | head -1 || true)"

for src in unit dockerfile makefile watchdog_start deploy_probe deploy_start; do
    if [ -z "${SRC[$src]}" ]; then
        echo "❌ 入口文件源提取失败(F273): ${src} 未找到预期声明"
        fail=1
    fi
done

# pgrep进程匹配模式(deploy.sh×3 + watchdog×1): 模式文件名去重后必须唯一
pgrep_names="$( (grep -oh 'pgrep -f "\$REPO_DIR/[^"]*\.py"' deploy.sh scripts/watchdog.sh || true) \
    | sed 's|pgrep -f "\$REPO_DIR/||; s|"$||' | sort -u)"
pgrep_count="$( (grep -c 'pgrep -f "\$REPO_DIR/[^"]*\.py"' deploy.sh scripts/watchdog.sh || true) | awk -F: '{s+=$2} END{print s+0}')"
if [ "${pgrep_count}" -lt 4 ]; then
    echo "❌ pgrep匹配模式数量异常(F273): 期望≥4处(deploy.sh×3+watchdog×1), 实测${pgrep_count}"
    fail=1
fi
if [ "$(echo "$pgrep_names" | wc -l)" -ne 1 ] || [ -z "$pgrep_names" ]; then
    echo "❌ pgrep匹配模式文件名漂移(F273): $(echo $pgrep_names)"
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    ref="${SRC[unit]}"
    for src in dockerfile makefile watchdog_start deploy_probe deploy_start; do
        if [ "${SRC[$src]}" != "$ref" ]; then
            echo "❌ 入口文件多源漂移(F273): unit=${ref} vs ${src}=${SRC[$src]}"
            fail=1
        fi
    done
    if [ -n "$pgrep_names" ] && [ "$pgrep_names" != "$ref" ]; then
        echo "❌ pgrep匹配模式与入口文件漂移(F273): pgrep=${pgrep_names} vs unit=${ref} (杀旧/status永不命中=静默双启)"
        fail=1
    fi
    if [ ! -f "$ref" ]; then
        echo "❌ 入口文件不存在(F273): 声明=${ref} 但磁盘无此文件"
        fail=1
    fi
fi

if [ "$fail" -ne 0 ]; then
    exit 1
fi
echo "✅ 入口文件多源一致(F273): ${SRC[unit]}(六声明源+pgrep×${pgrep_count}+实存)"
