# CI/CD 部署流水线

## 一键部署

```bash
# 构建 + 部署到云服务器
make deploy

# 或直接运行
bash ci/deploy-local.sh
```

## 部署流程

1. 构建前端 (`npm run build`)
2. 打包后端 + 前端dist
3. SCP上传到云服务器
4. 安装依赖 + 数据库迁移
5. 重启服务
6. 验证健康检查

## GitHub Actions（可选）

配置仓库 Secrets 后启用:
- `DEPLOY_HOST`: demo.example.com
- `DEPLOY_USER`: root
- `DEPLOY_KEY`: SSH私钥

## Git hooks（群辉自动部署）

在群辉Git服务器执行:
```bash
bash ci/git-hook-setup.sh /path/to/repo.git
```
推送到 `stable-v3.0` 分支时自动部署。

## 环境要求

- **本地**: Node 20+, sshpass
- **云服务器**: Python 3.10+, Node 18+, Nginx, systemd