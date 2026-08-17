/**
 * api ext18 — /security/logs, /security/policies 两新端点对接测试
 */
import { securityLogApi, securityPolicyApi } from '../api';

jest.mock('axios', () => {
  const mockAxios = {
    create: () => ({
      interceptors: {
        request: { use: jest.fn() },
        response: { use: jest.fn() },
      },
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      patch: jest.fn(),
      delete: jest.fn(),
    }),
  };
  return mockAxios;
});

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const api = require('../api').default;
const mockedGet = api.get as jest.MockedFunction<typeof api.get>;

describe('securityLogApi', () => {
  beforeEach(() => jest.clearAllMocks());

  it('getList returns mapped SecurityLog items', async () => {
    mockedGet.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            {
              id: 100,
              timestamp: '2026-08-11T10:00:00+08:00',
              user_id: 1,
              username: 'admin',
              user_role: 'super_admin',
              action: 'login',
              module: 'auth',
              target_id: '1',
              target_desc: '用户登录',
              detail: null,
              old_value: null,
              new_value: null,
              ip_address: '192.168.1.1',
              user_agent: 'Mozilla/5.0',
              result: 'success',
              error_msg: null,
            },
            {
              id: 101,
              timestamp: '2026-08-11T10:05:00+08:00',
              user_id: 0,
              username: 'system',
              user_role: null,
              action: 'create',
              module: 'alarms',
              target_id: '5000',
              target_desc: '创建告警:温度过高',
              detail: 'temp=52.1',
              old_value: null,
              new_value: '{"level":"warning"}',
              ip_address: null,
              user_agent: null,
              result: 'failure',
              error_msg: 'send_failed',
            },
          ],
          total: 5000,
          page: 1,
          page_size: 20,
        },
        timestamp: 1786446099,
      },
    });

    const res = await securityLogApi.getList({ page: 1, pageSize: 20 });
    expect(res.code).toBe(200);
    expect(res.data.items).toHaveLength(2);

    const log = res.data.items[0];
    expect(log.id).toBe(100);
    expect(log.userId).toBe(1);
    expect(log.username).toBe('admin');
    expect(log.userRole).toBe('super_admin');
    expect(log.action).toBe('login');
    expect(log.module).toBe('auth');
    expect(log.targetId).toBe('1');
    expect(log.ipAddress).toBe('192.168.1.1');
    expect(log.result).toBe('success');
    expect(log.errorMsg).toBeNull();

    const log2 = res.data.items[1];
    expect(log2.username).toBe('system');
    expect(log2.userRole).toBeNull();
    expect(log2.result).toBe('failure');
    expect(log2.errorMsg).toBe('send_failed');
    expect(log2.detail).toBe('temp=52.1');

    expect(res.data.total).toBe(5000);
    expect(mockedGet).toHaveBeenCalledWith(
      '/security/logs',
      expect.objectContaining({
        params: { page: 1, page_size: 20 },
      }),
    );
  });

  it('getList handles empty response', async () => {
    mockedGet.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {} },
    });
    const res = await securityLogApi.getList();
    expect(res.data.items).toHaveLength(0);
    expect(res.data.total).toBe(0);
  });

  it('getList uses default pagination', async () => {
    mockedGet.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { items: [], total: 0 } },
    });
    await securityLogApi.getList();
    expect(mockedGet).toHaveBeenCalledWith(
      '/security/logs',
      expect.objectContaining({
        params: { page: undefined, page_size: undefined },
      }),
    );
  });
});

describe('securityPolicyApi', () => {
  beforeEach(() => jest.clearAllMocks());

  it('getList returns mapped SecurityPolicy items', async () => {
    mockedGet.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            {
              id: 1,
              policy_key: 'password',
              policy_config: {
                min_length: 8,
                require_upper: true,
                require_digit: true,
                expire_days: 90,
              },
              description: '密码强度与过期策略',
              status: 'active',
              created_at: '2026-07-31T11:16:02.552846+08:00',
              updated_at: '2026-07-31T11:16:02.552846+08:00',
            },
            {
              id: 2,
              policy_key: 'login',
              policy_config: {
                fail_lock_count: 5,
                lock_duration_minutes: 30,
              },
              description: '登录失败锁定策略',
              status: 'active',
              created_at: '2026-07-31T11:16:02.552846+08:00',
              updated_at: '2026-07-31T11:16:02.552846+08:00',
            },
          ],
          total: 4,
        },
        timestamp: 1786446099,
      },
    });

    const res = await securityPolicyApi.getList();
    expect(res.code).toBe(200);
    expect(res.data.items).toHaveLength(2);

    const policy = res.data.items[0];
    expect(policy.id).toBe(1);
    expect(policy.policyKey).toBe('password');
    expect(policy.description).toBe('密码强度与过期策略');
    expect(policy.status).toBe('active');
    expect(policy.policyConfig).toEqual({
      min_length: 8,
      require_upper: true,
      require_digit: true,
      expire_days: 90,
    });

    const policy2 = res.data.items[1];
    expect(policy2.policyKey).toBe('login');
    expect(policy2.policyConfig).toHaveProperty('fail_lock_count', 5);

    expect(mockedGet).toHaveBeenCalledWith('/security/policies');
  });

  it('getList handles empty response', async () => {
    mockedGet.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {} },
    });
    const res = await securityPolicyApi.getList();
    expect(res.data.items).toHaveLength(0);
    expect(res.data.total).toBe(0);
  });
});
