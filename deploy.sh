#!/bin/bash
# 天链 V3 部署脚本 — 带健康检查、自动验证、自动回滚
# 用法: bash deploy.sh [--dry-run|--force]

set -euo pipefail

# 禁止 macOS bsdtar 把扩展属性打包成 ._xxx AppleDouble 文件
# （._xxx.py 会被服务器 alembic 的 *.py glob 误读 → null bytes SyntaxError）
export COPYFILE_DISABLE=1

# ==================== 配置 ====================
DEPLOY_USER="root"
DEPLOY_HOST="demo.example.com"
DEPLOY_PATH="/opt/tianlian-cloud"
BACKEND_PORT=8080
APP_URL="http://${DEPLOY_HOST}"
HEALTH_ENDPOINT="http://localhost:${BACKEND_PORT}/api/v1/health"
HEALTH_ENDPOINT_REMOTE="http://${DEPLOY_HOST}/api/v1/health"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="deploy_${TIMESTAMP}.log"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${GREEN}[✓]${NC} $*" | tee -a "${LOG_FILE}"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*" | tee -a "${LOG_FILE}"; }
err()   { echo -e "${RED}[✗]${NC} $*" | tee -a "${LOG_FILE}"; }
info()  { echo -e "${CYAN}[→]${NC} $*" | tee -a "${LOG_FILE}"; }

cleanup() {
    rm -f /tmp/tianlian-deploy-*.tar.gz 2>/dev/null || true
    rm -rf /tmp/tianlian-deploy-*/ 2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "========================================"
echo "  天链 V3 部署脚本"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  目标: ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}"
echo "========================================"
echo ""

# ==================== 阶段0: 部署前健康检查 ====================
info "阶段 0/6: 部署前健康检查..."

# 检查本地工具
for cmd in curl ssh scp tar npm; do
    if ! command -v "$cmd" &>/dev/null; then
        err "缺少命令: $cmd"
        exit 1
    fi
done
log "本地工具检测通过"

# 检查远程服务是否正常
PRE_HEALTH=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 "${HEALTH_ENDPOINT_REMOTE}" 2>/dev/null || echo "000")
if [ "$PRE_HEALTH" = "200" ]; then
    log "部署前健康检查通过 (HTTP ${PRE_HEALTH})"
else
    warn "部署前健康检查: 当前服务状态 HTTP ${PRE_HEALTH} (非200，继续部署)"
fi
echo ""

# ==================== 阶段1: 构建前端 ====================
info "阶段 1/6: 构建前端..."
cd frontend

if [ ! -d "node_modules" ]; then
    warn "node_modules 不存在，运行 npm ci..."
    npm ci 2>&1 | tail -3
fi

npm run build 2>&1 | tail -5
if [ ! -f "dist/index.html" ]; then
    err "前端构建失败: dist/index.html 未生成"
    exit 1
fi
log "前端构建完成 ($(du -sh dist | awk '{print $1}'))"
cd ..
echo ""

# ==================== 阶段2: 创建部署包 ====================
info "阶段 2/6: 创建部署包..."

DEPLOY_DIR="deploy_${TIMESTAMP}"
mkdir -p "${DEPLOY_DIR}"

# 复制后端
cp -r backend "${DEPLOY_DIR}/"
# 复制前端构建产物
mkdir -p "${DEPLOY_DIR}/frontend"
cp -r frontend/dist/* "${DEPLOY_DIR}/frontend/"

# 移除本地开发文件（防止覆盖云端）
rm -rf "${DEPLOY_DIR}/backend/venv" "${DEPLOY_DIR}/backend/.venv" "${DEPLOY_DIR}/backend/.venv2" 2>/dev/null || true
# glob 必须在引号外才会展开（引号内 "*.db" 按字面量匹配 = 死代码, 卡 0eae0bd5）
rm -f "${DEPLOY_DIR}"/backend/*.db 2>/dev/null || true
find "${DEPLOY_DIR}" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "${DEPLOY_DIR}" -name '*.pyc' -delete 2>/dev/null || true

# 创建远程安装脚本（内嵌，避免引用问题）
cat > "${DEPLOY_DIR}/install.sh" << 'INSTALL_SCRIPT'
#!/bin/bash
# 天链 V3 远程安装脚本 — 在服务器端执行
set -euo pipefail

DEPLOY_PATH="/opt/tianlian-cloud"
BACKEND_PORT=8080
HEALTH_ENDPOINT="http://localhost:${BACKEND_PORT}/api/v1/health"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${DEPLOY_PATH}_backup_${TIMESTAMP}.tar.gz"
LOG_FILE="/tmp/tianlian-install-${TIMESTAMP}.log"

log()   { echo "[✓] $*" | tee -a "${LOG_FILE}"; }
warn()  { echo "[!] $*" | tee -a "${LOG_FILE}"; }
err()   { echo "[✗] $*" | tee -a "${LOG_FILE}"; }

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log "=== 开始安装 (${TIMESTAMP}) ==="

# ---- 1. 备份 ----
log "备份旧版本..."
if [ -d "${DEPLOY_PATH}" ]; then
    # 用 tar czf 备份为单个压缩包，排除虚拟环境/字节码缓存/Git。
    # 原先用 cp -r 会被损坏符号链接/缺失文件触发数百个 "cannot stat"，
    # 在 set -euo pipefail 下直接中断部署；tar 对缺失目标容错且不中断。
    if tar czf "${BACKUP_PATH}" \
        --exclude="node_modules" --exclude=".venv" --exclude=".venv2" --exclude="venv" \
        --exclude="__pycache__" --exclude=".pytest_cache" --exclude="*.pyc" --exclude=".git" \
        --exclude="*.db" \
        -C "$(dirname "${DEPLOY_PATH}")" "$(basename "${DEPLOY_PATH}")" 2>/dev/null; then
        log "备份完成: ${BACKUP_PATH}"
    else
        warn "备份失败(tar 退出非零)，继续部署但失去回滚能力"
        BACKUP_PATH=""
    fi
else
    warn "没有旧版本需要备份"
    BACKUP_PATH=""
fi

# ---- 2. 复制文件 ----
log "复制文件（保留 .env 配置）..."
mkdir -p "${DEPLOY_PATH}"

# 云端 DATABASE_URL=PostgreSQL，SQLite 时代 .db 备份/恢复已移除（卡 ad470df5），仅保留 .env 备份
if [ -f "${DEPLOY_PATH}/backend/.env" ]; then
    cp "${DEPLOY_PATH}/backend/.env" /tmp/tianlian_env_backup
fi

cp -r "${INSTALL_DIR}/backend" "${DEPLOY_PATH}/"

# 清理部署包带入的本地开发 SQLite（云端 DATABASE_URL=PostgreSQL, .db 非生产数据源, 卡 0eae0bd5）
rm -f "${DEPLOY_PATH}"/backend/*.db 2>/dev/null || true

mkdir -p "${DEPLOY_PATH}/frontend"
cp -r "${INSTALL_DIR}/frontend/"* "${DEPLOY_PATH}/frontend/"

# 恢复配置（.db 恢复已随 SQLite 时代备份逻辑一并移除，卡 ad470df5）
if [ -f /tmp/tianlian_env_backup ]; then
    cp /tmp/tianlian_env_backup "${DEPLOY_PATH}/backend/.env"
    rm -f /tmp/tianlian_env_backup
fi

# Provisioning: POD_COMM_SHARED_SECRET (卡5487bb7a / D2 pod_security.py fail-closed)
# 未配置时 /api/v1/pod/*, /api/v1/cross/* 拒绝全部请求。首次部署自动生成强随机写入 .env。
ENV_FILE="${DEPLOY_PATH}/backend/.env"
if [ -f "${ENV_FILE}" ] && ! grep -q "^POD_COMM_SHARED_SECRET=" "${ENV_FILE}"; then
    [ -n "$(tail -c 1 "${ENV_FILE}")" ] && printf '\n' >> "${ENV_FILE}"   # 防末行无换行污染既有键
    printf 'POD_COMM_SHARED_SECRET=***' "$(openssl rand -hex 32)" >> "${ENV_FILE}"
    log "POD_COMM_SHARED_SECRET 未配置，已自动生成强随机值写入 .env"
fi

# 修复前端文件权限，防止nginx 403
find "${DEPLOY_PATH}/frontend" -type d -exec chmod 755 {} +
find "${DEPLOY_PATH}/frontend" -type f -exec chmod 644 {} +
chown -R www-data:www-data "${DEPLOY_PATH}/frontend/" 2>/dev/null || true
log "前端文件权限已修复"

# ---- 3. 安装后端依赖 ----
log "安装后端依赖..."
cd "${DEPLOY_PATH}/backend"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q --no-warn-script-location 2>&1 | tail -3 || \
    pip install -r requirements.txt --break-system-packages 2>&1 | tail -3 || \
    pip3 install -r requirements.txt --break-system-packages 2>&1 | tail -3
log "后端依赖安装完成"

# ---- 4. 数据库迁移 ----
log "停止后端服务（防止SQLite并发写入损坏）..."
systemctl stop tianlian-backend 2>/dev/null || true
sleep 1
log "数据库迁移..."
source venv/bin/activate

# 清理 Python 字节码缓存，杜绝历史偶发的 ".pyc 含 null bytes / 旧缓存污染" 导致 alembic 读取异常
find "${DEPLOY_PATH}/backend" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "${DEPLOY_PATH}/backend" -name '*.pyc' -delete 2>/dev/null || true
# 清理 macOS AppleDouble 垃圾文件（._xxx.py 会被 alembic 的 *.py glob 误读 → null bytes SyntaxError）
find "${DEPLOY_PATH}/backend" -name '._*' -delete 2>/dev/null || true

# Alembic 受控迁移（⚠️ 必须在 create_all 兜底之前 — 2026-07-31 事故教训:
# create_all 先跑会把迁移里的新表建成空表(无种子数据), 随后 alembic create_table
# 撞 "relation already exists" 失败, 版本链永久卡住, 后续所有迁移全堵。
# 正确顺序: 迁移先行(含种子), create_all 只兜底补迁移未覆盖的缺失表。
# 失败仍不阻断部署, 但用 RC 捕获真实退出码 — `| tail` 管道会吞掉失败码。）
log "执行 alembic 迁移 (upgrade head)..."
ALEMBIC_RC=0
ALEMBIC_OUT=$(alembic upgrade head 2>&1) || ALEMBIC_RC=$?
printf '%s\n' "${ALEMBIC_OUT}" | tail -5
if [ "${ALEMBIC_RC}" -ne 0 ]; then
    warn "alembic upgrade head 失败 (rc=${ALEMBIC_RC}) — create_all 将兜底建表, 但种子数据/版本链需人工补, 见上方输出"
fi

# 版本链完整性校验 (卡 6f5a35a2 方案A): baseline 已冻结为静态快照, 不再动态吸收模型漂移,
# 版本链必须真正走到 head — create_all 兜底只能补表, 补不了种子/索引/后续迁移语义。
# upgrade 退出码 0 也要复核 current==head, 防部分执行/多 head 分叉静默通过。
CURRENT_REV=$(alembic current 2>/dev/null | awk '{print $1}' | tail -n1) || CURRENT_REV=""
HEAD_REV=$(alembic heads 2>/dev/null | awk '{print $1}' | tail -n1) || HEAD_REV=""
if [ -n "${CURRENT_REV}" ] && [ -n "${HEAD_REV}" ] && [ "${CURRENT_REV}" = "${HEAD_REV}" ]; then
    log "alembic 版本链完整: current(${CURRENT_REV}) == head(${HEAD_REV})"
else
    warn "alembic 版本链不完整: current='${CURRENT_REV:-<空>}' head='${HEAD_REV:-<空>}' — 请人工排查 (多 head 用 alembic merge)"
fi

# create_all 兜底: 对已存在表是 no-op, 只补迁移未覆盖的缺失表（不会抢 DDL）
python3 -c "
from app.core.database import Base, engine
from app.models import *
Base.metadata.create_all(bind=engine)
print('数据库表创建/迁移完成')
" 2>&1 | tail -2

# ---- 4.5 Schema 漂移检测（只读守卫，不阻断部署）----
# 背景: 生产两次“模型加列忘写迁移 → 测试绿生产崩”。此处迁移完成后只读比对
# SQLAlchemy 模型与库实际结构，提前暴露漂移；孤儿列等已知项不卡部署。
# check_schema_drift.py 退出码: 0=无漂移 / 1=有漂移 / 2=连接失败；
# 任何非零都用 `|| DRIFT_RC=$?` 接住，绝不让 set -e 中断部署。
DRIFT_SCRIPT="${DEPLOY_PATH}/backend/scripts/check_schema_drift.py"
if [ ! -f "${DRIFT_SCRIPT}" ]; then
    : # 兼容老版本（无此脚本），静默跳过
else
    # 从 backend/.env 取 DATABASE_URL 注入检测子进程（脚本只在 parse 阶段读此环境变量；
    # 不整包 source .env，避免把 SECRET_KEY 等其他密钥铺进安装环境）。
    DRIFT_URL=""
    if [ -f "${DEPLOY_PATH}/backend/.env" ]; then
        DRIFT_URL=$(grep -E '^[[:space:]]*DATABASE_URL=' "${DEPLOY_PATH}/backend/.env" | tail -n1 | cut -d= -f2- | tr -d "\"'") || true
    fi
    if [ -z "${DRIFT_URL}" ]; then
        warn "Schema 漂移检测: .env 未配置 DATABASE_URL，跳过检测"
    else
        log "Schema 漂移检测（只读）..."
        DRIFT_RC=0
        # 子进程内注入 DATABASE_URL（凭据不落 install.sh 主环境）；2>&1 捕获报告与 traceback
        DRIFT_OUT=$( cd "${DEPLOY_PATH}/backend" && DATABASE_URL="${DRIFT_URL}" venv/bin/python scripts/check_schema_drift.py 2>&1 ) || DRIFT_RC=$?
        # 脱敏: URL 里 user:password@ → user:***@，防凭据落 LOG_FILE / ssh 回传控制台
        DRIFT_OUT=$( printf '%s\n' "${DRIFT_OUT}" | sed -E 's#(://[^/@:]+:)[^@/]+@#\1***@#g' )
        printf '%s\n' "${DRIFT_OUT}" | tee -a "${LOG_FILE}" || true
        case "${DRIFT_RC}" in
            0)  log "Schema 漂移检测: 无漂移" ;;
            1)  warn "Schema 漂移检测: 检测到漂移（见上方报告），不阻断部署 — 请人工确认是否补 alembic 迁移" ;;
            2)  warn "Schema 漂移检测: 连接失败，跳过检测（见上方报告）" ;;
            *)  warn "Schema 漂移检测: 异常退出 (rc=${DRIFT_RC})，跳过检测" ;;
        esac
    fi
fi

# ---- 5. 重启服务 ----
log "重启服务..."
systemctl daemon-reload 2>/dev/null || true
systemctl restart tianlian-backend 2>/dev/null || systemctl restart tianlian-backend.service

# celery beat/worker 也必须重启：beat 内存中持有 beat_schedule（新任务条目不会自动加载），
# worker 内存中持有已注册 task 代码（新 task/改动不会生效）。2026-08-20 卡eb9f824b 部署后实测实锤。
# 容错：服务不存在时 systemctl 返回非零，仅告警不阻断（与后端重启的容错姿态一致）。
for SVC in tianlian-celery-beat tianlian-celery-worker; do
    if systemctl list-unit-files "${SVC}.service" 2>/dev/null | grep -q "${SVC}"; then
        if systemctl restart "${SVC}" 2>/dev/null; then
            log "已重启 ${SVC}"
        else
            warn "重启 ${SVC} 失败，请手动检查（新 celery 任务/调度不会生效）"
        fi
    fi
done

# ---- 6. 等待启动 ----
log "等待后端启动 (最多120秒)..."
WAIT_MAX=120
for i in $(seq 1 $WAIT_MAX); do
    HEALTH=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 "${HEALTH_ENDPOINT}" 2>/dev/null || echo "000")
    if [ "$HEALTH" = "200" ]; then
        log "后端启动完成 ($((i))秒)"
        break
    fi
    if [ "$i" -eq "$WAIT_MAX" ]; then
        err "后端启动超时 (${WAIT_MAX}秒)"
        # ---- 自动回滚 ----
        log "执行自动回滚..."
        rm -rf "${DEPLOY_PATH}"
        if [ -n "${BACKUP_PATH}" ] && [ -f "${BACKUP_PATH}" ]; then
            mkdir -p "${DEPLOY_PATH}"
            tar xzf "${BACKUP_PATH}" -C "$(dirname "${DEPLOY_PATH}")"
            log "回滚完成: 恢复了备份 ${BACKUP_PATH}"
            systemctl restart tianlian-backend
            # 回滚同样需要重启 celery，使 beat/worker 回到旧版本的 schedule/task 代码
            for SVC in tianlian-celery-beat tianlian-celery-worker; do
                systemctl restart "${SVC}" 2>/dev/null || true
            done
            sleep 3
            ROLLBACK_HEALTH=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "${HEALTH_ENDPOINT}" 2>/dev/null || echo "000")
            if [ "$ROLLBACK_HEALTH" = "200" ]; then
                log "回滚后服务正常"
            else
                err "回滚后服务异常 (HTTP ${ROLLBACK_HEALTH})，请手动检查"
            fi
        else
            err "没有备份可回滚，服务可能不可用"
        fi
        exit 1
    fi
    sleep 1
done

# ---- 7. 部署后验证 ----
log "部署后验证..."
HEALTH_BODY=$(curl -s --connect-timeout 5 "${HEALTH_ENDPOINT}" 2>/dev/null || echo '{}')
SERVICE_STATUS=$(echo "$HEALTH_BODY" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")
SERVICE_VERSION=$(echo "$HEALTH_BODY" | python3 -c "import sys,json;print(json.load(sys.stdin).get('version','unknown'))" 2>/dev/null || echo "unknown")

if [ "$SERVICE_STATUS" = "healthy" ]; then
    log "服务状态: ${SERVICE_STATUS}, 版本: ${SERVICE_VERSION}"
else
    warn "服务状态异常: ${SERVICE_STATUS}"
fi

# ---- 8. 清理备份（保留最后3个）----
log "清理旧备份..."
ls -dt "${DEPLOY_PATH}_backup_"* 2>/dev/null | tail -n +4 | xargs -I{} rm -rf {} 2>/dev/null || true

log "=== 安装完成 ==="
INSTALL_SCRIPT

chmod +x "${DEPLOY_DIR}/install.sh"

log "部署包创建完成: ${DEPLOY_DIR}/"
echo ""

# 可选: 打包为一个文件
info "打包部署文件..."
tar czf "${DEPLOY_DIR}.tar.gz" --exclude="._*" --exclude=".DS_Store" --exclude="*.db" "${DEPLOY_DIR}/"
log "部署包: ${DEPLOY_DIR}.tar.gz ($(du -h "${DEPLOY_DIR}.tar.gz" | awk '{print $1}'))"
echo ""

# 检查是否为 dry-run
if [ "${1:-}" = "--dry-run" ]; then
    warn "Dry-run 模式: 部署包已创建，未上传"
    exit 0
fi

# ==================== 阶段3: 上传到服务器 ====================
info "阶段 3/6: 上传到服务器..."

scp -o StrictHostKeyChecking=no -q "${DEPLOY_DIR}.tar.gz" "${DEPLOY_USER}@${DEPLOY_HOST}:/tmp/"
log "上传完成"
echo ""

# ==================== 阶段4: 执行安装 ====================
info "阶段 4/6: 执行远程安装..."
echo ""

# 服务器端先解压 tar.gz（单文件传输，避免 scp -r 数万小文件逐个 round-trip），再执行安装
# set -e 会击杀管道内 ssh 非零退出，失败分支永远执行不到 → 暂时关闭，用 PIPESTATUS 精确取 ssh 退出码
set +e
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -o ServerAliveCountMax=6 "${DEPLOY_USER}@${DEPLOY_HOST}" "tar xzf /tmp/${DEPLOY_DIR}.tar.gz -C /tmp/ && bash /tmp/${DEPLOY_DIR}/install.sh" 2>&1 | while IFS= read -r line; do echo "   ${line}"; done
REMOTE_EXIT_CODE=${PIPESTATUS[0]}
set -e

if [ $REMOTE_EXIT_CODE -ne 0 ]; then
    err "远程安装失败 (退出码: $REMOTE_EXIT_CODE)"
    # 回捞服务器端安装日志尾部（只读，不改动服务器状态；失败不阻断）
    warn "回捞服务器端安装日志 /tmp/tianlian-install-*.log ..."
    ssh -o StrictHostKeyChecking=no "${DEPLOY_USER}@${DEPLOY_HOST}" "tail -50 /tmp/tianlian-install-*.log 2>/dev/null" 2>/dev/null | while IFS= read -r line; do echo "   [远端日志] ${line}" | tee -a "${LOG_FILE}"; done || true
    # 本地清理
    rm -rf "${DEPLOY_DIR}"
    exit 1
fi

log "远程安装成功"
echo ""

# ==================== 阶段5: 最终验证 ====================
info "阶段 5/6: 最终验证..."
sleep 2

# 验证前端
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 "${APP_URL}" 2>/dev/null || echo "000")
# 验证后端
API_CODE=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 "${APP_URL}/api/v1/health" 2>/dev/null || echo "000")
# 后端详情
API_BODY=$(curl -s --connect-timeout 5 "${APP_URL}/api/v1/health" 2>/dev/null || echo '{}')

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ] || [ "$HTTP_CODE" = "301" ]; then
    log "前端: ${APP_URL} → HTTP ${HTTP_CODE}"
else
    warn "前端: HTTP ${HTTP_CODE} (可能未配置nginx)"
fi

if [ "$API_CODE" = "200" ]; then
    log "后端: ${APP_URL}/api/v1/health → HTTP ${API_CODE}"
else
    warn "后端: HTTP ${API_CODE}"
fi

echo ""
echo "========================================"
if [ "$API_CODE" = "200" ]; then
    log "🎉 部署成功！"
else
    warn "⚠️  部署完成但存在异常，请手动检查服务状态"
fi
echo "  部署目录: ${DEPLOY_PATH}"
echo "  部署日志: ${LOG_FILE}"
echo "========================================"
echo ""

# ==================== 阶段6: 清理本地 ====================
info "阶段 6/6: 清理临时文件..."
rm -rf "${DEPLOY_DIR}"
ssh -o StrictHostKeyChecking=no "${DEPLOY_USER}@${DEPLOY_HOST}" "rm -rf /tmp/${DEPLOY_DIR} /tmp/${DEPLOY_DIR}.tar.gz" 2>/dev/null || true
log "清理完成"
echo ""
