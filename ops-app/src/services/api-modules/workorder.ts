/**
 * api-modules/workorder.ts — 工单契约映射 + 工单/告警 API + 工单记录/操作/转派
 * 从 services/api.ts 拆分 (F1360 维度21 结构重构)
 */
import api from './client';
import {
  ApiResponse,
  WorkOrder,
  Alarm,
  PaginatedData,
  WorkOrderStats,
} from '../../types';

export const WO_LEVEL_TO_PRIORITY: Record<string, 'low' | 'normal' | 'high' | 'urgent'> = {
  info: 'low',
  warning: 'normal',
  critical: 'high',
  fatal: 'urgent',
};
export const WO_PRIORITY_TO_LEVEL: Record<string, string> = {
  low: 'info',
  normal: 'warning',
  high: 'critical',
  urgent: 'critical',
};
export const WO_BACKEND_STATUS_TO_CLIENT: Record<string, 'pending' | 'in_progress' | 'completed' | 'cancelled'> = {
  pending: 'pending',
  accepted: 'in_progress',
  processing: 'in_progress',
  pending_verify: 'completed',
  completed: 'completed',
};
export const WO_CLIENT_STATUS_TO_BACKEND: Record<string, string> = {
  pending: 'pending',
  in_progress: 'processing',
  completed: 'completed',
};

interface RawWorkOrder {
  id?: string | number;
  station_id?: number;
  station_name?: string;
  fault_desc?: string;
  type?: string;
  level?: string;
  status?: string;
  assignee_id?: number;
  assignee_name?: string;
  creator_id?: number;
  creator_name?: string;
  finish_time?: string;
  create_time?: string;
  update_time?: string;
  solution?: string;
}


export function mapWorkOrder(raw: RawWorkOrder): WorkOrder {
  return {
    id: String(raw.id),
    stationId: raw.station_id ?? 0,
    stationName: raw.station_name ?? '',
    title: raw.fault_desc ?? '',
    description: raw.fault_desc ?? '',
    type: (raw.type ?? 'repair') as WorkOrder['type'],
    priority: WO_LEVEL_TO_PRIORITY[raw.level ?? ''] ?? 'normal',
    status: WO_BACKEND_STATUS_TO_CLIENT[raw.status ?? ''] ?? 'pending',
    assigneeId: raw.assignee_id ?? undefined,
    assigneeName: raw.assignee_name ?? undefined,
    creatorId: raw.creator_id ?? 999,
    creatorName: raw.creator_name ?? '',
    completedAt: raw.finish_time ?? undefined,
    createdAt: raw.create_time ?? '',
    updatedAt: raw.update_time ?? raw.create_time ?? '',
    solution: raw.solution ?? undefined,
  };
}

export const workOrderApi = {
  getList(params?: {
    status?: string;
    level?: string;
    type?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<WorkOrder>>> {
    const query: Record<string, unknown> = {
      page: params?.page,
      page_size: params?.pageSize,
      level: params?.level,
      type: params?.type,
    };
    if (params?.status) {
      query.status = WO_CLIENT_STATUS_TO_BACKEND[params.status] ?? params.status;
    }
    return api.get('/work-orders', { params: query }).then((res) => {
      const env = res.data as ApiResponse<Record<string, unknown>>;
      const rawPage = (env.data ?? {}) as Record<string, unknown>;
      return {
        ...env,
        data: {
          items: ((rawPage.items as RawWorkOrder[]) ?? []).map((it) => mapWorkOrder(it)),
          total: (rawPage.total as number) ?? 0,
          page: (rawPage.page as number) ?? params?.page ?? 1,
          pageSize: (rawPage.page_size as number) ?? params?.pageSize ?? 20,
        },
      };
    });
  },
  getDetail(id: string): Promise<ApiResponse<WorkOrder>> {
    return api.get(`/work-orders/${id}`).then((res) => ({
      ...res.data,
      data: mapWorkOrder(res.data.data),
    }));
  },
  create(data: {
    faultDesc: string;
    type?: string;
    level?: string;
    stationId?: number;
    deviceId?: number;
  }): Promise<ApiResponse<WorkOrder>> {
    return api
      .post('/work-orders', {
        fault_desc: data.faultDesc,
        type: data.type ?? 'repair',
        level: data.level ?? 'warning',
        station_id: data.stationId,
        device_id: data.deviceId,
      })
      .then((res) => ({ ...res.data, data: mapWorkOrder(res.data.data) }));
  },
  update(
    id: string,
    data: { faultDesc?: string; level?: string; status?: string; assigneeId?: number; solution?: string }
  ): Promise<ApiResponse<WorkOrder>> {
    return api
      .put(`/work-orders/${id}`, {
        fault_desc: data.faultDesc,
        level: data.level,
        status: data.status ? WO_CLIENT_STATUS_TO_BACKEND[data.status] ?? data.status : undefined,
        assignee_id: data.assigneeId,
        solution: data.solution,
      })
      .then((res) => ({ ...res.data, data: mapWorkOrder(res.data.data) }));
  },
  updateStatus(id: string, status: string): Promise<ApiResponse<WorkOrder>> {
    const backendStatus = WO_CLIENT_STATUS_TO_BACKEND[status];
    if (!backendStatus) {
      return Promise.reject(new Error(`后端不支持的工单状态: ${status}`));
    }
    return workOrderApi.update(id, { status: backendStatus });
  },
  assign(id: string, assigneeId: number): Promise<ApiResponse<WorkOrder>> {
    return workOrderApi.update(id, { assigneeId });
  },
  dispatch(id: string, auto = true): Promise<ApiResponse<unknown>> {
    return api.post(`/work-orders/${id}/dispatch`, { auto }).then((res) => res.data);
  },
  getStats(): Promise<ApiResponse<WorkOrderStats>> {
    return api.get('/work-orders/stats').then((res) => ({
      ...res.data,
      data: {
        total: res.data.data?.total ?? 0,
        statusDistribution: res.data.data?.status_distribution ?? {},
        levelDistribution: res.data.data?.level_distribution ?? {},
        typeDistribution: res.data.data?.type_distribution ?? {},
        groups: res.data.data?.groups ?? {},
      },
    }));
  },
};

export const alarmApi = {
  getList(params?: {
    stationId?: number;
    level?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Alarm>>> {
    return api.get('/alarms', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<Alarm>> {
    return api.get(`/alarms/${id}`).then((res) => res.data);
  },
  handleAlarm(id: number): Promise<ApiResponse<Alarm>> {
    /** 真云 OPTIONS 实测 allow=PUT (F3680 发现, 2026-09-03 复核) */
    return api.put(`/alarms/${id}/ack`).then((res) => res.data);
  },
  /** PUT /alarms/{id}/resolve — 解决告警 */
  resolve(id: number): Promise<ApiResponse<Alarm>> {
    return api.put(`/alarms/${id}/resolve`).then((res) => res.data);
  },
};
