# Phase 12 - 云端 Celery Worker 快速部署命令（Legacy 手工补建 systemd unit）

> ⚠️ **Legacy 废弃警示**
> 本文档仅为 Celery systemd unit 的**手工补建备忘**，日常部署请勿照此操作。
> 日常部署（代码同步、依赖安装、数据库迁移、celery 重启）一律使用根目录 `deploy.sh`，
> 完整 6 阶段流程见 **[docs/DEPLOY.md](./DEPLOY.md)**。
> `deploy.sh` 阶段 5 已自动 `systemctl restart tianlian-celery-beat tianlian-celery-worker`
>（见 `deploy.sh:285`）。本文仅在**首次部署、服务器尚未创建 celery unit 文件**时手工执行一次。

**服务器**: demo.example.com
**用户**: root
**项目路径**: /opt/tianlian-cloud
**后端端口**: 8080

---

## 🚀 手工补建 Celery unit 命令

> 代码通过 `deploy.sh` 打成 tar 包、scp 上传、服务器端解压安装（`deploy.sh` 阶段 2–4）。
> **生产两树均 `NOT_A_GIT_REPO`，禁止 `git pull`**——服务器上没有 git 工作树，pull 必败。
> 以下步骤的前提是 `deploy.sh` 已把后端代码部署到 `/opt/tianlian-cloud/backend`。

```bash
# 1. SSH 连接
ssh root@demo.example.com

# 2. 进入后端目录（代码已由 deploy.sh tar 包部署到此，无需 git pull）
cd /opt/tianlian-cloud/backend

# 3. 确保 Redis 运行
systemctl status redis || systemctl start redis

# 4. 激活虚拟环境并安装 Celery
source venv/bin/activate
pip install celery redis flower

# 5. 创建 systemd 服务文件（如未创建）
#    ⚠️ unit 名必须带 tianlian- 前缀，与 deploy.sh:285 重启的
#       tianlian-celery-worker / tianlian-celery-beat 完全一致。
#       若沿用旧文档的 celery-worker / celery-beat（无前缀），
#       会造出与生产并存的两套冲突服务。
cat > /etc/systemd/system/tianlian-celery-worker.service << 'EOF'
[Unit]
Description=Tianlian Cloud Celery Worker
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tianlian-cloud/backend
Environment="CELERY_BROKER_URL=redis://localhost:6379/0"
Environment="CELERY_RESULT_BACKEND=redis://localhost:6379/1"
ExecStart=/opt/tianlian-cloud/backend/venv/bin/celery -A app.core.celery_app worker --loglevel=info --queues=default,analytics,maintenance --concurrency=4
Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/tianlian-celery-beat.service << 'EOF'
[Unit]
Description=Tianlian Cloud Celery Beat
After=network.target redis.service tianlian-celery-worker.service
Requires=redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tianlian-cloud/backend
Environment="CELERY_BROKER_URL=redis://localhost:6379/0"
Environment="CELERY_RESULT_BACKEND=redis://localhost:6379/1"
ExecStart=/opt/tianlian-cloud/backend/venv/bin/celery -A app.core.celery_app beat --loglevel=info
Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

# 6. 启动服务
systemctl daemon-reload
systemctl start tianlian-celery-worker tianlian-celery-beat
systemctl enable tianlian-celery-worker tianlian-celery-beat

# 7. 验证（等待 3 秒）
sleep 3
systemctl status tianlian-celery-worker tianlian-celery-beat

# 8. 查看日志（如有问题）
journalctl -u tianlian-celery-worker -u tianlian-celery-beat -f
```

---

## ✅ 验证标准

> ⚠️ `/api/v1/tasks/*` 整个路由要求 `analytics:manage` 写权限
>（见 `backend/app/api/v1/tasks.py:15`，`router = APIRouter(dependencies=[Depends(require_write_permission("analytics:manage"))])`）。
> **无 token 实测返回 401**——旧文档称"curl 直接返回 200"是错的。先登录拿 token 再验证。

### 后端健康（公开端点，无需鉴权）

```bash
curl http://localhost:8080/api/v1/health
# 返回 { "status": "healthy", "version": "3.0.0", ... }
```

### Celery Worker 状态（需鉴权）

```bash
# 1. 登录拿 token —— OAuth2 密码表单，响应体字段名为 token（非 access_token）
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=<管理员账号>&password=<密码>" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# 2. 带 token 查 worker 状态（不带 token → 401）
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/tasks/status
```

返回应为：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "status": "running",
    "active_tasks": 0,
    "workers": ["celery@hostname"],
    "broker_url": "redis://localhost:6379/0"
  },
  "timestamp": 1234567890
}
```

> `data` 由 `get_celery_status()` 产生（`backend/app/core/celery_app.py`）：
> 无 worker 时 `status` 为 `no_workers`；Celery 未安装时为 `unavailable`。

---

## 🛠️ 快速测试命令

```bash
# 提交测试任务（需鉴权，复用上方 TOKEN）
curl -X POST http://demo.example.com/api/v1/tasks/submit \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_type":"health_score","params":{"device_id":1}}'

# 查看任务结果（替换 task_id，需鉴权）
curl -H "Authorization: Bearer $TOKEN" http://demo.example.com/api/v1/tasks/result/<task_id>
```

---

**石猴派发，云端执行**
