import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';

const TOKEN_KEY = 'tianlian_user_token';
// 环境变量 EXPO_PUBLIC_API_URL 优先，回退到生产地址
const BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://your-server-ip/api/v1';

// eslint-disable-next-line import/no-named-as-default-member -- axios 默认导出承载 .create; 此版本无具名导出, AxiosError/InternalAxiosRequestConfig 需同源默认导入
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

// =====================
// 401 全局回调（供 authStore 同步登出状态，避免 api↔store 循环依赖）
// =====================
type UnauthorizedHandler = () => void | Promise<void>;
let unauthorizedHandler: UnauthorizedHandler | null = null;

/**
 * 注册"token 失效(401)"处理器。
 * 移动端质量基线补齐: 此前 401 仅清 SecureStore 中的 token,
 * authStore 内存态仍是已登录, 用户停留在鉴权页面直到下次手动操作;
 * 现由 authStore 注册回调, 401 时同步清空登录态回到登录页。
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

// 401 响应拦截器 - token 过期自动清除 + 通知已注册处理器
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      try {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
      } catch {
        // 静默处理
      }
      if (unauthorizedHandler) {
        try {
          await unauthorizedHandler();
        } catch {
          // 处理器异常不影响错误传播
        }
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
