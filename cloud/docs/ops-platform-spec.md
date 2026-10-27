# 运营管理平台 SPEC

**版本**: v1.0  
**日期**: 2026-07-17  
**状态**: 详细设计

---

## 1. 定位与角色

### 一句话定位
面向运营人员的经营管理后台，以"营收闭环"为核心，覆盖充电运营全链路从定价→交易→结算→分析的业务流程。

### 面向用户角色

| 角色 | 描述 | 核心诉求 |
|------|------|----------|
| **运营主管** | 负责整体运营策略与营收目标 | 营收看板、运营分析、定价策略 |
| **运营专员** | 日常运营操作 | 订单管理、优惠管理、用户管理 |
| **财务人员** | 对账结算 | 账单管理、发票管理、费用审核 |
| **客服人员** | 处理用户咨询与异常 | 异常订单处理、退款管理 |

---

## 2. 功能闭环

### 2.1 费用模型管理

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **充电费定价** | 基于尖峰平谷时段设置基础电价 | 时段定义(尖/峰/平/谷)、电价(元/kWh)、生效日期、站点粒度 |
| **服务费定价** | 充电服务费标准设置 | 按电量计费(元/kWh) / 按次固定金额、可区分用户类型 |
| **停车费定价** | 站内停车计时收费 | 免费时长(分钟)、小时费率(元/小时)、封顶金额、区分时段 |
| **占桩费定价** | 充电完成后超时停放罚金 | 免罚时长(分钟)、罚金费率(元/分钟)、单次封顶 |
| **预约费定价** | 预约充电占位费 | 预约冻结金额、按时段费率、爽约罚款规则 |

#### 闭环流程

**充电费+服务费**  
开始 → 用户启动充电 → 系统记录起始电表值(SOC) → 充电结束记录结束电表值 → 按时段计量各时段电量 → 充电费 = ∑(时段电量×时段电价) → 服务费 = 总电量×费率 | 固定金额 → 生成费用明细 → 加入订单总费用 → **结束**

**停车费**  
开始 → 车辆进入车位(地锁/车牌识别触发) → 开始计时 → 充电期间免费(充电费已含停车权) → 充电结束+免停分钟 → 若未离场 → 按分钟计费 → 停车费 = 超时时长×小时费率 → 加入订单总费用 → **结束**

**占桩费**  
开始 → 充电完成(充电枪未拔) → 免罚倒计时(通常15-30分钟) → 超时未拔枪/未驶离 → 按分钟计罚金 → 占桩费 = 超时分钟×罚金费率 → 加入订单总费用 → **结束** (用户插枪/驶离后停止)

**预约费**  
开始 → 用户发起预约 → 系统锁定充电位 → 冻结预约押金 → 用户按时到场开始充电 → 释放押金 → 若爽约 → 扣除押金作为违约费 → **结束**

#### 总费用公式

```
总费用 = 充电费 + 服务费 + 停车费 + 占桩费 + 预约费
实收金额 = 总费用 - 优惠券抵扣 - 积分抵扣 - 折扣减免
```

---

### 2.2 订单管理

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **订单列表** | 所有充电订单展示 | 订单编号、用户信息、充电桩/枪、站点、开始/结束时间、时长、电量、SOC(始/末)、电表值(始/末)、5项费用明细、总费用、实收金额、支付方式、状态 |
| **订单筛选** | 多维度检索 | 按用户类型、站点、时间段、费用金额区间、状态(完成/异常/退款中) |
| **订单详情** | 完整订单信息 | 订单基本信息、计费明细(5项费用拆解)、充电曲线、设备日志、停止原因(充满/主动停止/故障/余额不足/后台停止) |
| **异常订单** | 非正常结束订单处理 | 故障中断、离线补传、对账不平 — 标记/人工审核/补录 |
| **退款处理** | 用户退款申请 | 退款审核、原路退回、部分退款、退款记录 |

#### 闭环流程

开始 → 用户启动充电 → 系统创建订单(状态:充电中) → 实时记录充电数据 → 用户停止/充满/异常中断 → 订单关闭(状态:待结算) → 费用计算(5项) → 支付扣款 → 订单完成(状态:已完成) → 若用户申请退款 → 退款审批 → 原路退回 → 订单标记(状态:已退款) → **结束**

---

### 2.3 用户类型管理

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **APP用户** | 通过手机APP注册的个人用户 | 手机号、昵称、注册时间、余额、累计充电量、累计消费 |
| **卡用户** | 持有实体RFID充电卡的用户 | 卡号、持卡人、关联手机号、余额、发卡日期 |
| **VIN用户** | 车辆VIN码绑定自动识别 | VIN码、车辆品牌、车主信息、自动计费账户 |
| **互联互通用户** | 其他平台(华为/国网等)跳转用户 | 来源平台、关联账户、分成比例 |
| **企业用户** | 企业账户下的子用户 | 企业名、部门、预算额度、对账周期 |

#### 闭环流程

开始 → 用户注册/导入(5种类型各自创建) → 用户信息审核 → 用户状态设置(正常/停用/黑名单) → 用户充电行为记录 → 用户等级/积分成长 → 用户数据纳入营收分析 → **结束**

---

### 2.4 优惠管理

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **折扣电价管理** | 不同用户类型享有差异化电价 | 折扣名称、折扣率、适用用户类型、适用时段、适用站点 |
| **折扣组管理** | 批量定价策略 | 折扣组名称、成员定义、阶梯规则、生效时间 |
| **优惠券管理** | 优惠券发行与核销 | 券类型(满减/折扣/抵扣)、面额、使用门槛、有效期、发行量、已领/已用 |
| **积分管理** | 积分获取与消费体系 | 积分规则(充电1元= x分)、积分有效期、积分抵扣比例、积分商城 |

#### 闭环流程

**优惠券**  
开始 → 创建优惠券活动 → 设置规则(类型/面额/阈值/有效期/总量) → 发布活动 → 用户领券 → 充电结算时自动匹配可用券 → 费用抵扣 → 券核销 → 统计核销率 → **结束**

**积分**  
开始 → 设置积分规则 → 用户充电获得积分 → 积分累积 → 积分有效期管理 → 积分兑换(折扣/实物) → 抵扣订单金额 → 积分扣减 → 统计积分流通 → **结束**

---

### 2.5 发票管理

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **发票申请** | 用户提交开票请求 | 申请来源(APP/后台代开)、开票金额、开票类型(电子发票/纸质)、抬头信息(个人/企业) |
| **发票抬头管理** | 常用发票抬头维护 | 抬头名称、纳税人识别号、注册地址、银行账户 |
| **发票审核** | 运营审核开票申请 | 审核列表、金额核对、审核通过/驳回 |
| **发票开具** | 对接税务系统 | 开票API调用、发票号码、发票PDF生成、发送用户 |
| **发票记录** | 历史开票查询 | 发票号码、金额、开票日期、状态(已开/已作废) |

#### 闭环流程

开始 → 用户提交开票申请(选择订单/选择金额) → 系统校验开票资格(已支付+未开票) → 运营审核 → 审核通过 → 调用开票服务 → 生成电子发票 → 发送用户邮箱/APP → 发票状态更新(已开票) → 如需作废 → 提交作废申请 → 审核通过 → 红冲处理 → **结束**

---

### 2.6 运营分析

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **营收总览** | 平台收入全貌 | 总营收(元)、总充电量(度)、总订单数、客单价；趋势图(日/周/月/年) |
| **费用占比分析** | 5项费用收入构成 | 充电费/服务费/停车费/占桩费/预约费各自占比，饼图+趋势 |
| **用户收入分析** | 按用户类型收入拆分 | APP/卡/VIN/互联互通/企业各自营收贡献、户均消费、复充率 |
| **站点收益排行** | 各站点营收排名 | 站点列表、营收、充电量、利用率、收益/桩 |
| **时段收益分析** | 按尖峰平谷时段营收 | 各时段电量分布、电价贡献、服务费占比 |
| **优惠效果分析** | 优惠活动的效果评估 | 券核销率、因优惠带来增量订单数、优惠成本vs营收增长、ROI计算 |

#### 闭环流程

开始 → 选择分析维度(时间范围/站点/用户类型) → 系统聚合数据(订单+费用+优惠) → 生成分析图表 → 运营解读 → 调整定价/优惠策略 → 新策略上线 → 持续监控效果 → **循环**

---

### 2.7 结算与对账

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **日结汇总** | 每日营收汇总 | 日期、总订单数、应收总额、实收总额、优惠金额、退款金额、结算状态 |
| **支付对账** | 与支付通道对账 | 平台订单vs支付流水(IM-B/支付宝/银联)、对账差异标记、差异处理 |
| **企业结算** | 企业用户定期结算 | 企业对账周期、消费明细、结算金额、发票匹配、打款记录 |
| **互联互通结算** | 与互联互通平台结算 | 他平台导流订单、分成比例、结算周期、结算记录 |

---

## 3. 页面路由结构

```
运营管理平台 Web (/operate):
├── /operate/dashboard                    运营首页（营收看板）
├── /operate/pricing                      费用定价管理
│   ├── /operate/pricing/energy           充电费定价（尖峰平谷）
│   ├── /operate/pricing/service          服务费定价
│   ├── /operate/pricing/parking          停车费定价
│   ├── /operate/pricing/occupancy        占桩费定价
│   └── /operate/pricing/reservation      预约费定价
├── /operate/orders                       订单管理
│   ├── /operate/orders/list              订单列表
│   ├── /operate/orders/detail/:id        订单详情
│   └── /operate/orders/abnormal          异常订单
├── /operate/refunds                      退款管理
│   ├── /operate/refunds/pending          待审核退款
│   └── /operate/refunds/history          退款记录
├── /operate/users                        用户管理（5种用户类型）
│   ├── /operate/users/app                APP用户
│   ├── /operate/users/card               卡用户
│   ├── /operate/users/vin                VIN用户
│   ├── /operate/users/interconnect       互联互通用户
│   └── /operate/users/enterprise         企业用户
├── /operate/discounts                    折扣管理
│   ├── /operate/discounts/prices         折扣电价
│   └── /operate/discounts/groups         折扣组
├── /operate/coupons                      优惠券管理
│   ├── /operate/coupons/list             优惠券列表
│   └── /operate/coupons/create           创建优惠活动
├── /operate/points                       积分管理
│   ├── /operate/points/rules             积分规则
│   ├── /operate/points/list              积分流水
│   └── /operate/points/exchange          积分兑换
├── /operate/invoices                     发票管理
│   ├── /operate/invoices/pending         待审核发票
│   ├── /operate/invoices/list            已开发票
│   └── /operate/invoices/titles          发票抬头
├── /operate/settlement                   结算对账
│   ├── /operate/settlement/daily         日结汇总
│   ├── /operate/settlement/reconciliation 支付对账
│   ├── /operate/settlement/enterprise    企业结算
│   └── /operate/settlement/interconnect  互联互通结算
└── /operate/analytics                    运营分析
    ├── /operate/analytics/revenue        营收总览
    ├── /operate/analytics/fee-breakdown  费用占比分析
    ├── /operate/analytics/user-revenue   用户收入分析
    ├── /operate/analytics/station-rank   站点收益排行
    ├── /operate/analytics/time-slot      时段收益分析
    └── /operate/analytics/coupon-effect  优惠效果分析
```

---

## 4. 数据库表

### 已有表（复用，无须新增）
- `work_orders` — 工单表（运营侧查看）
- `stations` — 站点表（运营定价按站点粒度）
- `devices` — 设备表（关联订单充电桩信息）

### 需新增的表

```sql
-- ==================== 费用定价 ====================

-- 时段定义（尖峰平谷时段模板）
time_slot_definitions: id, name(尖/峰/平/谷), start_time, end_time, season(夏季/冬季/全年), sort_order

-- 充电费定价
energy_prices: id, station_id, slot_definition_id, price_per_kwh, effective_date, expire_date, status, created_at

-- 服务费定价
service_fee_prices: id, station_id, user_type, fee_type(fixed/percent), fee_value(decimal), effective_date, expire_date, status, created_at

-- 停车费定价
parking_prices: id, station_id, free_minutes, hourly_rate, daily_cap, enable_night_rate, night_rate, night_start, night_end, created_at

-- 占桩费定价
occupancy_fee_prices: id, station_id, grace_minutes, rate_per_minute, max_fee, enable, created_at

-- 预约费定价
reservation_fee_prices: id, station_id, deposit_amount, reservation_policy(slot_based/flat), fee_amount, no_show_penalty, enable, created_at


-- ==================== 订单与费用 ====================

-- 充电订单（核心订单表）
charging_orders: id, order_no(订单编号), user_id, user_type(app/card/vin/interconnect/enterprise), device_id, station_id, connector_id,
  start_time, end_time, duration_seconds,
  start_soc, end_soc, start_meter, end_meter,
  total_energy_kwh, peak_energy, flat_energy, valley_energy, trough_energy,
  charge_fee(decimal), service_fee(decimal), parking_fee(decimal), occupancy_fee(decimal), reservation_fee(decimal),
  total_amount(decimal), paid_amount(decimal), discount_amount, coupon_amount, points_amount,
  payment_method(im-b/alipay/unionpay/balance/account),
  status(charging/completed/refunding/refunded/abnormal),
  stop_reason(full/active/fault/balance_low/admin),
  created_at, updated_at

-- 费用明细（5项费用拆分明细表）
order_fee_items: id, order_id, fee_type(energy/service/parking/occupancy/reservation), fee_name, quantity, unit_price, amount, unit(kwh/minutes/hour), created_at

-- 订单充电曲线记录
order_charge_curves: id, order_id, record_time, current_power, energy_this_minute, voltage, current, soc

-- 退款记录
refund_records: id, order_id, user_id, refund_amount, refund_reason, status(pending/approved/rejected/refunded), reviewer_id,
  review_time, remark, created_at


-- ==================== 用户类型 ====================

-- APP用户
app_users: id, user_id(关联system_users), phone, nickname, avatar, balance, total_charge_kwh, total_spent, level, points, status, created_at

-- 卡用户
card_users: id, card_no(唯一), user_id, holder_name, bind_phone, balance, status, issued_at, created_at

-- VIN用户
vin_users: id, vin(车辆识别码), brand, model, plate_number, user_id, bind_phone, auto_pay_account, status, created_at

-- 互联互通用户/平台
interconnect_platforms: id, platform_name, platform_code, api_key, contact, phone, revenue_share_ratio, bind_date, status, created_at
interconnect_users: id, platform_id, outer_user_id, nickname, phone, created_at

-- 企业用户
enterprise_accounts: id, enterprise_name, credit_code, contact_person, contact_phone, balance, billing_cycle(monthly/quarterly), status, created_at
enterprise_sub_users: id, enterprise_id, user_id, department, budget_limit, status, created_at


-- ==================== 优惠管理 ====================

-- 折扣电价
discount_prices: id, name, discount_type(fixed/percentage), discount_value, user_type_scope, station_scope, time_slot_scope, start_date, end_date, status, created_at

-- 折扣组
discount_groups: id, name, description, rule_json(阶梯规则), status, created_at

-- 优惠券
coupons: id, name, type(discount/deduction/full_reduction), value, min_amount, max_amount, user_type_scope, per_user_limit,
  total_quantity, remaining_quantity, start_time, end_time, status(draft/published/ended), created_at
coupon_claims: id, coupon_id, user_id, claim_time, usage_time, order_id, status(unused/used/expired)
coupon_activity_stats: id, coupon_id, total_claimed, total_used, total_discount_amount, created_at

-- 积分规则
points_rules: id, name, earn_rate(元/积分), consume_rate(积分/元), max_earn_per_order, expiration_days, status, created_at
points_logs: id, user_id, change_amount, balance_after, type(earn/consume/expire), source(charge/exchange/admin), related_id, created_at


-- ==================== 发票管理 ====================

-- 发票信息
invoice_titles: id, user_id, title_type(personal/enterprise), title_name, tax_id, register_address, register_phone, bank_name, bank_account, is_default, created_at
invoices: id, user_id, order_ids(JSON), invoice_title_id, amount, invoice_type(electronic/paper), invoice_status(pending/issued/voided),
  invoice_no, invoice_code, pdf_url, apply_time, review_time, issue_time, reviewer_id, created_at


-- ==================== 结算对账 ====================

-- 日结汇总
daily_settlements: id, settlement_date, total_orders, total_energy, total_charge_fee, total_service_fee, total_parking_fee,
  total_occupancy_fee, total_reservation_fee, total_amount, total_paid, total_discount, total_coupon, total_points,
  total_refund, status(pending/confirmed), confirmed_at, created_at

-- 支付对账
payment_reconciliation: id, settlement_date, platform_orders_count, platform_amount, payment_orders_count, payment_amount,
  difference_count, difference_amount, status(pending/reconciled), created_at

-- 互联互通结算
interconnect_settlements: id, platform_id, start_date, end_date, total_orders, total_energy,
  total_amount, revenue_share_ratio, our_revenue, partner_revenue, settlement_amount,
  invoice_id, status(pending/settled), settled_at, created_at


-- ==================== 运营分析 (报表聚合) ====================

-- 营收日汇总
revenue_daily: id, record_date, user_type, station_id, orders_count, energy_kwh, charge_fee, service_fee,
  parking_fee, occupancy_fee, reservation_fee, total_revenue, paid_revenue, refund_amount, created_at

-- 站点日运营指标
station_daily_metrics: id, station_id, record_date, active_users, new_users, orders_count, energy_kwh, revenue,
  utilization_rate, avg_charge_duration, avg_wait_time, online_devices, idle_ratio, created_at
```

---

## 5. 与其他板块的边界

| 交互方 | 本板块提供 | 本板块依赖 |
|--------|-----------|-----------|
| **运维管理平台** | 运营数据（用户/订单/收入）供运维看板参考 | 设备状态、站点健康度（用于分析利用率vs营收关联） |
| **平台管理** | — | 用户体系(Users)、权限控制(RBAC)、角色定义 |
| **车队管理平台** | 企业结算数据、企业用户费用明细 | 企业账户信息、车辆绑定关系 |

### 不归属于本板块的功能
- 设备管理/运维工单 → 归运维管理平台
- 系统用户/角色/权限 → 归平台管理
- 车辆管理/司机管理 → 归车队管理
- 物联网网关/协议/设备库 → 归平台管理

---

## 6. 易事特参考对比

### 已覆盖功能

| 易事特模块 | 天链运营平台覆盖情况 | 说明 |
|-----------|------------------|------|
| 运营概览 | ✅ 营收看板 | 本板块dashboard定位 |
| 财务管理(5种费用) | ✅ 完全覆盖 | 充电/服务/停车/占桩/预约, 新增3项 |
| 运营管理(折扣/优惠券/积分) | ✅ 已有 | Discount/Coupon/Points三个页面 |
| 用户管理(5种用户) | ✅ 完全覆盖 | APP/卡/VIN/互联互通/企业, UserTypeManagement页面 |
| 订单管理 | ✅ 完全覆盖 | Operate页面, 15种子订单类型需持续丰富 |
| 发票管理 | ✅ 新增 | 本板块补齐 |
| 统计分析 | ✅ 运营分析 | 按用户类型/营收/充电量 |
| 退款管理 | ✅ 订单管理中 | 退款处理闭环 |
| 合作加盟 | 🟡 待定 | 运营商合作伙伴管理，后续版本考虑 |

### 未覆盖功能（非本板块职责）

| 易事特模块 | 归属板块 | 原因 |
|-----------|---------|------|
| 设备管理 | 运维管理平台 | 设备运维闭环 |
| 车辆管理 | 车队管理平台 | 车辆运营闭环 |
| 停车管理(物理地锁/车位管理) | 运维管理平台 | 设备运维范畴 |
| 互联互通(运营商绑定) | ✅ 运营平台 | 按运营团队隔离配置 (§2.8) |
| 视频监控 | 运维管理平台 | 站点监控运维 |
| 消息通知 | 平台管理 | 系统级通知 |
| 系统管理(角色/支付通道) | 平台管理 | 平台基础管理 |
| 市政监管 | ✅ 运营平台 | 按运营团队隔离配置 (§2.9) |
---

## 2.8 互联互通对接（迁移自管理后台 2026-07-23）

### 定位
按运营团队隔离的互联互通（中电联协议）对接管理。不同运营团队对接的合作伙伴（其他运营商）不同，各团队独立配置伙伴清单+凭证。

### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **伙伴配置管理** | 配置互联互通合作伙伴 | team_id、伙伴名称、平台编码、中电联协议版本(V1.0/V1.6/V2.0)、API地址、认证方式、同步方向(push/pull/bidirectional)、分成比例 |
| **联调测试** | 校验对接配置可用性 | 地址可达性检查、认证有效性检查 |
| **导流订单查询** | 查看他平台同步过来的充电订单 | 来源平台、外部订单号、充电量、费用、分成金额、状态 |
| **手动录入订单** | 手动补录遗漏的导流订单 | 同订单字段 |

### 数据模型

```sql
-- interconnect_configs (已添加 team_id + protocol_version + sync_direction)
interconnect_configs: id, team_id, platform_name, platform_code(huawei/sgcc/csg/teld),
  api_base_url, auth_type(apikey/oauth), auth_params(json),
  protocol_version(V1.0/V1.6/V2.0), sync_direction(push/pull/bidirectional),
  revenue_share_ratio, data_sync_interval, status, remark, created_at, updated_at

-- interconnect_orders (已添加 team_id)
interconnect_orders: id, team_id, platform_id, platform_code, outer_order_id,
  outer_user_id, station_id, device_id, charge_energy_kwh, total_amount,
  our_share, partner_share, status(synced/settled/conflict), synced_at, created_at
```

### 团队隔离
- 所有查询和操作通过 `X-Team-Id` 请求头过滤
- `team_id=0` 表示平台默认模板（向后兼容）
- 团队A无法查看/编辑/删除团队B的配置

### API 路径
- `GET/POST/PUT/DELETE /api/v1/operate/interconnect/configs` — 伙伴配置 CRUD
- `POST /api/v1/operate/interconnect/configs/{id}/test` — 联调测试
- `GET/POST /api/v1/operate/interconnect/orders` — 订单查询/录入
- 旧路径 `/api/v1/admin/interconnect/*` 保留兼容（下个版本移除）

---

## 2.9 市政监管对接（迁移自管理后台 2026-07-23）

### 定位
按运营团队隔离的市政充电监管平台对接管理。各地市平台各有专属规则和协议（广州粤易充、上海联联、浙江浙里充等），协议适配器做成扩展点，具体城市适配器接入需求明确时逐个实现。

### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **监管配置管理** | 配置地市监管平台 | team_id、城市、城市编码、平台名称(粤易充/联联/浙里充)、平台类型、协议类型(http_push/http_pull/mqtt/websocket)、平台URL、认证配置 |
| **上报策略** | 配置数据上报规则 | 上报策略(scheduled/realtime)、上报间隔、端点配置(station/device/order/heartbeat)、心跳保活 |
| **上报记录** | 查看上报历史 | 上报类型、状态(success/failed/pending)、重试次数、错误信息 |
| **手动上报** | 触发一次数据上报 | 选择配置和上报类型 |
| **重试机制** | 重试失败的上报 | 自动+手动重试，重试计数 |
| **合规检查** | 监管合规状态检查 | 检查类型(data_integrity/report_delay/compliance)、结果(pass/warn/fail)、合规得分 |

### 数据模型

```sql
-- municipal_supervision_configs (已添加 team_id + city_code + platform_name + platform_type + protocol_type)
municipal_supervision_configs: id, team_id, city, city_code, platform_name(粤易充/联联/浙里充),
  platform_type(yueyichong/lianlian/zhelichong/generic/other), protocol_type(http_push/http_pull/mqtt/websocket),
  platform_url, auth_config(json), report_strategy(scheduled/realtime), report_interval_seconds,
  station_endpoints(json), heartbeat_enabled, status, remark, created_at, updated_at

-- regulatory_reports (已添加 team_id)
regulatory_reports: id, team_id, config_id, city, report_type(station/device/order/heartbeat),
  report_content(json), status(success/failed/pending), retry_count, error_message, reported_at, created_at

-- compliance_checks (已添加 team_id)
compliance_checks: id, team_id, config_id, city, check_type(data_integrity/report_delay/compliance),
  result(pass/warn/fail), score, details(json), checked_at, created_at
```

### 团队隔离
- 同互联互通，通过 `X-Team-Id` 请求头实现团队隔离

### API 路径
- `GET/POST/PUT/DELETE /api/v1/operate/supervision/configs` — 监管配置 CRUD
- `GET/POST /api/v1/operate/supervision/reports` — 上报记录 + 手动触发
- `POST /api/v1/operate/supervision/reports/{id}/retry` — 重试
- `GET/POST /api/v1/operate/supervision/compliance` — 合规检查
- 旧路径 `/api/v1/admin/supervision/*` 保留兼容（下个版本移除）

### 协议适配器扩展点

```python
# 接口层设计（具体城市适配器接入需求明确时逐个实现）
class SupervisionProtocolAdapter(ABC):
    @abstractmethod
    async def report_station(self, config: MunicipalSupervisionConfig, data: dict) -> bool: ...
    @abstractmethod
    async def report_device(self, config: MunicipalSupervisionConfig, data: dict) -> bool: ...
    @abstractmethod
    async def report_order(self, config: MunicipalSupervisionConfig, data: dict) -> bool: ...
    @abstractmethod
    async def heartbeat(self, config: MunicipalSupervisionConfig) -> bool: ...

# 注册表
ADAPTERS: dict[str, type[SupervisionProtocolAdapter]] = {
    "yueyichong": YueyichongAdapter,    # 广州粤易充
    "lianlian": LianlianAdapter,        # 上海联联
    "zhelichong": ZhelichongAdapter,    # 浙江浙里充
    "generic": GenericHTTPAdapter,      # 通用HTTP
}
```
