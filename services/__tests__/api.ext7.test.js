/**
 * api.ext7: getUserInfo L228 `if (res.data)` false臂闭合 (F1247)
 *
 * 背景: coverage显示 services/api.js L228 branch counts=[3,0] —
 * 既有3次getUserInfo调用全部返回带data的响应, false臂(res无data)从未走过。
 * 本套件补1测: /auth/me 返回无data字段 → 不写缓存, 原样返回。
 */
const api = require('../api');

const mockSetStorageSync = jest.fn();

global.wx = {
  request: jest.fn(),
  getStorageSync: jest.fn(),
  setStorageSync: mockSetStorageSync,
  removeStorageSync: jest.fn(),
  showLoading: jest.fn(),
  hideLoading: jest.fn(),
  showToast: jest.fn()
};

describe('api.ext7: getUserInfo 无data响应分支', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('getUserInfo: res无data字段 → 跳过缓存写入, 原样返回', async () => {
    // 模拟后端返回 code:200 但无 data 字段的形态(如会话异常降级)
    wx.request.mockImplementation(({ success }) => {
      success({ statusCode: 200, data: { code: 200, message: 'success' } });
    });

    const res = await api.getUserInfo();

    // 请求仍发出
    expect(wx.request).toHaveBeenCalledWith(
      expect.objectContaining({
        url: expect.stringContaining('/auth/me'),
        method: 'GET'
      })
    );
    // 关键断言: res.data为undefined → 不触发 wx.setStorageSync('userInfo', ...)
    expect(wx.setStorageSync).not.toHaveBeenCalled();
    // 原样返回
    expect(res.code).toBe(200);
  });
});
