import { ApiResponse, UserStats } from '../types';
import api from './client';

// =====================
// 统计 API
// =====================
export const statsApi = {
  getUserStats(): Promise<ApiResponse<UserStats>> {
    return api.get('/user/stats').then((res) => res.data);
  },
};
