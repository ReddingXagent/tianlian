# 平台管理 SPEC

**版本**: v1.0  
**日期**: 2026-07-17  
**状态**: 详细设计

---

## 1. 定位与角色

### 一句话定位
面向系统管理员的平台基础管理中心，覆盖"用户→权限→配置→监控→审计"的全链路，承载租户隔离、设备接入、外部系统对接等平台级能力。

### 面向用户角色

| 角色 | 描述 | 核心诉求 |
|------|------|----------|
| **系统管理员** | 平台最高权限管理者 | 用户管理、权限分配、系统配置、审计监控 |
| **租户管理员** | 多租户环境下的租户管理 | 租户隔离、租户资源配置、租户用量监控 |
| **安全管理员** | 安全策略与审核 | 审计日志、API密钥、SSL证书、安全策略 |
| **消息管理员** | 通知策略配置 | 消息模板、通知规则、发送记录 |
| **设备接入管理员** | 设备接入配置 | 设备库、协议管理、网关管理、终端管理 |
| **集成管理员** | 云服务与API密钥 | 云服务配置、API密钥管理、SSL证书 |

> **注**: 互联互通和市政监管已于 2026-07-23 迁移至运营平台。

---

## 2. 功能闭环

### 2.1 用户与权限管理

#### 功能清单

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **用户列表** | 全平台用户管理 | 用户名、昵称、手机号、邮箱、用户类型(admin/engineer/operator/fleet)、状态(正常/停用/锁定)、最后登录时间 |
| **用户创建** | 新增平台用户 | 用户名、密码、手机号、邮箱、用户类型、所属团队/企业 |
| **用户编辑** | 修改用户信息 | 同创建，预填充 |
| **用户停用/启用** | 用户状态管理 | 停用原因、停用/启用操作 |
| **用户类型管理** | 用户类型与权限预置 | 用户类型(admin/engineer/operator/fleet)、每种类型的默认角色、首页路由配置 |
| **角色管理(RBAC)** | 细粒度角色权限 | 角色名称、权限树(菜单可见性+按钮级权限+API权限)、角色类型(系统预置/自定义) |
| **权限矩阵** | 角色-权限可视化 | 矩阵视图(角色×权限)、继承关系、冲突检测 |
| **角色分配** | 为用户分配角色 | 用户选择、角色多选、生效时间 |

#### 闭环流程

开始 → 创建用户 → 分配用户类型 → 分配角色(一个或多个) → 用户登录 → 权限校验(菜单/按钮/API) → 授权操作 → 如需变更→修改角色/权限→重新登录生效 → 用户停用→立即禁止登录 → **结束**

---

### 2.2 租户管理

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **租户列表** | 多租户管理 | 租户名称、租户代码、联系人、套餐类型、状态、创建时间 |
| **租户创建** | 新增租户 | 租户名称、代码、联系人信息、套餐选择、容量限制(站点数/设备数/用户数)、过期时间 |
| **租户配置** | 租户级配置 | 独立品牌配置(Logo/名称/主题色)、数据隔离策略、功能菜单可见性 |
| **租户用量监控** | 租户资源使用统计 | 已用/总容量、站点数、设备数、用户数、存储使用量、API调用量 |
| **租户续费** | 租户套餐续期 | 当前套餐、到期时间、续费周期、续费操作 |

#### 闭环流程

开始 → 创建租户(分配资源配额) → 租户初始化(品牌+数据隔离+功能配置) → 租户入驻运维团队+设备 → 日常监控租户用量 → 接近容量上限→预警提示 → 租户续费/升级套餐 → 资源扩充 → 租户到期→数据冻结/自动下线 → **结束**

---

### 2.3 系统配置

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **全局配置** | 平台级参数设置 | 系统名称、Logo、版权信息、登录页背景、系统语言 |
| **通知配置** | 消息通知通道设置 | 短信通道(云服务商/服务商B云/华为云)、邮件服务器(SMTP)、APP推送通道、通道状态 |
| **支付通道** | 支付渠道配置 | IM-B支付、支付宝、银联、对公转账、通道参数配置、验签密钥 |
| **发票配置** | 开票服务配置 | 电子发票服务商、开票参数、税率设置、企业开票信息 |
| **AI模型配置** | 智能分析模型管理 | 模型列表、API端点配置、模型参数、启用/停用、调用统计 |

#### 闭环流程

开始 → 配置全局参数 → 对接外部服务(短信/邮件/支付) → 测试连通性 → 启用通道 → 日常运行 → 监控通道健康状态 → 异常告警 → 维护/切换通道 → **循环**

---

### 2.4 物联网接入管理

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **设备库** | 设备型号库管理 | 设备品牌、型号、类型(充电桩/光伏/储能/V2G)、技术参数模板、规格书 |
| **设备协议** | 通信协议管理 | 协议名称、协议类型(OCPP/Modbus/MQTT/HTTP)、协议版本、参数定义、数据点映射 |
| **协议管理** | 协议解析规则 | 上行数据解析规则、下行指令编码规则、自定义协议脚本 |
| **网关管理** | 设备网关配置 | 网关编号、网关类型(工业网关/边缘网关)、IP地址、端口、在线状态、关联设备数 |
| **终端管理** | 终端设备(摄像头/传感器) | 终端编号、类型、安装站点、在线状态、流地址(RTSP/RTMP)、录制配置 |
| **云服务** | 云平台连接配置 | 公有云/私有云配置、数据同步策略、存储桶配置 |

#### 闭环流程

开始 → 设备库录入设备型号 → 配置通信协议(OCPP/Modbus等) → 网关安装部署 → 真实设备注册 → 绑定协议+网关 → 设备上线连接 → 协议解析数据 → 数据上行(遥测/告警) → 控制指令下行 → 设备离线→断线重连 → 网关维护→恢复 → **持续循环**

---

### 2.5 物联网接入管理（互联互通+市政监管已迁移至运营平台）

> **架构变更 2026-07-23**: 互联互通和市政监管已迁移至运营平台 (`/operate/interconnect`, `/operate/supervision`)，按运营团队隔离。本节仅保留物联网终端管理和云服务配置。
>
> 详见 [运营平台 SPEC](./ops-platform-spec.md) §2.8 互联互通对接 + §2.9 市政监管对接。

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **终端管理** | 摄像头/传感器/门禁等物联网终端管理 | 终端类型、绑定站点、状态(在线/离线)、最后心跳 |
| **云服务配置** | 公有云/私有云对接配置 | 云服务商、存储桶、同步策略、连通性测试 |

#### 闭环流程

**终端管理**  
开始 → 终端录入 → 绑定站点 → 上线连接 → 状态监控 → 异常告警 → 维护/更换 → **循环**

---

### 2.6 API与集成管理

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **API密钥管理** | 平台API调用凭证 | 密钥名称、AppKey、AppSecret、权限范围(可访问API集合)、状态(启用/停用)、最后调用时间 |
| **API密钥创建** | 生成新密钥 | 名称、权限选择(按API分组分配)、自动生成AppKey+AppSecret |
| **API调用统计** | 监控第三方API调用 | 调用次数、成功/失败率、响应时间、按密钥/API路径统计 |
| **Webhook** | 事件回调配置 | Webhook名称、回调URL、事件类型(告警/工单/订单)、签名密钥、重试策略 |

#### 闭环流程

开始 → 创建API密钥(授予特定API权限) → 第三方使用AppKey+AppSecret调用平台API → 系统鉴权(校验密钥+权限) → 允许/拒绝调用 → 记录调用日志(成功/失败/IP/时间) → 超频限制→返回429 → 月调用统计分析 → 密钥泄露→停用+重新生成 → **结束**

---

### 2.7 审计与安全

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **审计日志** | 全平台操作日志 | 时间、操作用户、IP地址、操作类型、操作对象、操作内容、结果(成功/失败) |
| **日志筛选** | 多维度检索 | 按时间范围/用户/操作类型/对象/结果筛选 |
| **日志导出** | 审计日志导出 | 时间范围选择、格式(CSV/Excel)、导出 |
| **日志分析** | 操作行为分析 | 异常操作检测、频繁失败登录检测、敏感操作统计 |
| **安全配置** | 安全策略管理 | 密码策略(复杂度/过期时间/历史限制)、登录策略(失败锁定/并发登录/IP白名单)、会话超时 |
| **SSL证书管理** | HTTPS证书管理 | 证书名称、域名、颁发机构、生效/到期时间、证书状态、上传/更新/部署 |

#### 闭环流程

开始 → 用户操作 → 系统自动记录操作日志 → 审计日志集中存储 → 定期审计检查 → 安全策略执行(密码/登录/IP/会话) → 异常检测(失败登录/敏感操作) → 告警通知管理员 → 手动审查 → 安全事件处理 → **循环**

---

### 2.8 消息中心

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **消息列表** | 全平台消息通知 | 消息标题、内容、类型(告警/工单/系统/推广)、接收人、状态(未读/已读)、发送时间 |
| **消息模板** | 通知模板管理 | 模板名称、类型(短信/邮件/APP推送)、模板内容(支持变量)、示例预览 |
| **通知规则** | 消息发送策略 | 规则名称、触发事件(告警触发/工单分配/订单完成)、通知对象(角色/个人)、通知渠道(APP/短信/邮件)、时段限制、静默期 |
| **发送记录** | 查看所有消息发送 | 接收人、渠道、内容、发送时间、状态(成功/失败)、失败原因 |
| **消息统计** | 发送效果分析 | 发送总量、成功率、各渠道对比 |

#### 闭环流程

开始 → 配置消息模板 → 配置通知规则(事件→渠道→对象) → 系统事件触发 → 匹配规则 → 生成消息内容(模板渲染) → 多渠道发送(APP推送/短信/邮件) → 记录发送结果 → **循环**

---

### 2.9 平台监控与仪表板

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **平台仪表板** | 全平台运行状态总览 | 在线设备数/总设备数、活跃用户数、今日订单量、今日营收、API调用量、告警总数 |
| **系统资源** | 服务器资源监控 | CPU使用率、内存使用率、磁盘使用率、网络流量、服务状态 |
| **服务拓扑** | 微服务依赖关系图 | 各服务节点、调用链、健康状态(绿/黄/红)、响应时间 |
| **设备接入统计** | 接入设备全景 | 各类设备(充电桩/光伏/储能/V2G)统计、在线率、协议分布 |

#### 闭环流程

开始 → 系统各组件主动上报运行指标 → 平台仪表板实时汇总展示 → 资源超阈值→告警管理员 → 排查处理 → 指标恢复正常 → **持续循环**

---

### 2.10 Runbook审批

| 子功能 | 描述 | 核心元素 |
|--------|------|----------|
| **审批列表** | Runbook审批工单 | 审批编号、Runbook名称、提交人、提交时间、状态(待审批/已通过/已拒绝) |
| **审批详情** | 查看Runbook内容 | Runbook步骤、执行脚本、风险评估、提交说明 |
| **审批操作** | 通过/拒绝 | 审批意见、通过/拒绝按钮 |

---

## 3. 页面路由结构

```
平台管理 Web (/platform /gateway /tenants 等 admin路由):
├── /platform/dashboard                     平台仪表板（系统运行总览）
├── /config                                 系统配置（全局参数/基础配置）
├── /users                                   用户管理
├── /rbac                                    RBAC权限管理
│   ├── /rbac/users                         用户列表
│   ├── /rbac/roles                         角色管理
│   └── /rbac/teams                         团队管理
├── /tenants                                租户管理
│   ├── /tenants/list                       租户列表
│   ├── /tenants/:id                        租户详情
│   ├── /tenants/:id/usage                  租户用量
│   └── /tenants/create                     创建租户
├── /gateway                                网关管理
│   ├── /gateway/list                       网关列表
│   └── /gateway/:id                        网关详情
├── /device-library                         设备库管理
│   ├── /device-library/list                设备型号库
│   └── /device-library/:id                 设备型号详情
├── /device-protocols                       设备协议管理
│   ├── /device-protocols/list              协议列表
│   └── /device-protocols/:id               协议详情/配置
├── /protocols                              协议解析规则
│   ├── /protocols/list                     规则列表
│   └── /protocols/:id                      规则详情
├── /links                                  互联互通管理
│   ├── /links/platforms                    互联平台列表
│   ├── /links/platforms/:id                平台配置
│   ├── /links/orders                       互联互通订单
│   └── /links/settlements                  互联互通结算
├── /cloud                                  云服务配置
│   └── /cloud/settings                     云平台配置
├── /terminals                              终端管理
│   ├── /terminals/list                     终端列表
│   └── /terminals/:id                      终端详情
├── /api-keys                               API密钥管理
│   ├── /api-keys/list                      密钥列表
│   └── /api-keys/create                    创建密钥
├── /audit-log                              审计日志
│   ├── /audit-log/list                     日志列表
│   └── /audit-log/analysis                 日志分析
├── /log-analysis                           日志分析(详细分析)
├── /security                               安全配置
│   └── /security/policy                    密码/登录/会话策略
├── /ssl-certificates                       SSL证书管理
│   ├── /ssl-certificates/list              证书列表
│   └── /ssl-certificates/upload            上传证书
├── /message-center                         消息中心
│   ├── /message-center/messages            消息列表
│   ├── /message-center/templates           消息模板
│   └── /message-center/stats               消息统计
├── /notification-rules                     通知规则配置
│   ├── /notification-rules/list            规则列表
│   └── /notification-rules/create          创建规则
├── /runbook-approval                       Runbook审批
│   ├── /runbook-approval/pending           待审批
│   └── /runbook-approval/history           审批历史
├── /ai-model-config                        AI模型配置
└── /platform/monitor                       监控视图(资源/服务拓扑)
```

---

## 4. 数据库表

### 已有表（复用，无须新增）
- `teams` — 运维团队（复用）
- `engineers` — 工程师（复用）
- `stations` — 站点（复用）
- `devices` — 设备（复用）
- `work_orders` — 工单（复用）
- `alarms` — 告警（复用）
- `knowledge` — 知识库（复用）

### 需新增的表

```sql
-- ==================== 用户权限管理 ====================

-- 平台用户（已在system_users基础上扩展）
system_users: id, username, password_hash, nickname, phone, email,
  user_type(admin/engineer/operator/fleet), status(active/disabled/locked),
  login_fail_count, last_login_at, last_login_ip, created_at

-- 角色定义
roles: id, name, code, description, type(system/custom), user_type_scope, status, created_at

-- 权限定义
permissions: id, name, code, parent_id, type(menu/button/api), path/action, sort_order

-- 角色-权限关联
role_permissions: id, role_id, permission_id, effect(allow/deny)

-- 用户-角色分配
user_roles: id, user_id, role_id, effective_start, effective_end, assigned_by, created_at


-- ==================== 租户管理 ====================

tenants: id, name, code(唯一), contact_person, contact_phone, plan_type(basic/pro/enterprise),
  max_stations, max_devices, max_users, data_storage_limit_gb,
  brand_config(json: {logo_url, site_name, theme_color, login_bg}),
  status(active/frozen/expired), start_date, expire_date, created_at

tenant_usage: id, tenant_id, record_date, station_count, device_count, user_count,
  storage_used_gb, api_calls_today, created_at


-- ==================== 系统配置 ====================

system_configs: id, config_key, config_value(json), description, config_type(global/notification/payment/invoice/ai), updated_at


-- ==================== 物联网接入 ====================

-- 设备型号库
device_library: id, brand, model, device_type(charger_dc/charger_ac/pv/battery/v2g),
  rated_power_kw, params_template(json), supported_protocols(json), spec_url, status, created_at

-- 通信协议
device_protocols: id, name, code, type(ocpp/modbus/mqtt/http/custom), version,
  protocol_definition(json), data_point_mappings(json), status, created_at

-- 协议解析规则
protocol_rules: id, protocol_id, direction(uplink/downlink), message_type, 
  parse_rule(json), encode_rule(json), status, created_at

-- 网关
gateways: id, gateway_code, type(industrial/edge), ip_address, port, 
  station_id, protocol_ids(json), status(online/offline), last_heartbeat, created_at

-- 终端设备
terminals: id, terminal_code, type(camera/sensor/access_control), station_id,
  ip_address, stream_url, record_config(json), status, created_at

-- 云平台配置
cloud_configs: id, cloud_provider(cloud-provider/vendor-b/aws/private), config_json,
  storage_bucket, data_sync_policy, status, created_at


-- ==================== 互联互通 ====================

interconnect_configs: id, platform_name, platform_code(huawei/sgcc/csg/teld),
  api_base_url, auth_type(apikey/oauth), auth_params(json), 
  revenue_share_ratio, data_sync_interval, status, created_at

interconnect_orders: id, platform_id, outer_order_id, outer_user_id, 
  station_id, device_id, charge_energy_kwh, total_amount, our_share, partner_share,
  status(synced/settled/conflict), created_at

interconnect_settlements: id, platform_id, period_start, period_end, total_orders,
  total_energy, total_amount, our_share_total, partner_share_total,
  settlement_amount, status(pending/settled), settled_at, created_at


-- ==================== 市政监管 ====================

municipal_supervision_configs: id, city, platform_url, data_auth_config(json),
  report_interval_seconds, station_report_endpoints(json), status, created_at

municipal_report_logs: id, config_id, report_type(station/device/order/heartbeat),
  report_content(json), status(success/failed), error_message, reported_at


-- ==================== API密钥 ====================

api_keys: id, name, app_key, app_secret(加密存储), permission_scope(json: [api_paths]),
  ip_whitelist(json), status(active/disabled/expired), last_used_at, created_at

api_call_logs: id, api_key_id, request_path, method, ip_address,
  status_code, response_time_ms, created_at


-- ==================== 审计日志 ====================

audit_logs: id, user_id, username, ip_address, user_agent,
  action_type(login/logout/create/update/delete/export),
  target_type, target_id, action_detail(json),
  result(success/failure), created_at


-- ==================== 安全配置 ====================

security_policies: id, policy_key(password/login/session/ip), policy_config(json:
  {min_length, require_upper, require_digit, expire_days, history_count,
   fail_lock_count, lock_duration_minutes, concurrent_session_limit,
   session_timeout_minutes, ip_whitelist_enabled}),
  status, updated_at

ssl_certificates: id, domain, certificate_type, issuer, serial_no,
  effective_date, expire_date, certificate_content(加密存储), private_key(加密存储),
  status(valid/expired/revoked), deployed_at, created_at


-- ==================== 消息中心 ====================

notification_templates: id, name, code, channel(sms/email/app_push),
  template_content(含变量), params_definition(json), status, created_at

notification_rules: id, name, trigger_event(alarm/order/work_order/system),
  event_filters(json), recipient_type(role/specific), recipient_ids(json),
  channels(json: [sms/email/app_push]), time_restriction(json: {start_hour, end_hour}),
  quiet_seconds, status, created_at

notifications: id, title, content, type(alarm/order/work_order/system),
  sender, recipient_type(role/user), recipient_id, template_id,
  channel(sms/email/app_push), status(pending/sent/failed), error_msg,
  read_at, sent_at, created_at
```

---

## 5. 与其他板块的边界

| 交互方 | 本板块提供 | 本板块依赖 |
|--------|-----------|-----------|
| **运营管理平台** | 用户身份+权限校验、消息通知、支付通道配置、发票服务配置 | — |
| **运维管理平台** | 用户身份+权限校验、消息通知、设备接入数据(设备库/协议/网关)、告警通知推送 | — |
| **车队管理平台** | 用户身份+权限校验、消息通知 | — |

### 不归属于本板块的功能
- 充电定价/订单管理/用户类型(5种运营用户) → 归运营管理平台
- 设备运维/工单流转/巡检 → 归运维管理平台
- 车辆管理/充电排序/碳排放 → 归车队管理平台
- 费用定价策略/优惠券/积分 → 归运营管理平台

---

## 6. 易事特参考对比

| 易事特模块 | 天链平台管理覆盖情况 | 说明 |
|-----------|------------------|------|
| 系统管理（角色） | ✅ 完全覆盖 | RBAC角色+权限管理 |
| 系统管理（支付通道） | ✅ 完全覆盖 | 支付通道配置 |
| 系统管理（短信） | ✅ 完全覆盖 | 短信通道+消息通知 |
| 系统管理（发票） | ✅ 完全覆盖 | 发票服务配置 |
| 消息通知 | ✅ 完全覆盖 | 消息中心+模板+规则 |
| 互联互通（运营商绑定） | 🔄 已迁移至运营平台 | 见 ops-platform-spec.md §2.8 |
| 市政监管 | 🔄 已迁移至运营平台 | 见 ops-platform-spec.md §2.9 |
| 视频监控 | ✅ 已覆盖（终端管理） | 摄像头/传感器管理 |
| — | — | — |
| **天链特有（易事特未明确）** | | |
| 租户管理 | ✅ 新增 | 多租户隔离能力 |
| 设备库/协议管理 | ✅ 新增 | 完整的设备接入体系 |
| 网关管理 | ✅ 新增 | 物联网网关配置 |
| API密钥管理 | ✅ 新增 | 开放平台API管理 |
| SSL证书管理 | ✅ 新增 | 安全证书生命周期管理 |
| Audit日志+日志分析 | ✅ 新增 | 操作审计与安全 |
| AI模型配置 | ✅ 新增 | 智能运维模型管理 |
| Runbook审批 | ✅ 新增 | 自动化脚本审批流 |