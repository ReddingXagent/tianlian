/**
 * BASE_URL 解析分支测试 (api.ts 模块级)
 * - 非 __DEV__ 环境回退到生产云端地址 (ternary false 分支)
 *
 * 注: EXPO_PUBLIC_API_URL 由 babel 在转换期内联, 运行时无法改写, 故不在此覆盖。
 * 每个用例独立 resetModules 后重新 require, 确保模块级常量重新求值。
 */

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

type MutableGlobal = { __DEV__?: boolean };

describe('BASE_URL resolution branches', () => {
  const originalEnvUrl = process.env.EXPO_PUBLIC_API_URL;
  const originalDev = (globalThis as MutableGlobal).__DEV__;

  afterEach(() => {
    if (originalEnvUrl === undefined) {
      delete process.env.EXPO_PUBLIC_API_URL;
    } else {
      process.env.EXPO_PUBLIC_API_URL = originalEnvUrl;
    }
    (globalThis as MutableGlobal).__DEV__ = originalDev;
    jest.resetModules();
  });

  it('falls back to production cloud URL when __DEV__ is false', () => {
    delete process.env.EXPO_PUBLIC_API_URL;
    (globalThis as MutableGlobal).__DEV__ = false;
    jest.resetModules();
    const freshApi = require('../api').default;
    expect(freshApi.defaults.baseURL).toBe('http://your-server-ip/api/v1');
  });
});
