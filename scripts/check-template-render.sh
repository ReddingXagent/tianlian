#!/usr/bin/env bash
# F295: 部署模板渲染路径一致性守卫(部署守卫族第十枚)
# F347: 扩源deploy.sh回退探测目录 — Pi默认仓库路径同名双源补全(四模板字面量+sed模式+回退目录)
# 背景: make systemd-install 用 sed 把 unit/logrotate 模板中的Pi默认硬编码路径
#   渲染为当前仓库目录(F211)。sed模式(Makefile两行)↔模板路径字面量
#   (unit WorkingDirectory + EnvironmentFile前缀 + logrotate日志路径前缀)是
#   同名双源: 任一侧单独改动 → sed静默no-op(不报错!) → 渲染产物仍带模板默认路径
#   → 非Pi主机 systemd WorkingDirectory不存在即启动失败/读错.env,
#   logrotate指向不存在的日志(missingok静默跳过→日志不轮转膨胀)。
# F347扩源动机: deploy.sh REPO_DIR回退探测目录(脚本不在仓库内时的Pi生产路径探测,
#   status/rollback精确进程匹配基准)编码同一事实"Pi仓库在此路径", 是第六处字面量;
#   历史真实漂移事故(deploy.sh头部注释): 旧值 /home/tl/tianlian-v3-edge-gateway
#   词序写反在Pi上不存在→cd失败set -e第2步即死; 模板/sed侧整体改名(F295全绿)
#   而回退目录漏同步→引导场景(脚本拷贝到仓库外执行)探测旧路径永不命中, 部署静默中止。
# 断言:
#   1. Makefile两行sed模式相等(双源单语义)
#   2. unit WorkingDirectory == sed模式 == dirname(EnvironmentFile) == logrotate日志目录
#   3. 两模板内所有/home/*绝对路径必须以sed模式开头(渲染逃逸=零, 堵静默no-op)
#   4. 每模板sed模式命中数≥1 + 各提取非空(缺输入即FAIL, F212不放行)
#   5. (F347) deploy.sh回退探测目录 == sed模式(提取非空活性)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

fail=0
UNIT_TPL="systemd/tianlian-gateway.service"
LOG_TPL="systemd/logrotate.conf"
DEPLOY_SH="deploy.sh"

[ -f "$DEPLOY_SH" ] || { echo "❌ 缺输入: $DEPLOY_SH (F347)" >&2; exit 1; }

# --- 提取: Makefile两行sed模式(cut -d'|' -f2, 行形如 @sed "s|PATTERN|$(CURDIR)|g" <模板>) ---
sed_pattern() { # <模板文件名> → 该模板对应sed行的模式
    grep '@sed "s|' Makefile 2>/dev/null | grep -F "$1" | head -1 | cut -d'|' -f2 || true
}
pat_unit="$(sed_pattern "$UNIT_TPL")"
pat_log="$(sed_pattern "$LOG_TPL")"

for pair in "Makefile(unit行):${pat_unit}" "Makefile(logrotate行):${pat_log}"; do
    src="${pair%%:*}"; val="${pair#*:}"
    if [ -z "$val" ]; then
        echo "❌ sed模式源提取失败: ${src} 未找到 @sed \"s|...|...\" 渲染行(F295)"; fail=1
    fi
done

# --- 提取: 模板路径字面量 ---
wd="$(sed -n 's|^WorkingDirectory=\(.*\)$|\1|p' "$UNIT_TPL" 2>/dev/null | head -1 || true)"
envfile="$(sed -n 's|^EnvironmentFile=\(.*\)$|\1|p' "$UNIT_TPL" 2>/dev/null | head -1 || true)"
logpath="$(sed -n 's|^\(/[^ ]*\) {.*$|\1|p' "$LOG_TPL" 2>/dev/null | head -1 || true)"

for pair in "unit WorkingDirectory:${wd}" "unit EnvironmentFile:${envfile}" "logrotate日志路径:${logpath}"; do
    src="${pair%%:*}"; val="${pair#*:}"
    if [ -z "$val" ]; then
        echo "❌ 模板路径提取失败: ${src} 未找到预期声明(F295)"; fail=1
    fi
done

# --- 提取(F347): deploy.sh REPO_DIR回退探测目录(elif [ -d /home/...] 行内字面量) ---
fallback_dir="$(grep -oE 'elif \[ -d /home/[A-Za-z0-9._/-]+' "$DEPLOY_SH" 2>/dev/null | grep -oE '/home/[A-Za-z0-9._/-]+' | head -1 || true)"
if [ -z "$fallback_dir" ]; then
    echo "❌ deploy.sh回退探测目录提取失败(F347): 未找到 'elif [ -d /home/...' 回退分支"
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    # 断言1: Makefile双sed模式单语义
    if [ "$pat_unit" != "$pat_log" ]; then
        echo "❌ Makefile sed模式双源漂移(F295): unit行='${pat_unit}' vs logrotate行='${pat_log}'"
        echo "   两行必须同一Pi默认路径, 否则单侧渲染no-op"; fail=1
    fi

    # 断言2: 模板字面量 ↔ sed模式精确一致(含unit内同目录语义)
    pat="$pat_unit"
    [ "$wd" != "$pat" ] && { echo "❌ unit WorkingDirectory漂移(F295): '${wd}' vs sed模式'${pat}' → 非Pi主机sed静默no-op, WorkingDirectory不被渲染"; fail=1; }
    [ "$(dirname "$envfile")" != "$pat" ] && { echo "❌ unit EnvironmentFile目录漂移(F295): '$(dirname "$envfile")' vs sed模式'${pat}' → .env路径不被渲染, 读错/读不到env"; fail=1; }
    [ "$(dirname "$logpath")" != "$pat" ] && { echo "❌ logrotate日志目录漂移(F295): '$(dirname "$logpath")' vs sed模式'${pat}' → 日志路径不被渲染, missingok静默跳过轮转"; fail=1; }

    # 断言5(F347): deploy.sh回退探测目录 ↔ sed模式 — Pi默认仓库路径同名双源
    if [ "$fallback_dir" != "$pat" ]; then
        echo "❌ deploy.sh回退探测目录漂移(F347): '${fallback_dir}' vs sed模式'${pat}'"
        echo "   同一事实'Pi仓库在此路径'双源分叉: 引导场景(脚本在仓库外执行)探测旧路径永不命中, 部署静默中止(F295全绿也拦不住)"; fail=1
    fi

    # 断言3: 渲染逃逸扫描 — 模板内任何/home/*绝对路径必须以sed模式开头
    for tpl in "$UNIT_TPL" "$LOG_TPL"; do
        escapes="$(grep -oh '/home/[A-Za-z0-9._/-]*' "$tpl" 2>/dev/null | grep -vF "$pat" || true)"
        if [ -n "$escapes" ]; then
            echo "❌ ${tpl} 存在渲染逃逸路径(F295, 不以sed模式开头, 安装后仍为模板默认值):"
            echo "$escapes" | sed 's/^/   /'; fail=1
        fi
        # 断言4: 命中数≥1(模板被整体改写致sed无命中=静默no-op)
        n="$(grep -coF "$pat" "$tpl" 2>/dev/null || true)"
        if [ "${n:-0}" -lt 1 ]; then
            echo "❌ ${tpl} sed模式零命中(F295): 渲染将静默no-op, 模板路径字面量须含'${pat}'"; fail=1
        fi
    done
fi

if [ "$fail" -ne 0 ]; then
    exit 1
fi
echo "✅ 部署模板渲染路径一致(F295/F347): sed模式='${pat_unit}' unit/logrotate三字面量+deploy.sh回退目录对齐+零渲染逃逸"
