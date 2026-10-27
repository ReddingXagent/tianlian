# 天链V3 数据库迁移指南

## SQLite → PostgreSQL 迁移

### 概述

天链V3 默认使用 **SQLite** 作为数据库。当系统规模扩大、并发量增加或需生产部署时，建议切换到 **PostgreSQL**。

迁移不是原地替换，而是**准备迁移能力** — 代码已支持通过环境变量切换，数据迁移通过脚本完成。

### 数据库差异速览

| 特性 | SQLite | PostgreSQL |
|------|--------|-----------|
| 部署复杂度 | 零配置，单文件 | 需独立安装/容器 |
| 并发写入 | 单写入锁 | 高并发 MVCC |
| 数据类型 | 宽松（类型亲和） | 严格类型检查 |
| 自动递增 | `AUTOINCREMENT` | `SERIAL` / `IDENTITY` |
| BOOLEAN | INTEGER 0/1 | 原生 BOOLEAN |
| JSON | TEXT 存储 | 原生 JSONB 类型 |
| 连接池 | 不需要 | 推荐配置 |
| 适合规模 | 小-中规模 | 中-大规模 |

### 迁移前准备

#### 1. 确认环境

```bash
# 启动 PostgreSQL (Docker)
docker-compose up -d db

# 确认 PostgreSQL 就绪
docker-compose exec db pg_isready -U tianlian
```

#### 2. 安装依赖

```bash
cd backend
pip install psycopg2-binary
```

#### 3. 备份现有数据

```bash
cp backend/tianlian_v3.db backend/tianlian_v3.db.bak.$(date +%Y%m%d)
```

### 执行迁移

#### 方式一：自动化脚本（推荐）

```bash
# 设置 PG 连接信息
export PG_URL="postgresql://tianlian:tianlian123@localhost:5432/tianlian_v3"
export SQLITE_DB="./backend/tianlian_v3.db"

# 执行迁移
./scripts/migrate-to-postgres.sh
```

#### 方式二：Docker Compose 环境

```bash
# 1. 修改 .env.docker 或环境变量
DB_TYPE=postgres
DATABASE_URL=postgresql://tianlian:tianlian123@db:5432/tianlian_v3

# 2. 启动全部服务
docker-compose --profile full up -d

# 3. 在容器内执行迁移
docker-compose exec backend python -c "
from app.core.database import init_db
init_db()
print('Tables created')
"
```

### 切换数据库

#### 本地开发

在 `backend/.env` 中修改：

```env
# SQLite (默认)
DB_TYPE=sqlite

# PostgreSQL
# DB_TYPE=postgres
# DATABASE_URL=postgresql://tianlian:tianlian123@localhost:5432/tianlian_v3
```

#### Docker 环境

在 `.env.docker` 中修改：

```env
DB_TYPE=postgres
DATABASE_URL=postgresql://tianlian:tianlian123@db:5432/tianlian_v3
```

#### 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DB_TYPE` | `sqlite` | 数据库类型: `sqlite` 或 `postgres` |
| `DATABASE_URL` | `sqlite:///...` | SQLite 文件路径（sqlite模式）或 PG 连接串 |
| `DB_POOL_SIZE` | `20` | PG 连接池大小 |
| `DB_MAX_OVERFLOW` | `10` | PG 最大溢出连接数 |
| `DB_POOL_RECYCLE` | `3600` | PG 连接回收时间(秒) |
| `DB_POOL_PRE_PING` | `true` | PG 连接前 ping 检测 |

### 注意事项

#### ⚠️ 类型差异

1. **BOOLEAN 字段**：SQLite 用 `0`/`1` (INTEGER)，PostgreSQL 用 `TRUE`/`FALSE`。迁移脚本自动处理。
2. **DATETIME 字段**：SQLite 无原生日期类型，实际存 TEXT。PostgreSQL 支持 TIMESTAMP。
3. **AUTOINCREMENT**：SQLite `AUTOINCREMENT` → PostgreSQL `SERIAL`。迁移后序列会自动更新。
4. **JSON 字段**：SQLite TEXT 存储 → PostgreSQL 推荐用 JSONB，当前模型保持不变。

#### ⚠️ SQL 兼容性

- SQLite 的 `AUTOINCREMENT` 在 PG 中不存在
- SQLite 的 `IF NOT EXISTS` 语法 PG 也支持但行为有差异
- LIKE 操作符：SQLite 默认不区分大小写，PG 区分。用 `ILIKE` 代替。
- SQLite `||` 字符串拼接在 PG 中也可用
- SQLite 独有函数（如 `hex()`, `typeof()`）PG 中不支持

#### ⚠️ 性能建议

- 为高频查询字段添加索引：`CREATE INDEX ON table (column)`
- 使用 `EXPLAIN ANALYZE` 分析慢查询
- 考虑配置连接池参数匹配实际负载

### 回滚方法

```bash
# 1. 修改 .env
DB_TYPE=sqlite

# 2. 停止并重启
docker-compose down
docker-compose up -d

# 3. 恢复备份（如需要）
cp backend/tianlian_v3.db.bak.YYYYMMDD backend/tianlian_v3.db

# 4. (可选) 清除 PostgreSQL volume
docker volume rm tianlian-postgres-data
```

### 验证清单

- [ ] PostgreSQL 服务正常运行
- [ ] 所有表已创建（`\dt` 查看）
- [ ] 数据行数与 SQLite 一致
- [ ] 前后端 API 正常响应
- [ ] 登录认证正常
- [ ] CRUD 操作正常
- [ ] 定时任务/后台任务正常

### 目录结构

```
tianlian-v3/
├── backend/
│   ├── app/core/
│   │   ├── database.py        ← 数据库统一入口（支持切换）
│   │   └── database_pg.py     ← PostgreSQL 独立配置
│   └── requirements.txt       ← 含 psycopg2-binary
├── scripts/
│   └── migrate-to-postgres.sh ← 迁移脚本
├── docs/
│   └── database-migration.md  ← 本文档
├── .env.docker                ← Docker 环境变量
├── .env.example               ← 环境变量示例
└── docker-compose.yml         ← 含 PostgreSQL 服务定义
```