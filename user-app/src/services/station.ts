import { ApiResponse, Station, Charger, PaginatedData, StationQuery } from '../types';
import api from './client';

// =====================
// 站点 API
// =====================
export const stationApi = {
  getList(query?: StationQuery): Promise<ApiResponse<PaginatedData<Station>>> {
    return api.get('/stations/nearby', { params: query }).then((res) => res.data);
  },
  search(keyword: string): Promise<ApiResponse<PaginatedData<Station>>> {
    return api.get('/stations/search', { params: { keyword } }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<Station>> {
    return api.get(`/stations/${id}`).then((res) => res.data);
  },
  getChargers(stationId: number): Promise<ApiResponse<Charger[]>> {
    return api.get(`/stations/${stationId}/chargers`).then((res) => res.data);
  },
};
