#!/usr/bin/env bash
# F255: 环境变量键名双源一致性守卫
# F332: 读取侧 config.py单文件锚定 → 全仓Python扫描(os.getenv/os.environ.get/os.environ[三形态),
#       防新模块绕过config.py直读env成为对账盲区(读取侧单源化=扩源前的同型漂移通道)
#
# 同一语义(env键名)的双源声明, 零断言:
#   读取侧(权威源): 全仓 *.py os.getenv("KEY")/os.environ.get("KEY")/os.environ["KEY"]
#                   — 代码实际读取的全部键(排除隐藏目录=venv系、tests/、__pycache__/)
#   模板侧:         .env.example — 部署者照抄的配置模板键清单
#                     (compose env_file: .env, .env由部署者从.example复制而来)
# 任一侧单独变更即漂移:
#   代码新增os.getenv键而.example未登记 → 部署者不知道要配, 静默吃默认值
#   (如CLOUD_TOKEN漏配→云端认证失败, 排障时无人想到是env缺失);
#   新模块绕过config.py直读os.environ → 读取侧锚定单文件时同型漂移不可见(F332扩源动机);
#   .env.example残留代码已不再读取的死键 → 误导部署者配置无效项,
#   且真实.env中该键改来改去毫无效果。
#
# 断言: 两侧键集合双向相等 (缺输入/提取空/不等均 exit 1, F212不放行)
set -euo pipefail
cd "$(dirname "$0")/.."

fail() { echo "❌ [check-env-keys] $1" >&2; exit 1; }

ENV_EXAMPLE=.env.example

# 读取侧文件集: 全仓项目Python(排除隐藏目录=venv系/.git, 排除tests/测试代码不消费生产.env)
PY_COUNT=$(find . -name '*.py' \
  -not -path './.*' -not -path './tests/*' -not -path './venv/*' \
  -not -path '*/__pycache__/*' | wc -l)
[ "$PY_COUNT" -gt 0 ] || fail "缺输入: 全仓Python文件集为空"
[ -f "$ENV_EXAMPLE" ] || fail "缺输入: $ENV_EXAMPLE"

# 读取侧: 全仓Python 三种env读取形态的键名(去重排序)
#   os.getenv("KEY" / os.environ.get("KEY" / os.environ["KEY"]
CODE_KEYS=$(find . -name '*.py' \
    -not -path './.*' -not -path './tests/*' -not -path './venv/*' \
    -not -path '*/__pycache__/*' -exec grep -hoE \
    'os\.(getenv\("[A-Z0-9_]+"|environ\.get\("[A-Z0-9_]+"|environ\["[A-Z0-9_]+"\])' {} + 2>/dev/null \
  | grep -oE '"[A-Z0-9_]+"' | tr -d '"' | sort -u || true)
[ -n "$CODE_KEYS" ] || fail "提取空: 全仓Python env读取键集合"

# 模板侧: .env.example 行首 KEY= 键名(去重排序)
TPL_KEYS=$(grep -oE '^[A-Z0-9_]+=' "$ENV_EXAMPLE" | tr -d '=' | sort -u || true)
[ -n "$TPL_KEYS" ] || fail "提取空: .env.example 键集合"

echo "读取侧 全仓Python env读取键数:   $(echo "$CODE_KEYS" | wc -l)"
echo "模板侧 .env.example 键数:        $(echo "$TPL_KEYS" | wc -l)"

# 代码读了但模板未登记 → 部署者漏配静默吃默认值
MISSING_IN_TPL=$(comm -23 <(echo "$CODE_KEYS") <(echo "$TPL_KEYS") || true)
# 模板有但代码已不读 → 死键误导部署者
DEAD_IN_TPL=$(comm -13 <(echo "$CODE_KEYS") <(echo "$TPL_KEYS") || true)

[ -z "$MISSING_IN_TPL" ] || fail "漂移: 代码读取但.env.example未登记: $(echo "$MISSING_IN_TPL" | tr '\n' ' ')→ 部署者漏配静默吃默认值"
[ -z "$DEAD_IN_TPL" ] || fail "漂移: .env.example残留代码不读取的死键: $(echo "$DEAD_IN_TPL" | tr '\n' ' ')→ 配置无效项误导部署者"

echo "✅ [check-env-keys] env键双源一致($(echo "$CODE_KEYS" | wc -l)键): 全仓Python env读取 ↔ .env.example"
