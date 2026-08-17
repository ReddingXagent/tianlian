/**
 * types/modules/common.ts — 通用API响应 + 导航参数
 */
export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
  /** 后端部分端点随响应携带的服务器时间戳（秒） */
  timestamp?: number;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

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
