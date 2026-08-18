/**
 * types/modules/work-order.ts — 工单类型
 */
import type { WorkOrderStatus, WorkOrderType, WorkOrderPriority } from '@tianlian/shared-types';
export { type WorkOrderType, type WorkOrderPriority, type WorkOrderStatus, type WorkOrder, type WorkOrderReport } from '@tianlian/shared-types';

export interface WorkOrderQuery {
  stationId?: number;
  status?: WorkOrderStatus;
  page?: number;
  pageSize?: number;
}

export interface CreateWorkOrderData {
  stationId: number;
  title: string;
  description: string;
  type: WorkOrderType;
  priority: WorkOrderPriority;
  alarmId?: number;
  deviceId?: number;
}

// 工单报告已移入 @tianlian/shared-types
// 以下为 station-app 专属类型

