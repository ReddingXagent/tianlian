import { ApiResponse, Order, PaginatedData } from '../types';
import api from './client';

// =====================
// 订单 API
// =====================
export const orderApi = {
  getList(params?: {
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Order>>> {
    return api.get('/orders', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<Order>> {
    return api.get(`/orders/${id}`).then((res) => res.data);
  },
  cancelOrder(id: number): Promise<ApiResponse<Order>> {
    return api.post(`/orders/${id}/cancel`).then((res) => res.data);
  },
};
