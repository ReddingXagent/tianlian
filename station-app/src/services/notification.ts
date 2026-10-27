import { ApiResponse, AppNotification, PaginatedData } from '../types';
import api from './client';

// =====================
// 通知 API
// =====================
export const notificationApi = {
  getList(params?: {
    page?: number;
    pageSize?: number;
    unreadOnly?: boolean;
  }): Promise<ApiResponse<PaginatedData<AppNotification>>> {
    return api.get('/notifications', { params }).then((res) => res.data);
  },
  getUnreadCount(): Promise<ApiResponse<{ count: number }>> {
    return api.get('/notifications/unread-count').then((res) => res.data);
  },
  markAsRead(id: number): Promise<ApiResponse<AppNotification>> {
    return api.post(`/notifications/${id}/read`).then((res) => res.data);
  },
  markAllAsRead(): Promise<ApiResponse<null>> {
    return api.post('/notifications/read-all').then((res) => res.data);
  },
};
