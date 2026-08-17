/**
 * types/modules/common.ts — 通用API响应 + 导航参数
 */
// 共享类型从 @tianlian/shared-types 重导出，保持仓内 import 路径不变
export { type ApiResponse, type PaginatedData } from '@tianlian/shared-types';

// =====================
// 导航参数
// =====================
export type RootStackParamList = {
  Auth: undefined;
  Main: undefined;
  WorkOrderDetail: { orderId: string };
  WorkOrderCreate: undefined;
  WorkOrderTransfer: { orderId: string };
  ScanResult: { result: import('./monitor').ScanResult };
  KnowledgeArticle: { articleId: number };
  Diagnosis: undefined;
  Knowledge: undefined;
  KnowledgeDetail: { articleId: number };
  InspectionDetail: { taskId: number };
};

export type AuthStackParamList = {
  Login: undefined;
};

export type MainTabParamList = {
  Workbench: undefined;
  WorkOrders: undefined;
  Inspection: undefined;
  Scan: undefined;
  Monitor: undefined;
  Dashboard: undefined;
  Profile: undefined;
};
