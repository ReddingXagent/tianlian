/**
 * 定价管理 API 层
 *
 * 6 类定价 CRUD + 费用估算:
 * 1. TimeSlotDefinitions — 尖/峰/平/谷时段模板
 * 2. EnergyPrices        — 充电费定价
 * 3. ServiceFeePrices    — 服务费定价
 * 4. ParkingPrices       — 停车费定价
 * 5. OccupancyFeePrices  — 占桩费定价
 * 6. ReservationFeePrices — 预约费定价
 */
import api from './index';

/* ── 时段定义 ── */
export const timeSlotAPI = {
  list: (params?: { page?: number; page_size?: number; is_active?: boolean }) =>
    api.get('/pricing/mgmt/time-slots', { params }),
  get: (id: number) => api.get(`/pricing/mgmt/time-slots/${id}`),
  create: (data: Record<string, unknown>) => api.post('/pricing/mgmt/time-slots', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/pricing/mgmt/time-slots/${id}`, data),
  delete: (id: number) => api.delete(`/pricing/mgmt/time-slots/${id}`),
};

/* ── 充电费定价 ── */
export const energyPriceAPI = {
  list: (params?: { page?: number; page_size?: number; station_id?: number; is_active?: boolean }) =>
    api.get('/pricing/mgmt/energy', { params }),
  get: (id: number) => api.get(`/pricing/mgmt/energy/${id}`),
  create: (data: Record<string, unknown>) => api.post('/pricing/mgmt/energy', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/pricing/mgmt/energy/${id}`, data),
  delete: (id: number) => api.delete(`/pricing/mgmt/energy/${id}`),
};

/* ── 服务费定价 ── */
export const serviceFeeAPI = {
  list: (params?: { page?: number; page_size?: number; station_id?: number; is_active?: boolean }) =>
    api.get('/pricing/mgmt/service-fee', { params }),
  get: (id: number) => api.get(`/pricing/mgmt/service-fee/${id}`),
  create: (data: Record<string, unknown>) => api.post('/pricing/mgmt/service-fee', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/pricing/mgmt/service-fee/${id}`, data),
  delete: (id: number) => api.delete(`/pricing/mgmt/service-fee/${id}`),
};

/* ── 停车费定价 ── */
export const parkingPriceAPI = {
  list: (params?: { page?: number; page_size?: number; station_id?: number; is_active?: boolean }) =>
    api.get('/pricing/mgmt/parking', { params }),
  get: (id: number) => api.get(`/pricing/mgmt/parking/${id}`),
  create: (data: Record<string, unknown>) => api.post('/pricing/mgmt/parking', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/pricing/mgmt/parking/${id}`, data),
  delete: (id: number) => api.delete(`/pricing/mgmt/parking/${id}`),
};

/* ── 占桩费定价 ── */
export const occupancyFeeAPI = {
  list: (params?: { page?: number; page_size?: number; station_id?: number; is_active?: boolean }) =>
    api.get('/pricing/mgmt/occupancy', { params }),
  get: (id: number) => api.get(`/pricing/mgmt/occupancy/${id}`),
  create: (data: Record<string, unknown>) => api.post('/pricing/mgmt/occupancy', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/pricing/mgmt/occupancy/${id}`, data),
  delete: (id: number) => api.delete(`/pricing/mgmt/occupancy/${id}`),
};

/* ── 预约费定价 ── */
export const reservationFeeAPI = {
  list: (params?: { page?: number; page_size?: number; station_id?: number; is_active?: boolean }) =>
    api.get('/pricing/mgmt/reservation', { params }),
  get: (id: number) => api.get(`/pricing/mgmt/reservation/${id}`),
  create: (data: Record<string, unknown>) => api.post('/pricing/mgmt/reservation', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/pricing/mgmt/reservation/${id}`, data),
  delete: (id: number) => api.delete(`/pricing/mgmt/reservation/${id}`),
};

/* ── 订单费用估算 ── */
export const orderEstimateAPI = {
  estimate: (data: {
    station_id: number;
    user_type?: string;
    energy_kwh: number;
    charging_minutes?: number;
    parking_minutes?: number;
    occupancy_minutes?: number;
  }) => api.post('/pricing/mgmt/order-estimate', data),
};
