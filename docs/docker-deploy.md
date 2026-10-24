# 天链V3 Docker 容器化部署指南

> 最后更新: 2026-05-18

## 目录

- [前置要求](#前置要求)
- [快速开始](#快速开始)
- [部署步骤详解](#部署步骤详解)
- [架构概览](#架构概览)
- [环境变量说明](#环境变量说明)
- [数据持久化](#数据持久化)
- [常用命令](#常用命令)
- [故障排查](#故障排查)
- [生产环境建议](#生产环境建议)

---

## 前置要求

| 软件 | 最低版本 | 说明 |
|------|---------|------|
| Docker | 20.10+ | 容器运行时 |
| Docker Compose | 2.0+ | 容器编排 |
| 可用内存 | ≥ 2GB | 运行前后端容器 |
| 磁盘空间 | ≥ 5GB | 镜像 + 数据 |

### 安装 Docker (Linux)

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | bash

# CentOS/RHEL
sudo yum install -y docker docker-compose-plugin

# 启动 Docker
sudo systemctl enable docker --now
```

---

## 快速开始

```bash
# 1. 进入项目目录
cd tianlian-v3

# 2. 执行部署脚本
bash scripts/docker-deploy.sh deploy

# 3. 打开浏览器
# 前端: http://localhost:3004
# API文档: http://localhost:8000/docs
```

---

## 部署步骤详解

### 1. 克隆项目

```bash
git clone <仓库地址> tianlian-v3
cd tianlian-v3
```

### 2. 配置环境变量

```bash
# 复制示例配置
cp .env.docker .env

# 编辑配置（必须修改 SECRET_KEY）
vim .env
```

**必须修改**:
- `SECRET_KEY` - JWT 签名密钥，生成方式：
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- `DATABASE_URL` - 使用 PostgreSQL 时修改连接信息

### 3. 构建镜像

```bash
docker compose build
```

### 4. 启动服务

```bash
docker compose up -d
```

### 5. 验证部署

```bash
# 检查容器状态
docker compose ps

# 健康检查
curl http://localhost:8000/api/v1/health

# 查看服务日志
docker compose logs -f backend
```

---

## 架构概览

```
┌─────────────────────────────────────────────────┐
│                    Internet                      │
└────────────┬────────────────────────────────────┘
             │
    ┌────────▼────────┐
    │  Nginx (可选)    │  ← 端口 80 (统一入口)
    │  反向代理/负载   │
    └───┬─────────┬───┘
        │         │
   ┌────▼───┐  ┌──▼──────────┐
   │Frontend│  │  Backend     │
   │Nginx   │  │  FastAPI     │
   │ :3004  │  │  :8000       │
   │        │  │  (4 workers) │
   └────────┘  └──┬───────────┘
                  │
          ┌───────▼────────┐
          │   Data Volumes  │
          │  • SQLite/数据  │
          │  • 上传文件     │
          └────────────────┘
```

### 服务端口

| 服务 | 内部端口 | 外部端口 | 说明 |
|------|---------|---------|------|
| **后端** | 8000 | 8000 | FastAPI + Uvicorn (4 workers) |
| **前端** | 80 | 3004 | Nginx 静态文件 + API 代理 |
| **Nginx (可选)** | 80 | 80 | 统一入口反代 |

### 容器清单

| 容器名 | 镜像 | CPU限制 | 内存限制 |
|--------|------|---------|---------|
| tianlian-backend | python:3.11-slim | 1.0核 | 512M |
| tianlian-frontend | nginx:alpine | 0.5核 | 128M |
| tianlian-nginx | nginx:alpine | 0.25核 | 64M |

---

## 环境变量说明

完整环境变量见 `.env.docker` 文件。

### 核心配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_NAME` | 天链光储充运维系统 | 应用名称 |
| `DEBUG` | false | 调试模式（生产必须 false） |
| `SECRET_KEY` | (必填) | JWT 签名密钥，生产务必修改 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 1440 | Token 过期时间 (分钟) |

### 数据库配置

| 变量 | 格式 | 说明 |
|------|------|------|
| `DATABASE_URL` | `sqlite:///./data/tianlian_v3.db` | SQLite (默认) |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` | PostgreSQL |

### 可选服务

| 变量 | 说明 |
|------|------|
| `REDIS_URL` | Redis 连接（用于限流/缓存） |
| `SENTRY_DSN` | Sentry 错误监控 |
| `MQTT_BROKER` | MQTT 消息队列 |
| `CORS_ORIGINS` | 允许的跨域来源 |

---

## 数据持久化

Docker 卷挂载确保数据不丢失：

| 卷名 | 挂载路径 | 内容 |
|------|---------|------|
| `tianlian-backend-data` | `/app/data` | SQLite 数据库文件 |
| `tianlian-uploads-data` | `/app/uploads` | 上传的文件 |

```
docker compose down   ← 不会删除卷（数据保留）
docker compose down -v ← 删除卷（数据丢失！）
```

### 备份数据

```bash
# 备份数据卷
docker run --rm \
  -v tianlian-backend-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/backend-data-$(date +%Y%m%d).tar.gz -C /data .

docker run --rm \
  -v tianlian-uploads-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/uploads-$(date +%Y%m%d).tar.gz -C /data .
```

### 恢复数据

```bash
docker run --rm \
  -v tianlian-backend-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/backend-data-YYYYMMDD.tar.gz -C /data
```

---

## 常用命令

### 服务管理

```bash
# 启动
docker compose up -d

# 停止
docker compose down

# 重启
docker compose restart

# 重启单个服务
docker compose restart backend

# 重新构建并启动
docker compose up -d --build
```

### 日志查看

```bash
# 所有服务日志
docker compose logs -f

# 后端日志（最近 100 行）
docker compose logs --tail=100 backend

# 前端日志
docker compose logs frontend

# 按时间过滤
docker compose logs --since 10m backend
```

### 进入容器

```bash
# 进入后端容器
docker compose exec backend bash

# 进入前端容器
docker compose exec frontend sh
```

### 状态与监控

```bash
# 资源使用
docker stats

# 容器状态
docker compose ps

# 健康检查
bash scripts/docker-deploy.sh status
```

### 一键清理

```bash
# 停止并清理（保留数据卷）
docker compose down

# 完全清理（删除数据卷）
bash scripts/docker-deploy.sh clean
```

---

## 故障排查

### 后端启动失败

```bash
# 1. 查看详细日志
docker compose logs backend

# 2. 常见原因
# - 数据库文件权限问题 → 检查 volume 权限
# - 依赖安装失败 → 重新构建: docker compose build --no-cache backend
# - 端口冲突 → 检查 8000 端口: lsof -i :8000
```

### 前端无法访问

```bash
# 检查 Nginx 配置
docker compose exec frontend nginx -t

# 查看 Nginx 日志
docker compose exec frontend cat /var/log/nginx/tianlian-error.log
```

### API 代理不通

```bash
# 从前端容器测试后端连通性
docker compose exec frontend wget -qO- http://backend:8000/api/v1/health
```

### 数据库问题

```bash
# SQLite 文件检查
docker compose exec backend ls -la /app/data/

# 初始化数据库
docker compose exec backend python app/scripts/init_db.py
```

### 镜像构建慢

```bash
# 使用缓存构建
docker compose build

# 后台构建
docker compose build -q
```

### 完全重置

```bash
# 停止、删除卷、重新构建
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

---

## 生产环境建议

### 安全加固

1. **修改默认密钥**
   ```bash
   # 生成安全的 SECRET_KEY
   openssl rand -base64 32
   ```

2. **关闭 DEBUG**
   ```
   DEBUG=false
   ```

3. **使用 PostgreSQL**
   ```yaml
   # docker-compose.yml 添加
   db:
     image: postgres:15-alpine
     environment:
       POSTGRES_USER: tianlian
       POSTGRES_PASSWORD: ${DB_PASSWORD}
       POSTGRES_DB: tianlian_v3
     volumes:
       - postgres_data:/var/lib/postgresql/data
   ```

4. **配置 HTTPS**
   ```nginx
   # 使用 Let's Encrypt + nginx-proxy
   # 或配置 SSL 证书到 Nginx
   ```

5. **限制资源**
   ```yaml
   deploy:
     resources:
       limits:
         memory: 512M
         cpus: "1.0"
   ```

### 性能优化

- **增加 Uvicorn Workers**: 在 Dockerfile 中调整 `--workers` 参数
- **启用 Redis**: 配置 `REDIS_URL` 用于限流和缓存
- **外部 Nginx**: 使用专用 Nginx 服务器做反向代理和 SSL 终止

### 监控建议

- 配置 **Sentry DSN** 用于错误监控
- 集成 **Prometheus + Grafana** 监控容器指标
- 使用 **Docker Healthcheck** 自动检测服务状态
- 配置日志收集（ELK / Loki）

### 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建并滚动更新
docker compose up -d --build

# 清理旧镜像
docker image prune -f
```

---

## 附录：目录结构

```
tianlian-v3/
├── backend/
│   ├── Dockerfile           # 后端镜像
│   ├── requirements.txt     # Python 依赖
│   └── app/                 # 应用代码
├── frontend/
│   ├── Dockerfile           # 前端镜像（多阶段）
│   ├── nginx.conf           # Nginx 配置
│   └── src/                 # React 源码
├── scripts/
│   └── docker-deploy.sh     # 一键部署脚本
├── docs/
│   └── docker-deploy.md     # 本文档
├── docker-compose.yml       # 容器编排
├── .env.docker              # 环境变量示例
└── .dockerignore            # Docker 忽略文件
```

---

> 💡 遇到问题？查看日志: `docker compose logs -f` 或联系技术支持。