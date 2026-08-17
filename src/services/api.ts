/**
 * services/api.ts — Barrel re-export from api-modules/ (F1360 维度21 结构重构)
 *
 * 原始 4125 行单体文件按领域拆分为:
 *   api-modules/client.ts     — axios 实例 + 拦截器 + tokenStorage (80 行)
 *   api-modules/auth.ts       — 认证 + 工作台 API (70 行)
 *   api-modules/workorder.ts  — 工单契约映射 + 工单/告警 API (204 行)
 *   api-modules/device.ts     — 设备/监控/扫码/知识库/诊断 API (223 行)
 *   api-modules/operations.ts — 工单记录/操作/转派/巡检/看板/角色/权限 (371 行)
 *   api-modules/extended.ts   — 扩展 API (energy/report/security/gateway/vpp/...) (2939 行)
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
export {
  energyApi,
  userApi,
  reportApi,
  alarmRuleApi,
  notificationRuleApi,
  sparePartApi,
  notificationTemplateApi,
  chargingOrderApi,
  pricingApi,
  inspectionPlanApi,
  inspectionTemplateApi,
  inspectionTaskApi,
  engineerApi,
  webhookApi,
  healingRuleApi,
  healingExecutionApi,
  apiKeyApi,
  securityLogApi,
  securityPolicyApi,
  analyticsRevenueApi,
  securityThreatApi,
  notificationStatsApi,
  notificationUnreadApi,
  notificationActionApi,
  deviceHealthApi,
  gatewayApi,
  tenantListApi,
  vppApi,
  chatApi,
  notificationSendApi,
  fleetApi,
  runbookTemplateApi,
  healthApi,
  cacheApi,
  stationApi,
  teamApi,
} from './api-modules/extended';
export type {
  EngineerCreate,
  WebhookCreate,
  GatewayCreate,
  TenantCreate,
} from './api-modules/extended';
