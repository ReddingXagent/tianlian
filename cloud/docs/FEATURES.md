# 功能板块总览

> 天链 Cloud 全部功能板块索引 —— 按模块域划分，标注 Web 入口与后端 API 归属

本文档覆盖平台**所有业务板块**，共 11 个业务域、70+ 前端页面、100+ 后端 API 模块。「状态」列说明该板块在当前开源版中的完整度。

---

## 目录

1. [监控与总览](#1-监控与总览)
2. [设备与资产](#2-设备与资产)
3. [遥测与协议接入](#3-遥测与协议接入)
4. [告警与通知](#4-告警与通知)
5. [诊断与智能分析](#5-诊断与智能分析)
6. [工单与现场运维](#6-工单与现场运维)
7. [自动化运维](#7-自动化运维)
8. [充电运营](#8-充电运营)
9. [车队与 V2G](#9-车队与-v2g)
10. [能源与虚拟电厂](#10-能源与虚拟电厂)
11. [平台治理](#11-平台治理)
12. [移动端](#12-移动端)
13. [设备模拟器](#13-设备模拟器)

---

## 1. 监控与总览

| 板块 | Web 页面 | 说明 | 后端 API |
|------|----------|------|----------|
| 运维驾驶舱 | `/` Dashboard | 核心指标总览：在线设备、今日告警、工单进度、发电与充电量 | `dashboard.py` |
| 运营看板 | `/ops-dashboard` | 运维 KPI：工单时效、告警闭环率、巡检完成率 | `ops_dashboard.py` |
| 数据分析 | `/analytics-dashboard` | 多维数据聚合与趋势分析 | `analytics/` `operations_analytics.py` |
| 业主驾驶舱 | `/owner-cockpit` | 面向电站业主的收益与运行视图 | `owner_cockpit.py` |
| 数据大屏 | `/large-screen` | 全屏可视化大屏，适合展厅与指挥中心 | `stats.py` |
| 电子地图 | `/stations`（地图视图） | 站点地理分布与状态着色 | `stations.py` |
| 平台监控 | `/platform/dashboard` | 平台级健康度、Pod 路由、跨节点状态 | `platform_monitor.py` `pod_routes.py` `cross_pod.py` |
| 健康监控 | `/health` | 服务健康、依赖探活、SLA 趋势 | `health.py` `health_monitor.py` |

## 2. 设备与资产

| 板块 | Web 页面 | 说明 | 后端 API |
|------|----------|------|----------|
| 设备台账 | `/devices` | 全量设备档案：型号、SN、归属站点、运行状态 | `devices.py` |
| V2G 设备 | `/devices/v2g` | 车网互动设备专项管理 | `v2g.py` |
| 站点管理 | `/stations` | 站点档案、容量、设备挂载 | `stations.py` |
| 设备库 | `/device-library` | 可复用设备型号与参数模板 | `device_library.py` |
| 设备协议 | `/device-protocols` | 协议定义与寄存器/点位映射 | `device_protocols.py` |
| 协议实例 | `/protocols` | 协议实例化配置，关联具体设备 | `protocol_instances.py` |
| 网关管理 | `/gateway` | 边缘网关注册、在线状态、下挂设备 | `gateways.py` `admin_edge_gateways.py` |
| 备件管理 | — | 备件库存、领用与消耗记录 | `spare_parts.py` |
| 维保记录 | — | 设备维保历史与到期提醒 | `maintenance_records.py` |

## 3. 遥测与协议接入

| 板块 | Web 页面 | 说明 | 后端 API |
|------|----------|------|----------|
| 实时遥测 | `/telemetry` `/monitor` | 设备实时点位、曲线、批量上报 | `telemetry/` |
| 经典遥测 | `/telemetry-classic` | 兼容旧版展示方式的遥测视图 | `telemetry/` |
| WebSocket 推送 | — | `/ws/v1/` 设备遥测与数字孪生实时通道 | `app/ws/` |
| 协议解析 | — | Modbus / MQTT / DLT645 / IEC104 解析器 | `app/parsers/` |
| IoT 网关 | — | modbus / mqtt / rest 接入网关 | `app/gateway/` |

## 4. 告警与通知

| 板块 | Web 页面 | 说明 | 后端 API |
|------|----------|------|----------|
| 告警中心 | `/alarms` | 告警列表、级别、确认与关闭 | `alarms.py` |
| 告警通告 | `/alarm-notices` | 面向多方的告警通告发布 | `alarm_notices.py` |
| 告警规则 | — | 阈值/组合条件规则引擎 | `alarm_rules.py` |
| 告警工作流 | — | 告警升级、分派、SLA 计时 | `alert_workflow.py` `alert_ack.py` |
| 通知规则 | `/notification-rules` | 渠道与接收人配置（短信/邮件/IM/Webhook） | `notification_rules.py` `notification_configs.py` |
| 消息中心 | `/message-center` | 站内消息与订阅 | `notifications.py` |
| 告警 Webhook | — | 外部系统对接回调 | `alert_webhook.py` |

## 5. 诊断与智能分析

| 板块 | Web 页面 | 说明 | 后端 API |
|------|----------|------|----------|
| 故障诊断 | `/fault-diagnosis` `/diagnosis` | 故障现象归因、处理建议 | `fault_diagnosis.py` |
| 智能诊断 | `/smart-diagnosis` | 模型辅助的深度诊断 | `smart_diagnosis.py` |
| 预测性维护 | `/predictive-maintenance` | 基于趋势的故障预测与维护排期 | `predictive_maintenance.py` |
| 日志分析 | `/log-analysis` | 日志聚合、异常提取、根因辅助 | `log_analysis.py` |
| 知识库 | `/knowledge` | 故障案例、处置经验沉淀与检索 | `knowledge/` |
| 巡检运营 | `/inspection-ops` | 巡检计划、执行、结果归档 | `inspection.py` |
| AI 模型配置 | `/config`（AI 模型） | 可插拔 LLM 接入与场景路由 | `ai_model_config_api.py` |
| 智能问答 | — | 面向运维的自然语言助手 | `chat.py` |

## 6. 工单与现场运维

| 板块 | Web 页面 | 说明 | 后端 API |
|------|----------|------|----------|
| 工单管理 | `/workorders` | 创建、派发、接单、验收全流程 | `workorders/` |
| 工单统计 | `/workorder-stats` | 时效、完成率、人员效能 | `workorders/` |
| 值班管理 | `/on-call` | 排班、值班表、交接 | `on_call.py` |
| 团队管理 | `/teams` | 运维团队、成员、权限 | `teams.py` |
| 工程师档案 | `/teams/engineers` | 技能矩阵、等级、派单匹配 | `engineers.py` |
| 远程控制 | `/remote-control` | 设备远程指令下发与回执 | `devices.py` |
| 站点维保授权 | — | 临时授权与白名单 | `station_maintenance_grants.py` |

## 7. 自动化运维

| 板块 | Web 页面 | 说明 | 后端 API |
|------|----------|------|----------|
| Runbook 编排 | `/runbook` | 运维剧本定义与执行 | `runbook.py` `runbook_templates.py` |
| Runbook 审批 | `/runbook-approval` | 高风险动作审批流 | `runbook_approval.py` |
| 自愈 | `/healing` | 异常自动处置策略与执行记录 | `healing.py` |
| 数字孪生 | `/digital-twin` | three.js 三维站点还原与交互 | `digital_twin.py` |

## 8. 充电运营

入口：`/operate`（运营工作台，含 17 个子模块）

| 板块 | 说明 | 后端 API |
|------|------|----------|
| 充电订单 | 订单流水、异常单处理 | `charging_orders.py` `operate/orders.py` |
| 充电会话 | 实时充电过程、电量与费用 | `charging_sessions.py` |
| 充电排队 | 场站排队策略与调度 | `charging_queue.py` |
| 充电策略 | 功率分配、时段策略 | `charging_strategy.py` `charging_schedule.py` |
| 计费定价 | 分时电价、服务费模板 | `pricing.py` `pricing_management.py` `operate/pricing_templates.py` |
| 订单费用 | 费用构成、优惠叠加 | `order_fees.py` |
| 优惠券 | 券模板、发放、核销 | `operate/coupon_api.py` |
| 折扣管理 | 折扣规则与审批 | `operate/discount.py` |
| 积分管理 | 积分规则、账户、流水 | `operate/points_api.py` |
| 结算对账 | 平台费、商户分账、结算单 | `operate/ops_settlement.py` `operate/financial.py` |
| 开票 | 发票申请、平台配置、开具回调 | `operate/ops_invoice.py` `business_invoices.py` |
| 充电桩二维码 | 场站/枪口码生成与投放 | `operate/charger_qrcode.py` |
| 商户管理 | 运营商与服务商档案 | `operate/ops_merchants.py` |
| 营收统计 | 收入构成与趋势 | `operate/revenue_stats.py` |
| 企业充值 | 企业账户充值与审批 | `operate/enterprise_recharge.py` `RechargeApproval` |
| 退款 | 退款申请与处理 | `Refunds` |
| 互联互通 | 第三方充电网络对接 | `operate/interconnect.py` `admin_interconnect.py` |
| 运营监管 | 监管平台上报 | `operate/supervision.py` `admin_supervision.py` |

**C 端（终端用户）**：`/scan` 扫码充电、`/business/*` 用户侧接口 —— 车辆、收藏、优惠券、积分、发票、订单（`business_*.py`）

## 9. 车队与 V2G

| 板块 | Web 页面 | 说明 | 后端 API |
|------|----------|------|----------|
| 车队总览 | `/fleet` | 车辆、司机、充电整体视图 | `operate/` `fleet_overview.py` |
| 车辆档案 | — | 车型、VIN 白名单、车辆配置 | `fleet_vehicle_profiles.py` `enterprise_vehicles.py` `station_vin_whitelist.py` |
| 司机管理 | — | 司机档案与资质 | `fleet_drivers.py` |
| 排班考勤 | — | 车队排班与出勤 | `fleet_attendance.py` |
| 充电策略 | — | 车队专属充电时段与功率策略 | `fleet_charging_policies.py` `fleet_charging_stats.py` |
| 车队告警 | — | 车辆异常与充电异常告警 | `fleet_alerts.py` |
| 资金与充值 | — | 车队账户资金、充值记录 | `fleet_funds.py` `fleet_recharge.py` |
| 车队结算 | — | 月度结算与对账 | `fleet_settlement.py` |
| V2G 运营 | — | 车网互动放电调度与收益 | `fleet_v2g.py` `v2g.py` `operate/v2g.py` |
| 碳资产 | — | 碳减排核算与证书 | `fleet_carbon_certificates.py` `carbon_emission.py` |

## 10. 能源与虚拟电厂

| 板块 | Web 页面 | 说明 | 后端 API |
|------|----------|------|----------|
| 能源报表 | `/energy-report` | 发电、储能、充电三类能量流报表 | `energy_report.py` |
| 能源策略 | — | 峰谷套利、需量控制策略 | `energy_strategy.py` |
| 效率分析 | `/reports/generation` `/reports/efficiency` | 发电效率、充电效率 | `efficiency.py` `energy_report.py` |
| 利用率分析 | `/reports/utilization` | 设备与场站利用率 | `analytics/` |
| 虚拟电厂 | `/vpp` | 分布式资源聚合与调度 | `vpp.py` |
| 停车管理 | — | 车位、进出场、占位计费 | `parking.py` `parking_events.py` `parking_open.py` |

## 11. 平台治理

| 板块 | Web 页面 | 说明 | 后端 API |
|------|----------|------|----------|
| 用户管理 | `/users` | 账户、角色、状态、锁定 | `users.py` |
| RBAC 权限 | `/config`（权限 Tab） | 角色、权限点、数据域 | `rbac.py` `roles.py` `permissions.py` |
| 多租户 | — | 租户隔离、品牌定制、跨租户管理 | `tenant.py` `operate/tenant_brands.py` |
| 企业注册 | — | 企业入驻、审核、交易 | `enterprises.py` `enterprise_registration.py` `enterprise_transactions.py` |
| 审计日志 | `/config`（日志 Tab） | 全量操作留痕与检索 | `operation_log.py` `AuditLog` |
| 安全中心 | `/security` | 登录威胁、爆破尝试、安全基线 | `security.py` |
| API 密钥 | `/api-keys` | Key 签发、权限范围、吊销 | `api_key.py` |
| Webhooks | `/webhooks` | 出站事件订阅 | `webhooks.py` |
| SSL 证书 | `/ssl-certificates` | 证书到期监控与续期提醒 | `ssl_certificates.py` |
| 系统配置 | `/config` | 通知/日志/全局/支付/发票五个配置域 | `system_config/` |
| 备份恢复 | — | 数据库备份与恢复脚本 | `scripts/` `deploy/` |

## 12. 移动端

`mobile/` 基于 React Native（Expo），覆盖两类角色：

| 角色 | 主要能力 |
|------|----------|
| 站长 | 站点设备状态、告警处理、巡检打卡、工单接单 |
| 工程师 | 派单接收、现场处置、备件领用、知识检索 |

支持离线模式（`OFFLINE_MODE_IMPLEMENTATION.md`）与定位上报。

## 13. 设备模拟器

无真实现场设备也能跑通全链路 —— 详见 [backend/SIMULATOR_README.md](./backend/SIMULATOR_README.md)

| 协议 | 模拟对象 |
|------|----------|
| Modbus-RTU | 储能逆变器 / PCS / 电表 |
| MQTT | 直流充电桩（国标协议） |
| REST | 光伏气象站等 HTTP 设备 |
| OCPP 1.6J | 充电桩 |
| DLT645 | 多功能电能表 |
| IEC104 | 电力远动规约 RTU |

附加能力：故障注入引擎（7 类场景 + 随机模式）、批量并发（100+ 设备）。

---

## 附：技术分层速查

| 层 | 路径 | 说明 |
|----|------|------|
| 前端路由 | `frontend/src/App.tsx` | 全部页面路由定义 |
| 前端页面 | `frontend/src/pages/` | 72 个页面模块 |
| 后端路由 | `backend/app/api/v1/` | 100+ API 模块 |
| 数据模型 | `backend/app/models/` | SQLAlchemy 模型 |
| 业务逻辑 | `backend/app/services/` | 服务层 |
| 协议解析 | `backend/app/parsers/` | 多协议解析器 |
| WebSocket | `backend/app/ws/` | 实时推送 |
| 异步任务 | `backend/app/tasks/` | Celery 任务 |

---

最后更新：2026-10-24
