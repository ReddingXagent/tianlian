# ═══════════════════════════════════════════════════════════════
#  天链V3 - 部署指南
# ═══════════════════════════════════════════════════════════════

# 系统要求
- Docker >= 24.0.0
- Docker Compose >= 2.20.0
- Git

# 快速部署

## 1. 克隆代码
```bash
git clone <你的仓库地址> /opt/tianlian-v3
cd /opt/tianlian-v3
```

## 2. 配置环境变量
```bash
cp docker/.env.example docker/.env
# 编辑 docker/.env, 修改以下值:
# - DB_PASSWORD: 数据库密码 (随机字符串)
# - SECRET_KEY: JWT 密钥 (至少32位随机字符)
# - CORS_ORIGINS: 前端访问域名
```

## 3. 启动服务
```bash
# 启动全部服务
docker compose --env-file docker/.env up -d

# 查看启动日志
docker compose logs -f

# 确认所有服务健康
docker compose ps
```

## 4. 访问系统
- 前端: http://YOUR_SERVER_IP:80
- API: http://YOUR_SERVER_IP:80/api/v1/health

## 5. 配置 HTTPS (生产环境必须)
```bash
# 需要先设置域名 DNS A 记录指向服务器
sudo ./docker/scripts/setup-ssl.sh \
  --domain tianlian.example.com \
  --email admin@example.com
```

# 服务架构
```
┌─────────────┐     ┌──────────────┐
│   Nginx     │────▶│  FastAPI     │
│  (前端 SPA) │     │  (后端 API)  │
└──────┬──────┘     └──────┬───────┘
       │                   │
       │            ┌──────▼───────┐     ┌──────────┐
       │            │  PostgreSQL  │     │  Redis   │
       │            │  (数据库)    │     │ (缓存/队列)│
       │            └──────────────┘     └──────────┘
       │
       │            ┌──────────────┐
       └───────────▶│  Celery      │
                    │  (异步任务)   │
                    └──────────────┘
```

# 常用命令

## 启动/停止
```bash
docker compose up -d              # 启动所有服务
docker compose stop               # 停止所有服务
docker compose restart            # 重启所有服务
docker compose down               # 停止并删除容器
docker compose down -v            # 停止并删除数据卷 (⚠️ 会丢失数据)
```

## 查看日志
```bash
docker compose logs -f            # 所有服务日志
docker compose logs -f backend    # 后端日志
docker compose logs -f frontend   # 前端日志
docker compose logs -f db         # 数据库日志
```

## 数据库操作
```bash
# 创建备份
docker exec tianlian-db pg_dump -U tianlian tianlian_v3 > backup.sql

# 恢复备份
cat backup.sql | docker exec -i tianlian-db psql -U tianlian tianlian_v3
```

# 性能优化 (生产环境)

## 1. 调整 workers
在 docker-compose.yml 中修改:
```yaml
backend:
  command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers <CPU核心数*2+1>
```

## 2. 启用 Redis
修改 docker/.env:
```
REDIS_URL=redis://redis:6379/0
```

## 3. 日志轮转
```bash
docker compose logs --tail=100  # 限制日志行数
# 或在 docker-compose.yml 添加 logging 配置:
# logging:
#   driver: "json-file"
#   options:
#     max-size: "10m"
#     max-file: "3"
```

# 常见问题

## Q: 端口被占用?
修改 docker-compose.yml 中 ports 映射值

## Q: 数据库连接失败?
检查 docker/.env 中的 DATABASE_URL 和 DB_PASSWORD

## Q: 前端 API 请求 502?
1. 确认 backend 容器运行中: `docker compose ps`
2. 查看后端日志: `docker compose logs backend`
3. 检查 nginx 配置中的 proxy_pass 地址

## Q: 如何更新代码?
```bash
cd /opt/tianlian-v3
git pull
docker compose build
docker compose up -d
```

# 天链V3 运维管理系统
# 一键 Docker 部署方案
# 技术栈: React + FastAPI + PostgreSQL + Redis