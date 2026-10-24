#!/bin/bash
# 设置 Git 仓库 post-receive 钩子 - 自动部署
# 在群辉Git服务器上运行此脚本
set -euo pipefail

REPO_DIR="$1"
if [ -z "$REPO_DIR" ]; then
    echo "用法: bash ci/git-hook-setup.sh /path/to/repo.git"
    exit 1
fi

HOOK="${REPO_DIR}/hooks/post-receive"

cat > "$HOOK" << 'HOOK_EOF'
#!/bin/bash
# Git post-receive hook - 自动部署天链V3到云服务器
set -euo pipefail

DEPLOY_HOST="root@demo.example.com"
DEPLOY_PATH="/opt/tianlian-v3"
WORK_DIR="/tmp/tianlian-deploy"

# 只处理 stable-v3.0 分支
while read oldrev newrev refname; do
    case "$refname" in
        refs/heads/stable-v3.0)
            echo "[自动部署] stable-v3.0 分支更新, 开始自动部署..."
            
            # 导出代码到工作目录
            mkdir -p "$WORK_DIR"
            git archive "$newrev" --format=tar | tar xf - -C "$WORK_DIR"
            
            # 构建前端
            cd "$WORK_DIR/frontend"
            npm ci 2>/dev/null && npm run build
            
            # 上传到云服务器
            cd "$WORK_DIR"
            tar czf /tmp/deploy.tar.gz --exclude=node_modules --exclude=.git backend/ frontend/dist/
            scp /tmp/deploy.tar.gz "${DEPLOY_HOST}:/tmp/"
            
            # 远程安装
            ssh "${DEPLOY_HOST}" "
                cd ${DEPLOY_PATH}
                tar xzf /tmp/deploy.tar.gz
                cd backend
                if [ -d .venv ]; then source .venv/bin/activate; elif [ -d venv ]; then source venv/bin/activate; fi
                pip install -r requirements.txt 2>&1 | tail -1
                systemctl restart tianlian-backend
                cp -r ${WORK_DIR}/frontend/dist/* ${DEPLOY_PATH}/frontend/
                nginx -s reload
                echo '部署完成'
            "
            
            rm -rf "$WORK_DIR" /tmp/deploy.tar.gz
            echo "[自动部署] 完成"
            ;;
    esac
done
HOOK_EOF

chmod +x "$HOOK"
echo "✓ post-receive hook 已安装: $HOOK"
