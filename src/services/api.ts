import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import {
  ApiResponse,
  LoginRequest,
  LoginResponse,
  SendCodeRequest,
  User,
  Station,
  Charger,
  Order,
  Vehicle,
  Coupon,
  WalletRecord,
  PaginatedData,
  ScanResult,
  StartChargingRequest,
  ChargingStatus,
  PaymentRequest,
  PaymentResult,
  StationQuery,
  UserStats,
} from '../types';

const TOKEN_KEY = 'tianlian_user_token';
const BASE_URL = 'http://8.134.106.166/api/v1';

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
    return api.get('/auth/profile').then((res) => res.data);
  },
  updateProfile(data: Partial<User>): Promise<ApiResponse<User>> {
    return api.put('/auth/profile', data).then((res) => res.data);
  },
};

// =====================
// 站点 API
// =====================
export const stationApi = {
  getList(query?: StationQuery): Promise<ApiResponse<PaginatedData<Station>>> {
    return api.get('/stations/nearby', { params: query }).then((res) => res.data);
  },
  search(keyword: string): Promise<ApiResponse<PaginatedData<Station>>> {
    return api.get('/stations/search', { params: { keyword } }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<Station>> {
    return api.get(`/stations/${id}`).then((res) => res.data);
  },
  getChargers(stationId: number): Promise<ApiResponse<Charger[]>> {
    return api.get(`/stations/${stationId}/chargers`).then((res) => res.data);
  },
};

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

// =====================
// 支付 API
// =====================
export const paymentApi = {
  pay(data: PaymentRequest): Promise<ApiResponse<PaymentResult>> {
    return api.post('/payment/pay', data).then((res) => res.data);
  },
  getPaymentInfo(orderId: number): Promise<ApiResponse<{ amount: number; balance: number; couponDiscount: number }>> {
    return api.get(`/payment/${orderId}/info`).then((res) => res.data);
  },
};

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

// =====================
// 优惠券 API
// =====================
export const couponApi = {
  getList(params?: {
    status?: CouponStatus;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Coupon>>> {
    return api.get('/coupons', { params }).then((res) => res.data);
  },
  getAvailable(stationId?: number): Promise<ApiResponse<Coupon[]>> {
    return api.get('/coupons/available', { params: { stationId } }).then((res) => res.data);
  },
};

// =====================
// 钱包 API
// =====================
export const walletApi = {
  getBalance(): Promise<ApiResponse<{ balance: number }>> {
    return api.get('/wallet/balance').then((res) => res.data);
  },
  getRecords(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<WalletRecord>>> {
    return api.get('/wallet/records', { params }).then((res) => res.data);
  },
  recharge(amount: number): Promise<ApiResponse<{ tradeNo: string; url?: string }>> {
    return api.post('/wallet/recharge', { amount }).then((res) => res.data);
  },
};

// =====================
// 统计 API
// =====================
export const statsApi = {
  getUserStats(): Promise<ApiResponse<UserStats>> {
    return api.get('/user/stats').then((res) => res.data);
  },
};

export default api;