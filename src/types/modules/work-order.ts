/**
 * types/modules/work-order.ts — 工单类型
 */
export type WorkOrderType = 'repair' | 'inspection' | 'installation' | 'maintenance' | 'other';
export type WorkOrderPriority = 'low' | 'normal' | 'high' | 'urgent';
export type WorkOrderStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled';

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
  solution?: string;
  scheduledAt?: string;
  completedAt?: string;
  createdAt: string;
  updatedAt: string;
}

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
