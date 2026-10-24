#!/bin/bash
# ─── 天链V3 Phase9 SSL证书表迁移脚本 ───
# 在目标服务器上执行, 新增 ssl_certificates 表

set -euo pipefail

DEPLOY_HOST="demo.example.com"
DEPLOY_USER="root"
DEPLOY_PATH="/opt/tianlian-v3"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Phase9: SSL 证书表迁移"
echo "目标: ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# SSH 执行迁移
ssh -o StrictHostKeyChecking=no "${DEPLOY_USER}@${DEPLOY_HOST}" << 'REMOTE_SCRIPT'
set -euo pipefail

cd /opt/tianlian-v3/backend
source venv/bin/activate

python3 -c "
from app.core.database import engine, Base
from app.models.ssl_certificate import SSLCertificate

# 只创建新表 (create_all 不会修改已有表)
Base.metadata.create_all(bind=engine)
print('✅ ssl_certificates 表已创建/确认')
" 2>&1

echo "迁移完成"
REMOTE_SCRIPT

echo ""
echo "✅ Phase9 SSL 表迁移完成"
