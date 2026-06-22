// services/__tests__/api.test.js
// Mock wx APIs before loading the module
const mockWxRequest = jest.fn();
const mockGetStorageSync = jest.fn();
const mockSetStorageSync = jest.fn();
const mockRemoveStorageSync = jest.fn();
const mockShowLoading = jest.fn();
const mockHideLoading = jest.fn();
const mockShowToast = jest.fn();

global.wx = {
  request: mockWxRequest,
  getStorageSync: mockGetStorageSync,
  setStorageSync: mockSetStorageSync,
  removeStorageSync: mockRemoveStorageSync,
  showLoading: mockShowLoading,
  hideLoading: mockHideLoading,
  showToast: mockShowToast
};

const api = require('../api');
const config = require('../../config/index');

describe('API Service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetStorageSync.mockReturnValue(null);
  });

  // ========== API 实例创建和 baseURL 验证 ==========
  describe('baseURL', () => {
    it('should use API_BASE_URL from config', () => {
      expect(config.API_BASE_URL).toBeDefined();
      expect(config.API_BASE_URL).toBe('http://8.134.106.166/api/v1');
    });
  });

  // ========== request 封装 ==========
  describe('request', () => {
    describe('GET request', () => {
      it('should make a GET request with correct URL', async () => {
        mockWxRequest.mockImplementation((opts) => {
          opts.success({
            statusCode: 200,
            data: { code: 0, data: { id: 1, name: 'test' } }
          });
        });

        const result = await api.request('/test');
        expect(mockWxRequest).toHaveBeenCalledTimes(1);
        const callArgs = mockWxRequest.mock.calls[0][0];
        expect(callArgs.url).toBe(`${config.API_BASE_URL}/test`);
        expect(callArgs.method).toBe('GET');
        expect(result).toEqual({ code: 0, data: { id: 1, name: 'test' } });
      });

      it('should include Authorization header when token exists', async () => {
        mockGetStorageSync.mockReturnValue('test-token-123');
        mockWxRequest.mockImplementation((opts) => {
          opts.success({
            statusCode: 200,
            data: { code: 0, data: {} }
          });
        });

        await api.request('/test');
        const callArgs = mockWxRequest.mock.calls[0][0];
        expect(callArgs.header.Authorization).toBe('Bearer test-token-123');
      });

      it('should not include Authorization header when no token', async () => {
        mockWxRequest.mockImplementation((opts) => {
          opts.success({
            statusCode: 200,
            data: { code: 0, data: {} }
          });
        });

        await api.request('/test');
        const callArgs = mockWxRequest.mock.calls[0][0];
        expect(callArgs.header.Authorization).toBeUndefined();
      });
    });

    describe('POST request', () => {
      it('should make a POST request with body data', async () => {
        mockWxRequest.mockImplementation((opts) => {
          opts.success({
            statusCode: 200,
            data: { code: 0, data: { success: true } }
          });
        });

        const result = await api.request('/submit', {
          method: 'POST',
          data: { name: 'foo', value: 42 }
        });

        const callArgs = mockWxRequest.mock.calls[0][0];
        expect(callArgs.method).toBe('POST');
        expect(callArgs.data).toEqual({ name: 'foo', value: 42 });
        expect(result.data.success).toBe(true);
      });

      it('should set Content-Type header', async () => {
        mockWxRequest.mockImplementation((opts) => {
          opts.success({
            statusCode: 200,
            data: { code: 0, data: {} }
          });
        });

        await api.request('/submit', { method: 'POST' });
        const callArgs = mockWxRequest.mock.calls[0][0];
        expect(callArgs.header['Content-Type']).toBe('application/json');
      });
    });

    describe('loading indicator', () => {
      it('should show and hide loading when showLoading is true', async () => {
        mockWxRequest.mockImplementation((opts) => {
          opts.success({
            statusCode: 200,
            data: { code: 0, data: {} }
          });
          opts.complete && opts.complete();
        });

        await api.request('/test', { showLoading: true, loadingText: '加载中...' });
        expect(mockShowLoading).toHaveBeenCalledWith({ title: '加载中...', mask: true });
        expect(mockHideLoading).toHaveBeenCalled();
      });

      it('should not show loading when showLoading is false', async () => {
        mockWxRequest.mockImplementation((opts) => {
          opts.success({
            statusCode: 200,
            data: { code: 0, data: {} }
          });
        });

        await api.request('/test');
        expect(mockShowLoading).not.toHaveBeenCalled();
      });
    });

    describe('timeout', () => {
      it('should set timeout from config', async () => {
        mockWxRequest.mockImplementation((opts) => {
          opts.success({
            statusCode: 200,
            data: { code: 0, data: {} }
          });
        });

        await api.request('/test');
        const callArgs = mockWxRequest.mock.calls[0][0];
        expect(callArgs.timeout).toBe(config.REQUEST_TIMEOUT);
      });
    });
  });

  // ========== Token 管理 ==========
  describe('token management', () => {
    it('should read token from storage on each request', async () => {
      mockGetStorageSync.mockReturnValue('my-token');
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: {} }
        });
      });

      await api.request('/test');
      expect(mockGetStorageSync).toHaveBeenCalledWith('token');
    });

    it('should clear token on 401 response (data code)', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 401, message: 'Token expired' }
        });
      });

      await expect(api.request('/test')).rejects.toThrow('TOKEN_EXPIRED');
      expect(mockRemoveStorageSync).toHaveBeenCalledWith('token');
    });

    it('should clear token on 401 status code', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 401,
          data: {}
        });
      });

      await expect(api.request('/test')).rejects.toThrow('TOKEN_EXPIRED');
      expect(mockRemoveStorageSync).toHaveBeenCalledWith('token');
    });
  });

  // ========== 错误处理 ==========
  describe('error handling', () => {
    it('should handle network error', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.fail({ errMsg: 'request:fail net::ERR_CONNECTION_REFUSED' });
      });

      await expect(api.request('/test')).rejects.toEqual(
        expect.objectContaining({ errMsg: expect.stringContaining('ERR_CONNECTION_REFUSED') })
      );
    });

    it('should handle timeout error', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.fail({ errMsg: 'request:fail timeout' });
      });

      await expect(api.request('/test')).rejects.toEqual(
        expect.objectContaining({ errMsg: expect.stringContaining('timeout') })
      );
    });

    it('should handle business error (non-zero code)', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 500, message: '服务器内部错误' }
        });
      });

      await expect(api.request('/test')).rejects.toThrow('服务器内部错误');
    });

    it('should handle non-200 status code', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 500,
          data: {}
        });
      });

      await expect(api.request('/test')).rejects.toThrow('HTTP 500');
    });

    it('should handle 403 status code', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 403,
          data: {}
        });
      });

      await expect(api.request('/test')).rejects.toThrow('HTTP 403');
    });

    it('should handle business error without message', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 500 }
        });
      });

      await expect(api.request('/test')).rejects.toThrow('REQUEST_ERROR');
    });
  });

  // ========== login 接口 ==========
  describe('login', () => {
    it('should call login with code', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { token: 'jwt-token', user: { id: 1 } } }
        });
      });

      const result = await api.login('wx-code-abc');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/auth/login');
      expect(callArgs.method).toBe('POST');
      expect(callArgs.data).toEqual({ code: 'wx-code-abc' });
      expect(result.data.token).toBe('jwt-token');
    });

    it('should show loading during login', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: {} }
        });
      });

      await api.login('code');
      expect(mockShowLoading).toHaveBeenCalledWith({ title: '登录中...', mask: true });
    });
  });

  // ========== stations 接口 ==========
  describe('stations', () => {
    it('getNearbyStations should pass lat/lng/radius', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: [] }
        });
      });

      await api.getNearbyStations(30.5, 120.5, 3000);
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/stations/nearby');
      expect(callArgs.data).toEqual({ lat: 30.5, lng: 120.5, radius: 3000 });
    });

    it('getNearbyStations should use default radius', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: [] }
        });
      });

      await api.getNearbyStations(30.5, 120.5);
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.data.radius).toBe(5000);
    });

    it('getStationDetail should fetch by id', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { id: 'st-1', name: 'Station A' } }
        });
      });

      const result = await api.getStationDetail('st-1');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/stations/st-1');
      expect(result.data.name).toBe('Station A');
    });

    it('searchStations should pass keyword', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: [] }
        });
      });

      await api.searchStations('西湖');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.data).toEqual({ keyword: '西湖' });
    });
  });

  // ========== charging 接口 ==========
  describe('charging', () => {
    it('startCharging should send chargerId', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { sessionId: 'sess-1' } }
        });
      });

      const result = await api.startCharging('charger-001');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.data).toEqual({ chargerId: 'charger-001' });
      expect(result.data.sessionId).toBe('sess-1');
    });

    it('getChargingStatus should fetch by sessionId', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { power: 5.2, cost: 3.5 } }
        });
      });

      const result = await api.getChargingStatus('sess-1');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/charging/status/sess-1');
      expect(result.data.power).toBe(5.2);
    });

    it('stopCharging should send sessionId', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { success: true } }
        });
      });

      await api.stopCharging('sess-1');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.data).toEqual({ sessionId: 'sess-1' });
    });
  });

  // ========== orders 接口 ==========
  describe('orders', () => {
    it('getOrders should pass pagination params', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { list: [], total: 0 } }
        });
      });

      await api.getOrders({ page: 2, pageSize: 20 });
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.data).toEqual({ page: 2, pageSize: 20 });
    });

    it('getOrders should use default pagination', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { list: [], total: 0 } }
        });
      });

      await api.getOrders();
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.data).toEqual({ page: 1, pageSize: 10 });
    });

    it('getOrders should include status filter when provided', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { list: [], total: 0 } }
        });
      });

      await api.getOrders({ status: 'finished' });
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.data).toEqual({ page: 1, pageSize: 10, status: 'finished' });
    });

    it('getOrderDetail should fetch by orderId', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { id: 'ord-1', amount: 25.5 } }
        });
      });

      const result = await api.getOrderDetail('ord-1');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/orders/ord-1');
      expect(result.data.amount).toBe(25.5);
    });
  });

  // ========== payment 接口 ==========
  describe('payment', () => {
    it('createPayment should send orderId', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { payId: 'pay-1', amount: 25.5 } }
        });
      });

      const result = await api.createPayment('ord-1');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.data).toEqual({ orderId: 'ord-1' });
      expect(result.data.payId).toBe('pay-1');
    });

    it('queryPaymentStatus should fetch by orderId', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { status: 'paid' } }
        });
      });

      const result = await api.queryPaymentStatus('ord-1');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/payment/status/ord-1');
      expect(result.data.status).toBe('paid');
    });
  });

  // ========== 导出完整性 ==========
  describe('module exports', () => {
    it('should export all expected functions', () => {
      expect(api.request).toBeDefined();
      expect(api.login).toBeDefined();
      expect(api.getUserInfo).toBeDefined();
      expect(api.updateUserInfo).toBeDefined();
      expect(api.getNearbyStations).toBeDefined();
      expect(api.getStationDetail).toBeDefined();
      expect(api.searchStations).toBeDefined();
      expect(api.filterStations).toBeDefined();
      expect(api.getFavorites).toBeDefined();
      expect(api.addFavorite).toBeDefined();
      expect(api.removeFavorite).toBeDefined();
      expect(api.startCharging).toBeDefined();
      expect(api.getChargingStatus).toBeDefined();
      expect(api.stopCharging).toBeDefined();
      expect(api.getOrders).toBeDefined();
      expect(api.getOrderDetail).toBeDefined();
      expect(api.reviewOrder).toBeDefined();
      expect(api.createPayment).toBeDefined();
      expect(api.queryPaymentStatus).toBeDefined();
      expect(api.getWallet).toBeDefined();
      expect(api.recharge).toBeDefined();
      expect(api.getTransactions).toBeDefined();
      expect(api.getCoupons).toBeDefined();
      expect(api.claimCoupon).toBeDefined();
      expect(api.useCoupon).toBeDefined();
      expect(api.getPoints).toBeDefined();
      expect(api.getPointsHistory).toBeDefined();
      expect(api.dailySignIn).toBeDefined();
      expect(api.redeemPoints).toBeDefined();
      expect(api.getNotifications).toBeDefined();
      expect(api.markNotificationRead).toBeDefined();
      expect(api.markAllNotificationsRead).toBeDefined();
      expect(api.getUnreadNotificationCount).toBeDefined();
    });
  });

  // ========== P1: 站点筛选 ==========
  describe('station filters', () => {
    it('filterStations should pass filter params', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { list: [], total: 0 } }
        });
      });

      await api.filterStations({ lat: 30.5, lng: 120.5, gunType: 'dc', sortBy: 'price', page: 2, pageSize: 15 });
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/stations/filter');
      expect(callArgs.data).toEqual({ lat: 30.5, lng: 120.5, gunType: 'dc', sortBy: 'price', radius: 5000, page: 2, pageSize: 15 });
    });

    it('filterStations should use defaults', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { list: [], total: 0 } }
        });
      });

      await api.filterStations({ lat: 30, lng: 120 });
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.data.page).toBe(1);
      expect(callArgs.data.pageSize).toBe(20);
      expect(callArgs.data.radius).toBe(5000);
    });
  });

  // ========== P1: 收藏接口 ==========
  describe('favorites', () => {
    it('getFavorites should fetch favorites list', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: [{ id: 's1', name: 'Station A' }] }
        });
      });

      const result = await api.getFavorites();
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/user/favorites');
      expect(result.data[0].name).toBe('Station A');
    });

    it('addFavorite should POST stationId', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { success: true } }
        });
      });

      await api.addFavorite('st-123');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.data).toEqual({ stationId: 'st-123' });
    });

    it('removeFavorite should DELETE by stationId', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { success: true } }
        });
      });

      await api.removeFavorite('st-123');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('DELETE');
      expect(callArgs.url).toContain('/user/favorites/st-123');
    });
  });

  // ========== P1: 订单评价 ==========
  describe('review order', () => {
    it('reviewOrder should POST rating and comment', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { success: true } }
        });
      });

      await api.reviewOrder('ord-1', 5, 'Great service!');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.url).toContain('/orders/ord-1/review');
      expect(callArgs.data).toEqual({ rating: 5, comment: 'Great service!' });
    });
  });

  // ========== P1: 优惠券接口 ==========
  describe('coupons', () => {
    it('getCoupons should fetch with optional status', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: [] }
        });
      });

      await api.getCoupons('unused');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/coupons');
      expect(callArgs.data).toEqual({ status: 'unused' });
    });

    it('getCoupons should omit status when not provided', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: [] }
        });
      });

      await api.getCoupons();
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.data).toEqual({});
    });

    it('claimCoupon should POST couponCode', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { success: true } }
        });
      });

      await api.claimCoupon('COUPON123');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.data).toEqual({ couponCode: 'COUPON123' });
    });

    it('useCoupon should POST couponId and orderId', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { success: true } }
        });
      });

      await api.useCoupon('coup-1', 'ord-1');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.data).toEqual({ couponId: 'coup-1', orderId: 'ord-1' });
    });
  });

  // ========== P1: 积分接口 ==========
  describe('points', () => {
    it('getPoints should fetch points info', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { points: 500, signInDays: 7 } }
        });
      });

      const result = await api.getPoints();
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/points/info');
      expect(result.data.points).toBe(500);
    });

    it('getPointsHistory should pass page', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: [] }
        });
      });

      await api.getPointsHistory(3);
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.data).toEqual({ page: 3, pageSize: 20 });
    });

    it('dailySignIn should POST', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { points: 5 } }
        });
      });

      await api.dailySignIn();
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.url).toContain('/points/sign-in');
    });

    it('redeemPoints should POST rewardId', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { success: true } }
        });
      });

      await api.redeemPoints('reward-1');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.data).toEqual({ rewardId: 'reward-1' });
    });
  });

  // ========== P1: 通知接口 ==========
  describe('notifications', () => {
    it('getNotifications should pass page and optional type', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { list: [], total: 0 } }
        });
      });

      await api.getNotifications(2, 'system');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.url).toContain('/notifications');
      expect(callArgs.data).toEqual({ page: 2, pageSize: 20, type: 'system' });
    });

    it('markNotificationRead should POST to mark single', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: {} }
        });
      });

      await api.markNotificationRead('notif-1');
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.url).toContain('/notifications/notif-1/read');
    });

    it('markAllNotificationsRead should POST', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: {} }
        });
      });

      await api.markAllNotificationsRead();
      const callArgs = mockWxRequest.mock.calls[0][0];
      expect(callArgs.method).toBe('POST');
      expect(callArgs.url).toContain('/notifications/read-all');
    });

    it('getUnreadNotificationCount should return count', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({
          statusCode: 200,
          data: { code: 0, data: { count: 5 } }
        });
      });

      const result = await api.getUnreadNotificationCount();
      expect(result.data.count).toBe(5);
    });
  });
});
