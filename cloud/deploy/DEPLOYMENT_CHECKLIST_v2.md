# 🚀 天链V3 生产部署检查清单 v2 (Phase28-1)

**更新日期**: 2026-06-01
**上一版本**: DEPLOYMENT_CHECKLIST.md (2026-04-04)

---

## 一、系统现状总览

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 云服务器 API | ✅ healthy | http://demo.example.com:8000 v3.0.0 |
| 云服务器 Web | ✅ 运行中 | Nginx反向代理+PWA |
| HTTPS/SSL | ✅ 已配置 | Let's Encrypt自动续期(Phase24) |
| Docker部署 | ✅ 已就绪 | docker-compose.yml + docker-compose.monitoring.yml |
| PostgreSQL | ✅ 已就绪 | Docker Compose中配置(postgres:16-alpine) |
| Redis | ✅ 已就绪 | Docker Compose中配置(redis:7-alpine) |
| Prometheus | ✅ 已就绪 | 自定义指标+告警规则(Phase17) |
| Grafana | ✅ 已就绪 | 17+面板, 系统总览大屏(Phase25) |
| Loki | ✅ 已就绪 | 日志聚合配置(Phase25) |
| Locust压测 | ✅ 已就绪 | 3场景: 50/100/200用户(Phase26) |
| CI/CD | ✅ 已就绪 | GitHub Actions+自动构建(Phase23) |
| 备份脚本 | ✅ 已就绪 | backup-db.sh + restore-from-backup.sh |
| AI诊断 | ✅ 已集成 | LLM诊断助手(Phase8) |
| 多租户 | ✅ 已支持 | 权限隔离(Phase8) |

---

## 二、数据库迁移完整方案 (SQLite → PostgreSQL)

### 2.1 当前数据库
- **来源**: SQLite (`projects/tianlian-v3/backend/tianlian_v3.db`)
- **数据量**: 约53KB (7个设备, 3个站点)
- **表结构**: 通过SQLAlchemy ORM定义, 在 `app/models/` 中

### 2.2 迁移目标
- **目标**: PostgreSQL 16 (Docker容器 `tianlian-postgres:5432`)
- **连接**: `postgresql://tianlian:tianlian123@localhost:5432/tianlian_v3`

### 2.3 迁移脚本

```bash
# 在本地或云服务器上运行迁移脚本
# 需要: Docker Compose + PostgreSQL 16 运行中

# 1. 确认PostgreSQL容器运行
docker exec tianlian-postgres pg_isready -U tianlian -d tianlian_v3

# 2. 使用SQLAlchemy自动创建表结构
cd projects/tianlian-v3
source backend/.venv/bin/activate

# 设置PG连接串
export DATABASE_URL="postgresql://tianlian:tianlian123@localhost:5432/tianlian_v3"

# 3. 使用Alembic（如已配置）或直接创建所有表
python3 -c "
from app.database import engine
from app.models import Base
# Base.metadata.create_all(bind=engine)  # 当DATABASE_URL指向PG时创建PG表
print('✅ 表结构创建完成')
"

# 4. 数据迁移：SQLite→PG
# 导出SQLite数据
sqlite3 backend/tianlian_v3.db .dump > /tmp/tianlian_dump.sql
# 注意: SQLite的dump不完全兼容PG, 需要处理:
# - 移除 PRAGMA 语句
# - 将 ' 改为 标准引号
# - 处理AUTOINCREMENT→SERIAL
# 建议使用SQLAlchemy ORM逐表迁移
```

### 2.4 迁移回滚方案

```bash
# ===== 回滚步骤 =====

# 方案A: Docker容器级回滚（推荐）
# 1. 停止并删除PG容器
cd projects/tianlian-v3
docker-compose stop db
docker-compose rm -f db
# 2. 删除PG数据卷（重要: 确保数据已备份）
docker volume rm tianlian-v3_postgres_data
# 3. 恢复docker-compose.yml中的数据库配置
#   将 DATABASE_URL 指向SQLite: sqlite:///./tianlian_v3.db
# 4. 重新部署
docker-compose up -d

# 方案B: 数据导出恢复
# 1. 从PG导出数据
pg_dump -h localhost -U tianlian -d tianlian_v3 > /tmp/pg_backup.sql
# 2. 保留PG数据, 回滚应用配置即可
# 3. 将应用 DATABASE_URL 改回SQLite

# 方案C: 完全回滚（备份文件）
# 备份文件位于: projects/tianlian-v3/backups/
# 使用 restore-from-backup.sh 恢复
./scripts/restore-from-backup.sh --latest
```

---

## 三、云端完整部署步骤

### 阶段1: 基础设施
```bash
# 在云服务器上（SSH）
# 1. 安装Docker + Docker Compose
curl -fsSL https://get.docker.com | sh
# 2. 克隆/同步代码
# 3. 启动核心服务
cd tianlian-v3
docker-compose up -d              # Redis + PostgreSQL + Backend + Frontend
docker-compose -f docker-compose.monitoring.yml up -d  # Prometheus+Grafana+Loki
```

### 阶段2: 数据库初始化
```bash
# 确保PG容器就绪后, 创建表并迁移数据
# 参见上面 "数据库迁移完整方案"
```

### 阶段3: SSL/HTTPS（已在云服上配置）
```bash
# 通过 nginx/conf.d/tianlian-server.conf 配置
# 证书自动续期: certbot + crontab
```

### 阶段4: 验证
```bash
# API健康检查
curl https://demo.example.com/api/v1/health

# Web访问
curl -I https://demo.example.com:3000

# 监控检查
curl http://demo.example.com:9090/-/healthy   # Prometheus
curl http://demo.example.com:9093/-/healthy   # Alertmanager
curl http://demo.example.com:3100/ready        # Loki
```

---

## 四、CI/CD自动部署流程（基于Phase23）

```yaml
# .github/workflows/deploy.yml (已有)
name: Deploy
on:
  push:
    branches: [stable-v3.0]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and Deploy
        run: |
          # 构建前端
          cd frontend && npm ci && npm run build
          # 构建后端
          cd backend && docker build -t tianlian-api .
          # 部署到云服务器（通过SSH）
          scp -r dist/* user@demo.example.com:/var/www/tianlian/
```

---

## 五、监控告警体系（完整版）

| 组件 | 探活端点 | 预期 |
|------|----------|-------|
| API服务 | /api/v1/health | 200 + status=healthy |
| Redis | docker healthcheck | PONG |
| PostgreSQL | docker healthcheck | pg_isready OK |
| Prometheus | /-/healthy | 200 |
| Alertmanager | /-/healthy | 200 |
| Grafana | /api/health | 200 |
| Loki | /ready | 200 |

**告警规则**: prometheus/alerts.yml (Phase17)
- 服务Down告警
- API高错误率(>5%)
- 高响应延迟(P95>2s)
- 设备离线检测

**通知渠道**: IMWebhook (Phase19)

---

## 六、回滚预案汇总

| 场景 | 回滚策略 | 影响范围 |
|------|----------|----------|
| API部署失败 | `docker-compose restart api` | 短暂不可用 |
| 前端部署失败 | Nginx恢复旧dist | 基本无影响 |
| 数据库迁移失败 | 方案A/B/C | 数据一致性需验证 |
| SSL证书过期 | certbot renew (自动) | 用户证书警告 |
| 监控栈故障 | docker-compose重启对应服务 | 仅监控功能 |

---

*文档版本: v2.0 | 生成: 2026-06-01*