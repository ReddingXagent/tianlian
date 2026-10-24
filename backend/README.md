# 天链 V3 后端服务

FastAPI + SQLAlchemy + Pydantic v2 构建的光储充一体化运维后端，提供设备管理、遥测采集、告警诊断、工单调度、运营结算、虚拟电厂等全业务 API。

---

## 环境要求

| 项 | 要求 | 说明 |
|----|------|------|
| Python | 3.9+ | `pyproject.toml` 目标 `py39`；项目内置 `venv` 实测 3.9.6，`.venv` 实测 3.11，均可用 |
| 数据库 | SQLite（默认）/ PostgreSQL（生产） | 通过 `DB_TYPE` 切换 |
| Redis | 可选 | 缓存 / Celery broker / Pod 矩阵路由跨 Pod 查询 |
| MQTT Broker | 可选 | 设备遥测接入（边缘网关上行） |

> 依赖清单见 `requirements.txt`（FastAPI≥0.109、SQLAlchemy≥2.0、Pydantic≥2.5、Celery≥5.3、Alembic≥1.13、pytest≥8.0 等）。

---

## 环境搭建

```bash
cd backend

# 1. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp ../.env.example .env      # 或从项目根 .env.example 复制
# 编辑 .env，至少修改 SECRET_KEY（生产必改）
```

### 关键环境变量（`.env`）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DB_TYPE` | `sqlite` | `sqlite` 或 `postgres` |
| `DATABASE_URL` | `sqlite:///./tianlian_v3.db` | 生产用 `postgresql://...` |
| `SECRET_KEY` | dev 默认值 | **生产必须替换**为强随机串 |
| `HOST` / `PORT` | `0.0.0.0` / `8080` | 本地开发建议 `PORT=8000`（对齐前端 vite proxy） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT 有效期 24 小时 |
| `ALERT_WEBHOOK_SECRET` | 空 | Alertmanager webhook 认证密钥，未配置则拒绝所有回调（详见 `docs/DEPLOY.md`） |
| `CORS_ORIGINS` | — | 跨域白名单，逗号分隔 |
| `REDIS_URL` | `redis://localhost:6379/0` | 可选 |

完整字段见 `app/core/config.py` 与项目根 `.env.example`。

---

## 本地运行

```bash
# 方式 A（推荐，对齐前端 proxy 8000 端口）—— 在项目根执行
make backend

# 方式 B（手动，指定 8000 端口）
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 方式 C（用 config.py 默认 8080，需同步调整前端 vite proxy target）
uvicorn app.main:app --reload
```

> ⚠️ **端口一致性**：前端 `vite.config.ts` 的 dev proxy 固定指向 `http://localhost:8000`。本地起后端**必须用 8000**（`make backend` 已固化），否则前端请求代理失败。

启动后访问：
- Swagger UI：http://localhost:8000/api/docs
- ReDoc：http://localhost:8000/api/redoc
- OpenAPI JSON：http://localhost:8000/api/openapi.json
- 健康检查：http://localhost:8000/api/v1/health

---

## 数据库迁移

项目采用 **`create_all` 兜底 + Alembic 受控迁移** 双轨制：

```bash
source venv/bin/activate

# 方式 1：建表兜底（开发常用，按 model 定义创建缺失的表）
python3 -c "from app.core.database import Base, engine; from app.models import *; Base.metadata.create_all(bind=engine)"

# 方式 2：Alembic 版本迁移（生产推荐，记录 schema 变更）
alembic upgrade head
```

迁移脚本位于 `alembic/`。`make db-migrate`（项目根）封装了带备份与验证的迁移流程。

---

## 测试

测试套件位于 `tests/`，使用 pytest + pytest-asyncio，`pytest.ini` 默认开启 **pytest-xdist 4 进程并发**（防止单进程跑全量时内存线性累积导致 OOM）。

```bash
source venv/bin/activate

# 全量测试（4 worker 并发）
venv/bin/python -m pytest tests/

# 单进程调试（关闭 xdist）
venv/bin/python -m pytest tests/ -n 0

# 指定模块
venv/bin/python -m pytest tests/test_auth.py -v

# 带覆盖率
venv/bin/python -m pytest tests/ --cov=app --cov-report=term-missing

# 跳过慢测试（pytest.ini 默认已 -m "not slow"）
venv/bin/python -m pytest tests/ -m "not slow"
```

> 💡 必须用 `venv/bin/python -m pytest` 而非直接 `pytest`：历史项目改名（tianlian-v3 → tianlian-cloud）导致 `.venv/bin/pytest` 的 shebang 失效。`make test` 用系统 `python3 -m pytest`，需系统已装 pytest。

Markers：`slow` / `integration` / `unit`。

---

## 目录结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口（中间件/路由注册/启动事件）
│   ├── api/v1/              # API 路由模块（60+ 业务路由文件）
│   │   ├── __init__.py      # 路由聚合（include_router + 前缀）
│   │   ├── auth.py          # 认证（全局 enforce_auth 强制鉴权）
│   │   ├── operate/         # 运营管理子包（统一 /operate 前缀）
│   │   └── ...
│   ├── core/                # 配置 / 数据库 / 安全 / 缓存 / 限流 / 日志 / Sentry
│   ├── models/              # SQLAlchemy 数据模型
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── services/            # 业务逻辑层
│   ├── gateway/             # IoT 网关模块（modbus/mqtt/rest/registry）
│   ├── parsers/             # 协议解析器（modbus/mqtt/dlt645 等）
│   ├── ws/                  # WebSocket 统一路由与管理器（/ws/v1/）
│   ├── middleware/          # 安全头 / CSRF / 审计 / 请求ID / 请求体限制
│   ├── tasks/               # Celery 异步任务
│   ├── cli/                 # 命令行工具
│   ├── metrics.py           # Prometheus 指标（/metrics）
│   └── utils/               # 工具函数
├── alembic/                 # 数据库迁移版本
├── tests/                   # 测试套件（conftest.py 自动处理 import 与测试库）
├── scripts/                 # 运维/种子脚本（含 seed_mobile_test_user.py 等）
├── requirements.txt
├── pytest.ini
└── pyproject.toml           # black / isort / flake8 / pytest 配置
```

---

## 认证机制

- **全局强制鉴权**：所有 `/api/v1/*` 端点默认要求 Bearer JWT，由 `app/api/v1/auth.py` 的 `enforce_auth` 依赖统一拦截。
- **白名单豁免**：健康检查、扫码报修、遥测上报、Pod 矩阵路由、跨 Pod 查询、Alertmanager 回调、认证公开端点等在 `is_public_path` 内豁免。
- **登录**：`POST /api/v1/auth/login`（`OAuth2PasswordRequestForm`，即 `application/x-www-form-urlencoded`）或 `POST /api/v1/auth/sms/login`（验证码）。

---

## 更多文档

- API 端点清单：`docs/API.md` 或线上 `/api/docs`
- 部署流程：`docs/DEPLOY.md`
- 项目总览：项目根 `README.md`
