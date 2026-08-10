const api = require('../api');

const mockGetStorageSync = jest.fn();
const mockSetStorageSync = jest.fn();

global.wx = {
  request: jest.fn(),
  getStorageSync: mockGetStorageSync,
  setStorageSync: mockSetStorageSync,
  removeStorageSync: jest.fn(),
  showLoading: jest.fn(),
  hideLoading: jest.fn(),
  showToast: jest.fn()
};

// F750: user-mp /auth/me + /energy/summary + updateUserInfo 对接测试

describe('api.ext5 — auth/me + energy/summary 对接', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // getUserInfo → GET /auth/me
  test('getUserInfo: 调用 /auth/me 并缓存用户信息', async () => {
    const mockUser = { id: 1, username: 'tl', real_name: '测试用户', permissions: ['read', 'write'] };
    wx.request.mockImplementation(({ success }) => {
      success({ statusCode: 200, data: { code: 0, data: mockUser } });
    });

    const res = await api.getUserInfo();
    expect(wx.request).toHaveBeenCalledWith(
      expect.objectContaining({
        url: expect.stringContaining('/auth/me'),
        method: 'GET'
      })
    );
    expect(res.data).toEqual(mockUser);
    expect(wx.setStorageSync).toHaveBeenCalledWith('userInfo', mockUser);
  });

  // getUserInfo: token过期 401
  test('getUserInfo: 401 → TOKEN_EXPIRED reject', async () => {
    wx.request.mockImplementation(({ success }) => {
      success({ statusCode: 401, data: { detail: 'Not authenticated' } });
    });

    await expect(api.getUserInfo()).rejects.toThrow('TOKEN_EXPIRED');
  });

  // updateUserInfo: 本地缓存合并
  test('updateUserInfo: 合并到本地缓存并返回', async () => {
    mockGetStorageSync.mockReturnValueOnce({ id: 1, username: 'tl' });

    const res = await api.updateUserInfo({ nickname: '猴王', phone: '13800138000' });
    expect(res.code).toBe(200);
    expect(res.data.nickname).toBe('猴王');
    expect(res.data.phone).toBe('13800138000');
    expect(res.data.id).toBe(1);
    expect(wx.setStorageSync).toHaveBeenCalledWith(
      'userInfo',
      expect.objectContaining({ id: 1, nickname: '猴王', phone: '13800138000' })
    );
  });

  // updateUserInfo: 未登录
  test('updateUserInfo: 无本地用户 → reject', async () => {
    mockGetStorageSync.mockReturnValueOnce(null);
    await expect(api.updateUserInfo({ nickname: 'test' })).rejects.toThrow('未登录');
  });

  // getEnergySummary → GET /energy/summary
  test('getEnergySummary: 返回光储充经营数据', async () => {
    const mockEnergy = {
      total_generation_kwh: 125000.5,
      total_charging_kwh: 98000.3,
      total_revenue: 156800.75,
      today_generation_kwh: 850.2
    };
    wx.request.mockImplementation(({ success }) => {
      success({ statusCode: 200, data: { code: 0, data: mockEnergy } });
    });

    const res = await api.getEnergySummary();
    expect(wx.request).toHaveBeenCalledWith(
      expect.objectContaining({
        url: expect.stringContaining('/energy/summary'),
        method: 'GET'
      })
    );
    expect(res.data.total_generation_kwh).toBe(125000.5);
    expect(res.data.total_revenue).toBe(156800.75);
  });

  // getEnergySummary: 5xx 重试 (幂等GET)
  test('getEnergySummary: 500 → 幂等重试一次', async () => {
    const mockEnergy = { total_generation_kwh: 100 };
    let calls = 0;
    wx.request.mockImplementation(({ success }) => {
      calls++;
      if (calls === 1) {
        success({ statusCode: 500, data: { error: 'Internal Error' } });
      } else {
        success({ statusCode: 200, data: { code: 0, data: mockEnergy } });
      }
    });

    // 重试需要等待1秒
    const res = await api.getEnergySummary();
    expect(calls).toBe(2);
    expect(res.data.total_generation_kwh).toBe(100);
  });
});
