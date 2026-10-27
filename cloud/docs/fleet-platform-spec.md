# 天链 V3 车队管理平台 SPEC

**版本**: v1.4  
**日期**: 2026-07-23  
**状态**: 详细设计（对齐后端已实现 7 大 API 模块 + 丁哥澄清的车队业务模型）

---

## 1. 定位与角色

### 一句话定位
面向企业车队管理员、司机、财务人员的综合管理平台，覆盖**车辆全生命周期、司机账户体系、充电排队调度、V2G 双向互动、对账结算、碳排放核算、车队概览看板**七大功能闭环。

> **业务模型（v1.4 核心澄清）**：车队 = 光储充场站的**固定充电车队**，由**场站经营团队**创建与管理。闭环：经营团队建车队 → 绑定该团队所属场站(1..N) → 车队预储值 → 车辆 VIN 绑定 → 运营商手动/自动确认 → VIN 码在该运营商场站启动充电 → 充电统计/扣费。充电鉴权走 **VIN 码唯一路径**（不做 IC 卡用户）。

### 面向用户角色

| 角色 | 描述 | 核心诉求 |
|------|------|----------|
| **车队管理员** | 企业车队主管/调度员 | 车辆/司机档案、充电调度、V2G 计划、碳排报告、运营看板 |
| **司机** | 企业所属驾驶员 | 账户余额、充值/消费流水、排队叫号、充电记录、个人评分 |
| **财务人员** | 企业财务/会计 | 月度账单生成、对账确认、付款记录、发票申请、收益统计 |
| **经营团队** | 场站经营团队(operator) | 创建/管理本团队车队、绑定所属场站、预储值管理、车辆确认审核、自动确认规则配置 |

---

## 2. 功能闭环

### 2.1 车辆管理

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **车辆列表** | 企业名下所有车辆档案 | 车牌号、VIN、品牌车型、绑定司机、状态(在役/维修/退役) |
| **车辆绑定** | 新车入库/二手车入户 | 车牌号唯一性、VIN 唯一性、关联企业、初始状态 |
| **车辆解绑** | 车辆退役/过户 | 解绑校验(有无未结账单/未完成充电)、软删除保留历史 |
| **状态变更** | 维修/检修/恢复运营 | 状态流转: active → maintenance → active / retired |
| **车辆详情** | 单车全维度视图 | 基础信息、绑定司机、充电历史、V2G 收益、碳减排、费用汇总 |
| **VIN 绑定** | 车辆 VIN 码绑定，充电鉴权唯一依据 | VIN 17 位格式校验、VIN 唯一性、确认后自动同步站点白名单 |
| **车辆确认** | 运营商审核绑定车辆(手动/自动/批量) | approval_status(pending/confirmed/rejected)、自动确认规则(余额阈值/企业码)、确认同步 VIN 白名单、拒绝移出白名单 |
| **VIN 白名单** | 站点级充电白名单 | station_id + vin + enterprise_id + source(manual/auto)、仅白名单 VIN 可在该站充电 |

#### 闭环流程

```
开始 → 经营团队创建车队(enterprise)并绑定本团队场站(1..N) → 车队预储值
  → 录入车牌/VIN(17位校验)/司机 → 唯一性校验 → 创建车辆记录(active, approval_status=pending)
  → 运营商手动确认 / 自动确认(余额阈值/企业码) / 批量确认
  → 确认通过 → VIN 同步至绑定场站白名单 → VIN 码可在该运营商场站启动充电
  → 充电统计/扣费 → 解绑自动移除白名单 / 拒绝移出白名单
  → 维修: active → maintenance(禁止调度)
  → 退役: active → retired(冻结账户、结清账单)
  → 结束
```

---

### 2.2 司机管理

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **司机列表** | 分页/搜索/筛选 | 姓名/电话/驾照号/准驾车型/所属车辆/状态/累计充电/累计消费/评分 |
| **司机新增** | 入职建档 + 自动开户 | 驾照唯一性、账户自动创建(余额 0、ACTIVE) |
| **司机编辑** | 信息维护/车辆调派 | 驾照变更校验、车辆关联解绑 |
| **司机离职** | 级联删除/软删除 | 账户冻结、交易记录保留、关联车辆解绑 |
| **账户管理** | 余额查询/充值/冻结 | 余额、支付密码、状态(active/frozen/closed) |
| **交易流水** | 充值/消费/退款明细 | 类型、金额、交易后余额、关联订单号、备注、时间 |
| **人工记账** | 线下收退/补录 | consume/refund 类型、扣减/增加余额、关联订单号可选 |

#### 闭环流程

```
入职: 开始 → 录入基础信息 → 驾照唯一性校验 → 创建司机 → 自动创建账户 → 结束
充值: 开始 → 选择司机 → 输入金额/备注 → 余额增加 → 生成 recharge 流水 → 结束
消费: 开始 → 充电结算 → 余额扣减(检查充足) → 生成 consume 流水 → 更新司机累计消费 → 结束
退款: 开始 → 选择流水/订单 → 退款金额 → 余额增加 → 生成 refund 流水 → 结束
离职: 开始 → 账户冻结 → 车辆解绑 → 标记 terminated → 保留历史 → 结束
```

---

### 2.3 充电排队调度

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **实时队列** | 站点级等待/充电中列表 | 排序优先级、预计等待、需求电量、目标 SOC、当前 SOC、状态、分配设备 |
| **车辆入队** | 司机/车辆发起排队 | 站点、车辆、企业、需求电量、目标/当前 SOC、初始优先级 |
| **车辆离队** | 充电完成/主动取消/超时剔除 | 完成/取消状态、离队原因、触发重排 |
| **优先级调整** | 运营/调度人工干预 | 仅 waiting 状态可调、调整后自动重排 |
| **排序规则** | 多维度权重配置 | JSON 标准: `[{field, weight, direction}]`、企业/站点级、启停 |

#### 优先级计算标准 (JSON Schema)

```json
[
  {"field": "vip_level", "weight": 40, "direction": "desc"},     // VIP 等级越高越前
  {"field": "arrival_time", "weight": 30, "direction": "asc"},    // 先到先得
  {"field": "required_energy", "weight": 20, "direction": "desc"}, // 大电量优先
  {"field": "current_soc", "weight": 10, "direction": "asc"}      // 低电量优先
]
```

#### 闭环流程

```
入队: 开始 → 司机到站/APP 叫号 → 校验重复入队 → 校验队列上限 → 创建记录(waiting)
  → 读取活跃规则 → 计算优先级 → 插入队列 → 重算全队等待时间 → 结束

排队: 实时轮询 → 空闲枪匹配队首 → 分配设备 → 状态 charging → 开始充电 → 结束

离队: 充电完成/主动取消/超时 → 状态 completed/cancelled → 释放枪位
  → 读取规则 → 重排剩余队列 → 更新等待时间 → 结束
```

---

### 2.4 V2G 调度管理

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **计划管理** | 充放电时段排程 | 计划日期、充电窗口(开始/结束)、放电窗口(开始/结束)、目标 SOC 范围、状态 |
| **计划状态流转** | 执行过程跟踪 | scheduled → charging → discharging → completed / cancelled / failed |
| **收益记录** | 日度放电收益入账 | 放电电量、放电收益、电网响应次数、削峰电量、填谷电量、总收益 |
| **收益汇总** | 企业/车辆/时间维度聚合 | 总收益、总放电量、记录条数、月度趋势 |
| **调度执行记录** | 复用运维侧 `v2g_dispatch_logs` | 设备 ID、调度类型(charge/discharge/standby)、目标/实时功率、执行状态、时间窗 |

#### 闭环流程

```
排程: 开始 → 选择车辆/日期 → 设置充放电窗口/SOC 范围 → 创建计划(scheduled) → 结束

执行: 定时任务/人工触发 → scheduled → charging(下发充电指令)
  → 充电完成/达到 SOC 上限 → discharging(下发放电指令)
  → 放电完成/电网指令结束 → completed(记录收益) → 结束

异常: 任意阶段故障 → failed(记录错误) → 人工介入/重新排程 → 结束
```

---

### 2.5 对账结算

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **账单生成** | 按月聚合企业充电订单 | 账期(YYYY-MM)、企业、订单数、总电量、电费/服务费/停车费/优惠、应收/实收/余额、状态 |
| **账单列表** | 分页/筛选/导出 | 企业、账期、状态(pending/confirmed/paid) |
| **账单详情** | 汇总指标 + 明细入口 | 同生成字段 + 确认/付款时间、备注 |
| **账单明细** | 单笔订单级明细 | 订单号、车牌、司机、充电时间、电量、分项费用、优惠、实收 |
| **账单确认** | pending → confirmed | 仅 pending 可确认、记录确认时间/确认人/备注 |
| **账单付款** | confirmed → paid | 仅 confirmed 可付款、实付金额、余额自动计算、记录付款时间/备注 |
| **发票申请** | 对账单开具发票 | 抬头/税号/类型(普/专)/邮箱/备注、状态(pending/issued/voided) |
| **发票列表** | 申请记录查询 | 企业、状态、分页 |

#### 闭环流程

```
生成: 开始 → 选企业/账期 → 查该账期 completed 订单(按企业车牌/支付方式 enterprise 匹配)
  → 汇总 5 大费项 + 优惠 → 生成 bill_no(FSB+YYYYMM+企业ID) → 创建账单 + 明细 → 结束

确认: 开始 → 核对明细 → pending → confirmed(记录时间) → 结束

付款: 开始 → 确认到账金额 → confirmed → paid(记录时间/实付/余额) → 结束

开票: 开始 → 选账单 → 填抬头/税号/类型 → 创建申请(pending) → 财务审核 → 对接税务开具
  → 发送 PDF/邮箱 → 状态 issued → 作废: issued → voided(红冲) → 结束
```

---

### 2.6 碳排放管理

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **碳减排概览** | 企业年度/月度聚合视图 | 总充电量、总减排量(kgCO₂)、等效节油(L)、参与车辆数、月度趋势图 |
| **减排明细** | 单车/单日记录查询 | 车辆、日期、充电量、电网因子、燃油基准、减排量、等效节油 |
| **月度报告** | 汇总表(可审核归档) | 年/月、总充电量、总减排、总节油、车辆数、审核状态 |
| **报告审核** | 未审核 → 已审核 | 仅财务/管理员可操作、审核后不可修改明细 |
| **排放因子维护** | 电网/燃油基准配置 | 年份、区域(全国/分省)、类型(grid/fuel)、因子值、来源、唯一索引 |
| **手动计算入账** | 补录/修正单笔记录 | 车辆、日期、充电量 → 自动套用当年因子 → 计算减排/节油 → 入库 |

#### 核算公式

```
电网排放因子(grid_factor): kgCO₂/kWh (如 2022 全国平均 0.5703)
燃油基准排放(fuel_factor): kgCO₂/kWh = 0.56 L/kWh × 2.1625 kgCO₂/L = 1.211 kgCO₂/kWh

单次减排量 = (fuel_factor - grid_factor) × 充电电量(kWh)
等效节油量 = 充电电量(kWh) × 0.56 L/kWh
```

#### 闭环流程

```
自动汇总: 充电订单完成 → 定时任务按车辆/日期聚合 → 读取当年因子 → 计算减排/节油
  → 写入 carbon_reduction_records → 月末聚合生成 carbon_reduction_summary → 结束

手动补录: 开始 → 选车辆/日期/充电量 → 读取因子 → 计算 → 写入记录 → 结束

报告审核: 未审核 → 财务核对明细 → 标记 verified=true → 归档/导出 PDF → 结束
```

---

### 2.7 车队概览看板

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **企业基础信息** | 名称/编码/余额/状态/信用额度 | 实时余额、信用额度、状态标签 |
| **车队规模** | 车辆总数、在役/维修/退役分布 | 计数、占比饼图 |
| **充电运营** | 累计充电量(kWh)、累计消费(元) | 从交易流水/订单聚合 |
| **V2G 收益** | 累计放电量/收益/响应次数 | 从 fleet_v2g_revenue 聚合 |
| **碳减排** | 累计减排/节油/车辆数 | 从 carbon_reduction_records 聚合 |
| **近期交易** | 最近 5 笔充值/消费/退款 | 类型、金额、余额、关联单号、时间 |

#### 闭环流程

```
打开看板 → 并行查询 7 个聚合指标 → 前端渲染卡片/图表
  → 点击"查看详情"跳转对应管理页面(车辆/司机/账单/V2G/碳排) → 结束
```

---

### 2.8 企业运营管理（经营团队/场站绑定/预储值）

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **经营团队归属** | 车队(企业)必须归属场站经营团队 | owner_team_id → teams.id，创建时设定，数据按团队维度隔离 |
| **场站绑定** | 车队绑定本团队所属场站(1..N) | enterprise_stations 多对多、跨团队绑定 403 拒绝、available-stations 仅列本团队场站 |
| **预储值** | 车队账户预储值 + 信用额度 | balance 余额、credit_limit 信用额度，充电结算实时扣减 |
| **自动确认规则** | 车辆绑定自动确认条件 | system_config 配置: 余额阈值 / 企业码，达阈值自动 confirm |

#### 闭环流程

```
开始 → 经营团队创建车队 → 选择经营团队归属(owner_team) → 绑定本团队场站(1..N, 跨团队 403)
  → 车队预储值(balance) → 车辆 VIN 绑定 → 自动/手动确认
  → VIN 入站点白名单 → 充电扣费 → 余额不足触发告警/冻结
  → 结束
```

---

### 2.9 充电统计

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **单车充电统计** | 车队内单车充电聚合 | 日期范围、充电次数、总电量(kWh)、总费用、平均单次电量 |
| **车队级充电汇总** | 全车队充电汇总 | 日期范围、车辆数、总电量、总费用、车辆排行 |

#### 闭环流程

```
充电订单完成 → 按企业/车辆/日期聚合 → 单车统计 + 车队汇总
  → 车队看板/车辆详情页展示 → 结束
```

---

## 3. 页面路由结构

```
车队管理平台 Web (/fleet):
├── /fleet/dashboard                       车队概览看板
├── /fleet/vehicles                        车辆管理
│   ├── /fleet/vehicles/list               车辆列表
│   ├── /fleet/vehicles/create             绑定新车辆
│   └── /fleet/vehicles/:id                车辆详情(充电/V2G/碳排/费用标签页)
├── /fleet/drivers                         司机管理
│   ├── /fleet/drivers/list                司机列表
│   ├── /fleet/drivers/create              新增司机
│   └── /fleet/drivers/:id                 司机详情
│       ├── /fleet/drivers/:id/account     账户余额/充值
│       └── /fleet/drivers/:id/transactions 交易流水
├── /fleet/charging                        充电调度
│   ├── /fleet/charging/queue              实时队列(按站点)
│   ├── /fleet/charging/enqueue            手动入队
│   └── /fleet/charging/rules              排序规则配置
│       ├── /fleet/charging/rules/list     规则列表
│       └── /fleet/charging/rules/create   新建规则
├── /fleet/v2g                             V2G 调度
│   ├── /fleet/v2g/plans                   充放电计划
│   │   ├── /fleet/v2g/plans/list          计划列表
│   │   └── /fleet/v2g/plans/create        新建计划
│   ├── /fleet/v2g/revenue                 收益记录
│   │   └── /fleet/v2g/revenue/list        收益列表/汇总
│   ├── /fleet/v2g/status                  调度状态概览
│   └── /fleet/v2g/records                 执行记录(运维侧日志)
├── /fleet/settlement                      对账结算
│   ├── /fleet/settlement/bills            账单管理
│   │   ├── /fleet/settlement/bills/list   账单列表
│   │   ├── /fleet/settlement/bills/generate 生成账单
│   │   ├── /fleet/settlement/bills/:id    账单详情
│   │   │   ├── /fleet/settlement/bills/:id/details 明细列表
│   │   │   └── /fleet/settlement/bills/:id/invoice  申请发票
│   │   └── /fleet/settlement/bills/:id/confirm 确认账单
│   └── /fleet/settlement/invoices         发票申请列表
├── /fleet/carbon                          碳排放管理
│   ├── /fleet/carbon/overview             碳减排概览
│   ├── /fleet/carbon/details              减排明细
│   ├── /fleet/carbon/reports              月度报告
│   │   └── /fleet/carbon/reports/:id/verify 审核报告
│   ├── /fleet/carbon/factors              排放因子维护
│   │   ├── /fleet/carbon/factors/list     因子列表
│   │   └── /fleet/carbon/factors/create   新建因子
│   └── /fleet/carbon/calculate            手动计算入账
└── /fleet/settings                        设置
    ├── /fleet/settings/enterprise         企业基础信息
    └── /fleet/settings/vehicles           车辆默认配置
```

---

## 4. 数据库表结构

### 4.1 已实现表（复用/核心业务表）

| 表名 | 说明 | 核心字段 |
|------|------|----------|
| `enterprises` | 企业账户(车队) | id, name, code, balance, credit_limit, status, **owner_team_id**(FK→teams, 经营团队归属) |
| `enterprise_stations` | 车队-场站绑定(多对多) | id, enterprise_id, station_id, created_at（跨团队绑定 API 层 403 拒绝） |
| `enterprise_vehicles` | 企业车辆 | id, enterprise_id, plate_number, vin, driver_name, driver_phone, status, **approval_status**(pending/confirmed/rejected), confirmed_at, confirmed_by |
| `station_vin_whitelist` | 站点 VIN 充电白名单 | id, station_id, vin, enterprise_id, source(manual/auto), created_at（确认同步写入/拒绝·解绑移除） |
| `fleet_drivers` | 车队司机 | id, enterprise_id, name, phone, license_no, license_type, assigned_vehicle_id, hire_date, status, total_charge_kwh, total_spent, rating |
| `fleet_driver_accounts` | 司机账户 | id, driver_id, balance, pay_password, status |
| `fleet_driver_transactions` | 司机交易流水 | id, account_id, type(recharge/consume/refund), amount, balance_after, related_order_id, remark |
| `fleet_v2g_plans` | V2G 充放电计划 | id, enterprise_id, vehicle_id, plan_date, planned_charge_start/end, planned_discharge_start/end, target_soc_min/max, status |
| `fleet_v2g_revenue` | V2G 收益统计 | id, enterprise_id, vehicle_id, record_date, discharge_energy_kwh, discharge_revenue, grid_response_count, peak_shaving_kwh, valley_filling_kwh, total_revenue |
| `charging_queues` | 充电排队队列 | id, station_id, vehicle_id, enterprise_id, rule_id, priority, arrival_time, estimated_wait_minutes, required_energy_kwh, target_soc, current_soc, status, assigned_device_id |
| `charging_queue_rules` | 排序规则 | id, enterprise_id, station_id, rule_name, priority_criteria(JSON), max_queue_length, enable |
| `carbon_emission_factors` | 排放因子 | id, year, region, factor_type(grid/fuel), emission_factor, source |
| `carbon_reduction_records` | 碳减排明细 | id, vehicle_id, enterprise_id, record_date, charge_energy_kwh, grid_factor, fuel_factor, carbon_reduction_kg, equivalent_fuel_saved_liters |
| `carbon_reduction_summary` | 月度汇总报告 | id, enterprise_id, report_year, report_month, total_charge_kwh, total_reduction_kg, total_fuel_saved_liters, vehicle_count, verified |
| `fleet_settlement_bills` | 对账账单 | id, bill_no, enterprise_id, bill_period, total_orders, total_energy_kwh, total_charge_fee, total_service_fee, total_parking_fee, total_discount, total_amount, paid_amount, balance_amount, status, confirmed_at, paid_at |
| `fleet_settlement_details` | 账单明细 | id, bill_id, order_id, order_no, vehicle_id, plate_number, driver_id, charging_time, energy_kwh, charge_fee, service_fee, parking_fee, discount_amount, total_amount |
| `fleet_invoice_requests` | 发票申请 | id, enterprise_id, bill_id, amount, invoice_type, title, tax_no, email, status, remark |

### 4.2 关联/引用表（运维/运营侧复用）

| 表名 | 来源板块 | 用途 |
|------|----------|------|
| `charging_orders` | 运营平台/计费引擎 | 充电订单主表，结算按车牌/支付方式匹配企业 |
| `v2g_dispatch_logs` | 运维平台 | V2G 执行日志，/fleet/v2g/records 复用 |
| `stations` / `devices` | 运维平台 | 站点/设备基础信息，队列/调度关联 |
| `system_users` / `roles` | 平台管理 | 司机/管理员登录鉴权、RBAC |

### 4.3 需新增/扩展表（规划中）

| 表名 | 用途 | 核心字段草案 |
|------|------|--------------|
| `fleet_vehicle_maintenance` | 车辆维修保养记录 | id, vehicle_id, type(maintenance/repair/inspection), start_at, end_at, cost, mileage, description, status |
| `fleet_vehicle_insurance` | 车辆保险档案 | id, vehicle_id, insurance_type, company, policy_no, start_date, end_date, premium, attachment_url |
| `fleet_driver_attendance` | 司机考勤/工时 | id, driver_id, date, shift_type, hours, status, remark |
| `fleet_charging_policies` | 企业充电策略(限额/时段/站点白名单) | id, enterprise_id, daily_kwh_limit, allowed_time_slots(JSON), allowed_station_ids(JSON), enable |
| `fleet_alert_rules` | 车队告警规则(低电量/异常充电/超时未离桩) | id, enterprise_id, rule_type, threshold, notify_channels(JSON), enable |
| `fleet_carbon_certificates` | 碳减排核证/交易记录 | id, enterprise_id, summary_id, certificate_no, verified_at, trade_volume, trade_price, status |

---

## 5. 与其他板块边界

| 交互方 | 本板块提供 | 本板块依赖 |
|--------|-----------|-----------|
| **运维管理平台** | 车队充电需求(队列入队)、V2G 调度计划 | 设备实时状态(枪空闲/故障)、站点健康度、V2G 执行日志 |
| **运营管理平台** | 企业结算账单数据、企业用户消费明细 | 费用定价模型(尖峰平谷/服务费/停车费)、优惠券/积分规则、订单完整数据 |
| **平台管理** | — | 系统用户体系、RBAC 权限、企业/角色定义、支付通道配置 |
| **碳资产管理(规划)** | 月度核证报告、减排明细 | 国家/区域排放因子权威发布、碳交易所接口 |

### 不归属于本板块的功能

| 功能 | 归属板块 | 原因 |
|------|----------|------|
| 充电桩设备管理/固件升级/运维工单 | 运维管理平台 | 设备运维闭环 |
| 充电费定价/服务费/停车费/占桩费配置 | 运营管理平台 | 定价策略统一管理 |
| 优惠券/折扣/积分活动运营 | 运营管理平台 | 营销活动统一管理 |
| APP 用户/卡用户/VIN 用户/互联互通用户管理 | 运营管理平台 | C 端用户体系 |
| 系统配置/支付通道/消息通知/视频监控 | 平台管理 | 基础设施能力 |
| 站点建设/选址/电力接入/电网接入 | 运维/规划板块 | 基建范畴 |

---

## 6. API 模块对照表

| API 文件 | 路由前缀 | 核心端点 | 对应功能闭环 |
|----------|----------|----------|-------------|
| `fleet_overview.py` | `/api/v1/fleet` | `GET /overview` | 车队概览看板 |
| `enterprises.py` | `/api/v1/enterprises` | `CRUD + /stations GET/PUT + /available-stations` | 企业运营管理(经营团队归属/场站绑定) |
| `enterprise_vehicles.py` | `/api/v1/enterprises/{eid}/vehicles` | `GET/POST/DELETE + /confirm /reject /batch-confirm` | 车辆管理 + VIN 确认流 |
| `station_vin_whitelist.py` | `/api/v1/stations/{sid}/vin-whitelist` | `GET/POST/DELETE` | 站点 VIN 白名单 |
| `fleet_charging_stats.py` | `/api/v1/enterprises/{eid}` | `/charging-stats, /vehicles/{vid}/charging-stats` | 充电统计(车队级/单车) |
| `fleet_drivers.py` | `/api/v1/fleet/drivers` | `CRUD + /account + /transactions` | 司机管理 + 账户 + 流水 |
| `charging_queue.py` | `/api/v1/fleet/charging` | `/queue, /enqueue, /dequeue, /priority, /rules CRUD` | 充电排队调度 |
| `fleet_v2g.py` | `/api/v1/fleet/v2g` | `/plans CRUD, /revenue CRUD, /status, /records` | V2G 调度管理 |
| `fleet_settlement.py` | `/api/v1/fleet/settlement` | `/bills generate/list/detail/confirm/pay/invoice, /invoices` | 对账结算 |
| `carbon_emission.py` | `/api/v1/fleet/carbon` | `/overview, /details, /reports, /verify, /factors CRUD, /calculate` | 碳排放管理 |

---

## 7. 易事特/行业参考对比

| 易事特车队模块 | 天链车队平台覆盖 | 说明 |
|---------------|----------------|------|
| 车辆档案管理 | ✅ 完全覆盖 | 车牌/VIN/司机/状态全维度 |
| 司机管理 | ✅ 完全覆盖 | 档案+账户+流水一体化 |
| 充电调度/排队 | ✅ 完全覆盖 | 规则引擎+实时队列+优先级 |
| V2G 充放电策略 | ✅ 核心覆盖 | 计划排程+收益核算+执行记录 |
| 对账结算/发票 | ✅ 完全覆盖 | 月度账单+明细+确认付款+开票 |
| 碳排放/碳资产 | ✅ 核心覆盖 | 因子配置+减排核算+月报+审核 |
| 车辆维修保养 | 🟡 待扩展 | 已规划 fleet_vehicle_maintenance 表 |
| 车辆保险/年检 | 🟡 待扩展 | 已规划 fleet_vehicle_insurance 表 |
| 司机考勤/绩效 | 🟡 待扩展 | 已规划 fleet_driver_attendance 表 |
| 充电策略/权限控制 | 🟡 待扩展 | 已规划 fleet_charging_policies 表 |
| 告警/通知中心 | 🟡 待扩展 | 已规划 fleet_alert_rules 表 |
| 碳核证/交易 | 🟡 待扩展 | 已规划 fleet_carbon_certificates 表 |

---

## 8. 非功能性需求

| 维度 | 指标 |
|------|------|
| **并发** | 单企业 500+ 车辆同时排队，队列排序 < 200ms |
| **数据一致性** | 账单生成/确认/付款 状态机强约束，事务级原子性 |
| **审计** | 所有金额变动(充值/消费/退款/结算/发票)全链路留痕 |
| **数据保留** | 交易流水/充电明细/碳减排记录 ≥ 7 年 |
| **导出** | 账单/明细/碳报告 支持 Excel/PDF 导出，单次 ≤ 10 万行 |
| **权限** | 企业级数据隔离，跨企业查询需显式授权 |
| **兼容** | RESTful + OpenAPI 3.0，WebSocket 推送队列/V2G 状态实时更新 |

---

## 9. 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|----------|
| v1.0 | 2026-07-20 | 碳排放 stub (1.3KB) |
| v1.1 | 2026-07-21 | 新增车辆/司机/概览模块 |
| v1.2 | 2026-07-22 | 补齐充电队列/V2G/结算/碳排完整 API 与模型映射 |
| v1.3 | 2026-07-22 | 对齐 ops-platform-spec.md 格式，≥15KB 完整规格 |
| v1.4 | 2026-07-23 | **本版本** - 写入丁哥澄清的车队业务模型: 经营团队归属(owner_team_id)+场站绑定(enterprise_stations)+VIN 确认流(approval_status)+站点 VIN 白名单(station_vin_whitelist)+充电统计(§2.8/§2.9)；对齐已实现代码 faea454a8/c0f535d1d |

---

*文档维护: 石猴 @ 天链 V3 后端组*
