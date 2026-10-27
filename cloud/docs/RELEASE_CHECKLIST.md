# 天链V3 上线 Checklist — Phase 50c 最终验收

> 生成时间: 2026-06-24 18:21 CST  
> 版本: 1.0.0  
> 状态: ✅ 通过 / ⚠️ 注意 / ❌ 待修复

---

## 1. Docker 容器化部署配置

| 检查项 | 状态 | 详情 |
|--------|------|------|
| `docker-compose.yml` | ✅ | 完整编排：PostgreSQL 16、Redis 7、Backend (FastAPI)、Frontend (Nginx)、Celery Worker |
| `docker-compose.monitoring.yml` | ✅ | 独立监控栈：Prometheus、Alertmanager、Grafana、Loki、Promtail |
| `backend/Dockerfile` | ✅ | Python 3.11-slim，非 root 用户 (appuser)，4 workers uvicorn |
| `frontend/Dockerfile` | ✅ | 多阶段构建 (node:20-alpine → nginx:alpine)，产物仅 10s 构建 |
| `edge-gateway/Dockerfile` | ✅ | Python 3.11-slim，暴露 8080 (管理) + 9000 (OCPP WebSocket) |
| `.dockerignore` | ✅ | 排除 `__pycache__`、`*.db`、`venv`、`node_modules` 等 |
| 健康检查 | ✅ | db (pg_isready)、redis (redis-cli ping)、backend (/api/v1/health)、frontend (wget /) |
| 资源限制 | ✅ | backend 1G、db 512M、redis 384M、frontend 128M、worker 512M |
| 网络隔离 | ✅ | tianlian-net (bridge, 172.28.0.0/16) + monitoring-network (独立) |
| 持久化卷 | ✅ | postgres-data、redis-data、uploads-data、+ 监控卷 (prometheus/alertmanager/grafana/loki) |
| 端口绑定 | ✅ | db/redis/backend 仅绑定 127.0.0.1，frontend 绑定 80/443 |

**⚠ 建议：**
- `docker-compose.yml` 依赖 `docker/.env` 但目录下无 `docker/.env`；需确认部署时 `.env.prod` 或 `.env.docker` 会被复制到位
- `frontend` Dockerfile 引用了 `nginx.conf`（存在），但 docker-compose 中 frontend 直接暴露 80/443，实际生产应通过 Nginx 反向代理统一入口

---

## 2. SSL / HTTPS 配置

| 检查项 | 状态 | 详情 |
|--------|------|------|
| `nginx.ssl.conf` | ✅ | Let's Encrypt 完整配置：HTTP→HTTPS 301、TLS 1.2/1.3、OCSP Stapling、HSTS preload |
| `nginx.prod.conf`（统一入口） | ✅ | HTTP/2、速率限制 (api 30r/s, login 5r/m)、安全头、Gzip/Brotli、静态缓存策略 |
| `scripts/ssl-setup.sh` | ✅ | certbot 证书申请脚本，支持 staging 测试和多域名 |
| `scripts/ssl-auto-renew.sh` | ✅ | 自动续期守护：提前 30 天续期，cron 安装 `0 2,14 * * *`，IM webhook 通知，续后重载 Nginx |
| `deploy/certbot-setup.sh` | ✅ | 独立 certbot 部署辅助脚本 |
| `scripts/ssl-selfsign.sh` | ✅ | 自签证书脚本（内网/测试用） |
| 安全头 (HSTS/CSP/X-Frame/etc) | ✅ | 统一入口全面配置，前端 Nginx 也配置了基本安全头 |

**⚠ 建议：**
- `nginx.prod.conf` 硬编码 `ssl_certificate /etc/letsencrypt/live/tianlian.example.com/`，需在部署时将 `tianlian.example.com` 替换为实际域名；`nginx.ssl.conf` 使用 `${DOMAIN}` 变量更灵活
- 两套 Nginx 配置存在功能重叠，建议选一套作为标准，另一套归档

---

## 3. 备份策略

| 检查项 | 状态 | 详情 |
|--------|------|------|
| `scripts/auto-backup.sh` | ✅ | 完整备份方案：数据库 dump、配置文件备份、上传 NAS (192.168.1.100)、保留 7 天、完整性验证 |
| `scripts/backup-db.sh` | ✅ | 独立数据库备份脚本 |
| `scripts/restore-from-backup.sh` | ✅ | 从备份恢复脚本 |
| `scripts/backup-report.sh` | ✅ | 备份报告生成 |
| `deploy.sh` 内置备份 | ✅ | 部署前自动备份旧版本，保留最近 3 个备份，失败自动回滚 |
| `Makefile backup-db` | ✅ | `make backup-db` 入口 |

**⚠ 建议：**
- `auto-backup.sh` 依赖 `NAS_PASSWORD` 环境变量，需在部署环境设置
- 建议配置 cron：`0 2 * * * bash /opt/tianlian-v3/scripts/auto-backup.sh`
- Docker 环境 PostgreSQL 需要 `pg_dump` 而非 sqlite `.dump`，脚本需确认兼容

---

## 4. 监控告警配置

| 检查项 | 状态 | 详情 |
|--------|------|------|
| Prometheus | ✅ | 抓取间隔 15s，采集 backend /metrics，30 天保留，启用 lifecycle API |
| Alertmanager | ✅ | 按 severity 路由：critical (1h 重复) / warning (2h)，webhook → 后端 `/api/v1/alert-webhook` |
| Grafana | ✅ | 预配 dashboard (tianlian-overview + system-overview)、Loki 日志数据源、禁止匿名访问、时钟/饼图插件 |
| Loki + Promtail | ✅ | 日志聚合 2.9.6，采集 /var/log + Docker container logs |
| `alertmanager/alertmanager.yml` | ✅ | 分组 (alertname/severity/component)，IM critical/warning 通道 |
| `prometheus/prometheus.yml` | ✅ | 采集 backend host.docker.internal:8000 + 自监控 |
| `prometheus/alerts.yml` | ✅ | 告警规则文件已配置 |
| `scripts/health-check.sh` | ✅ | 全面健康检查：系统资源、API 健康、Nginx、数据库、磁盘 |
| `scripts/monitor.sh` | ✅ | 性能监控：CPU/内存/磁盘阈值告警 + 日志记录 |
| `scripts/start-monitoring.sh` | ✅ | 一键启动监控栈 |
| `scripts/log-viewer.sh` | ✅ | 日志查看工具 |

**⚠ 建议：**
- Alertmanager webhook URL 指向 `host.docker.internal:8000`，仅在 Docker Desktop (Mac/Windows) 有效；Linux 服务器需改用 `tianlian-net` 网络内的 `backend:8000`
- Prometheus targets 也用了 `host.docker.internal:8000`，需确认实际部署环境兼容
- 建议在 Grafana 中配置告警通知渠道（IM/Slack/邮件）

---

## 5. CI/CD 及自动化部署

| 检查项 | 状态 | 详情 |
|--------|------|------|
| `.github/workflows/ci-cd.yml` | ✅ | 完整 CI/CD：前端 Lint+TypeCheck+Vitest+Build、后端 Flake8+Pytest、Docker 构建+推送、SSH 部署+健康检查 |
| `.github/workflows/deploy.yml` | ✅ | 独立部署 workflow |
| `.github/workflows/docker-build.yml` | ✅ | 独立 Docker 构建 workflow |
| `.github/workflows/backend-tests.yml` | ✅ | 独立后端测试 workflow |
| `.github/workflows/frontend-tests.yml` | ✅ | 独立前端测试 workflow |
| `.github/workflows/changelog.yml` | ✅ | 自动变更日志 |
| `deploy.sh` | ✅ | 本地一键部署：6 阶段 (健康检查→构建→打包→上传→安装→验证)，自动回滚 |
| `scripts/ci-deploy.sh` | ✅ | CI 环境部署脚本 |
| `scripts/docker-deploy.sh` | ✅ | Docker 环境部署脚本 |
|  `docs/QUICK_DEPLOY_CLOUD.md` | ✅ | 快速部署命令参考 |
| `Makefile` | ✅ | 统一命令入口：dev/build/backend/deploy/test/db-migrate/check/lint/changelog |

---

## 6. 环境配置

| 检查项 | 状态 | 详情 |
|--------|------|------|
| `.env.example` | ✅ | 完整配置模板，含数据库切换指南 (SQLite vs PostgreSQL) |
| `.env.prod` | ✅ | 生产环境配置 |
| `.env.dev` | ✅ | 开发环境配置 |
| `.env.docker` | ✅ | Docker 环境配置模板 |
| `backend/.env` | ✅ | 后端本地配置 |
| `frontend/.env` | ✅ | 前端环境变量 (VITE_API_BASE_URL) |
| `frontend/.env.production` | ✅ | 前端生产环境变量 |
| `frontend/.env.test` | ✅ | 前端测试环境变量 |

**❌ 需修复：**
- `.env.prod` 中 `SECRET_KEY=change-me-to-a-random-string-in-production` — 生产部署前必须替换为强密钥
- `.env.prod` 中 `DB_PASSWORD=tianlian123` — 生产部署前必须替换
- `.env.prod` 中 `GRAFANA_ADMIN_PASSWORD=tianlian123` — 生产部署前必须替换
- 所有 `tianlian123` 默认密码均应在上线前更换

---

## 7. 前端 UI 走查

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 构建 | ✅ | `npm run build` 成功 (10.43s)，产出 dist/ 含 assets、index.html、PWA manifest |
| TypeScript 类型检查 | ⚠️ | 存在 18 个 TS 错误（非阻断，均为未导入组件/类型声明缺失/Spread types），构建通过 |
| 页面数量 | ✅ | 55+ 页面模块覆盖完整业务：Dashboard、设备管理、站点、工单、告警、知识库、报告、团队、大屏等 |
| 路由 | ✅ | React Router lazy loading，RouteGuard 权限守卫，PageTransition 动画 |
| UI 框架 | ✅ | Ant Design 5.12 + @ant-design/icons，统一组件体系 |
| 图表 | ✅ | ECharts 6.0 + echarts-for-react 3.0 |
| 3D 可视化 | ✅ | @react-three/fiber + @react-three/drei (数字孪生) |
| 暗黑模式 | ✅ | `dark-mode.css` + ThemeToggle 组件 |
| 国际化 | ✅ | `i18n.ts` + `locales/` 多语言支持 |
| PWA | ✅ | service worker (`sw.js`)、manifest.json、PWA 图标 |
| 错误处理 | ✅ | ErrorBoundary + OfflineNotice + LoadingSpinner + EmptyState + Skeleton |
| WebSocket | ✅ | useWebSocket hook，自动重连 (max 5)、心跳 (30s)，`WS_BASE_URL` 配置化 |
| 虚拟滚动 | ✅ | useVirtualScroll hook + VirtualList 组件 (大数据表格优化) |
| 数据大屏 | ✅ | LargeScreen 独立展示模式 (Phase48)，`/large-screen` 路由 |
| Nginx SPA | ✅ | `try_files $uri $uri/ /index.html`，`/assets/` 1y 缓存 |
| 安全头 | ✅ | X-Frame-Options DENY、X-Content-Type-Options nosniff |

**⚠ 建议修复 (非阻断)：**
- `DeviceConfigPanel.tsx`: 缺少 Input/Divider 导入
- `MaintenancePlanPanel.tsx`: 导入路径 `../../api` 不存在
- `Knowledge/index.tsx`: API 类型声明缺少 search/createCategory 等方法
- `Teams/Roles.tsx`: 类型运算错误
- `EmptyState/index.tsx`: ReactNode → string 类型不匹配

---

## 8. 后端代码质量

| 检查项 | 状态 | 详情 |
|--------|------|------|
| Python 版本 | ✅ | Python 3.11 (slim Docker 镜像) |
| FastAPI 框架 | ✅ | 生产级 ASGI (uvicorn 4 workers) |
| 数据库 | ✅ | SQLAlchemy ORM、支持 SQLite/PostgreSQL 双模式、连接池配置 |
| 认证 | ✅ | JWT (HS256)、1440min 过期、RBAC 权限 |
| Redis 集成 | ✅ | 缓存、限流、Celery 任务队列 |
| WebSocket | ✅ | `/ws/v1/` 标准化端点，支持设备实时通信 |
| Celery | ✅ | 异步任务处理 (4 concurrency)，Flower 监控可选 |
| CORS | ✅ | 可配置允许来源 |
| 文件上传 | ✅ | 10MB 限制、uploads 目录 |
| API 文档 | ✅ | OpenAPI JSON (`docs/openapi.json` 267KB) + 自动生成脚本 |
| 测试 | ✅ | pytest + pytest-asyncio + pytest-cov + httpx-ws |

---

## 9. 安全审计

| 检查项 | 状态 | 详情 |
|--------|------|------|
| API 速率限制 | ✅ | Nginx 层 api 30r/s、login 5r/m |
| WebSocket 安全 | ✅ | 独立 `/ws/` 端点，86400s timeout |
| Metrics 端点保护 | ✅ | `allow 10.0.0.0/8; 172.16.0.0/12; 192.168.0.0/16; deny all` |
| 隐藏文件禁止 | ✅ | Nginx `location ~ /\\.` deny all |
| 数据库密码 | ⚠️ | 默认密码 `tianlian123` 需上线前更换 |
| JWT Secret | ❌ | 默认值 `change-me-to-a-random-string-in-production` — 必须更换 |
| Grafana 密码 | ⚠️ | 默认 `admin/tianlian123` — 需更换 |
| 非 root 运行 | ✅ | backend (appuser:1000)、frontend (nginx user) |
| Health Check 不记录日志 | ✅ | `access_log off` |

---

## 10. 数据库 & 迁移

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 迁移脚本 | ✅ | `scripts/db-migrate.sh` 带备份+索引创建+验证 |
| SQLite→PG 迁移 | ✅ | `scripts/migrate-to-postgres.sh`、`scripts/migrate-to-pg.sh` |
| PG 搭建辅助 | ✅ | `scripts/setup-pg.sh` (支持 --docker) |
| PostgreSQL 健康检查 | ✅ | `pg_isready` 命令 |
| 连接池 | ✅ | pool_size=20, max_overflow=10, recycle=3600, pre_ping=true |

---

## 11. 文档完备性

| 检查项 | 状态 | 详情 |
|--------|------|------|
| README.md | ✅ | 项目主文档 |
| ARCHITECTURE.md | ✅ | 架构设计 |
| DEPLOYMENT.md | ✅ | 部署指南 |
| USER_MANUAL.md | ✅ | 用户手册 |
| ACCESS_GUIDE.md | ✅ | 访问指南 |
| SPEC.md | ✅ | 需求规格 |
| API.md | ✅ | API 文档 |
| CHANGELOG.md | ✅ | 变更日志 |
| OpenAPI | ✅ | openapi.json (267KB) |

---

## 12. 上线前置必做清单 (P0)

> 以下项目在上线前 **必须** 完成，否则有安全风险

- [ ] **1. 更换 SECRET_KEY** — 所有 `.env.prod`、`.env.docker`、`docker-compose.yml` 中的默认值
  - 生成命令: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- [ ] **2. 更换数据库密码** — `DB_PASSWORD` 从 `tianlian123` 改为强密码
- [ ] **3. 更换 Grafana 密码** — `GRAFANA_ADMIN_PASSWORD` 从 `tianlian123` 改为强密码
- [ ] **4. 配置实际域名** — `nginx.prod.conf` 中 `tianlian.example.com` 替换为真实域名
- [ ] **5. 申请 SSL 证书** — 运行 `scripts/ssl-setup.sh` 获取 Let's Encrypt 证书
- [ ] **6. 修复 Alertmanager/Prometheus 网络** — `host.docker.internal` 在 Linux 服务器不可用，改为 `backend:8000`
- [ ] **7. 确认 docker/.env 文件** — 部署前确认环境变量文件路径正确

---

## 13. 上线后验证清单

- [ ] 前端首页可访问 (HTTP 200)
- [ ] API 健康检查 `GET /api/v1/health` 返回 `{"status": "healthy"}`
- [ ] HTTPS 证书有效 (浏览器无警告)
- [ ] WebSocket 连接正常 (`/ws/v1/`)
- [ ] Prometheus targets all UP
- [ ] Grafana dashboard 数据正常
- [ ] Alertmanager webhook 可送达
- [ ] 数据库备份任务正常运行
- [ ] SSL 自动续期 cron 已安装
- [ ] 日志正常写入 (Loki 可查询)

---

## 总结

| 分类 | 通过 | 注意 | 待修复 |
|------|------|------|--------|
| Docker 配置 | 10 | 1 | 0 |
| SSL/HTTPS | 6 | 2 | 0 |
| 备份策略 | 5 | 2 | 0 |
| 监控告警 | 11 | 2 | 0 |
| CI/CD | 10 | 0 | 0 |
| 环境配置 | 7 | 0 | 3 (P0) |
| 前端 UI | 15 | 5 (非阻断) | 0 |
| 后端 | 12 | 0 | 0 |
| 安全 | 4 | 2 | 1 (P0) |
| 数据库 | 5 | 0 | 0 |
| 文档 | 8 | 0 | 0 |
| **合计** | **93** | **14** | **4 (P0)** |

**整体评级：准备就绪** ✅  
完成 P0 修复后即可上线。非阻断问题可在上线后迭代修复。

---

## 长期约定：API 变更同步（2026-07-31 起）

- API 端点/ schema 变更的**唯一交付物 = 刷新 `docs/openapi.json`**（in-process 导出，不跑 generate-openapi.sh 全服模式——见 TOOLS.md 踩坑记录）：
  ```bash
  cd backend && .venv/bin/python -c "import json; from app.main import app; spec=app.openapi(); json.dump(spec, open('/tmp/openapi_new.json','w'), ensure_ascii=False, indent=2); print(len(spec['paths']))"
  # diff 核实纯增量后 cp /tmp/openapi_new.json ../docs/openapi.json
  ```
- 不再维护手工 changelog（`api-changelog.md` 已归档）；重大 API 变更写入对应 feature 文档即可。

---

*Phase 50c Checklist — 天链V3 大圣 @ 2026-06-24*
