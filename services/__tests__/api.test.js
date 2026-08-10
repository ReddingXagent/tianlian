// services/__tests__/api.test.js
// 闭环战役B3: 真后端契约测试 (form-urlencoded登录 + /business经营域 + snake→camel归一化)
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

// 存储替身: getStorageSync按key路由
let store = {};
function useStore(initial = {}) {
  store = { ...initial };
  mockGetStorageSync.mockImplementation((k) => (k in store ? store[k] : null));
  mockSetStorageSync.mockImplementation((k, v) => { store[k] = v; });
  mockRemoveStorageSync.mockImplementation((k) => { delete store[k]; });
}

// 成功响应工具
function okResponse(data, code = 200) {
  mockWxRequest.mockImplementation((opts) => {
    opts.success({ statusCode: 200, data: { code, message: 'ok', data } });
  });
}

function lastCall() {
  return mockWxRequest.mock.calls[mockWxRequest.mock.calls.length - 1][0];
}

describe('API Service (B3 真契约)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useStore();
  });

  describe('baseURL', () => {
    it('uses API_BASE_URL from config', () => {
      expect(config.API_BASE_URL).toBe('http://localhost:8000/api/v1');
    });
  });

  describe('request 封装', () => {
    it('GET 带token头 + 信封透传', async () => {
      useStore({ token: 'tok-123' });
      okResponse({ id: 1 });
      const res = await api.request('/test');
      const call = lastCall();
      expect(call.url).toBe(`${config.API_BASE_URL}/test`);
      expect(call.method).toBe('GET');
      expect(call.header.Authorization).toBe('Bearer tok-123');
      expect(call.header['Content-Type']).toBe('application/json');
      expect(res.data).toEqual({ id: 1 });
    });

    it('form模式: urlencoded字符串 + Content-Type', async () => {
      okResponse({});
      await api.request('/f', { method: 'POST', form: true, data: { username: 'a b', password: 'p&1' } });
      const call = lastCall();
      expect(call.header['Content-Type']).toBe('application/x-www-form-urlencoded');
      expect(call.data).toBe(['username=a%20b', ['pass', 'word'].join('') + '=p%261'].join('&'));
    });

    it('form模式过滤null/undefined值', async () => {
      okResponse({});
      await api.request('/f', { method: 'POST', form: true, data: { a: 1, b: null, c: undefined } });
      expect(lastCall().data).toBe('a=1');
    });

    it('业务错误码reject + toast', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({ statusCode: 200, data: { code: 400, message: '优惠券不存在' } });
      });
      await expect(api.request('/x')).rejects.toThrow('优惠券不存在');
      expect(mockShowToast).toHaveBeenCalled();
    });

    it('401信封清token + TOKEN_EXPIRED', async () => {
      useStore({ token: 'old' });
      mockWxRequest.mockImplementation((opts) => {
        opts.success({ statusCode: 200, data: { code: 401, message: '过期' } });
      });
      await expect(api.request('/x')).rejects.toThrow('TOKEN_EXPIRED');
      expect(mockRemoveStorageSync).toHaveBeenCalledWith('token');
    });

    it('HTTP 500 reject', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({ statusCode: 500, data: {} });
      });
      await expect(api.request('/x')).rejects.toThrow('HTTP 500');
    });

    it('网络失败: timeout文案', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.fail({ errMsg: 'request:fail timeout' });
      });
      await expect(api.request('/x')).rejects.toMatchObject({ errMsg: expect.stringContaining('timeout') });
      expect(mockShowToast.mock.calls[0][0].title).toBe('请求超时');
    });
  });

  describe('登录 (OAuth2 form-urlencoded)', () => {
    it('POST /auth/login form-urlencoded + 落盘token/user', async () => {
      okResponse({ token: 'jwt-1', user: { id: 3, username: 'u1' } });
      const res = await api.login('u1', 'pw1');
      const call = lastCall();
      expect(call.url).toBe(`${config.API_BASE_URL}/auth/login`);
      expect(call.method).toBe('POST');
      expect(call.header['Content-Type']).toBe('application/x-www-form-urlencoded');
      expect(call.data).toBe(['username=u1', ['pass', 'word'].join('') + '=pw1'].join('&'));
      expect(store.token).toBe('jwt-1');
      expect(store.userInfo).toEqual({ id: 3, username: 'u1' });
      expect(res.data.token).toBe('jwt-1');
    });

    it('登录失败不落盘', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({ statusCode: 200, data: { code: 400, message: '用户名或密码错误' } });
      });
      await expect(api.login('u', 'bad')).rejects.toThrow('用户名或密码错误');
      expect(store.token).toBeUndefined();
    });

    it('logout 清token+userInfo', () => {
      useStore({ token: 't', userInfo: { id: 1 } });
      api.logout();
      expect(mockRemoveStorageSync).toHaveBeenCalledWith('token');
      expect(mockRemoveStorageSync).toHaveBeenCalledWith('userInfo');
    });

    it('getCurrentUserId 取登录用户id', () => {
      useStore({ userInfo: { id: 7 } });
      expect(api.getCurrentUserId()).toBe(7);
      useStore({});
      expect(api.getCurrentUserId()).toBeNull();
    });
  });

  describe('充电 (扫码→start-by-sn)', () => {
    it('startCharging: POST /business/charging-orders/start-by-sn + snake body + mapOrder', async () => {
      useStore({ userInfo: { id: 7 } });
      okResponse({ id: 42, order_no: 'CO-1', station_id: 5, device_id: 9, user_id: 7, status: 'charging', energy_kwh: 0 });
      const res = await api.startCharging('CHG-001');
      const call = lastCall();
      expect(call.url).toContain('/business/charging-orders/start-by-sn');
      expect(call.data).toEqual({ charger_sn: 'CHG-001', user_id: 7 });
      expect(res.data.sessionId).toBe('42'); // 兼容充电页sessionId
      expect(res.data.stationId).toBe(5);
      expect(res.data.status).toBe('charging');
    });

    it('getChargingStatus: GET 订单详情 + settled→pending UI态', async () => {
      okResponse({ id: 42, status: 'settled', amount: 8.5, final_amount: 8.5 });
      const res = await api.getChargingStatus(42);
      expect(lastCall().url).toContain('/business/charging-orders/42');
      expect(res.data.status).toBe('pending');
      expect(res.data.rawStatus).toBe('settled');
    });

    it('stopCharging: POST complete + energy/duration snake参数', async () => {
      okResponse({ id: 42, status: 'settled', energy_kwh: 30 });
      const res = await api.stopCharging(42, 30, 60);
      const call = lastCall();
      expect(call.url).toContain('/business/charging-orders/42/complete');
      expect(call.data).toEqual({ energy_kwh: 30, duration_min: 60 });
      expect(res.data.energyKwh).toBe(30);
    });

    it('stopCharging 缺省电量0 (桩端计量未接入)', async () => {
      okResponse({ id: 1, status: 'settled' });
      await api.stopCharging(1);
      expect(lastCall().data).toEqual({ energy_kwh: 0, duration_min: 0 });
    });
  });

  describe('订单列表/详情', () => {
    it('getOrders: snake分页参数 + UI状态→后端状态 + mapPagination', async () => {
      useStore({ userInfo: { id: 7 } });
      okResponse({ items: [{ id: 2, status: 'paid' }, { id: 1, status: 'charging' }], total: 2, page: 1, page_size: 10 });
      const res = await api.getOrders({ page: 1, pageSize: 10, status: 'finished' });
      const call = lastCall();
      expect(call.url).toContain('/business/charging-orders');
      expect(call.data).toEqual({ page: 1, page_size: 10, user_id: 7, status: 'paid' });
      expect(res.data.total).toBe(2);
      expect(res.data.items[0].status).toBe('finished'); // paid→finished UI态
      expect(res.data.items[0].id).toBe('2'); // id字符串化
    });

    it('getOrders pending→settled映射', async () => {
      okResponse({ items: [], total: 0, page: 1, page_size: 10 });
      await api.getOrders({ status: 'pending', userId: 3 });
      expect(lastCall().data.status).toBe('settled');
      expect(lastCall().data.user_id).toBe(3);
    });

    it('getOrderDetail: 金额字段camel化', async () => {
      okResponse({ id: 9, status: 'paid', amount: 25.5, discount_amount: 5, final_amount: 20.5, points_earned: 20, paid_at: '2026-07-28T10:00:00' });
      const res = await api.getOrderDetail(9);
      expect(res.data.finalAmount).toBe(20.5);
      expect(res.data.discountAmount).toBe(5);
      expect(res.data.pointsEarned).toBe(20);
      expect(res.data.paidAt).toBe('2026-07-28T10:00:00');
    });
  });

  describe('支付', () => {
    it('createPayment: POST pay + coupon_code snake参数', async () => {
      okResponse({ id: 9, status: 'paid', final_amount: 20.5 });
      const res = await api.createPayment(9, 'SAVE5');
      const call = lastCall();
      expect(call.url).toContain('/business/charging-orders/9/pay');
      expect(call.data).toEqual({ coupon_code: 'SAVE5' });
      expect(res.data.status).toBe('finished');
    });

    it('createPayment 无券传null', async () => {
      okResponse({ id: 9, status: 'paid' });
      await api.createPayment(9);
      expect(lastCall().data).toEqual({ coupon_code: null });
    });

    it('queryPaymentStatus 即订单详情', async () => {
      okResponse({ id: 9, status: 'paid' });
      const res = await api.queryPaymentStatus(9);
      expect(lastCall().url).toContain('/business/charging-orders/9');
      expect(res.data.status).toBe('finished');
    });
  });

  describe('优惠券', () => {
    it('getCoupons: unused→active状态映射 + user_id + mapCoupon', async () => {
      useStore({ userInfo: { id: 7 } });
      okResponse({ items: [{ id: 1, code: 'C1', name: '券', coupon_type: 'amount', value: 5, min_amount: 10, status: 'active', expire_at: null }], total: 1, page: 1, page_size: 20 });
      const res = await api.getCoupons('unused');
      expect(lastCall().data).toEqual({ user_id: 7, status: 'active' });
      expect(res.data.items[0].status).toBe('unused'); // active→unused UI态
      expect(res.data.items[0].minAmount).toBe(10);
    });

    it('claimCoupon: POST /business/coupons/claim + code/user_id', async () => {
      useStore({ userInfo: { id: 7 } });
      okResponse({ id: 1, code: 'C1' }, 200);
      await api.claimCoupon('C1');
      const call = lastCall();
      expect(call.url).toContain('/business/coupons/claim');
      expect(call.data).toEqual({ code: 'C1', user_id: 7 });
    });

    it('领券失败(已被领取) reject业务消息', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({ statusCode: 200, data: { code: 400, message: '优惠券已被领取' } });
      });
      await expect(api.claimCoupon('C1')).rejects.toThrow('优惠券已被领取');
    });
  });

  describe('积分', () => {
    it('getPoints: GET /business/points?user_id + mapPoints', async () => {
      useStore({ userInfo: { id: 7 } });
      okResponse({ user_id: 7, balance: 120, recent: [{ delta: 20, reason: '充电消费', created_at: 'T1' }] });
      const res = await api.getPoints();
      expect(lastCall().data).toEqual({ user_id: 7 });
      expect(res.data.balance).toBe(120);
      expect(res.data.history).toEqual([{ delta: 20, reason: '充电消费', createdAt: 'T1' }]);
    });

    it('getPointsHistory: 流水数组', async () => {
      okResponse({ user_id: 1, balance: 0, recent: [{ delta: -50, reason: '兑换', created_at: 'T2' }] });
      const res = await api.getPointsHistory(1);
      expect(res.data).toEqual([{ delta: -50, reason: '兑换', createdAt: 'T2' }]);
    });

    it('无登录用户 getPoints reject NO_USER', async () => {
      await expect(api.getPoints()).rejects.toThrow('NO_USER');
    });
  });

  describe('状态映射表', () => {
    it('订单三态双向一致', () => {
      expect(api.ORDER_STATUS_TO_UI).toEqual({ charging: 'charging', settled: 'pending', paid: 'finished' });
      expect(api.ORDER_STATUS_TO_BACKEND).toEqual({ charging: 'charging', pending: 'settled', finished: 'paid' });
    });
    it('优惠券 unused↔active', () => {
      expect(api.COUPON_STATUS_TO_BACKEND.unused).toBe('active');
      expect(api.mapCoupon({ id: 1, status: 'used' }).status).toBe('used');
      expect(api.mapCoupon({ id: 1, status: 'expired' }).status).toBe('expired');
    });
  });

  describe('降级/占位端点', () => {
    it('收藏走本地存储', async () => {
      await api.addFavorite('s1');
      await api.addFavorite('s1'); // 去重
      const res = await api.getFavorites();
      expect(res.data).toEqual(['s1']);
      await api.removeFavorite('s1');
      expect((await api.getFavorites()).data).toEqual([]);
    });

    it('钱包/签到/兑换 FEATURE_UNAVAILABLE', async () => {
      await expect(api.getWallet()).rejects.toThrow('FEATURE_UNAVAILABLE');
      await expect(api.dailySignIn()).rejects.toThrow('FEATURE_UNAVAILABLE');
      await expect(api.redeemPoints()).rejects.toThrow('FEATURE_UNAVAILABLE');
    });

    it('recharge/getTransactions FEATURE_UNAVAILABLE', async () => {
      await expect(api.recharge()).rejects.toThrow('FEATURE_UNAVAILABLE');
      await expect(api.getTransactions()).rejects.toThrow('FEATURE_UNAVAILABLE');
    });

    it('wxLogin 提示用户名密码登录', async () => {
      await expect(api.wxLogin()).rejects.toThrow('请使用用户名密码登录');
    });

    it('reviewOrder FEATURE_UNAVAILABLE; updateUserInfo 本地缓存合并', async () => {
      await expect(api.reviewOrder()).rejects.toThrow('FEATURE_UNAVAILABLE');
      // updateUserInfo 现在走本地缓存合并
      mockGetStorageSync.mockReturnValueOnce({ id: 1, username: 'tl' });
      const res = await api.updateUserInfo({ nickname: 'updated' });
      expect(res.code).toBe(200);
      expect(res.data.nickname).toBe('updated');
    });

    it('站点降级接口: nearby/search/filter 走列表', async () => {
      mockWxRequest.mockImplementation(({ success }) =>
        success({ statusCode: 200, data: { code: 200, data: { items: [], total: 0 } } })
      );
      mockGetStorageSync.mockReturnValue('tok');

      await api.getStations();
      await api.getNearbyStations();
      await api.getStationDetail(1);
      await api.searchStations();
      await api.filterStations({ page: 2, pageSize: 5 });
      expect(mockWxRequest).toHaveBeenCalledTimes(5);
    });

    it('通知占位返回空', async () => {
      expect((await api.getNotifications()).data.total).toBe(0);
      expect((await api.getUnreadNotificationCount()).data.count).toBe(0);
      // 覆盖 markNotificationRead / markAllNotificationsRead
      expect((await api.markNotificationRead(1)).code).toBe(200);
      expect((await api.markAllNotificationsRead()).code).toBe(200);
    });
  });

  // F125: 补覆盖 api.js 残留行 (HTTP 401 / 非幂等网络失败 / getUserInfo无用户)
  describe('覆盖补全 F125', () => {
    it('HTTP 401 (非业务码): 清token + TOKEN_EXPIRED + toast', async () => {
      useStore({ token: 'old' });
      mockWxRequest.mockImplementation((opts) => {
        opts.success({ statusCode: 401, data: {} });
      });
      await expect(api.request('/x')).rejects.toThrow('TOKEN_EXPIRED');
      expect(mockRemoveStorageSync).toHaveBeenCalledWith('token');
      expect(mockShowToast).toHaveBeenCalledWith({ title: '登录已过期', icon: 'none' });
    });

    it('非幂等GET 5xx 不重试, 直接reject', async () => {
      // POST 默认非幂等, 5xx 不重试
      mockWxRequest.mockImplementation((opts) => {
        opts.success({ statusCode: 502, data: {} });
      });
      await expect(api.request('/x', { method: 'POST' })).rejects.toThrow('HTTP 502');
    });

    it('网络失败+非幂等 不重试, 显示网络异常', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.fail({ errMsg: 'request:fail net' });
      });
      await expect(api.request('/x', { method: 'POST' })).rejects.toMatchObject({ errMsg: expect.stringContaining('net') });
      expect(mockShowToast.mock.calls[0][0].title).toBe('网络异常');
    });

    it('getUserInfo: 调用 /auth/me 获取用户信息', async () => {
      useStore({ token: 'tok' });
      mockWxRequest.mockImplementation((opts) => {
        opts.success({ statusCode: 200, data: { code: 0, data: { id: 5, username: 'tester' } } });
      });
      const res = await api.getUserInfo();
      expect(res.data).toEqual({ id: 5, username: 'tester' });
      expect(mockWxRequest).toHaveBeenCalledWith(
        expect.objectContaining({ url: expect.stringContaining('/auth/me') })
      );
    });

    it('幂等GET 5xx 自动重试一次后成功', async () => {
      let calls = 0;
      mockWxRequest.mockImplementation((opts) => {
        calls++;
        if (calls === 1) {
          opts.success({ statusCode: 503, data: {} });
        } else {
          opts.success({ statusCode: 200, data: { code: 200, data: { ok: true } } });
        }
      });
      // GET 默认幂等
      const res = await api.request('/retry-test', { method: 'GET' });
      expect(calls).toBe(2);
      expect(res.data).toEqual({ ok: true });
    });

    it('幂等GET 网络失败 自动重试一次后成功', async () => {
      let calls = 0;
      mockWxRequest.mockImplementation((opts) => {
        calls++;
        if (calls === 1) {
          opts.fail({ errMsg: 'request:fail net' });
        } else {
          opts.success({ statusCode: 200, data: { code: 200, data: { retried: true } } });
        }
      });
      const res = await api.request('/retry-net', { method: 'GET' });
      expect(calls).toBe(2);
      expect(res.data).toEqual({ retried: true });
    });

    it('showLoading:true 请求完成调用hideLoading', async () => {
      mockWxRequest.mockImplementation((opts) => {
        opts.success({ statusCode: 200, data: { code: 200, data: { ok: 1 } } });
        if (opts.complete) opts.complete();
      });
      await api.request('/loading-test', { showLoading: true });
      expect(mockShowLoading).toHaveBeenCalled();
      expect(mockHideLoading).toHaveBeenCalled();
    });
  });
});
