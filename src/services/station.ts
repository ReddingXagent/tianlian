import { ApiResponse, Station, Device, Alarm, PaginatedData } from '../types';
import api from './client';
import { mapStation, mapAlarm, mapPagination } from './mappers';

// =====================
// 站点 API
// =====================
export const stationApi = {
  getList(params?: { page?: number; pageSize?: number; search?: string }): Promise<ApiResponse<PaginatedData<Station>>> {
    const query = {
      page: params?.page,
      page_size: params?.pageSize,
      search: params?.search,
    };
    return api.get('/stations', { params: query }).then((res) => ({
      ...res.data,
      data: mapPagination<Station>(res.data?.data, mapStation),
    }));
  },
  getDetail(id: number): Promise<ApiResponse<Station>> {
    return api.get(`/stations/${id}`).then((res) => ({
      ...res.data,
      data: mapStation(res.data?.data ?? {}),
    }));
  },
  getDevices(stationId: number): Promise<ApiResponse<Device[]>> {
    return api.get(`/stations/${stationId}/devices`).then((res) => res.data);
  },
  getAlarms(stationId: number, params?: { page?: number; pageSize?: number }): Promise<ApiResponse<PaginatedData<Alarm>>> {
    const query = { page: params?.page, page_size: params?.pageSize };
    return api.get(`/stations/${stationId}/alarms`, { params: query }).then((res) => ({
      ...res.data,
      data: mapPagination<Alarm>(res.data?.data, mapAlarm),
    }));
  },
};
