import { ApiResponse, ScanResult, StartChargingRequest, ChargingStatus, Order } from '../types';
import api from './client';

// =====================
// 充电 API
// =====================
export const chargingApi = {
  scan(code: string): Promise<ApiResponse<ScanResult>> {
    return api.get('/charging/scan', { params: { code } }).then((res) => res.data);
  },
  start(data: StartChargingRequest): Promise<ApiResponse<ChargingStatus>> {
    return api.post('/charging/start', data).then((res) => res.data);
  },
  stop(orderId: number): Promise<ApiResponse<Order>> {
    return api.post(`/charging/${orderId}/stop`).then((res) => res.data);
  },
  getStatus(orderId: number): Promise<ApiResponse<ChargingStatus>> {
    return api.get(`/charging/${orderId}/status`).then((res) => res.data);
  },
  getActiveOrder(): Promise<ApiResponse<ChargingStatus | null>> {
    return api.get('/charging/active').then((res) => res.data);
  },
};
