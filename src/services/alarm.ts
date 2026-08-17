import { ApiResponse, Alarm, PaginatedData } from '../types';
import api from './client';
import { mapAlarm, mapPagination, ALARM_STATUS_REVERSE } from './mappers';

// =====================
// 告警 API (真云端: /alarms, 状态 active/acknowledged/resolved)
// =====================
export const alarmApi = {
  getList(params?: {
    stationId?: number;
    level?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Alarm>>> {
    const query = {
      station_id: params?.stationId,
      level: params?.level,
      status: params?.status ? (ALARM_STATUS_REVERSE[params.status] ?? params.status) : undefined,
      page: params?.page,
      page_size: params?.pageSize,
    };
    return api.get('/alarms', { params: query }).then((res) => ({
      ...res.data,
      data: mapPagination<Alarm>(res.data?.data, mapAlarm),
    }));
  },
  getDetail(id: number): Promise<ApiResponse<Alarm>> {
    return api.get(`/alarms/${id}`).then((res) => ({
      ...res.data,
      data: mapAlarm(res.data?.data ?? {}),
    }));
  },
  // 真云端无 /handle 端点, 对齐 PUT /{id}/ack (确认告警)
  handleAlarm(id: number): Promise<ApiResponse<Alarm>> {
    return api.put(`/alarms/${id}/ack`).then((res) => ({
      ...res.data,
      data: res.data?.data ? mapAlarm(res.data.data) : undefined,
    }));
  },
};
