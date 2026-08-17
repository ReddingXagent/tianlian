import { ApiResponse, LoginRequest, LoginResponse, SendCodeRequest, User } from '../types';
import api from './client';

// =====================
// 认证 API
// =====================
export const authApi = {
  sendCode(data: SendCodeRequest): Promise<ApiResponse<null>> {
    return api.post('/auth/send-code', data).then((res) => res.data);
  },
  loginByCode(data: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    return api.post('/auth/login/code', data).then((res) => res.data);
  },
  loginByPassword(data: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    return api.post('/auth/login/password', data).then((res) => res.data);
  },
  logout(): Promise<ApiResponse<null>> {
    return api.post('/auth/logout').then((res) => res.data);
  },
  getProfile(): Promise<ApiResponse<User>> {
    return api.get('/auth/me').then((res) => res.data);
  },
  updateProfile(data: Partial<User>): Promise<ApiResponse<User>> {
    return api.put('/auth/me', data).then((res) => res.data);
  },
};
