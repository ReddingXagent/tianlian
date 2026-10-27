// services/__tests__/api.ext6.test.js
// F1238: api.js最后4缺口闭合 — ①fn getTenantBranding L255/stmt L256真调(api层从未直测, branding套件全mock不触真码)
// ②L83 unref守卫false臂(HTTP 5xx重试路径) ③L93 unref守卫false臂(网络fail重试路径)
// 手法: spyOn(global,'setTimeout').mockImplementation同步执行回调+返回undefined — 模拟微信小程序
// setTimeout无timer对象返回值形态(生产真实环境), L83/L93 if(t&&typeof t.unref==='function')走false臂;
// 同步执行回调保证重试链(calls=2)与最终reject照常锚定, 非人为强造(F1235 cache.js b12同族先例)
const mockWxRequest = jest.fn();

global.wx = {
  request: mockWxRequest,
  getStorageSync: jest.fn(),
  setStorageSync: jest.fn(),
  removeStorageSync: jest.fn(),
  showLoading: jest.fn(),
  hideLoading: jest.fn(),
  showToast: jest.fn()
};

const api = require('../api');

describe('api.ext6 — getTenantBranding真调 + unref守卫小程序形态', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('getTenantBranding: GET /tenants/{id}/branding pass-through', async () => {
    mockWxRequest.mockImplementation(({ success }) => {
      success({ statusCode: 200, data: { code: 0, data: { operator_name: '天链能源', theme_color: '#00B96B', source: 'default' } } });
    });
    const res = await api.getTenantBranding(42);
    expect(mockWxRequest).toHaveBeenCalledTimes(1);
    expect(mockWxRequest).toHaveBeenCalledWith(expect.objectContaining({
      url: expect.stringContaining('/tenants/42/branding'),
      method: 'GET'
    }));
    expect(res.data.operator_name).toBe('天链能源');
    expect(res.data.theme_color).toBe('#00B96B');
  });

  test('L83: HTTP 5xx幂等重试, setTimeout无返回值(小程序形态) → unref守卫false臂, 重试链仍走完', async () => {
    jest.spyOn(global, 'setTimeout').mockImplementation((fn) => { fn(); return undefined; });
    let calls = 0;
    mockWxRequest.mockImplementation((opts) => {
      calls++;
      opts.success({ statusCode: 503, data: {} });
    });
    await expect(api.request('/x', { method: 'GET' })).rejects.toThrow('HTTP 503');
    expect(calls).toBe(2); // 初次 + 1次重试(回调同步执行, 链条不靠timer驱动)
  });

  test('L93: 网络fail幂等重试, setTimeout无返回值 → unref守卫false臂, 重试后仍fail reject', async () => {
    jest.spyOn(global, 'setTimeout').mockImplementation((fn) => { fn(); return undefined; });
    let calls = 0;
    mockWxRequest.mockImplementation((opts) => {
      calls++;
      opts.fail({ errMsg: 'request:fail timeout' });
    });
    await expect(api.request('/x', { method: 'GET' })).rejects.toMatchObject({ errMsg: expect.stringContaining('timeout') });
    expect(calls).toBe(2);
  });
});
