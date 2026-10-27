#!/usr/bin/env bash
# F301: 备份写模式↔回滚/保留读glob双向对账 + deploy.sh DB_FILE↔config.py db_path一致性守卫
# 背景: deploy.sh 迁移前备份与回滚/保留读取分四处字面量维护, 零对账:
#   写侧① BAK="data/backups/gateway.db.$TS.bak"        (主备份命名)
#   写侧② BAK="data/backups/gateway.db.$TS-$SUFFIX.bak" (带后缀变体)
#   读侧③ rollback: ls -1t data/backups/gateway.db.*.bak (回滚选最新备份)
#   读侧④ retention: 同glob tail -n +6 清理旧备份
#   另: DB_FILE="data/gateway.db" 在 deploy.sh 内两处声明(rollback分支+部署分支),
#       与 config.py db_path 字段默认值(F267声明侧权威源)零对账。
# F267 已覆盖 config.py↔Dockerfile↔compose↔备份basename, 但写模式形态↔读glob
# 形态是否互相匹配、DB_FILE双处是否同源且等于config.py, 均未断言。
# 漂移后果(最恶形态=静默): 写侧改名(如 gateway.db.$TS.backup 或 db-$TS.bak)→
#   读glob永远匹配不到任何备份→回滚时"无备份可用"在凌晨3点回滚现场才暴露;
#   retention glob漂移→旧备份永不清理占满边缘设备磁盘; DB_FILE单侧漂移→
#   rollback恢复目标≠真实DB位置→恢复成功假象+数据仍在旧处。
# 本脚本断言:
#   1. 写侧每模式: 固定前缀+$变量+固定后缀 推导期望glob(前缀+*+后缀), 读glob必须相等
#   2. 读glob出现≥2(rollback+retention双消费点)且全部相同
#   3. 写侧模式≥1, 全部匹配读glob形态
#   4. DB_FILE≥2处全部相同, 且==config.py db_path字段默认值(与F267同法提取)
#   5. 读glob目录前缀==dirname(DB_FILE)/backups
#   任一源缺输入/提取空/不一致均FAIL(exit 1, F212不放行)。接入 make check + CI。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

DEPLOY_SH="deploy.sh"
CONFIG_PY="config.py"

fail() { echo "❌ $1"; exit 1; }

for f in "$DEPLOY_SH" "$CONFIG_PY"; do
    [ -f "$f" ] || fail "缺输入(F301): $f 不存在"
done

# 写侧: 全部 BAK="<dir>/backups/<name>.$TS..." 备份命名模式(收窄backups/字面量,
# 排除restore-db子命令 BAK="${2:-$LATEST}" 参数形态——非命名声明)
WRITE_PATTERNS="$(grep -oE 'BAK="[^"]*backups/[^"]+"' "$DEPLOY_SH" | sed -E 's|^BAK="([^"]+)"$|\1|' || true)"
[ -n "$WRITE_PATTERNS" ] || fail "提取空(F301): deploy.sh 未找到 BAK=\"...\" 备份写模式"

# 读侧: 全部 ls -1t <glob> 读取点(rollback + retention), 提取整token再滤*号
# (变异P2实证: 提取regex若锚定\*\.bak, 会把.bak2类后缀延伸漂移静默截断为.bak→漏检)
READ_GLOBS="$(grep -oE 'ls -1t [^ ]+' "$DEPLOY_SH" | sed -E 's|^ls -1t ||' | grep -F '*' || true)"
[ -n "$READ_GLOBS" ] || fail "提取空(F301): deploy.sh 未找到 ls -1t <glob> 备份读取点"
READ_COUNT="$(printf '%s\n' "$READ_GLOBS" | wc -l)"
[ "$READ_COUNT" -ge 2 ] || fail "缺消费点(F301): 备份读glob仅$READ_COUNT处(<2), rollback/retention双消费点必须齐备——单侧存在时另一侧静默失配"
READ_UNIQ="$(printf '%s\n' "$READ_GLOBS" | sort -u)"
[ "$(printf '%s\n' "$READ_UNIQ" | wc -l)" -eq 1 ] || fail "漂移(F301): 备份读glob多处分叉: $(printf '%s' "$READ_UNIQ" | tr '\n' ' ') → rollback与retention匹配不到同一批备份"
READ_GLOB="$READ_UNIQ"

# 写侧每模式推导期望glob: 前缀=首个$变量前, 后缀=末个$变量后
while IFS= read -r p; do
    case "$p" in *\$*) ;; *) fail "漂移(F301): 备份写模式无时间戳变量: $p";; esac
    prefix="${p%%\$*}"
    suffix="$(printf '%s' "$p" | sed -E 's/^.*\$[A-Za-z_][A-Za-z0-9_]*//')"
    [ -n "$prefix" ] && [ -n "$suffix" ] || fail "提取空(F301): 备份写模式前缀/后缀解析失败: $p"
    expected="${prefix}*${suffix}"
    [ "$expected" = "$READ_GLOB" ] || fail "漂移(F301): 备份写模式($p)推导期望glob($expected) ≠ 读侧glob($READ_GLOB) → 该模式写出的备份回滚/保留永远匹配不到(静默)"
done <<EOF
$WRITE_PATTERNS
EOF

# DB_FILE: deploy.sh内多处声明全同, 且==config.py db_path字段默认值
DB_FILES="$(grep -oE 'DB_FILE="[^"]+"' "$DEPLOY_SH" | sed -E 's|^DB_FILE="([^"]+)"$|\1|' || true)"
[ -n "$DB_FILES" ] || fail "提取空(F301): deploy.sh 未找到 DB_FILE=\"...\" 声明"
DBF_COUNT="$(printf '%s\n' "$DB_FILES" | wc -l)"
[ "$DBF_COUNT" -ge 2 ] || fail "缺声明(F301): DB_FILE仅$DBF_COUNT处(<2), rollback分支与部署分支必须各自声明同一DB路径"
DBF_UNIQ="$(printf '%s\n' "$DB_FILES" | sort -u)"
[ "$(printf '%s\n' "$DBF_UNIQ" | wc -l)" -eq 1 ] || fail "漂移(F301): DB_FILE多处分叉: $(printf '%s' "$DBF_UNIQ" | tr '\n' ' ') → rollback恢复目标≠部署备份来源"
DB_FILE="$DBF_UNIQ"

FIELD_DEFAULT="$(grep -oE 'db_path: *str *= *"[^"]+"' "$CONFIG_PY" \
    | sed -E 's|^db_path: *str *= *"([^"]+)"$|\1|' | head -1 || true)"
[ -n "$FIELD_DEFAULT" ] || fail "提取空(F301): config.py 未找到 db_path 字段默认值声明"
[ "$DB_FILE" = "$FIELD_DEFAULT" ] || fail "漂移(F301): deploy.sh DB_FILE($DB_FILE) ≠ config.py db_path默认($FIELD_DEFAULT) → 备份/回滚操作的不是运行时真实DB"

# 读glob目录前缀 == dirname(DB_FILE)/backups
GLOB_DIR="$(dirname "$READ_GLOB")"
EXPECT_DIR="$(dirname "$DB_FILE")/backups"
[ "$GLOB_DIR" = "$EXPECT_DIR" ] || fail "漂移(F301): 备份读glob目录($GLOB_DIR) ≠ DB目录推导($EXPECT_DIR) → 备份目录与DB位置分叉"

echo "✅ [check-backup-restore] 备份写读对账一致: 写模式$(printf '%s\n' "$WRITE_PATTERNS" | wc -l)种↔读glob($READ_GLOB, ${READ_COUNT}消费点), DB_FILE($DB_FILE)==config.py db_path"
