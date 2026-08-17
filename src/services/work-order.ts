import { ApiResponse, WorkOrder, CreateWorkOrderData, PaginatedData } from '../types';
import api from './client';
import { mapWorkOrder, mapPagination, WO_PRIORITY_TO_LEVEL, WO_STATUS_REVERSE } from './mappers';

// =====================
// 工单 API (真云端: /work-orders, id 为 WO- 字符串, snake_case)
// =====================
export const workOrderApi = {
  getList(params?: {
    stationId?: number;
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<WorkOrder>>> {
    const query = {
      station_id: params?.stationId,
      status: params?.status ? (WO_STATUS_REVERSE[params.status] ?? params.status) : undefined,
      page: params?.page,
      page_size: params?.pageSize,
    };
    return api.get('/work-orders', { params: query }).then((res) => ({
      ...res.data,
      data: mapPagination<WorkOrder>(res.data?.data, mapWorkOrder),
    }));
  },
  getDetail(id: string): Promise<ApiResponse<WorkOrder>> {
    return api.get(`/work-orders/${id}`).then((res) => ({
      ...res.data,
      data: mapWorkOrder(res.data?.data ?? {}),
    }));
  },
  createWorkOrder(data: CreateWorkOrderData): Promise<ApiResponse<WorkOrder>> {
    const body = {
      fault_desc: data.title,
      type: data.type,
      level: WO_PRIORITY_TO_LEVEL[data.priority] ?? 'warning',
      station_id: data.stationId,
      device_id: data.deviceId ?? null,
    };
    return api.post('/work-orders', body).then((res) => ({
      ...res.data,
      data: res.data?.data ? mapWorkOrder(res.data.data) : undefined,
    }));
  },
  // 真云端 complete 的 solution 是 query 参数
  completeWorkOrder(id: string, solution?: string): Promise<ApiResponse<WorkOrder>> {
    return api
      .post(`/work-orders/${id}/complete`, null, { params: solution ? { solution } : undefined })
      .then((res) => ({
        ...res.data,
        data: res.data?.data ? mapWorkOrder(res.data.data) : undefined,
      }));
  },
  getStats(): Promise<ApiResponse<{
    total: number;
    status_distribution: Record<string, number>;
    level_distribution: Record<string, number>;
    type_distribution: Record<string, number>;
  }>> {
    return api.get('/work-orders/stats').then((res) => res.data);
  },
};
