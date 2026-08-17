/**
 * types/modules/work-order.ts — 工单相关类型
 */
import type { WorkOrderType, WorkOrderPriority, WorkOrderStatus, WorkOrder, WorkOrderReport } from '@tianlian/shared-types';
export { type WorkOrderType, type WorkOrderPriority, type WorkOrderStatus, type WorkOrder, type WorkOrderReport } from '@tianlian/shared-types';

export type WorkOrderAction =
  | 'created'
  | 'accepted'
  | 'check_in'
  | 'executing'
  | 'completed'
  | 'cancelled'
  | 'reassigned';

export interface WorkOrderStats {
  total: number;
  statusDistribution: Record<string, number>;
  levelDistribution: Record<string, number>;
  typeDistribution: Record<string, number>;
  groups: Record<string, number>;
}

// 工单执行记录
export interface WorkOrderRecord {
  id: number;
  orderId: string;
  action: WorkOrderAction;
  operatorId: number;
  operatorName: string;
  note: string;
  createdAt: string;
}

// 工单评价 (Work Order Rating — from POST /work-orders/{id}/rate)
export interface WorkOrderRating {
  responseRating: number;
  qualityRating: number;
  attitudeRating: number;
  comment?: string;
}

// 工单报告已移入 @tianlian/shared-types
// 以下为 ops-app 专属类型


// 工单趋势
export interface WorkOrderTrend {
  date: string;
  created: number;
  completed: number;
}

// 工单备件申请 (from POST /work-orders/{id}/spare-parts)
export interface WorkOrderSparePartCreate {
  partName: string;
  reason: string;
  partModel?: string;
  quantity?: number;
}

export interface WorkOrderSparePartCreated {
  id: number;
  orderId: string;
  partName: string;
  partModel: string | null;
  quantity: number;
  reason: string;
  status: string;
  inventoryDeducted: boolean;
  createdAt: string;
}
