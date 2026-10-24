"""
API 路由初始化 - 基于光储充设备协议分析
"""
from fastapi import APIRouter, Depends
from app.api.v1 import (
    charging_queue,  # Phase41 - 充电排序队列
    chat,  # V3 - 天链助手AI对话
    fleet_drivers,  # Phase44 - 车队司机管理
    report_mgmt,
    health, auth, users, stations, devices, alarms, alarm_rules, workorders, maintenance_records,
    spare_parts,  # maint-spec §2.2 备件库存管理
    v2g,
    cache, knowledge, stats, rbac, roles, reports, gateways, teams, engineers,
    monitor, health_monitor, scan, diagnosis, smart_diagnosis,
    telemetry, fault_diagnosis, log_analysis, security, operation_log,
    alarm_notices,
    notification_configs,
    notification_rules,
    notifications,
    tenant,
    api_key,
    ssl_certificates,
    on_call,
    runbook,
    runbook_approval,
    runbook_templates,
    energy_report,
    digital_twin,
    predictive_maintenance,
    vpp,
    healing,
    ops_dashboard,
    analytics,
    tasks,
    device_library,
    device_protocols,  # admin-spec §2.4 通信协议+解析规则
    alert_workflow,  # Phase 5 - 告警闭环
    alert_webhook,    # Phase17 - Alertmanager webhook
    alert_ack,        # 卡 8d98ebe3 - 告警确认(终止升级链) POST /alerts/{id}/ack
    protocol_instances,# Phase33 - 前端协议管理页面
    inspection,       # 巡检运维管理
    pod_routes,       # Phase2 - Pod健康注册
    cross_pod,        # Phase2 - 跨Pod查询
    charging_strategy,# P7 - 充电策略引擎
    system_config,    # 系统配置
    ai_model_config_api,  # AI模型配置
    permissions,      # 权限列表/树形图
    enterprises,      # Phase42 - 企业账户管理
    pricing,          # Phase42 - 定价管理
    charging_orders,  # Phase42 - 充电订单管理
    charging_sessions,  # d018e3dc - 充电交易 ingestion(OCPP 自动建单)
    enterprise_vehicles,      # Phase43 - 车队车辆管理
    enterprise_transactions,  # Phase43 - 车队资金池交易
    fleet_overview,           # Phase43 - 车队概览
    fleet_v2g,                # Phase44 - V2G车队调度
    charging_schedule,        # Phase45 - 智能充电调度引擎
    fleet_charging_policies,  # fleet §4.3 企业充电策略
    fleet_funds,  # fleet §4.3 企业资金账户
    fleet_recharge,  # 车队充值申请
    fleet_attendance,         # fleet §4.3 司机考勤/工时
    fleet_alerts,  # fleet §4.3 车队告警规则引擎
    fleet_vehicle_profiles,  # fleet §4.3 车辆维保/保险档案
    fleet_carbon_certificates,  # fleet §4.3 碳减排核证/交易
    dashboard,        # Phase48 - 数据大屏独立展示模式
    efficiency,        # V3 - 设备效率报表
    parking,           # Phase46 - 停车折扣方案管理
    parking_events,    # 无人值守占位费自动化 (卡 f0db2036)
    parking_open,      # 停车场系统对接开放API (卡 309b4132)
    order_fees,        # 运营-订单五项费用明细+退款
    carbon_emission,   # 碳排放管理
    pricing_management,  # 定价管理 V2 - 6表CRUD
    operations_analytics,  # 运营分析6大报表
    owner_cockpit,  # 经营驾驶舱 (拥有者视角 收入/利用率/毛利/ROI)
    energy_strategy,  # P1-4 光储充能量策略 REST API
)
# P0 运营核心补齐 - 折扣/优惠券/积分/用户管理/结算对账/发票管理
from app.api.v1.operate import overview, revenue_stats, financial, orders, enterprise_recharge
from app.api.v1.operate import discount, coupon_api, points_api, users_api
from app.api.v1.operate import ops_settlement, ops_invoice, invoice_platform_config
from app.api.v1.operate import charger_qrcode
from app.api.v1.operate import v2g as v2g_ops  # 运营-V2G车网互动 (2026-10-09); alias 防遮蔽 app.api.v1.v2g
from app.api.v1.operate import pricing_templates  # 运营-费率模板 (2026-10-09)
from app.api.v1.operate import tenant_brands as ops_tenant_brands  # 运营-租户品牌(卡28546b66)
from app.api.v1 import business  # 用户端支付 prepay/notify/orders (卡280c85ee 契约§2)
from app.api.v1 import business_invoices  # 用户端开票申请 (卡a09f8a21 契约§5)
from app.api.v1 import business_orders  # 用户端充电生命周期 (卡0a080df5 契约§7)
from app.api.v1 import business_end_user_auth  # C端用户体系 (卡d95dafd3 契约§8)
from app.api.v1 import business_end_user_vehicles  # C端车辆管理 (卡36396f29 契约§8.6)
from app.api.v1 import business_end_user_favorites  # C端收藏场站 (卡36396f29 契约§8.7)
from app.api.v1 import business_end_user_charging  # C端充电订单 start-by-sn/pay/complete (卡089b01b2 契约§7)
from app.api.v1 import business_end_user_coupons  # C端优惠券 list/claim (卡089b01b2)
from app.api.v1 import business_end_user_points  # C端积分 (卡089b01b2)
from app.api.v1 import business_end_user_branding  # C端品牌 公开 (卡089b01b2 契约§1)
from app.api.v1.operate import ops_merchants  # 运营-特约商户进件 (卡280c85ee 契约§3)
from app.api.v1.operate import ops_platform_fee  # 运营-平台服务费预留 (卡280c85ee 契约§4)
from app.api.v1.operate import ops_invoice_request  # 运营-手动开票 (卡a09f8a21 契约§5.4)
from app.api.v1.operate import interconnect as ops_interconnect  # 运营-互联互通(迁移自admin)
from app.api.v1.operate import supervision as ops_supervision    # 运营-市政监管(迁移自admin)
from app.api.v1.operate import fleet_grants as ops_fleet_grants  # 运营-车队三级授权(卡a1468299)
# 运营分析已在主导入中
from app.api.v1 import fleet_settlement  # Phase45 车队对账结算
from app.api.v1 import fleet_charging_stats  # 车队充电统计
from app.api.v1 import platform_monitor  # 平台监控-拓扑+设备接入统计
from app.api.v1 import admin_interconnect, admin_supervision  # 管理后台-外部系统对接
from app.api.v1 import admin_terminals, admin_cloud  # 管理后台-物联网接入(终端+云服务)
from app.api.v1 import admin_edge_gateways  # 管理后台-边缘网关SN台账(任务卡 e940c9f4)
from app.api.v1 import webhooks  # SPEC §2.6 - 出站Webhook管理
from app.api.v1 import station_vin_whitelist  # 场站VIN白名单
from app.api.v1 import enterprise_registration  # 企业注册+审批 (卡 c8f7be6f)
from app.api.v1 import admin_data_ops  # 数据导出/备份 (卡 922b2fba)
from app.api.v1 import station_maintenance_grants  # 运维分离架构 (卡 00d7d49a)
from app.api.gateway import api_gateway  # Phase11 开放API网关 (卡片 ba9d3461 挂载)

from app.api.v1.auth import enforce_auth

# 全局认证强制：所有 /api/v1/* 端点默认要求 Bearer token；白名单（健康检查 /
# 扫码报修 / 遥测上报 / Pod 矩阵 / 跨Pod查询 / Alertmanager 回调 / 认证公开端点）
# 在 enforce_auth 内部豁免，详见 app.api.v1.auth.is_public_path。
api_router = APIRouter(dependencies=[Depends(enforce_auth)])

# 健康检查
api_router.include_router(health.router, tags=["健康检查"])

# 扫码报修
api_router.include_router(scan.router, prefix="/scan", tags=["扫码报修"])

# ========== 遥测数据采集（基于协议分析）==========
api_router.include_router(telemetry.router, prefix="/telemetry", tags=["遥测数据"])

# ========== 故障码诊断（基于协议分析）==========
api_router.include_router(fault_diagnosis.router, prefix="/fault-diagnosis", tags=["故障码诊断"])

# 智能诊断（设备健康）
api_router.include_router(diagnosis.router, prefix="/diagnosis", tags=["智能诊断"])

# 智能诊断（故障关键词）
api_router.include_router(smart_diagnosis.router, prefix="/smart-diagnosis", tags=["智能故障诊断"])

# 报表导出
api_router.include_router(reports.router, prefix="/reports", tags=["报表导出"])

# 认证
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(enterprise_registration.router, prefix="/auth", tags=["企业注册"])

# 用户
api_router.include_router(users.router, prefix="/users", tags=["用户"])

# 数据导出/备份 (卡 922b2fba)
api_router.include_router(admin_data_ops.router, prefix="/admin-data", tags=["数据导出备份"])

# 运维分离架构 (卡 00d7d49a): 场站运维授权 + 运维视角被授权站点。
# 注意: 必须在 stations.router (含 /stations/{station_id} 通配) 之前注册,
# 否则 GET /stations/maintained 会被 {station_id} 吞掉 → 422。
api_router.include_router(station_maintenance_grants.router, tags=["运维授权"])

# 站点
api_router.include_router(stations.router, prefix="/stations", tags=["站点"])
api_router.include_router(station_vin_whitelist.router, prefix="/stations", tags=["场站VIN白名单"])

# 设备
api_router.include_router(devices.router, prefix="/devices", tags=["设备"])
# V2G 调度（挂载到 devices 路由下）
api_router.include_router(v2g.router, prefix="/devices", tags=["V2G调度"])

# 告警
api_router.include_router(alarms.router, prefix="/alarms", tags=["告警"])
# 告警规则配置 (SPEC 第7章 - 独立端点)
api_router.include_router(alarm_rules.router, prefix="/alarm-rules", tags=["告警规则"])

# 工单
api_router.include_router(workorders.router, prefix="/work-orders", tags=["工单"])
api_router.include_router(spare_parts.router, prefix="/spare-parts", tags=["备件库存管理"])

# 设备维护记录
api_router.include_router(maintenance_records.router, prefix="/maintenance-records", tags=["设备维护记录"])

# 知识库
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["知识库"])

# 统计
api_router.include_router(stats.router, prefix="/stats", tags=["统计"])

# 权限管理
api_router.include_router(rbac.router, prefix="/rbac", tags=["权限管理"])

# 权限列表/树形图 (GET /api/v1/permissions)
api_router.include_router(permissions.router, prefix="/permissions", tags=["权限管理"])

# 角色管理（团队级，供 /teams/roles 使用）
api_router.include_router(roles.router, prefix="/roles", tags=["角色管理"])

# 实时监控
api_router.include_router(monitor.router, prefix="/monitor", tags=["实时监控"])

# 健康度监控
api_router.include_router(health_monitor.router, prefix="/health", tags=["健康度监控"])

# 团队管理
api_router.include_router(teams.router, prefix="/teams", tags=["团队管理"])

# 工程师管理（独立于团队管理）
api_router.include_router(engineers.router, prefix="/engineers", tags=["工程师管理"])

# 网关管理
api_router.include_router(gateways.router, prefix="/gateways", tags=["网关管理"])
# 协议实例管理 (Phase33)
api_router.include_router(protocol_instances.router, prefix="", tags=["协议实例管理"])
# WebSocket已迁移到统一模块 app/ws/ (前缀: /ws/v1/)

# AI智能日志分析
api_router.include_router(log_analysis.router, prefix="/log-analysis", tags=["AI日志分析"])

# 多租户管理
api_router.include_router(tenant.router, prefix="/tenants", tags=["多租户管理"])

# API 密钥管理
api_router.include_router(api_key.router, tags=["API密钥管理"])

# 安全管理
api_router.include_router(security.router, prefix="/security", tags=["安全管理"])

# 操作日志
api_router.include_router(operation_log.router, prefix="/operation-log", tags=["操作日志"])

# 告警通知
api_router.include_router(alarm_notices.router, prefix="/alarm-notices", tags=["告警通知"])

# 通知配置 (SMS/邮件/APP开关)
api_router.include_router(notification_configs.router, prefix="/notification-configs", tags=["通知配置"])

# 通知规则配置
api_router.include_router(notification_rules.router, prefix="/notification-rules", tags=["通知规则"])

# 通知发送
api_router.include_router(notifications.router, prefix="/notifications", tags=["通知发送"])
# 站内消息中心收件箱 (admin-platform-spec §2.8) — 用户自服务, 独立 router 不继承写权限守卫
api_router.include_router(notifications.inbox_router, prefix="/notifications", tags=["站内消息"])

# SSL证书管理 (Phase9)
api_router.include_router(ssl_certificates.router, prefix="/ssl", tags=["SSL证书管理"])

# 值班排班管理 (Phase9 #52)
api_router.include_router(on_call.router, prefix="/on-call", tags=["值班排班管理"])

# Runbook自动化执行 (Phase9 #53)
api_router.include_router(runbook.router, prefix="/runbook", tags=["Runbook自动化"])

# Runbook审批流 (Phase11 #58)
api_router.include_router(runbook_approval.router, prefix="/runbook/approvals", tags=["Runbook审批流"])

# Runbook模板CRUD (spec maint-platform §2.6, 硬编码→DB持久化)
api_router.include_router(runbook_templates.router, prefix="/runbooks", tags=["Runbook模板"])

# 能耗分析报表 (Phase9 #54)
api_router.include_router(energy_report.router, prefix="/energy", tags=["能耗分析报表"])

# 光储充能量策略 (P1-4) — 策略配置/购电价模板/调度计划/能量流水
api_router.include_router(energy_strategy.router, prefix="/energy-strategy", tags=["能量策略"])

# 数字孪生可视化 (Phase10 #55)
api_router.include_router(digital_twin.router, prefix="/digital-twin", tags=["数字孪生可视化"])

# 预测性维护AI模型 (Phase10 #56)
api_router.include_router(predictive_maintenance.router, prefix="/predictive-maintenance", tags=["预测性维护"])

# 虚拟电厂(VPP)调度优化 - 多站点协同+电网互动响应 (Phase10 #57)
api_router.include_router(vpp.router, prefix="/vpp", tags=["虚拟电厂VPP"])
api_router.include_router(report_mgmt.router, prefix="/report-mgmt", tags=["报告管理"])

# 告警自愈引擎 (Phase11)
api_router.include_router(healing.router, prefix="/healing", tags=["告警自愈引擎"])

# 运维大屏可视化 (Phase11 #59)
api_router.include_router(ops_dashboard.router, tags=["运维大屏可视化"])

# 运维数据分析与预测 (任务#64)
api_router.include_router(analytics.router, prefix="/analytics", tags=["运维数据分析与预测"])
api_router.include_router(inspection.router, prefix="/inspection", tags=["巡检运维管理"])

# 设备库管理 (admin-platform-spec §2.4)
api_router.include_router(device_library.router, prefix="/device-library", tags=["设备库管理"])
# 通信协议 + 协议解析规则 (admin-platform-spec §2.4)
api_router.include_router(device_protocols.router, prefix="/device-protocols", tags=["设备协议管理"])
api_router.include_router(device_protocols.rules_router, prefix="/protocol-rules", tags=["协议解析规则"])

# Celery异步任务管理 (Phase4)
api_router.include_router(tasks.router, prefix="/tasks", tags=["异步任务管理"])

# 监控告警闭环 (Phase5)
api_router.include_router(alert_workflow.router, prefix="/alert-workflow", tags=["监控告警闭环"])

# Alertmanager Webhook (Phase17)
api_router.include_router(alert_webhook.router, tags=["告警Webhook"])

# 告警确认 (终止升级链, 卡 8d98ebe3): POST /alerts/{alarm_id}/ack
api_router.include_router(alert_ack.router, prefix="/alerts", tags=["告警确认(升级链)"])

# Pod管理 (Phase2 - 矩阵路由层)
api_router.include_router(pod_routes.router, tags=["Pod管理"])

# 跨Pod查询 (Phase2 - 矩阵路由层)
api_router.include_router(cross_pod.router, tags=["跨Pod查询"])

# 充电策略引擎 (P7) — 5种模式 + 光伏预测 + 储能调度
api_router.include_router(charging_strategy.router, prefix="/charging", tags=["充电策略引擎"])

# 系统配置
api_router.include_router(system_config.router, prefix="/system-config", tags=["系统配置"])

# Phase42 - 运营管理 API
api_router.include_router(enterprises.router, prefix="", tags=["企业账户管理"])
# 车队板块别名：同一 router 在 /fleet 前缀下再挂载一次，使前端 /fleet/enterprises* 可用（原 /enterprises* 不变）
api_router.include_router(enterprises.router, prefix="/fleet", tags=["车队企业管理"])
api_router.include_router(pricing.router, prefix="", tags=["定价管理"])
api_router.include_router(charging_orders.router, prefix="", tags=["充电订单管理"])
api_router.include_router(charging_sessions.router, prefix="", tags=["充电交易接收(OCPP ingestion)"])

# Phase43 - 车队管理
api_router.include_router(enterprise_vehicles.router, prefix="/enterprises/{enterprise_id}/vehicles", tags=["车队车辆管理"])
api_router.include_router(enterprise_transactions.router, prefix="/enterprises/{enterprise_id}/transactions", tags=["车队资金池交易"])
api_router.include_router(fleet_overview.router, prefix="/fleet", tags=["车队概览"])
# Phase41 - 充电排序队列
api_router.include_router(charging_queue.router, prefix="/fleet", tags=["充电排序队列"])

# Phase44 - 车队司机管理
api_router.include_router(fleet_drivers.router, prefix="/fleet/drivers", tags=["车队司机管理"])

# 碳排放管理
api_router.include_router(carbon_emission.router, prefix="/fleet", tags=["碳排放管理"])

# Phase44 - V2G车队调度计划+收益管理
api_router.include_router(fleet_v2g.router, prefix="/fleet", tags=["V2G车队调度"])

# Phase45 - 智能充电调度引擎 (有序充电+负荷均衡)
api_router.include_router(charging_schedule.router, prefix="/fleet", tags=["智能充电调度"])

# 企业充电策略(限额/时段/站点白名单)
api_router.include_router(fleet_charging_policies.router, prefix="/fleet/policies", tags=["企业充电策略"])

# 企业资金账户(对齐前端 Fleet FundAccount 契约)
api_router.include_router(fleet_funds.router, prefix="/fleet/funds", tags=["车队资金账户"])
api_router.include_router(fleet_recharge.router, prefix="/fleet/recharge", tags=["车队充值"])

# 司机考勤/工时(批量录入+月度汇总+出勤率)
api_router.include_router(fleet_attendance.router, prefix="/fleet/attendance", tags=["司机考勤工时"])

# fleet §4.3 车队告警规则引擎 (低电量/异常充电/超时未离桩)
api_router.include_router(fleet_alerts.router, prefix="/fleet", tags=["车队告警规则引擎"])

# fleet §4.3 车辆维保/保险档案 (维修记录+保险管理+聚合档案)
api_router.include_router(fleet_vehicle_profiles.router, prefix="/fleet", tags=["车辆维保保险档案"])

# fleet §4.3 碳减排核证/交易 (申请->核证->交易登记, 状态机约束)
api_router.include_router(fleet_carbon_certificates.router, prefix="/fleet", tags=["碳核证/交易"])

# Phase48 - 数据大屏独立展示模式
api_router.include_router(dashboard.router, tags=["数据大屏"])

# V3 - 设备效率报表 (GET /reports/utilization|efficiency|generation)
api_router.include_router(efficiency.router, prefix="/reports", tags=["效率报表"])

# Phase46 - 停车折扣方案管理 (商户站点)
api_router.include_router(parking.router, prefix="", tags=["停车管理"])

# 无人值守占位费自动化 (卡 f0db2036): 外部车牌识别系统占位事件接入
api_router.include_router(parking_events.router, prefix="", tags=["占位费"])

# 停车场系统对接开放API (卡 309b4132): 独立鉴权(X-App-Key/X-App-Secret), /open/parking 白名单豁免 user JWT
api_router.include_router(parking_open.router, prefix="", tags=["停车对接开放API"])

# AI模型配置管理
api_router.include_router(ai_model_config_api.router, tags=["AI模型配置"])

# V3 - 天链助手AI对话（通用对话/语音配置）
api_router.include_router(chat.router, prefix="", tags=["天链助手"])

# 订单费用明细+退款
api_router.include_router(order_fees.router, tags=["订单费用管理"])

# 定价管理 V2 - 6表CRUD + 费用估算
api_router.include_router(pricing_management.router, tags=["定价管理V2"])

# 缓存统计
api_router.include_router(cache.router, prefix="/cache", tags=["缓存"])

# ========== 运营管理 - 统一 /operate 前缀 ==========
api_router.include_router(overview.router, prefix="/operate", tags=["运营概览"])
api_router.include_router(v2g_ops.router, prefix="/operate/v2g", tags=["V2G运营"])
api_router.include_router(pricing_templates.router, prefix="/operate/pricing-templates", tags=["费率模板"])
api_router.include_router(revenue_stats.router, prefix="/operate", tags=["营收统计"])
api_router.include_router(financial.router, prefix="/operate", tags=["财务管理"])
api_router.include_router(orders.router, prefix="/operate", tags=["订单管理"])
api_router.include_router(enterprise_recharge.router, prefix="/operate", tags=["企业充值"])
# P0 运营核心补齐 - 折扣/优惠券/积分/用户管理
api_router.include_router(discount.router, prefix="/operate", tags=["折扣管理"])
api_router.include_router(coupon_api.router, prefix="/operate", tags=["优惠券管理"])
api_router.include_router(points_api.router, prefix="/operate", tags=["积分管理"])
api_router.include_router(users_api.router, prefix="/operate", tags=["用户类型管理"])

# 运营结算对账 + 发票管理
api_router.include_router(ops_settlement.router, prefix="/operate", tags=["运营-结算对账"])
api_router.include_router(ops_invoice.router, prefix="/operate", tags=["运营-发票管理"])
api_router.include_router(invoice_platform_config.router, prefix="/operate", tags=["运营-开票平台配置"])
api_router.include_router(charger_qrcode.router, prefix="/operate", tags=["运营-充电桩二维码"])
# 运营-租户品牌 CRUD (团队级, 卡 28546b66 契约§1 品牌录入)
api_router.include_router(ops_tenant_brands.router, prefix="/operate", tags=["运营-租户品牌"])

# 用户端IM-B支付 + 运营特约商户进件 + 平台服务费 (卡 280c85ee 契约 §2/§3/§4)
api_router.include_router(business.router, prefix="/business", tags=["用户端IM-B支付"])
# 用户端开票申请 (卡a09f8a21 契约§5): 申请/列表/详情/补发邮箱 + 签名文件下载(白名单免登录)
api_router.include_router(business_invoices.router, prefix="/business", tags=["用户端开票申请"])
# C端场站入口 (卡 5300ccc2 契约 §1): 只读鉴权 + branding, 独立于管理侧 /stations
api_router.include_router(business.stations_router, prefix="/business", tags=["用户端场站（C端）"])
# 用户端充电生命周期 (卡 0a080df5 契约 §7): 创建/停止/状态/列表/取消订单;
# GET /business/orders/{order_id} 完整明细(?detail=full) 复用 business.router 同路径端点。
api_router.include_router(business_orders.router, prefix="/business", tags=["用户端充电生命周期"])
api_router.include_router(business_end_user_auth.router, prefix="/business", tags=["C端用户体系"])
api_router.include_router(business_end_user_vehicles.router, prefix="/business", tags=["C端车辆管理"])
api_router.include_router(business_end_user_favorites.router, prefix="/business", tags=["C端收藏场站"])
# C端端侧路径 (卡089b01b2): 无 /business 前缀, 端侧 BASE_URL=/api/v1 直连。
# 鉴权: get_current_end_user (aud=end_user); enforce_auth 经 _END_USER_PATH_PREFIXES 放行,
# 端点级依赖校验 aud, 运营 token→401。复用 business_orders/business 的 impl, 不重复造逻辑。
api_router.include_router(business_end_user_charging.router, prefix="", tags=["C端充电订单"])
api_router.include_router(business_end_user_coupons.router, prefix="", tags=["C端优惠券"])
api_router.include_router(business_end_user_points.router, prefix="", tags=["C端积分"])
# branding 公开 (is_public_path 后缀特判放行), 无需 C端 token
api_router.include_router(business_end_user_branding.router, prefix="", tags=["C端品牌"])
api_router.include_router(ops_merchants.router, prefix="/ops", tags=["运营-特约商户进件"])
api_router.include_router(ops_platform_fee.router, prefix="/ops", tags=["运营-平台服务费"])
# 运营手动开票 (卡a09f8a21 契约§5.4): 申请列表 + 上传发票 + 拒绝
api_router.include_router(ops_invoice_request.router, prefix="/ops", tags=["运营-手动开票"])

# Phase45 车队对账结算
api_router.include_router(fleet_settlement.router, prefix="/fleet/settlement", tags=["车队对账结算"])

# 车队充电统计（单车+汇总）
api_router.include_router(fleet_charging_stats.router, tags=["车队充电统计"])

# ========== 运营分析6大报表 ==========
api_router.include_router(operations_analytics.router, tags=["运营分析"])

# ========== 运营 - 互联互通 + 市政监管 (迁移自 admin, 按运营团队隔离) ==========
api_router.include_router(ops_interconnect.router, prefix="/operate", tags=["运营-互联互通"])
api_router.include_router(ops_supervision.router, prefix="/operate", tags=["运营-市政监管"])
# 车队三级授权 公司→场站→设备(桩级白名单) + 充电启动 scope 校验 (卡 a1468299)
api_router.include_router(ops_fleet_grants.router, prefix="/operate", tags=["运营-车队三级授权"])

# ========== 管理后台 - 外部系统对接 (已迁移至 /operate, 旧路径保留兼容别名) ==========
# 兼容别名: /admin/interconnect/* → /operate/interconnect/* (下个版本移除)
api_router.include_router(admin_interconnect.router, prefix="/admin/interconnect", tags=["管理后台-互联互通(兼容)"])
api_router.include_router(admin_supervision.router, prefix="/admin/supervision", tags=["管理后台-市政监管(兼容)"])

# ========== 管理后台 - 物联网接入 (终端管理 + 云服务配置) ==========
api_router.include_router(admin_terminals.router, prefix="/admin/terminals", tags=["管理后台-终端管理"])
api_router.include_router(admin_cloud.router, prefix="/admin/cloud-configs", tags=["管理后台-云服务配置"])
# 边缘网关 SN 平台台账 (任务卡 e940c9f4): router 自带 /admin/edge-gateways 前缀
api_router.include_router(admin_edge_gateways.router, tags=["管理后台-边缘网关SN台账"])
api_router.include_router(enterprise_registration.admin_router, prefix="/admin/registrations", tags=["企业注册审批"])

# ========== SPEC §2.6 - 出站 Webhook 管理 ==========
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhook管理"])

# ========== Phase11 开放API网关 (卡片 ba9d3461): /api/v1/gateway/* ==========
api_router.include_router(api_gateway.router, tags=["API网关"])

# ========== 平台监控扩展 ==========
api_router.include_router(platform_monitor.router, tags=["平台监控"])

# ========== 经营驾驶舱 (拥有者视角: 收入/利用率/毛利/ROI 聚合) ==========
api_router.include_router(owner_cockpit.router, tags=["经营驾驶舱"])
