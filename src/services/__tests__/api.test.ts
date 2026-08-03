import {
  authApi,
  stationApi,
  chargingApi,
  orderApi,
  paymentApi,
  vehicleApi,
  couponApi,
  walletApi,
  statsApi,
  tokenStorage,
  setUnauthorizedHandler,
} from '../api';

// Mock axios and SecureStore at module level
jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return {
    __esModule: true,
    default: {
      create: jest.fn(() => mockInstance),
    },
  };
});

const mockGetItem = jest.fn();
const mockSetItem = jest.fn();
const mockDeleteItem = jest.fn();

jest.mock('expo-secure-store', () => ({
  __esModule: true,
  getItemAsync: (...args: any[]) => mockGetItem(...args),
  setItemAsync: (...args: any[]) => mockSetItem(...args),
  deleteItemAsync: (...args: any[]) => mockDeleteItem(...args),
}));

import axios from 'axios';
import * as SecureStore from 'expo-secure-store';

// Get the mocked instance
const mockAxiosInstance = (axios as any).create();

// Helper to create AxiosResponse-like mock
const mockResponse = (data: any) => ({ data });

// Helper to create AxiosError-like mock
const mockAxiosError = (status: number, data?: any) => ({
  response: { status, data },
  message: 'Request failed',
});

describe('API Service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Re-setup default mocks
    mockAxiosInstance.get.mockResolvedValue(mockResponse({ success: true }));
    mockAxiosInstance.post.mockResolvedValue(mockResponse({ success: true }));
    mockAxiosInstance.put.mockResolvedValue(mockResponse({ success: true }));
    mockAxiosInstance.delete.mockResolvedValue(mockResponse({ success: true }));
    mockGetItem.mockResolvedValue(null);
    mockSetItem.mockResolvedValue(undefined);
    mockDeleteItem.mockResolvedValue(undefined);
  });

  // =====================
  // Token Storage
  // =====================
  describe('tokenStorage', () => {
    it('getToken returns stored token', async () => {
      mockGetItem.mockResolvedValue('token-abc');
      const token = await tokenStorage.getToken();
      expect(token).toBe('token-abc');
      expect(mockGetItem).toHaveBeenCalledWith('tianlian_user_token');
    });

    it('getToken returns null on error', async () => {
      mockGetItem.mockRejectedValue(new Error('fail'));
      const token = await tokenStorage.getToken();
      expect(token).toBeNull();
    });

    it('setToken stores token', async () => {
      await tokenStorage.setToken('new-token');
      expect(mockSetItem).toHaveBeenCalledWith('tianlian_user_token', 'new-token');
    });

    it('removeToken deletes token', async () => {
      await tokenStorage.removeToken();
      expect(mockDeleteItem).toHaveBeenCalledWith('tianlian_user_token');
    });
  });

  // =====================
  // Auth API
  // =====================
  describe('authApi', () => {
    it('sendCode posts to /auth/send-code', async () => {
      mockAxiosInstance.post.mockResolvedValue(mockResponse({ code: 0 }));
      const result = await authApi.sendCode({ phone: '13800138000' });
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/auth/send-code', { phone: '13800138000' });
      expect(result).toEqual({ code: 0 });
    });

    it('loginByCode posts to /auth/login/code', async () => {
      mockAxiosInstance.post.mockResolvedValue(mockResponse({ code: 0, data: { token: 't' } }));
      await authApi.loginByCode({ phone: '13800138000', code: '1234' });
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/auth/login/code', { phone: '13800138000', code: '1234' });
    });

    it('loginByPassword posts to /auth/login/password', async () => {
      mockAxiosInstance.post.mockResolvedValue(mockResponse({ code: 0 }));
      await authApi.loginByPassword({ phone: '13800138000', password: 'pass' });
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/auth/login/password', { phone: '13800138000', password: 'pass' });
    });

    it('logout posts to /auth/logout', async () => {
      await authApi.logout();
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/auth/logout');
    });

    it('getProfile gets /auth/profile', async () => {
      await authApi.getProfile();
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/auth/profile');
    });

    it('updateProfile puts to /auth/profile', async () => {
      const data = { nickname: 'Updated' };
      await authApi.updateProfile(data);
      expect(mockAxiosInstance.put).toHaveBeenCalledWith('/auth/profile', data);
    });
  });

  // =====================
  // Station API
  // =====================
  describe('stationApi', () => {
    it('getList calls /stations/nearby with query params', async () => {
      await stationApi.getList({ latitude: 30, longitude: 120 });
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/stations/nearby', { params: { latitude: 30, longitude: 120 } });
    });

    it('getList works without query', async () => {
      await stationApi.getList();
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/stations/nearby', { params: undefined });
    });

    it('search calls /stations/search', async () => {
      await stationApi.search('test');
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/stations/search', { params: { keyword: 'test' } });
    });

    it('getDetail calls /stations/:id', async () => {
      await stationApi.getDetail(5);
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/stations/5');
    });

    it('getChargers calls /stations/:id/chargers', async () => {
      await stationApi.getChargers(3);
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/stations/3/chargers');
    });
  });

  // =====================
  // Charging API
  // =====================
  describe('chargingApi', () => {
    it('scan calls /charging/scan', async () => {
      await chargingApi.scan('CH-001');
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/charging/scan', { params: { code: 'CH-001' } });
    });

    it('start posts to /charging/start', async () => {
      const data = { chargerId: 1, vehicleId: 2 };
      await chargingApi.start(data);
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/charging/start', data);
    });

    it('stop posts to /charging/:orderId/stop', async () => {
      await chargingApi.stop(99);
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/charging/99/stop');
    });

    it('getStatus calls /charging/:orderId/status', async () => {
      await chargingApi.getStatus(42);
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/charging/42/status');
    });

    it('getActiveOrder calls /charging/active', async () => {
      await chargingApi.getActiveOrder();
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/charging/active');
    });
  });

  // =====================
  // Order API
  // =====================
  describe('orderApi', () => {
    it('getList calls /orders with params', async () => {
      await orderApi.getList({ status: 'active', page: 1, pageSize: 10 });
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/orders', { params: { status: 'active', page: 1, pageSize: 10 } });
    });

    it('getList works without params', async () => {
      await orderApi.getList();
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/orders', { params: undefined });
    });

    it('getDetail calls /orders/:id', async () => {
      await orderApi.getDetail(7);
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/orders/7');
    });

    it('cancelOrder posts to /orders/:id/cancel', async () => {
      await orderApi.cancelOrder(7);
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/orders/7/cancel');
    });
  });

  // =====================
  // Payment API
  // =====================
  describe('paymentApi', () => {
    it('pay posts to /payment/pay', async () => {
      const data = { orderId: 1, method: 'wechat' as const };
      await paymentApi.pay(data);
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/payment/pay', data);
    });

    it('getPaymentInfo calls /payment/:orderId/info', async () => {
      await paymentApi.getPaymentInfo(10);
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/payment/10/info');
    });
  });

  // =====================
  // Vehicle API
  // =====================
  describe('vehicleApi', () => {
    it('getList calls /vehicles', async () => {
      await vehicleApi.getList();
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/vehicles');
    });

    it('add posts to /vehicles', async () => {
      const data = { plate: '京A12345', brand: 'Tesla', model: 'M3', color: 'red', vin: 'VIN1', isDefault: true };
      await vehicleApi.add(data);
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/vehicles', data);
    });

    it('update puts to /vehicles/:id', async () => {
      const data = { color: 'blue' };
      await vehicleApi.update(3, data);
      expect(mockAxiosInstance.put).toHaveBeenCalledWith('/vehicles/3', data);
    });

    it('remove deletes /vehicles/:id', async () => {
      await vehicleApi.remove(3);
      expect(mockAxiosInstance.delete).toHaveBeenCalledWith('/vehicles/3');
    });

    it('setDefault posts to /vehicles/:id/default', async () => {
      await vehicleApi.setDefault(5);
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/vehicles/5/default');
    });
  });

  // =====================
  // Coupon API
  // =====================
  describe('couponApi', () => {
    it('getList calls /coupons with params', async () => {
      await couponApi.getList({ status: 'unused', page: 1, pageSize: 10 });
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/coupons', { params: { status: 'unused', page: 1, pageSize: 10 } });
    });

    it('getList works without params', async () => {
      await couponApi.getList();
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/coupons', { params: undefined });
    });

    it('getAvailable calls /coupons/available', async () => {
      await couponApi.getAvailable(42);
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/coupons/available', { params: { stationId: 42 } });
    });

    it('getAvailable works without stationId', async () => {
      await couponApi.getAvailable();
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/coupons/available', { params: { stationId: undefined } });
    });
  });

  // =====================
  // Wallet API
  // =====================
  describe('walletApi', () => {
    it('getBalance calls /wallet/balance', async () => {
      await walletApi.getBalance();
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/wallet/balance');
    });

    it('getRecords calls /wallet/records with params', async () => {
      await walletApi.getRecords({ page: 2, pageSize: 20 });
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/wallet/records', { params: { page: 2, pageSize: 20 } });
    });

    it('recharge posts to /wallet/recharge', async () => {
      await walletApi.recharge(100);
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/wallet/recharge', { amount: 100 });
    });
  });

  // =====================
  // Stats API
  // =====================
  describe('statsApi', () => {
    it('getUserStats calls /user/stats', async () => {
      await statsApi.getUserStats();
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/user/stats');
    });
  });

  // =====================
  // Interceptor Registration
  // =====================
  describe('axios instance configuration', () => {
    it('registers request and response interceptors', () => {
      // Interceptors registration happens at module import time.
      expect(mockAxiosInstance.interceptors).toBeDefined();
      expect(mockAxiosInstance.interceptors.request.use).toBeDefined();
      expect(mockAxiosInstance.interceptors.response.use).toBeDefined();
    });
  });

  // =====================
  // 401 处理器 (token 失效同步登出)
  // =====================
  describe('401 unauthorized handler', () => {
    // 模块导入时注册的响应拦截器: [onFulfilled, onRejected]
    const responseUse = mockAxiosInstance.interceptors.response.use as jest.Mock;
    const errorHandler = responseUse.mock.calls[0][1];
    const handler = jest.fn();

    afterEach(() => {
      setUnauthorizedHandler(null);
      handler.mockClear();
      mockDeleteItem.mockClear();
    });

    it('clears stored token and invokes registered handler on 401', async () => {
      setUnauthorizedHandler(handler);
      await expect(errorHandler(mockAxiosError(401))).rejects.toEqual(mockAxiosError(401));
      expect(mockDeleteItem).toHaveBeenCalledTimes(1);
      expect(handler).toHaveBeenCalledTimes(1);
    });

    it('does not invoke handler for non-401 errors', async () => {
      setUnauthorizedHandler(handler);
      await expect(errorHandler(mockAxiosError(500))).rejects.toEqual(mockAxiosError(500));
      expect(mockDeleteItem).not.toHaveBeenCalled();
      expect(handler).not.toHaveBeenCalled();
    });

    it('still rejects when no handler is registered', async () => {
      setUnauthorizedHandler(null);
      await expect(errorHandler(mockAxiosError(401))).rejects.toEqual(mockAxiosError(401));
      expect(mockDeleteItem).toHaveBeenCalledTimes(1);
    });

    it('propagates rejection even if handler throws', async () => {
      setUnauthorizedHandler(() => {
        throw new Error('handler boom');
      });
      await expect(errorHandler(mockAxiosError(401))).rejects.toEqual(mockAxiosError(401));
      expect(mockDeleteItem).toHaveBeenCalledTimes(1);
    });
  });
});
