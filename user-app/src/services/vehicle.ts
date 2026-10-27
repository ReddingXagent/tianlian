import { ApiResponse, Vehicle } from '../types';
import api from './client';

// =====================
// 车辆 API
// =====================
export const vehicleApi = {
  getList(): Promise<ApiResponse<Vehicle[]>> {
    return api.get('/vehicles').then((res) => res.data);
  },
  add(data: Omit<Vehicle, 'id' | 'userId' | 'createdAt'>): Promise<ApiResponse<Vehicle>> {
    return api.post('/vehicles', data).then((res) => res.data);
  },
  update(id: number, data: Partial<Vehicle>): Promise<ApiResponse<Vehicle>> {
    return api.put(`/vehicles/${id}`, data).then((res) => res.data);
  },
  remove(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/vehicles/${id}`).then((res) => res.data);
  },
  setDefault(id: number): Promise<ApiResponse<Vehicle>> {
    return api.post(`/vehicles/${id}/default`).then((res) => res.data);
  },
};
