// services/__tests__/api.ext2.test.js
// F663: api.js branches 78→100% 覆盖率提升
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

let store = {};
function useStore(initial = {}) {
  store = { ...initial };
  mockGetStorageSync.mockImplementation((k) => (k in store ? store[k] : null));
  mockSetStorageSync.mockImplementation((k, v) => { store[k] = v; });
  mockRemoveStorageSync.mockImplementation((k) => { delete store[k]; });
}

function okResponse(data, code = 200) {
  mockWxRequest.mockImplementation((opts) => {
    opts.success({ statusCode: 200, data: { code, message: 'ok', data } });
  });
}

function lastCall() {
  return mockWxRequest.mock.calls[mockWxRequest.mock.calls.length - 1][0];
}

describe('api.ext2: branches 78→100%', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useStore();
  });

  // === request 封装残留分支 ===

  it('resData.code === 0 也能resolve', async () => {
    mockWxRequest.mockImplementation((opts) => {
      opts.success({ statusCode: 200, data: { code: 0, data: { ok: 1 } } });
    });
    const res = await api.request('/zero-code');
    expect(res.data).toEqual({ ok: 1 });
  });

  it('业务错误码 code=500: message fallback to REQUEST_ERROR', async () => {
    mockWxRequest.mockImplementation((opts) => {
      opts.success({ statusCode: 200, data: { code: 500 } });
    });
    await expect(api.request('/x')).rejects.toThrow('REQUEST_ERROR');
  });

  it('HTTP 403 reject with HTTP 403', async () => {
    mockWxRequest.mockImplementation((opts) => {
      opts.success({ statusCode: 403, data: {} });
    });
    await expect(api.request('/x')).rejects.toThrow('HTTP 403');
  });

  it('HTTP 5xx 幂等GET 重试后仍失败 → reject HTTP 5xx', async () => {
    let calls = 0;
    mockWxRequest.mockImplementation((opts) => {
      calls++;
      opts.success({ statusCode: 503, data: {} });
    });
    await expect(api.request('/x', { method: 'GET' })).rejects.toThrow('HTTP 503');
    expect(calls).toBe(2); // 初次 + 1次重试
  });

  it('网络失败 幂等GET 重试后仍失败 → reject', async () => {
    let calls = 0;
    mockWxRequest.mockImplementation((opts) => {
      calls++;
      opts.fail({ errMsg: 'request:fail timeout' });
    });
    await expect(api.request('/x', { method: 'GET' })).rejects.toMatchObject({ errMsg: expect.stringContaining('timeout') });
    expect(calls).toBe(2);
  });

  it('网络失败 非timeout → 显示网络异常', async () => {
    mockWxRequest.mockImplementation((opts) => {
      opts.fail({ errMsg: 'request:fail dns' });
    });
    await expect(api.request('/x', { method: 'POST' })).rejects.toMatchObject({ errMsg: expect.stringContaining('dns') });
    expect(mockShowToast.mock.calls[0][0].title).toBe('网络异常');
  });

  it('header参数传入: 自定义header合并', async () => {
    okResponse({});
    await api.request('/h', { header: { 'X-Custom': 'val' } });
    const call = lastCall();
    expect(call.header['X-Custom']).toBe('val');
  });

  it('showLoading + 自定义loadingText', async () => {
    mockWxRequest.mockImplementation((opts) => {
      opts.success({ statusCode: 200, data: { code: 200, data: {} } });
      if (opts.complete) opts.complete();
    });
    await api.request('/lt', { showLoading: true, loadingText: '自定义' });
    expect(mockShowLoading).toHaveBeenCalledWith({ title: '自定义', mask: true });
    expect(mockHideLoading).toHaveBeenCalled();
  });

  it('complete回调: showLoading=false 时不调用hideLoading', async () => {
    mockWxRequest.mockImplementation((opts) => {
      opts.success({ statusCode: 200, data: { code: 200, data: {} } });
      if (opts.complete) opts.complete();
    });
    await api.request('/no-loading');
    expect(mockHideLoading).not.toHaveBeenCalled();
  });

  // === login 残留分支 ===

  it('login成功但响应无token: 不落盘', async () => {
    okResponse({ user: { id: 1 } });
    await api.login('u', 'p');
    expect(store.token).toBeUndefined();
    expect(store.userInfo).toEqual({ id: 1 });
  });

  it('login成功但响应无user: 不落盘userInfo', async () => {
    okResponse({ token: 'tok' });
    await api.login('u', 'p');
    expect(store.token).toBe('tok');
    expect(store.userInfo).toBeUndefined();
  });

  // === map归一化函数残留分支 ===

  it('mapOrder(null) → null', () => {
    expect(api.mapOrder(null)).toBeNull();
  });

  it('mapOrder: 未知status原样透传', () => {
    const o = api.mapOrder({ id: 1, status: 'cancelled', order_no: 'O1' });
    expect(o.status).toBe('cancelled');
    expect(o.rawStatus).toBe('cancelled');
  });

  it('mapOrder: 缺失可选字段 → undefined', () => {
    const o = api.mapOrder({ id: 5, status: 'charging' });
    expect(o.orderNo).toBeUndefined();
    expect(o.energyKwh).toBeUndefined();
    expect(o.durationMin).toBeUndefined();
    expect(o.amount).toBeUndefined();
  });

  it('mapCoupon(null) → null', () => {
    expect(api.mapCoupon(null)).toBeNull();
  });

  it('mapPoints(null) → null', () => {
    expect(api.mapPoints(null)).toBeNull();
  });

  it('mapPoints: 无recent字段 → history空数组', () => {
    const p = api.mapPoints({ user_id: 1, balance: 100 });
    expect(p.history).toEqual([]);
  });

  it('mapPagination: 缺失items/total/page/page_size → 默认值', () => {
    const d = api.mapPagination({}, () => ({}));
    expect(d.items).toEqual([]);
    expect(d.total).toBe(0);
    expect(d.page).toBe(1);
    expect(d.pageSize).toBe(20);
  });

  // === getOrders 无userId分支 ===

  it('getOrders: 无登录用户 uid=null → query不含user_id', async () => {
    useStore({});
    okResponse({ items: [], total: 0 });
    await api.getOrders({ page: 2 });
    expect(lastCall().data).toEqual({ page: 2, page_size: 10 });
    // user_id should not be in query since uid is null
    expect(lastCall().data.user_id).toBeUndefined();
  });

  it('getOrders: 无status参数 → query不含status', async () => {
    useStore({ userInfo: { id: 3 } });
    okResponse({ items: [], total: 0 });
    await api.getOrders({ page: 1 });
    expect(lastCall().data.status).toBeUndefined();
  });

  // === getCoupons 残留分支 ===

  it('getCoupons: 无status → query不含status', async () => {
    useStore({ userInfo: { id: 7 } });
    okResponse({ items: [], total: 0 });
    await api.getCoupons();
    expect(lastCall().data.user_id).toBe(7);
    expect(lastCall().data.status).toBeUndefined();
  });

  it('getCoupons: 无登录用户 → query不含user_id', async () => {
    useStore({});
    okResponse({ items: [], total: 0 });
    await api.getCoupons('unused');
    expect(lastCall().data.user_id).toBeUndefined();
    expect(lastCall().data.status).toBe('active');
  });

  it('getCoupons: 未知status原样透传', async () => {
    useStore({});
    okResponse({ items: [], total: 0 });
    await api.getCoupons('custom_status');
    expect(lastCall().data.status).toBe('custom_status');
  });

  // === getPoints 残留分支 ===

  it('getPoints: 显式传入userId', async () => {
    okResponse({ user_id: 42, balance: 500, recent: [] });
    const res = await api.getPoints(42);
    expect(lastCall().data).toEqual({ user_id: 42 });
    expect(res.data.balance).toBe(500);
    expect(res.data.history).toEqual([]);
  });

  it('getPoints: 无userId且无登录 → reject NO_USER', async () => {
    useStore({});
    await expect(api.getPoints()).rejects.toThrow('NO_USER');
  });

  // === getCurrentUserId 边界 ===

  it('getCurrentUserId: user.id显式null → 返回null', () => {
    useStore({ userInfo: { id: null } });
    expect(api.getCurrentUserId()).toBeNull();
  });

  // === form模式残留 ===

  it('form模式: data含0/false → 不被过滤', async () => {
    okResponse({});
    await api.request('/f', { method: 'POST', form: true, data: { a: 0, b: false } });
    // 0 and false are !== null && !== undefined, so they should pass the filter
    const payload = lastCall().data;
    expect(payload).toContain('a=0');
    expect(payload).toContain('b=false');
  });

  // === getStationDetail ===

  it('getStationDetail: URL包含stationId', async () => {
    okResponse({ id: 99, name: '站' });
    const res = await api.getStationDetail(99);
    expect(lastCall().url).toContain('/stations/99');
    expect(res.data.id).toBe(99);
  });

  // === filterStations ===

  it('filterStations: 传递分页参数', async () => {
    okResponse({ items: [], total: 0 });
    await api.filterStations({ page: 3, pageSize: 15 });
    // filterStations calls getStations which calls request
    expect(lastCall().data).toEqual({ page: 3, page_size: 15 });
  });

  // === getNearbyStations / searchStations 降级 ===

  it('getNearbyStations: 降级为列表', async () => {
    okResponse({ items: [], total: 0 });
    await api.getNearbyStations();
    expect(lastCall().url).toContain('/stations');
  });

  it('searchStations: 降级为列表', async () => {
    okResponse({ items: [], total: 0 });
    await api.searchStations();
    expect(lastCall().url).toContain('/stations');
  });

  // === getPointsHistory 显式userId ===

  it('getPointsHistory: 显式userId透传', async () => {
    okResponse({ user_id: 55, balance: 0, recent: [{ delta: 10, reason: 'test', created_at: 'T' }] });
    const res = await api.getPointsHistory(55);
    expect(lastCall().data).toEqual({ user_id: 55 });
    expect(res.data).toEqual([{ delta: 10, reason: 'test', createdAt: 'T' }]);
  });

  // === getUserInfo: 调用 /auth/me ===

  it('getUserInfo: 调用 /auth/me 并更新缓存', async () => {
    useStore({ token: 'tok' });
    mockWxRequest.mockImplementation((opts) => {
      opts.success({ statusCode: 200, data: { code: 0, data: { id: 5, name: 'test' } } });
    });
    const res = await api.getUserInfo();
    expect(res.data).toEqual({ id: 5, name: 'test' });
    expect(mockWxRequest).toHaveBeenCalledWith(
      expect.objectContaining({ url: expect.stringContaining('/auth/me') })
    );
  });

  // === createPayment 无券 ===

  it('createPayment: couponCode=undefined → null', async () => {
    okResponse({ id: 1, status: 'paid' });
    await api.createPayment(1);
    expect(lastCall().data).toEqual({ coupon_code: null });
  });

  // === HEAD method 幂等 ===

  it('HEAD方法: 幂等 5xx 重试', async () => {
    let calls = 0;
    mockWxRequest.mockImplementation((opts) => {
      calls++;
      if (calls === 1) {
        opts.success({ statusCode: 500, data: {} });
      } else {
        opts.success({ statusCode: 200, data: { code: 200, data: { ok: true } } });
      }
    });
    const res = await api.request('/head-test', { method: 'HEAD' });
    expect(calls).toBe(2);
    expect(res.data).toEqual({ ok: true });
  });

  // === 补全残留分支 ===

  // L189: login res.data为null → || {} fallback
  it('login: 响应data为null → 不崩溃', async () => {
    mockWxRequest.mockImplementation((opts) => {
      opts.success({ statusCode: 200, data: { code: 200, data: null } });
    });
    const res = await api.login('u', 'p');
    expect(res.data).toBeNull();
    expect(store.token).toBeUndefined();
  });

  // L272-273: filterStations无参数 → 默认值
  it('filterStations: 无参数 → 默认page=1, pageSize=20', async () => {
    okResponse({ items: [], total: 0 });
    await api.filterStations();
    expect(lastCall().data).toEqual({ page: 1, page_size: 20 });
  });

  // L280: getStations pageSize默认值20
  it('getStations: 无pageSize → 默认20', async () => {
    okResponse({ items: [], total: 0 });
    await api.getStations({ page: 1 });
    expect(lastCall().data).toEqual({ page: 1, page_size: 20 });
  });

  // L293: removeFavorite favorites不存在 → || [] fallback
  it('removeFavorite: favorites未初始化 → [] fallback', async () => {
    useStore({}); // no favorites key
    const res = await api.removeFavorite('s1');
    expect(res.data).toEqual({ stationId: 's1' });
  });

  // L345: getOrders全默认参数
  it('getOrders: 无参数 → 默认page=1, pageSize=10', async () => {
    useStore({ userInfo: { id: 1 } });
    okResponse({ items: [], total: 0 });
    await api.getOrders();
    expect(lastCall().data).toEqual({ page: 1, page_size: 10, user_id: 1 });
  });

  // L348: uid === null (no user) → user_id not set, backendStatus falsy
  it('getOrders: uid=null + status未知 → 跳过user_id和status', async () => {
    useStore({});
    okResponse({ items: [], total: 0 });
    await api.getOrders();
    expect(lastCall().data).toEqual({ page: 1, page_size: 10 });
    expect(lastCall().data.user_id).toBeUndefined();
  });

  // L348: uid explicit null via userId=null
  it('getOrders: userId=null显式传 → uid=null, 跳过user_id', async () => {
    useStore({ userInfo: { id: 99 } });
    okResponse({ items: [], total: 0 });
    await api.getOrders({ userId: null });
    expect(lastCall().data).toEqual({ page: 1, page_size: 10 });
  });
});
