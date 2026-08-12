/**
 * api ext20 — /roles/{id}, /healing/rules/{id}, /security/policies/{key} 三新详情端点对接测试
 */
import { roleApi, healingRuleApi, securityPolicyApi } from '../api';

jest.mock('axios', () => {
  const mockInstance = {
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  };
  return {
    create: jest.fn(() => mockInstance),
  };
});

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const axios = require('axios');
const mockGet = axios.create().get as jest.Mock;

describe('api.ext20 — 详情端点对接', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ---------- roleApi.getById ----------
  describe('roleApi.getById', () => {
    it('映射 /roles/{id} 响应字段', async () => {
      mockGet.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: {
            id: 1,
            name: 'super_admin',
            display_name: '超级管理员',
            description: '超级管理员，拥有全部权限。',
            is_system: true,
            permissions: ['alarm:delete', 'device:view', 'station:edit'],
          },
        },
      });

      const res = await roleApi.getById(1);
      expect(res.data.id).toBe(1);
      expect(res.data.name).toBe('super_admin');
      expect(res.data.displayName).toBe('超级管理员');
      expect(res.data.isSystem).toBe(true);
      expect(res.data.permissions).toEqual(['alarm:delete', 'device:view', 'station:edit']);
    });

    it('缺失字段使用默认值', async () => {
      mockGet.mockResolvedValueOnce({
        data: { code: 200, message: 'ok', data: {} },
      });

      const res = await roleApi.getById(99);
      expect(res.data.id).toBe(0);
      expect(res.data.name).toBe('');
      expect(res.data.displayName).toBe('');
      expect(res.data.isSystem).toBe(false);
      expect(res.data.permissions).toEqual([]);
    });

    it('调用正确URL', async () => {
      mockGet.mockResolvedValueOnce({
        data: { code: 200, message: 'ok', data: { id: 5 } },
      });
      await roleApi.getById(5);
      expect(mockGet).toHaveBeenCalledWith('/roles/5');
    });
  });

  // ---------- healingRuleApi.getById ----------
  describe('healingRuleApi.getById', () => {
    it('映射 /healing/rules/{id} 响应字段', async () => {
      mockGet.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: {
            id: 1,
            name: '充电桩重启规则',
            description: '高温自动重启',
            alarm_pattern: { temperature: '>80' },
            runbook_template: 'restart_runbook',
            auto_approve: true,
            max_retries: 2,
            cooldown_minutes: 45,
            priority: 5,
            enabled: true,
            created_at: '2026-07-01T00:00:00Z',
            updated_at: '2026-08-01T10:00:00Z',
          },
        },
      });

      const res = await healingRuleApi.getById(1);
      expect(res.data.id).toBe(1);
      expect(res.data.name).toBe('充电桩重启规则');
      expect(res.data.description).toBe('高温自动重启');
      expect(res.data.alarmPattern).toEqual({ temperature: '>80' });
      expect(res.data.runbookTemplate).toBe('restart_runbook');
      expect(res.data.autoApprove).toBe(true);
      expect(res.data.maxRetries).toBe(2);
      expect(res.data.cooldownMinutes).toBe(45);
      expect(res.data.priority).toBe(5);
      expect(res.data.enabled).toBe(true);
    });

    it('规则不存在返回404 data=null', async () => {
      mockGet.mockResolvedValueOnce({
        data: { code: 404, message: '规则#99不存在', data: null },
      });

      const res = await healingRuleApi.getById(99);
      expect(res.data.id).toBe(0);
      expect(res.data.name).toBe('');
    });
  });

  // ---------- securityPolicyApi.getByKey ----------
  describe('securityPolicyApi.getByKey', () => {
    it('映射 /security/policies/{key} 响应字段', async () => {
      mockGet.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: {
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
        },
      });

      const res = await securityPolicyApi.getByKey('password');
      expect(res.data.id).toBe(1);
      expect(res.data.policyKey).toBe('password');
      expect(res.data.policyConfig).toEqual({
        min_length: 8,
        require_upper: true,
        require_digit: true,
        expire_days: 90,
      });
      expect(res.data.description).toBe('密码强度与过期策略');
      expect(res.data.status).toBe('active');
    });

    it('调用正确URL', async () => {
      mockGet.mockResolvedValueOnce({
        data: { code: 200, message: 'ok', data: { id: 1 } },
      });
      await securityPolicyApi.getByKey('login');
      expect(mockGet).toHaveBeenCalledWith('/security/policies/login');
    });

    it('空data使用默认值', async () => {
      mockGet.mockResolvedValueOnce({
        data: { code: 200, message: 'ok', data: {} },
      });

      const res = await securityPolicyApi.getByKey('session');
      expect(res.data.id).toBe(0);
      expect(res.data.policyKey).toBe('');
      expect(res.data.policyConfig).toEqual({});
      expect(res.data.status).toBe('active');
    });
  });
});
