/**
 * api-modules/client.ts — axios 实例、拦截器、tokenStorage
 * 从 services/api.ts 拆分 (F1360 维度21 结构重构)
 */
import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import { HealthStatus } from '../../types';

/** health端点返回类型 */
export type HealthInfo = {
  status: HealthStatus;
  version: string;
  service: string;
};

const TOKEN_KEY = 'auth_token';
const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ||
  (__DEV__ ? 'http://localhost:8000/api/v1' : 'http://8.134.106.166/api/v1');

// eslint-disable-next-line import/no-named-as-default-member
const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// JWT token 注入拦截器
api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    try {
      const token = await SecureStore.getItemAsync(TOKEN_KEY);
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch {
      // SecureStore 失败时静默处理
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);

// 401 响应拦截器 - token 过期自动清除
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      try {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
      } catch {
        // 静默处理
      }
    }
    return Promise.reject(error);
  }
);

// =====================
// Token 管理
// =====================
export const tokenStorage = {
  async getToken(): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  async setToken(token: string): Promise<void> {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
  },
  async removeToken(): Promise<void> {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  },
};

export default api;
