# TDengine 累计计数器聚合口径修正方案

> 调研卡: **eedd9431**（仅调研+文档，不改代码逻辑）
> 上游裁决: 卡 **1b312e62** D2（commit 3c5dbe0cb）已裁决"口径一致不改"，本卡为范外深化调研。
> 关联: 卡 **26e833c5**（TDengine 查询 SQL 加固）、卡 **b2a9b126d**（telemetry 批量毒记录隔离）。
> 状态: **未实施 —— 待立独立财务口径工单三处同步改，禁止单点改。**

## 1. 问题陈述

`query_station_stats` / `aggregate_station_hourly` / TDengine 连续聚合流 三处对
`daily_generation`、`daily_charge`、`daily_discharge`、`charger_kwh` 字段统一使用
`SUM()` 聚合。但这些字段是 **modbus 寄存器直读的累计计数器快照**，遥测每行重复携带
当前累计值 → `SUM` 翻 N 倍（N = 窗口内遥测行数）。

## 2. 寄存器语义证据（modbus_schema.py + 协议域知识）

| 字段 | 寄存器 | 描述 | 语义 |
|------|--------|------|------|
| `daily_generation` | 400 | 日发电量 | **日内累计计数器**：自 00:00 起累计 kWh，日内单调递增，零点重置为 0 |
| `daily_charge` | 401 | 日充电量 | 同上（日内累计） |
| `daily_discharge` | 402 | 日放电量 | 同上（日内累计） |
| `total_generation` | 403 | 累计发电量 | 终身累计计数器（参照字段，本方案不涉及） |
| `total_charge/discharge` | 404/405 | 累计充/放电量 | 终身累计（参照，不涉及） |
| `charger_kwh` | telemetry_charger | 充电电量 | **累计电能表**（无独立 daily 变体，疑似终身/会话累计，单调递增） |

**关键**：这些寄存器返回的是 **当前累计快照值**，不是"自上次读取以来的增量"。
遥测按固定周期（如 60s）轮询 → 一个 1h 窗口内 60 行，每行携带同一累计计数器的
递增序列（如 1.0, 1.0, 1.1, ... 5.0 kWh）。

## 3. 为什么 SUM 是错的（数值推演）

日内累计计数器在 1h 窗口内从 a 线性爬升到 b，N 个采样点：

- `SUM` = N × (a+b)/2（对递增序列求和）
- 实际该窗口发电量 = b − a（首末差值）

例：a=1.0, b=5.0, N=60 → SUM ≈ 180 kWh，实际 = 4.0 kWh，**虚高约 45 倍**。
窗口越长 / 采样越密，虚高越严重。

## 4. 三处聚合现状（全部用 SUM，口径一致）

| # | 位置 | 文件:行 | 聚合 |
|---|------|---------|------|
| 1 | `query_station_stats` | `app/services/tdengine_writer.py:447/461/462/474` | `SUM(daily_generation)` / `SUM(daily_charge)` / `SUM(daily_discharge)` / `SUM(charger_kwh)` |
| 2 | `aggregate_station_hourly` | `app/models/pre_aggregation.py:186/201/202/217` | `sql_func.sum(daily_generation)` / `sum(daily_charge)` / `sum(daily_discharge)` / `sum(charger_kwh)` |
| 3 | 连续聚合流 CREATE STREAM | `app/core/tdengine.py:207/224/225/242` | `SUM(daily_generation)` / `SUM(daily_charge)` / `SUM(daily_discharge)` / `SUM(charger_kwh)` |

三处完全一致 → 单改任一处会制造 **TDengine / SQLAlchemy / 连续聚合流 三方口径分裂**，
财务对账更乱。这正是 1b312e62 裁决"不改"的核心理由。

## 5. 调用方核查

- `query_station_stats`：`grep -rn "query_station_stats" app/`（排除定义）**零生产调用方** → 当前是死方法，
  虚高数值未流入任何在线接口，**这是低危而非高危**，也是本方案允许"暂不实施、待工单"的依据。
- 连续聚合流：写入 `station_*_hourly_stats` 物化表，若有报表/驾驶舱读取这些表则会读到虚高值。
- `aggregate_station_hourly`：由预聚合任务调用，结果落 `StationHourlyStats` 表，同样可能被报表读取。

→ 优先级排序：若确认无报表读取 `station_*_hourly_stats` / `StationHourlyStats` 的电量列，则整族为
  "一致错误且无人消费"，可继续挂起；一旦有消费者，必须三处同步修。

## 6. 全局口径修正方案（三处同步改）

累计计数器的正确聚合 = **窗口内净增量 = LAST − FIRST**（首末快照差），而非 SUM。
注意 LAST−FIRST 比 MAX−MIN 更鲁棒：MAX−MIN 在传感器回退/重置时错乱，LAST−FIRST 捕获净变化。

### 6.1 关键陷阱：必须先按设备求差，再跨设备求和

`query_station_stats` 与连续聚合流是**场站级（聚合站内多设备子表）**聚合。在超级表/多设备上
直接 `LAST(x) − FIRST(x)` 是**错的** —— TDengine 的 LAST/FIRST 在超级表上返回全局首末行，
会把 A 设备的末值减去 B 设备的首值。正确写法是**嵌套子查询**：先 `PARTITION BY device_id` 求每设备增量，
再 `SUM` 这些设备增量：

```sql
-- TDengine (query_station_stats + 连续聚合流) 正确口径
SELECT
    SUM(dev_delta) AS pv_generation_kwh
FROM (
    SELECT LAST(daily_generation) - FIRST(daily_generation) AS dev_delta
    FROM telemetry_pv
    WHERE station_id = {station_id} AND ts >= '...' AND ts <= '...'
    PARTITION BY device_id
)
```

### 6.2 SQLAlchemy 侧（pre_aggregation.py，SQLite/PG 便携）

SQLAlchemy 无便携 LAST/FIRST；对单调计数器用 `MAX − MIN` 等价（须先按 device 分组求差再聚合，
即子查询 / 两段查询，不能直接在站级 `MAX−MIN`，理由同 6.1）。注意 `daily_*` 零点重置 →
窗口跨零点时 MAX−MIN 会异常，须保证聚合窗口与小时边界对齐（见 6.3）。

### 6.3 日内重置陷阱（daily_* 专有）

`daily_*` 零点重置为 0。若聚合窗口**跨越零点**（如 23:00 → 01:00），LAST−FIRST 可能为负或失真。
缓解：
- 连续聚合流 `INTERVAL(1h)` 按整点切，零点恰在边界 → 23:00 窗口（23:00–24:00 的累计末值 − 首值）
  与 00:00 窗口（从 0 起）各自正确，**天然安全**。
- `query_station_stats` 接受任意 start/end → 实施时须**拒绝/裁剪跨零点窗口**，或在文档明确"窗口须落在同一自然日内"。
- `charger_kwh`（终身累计，不重置）无此问题，LAST−FIRST 对任意窗口成立。

### 6.4 业务语义二选一（实施前需大圣裁决）

窗口电量有两种合理口径，取决于消费者需求：
- **(A) 窗口净增量** LAST−FIRST：可跨窗口 SUM 得日/月总量（推荐，与小时表语义一致）。
- **(B) 窗口末快照** `LAST(x)`：返回"截至窗口末的当日累计"，不可跨窗口 SUM。

连续聚合流 / 小时表 → 选 (A)。`query_station_stats` 若仅用于"看面板当前累计"可考虑 (B)，
但为口径统一建议同选 (A)，并在接口文档标注。

## 7. 实施清单（待工单）

1. 先确认 `station_*_hourly_stats` / `StationHourlyStats` 电量列有无报表/驾驶舱消费者（grep + 前端 API 核对）。
   - 有消费者 → 本族升为 P1 财务缺陷，按本方案三处同步修。
   - 无消费者 → 维持现状，本方案存档备查。
2. 三处同步改：6.1（子查询 PARTITION BY device_id）/ 6.2（SQLAlchemy 两段查询）/ 6.3（跨零点守卫）。
3. 翻转 1b312e62 新增的 3 个锁定 SUM 现状的测试（`tests/services/test_tdengine_writer_safety.py`），
   改断言为 LAST−FIRST 口径，并补"多设备子查询正确求和"与"跨零点窗口守卫"用例。
4. 全量 pytest（本机 `-n0` 串行，参卡 1b312e62 -n4 hang 教训）。

## 8. 本卡（eedd9431）已交付

- 本调研文档（不改任何聚合逻辑）。
- 三处 SUM 站点各加一行口径警示注释，指向本文档。
- `query_station_stats` docstring 加口径警告段。
