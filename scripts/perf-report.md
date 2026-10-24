# 天链V3 性能测试报告

> **生成时间**: 2026-05-18 17:55 CST  
> **项目**: 天链V3 光储充运维系统  
> **版本**: 3.0.0
> **后端**: FastAPI + SQLAlchemy + SQLite (开发环境)  
> **测试工具**: Apache Bench, Python requests, Locust

---

## 目录

1. [环境信息](#1-环境信息)
2. [关键API端点](#2-关键api端点)
3. [数据库索引分析](#3-数据库索引分析)
4. [慢查询分析](#4-慢查询分析)
5. [性能基线数据](#5-性能基线数据)
6. [瓶颈分析](#6-瓶颈分析)
7. [改进建议](#7-改进建议)
8. [运行方式](#8-运行方式)

---

## 1. 环境信息

| 项目 | 值 |
|------|-----|
| 服务器 | 本地开发环境 (macOS arm64) |
| 数据库 | SQLite (tianlian_v3.db, 610KB) |
| 表数量 | 29 |
| 索引数量 | 109 |
| 数据量 | 极低 (多为空表或少量数据) |

---

## 2. 关键API端点

### 核心API路由

| 前缀 | 功能 | 认证 | 方法数 |
|------|------|------|--------|
| `/api/v1/health` | 健康检查 | 否 | GET |
| `/api/v1/auth` | 认证(登录/注册/刷新) | 否/是 | POST |
| `/api/v1/stations` | 站点管理 | 是 | GET/POST/PUT/DELETE |
| `/api/v1/devices` | 设备管理 | 是 | GET/POST/PUT/DELETE |
| `/api/v1/alarms` | 告警管理 | 是 | GET/POST/PUT/DELETE |
| `/api/v1/workorders` | 工单管理 | 是 | GET/POST/PUT/DELETE |
| `/api/v1/stats` | 数据看板 | 否 | GET |
| `/api/v1/knowledge` | 知识库 | 是 | GET/POST/PUT/DELETE |
| `/api/v1/telemetry` | 遥测数据 | 是 | GET/POST |

### 性能测试端点

以下4个端点被选为性能基准测试目标:

| 端点 | 类型 | 说明 | 影响 |
|------|------|------|------|
| `/api/v1/health` | GET | 健康检查, 无DB查询 | 纯CPU/网络 |
| `/api/v1/auth/login` | POST | 认证登录, 无DB查询(dev) | 轻量级 |
| `/api/v1/stations` | GET | 分页查询, 带DB查询 | DB I/O |
| `/api/v1/alarms` | GET | 分页+过滤, 带DB查询+JOIN | DB I/O |

---

## 3. 数据库索引分析

### 3.1 索引覆盖情况

整体索引覆盖率良好，**109个索引覆盖29个表**:

| 表名 | 索引数 | 覆盖情况 |
|------|--------|---------|
| `workorders` | 10 | ✅ 完全覆盖: status, type, station_id, device_id, priority, created_at, creator_id, assignee_id |
| `alarms` | 7 | ✅ 完全覆盖: device_id, station_id, alarm_type, fault_code, rule_id, handler_id, id |
| `devices` | 9 | ✅ 完全覆盖: code(unique), sn(unique), type, station_id, protocol_type, mqtt_client_id, gateway_id |
| `stations` | 5 | ✅ 完全覆盖: code(unique), name, operator_id, team_id |
| `telemetry` | 3 | ✅ 完全覆盖: device_id, timestamp |
| `work_orders` | 3 | ⚠️ 缺少 status 和 create_time 索引 (SCAN查询) |
| `device_data` | 3 | ✅ 完全覆盖: device_id, timestamp |
| `users` | 5 | ✅ 完全覆盖: username(unique), phone, team_id |

### 3.2 潜在问题

**`work_orders`表索引不足**: 该表使用 `id VARCHAR(50) PRIMARY KEY` (非自增整数), 仅有 `assignee_id`, `device_id`, `station_id`, `creator_id` 索引, **缺少 `status` 和 `create_time` 索引**。每次按状态查询+排序都会导致全表扫描(SCAN)。

```sql
-- 以下查询会导致SCAN (无索引)
EXPLAIN QUERY PLAN SELECT * FROM work_orders WHERE status='pending' ORDER BY create_time DESC LIMIT 20;
-- QUERY PLAN: |--SCAN work_orders
--             `--USE TEMP B-TREE FOR ORDER BY
```

**`alarms`表的聚合查询**: GROUP BY status 需要临时B-TREE排序，数据量大时可能成为瓶颈。

```sql
EXPLAIN QUERY PLAN SELECT COUNT(*) FROM alarms GROUP BY status;
-- QUERY PLAN: |--SCAN alarms
--             `--USE TEMP B-TREE FOR GROUP BY
```

---

## 4. 慢查询分析

### 4.1 当前索引优化的查询

这些查询在SQLite开发环境中表现良好（已有索引支持):

| 查询场景 | 查询计划 | 复杂度 |
|----------|---------|--------|
| 按主键查站点 | `SEARCH stations USING INTEGER PRIMARY KEY` | O(1) |
| 按code查站点 | `SEARCH stations USING INDEX ix_stations_code` | O(log n) |
| 按station_id查设备 | `SEARCH devices USING INDEX ix_devices_station_id` | O(log n) |
| 按device_id查告警 | `SEARCH alarms USING INDEX ix_alarms_device_id` | O(log n) |
| 按status查工单 | `SEARCH workorders USING INDEX idx_workorders_status` | O(log n) |
| 按device_id查遥测 | `SEARCH telemetry USING INDEX ix_telemetry_device_id` | O(log n) |
| 按username查用户 | `SEARCH users USING INDEX ix_users_username` | O(log n) |

### 4.2 建议增加的索引

```sql
-- work_orders 表: status + create_time 复合索引
CREATE INDEX ix_work_orders_status_create_time ON work_orders(status, create_time);

-- alarms 表: 支持常见过滤组合
CREATE INDEX ix_alarms_status_level ON alarms(status, level);
```

---

## 5. 性能基线数据

> 注: 由于当前数据库无实际数据, 以下为预期理论基线。
> 实际投产前需在**生产规模数据(万级记录)**下重新测试。

### 5.1 各端点预期延迟 (空表)

| 端点 | 并发10 | 并发50 | 并发100 |
|------|--------|--------|---------|
| `/health` | <1ms | <2ms | <3ms |
| `/auth/login` | <5ms | <10ms | <15ms |
| `/stations` | <3ms | <8ms | <12ms |
| `/alarms` | <5ms | <10ms | <20ms |

### 5.2 各并发级别的QPS预期 (空表, SQLite)

| 并发级别 | 健康检查 | 站点查询 | 告警查询 |
|---------|---------|---------|---------|
| 10 | ~2000 | ~1500 | ~1000 |
| 50 | ~8000 | ~5000 | ~3000 |
| 100 | ~15000 | ~8000 | ~5000 |

### 5.3 限制因素

- **SQLite**: 同一时刻只能有一个写入连接，高并发写入将排队
- **SQLite**: 连接必须使用 `check_same_thread=False`
- **GIL**: Python GIL 限制多线程并发性能

---

## 6. 瓶颈分析

### 6.1 当前架构瓶颈 (排名从高到低)

| 优先级 | 瓶颈 | 影响 | 缓解方案 |
|--------|------|------|---------|
| 🔴 P0 | **SQLite 写入并发限制** | 高并发写入QPS < 100 | 迁移 PostgreSQL |
| 🟠 P1 | **`work_orders`表无status/create_time索引** | 状态筛选+排序全表扫描 | 添加复合索引 |
| 🟠 P1 | **Python GIL** | 多线程下CPU密集操作受限 | 使用多进程uvicorn |
| 🟡 P2 | **无数据库连接池(定时会话)** | 每次请求创建Session | 使用会话池 |
| 🟡 P2 | **ORM N+1 查询** | _serialize_alarm中逐条查device/station | 使用eager loading |
| 🟢 P3 | **告警诊断threading后台线程** | 触发后后台启动线程 | 使用Celery/消息队列 |
| 🟢 P3 | **WebSocket广播同步循环** | _broadcast_wo使用事件循环可能阻塞 | 异步化处理 |

### 6.2 代码级热点

1. **alarms.py `_serialize_alarm`**: 每个告警序列化时额外查询device和station表，批量查询时产生N+1问题
2. **auth.py `login`**: 开发环境的测试账号检查(if username=="admin" and password=="admin123")跳过DB查询，生产环境需真实DB检查
3. **stats.py**: `get_devices_health` 和 `get_station_rank` 直接 `db.query(Device).all()`，无数据时返回mock，需迁移到services层

---

## 7. 改进建议

### 🔥 紧急 (生产部署前)

1. **迁移 PostgreSQL**
   ```python
   # 生产配置使用 PostgreSQL
   DATABASE_URL=postgresql://tianlian:tianlian123@localhost:5432/tianlian_v3
   ```
   - 支持高并发读写
   - 原生连接池支持
   - 更好的并发查询性能

2. **添加 work_orders 表索引**
   ```sql
   CREATE INDEX ix_work_orders_status ON work_orders(status);
   CREATE INDEX ix_work_orders_create_time ON work_orders(create_time);
   ```

### 📌 重要

3. **优化告警序列化 N+1 问题**
   ```python
   # 改为批量预加载
   devices_map = {d.id: d for d in db.query(Device).filter(Device.id.in_([a.device_id for a in alarms])).all()}
   ```

4. **添加Redis缓存层**
   -  （配置中已有REDIS_URL）**
   - 缓存 `alarms/stats/summary` 等聚合查询结果（TTL 60s）
   - 缓存 `stats/*` 仪表盘数据（TTL 30s）

### 💡 建议

5. **启用 uvicorn 多worker模式**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 4
   ```

6. **异步化后台任务**
   - 告警触发AI诊断 → Celery/APScheduler
   - 耗时统计计算 → 异步刷新

7. **添加请求级性能日志**
   ```python
   # middleware
   @app.middleware("http")
   async def perf_logging(request: Request, call_next):
       start = time.time()
       response = await call_next(request)
       duration = time.time() - start
       if duration > 0.5:  # 超过500ms记录慢请求
           logger.warning(f"SLOW: {request.method} {request.url.path} took {duration:.3f}s")
       return response
   ```

---

## 8. 运行方式

### 性能测试 (`perf-test.sh`)

```bash
# 必须先启动后端服务
cd backend
pip install -r requirements.txt
python app/main.py &

# 运行性能测试 (本地默认)
bash scripts/perf-test.sh

# 测试远程服务器
BASE_URL=http://demo.example.com:8080 bash scripts/perf-test.sh
```

### Locust 压力测试

```bash
# 安装 Locust
pip install locust

# Web UI 模式
locust -f scripts/locustfile.py

# 命令行模式 - 50用户 60秒
locust -f scripts/locustfile.py --headless -u 50 -r 5 --run-time 60s

# 100用户 120秒 CSV输出
locust -f scripts/locustfile.py --headless -u 100 -r 10 --run-time 120s --csv=perf-results/locust-report

# 远程服务器
locust -f scripts/locustfile.py --host=http://demo.example.com:8080 --headless -u 100 -r 10 --run-time 60s
```

---

## 附录: 数据库 Schema 概览

| 表名 | 字段数 | 索引数 | 用途 |
|------|--------|--------|------|
| `stations` | 18 | 5 | 站点信息 |
| `devices` | 40+ | 9 | 设备信息 |
| `alarms` | 27 | 7 | 告警记录 |
| `workorders` | 30+ | 10 | 工单(新版) |
| `work_orders` | 14 | 3 | 工单(旧版,不足) |
| `users` | 9 | 5 | 用户 |
| `telemetry` | 60+ | 3 | 遥测数据 |
| `gateways` | 16 | 4 | 网关设备 |
| `ai_diagnosis_records` | 23 | 5 | AI诊断记录 |
| **合计** | **29表** | **109** | |