import { healingRuleApi } from '../api';

// Mock expo-secure-store before axios mock
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// Mock axios
jest.mock('axios', () => {
  const mockAxios: Record<string, any> = {
    create: jest.fn(() => mockAxios),
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    defaults: { headers: { common: {} } },
  };
  return mockAxios;
});

// Import mocked axios
import axios from 'axios';
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('healingRuleApi.create + delete (ext35)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ---------- create ----------
  describe('create', () => {
    it('maps create request fields to snake_case and returns result', async () => {
      mockedAxios.post.mockResolvedValueOnce({
        data: {
          code: 200,
          message: '创建成功',
          data: { id: 10, name: 'auto_restart', message: '创建成功' },
          timestamp: 1786570364,
        },
      });

      const res = await healingRuleApi.create({
        name: 'auto_restart',
        alarmPattern: { severity: 'critical' },
        description: 'test rule',
        autoApprove: true,
        maxRetries: 5,
        cooldownMinutes: 15,
        priority: 3,
        enabled: true,
      });

      expect(mockedAxios.post).toHaveBeenCalledWith('/healing/rules', {
        name: 'auto_restart',
        alarm_pattern: { severity: 'critical' },
        description: 'test rule',
        runbook_template: null,
        auto_approve: true,
        max_retries: 5,
        cooldown_minutes: 15,
        priority: 3,
        enabled: true,
      });
      expect(res.data.id).toBe(10);
      expect(res.data.name).toBe('auto_restart');
      expect(res.data.message).toBe('创建成功');
    });

    it('applies defaults for optional fields', async () => {
      mockedAxios.post.mockResolvedValueOnce({
        data: {
          code: 200,
          message: '创建成功',
          data: { id: 11, name: 'minimal', message: '创建成功' },
          timestamp: 1786570364,
        },
      });

      await healingRuleApi.create({
        name: 'minimal',
        alarmPattern: { type: 'offline' },
      });

      const body = mockedAxios.post.mock.calls[0][1];
      expect(body.description).toBe('');
      expect(body.runbook_template).toBeNull();
      expect(body.auto_approve).toBe(false);
      expect(body.max_retries).toBe(1);
      expect(body.cooldown_minutes).toBe(30);
      expect(body.priority).toBe(0);
      expect(body.enabled).toBe(true);
    });

    it('handles null data in response', async () => {
      mockedAxios.post.mockResolvedValueOnce({
        data: { code: 400, message: 'error', data: null, timestamp: 0 },
      });

      const res = await healingRuleApi.create({
        name: 'x',
        alarmPattern: {},
      });
      expect(res.data.id).toBe(0);
      expect(res.data.name).toBe('');
      expect(res.data.message).toBe('');
    });
  });

  // ---------- delete ----------
  describe('delete', () => {
    it('calls DELETE /healing/rules/{id}', async () => {
      mockedAxios.delete.mockResolvedValueOnce({
        data: { code: 200, message: '删除成功', data: null, timestamp: 1786570386 },
      });

      const res = await healingRuleApi.delete(5);
      expect(mockedAxios.delete).toHaveBeenCalledWith('/healing/rules/5');
      expect(res.code).toBe(200);
      expect(res.message).toBe('删除成功');
      expect(res.data).toBeNull();
    });

    it('handles error response', async () => {
      mockedAxios.delete.mockResolvedValueOnce({
        data: { code: 404, message: '规则不存在', data: null, timestamp: 0 },
      });

      const res = await healingRuleApi.delete(99);
      expect(res.code).toBe(404);
    });
  });
});
