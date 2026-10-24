#!/bin/bash
# 本地一键部署脚本 - 构建 + 上传 + 安装
# 用法: bash ci/deploy-local.sh [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

DEPLOY_HOST="root@demo.example.com"
DEPLOY_PATH="/opt/tianlian-v3"
DRY_RUN="${1:-}"

log()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*"; }
info()  { echo -e "${CYAN}[→]${NC} $*"; }

# ============================================
# 1. 构建前端
# ============================================
info "1/5 构建前端..."
cd frontend
npm run build 2>/dev/null || npm run build
log "前端构建完成 $(ls -la dist/index.html 2>/dev/null | awk '{print $5}' || echo '?')"

# ============================================
# 2. 创建部署包
# ============================================
cd "${PROJECT_DIR}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEPLOY_DIR="/tmp/tianlian-deploy-${TIMESTAMP}"
mkdir -p "${DEPLOY_DIR}"

info "2/5 创建部署包..."
cp -r backend "${DEPLOY_DIR}/"
cp -r frontend/dist "${DEPLOY_DIR}/frontend"
cp deploy.sh "${DEPLOY_DIR}/" 2>/dev/null || true

# 移除本地 venv 和数据库（防止覆盖云端环境）
rm -rf "${DEPLOY_DIR}/backend/venv" 2>/dev/null || true
rm -f "${DEPLOY_DIR}/backend/tianlian_v3.db" 2>/dev/null || true
rm -f "${DEPLOY_DIR}/backend/tianlian.db" 2>/dev/null || true

# 移除本地开发文件
find "${DEPLOY_DIR}" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "${DEPLOY_DIR}" -name '*.pyc' -delete 2>/dev/null || true

# 创建安装脚本
cat > "${DEPLOY_DIR}/install.sh" << 'INSTALL_EOF'
#!/bin/bash
set -euo pipefail

DEPLOY_PATH="/opt/tianlian-v3"
BACKUP_PATH="${DEPLOY_PATH}_backup_$(date +%Y%m%d_%H%M%S)"

echo "[备份] 旧版本 → ${BACKUP_PATH}"
[ -d "$DEPLOY_PATH" ] && cp -r "$DEPLOY_PATH" "$BACKUP_PATH"

echo "[部署] 复制文件..."
mkdir -p "$DEPLOY_PATH"
cp -r backend "$DEPLOY_PATH/"
mkdir -p "$DEPLOY_PATH/frontend"
cp -r frontend/* "$DEPLOY_PATH/frontend/"

echo "[部署] 安装后端依赖..."
cd "$DEPLOY_PATH/backend"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt 1>/dev/null 2>&1 || pip install -r requirements.txt 2>&1 | tail -3

echo "[部署] 数据库迁移..."
# 清理 Python 字节码缓存 + macOS AppleDouble（防 alembic 读取异常，对齐 deploy.sh 59880f72d）
find "$DEPLOY_PATH/backend" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$DEPLOY_PATH/backend" -name '*.pyc' -delete 2>/dev/null || true
find "$DEPLOY_PATH/backend" -name '._*' -delete 2>/dev/null || true

# Alembic 受控迁移（⚠️ 必须先于 create_all — 2026-07-31 事故教训:
# create_all 先跑会把迁移新表建成空表(无种子), 随后 alembic create_table 撞
# "relation already exists" 失败, 版本链永久卡死。迁移先行(含种子), create_all 只补漏。
# 捕获真实退出码 — |tail 管道会吞码; RC≠0 明确失败退出，禁静默 warn 继续）
ALEMBIC_RC=0
ALEMBIC_OUT=$(alembic upgrade head 2>&1) || ALEMBIC_RC=$?
printf '%s\n' "${ALEMBIC_OUT}" | tail -5
if [ "${ALEMBIC_RC}" -ne 0 ]; then
    echo "[失败] alembic upgrade head 失败 (rc=${ALEMBIC_RC}) — 部署中止, 需人工补种子/版本链, 见上方输出"
    exit 1
fi

# create_all 兜底: 对已存在表是 no-op，只补迁移未覆盖的缺失表
python3 -c "from app.core.database import Base, engine; from app.models import *; Base.metadata.create_all(bind=engine)" 2>&1 | tail -2

echo "[部署] 索引优化..."
# 创建缺失的数据库索引
python3 << 'IDXEOF' 2>&1 | tail -3
from sqlalchemy import inspect, text
from app.core.database import engine
inspector = inspect(engine)
with engine.connect() as conn:
    for table in inspector.get_table_names():
        indices = {i['name'] for i in inspector.get_indexes(table)}
        columns = [c['name'] for c in inspector.get_columns(table)]
        pk_info = inspector.get_pk_constraint(table)
        pk_cols = set(pk_info.get('constrained_columns', []) if pk_info else [])
        indexed = set()
        for idx in inspector.get_indexes(table):
            indexed.update(idx['column_names'])
        for col in columns:
            if col.endswith('_id') and col not in pk_cols and col not in indexed:
                idx_name = f"ix_{table}_{col}"
                if idx_name not in indices:
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON \"{table}\" ({col})"))
    conn.commit()
print('索引优化完成')
IDXEOF

echo "[部署] 重启服务..."
systemctl restart tianlian-backend 2>/dev/null || systemctl restart tianlian-backend.service
sleep 2
systemctl is-active --quiet tianlian-backend && echo "[✓] 后端服务运行中" || echo "[!] 后端服务异常"

echo "[部署] 重启Nginx..."
nginx -s reload 2>/dev/null || systemctl restart nginx
sleep 1

echo "[完成] 部署完成"
INSTALL_EOF
chmod +x "${DEPLOY_DIR}/install.sh"

# 打包
tar czf "${DEPLOY_DIR}.tar.gz" -C /tmp "tianlian-deploy-${TIMESTAMP}"
log "部署包: ${DEPLOY_DIR}.tar.gz ($(du -h "${DEPLOY_DIR}.tar.gz" | cut -f1))"

if [ "$DRY_RUN" = "--dry-run" ]; then
    warn "仅构建模式, 不上传服务器"
    rm -rf "${DEPLOY_DIR}" "${DEPLOY_DIR}.tar.gz"
    exit 0
fi

# ============================================
# 3. 上传到服务器
# ============================================
info "3/5 上传到服务器..."
scp -o StrictHostKeyChecking=no -q "${DEPLOY_DIR}.tar.gz" "${DEPLOY_HOST}:/tmp/"
log "上传完成"

# ============================================
# 4. 远程解压+安装
# ============================================
info "4/5 远程安装..."
ssh -o StrictHostKeyChecking=no "${DEPLOY_HOST}" "
    cd /tmp
    tar xzf tianlian-deploy-${TIMESTAMP}.tar.gz
    cd tianlian-deploy-${TIMESTAMP}
    bash install.sh
    cd /tmp
    rm -rf tianlian-deploy-${TIMESTAMP} tianlian-deploy-${TIMESTAMP}.tar.gz
" 2>&1 | while IFS= read -r line; do echo "   ${line}"; done

# ============================================
# 5. 验证
# ============================================
info "5/5 验证部署..."
sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 http://demo.example.com/ 2>/dev/null || echo '000')
API_CODE=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 http://demo.example.com/api/v1/health 2>/dev/null || echo '000')

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
    log "前端: http://demo.example.com → ${HTTP_CODE}"
else
    warn "前端: HTTP ${HTTP_CODE}"
fi

if [ "$API_CODE" = "200" ]; then
    log "后端: /api/v1/health → ${API_CODE}"
else
    warn "后端: HTTP ${API_CODE}"
fi

log "部署完成 ✓"

# ============================================
# 清理本地
# ============================================
rm -rf "${DEPLOY_DIR}" "${DEPLOY_DIR}.tar.gz"
