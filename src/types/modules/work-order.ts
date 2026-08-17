/**
 * types/modules/work-order.ts — 工单相关类型
 */
export type WorkOrderType =
  | 'repair'
  | 'inspection'
  | 'installation'
  | 'maintenance'
  | 'other';

export type WorkOrderPriority = 'low' | 'normal' | 'high' | 'urgent';

export type WorkOrderStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'cancelled';

export type WorkOrderAction =
  | 'created'
  | 'accepted'
  | 'check_in'
  | 'executing'
  | 'completed'
  | 'cancelled'
  | 'reassigned';

export interface WorkOrder {
  id: string;
  stationId: number;
  stationName: string;
  title: string;
  description: string;
  type: WorkOrderType;
  priority: WorkOrderPriority;
  status: WorkOrderStatus;
  assigneeId?: number;
  assigneeName?: string;
  creatorId: number;
  creatorName: string;
  alarmId?: number;
  scheduledAt?: string;
  completedAt?: string;
  createdAt: string;
  updatedAt: string;
  solution?: string;
}

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

// 工单报告 (WorkOrderReport — from /reports/workorders)
export interface WorkOrderReport {
  periodDays: number;
  totalWorkorders: number;
  typeDistribution: Record<string, number>;
  levelDistribution: Record<string, number>;
  statusDistribution: Record<string, number>;
  completionRate: number;
  efficiency: {
    avgResponseHours: number;
    avgCompletionHours: number;
  };
  engineerPerformance: {
    engineerId: number;
    engineerName: string;
    completedCount: number;
    avgCompletionHours: number;
  }[];
}

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
