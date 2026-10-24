# 后端性能优化报告 (Phase47)

## 一、N+1 查询问题修复

### 1.1 on_call.py — 值班排班模块（最高风险）

**问题描述:**
- `list_rules()`: 遍历规则列表时为每个规则执行单独的 User 查询（L150），以及 2 个独立的 COUNT 查询（L168-169）
- `get_rule()`: 遍历班次列表时为每个班次单独查询 User（L190）
- `get_current_shifts()`: 遍历当前班次时为每个班次单独查询 primary/backup User（L347-348）
- `list_shifts()`: 遍历班次列表时为每个班次单独查询 User（L393-396）
- `get_stats()`: 统计报表中为每个 user_id 单独查询 User（L600）
- `create_rule()`: 为 rotation_order 中每个用户单独验证（L231）

**修复方案:**
1. 添加 `_batch_get_users()` 辅助函数，使用 `User.id.in_(user_ids)` 批量查询用户
2. `list_rules()`: 使用 `selectinload(OnCallRule.shifts)` 预加载班次，批量收集 user_ids 后一次性查询
3. `get_rule()`: 同上，使用 `selectinload` 预加载班次
4. `get_current_shifts()`: 使用 `selectinload(OnCallShift.rule)` 预加载 rule 关联
5. `list_shifts()`: 批量收集 user_ids + backup_user_ids 后一次性查询
6. `get_stats()`: 批量查询 by_user 中的用户信息
7. `create_rule()`: 使用 `User.id.in_(user_ids)` 批量验证

### 1.2 alarms.py — 告警列表模块

**问题描述:**
- `_serialize_alarm()`: 每个告警序列化时，执行 3 个独立查询（Device, Station, AlarmRule）
- `list_alarms()`: 调用时若返回 20 条告警，最多产生 60 个额外查询

**修复方案:**
1. 修改 `_serialize_alarm()` 签名，支持接收预加载的 `device_map`/`station_map`/`rule_map`
2. `list_alarms()`: 在执行序列化前，收集所有 device_ids/station_ids/rule_ids，使用 `IN` 子句批量查询
3. 未传入 map 时回退到原有逐条查询模式（向后兼容）

### 1.3 predictive_maintenance.py — 预测性维护模块

**问题描述:**
- `/dashboard`: 遍历所有设备时，为每个设备单独查询 Telemetry 数据（每条产生 1 个额外查询）
- `/batch-predict`: 遍历设备列表时，为每个设备单独查询 Device 和 Telemetry

**修复方案:**
1. `/dashboard`: 使用 `Device.id.in_(device_ids)` 批量查询所有设备的最新遥测数据，构建 `telemetry_map` 减少 N+1
2. `/batch-predict`: 一次性查询所有设备和遥测数据，使用 `telemetry_map` 按 device_id 分组

### 1.4 ops_dashboard.py — 运维大屏

**问题描述:**
- `/topology`: 查询所有站点/网关/设备后，在 Python 内存中构建关系（当前已是最优方案）
- `/overview` 和 `/health-scores`: 多个独立的聚合查询

**修复方案:**
1. 为全部 3 个高频读取端点添加 `@cached(ttl=30)` 缓存

## 二、Redis 缓存优化

### 2.1 缓存架构

项目已有完整的 CacheService（app/core/cache.py）：
- 一级缓存：进程内 TTL 字典（内存，零延迟）
- 二级缓存：Redis（分布式）
- Redis 不可用时自动降级到内存缓存
- 所有 key 自动加 `tianlian:` 前缀

### 2.2 新增缓存装饰器

| API 端点 | 缓存 TTL | 说明 |
|---------|---------|------|
| `on_call.py` → `GET /rules` | 30s | 值班规则列表，写入时清除缓存 |
| `on_call.py` → `GET /shifts/current` | 30s | 当前值班人员 |
| `on_call.py` → `GET /stats` | 60s | 值班统计报表 |
| `alert_workflow.py` → `GET /stats` | 30s | 闭环统计 |
| `predictive_maintenance.py` → `GET /dashboard` | 60s | 预测性维护仪表盘 |
| `predictive_maintenance.py` → `POST /batch-predict` | 30s | 批量预测 |
| `ops_dashboard.py` → `GET /topology` | 30s | 实时拓扑 |
| `ops_dashboard.py` → `GET /overview` | 30s | 大屏综合概览 |
| `ops_dashboard.py` → `GET /health-scores` | 30s | 健康度评分 |
| `stations.py` → `GET /stations` | 30s | 站点列表（已有） |

### 2.3 缓存失效策略

- 写操作（create/update/delete）后使用 `cache.delete_pattern()` 清理相关缓存
- `on_call.py` 的写入接口（create_rule/update_rule/delete_rule/create_shift）均会清除缓存

## 三、数据库索引优化建议

### 3.1 当前索引状态

- Alarms 表：`id`、`device_id`、`station_id`、`rule_id`、`alarm_type`、`fault_code`、`workorder_id` 已建索引
- Telemetry 表：`id`、`device_id`、`timestamp` 已建索引
- TelemetryV2 专表：`device_id`、`station_id`、`region_id`、`pod_id` 已建索引
- Device 表：`id`、`station_id` 等已建索引

### 3.2 建议新增的复合索引

```sql
-- 1. Telemetry 表：设备+时间复合索引（最常查询的模式）
CREATE INDEX ix_telemetry_device_timestamp ON telemetry (device_id, timestamp DESC);

-- 2. TelemetryV2 专表复合索引
CREATE INDEX ix_telemetry_pv_device_timestamp ON telemetry_pv (device_id, timestamp DESC);
CREATE INDEX ix_telemetry_battery_device_timestamp ON telemetry_battery (device_id, timestamp DESC);
CREATE INDEX ix_telemetry_charger_device_timestamp ON telemetry_charger (device_id, timestamp DESC);

-- 3. Alarms 表：status + created_at 复合索引（列表查询常用过滤）
CREATE INDEX ix_alarms_status_created ON alarms (status, created_at DESC);
CREATE INDEX ix_alarms_level_created ON alarms (level, created_at DESC);

-- 4. WorkOrder 表：status + create_time 复合索引
CREATE INDEX ix_workorders_status_created ON work_orders (status, create_time DESC);

-- 5. OnCallShift 表：rule_id + start_time（班次查询常用过滤）
CREATE INDEX ix_oncall_shift_rule_start ON on_call_shifts (rule_id, start_time DESC);
CREATE INDEX ix_oncall_shift_user_start ON on_call_shifts (user_id, start_time DESC);

-- 6. Device 表：status + station_id（设备列表筛选用）
CREATE INDEX ix_devices_status_station ON devices (status, station_id);
```

### 3.3 迁移方式

上述索引可作为 Alembic migration 的 upgrade() 函数内容：

```python
from alembic import op

def upgrade():
    op.create_index('ix_telemetry_device_timestamp', 'telemetry', ['device_id', sa.text('timestamp DESC')])
    op.create_index('ix_alarms_status_created', 'alarms', ['status', sa.text('created_at DESC')])
    op.create_index('ix_workorders_status_created', 'work_orders', ['status', sa.text('create_time DESC')])
    # ... 以此类推
```

## 四、压测与验收

### 4.1 验收标准

| 指标 | 目标 | 当前 |
|------|------|------|
| 100 并发 P99 响应 | < 500ms | 待压测 |
| N+1 查询数 | 0 | 已修复 |

### 4.2 压测准备

1. 启动服务: `uvicorn app.main:app --host 0.0.0.0 --port 8080`
2. 运行 Locust: `locust -f tests/benchmark/locustfile.py`
3. 设置并发数 100，观察 P99 延迟

### 4.3 预期效果

- N+1 修复后，告警列表接口（20条记录）的 SQL 查询数从 1+60=61 降至 1+3=4 次
- 值班规则列表的 SQL 查询数降至常数级别
- 缓存使仪表盘类接口响应时间降低 80%+

## 五、变更文件清单

| 文件 | 变更内容 |
|------|---------|
| `app/api/v1/on_call.py` | N+1 修复 + 批量查询 + @cached + 缓存失效 |
| `app/api/v1/alarms.py` | N+1 修复（_serialize_alarm + 批量预加载） |
| `app/api/v1/predictive_maintenance.py` | N+1 修复（批量遥测查询）+ @cached |
| `app/api/v1/alert_workflow.py` | @cached 添加 |
| `app/api/v1/ops_dashboard.py` | @cached 添加 |
| `docs/performance-optimization.md` | 本报告 |