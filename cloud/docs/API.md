# 天链 V3 API 文档

> 本文档基于 `backend/app/api/v1/__init__.py` 的真实路由注册编写，给出模块前缀与说明。
> **完整端点、请求/响应 schema 以在线 Swagger 为准**：`/api/docs`（开发环境 http://localhost:8000/api/docs）。

> 📌 **API 单一源宣告（2026-07-31）**：`docs/openapi.json` 为 API 的机器唯一源（由后端代码 in-process 导出，613 paths，随代码变更同步刷新）。原手工维护的 `api-changelog.md`（止于 Phase33 / 2026-06-03）已归档至 `docs/archive/api-changelog.md`，不再更新。2026-06 以来的新增端点（security/policies CRUD、V2G 效率、websocket 标准化、登录锁定、站内消息中心等）以 openapi.json + 各 feature 文档为准。

## 基础信息

| 项 | 值 |
|----|----|
| 基础前缀 | `/api/v1` |
| WebSocket 前缀 | `/ws/v1/` |
| 认证 | OAuth2 Password Bearer（JWT，HS256） |
| 响应格式 | 统一 JSON：`{ code, message, data, ts }` |
| 分页格式 | `data: { items, total, page, page_size }` |
| API 文档 | Swagger `/api/docs` · ReDoc `/api/redoc` · OpenAPI `/api/openapi.json` |

### 统一响应示例

```json
{
  "code": 200,
  "message": "success",
  "data": { "id": 1, "name": "..." },
  "ts": "2026-07-27T10:00:00"
}
```

---

## 🔒 鉴权说明

### 全局强制认证

所有 `/api/v1/*` 端点默认要求 Bearer JWT，由 `app/api/v1/auth.py` 的 `enforce_auth` 依赖统一拦截。

**公开白名单**（无需 token，定义见 `is_public_path`）：
- `/api/v1/health/*` — 健康检查
- `/api/v1/auth/login`、`/api/v1/auth/register`、`/api/v1/auth/sms/*` — 认证公开端点
- `/api/v1/scan/*` — 扫码报修
- `/api/v1/telemetry/*` — 遥测数据上报
- Pod 注册 / 跨 Pod 查询（矩阵路由层）
- `/api/v1/alert-webhook` — Alertmanager 回调（需共享密钥，见 `docs/DEPLOY.md`）

### 认证流程

1. `POST /api/v1/auth/login`（`application/x-www-form-urlencoded`，字段 `username` / `password`）→ 返回 JWT
2. 后续请求携带头：`Authorization: Bearer <token>`
3. Token 默认有效期 **24 小时**（`ACCESS_TOKEN_EXPIRE_MINUTES=1440`）

```bash
# 登录示例
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -d "username=admin" -d "password=<密码>"

# 携带 token 请求
curl -H "Authorization: Bearer <token>" "http://localhost:8000/api/v1/stations?page=1"
```

### 认证端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册 |
| POST | `/auth/login` | 密码登录（OAuth2 form） |
| POST | `/auth/logout` | 登出 |
| POST | `/auth/refresh` | 刷新 token |
| POST | `/auth/sms/login` | 短信验证码登录 |
| POST | `/auth/sms/send` | 发送短信验证码 |
| POST | `/auth/sms/verify` | 校验验证码 |
| POST | `/auth/password-reset` | 密码重置 |

---

## API 模块清单（按业务域）

> 前缀已加到 `/api/v1` 之前。标注「见 Swagger」的模块路由路径在各自 router 内部定义，完整端点请查 `/api/docs`。

### 设备与站点

| 模块 | 前缀 | 说明 |
|------|------|------|
| 站点管理 | `/stations` | 站点 CRUD + VIN 白名单 |
| 设备管理 | `/devices` | 设备注册/监控/控制 + V2G 调度 |
| 设备库 | `/device-library` | 设备模板库 |
| 设备协议 | `/device-protocols`、`/protocol-rules` | 通信协议 + 解析规则 |
| 协议实例 | 见 Swagger | 设备协议实例管理 |
| 网关管理 | `/gateways` | IoT 网关注册、SN、固件 |
| 遥测数据 | `/telemetry` | report / latest / history / stats |

### 告警与通知

| 模块 | 前缀 | 说明 |
|------|------|------|
| 告警 | `/alarms` | 告警查询/确认/关闭 |
| 告警规则 | `/alarm-rules` | 阈值/触发条件/沉默期配置（**非** `/alarms/rules`） |
| 告警通知 | `/alarm-notices` | 通知记录/标记已读/统计 |
| 告警闭环 | `/alert-workflow` | 监控→告警→自愈闭环 |
| Alertmanager Webhook | `/alert-webhook` | 回调接收，强制密钥认证 |
| 通知配置 | `/notification-configs` | SMS/邮件/APP 渠道开关 |
| 通知规则 | `/notification-rules` | 发送规则 |
| 通知发送 | `/notifications` | 消息发送 |

### 诊断与运维

| 模块 | 前缀 | 说明 |
|------|------|------|
| 故障码诊断 | `/fault-diagnosis` | 故障码知识库 + 诊断 |
| 智能诊断 | `/diagnosis` | 设备健康五维评估/批量/趋势 |
| 智能故障诊断 | `/smart-diagnosis` | 关键词匹配自动诊断 |
| AI 日志分析 | `/log-analysis` | 大模型日志诊断流水线 |
| 告警自愈 | `/healing` | 自动修复引擎 |
| 工单 | `/work-orders` | 创建/派单/接单/处理/完成（**非** `/workorders`） |
| 备件库存 | `/spare-parts` | 备件 CRUD |
| 维护记录 | `/maintenance-records` | 维护记录 + 计划 |
| 巡检运维 | `/inspection` | 巡检计划与执行 |
| 值班排班 | `/on-call` | 值班调度 |
| Runbook | `/runbook`、`/runbook/approvals`、`/runbooks` | 自动化执行 / 审批流 / 模板 |
| 异步任务 | `/tasks` | Celery 任务管理 |

### 监控与分析

| 模块 | 前缀 | 说明 |
|------|------|------|
| 健康检查 | `/health` | 系统存活/就绪探针 |
| 健康度监控 | `/health` | 设备健康度 devices/trend（**非** `/health-monitor`） |
| 实时监控 | `/monitor` | 设备实时数据 |
| 运维大屏 | 见 Swagger | 大屏数据聚合 |
| 运维数据分析 | `/analytics` | 趋势分析与预测 |
| 数据大屏 | 见 Swagger | 独立展示模式 |
| 平台监控 | 见 Swagger | 拓扑 + 设备接入统计 |
| Prometheus 指标 | `/metrics` | 非 `/api/v1`，根级指标端点 |

### 报表

| 模块 | 前缀 | 说明 |
|------|------|------|
| 报表导出 | `/reports` | 设备/工单/站点/汇总（CSV/Excel） |
| 效率报表 | `/reports` | utilization / efficiency / generation |
| 能耗分析 | `/energy` | 光储充能耗数据 |
| 报告管理 | `/report-mgmt` | 报告模板与生成 |
| 运营分析 | 见 Swagger | 6 大运营报表 |

### 能源与调度

| 模块 | 前缀 | 说明 |
|------|------|------|
| 数字孪生 | `/digital-twin` | 站点/设备 3D 可视化 |
| 预测性维护 | `/predictive-maintenance` | AI 预测模型 |
| 虚拟电厂 | `/vpp` | VPP 调度优化、多站点协同 |
| 充电策略 | `/charging` | 5 种模式 + 光伏预测 + 储能调度 |

### 运营管理（`/operate` 前缀）

| 子模块 | 说明 |
|--------|------|
| overview / revenue_stats / financial | 运营概览 / 营收统计 / 财务管理 |
| orders / enterprise_recharge | 订单管理 / 企业充值 |
| discount / coupon / points / users | 折扣 / 优惠券 / 积分 / 用户类型 |
| settlement / invoice / invoice_platform_config | 结算对账 / 发票 / 开票平台配置 |
| charger_qrcode | 充电桩二维码 |
| interconnect / supervision | 互联互通 / 市政监管 |

运营域另含（前缀见 Swagger）：企业账户 `enterprises`（车队别名 `/fleet`）、定价 `pricing` / `pricing_management`、充电订单 `charging_orders`、停车 `parking`、订单费用 `order_fees`。

> ⚠️ 企业账户双路由字段坑：`/enterprises` 用 `contact`/`phone`；`/fleet/enterprises` 用 `contact_person`。

### 车队管理（`/fleet` 前缀）

| 子模块 | 前缀 | 说明 |
|------|------|------|
| 车队概览 | `/fleet` | 整体运营数据 |
| 司机管理 | `/fleet/drivers` | 司机 CRUD |
| 充电策略 | `/fleet/policies` | 限额/时段/站点白名单 |
| 资金账户 | `/fleet/funds` | 企业资金账户 |
| 考勤工时 | `/fleet/attendance` | 批量录入/月度汇总 |
| 对账结算 | `/fleet/settlement` | 车队对账 |
| V2G 调度 / 智能充电调度 / 碳排放 / 碳核证 / 车辆维保 / 告警规则 / 充电排序 | `/fleet` | 见 Swagger |
| 车辆管理 | `/enterprises/{enterprise_id}/vehicles` | 车队车辆 CRUD |
| 资金池交易 | `/enterprises/{enterprise_id}/transactions` | 充值/扣费/交易记录 |
| 车队充电统计 | 见 Swagger | 单车 + 汇总 |

### 管理后台

| 模块 | 前缀 | 说明 |
|------|------|------|
| 终端管理 | `/admin/terminals` | 物联网终端接入 |
| 云服务配置 | `/admin/cloud-configs` | 云服务接入 |
| 互联互通（兼容） | `/admin/interconnect` | 旧路径，已迁至 `/operate/interconnect` |
| 市政监管（兼容） | `/admin/supervision` | 旧路径，已迁至 `/operate/supervision` |
| 出站 Webhook | `/webhooks` | SPEC §2.6 出站 Webhook 管理 |

### 权限、用户与系统

| 模块 | 前缀 | 说明 |
|------|------|------|
| 权限管理 | `/rbac` | 角色/权限/用户 |
| 权限列表/树 | `/permissions` | 权限树形图 |
| 角色管理 | `/roles` | 团队级角色 |
| 用户管理 | `/users` | 用户 CRUD |
| 团队 / 工程师 | `/teams`、`/engineers` | 团队 / 工程师管理 |
| 安全管理 | `/security` | 安全策略与配置 |
| 操作日志 | `/operation-log` | 操作审计 |
| SSL 证书 | `/ssl` | 证书生命周期 |
| 多租户 | `/tenants` | 租户隔离 |
| API 密钥 | 见 Swagger | 密钥创建/撤销 |
| 系统配置 | `/system-config` | 全局配置 |
| 知识库 | `/knowledge` | 文章 CRUD / 搜索 |
| 统计 | `/stats` | 系统统计面板 |
| 缓存 | `/cache` | 缓存统计 |

### AI

| 模块 | 前缀 | 说明 |
|------|------|------|
| 天链助手 | 见 Swagger | AI 对话 / 语音配置 |
| AI 模型配置 | 见 Swagger | 模型配置管理 |

### 实时推送

| 通道 | 前缀 | 说明 |
|------|------|------|
| WebSocket | `/ws/v1/` | 设备遥测、数字孪生实时推送（标准化前缀，详见 `app/ws/`） |

### Pod 矩阵路由层

| 模块 | 前缀 | 说明 |
|------|------|------|
| Pod 注册 | 见 Swagger | 分布式 Pod 健康注册（Phase2） |
| 跨 Pod 查询 | 见 Swagger | 矩阵路由层跨 Pod 数据查询 |

---

## 核心端点速查

### 健康检查
```bash
curl http://localhost:8000/api/v1/health
# → { "status": "healthy", "version": "3.0.0", ... }
```

### 站点列表
```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/stations?page=1&page_size=10"
```

### 遥测上报
```bash
curl -X POST "http://localhost:8000/api/v1/telemetry/report" \
  -H "Content-Type: application/json" \
  -d '{"device_id": 1, "metrics": {"voltage": 220.5}}'
```

### WebSocket 实时数据
```js
const ws = new WebSocket('ws://localhost:8000/ws/v1/realtime');
```

---

## 模拟器（无设备联调）

`backend/scripts/` 提供设备模拟器，支持无真实设备联调：
- Modbus 逆变器模拟
- MQTT 充电桩模拟
- 故障码自动生成（正常/故障比例可配）

---

> 本文档为模块级导航。每个端点的精确路径、参数、响应 schema 请以 **`/api/docs` Swagger UI** 为准（FastAPI 自动生成，始终与代码同步）。
