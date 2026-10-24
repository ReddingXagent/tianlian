# 天链 V3 部署文档

> 生产部署使用根目录 `deploy.sh`，6 阶段全自动化流程，内置健康检查、数据库保留、自动回滚。

## 环境要求

| 项 | 要求 | 说明 |
|----|------|------|
| 本地 | curl / ssh / scp / tar / npm | 部署机执行 `deploy.sh` 前自动检测 |
| 服务器 | Python 3.9+ / systemd / Nginx | 远程通过 ssh 操作 |
| 数据库 | SQLite（默认，文件 `backend/tianlian_v3.db`）/ PostgreSQL | 部署时自动保留既有数据库 |
| 端口 | 后端 `8080`（生产）/ 前端 80（Nginx） | 本地开发后端用 8000，**生产部署固定 8080** |

---

## 快速部署

```bash
# 一键部署（默认目标：root@demo.example.com:/opt/tianlian-cloud）
bash deploy.sh

# 试运行（只构建+打包，不上传）
bash deploy.sh --dry-run
```

### 部署目标（`deploy.sh` 顶部配置）

```
DEPLOY_USER    = root
DEPLOY_HOST    = demo.example.com
DEPLOY_PATH    = /opt/tianlian-cloud
BACKEND_PORT   = 8080
HEALTH_ENDPOINT = /api/v1/health
```

---

## 6 阶段部署流程

`deploy.sh` 按以下阶段顺序执行，每阶段输出带颜色日志并写入 `deploy_<时间戳>.log`：

### 阶段 0/6 — 部署前健康检查
- 检测本地必备命令：`curl ssh scp tar npm`，缺失即中止
- 探测远程服务当前健康状态（非 200 仅告警，不阻断）

### 阶段 1/6 — 构建前端
- `cd frontend`，若 `node_modules` 不存在先 `npm ci`
- `npm run build`，校验 `dist/index.html` 已生成
- 失败则中止

### 阶段 2/6 — 创建部署包
- 复制 `backend/` 与 `frontend/dist/*` 到 `deploy_<时间戳>/`
- **剔除本地开发产物**：`venv` / `.venv` / `*.db` / `__pycache__` / `*.pyc`（防止覆盖云端）
- 内嵌生成远程 `install.sh`（见下节）
- 设置 `COPYFILE_DISABLE=1`，防止 macOS bsdtar 生成 `._xxx` AppleDouble 文件污染服务器（曾导致 alembic 读取 `._*.py` 报 null bytes）
- 打包为单文件 `deploy_<时间戳>.tar.gz`（避免 `scp -r` 数万小文件逐个 round-trip）

### 阶段 3/6 — 上传到服务器
- `scp` 上传 `tar.gz` 到远程 `/tmp/`

### 阶段 4/6 — 执行远程安装
- `ssh` 远程解压并执行 `install.sh`（详见下节）

### 阶段 5/6 — 最终验证
- 校验前端 `http://demo.example.com`（200/301/302 视为正常）
- 校验后端 `http://demo.example.com/api/v1/health` 返回 200

### 阶段 6/6 — 清理临时文件
- 删除本地 `deploy_<时间戳>/` 目录
- 删除远程 `/tmp/deploy_<时间戳>*`

---

## 远程 `install.sh` 内部步骤

部署包内的 `install.sh` 在服务器端执行，共 8 步：

1. **备份旧版本** — `tar czf` 打包 `/opt/tianlian-cloud`（排除 `node_modules` / `.venv` / `venv` / `__pycache__` / `.pytest_cache` / `*.pyc` / `.git`），失败不阻断但失去回滚能力
2. **复制文件（保留数据库）** — 先备份 `tianlian_v3.db` 与 `.env` 到 `/tmp`，复制新代码后再恢复，**防止部署覆盖生产数据与配置**
3. **修复前端权限** — 目录 755 / 文件 644 / `chown www-data`，防 Nginx 403
4. **安装后端依赖** — `python3 -m venv venv`（不存在时）+ `pip install -r requirements.txt`（含 `--break-system-packages` 兜底）
5. **数据库迁移** — 停止后端服务（防 SQLite 并发写入损坏）→ **`alembic upgrade head` 先行**（含种子数据；捕获真实退出码，失败显式 warn，不被管道吞）→ `Base.metadata.create_all` 只补迁移未覆盖的缺失表（对已存在表 no-op）→ 清理 `__pycache__`/`.pyc`/`._*`。⚠️ 顺序不可颠倒：create_all 先跑会把迁移新表建成空表（无种子），alembic 随后撞 `relation already exists` 致版本链卡死（2026-07-31 生产事故根因，根治见 commit 59880f72d）
6. **重启服务** — `systemctl daemon-reload && systemctl restart tianlian-backend`
7. **等待启动（最多 120 秒）** — 轮询 `/api/v1/health`；**超时则触发自动回滚**
8. **部署后验证 + 清理备份** — 校验服务状态与版本，旧备份保留最后 3 个

---

## 自动回滚机制

阶段 7 等待启动超时（120s 未返回 200）时：

1. 删除当前 `/opt/tianlian-cloud`
2. 从步骤 1 的备份 `tar.gz` 解压恢复
3. `systemctl restart tianlian-backend` 并复检健康
4. 回滚后仍异常则告警，提示人工介入

> 因此**部署前必须有可用备份**；首次部署或备份失败时不具备回滚能力。

---

## 环境变量配置

服务器 `backend/.env`（部署时自动保留，不被新包覆盖）。关键项：

```env
DB_TYPE=sqlite                       # 或 postgres
DATABASE_URL=sqlite:///./tianlian_v3.db
SECRET_KEY=<生产强随机串>             # 必改
HOST=0.0.0.0
PORT=8080                            # 生产固定 8080
ACCESS_TOKEN_EXPIRE_MINUTES=1440
ALERT_WEBHOOK_SECRET=<共享密钥>       # Alertmanager 回调认证，详见下方加固段
CORS_ORIGINS=http://demo.example.com,http://localhost:3004
```

完整字段见项目根 `.env.example` 与 `backend/app/core/config.py`。

---

## 健康检查

```bash
# 后端健康（部署脚本轮询此端点）
curl http://demo.example.com/api/v1/health
# 返回 { "status": "healthy", "version": "3.0.0", ... }
```

---

## 手工部署（备选）

> 一般情况下使用 `deploy.sh` 即可。以下为 systemd / Nginx 的底层配置参考。

### systemd 服务
```bash
sudo cp tianlian-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tianlian-backend
sudo systemctl start tianlian-backend
```

### Nginx
```bash
sudo cp tianlian-nginx.conf /etc/nginx/conf.d/
sudo nginx -t
sudo systemctl restart nginx
```

### 访问地址
- 前端：http://demo.example.com
- 后端 API：http://demo.example.com/api/v1
- API 文档：http://demo.example.com/api/docs

---

## 历史安全加固记录

### 2026-07-26 Alertmanager Webhook 认证加固（da16d511）

**背景**：`POST /api/v1/alert-webhook` 原先在 `enforce_auth` 公开白名单中且无任何认证，任何人可 POST 伪造 critical 告警刷屏IM（通知通道 DoS）。

**变更**：端点新增共享密钥校验（详见 `backend/app/api/v1/alert_webhook.py`）：
- 从请求头 `X-Webhook-Secret` 或 query `?secret=` 读取密钥
- 与 `settings.ALERT_WEBHOOK_SECRET` 做 `hmac.compare_digest` 常数时间比较
- 密钥未配置（None/空）→ 拒绝所有请求（403）并 warning，**强制生产配置，不保留裸奔兼容**
- 不匹配 → 403

`GET /alert-webhook/health` 仍公开（无害健康检查，不受影响）。

**部署必做（丁哥侧操作）**：
1. 在 `backend/.env` 配置：
   ```env
   ALERT_WEBHOOK_SECRET=<生成强密钥>
   # 生成命令: python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Alertmanager `alertmanager.yml` 的 `webhook_configs.url` 末尾追加 `?secret=<同值>`
3. **顺序不能反**：先配 `.env` 再配 Alertmanager。若先发版而后端未配 secret，所有告警将被 403 拒绝（这是强制配置的预期行为）
4. 重启后端使 `.env` 生效；改 `alertmanager.yml` 后 `reload` Alertmanager

### 2026-05-17 安全加固

**CORS 白名单**：
```python
ALLOWED_ORIGINS = [
    "http://localhost:3004", "http://localhost:3000", "http://localhost:5173",
    "http://demo.example.com", "http://127.0.0.1:3004",
]
```

**安全响应头**：`X-Content-Type-Options: nosniff` / `X-Frame-Options: DENY` / `X-XSS-Protection` / HSTS / `Referrer-Policy`

**前端性能**：React lazy loading 分包；`manualChunks` 拆分 antd/echarts/three 等大依赖；生产关闭 sourcemap 与 PWA。

**异常处理**：DEBUG 模式可暴露错误详情；生产模式脱敏，全局异常处理器不泄露堆栈与内部路径。
