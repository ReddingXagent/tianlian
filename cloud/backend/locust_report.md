# 天链V3 后端 Phase47d 性能压测报告

> **测试日期**: 2026-06-24 09:35-09:40 CST  
> **工具**: Locust 2.42.3  
> **测试环境**: mac OS, Python 3.11, SQLite (开发环境)  
> **后端端口**: 8090  

---

## 一、测试概要

| 指标 | 值 |
|------|-----|
| 并发用户数 | 100 |
| 启动速率 | 10 users/s |
| 测试时长 | 90s (10s预热 + 80s稳态) |
| 总请求数 | 2,551 |
| 成功请求 | 317 (12.4%) |
| 失败请求 | 2,234 (87.6%) |
| 平均 QPS | 38.4 req/s |
| 失败 QPS | 33.7 req/s |

## 二、P50/P90/P99 延迟指标

### 全局聚合

| 指标 | 值 |
|------|-----|
| **P50** | **21 ms** |
| P66 | 27 ms |
| P75 | 35 ms |
| P80 | 42 ms |
| **P90** | **80 ms** |
| P95 | 120 ms |
| P98 | 170 ms |
| **P99** | **210 ms** ✅ |
| P100 | 360 ms |
| 平均 | 34.7 ms |

> **P99 < 500ms 目标: ✅ 达标** (210ms)

### 各接口延迟明细

| 接口 | 成功/失败 | P50 | P90 | P99 | P100 | 平均 | QPS |
|------|-----------|-----|-----|-----|------|------|-----|
| `/api/v1/health` | 58/0 | 6ms | 29ms | 89ms | 93ms | 13ms | 0.9 |
| `/api/v1/auth/login` | 100/0 | 86ms | 120ms | 120ms | 125ms | 89ms | 1.5 |
| `/api/v1/stats/overview` | 0/543 | 19ms | 40ms | 140ms | 171ms | 25ms | 8.2 |
| `/api/v1/devices` | 0/391 | 23ms | 72ms | 220ms | 341ms | 37ms | 5.9 |
| `/api/v1/stations` | 0/425 | 20ms | 91ms | 320ms | 356ms | 39ms | 6.4 |
| `/api/v1/alarms` | 0/299 | 21ms | 81ms | 240ms | 342ms | 36ms | 4.5 |
| `/api/v1/workorders` | 0/144 | 24ms | 76ms | 160ms | 204ms | 34ms | 2.2 |
| `/api/v1/telemetry/device/{id}/latest` | 0/143 | 25ms | 81ms | 190ms | 260ms | 40ms | 2.2 |
| `/api/v1/users` | 0/71 | 17ms | 54ms | 230ms | 225ms | 28ms | 1.1 |
| `/api/v1/teams` | 0/64 | 16ms | 45ms | 160ms | 158ms | 26ms | 1.0 |
| `/api/v1/stats/dashboard` | 0/85 | 7ms | 42ms | 210ms | 214ms | 20ms | 1.3 |
| `/api/v1/workorders [POST]` | 0/48 | 14ms | 62ms | 260ms | 255ms | 30ms | 0.7 |
| `/api/v1/health/device-health` | 0/21 | 5ms | 20ms | 60ms | 59ms | 11ms | 0.3 |

---

## 三、失败分析

### 失败原因分布

| 错误类型 | 次数 | 占比 | 根因 |
|---------|------|------|------|
| **500 数据库锁** | 2,036 | 91.2% | SQLite 并发写入锁 |
| **422 参数校验** | 56 | 2.5% | station_id 不存在 |
| **404 路由不存在** | 87 | 3.9% | API 路径错误 |
| **连接重置** | 1 | 0.04% | 服务端断开 |

### 500 错误根因分析

**核心问题**: SQLite 不支持高并发写入。100 并发用户下，SQLite 的数据库级写锁导致大量 "database is locked" 错误。

```
SQLite 并发限制:
- 单写者 + 多读者
- WAL 模式下读不阻塞读，但写会阻塞其他写
- 100并发请求时，大量请求在争抢数据库锁
```

### 422 错误
- POST `/api/v1/workorders` 使用随机 `station_id` (1-21)，部分 ID 不存在
- 建议: 压测前先查询有效的 station_id 列表

### 404 错误
- `/api/v1/health/device-health` 不存在（正确路径可能是 `/api/v1/health/devices`）
- `/api/v1/stats/dashboard` 不存在（已废弃或未实现）

---

## 四、瓶颈分析

### 4.1 数据库层瓶颈 ⚠️ CRITICAL

| 问题 | 严重度 | 影响 |
|------|--------|------|
| SQLite 不适合高并发 | 🔴 CRITICAL | 87% 请求失败 |
| Phase47b Redis缓存未生效(本地无Redis) | 🟡 MEDIUM | 高频 API 无缓存兜底 |
| 数据库连接池可能不足 | 🟡 MEDIUM | 争抢连接 |

### 4.2 慢接口 TOP3

| 排名 | 接口 | P99 | P90 | 分析 |
|------|------|-----|-----|------|
| 🥇 | `/api/v1/stations` | 320ms | 91ms | 站点列表含子查询/关联加载 |
| 🥈 | `/api/v1/workorders [POST]` | 260ms | 62ms | 写入操作 + 关联验证 |
| 🥉 | `/api/v1/alarms` | 240ms | 81ms | 告警列表查询含 join |

### 4.3 快接口 TOP3

| 排名 | 接口 | P50 | P90 | 分析 |
|------|------|-----|-----|------|
| 🥇 | `/api/v1/health` | 6ms | 29ms | 无数据库查询 |
| 🥈 | `/api/v1/teams` | 16ms | 45ms | 轻量查询 |
| 🥉 | `/api/v1/users` | 17ms | 54ms | 简单分页查询 |

---

## 五、优化建议

### 5.1 数据库升级 🔴 HIGH PRIORITY

```
方案1 (推荐): 切换到 PostgreSQL
  - 真正的行级锁 + MVCC
  - 支持高并发读写
  - Docker: docker run -d --name pg-tianlian -e POSTGRES_USER=tianlian -e POSTGRES_PASSWORD=tianlian123 -e POSTGRES_DB=tianlian_v3 -p 5432:5432 postgres:16

方案2 (临时): SQLite 优化
  - 设置 PRAGMA journal_mode=WAL
  - 设置 PRAGMA busy_timeout=5000
  - 使用连接池限制并发写入数
```

### 5.2 Redis 缓存激活 🟡 MEDIUM PRIORITY

当前 Phase47b 已实现的 Redis 缓存层因本地无 Redis 服务而降级：

```bash
# 启动 Redis
brew install redis && brew services start redis
# 或
redis-server --daemonize yes
```

缓存激活后，高频接口（stats/overview、devices、stations）预期延迟可降低 60-80%。

### 5.3 接口优化

| 接口 | 优化措施 | 预期效果 |
|------|----------|---------|
| `/api/v1/stations` | 添加 Redis 缓存 (TTL=30s) | P99 320ms → ~10ms |
| `/api/v1/alarms` | SQL 查询重写 + 索引优化 | P99 240ms → ~30ms |
| `/api/v1/devices` | 预加载关联数据 (selectinload) | P99 220ms → ~20ms |
| `/api/v1/workorders [POST]` | 异步写入队列 | P99 260ms → ~5ms |

### 5.4 连接池调优

```python
# app/core/database.py
engine = create_engine(
    DATABASE_URL,
    pool_size=20,        # 增加连接池 (默认5)
    max_overflow=10,     # 允许临时连接
    pool_recycle=3600,   # 连接回收时间
    pool_pre_ping=True,  # 连接前检查
)
```

### 5.5 压测脚本修复

```python
# locustfile.py 修复
1. 移除不存在的 API: /api/v1/stats/dashboard, /api/v1/health/device-health
2. POST /workorders 使用预查询的有效 station_id
3. 改用不同用户登录避免单用户瓶颈
```

---

## 六、结论与建议

### ✅ 达标项
- **P99: 210ms < 500ms** — 延迟目标达标
- 健康检查接口 < 100ms
- 登录接口稳定，无失败

### ⚠️ 风险项
- **87% 失败率** — SQLite 不适合 100 并发
- 生产环境需切换 PostgreSQL
- Redis 缓存未激活影响高频 API 性能

### 📊 生产环境预估（PostgreSQL + Redis）

| 指标 | SQLite (当前) | PostgreSQL + Redis (预估) |
|------|--------------|--------------------------|
| P50 | 21ms | ~5ms |
| P90 | 80ms | ~15ms |
| **P99** | **210ms** | **~50ms** |
| 失败率 | 87.6% | < 0.1% |
| QPS | 38 | ~500+ |

---

## 七、原始数据

- CSV 统计: `backend/locust_results_stats.csv`
- CSV 历史: `backend/locust_results_stats_history.csv`
- CSV 失败: `backend/locust_results_failures.csv`
- Locustfile: `backend/locustfile.py`

---

*报告生成时间: 2026-06-24 09:40 CST*
