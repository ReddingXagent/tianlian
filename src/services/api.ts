/**
 * services/api.ts — Barrel re-export from api-modules/ (F1361 维度22 领域细分)
 *
 * api-modules/ 目录结构:
 *   client.ts           — axios 实例 + 拦截器 + tokenStorage (80 行)
 *   auth.ts             — 认证 + 工作台 API (70 行)
 *   workorder.ts        — 工单契约映射 + 工单/告警 API (204 行)
 *   device.ts           — 设备/监控/扫码/知识库/诊断 API (223 行)
 *   operations.ts       — 工单记录/操作/转派/巡检/看板/角色/权限 (371 行)
 *   energy-report.ts    — 能源/报表 API (312 行)
 *   user-tenant.ts      — 用户/租户/站点/团队 API (419 行)
 *   alarm-notification.ts — 告警规则/通知 API (402 行)
 *   inspection-engineer.ts — 巡检/工程师/Webhook/Fleet/Runbook API (544 行)
 *   security.ts         — 安全/密钥/愈合规则 API (600 行)
 *   infrastructure.ts   — 设施/充电/网关/VPP/健康/缓存 API (733 行)
 *
 * 所有 import 路径 `from '../services/api'` 保持不变。
 */
export { default } from './api-modules/client';
export { default as api } from './api-modules/client';
export { tokenStorage } from './api-modules/client';
export type { HealthInfo } from './api-modules/client';
export {
  authApi,
  workbenchApi,
} from './api-modules/auth';
export {
  WO_LEVEL_TO_PRIORITY,
  WO_PRIORITY_TO_LEVEL,
  WO_BACKEND_STATUS_TO_CLIENT,
  WO_CLIENT_STATUS_TO_BACKEND,
  mapWorkOrder,
  workOrderApi,
  alarmApi,
} from './api-modules/workorder';
export {
  deviceApi,
  monitorApi,
  scanApi,
  knowledgeApi,
  diagnosisApi,
} from './api-modules/device';
export {
  workOrderRecordApi,
  workOrderActionApi,
  deviceMonitorApi,
  inspectionApi,
  dashboardApi,
  workOrderTransferApi,
  roleApi,
  permissionApi,
} from './api-modules/operations';
// energy-report
export {
  energyApi,
  reportApi,
} from './api-modules/energy-report';
// user-tenant
export {
  userApi,
  tenantListApi,
  stationApi,
  teamApi,
} from './api-modules/user-tenant';
export type {
  TenantCreate,
} from './api-modules/user-tenant';
// alarm-notification
export {
  alarmRuleApi,
  notificationRuleApi,
  notificationTemplateApi,
  notificationStatsApi,
  notificationUnreadApi,
  notificationActionApi,
  notificationSendApi,
} from './api-modules/alarm-notification';
// inspection-engineer
export {
  inspectionPlanApi,
  inspectionTemplateApi,
  inspectionTaskApi,
  engineerApi,
  webhookApi,
  fleetApi,
  runbookTemplateApi,
} from './api-modules/inspection-engineer';
export type {
  EngineerCreate,
  WebhookCreate,
} from './api-modules/inspection-engineer';
// security
export {
  healingRuleApi,
  healingExecutionApi,
  apiKeyApi,
  securityLogApi,
  securityPolicyApi,
  analyticsRevenueApi,
  securityThreatApi,
} from './api-modules/security';
// infrastructure
export {
  sparePartApi,
  chargingOrderApi,
  pricingApi,
  deviceHealthApi,
  gatewayApi,
  vppApi,
  chatApi,
  healthApi,
  cacheApi,
} from './api-modules/infrastructure';
export type {
  GatewayCreate,
} from './api-modules/infrastructure';
// merchant-audit (商户进件审核, 卡 a8ca56aa)
export {
  MERCHANT_STATUS_LABEL,
  merchantStatusLabel,
  mapMerchantApplication,
  mapMerchantApplicationList,
  merchantAuditApi,
} from './api-modules/merchant-audit';
export type { RawMerchantApplication } from './api-modules/merchant-audit';
export {
  merchantAuditMockApi,
  MerchantAuditNotFoundError,
  MerchantAuditInvalidTransitionError,
  __mockStore as merchantAuditMockStore,
} from './api-modules/merchant-audit-mock';
export {
  resolveMerchantAuditMode,
  merchantAuditModeLabel,
  createMerchantAuditClient,
  realMerchantAuditAdapter,
  MERCHANT_AUDIT_MODE,
  merchantAudit,
} from './api-modules/merchant-audit-source';
export type {
  MerchantAuditMode,
  MerchantAuditClient,
} from './api-modules/merchant-audit-source';
