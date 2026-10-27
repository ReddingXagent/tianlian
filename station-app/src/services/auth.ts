import { ApiResponse, LoginRequest, LoginResponse, User } from '../types';
import api from './client';

// =====================
// 认证 API (真云端: OAuth2 form-urlencoded, token 键为 token)
// =====================
export const authApi = {
  login(data: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    const form = new URLSearchParams();
    form.append('username', data.username);
    form.append('password', data.password);
    return api
      .post('/auth/login', form.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      .then((res) => res.data);
  },
  logout(): Promise<ApiResponse<null>> {
    return api.post('/auth/logout').then((res) => res.data);
  },
  getProfile(): Promise<ApiResponse<User>> {
    return api.get('/auth/me').then((res) => res.data);
  },
};
