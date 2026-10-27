#!/bin/bash
# F314: 启动解释器多源对账守卫(部署守卫族第十三枚)
#
# 生产启动解释器字面量散布四源零断言:
#   ① deploy.sh `PYTHON="python3"` 声明(nohup直启分支解释器)
#   ② scripts/watchdog.sh `nohup python3 ...` 硬编码字面量(systemd退位后唯一复活源)
#   ③ systemd/tianlian-gateway.service `ExecStart=/usr/bin/python3 main.py`
#   ④ Dockerfile `CMD ["python3", "main.py"]`
# (Makefile run目标走 $(VENV)/bin/python 是dev venv语义, 与生产裸解释器刻意不同, 豁免入列但断言提取非空)
#
# F287(python-version-check)只覆盖"最低版本数字"声明源(3.10 minor×7), 启动命令行解释器token是盲区:
# 漂移后果(最恶形态=静默): deploy.sh单侧换解释器(如python3.11/venv路径)→watchdog/systemd/Docker未同步→
# watchdog复活进程静默用旧解释器, 新语法/新标准库在运行时才崩(F287版本声明全绿但实际进程跑错解释器);
# systemd ExecStart换版本化二进制不同步→重启后行为与deploy直启分叉, 排障时两模式复现不一致。
#
# 断言: 四生产源归一化(basename去目录前缀)后精确相等 + 各源提取≥1(活性, 防豁免吞断言),
# 缺输入/提取空/漂移均exit 1(F212不放行)。接入 make check(start-interpreter-check) + CI check job。

set -uo pipefail
cd "$(dirname "$0")/.." || { echo "❌ 无法定位仓库根"; exit 1; }

fail=0

# ① deploy.sh PYTHON声明
interp_deploy="$(sed -n 's/^PYTHON="\(.*\)"/\1/p' deploy.sh 2>/dev/null | head -1 || true)"

# ② watchdog.sh nohup行解释器字面量(nohup后第一个token)
interp_watchdog="$(grep -h '^[[:space:]]*nohup ' scripts/watchdog.sh 2>/dev/null | head -1 | awk '{print $2}' || true)"

# ③ systemd unit ExecStart第一token取basename
execstart="$(sed -n 's/^ExecStart=//p' systemd/tianlian-gateway.service 2>/dev/null | head -1 || true)"
interp_unit="$(printf '%s' "$execstart" | awk '{print $1}' | sed 's|.*/||' || true)"

# ④ Dockerfile CMD json数组第一元素
interp_docker="$(sed -n 's/^CMD \["\([^"]*\)".*/\1/p' Dockerfile 2>/dev/null | head -1 || true)"

# dev豁免源: Makefile PYTHON定义(venv语义, 只断言提取非空不要求等值)
interp_makefile="$(sed -n 's/^PYTHON[[:space:]]*[?:]*=[[:space:]]*\(.*\)$/\1/p' Makefile 2>/dev/null | head -1 || true)"

# 缺输入/提取空检查(F212)
for pair in "deploy.sh PYTHON声明:${interp_deploy}" "watchdog.sh nohup字面量:${interp_watchdog}" "systemd unit ExecStart:${interp_unit}" "Dockerfile CMD:${interp_docker}" "Makefile PYTHON(dev豁免源):${interp_makefile}"; do
    src="${pair%%:*}"; val="${pair#*:}"
    if [ -z "$val" ]; then
        echo "❌ 启动解释器源提取失败(F212): ${src} 未找到预期声明/提取为空"
        fail=1
    fi
done

# 归一化: deploy/watchdog/docker本就是裸token; unit已取basename; 全部再去目录前缀兜底
norm_deploy="$(printf '%s' "$interp_deploy" | sed 's|.*/||')"
norm_watchdog="$(printf '%s' "$interp_watchdog" | sed 's|.*/||')"
norm_unit="$interp_unit"
norm_docker="$(printf '%s' "$interp_docker" | sed 's|.*/||')"

if [ "$fail" -eq 0 ]; then
    if [ "$norm_deploy" != "$norm_watchdog" ] || [ "$norm_deploy" != "$norm_unit" ] || [ "$norm_deploy" != "$norm_docker" ]; then
        echo "❌ 生产启动解释器四源漂移(F314):"
        echo "   deploy.sh PYTHON声明:       ${interp_deploy}"
        echo "   watchdog.sh nohup字面量:    ${interp_watchdog}"
        echo "   systemd unit ExecStart:     ${interp_unit}"
        echo "   Dockerfile CMD:             ${interp_docker}"
        echo "   (最恶形态: watchdog复活进程静默用旧解释器, F287版本声明全绿但进程跑错解释器)"
        fail=1
    fi
fi

if [ "$fail" -eq 0 ]; then
    echo "✅ 启动解释器四源一致: ${norm_deploy}(deploy/watchdog/systemd/Docker) + Makefile dev源=${interp_makefile}(venv豁免)"
    exit 0
fi
exit 1
