"""
天链 V3 模型初始化 - 基于光储充设备协议分析
"""
from app.models.user import User, Team
from app.models.sms_verification import SmsVerificationCode
from app.models.station import Station
from app.models.device import Device, DeviceHealthRecord, DeviceType, DeviceStatus, ProtocolType
from app.models.device_config import DeviceConfig, ChargeMode
from app.models.workorder import WorkOrder, WorkOrderLog, WorkOrderCheckin, WorkOrderSupportRequest, WorkOrderSparePart, WorkOrderRating
from app.models.spare_part import SparePartInventory
from app.models.alarm import Alarm, AlarmRule, AlarmRuleLog, AlarmLevel, AlarmStatus
from app.models.alarm_notification import AlarmNotification
from app.models.telemetry import Telemetry
from app.models.telemetry_v2 import TelemetryPV, TelemetryBattery, TelemetryCharger, TelemetryTableType, DEVICE_TYPE_TABLE_MAP, get_telemetry_model_by_device_type
from app.models.pre_aggregation import StationHourlyStats, DeviceDailyStats, aggregate_station_hourly
from app.models.fault_code import FaultCode, FaultLevel, FaultCategory, DiagnosisRule, RepairGuide
from app.models.knowledge import KnowledgeArticle, KnowledgeCategory
from app.models.gateway import Gateway, GatewaySN, Firmware, UpgradeTask
# 设备级固件升级任务 (卡 43b26421): 与网关级 UpgradeTask 正交
from app.models.device_upgrade_task import DeviceUpgradeTask
from app.models.device_qrcode import DeviceQRCode
from app.models.code_sequence import CodeSequence
from app.models.audit_log import AuditLog
from app.models.notification_rule import NotificationRule
from app.models.notification_config import NotificationConfig, NotificationTemplate, NotificationLog
# admin-platform-spec §2.8 站内消息中心 (收件箱/已读未读)
from app.models.notification import Notification
# 通知渠道凭证配置 (卡 8d98ebe3): 团队级真实发送渠道凭证, 与 NotificationConfig 正交
from app.models.channel_config import ChannelConfig, ChannelType
from app.models.ai_diagnosis import AIDiagnosisRecord, DiagnosisStatus
# 天链智能体 P1 记忆 (设计文档 §5.2): 巡检发现/诊断结论/经验积累 + 对话历史
from app.models.agent_memory import AgentMemory, AgentConversation
from app.models.ssl_certificate import SSLCertificate
from app.models.digital_twin import DigitalTwinModel, DigitalTwinScene, DigitalTwinDataPoint
from app.models.healing_rule import HealingRule
from app.models.healing_execution import HealingExecution
from app.models.runbook_execution import RunbookExecutionRecord
from app.models.runbook_approval import RunbookApproval, RunbookApprovalLog
from app.models.runbook import RunbookTemplateModel, seed_builtin_runbook_templates
from app.models.inspection import InspectionTask, InspectionPlan, TaskStatus, PlanStatus, PlanCycle, PlanTarget
from app.models.inspection import InspectionTemplate, InspectionResult
from app.models.analytics import AnalyticsResult, MLModel, PredictionAlert, DeviceHealthHistory
from app.models.rbac import RoleTable, PermissionTable, role_permission_table, user_role_table, seed_roles_and_permissions
from app.models.on_call import OnCallRule, OnCallShift, OnCallLog
from app.models.tenant import Tenant, TenantConfig, TenantAuditLog
from app.models.tenant_usage import TenantUsage
from app.models.tenant_brand import TenantBrand
from app.models.password_reset_request import PasswordResetRequest
# IM-B服务商模式 (卡 280c85ee 契约 §2/§3/§4)
from app.models.merchant import Merchant, MerchantType, ApplymentState, MerchantStatus
from app.models.payment_order import PaymentOrder, PaymentStatus, PayScene
from app.models.end_user import EndUser, EndUserStatus, EndUserType
from app.models.end_user_device_token import EndUserDeviceToken
from app.models.end_user_vehicle import EndUserVehicle
from app.models.end_user_favorite import EndUserFavorite
from app.models.platform_fee_config import PlatformFeeConfig, FeeScope
from app.models.enterprise import Enterprise, EnterpriseStatus, enterprise_stations
# 车队三级授权 公司→场站→设备(桩级白名单) (卡 a1468299)
from app.models.enterprise_device_grant import EnterpriseDeviceGrant
from app.models.enterprise_vehicle import (
    EnterpriseVehicle, EnterpriseVehicleStatus,
    ApprovalStatus, StationVinWhitelist,
)
# 车队管理 - 车辆表 vehicles (注册到 __init__ 以对齐 env.py autogenerate 与 baseline 加载路径, 卡 8c8483c1)
from app.models.vehicle import Vehicle, VehicleStatus
# 企业充值申请 enterprise_recharge_applications (同上)
from app.models.enterprise_recharge import RechargeApplication, RechargeStatus
# 车队充值申请 fleet_recharge_requests (卡 4144ef1b)。枚举与 enterprise_recharge 的
# RechargeStatus 同名，故别名导出避免覆盖上方既有导出。
from app.models.fleet_recharge import FleetRechargeRequest
from app.models.fleet_recharge import RechargeStatus as FleetRechargeStatus
from app.models.enterprise_transaction import EnterpriseTransaction, TransactionType
from app.models.fund_pool import (
    FundPool, FundPoolTransaction,
    FundAccountStatus, FundAccountType,
    FundTransactionType, FundTransactionStatus,
)
from app.models.fleet_driver import (
    FleetDriver, FleetDriverAccount, FleetDriverTransaction,
    DriverStatus, LicenseType, AccountStatus, DriverTransactionType,
)
# 注: PeriodType/UserType/FeeType 包级导出以 pricing_v2 版为准(Phase42),
# pricing_rule/charging_order/order_fee_item 的同名枚举请从各自模块导入
from app.models.pricing_rule import PricingRule
from app.models.charging_order import ChargingOrder, OrderPaymentStatus, OrderStatus, PaymentMethod
from app.models.order_fee_item import OrderFeeItem, RefundRecord, RefundStatus
from app.models.api_key import ApiKey, ApiKeyUsageLog, ClientCertificate
from app.models.maintenance_record import MaintenanceRecord, MaintenanceType, MaintenanceStatus
from app.models.api_gateway import ApiClient, GatewayApiKey, ApiEndpoint, ApiRequestLog, OAuthAuthorizationCode, RateLimitRule, ApiUsageQuota, ThirdPartyIntegration
from app.models.device_control_log import DeviceControlLog
from app.models.device_efficiency_log import DeviceEfficiencyLog
from app.models.v2g_dispatch import V2GDispatchLog
from app.models.fleet_v2g import FleetV2GPlan, FleetV2GRevenue, V2GPlanStatus
from app.models.fleet_alert_rule import (
    FleetAlertRule, FleetAlertRecord, AlertRuleType, AlertRecordStatus,
)
from app.models.parking import ParkingDiscount
# 无人值守占位费自动化 (卡 f0db2036): OccupancyEvent 记录车位占用 + 占位费状态
from app.models.parking_event import (
    OccupancyEvent, OccupancyEventSource, OccupancyFeeStatus,
)
# 停车场系统对接开放API (卡 309b4132): 集成凭证 + 减免留痕
from app.models.parking_integration import ParkingIntegrationConfig, IntegrationMode
from app.models.parking_discount_applied import ParkingDiscountApplied
from app.models.charging_queue import ChargingQueue, ChargingQueueRule, ChargingQueueStatus
# Phase45 智能充电调度引擎
from app.models.charging_schedule import (
    ChargingSchedulePlan, ChargingScheduleEntry, ChargingScheduleRule,
    ChargingSchedulePlanStatus, ChargingScheduleRuleType,
    ChargingEntryMode, ChargingPeriodType,
)
# fleet-platform-spec §4.3 企业充电策略(限额/时段/站点白名单)
from app.models.fleet_charging_policy import FleetChargingPolicy
# fleet-platform-spec §4.3 车辆维保/保险档案
from app.models.fleet_vehicle_profile import (
    FleetVehicleMaintenance, FleetVehicleInsurance,
    VehicleMaintenanceType, VehicleMaintenanceStatus, VehicleInsuranceType,
)
# fleet-platform-spec §4.3 司机考勤/工时
from app.models.fleet_driver_attendance import FleetDriverAttendance
# P0 运营核心补齐
from app.models.price_discount import PriceDiscount, DiscountGroup, DiscountType
from app.models.coupon import Coupon, CouponBatch, CouponUsage, CouponType, CouponStatus
from app.models.points import PointsRule, PointsRecord, PointsRuleType, PointsRecordType
# 碳排放管理
from app.models.carbon_emission import (
    CarbonEmissionFactor, CarbonReductionRecord, CarbonReductionSummary,
)
# fleet-platform-spec §4.3 碳减排核证/交易
from app.models.fleet_carbon_certificate import (
    FleetCarbonCertificate, CertificateStatus,
)
# Phase42 定价管理 V2 (运营管理) — 包级 PeriodType/UserType/FeeType 以此处为准
from app.models.pricing_v2 import (
    TimeSlotDefinition, PeriodType,
    EnergyPrice,
    ServiceFeePrice,
    ParkingPrice,
    OccupancyFeePrice,
    ReservationFeePrice,
    UserType, FeeType, ReservationPolicy
)
# Phase45 车队对账结算
from app.models.settlement import (
    FleetSettlementBill, BillStatus,
    FleetSettlementDetail,
    FleetInvoiceRequest, InvoiceStatus,
)

# 运营结算对账 + 发票管理
from app.models.ops_settlement import (
    DailySettlement, SettlementStatus,
    PaymentReconciliation, ReconciliationStatus,
    InterconnectSettlement, InterconnectSettlementStatus,
    InvoiceTitle, TitleType,
    OpsInvoice, OpsInvoiceStatus, OpsInvoiceType,
)
# 管理后台 - 外部系统对接(互联互通 + 市政监管)
from app.models.admin_interconnect import (
    InterconnectConfig, InterconnectOrder,
)
from app.models.admin_supervision import (
    MunicipalSupervisionConfig, RegulatoryReport, ComplianceCheck,
)
# 管理后台 - 物联网接入(终端管理 + 云服务配置)
from app.models.admin_terminals import (
    Terminal, CloudConfig,
)
from app.models.webhook import (
    Webhook, WebhookDelivery,
    WEBHOOK_EVENT_TYPES, DELIVERY_STATUS,
)
# SPEC §4 缺口补齐 - 用户类型/优惠/分析/订单
from app.models.spec_tables import (
    AppUser, CardUser, VinUser,
    InterconnectPlatform, InterconnectUser,
    EnterpriseAccount, EnterpriseSubUser, BillingCycle,
    CouponActivityStat,
    OrderChargeCurve,
    RevenueDaily, StationDailyMetric,
)
# admin-platform-spec §2.4 - 物联网接入(设备型号库 + 通信协议 + 协议解析规则)
from app.models.device_library import DeviceLibrary
from app.models.device_protocols import DeviceProtocol, ProtocolRule
# admin-platform-spec §2.7 - 安全管理(安全策略) + system_configs ORM 占位
from app.models.security_policy import SecurityPolicy, default_security_policies, seed_security_policies
from app.models.system_config import SystemConfig
# P1-1 光储充能量策略 (卡片 469f03ac) — PeriodType 复用 pricing_v2
from app.models.energy_strategy import (
    EnergyPriceTemplate, EnergyPricePeriod, EnergyPriceSpot,
    StationEnergyStrategy, EnergyDispatchPlan, EnergyFlowLog,
)
# 企业注册申请 + 主体 (卡 c8f7be6f): 注册审批 → approve 建 Subject + Team + admin User
from app.models.subject import Subject
from app.models.registration import (
    RegistrationApplication, ApplyScope, RegistrationStatus,
)
# 手动开票申请 (卡 a09f8a21 契约 §5): C端用户申请 → 运营上传发票/拒绝
from app.models.invoice_request import (
    InvoiceRequest, InvoiceRequestStatus, InvoiceMode,
    InvoiceTitleType, InvoiceFileType,
)
# 边缘网关 SN 平台台账 (任务卡 e940c9f4): SN 入库/出库/绑定/在线/退役生命周期
from app.models.edge_gateway import (
    EdgeGateway,
    EDGE_GATEWAY_STATUS_INVENTORY, EDGE_GATEWAY_STATUS_SHIPPED,
    EDGE_GATEWAY_STATUS_BOUND, EDGE_GATEWAY_STATUS_ONLINE,
    EDGE_GATEWAY_STATUS_DECOMMISSIONED, EDGE_GATEWAY_STATUS_VALUES,
)
# 运维分离架构 (卡 00d7d49a): 运营公司 → 第三方运维团队 场站级运维授权
from app.models.station_maintenance_grant import (
    StationMaintenanceGrant, GrantScope, GrantStatus, SCOPE_ALLOWED_ACTIONS,
)

__all__ = [
    "User", "Team",
    "SmsVerificationCode",
    "Station",
    "Device", "DeviceHealthRecord", "DeviceType", "DeviceStatus", "ProtocolType",
    "DeviceConfig", "ChargeMode",
    "DeviceQRCode",
    "Telemetry",
    # Phase1 新增遥测专表
    "TelemetryPV", "TelemetryBattery", "TelemetryCharger",
    "TelemetryTableType", "DEVICE_TYPE_TABLE_MAP", "get_telemetry_model_by_device_type",
    # Phase1 新增预聚合模型
    "StationHourlyStats", "DeviceDailyStats", "aggregate_station_hourly",
    "FaultCode", "FaultLevel", "FaultCategory", "DiagnosisRule", "RepairGuide",
    "WorkOrder", "WorkOrderLog", "SparePartInventory",
    "Alarm", "AlarmRule", "AlarmRuleLog", "AlarmLevel", "AlarmStatus",
    "AlarmNotification",
    "KnowledgeArticle", "KnowledgeCategory",
    "Gateway", "GatewaySN", "Firmware", "UpgradeTask",
    "AIDiagnosisRecord", "DiagnosisStatus",
    "NotificationRule",
    "NotificationConfig", "NotificationTemplate", "NotificationLog",
    "Notification",
    "ChannelConfig", "ChannelType",
    "SSLCertificate",
    "DigitalTwinModel", "DigitalTwinScene", "DigitalTwinDataPoint",
    "HealingRule", "HealingExecution",
    "RunbookExecutionRecord",
    "RunbookApproval", "RunbookApprovalLog",
    "RunbookTemplateModel", "seed_builtin_runbook_templates",
    "AnalyticsResult", "MLModel", "PredictionAlert", "DeviceHealthHistory",
    "RoleTable", "PermissionTable",
    "InspectionTask", "InspectionPlan", "TaskStatus", "PlanStatus", "PlanCycle", "PlanTarget",
    "InspectionTemplate", "InspectionResult",
    "CodeSequence",
    "MaintenanceRecord", "MaintenanceType", "MaintenanceStatus",
    "OnCallRule", "OnCallShift", "OnCallLog",
    "Tenant", "TenantConfig", "TenantAuditLog",
    "TenantUsage",
    "TenantBrand",
    "ApiKey", "ApiKeyUsageLog", "ClientCertificate",
    "ApiClient", "GatewayApiKey", "ApiEndpoint", "ApiRequestLog",
    "OAuthAuthorizationCode", "RateLimitRule", "ApiUsageQuota", "ThirdPartyIntegration",
    "DeviceControlLog",
    # Phase41 运营+车队+计费引擎
    "Enterprise", "EnterpriseStatus", "enterprise_stations",
    "EnterpriseDeviceGrant",  # 车队三级授权 (卡 a1468299)
    "EnterpriseVehicle", "EnterpriseVehicleStatus",
    "ApprovalStatus", "StationVinWhitelist",
    "Vehicle", "VehicleStatus",
    "RechargeApplication", "RechargeStatus",
    "FleetRechargeRequest", "FleetRechargeStatus",
    "EnterpriseTransaction", "TransactionType",
    "FleetDriver", "FleetDriverAccount", "FleetDriverTransaction",
    "DriverStatus", "LicenseType", "AccountStatus", "DriverTransactionType",
    "PricingRule", "PeriodType",
    "ChargingOrder", "OrderPaymentStatus", "OrderStatus", "PaymentMethod", "UserType",
    "OrderFeeItem", "RefundRecord", "FeeType", "RefundStatus",
    "DeviceEfficiencyLog", "V2GDispatchLog",
    "FleetV2GPlan", "FleetV2GRevenue", "V2GPlanStatus",
    "FleetChargingPolicy",
    "FleetVehicleMaintenance", "FleetVehicleInsurance",
    "VehicleMaintenanceType", "VehicleMaintenanceStatus", "VehicleInsuranceType",
    "FleetDriverAttendance",
    "FleetAlertRule", "FleetAlertRecord", "AlertRuleType", "AlertRecordStatus",
    "ParkingDiscount",
    # 停车场系统对接开放API (卡 309b4132)
    "ParkingIntegrationConfig", "IntegrationMode",
    "ParkingDiscountApplied",
    # P0 运营核心补齐
    "PriceDiscount", "DiscountGroup", "DiscountType",
    "Coupon", "CouponBatch", "CouponUsage", "CouponType", "CouponStatus",
    "PointsRule", "PointsRecord", "PointsRuleType", "PointsRecordType",
    # Phase45 车队对账结算
    "FleetSettlementBill", "BillStatus",
    "FleetSettlementDetail",
    "FleetInvoiceRequest", "InvoiceStatus",
    # 碳排放管理
    "CarbonEmissionFactor", "CarbonReductionRecord", "CarbonReductionSummary",
    # 碳减排核证/交易
    "FleetCarbonCertificate", "CertificateStatus",
    # 管理后台 - 外部系统对接
    "InterconnectConfig", "InterconnectOrder",
    "MunicipalSupervisionConfig", "RegulatoryReport", "ComplianceCheck",
    "Terminal", "CloudConfig",
    # SPEC §4 缺口补齐
    "AppUser", "CardUser", "VinUser",
    "InterconnectPlatform", "InterconnectUser",
    "EnterpriseAccount", "EnterpriseSubUser", "BillingCycle",
    "CouponActivityStat",
    "OrderChargeCurve",
    "RevenueDaily", "StationDailyMetric",
    # SPEC §2.6 - 出站 Webhook
    "Webhook", "WebhookDelivery",
    "WEBHOOK_EVENT_TYPES", "DELIVERY_STATUS",
    # 企业资金账户(对齐前端 Fleet FundAccount 契约)
    "FundPool", "FundPoolTransaction",
    "FleetRechargeRequest", "RechargeStatus",
    "FundAccountStatus", "FundAccountType",
    "FundTransactionType", "FundTransactionStatus",
    # admin-platform-spec §2.4 - 物联网接入
    "DeviceLibrary",
    "DeviceProtocol", "ProtocolRule",
    # admin-platform-spec §2.7 - 安全管理
    "SecurityPolicy", "default_security_policies", "seed_security_policies",
    "SystemConfig",
    # P1-1 光储充能量策略 (卡片 469f03ac)
    "EnergyPriceTemplate", "EnergyPricePeriod", "EnergyPriceSpot",
    "StationEnergyStrategy", "EnergyDispatchPlan", "EnergyFlowLog",
    # 企业注册申请 + 主体 (卡 c8f7be6f)
    "Subject",
    "RegistrationApplication", "ApplyScope", "RegistrationStatus",
    # 手动开票申请 (卡 a09f8a21 契约 §5)
    "InvoiceRequest", "InvoiceRequestStatus", "InvoiceMode",
    "InvoiceTitleType", "InvoiceFileType",
    # 边缘网关 SN 平台台账 (任务卡 e940c9f4)
    "EdgeGateway",
    "EDGE_GATEWAY_STATUS_INVENTORY", "EDGE_GATEWAY_STATUS_SHIPPED",
    "EDGE_GATEWAY_STATUS_BOUND", "EDGE_GATEWAY_STATUS_ONLINE",
    "EDGE_GATEWAY_STATUS_DECOMMISSIONED", "EDGE_GATEWAY_STATUS_VALUES",
    # 运维分离架构 (卡 00d7d49a)
    "StationMaintenanceGrant", "GrantScope", "GrantStatus", "SCOPE_ALLOWED_ACTIONS",
]
