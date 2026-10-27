/**
 * api ext65 — healingRuleApi.update (PUT /healing/rules/{id})
 * Partial update with camelCase → snake_case body, snake → camel response
 */
import { healingRuleApi } from '../api';
import axios from 'axios';
import type { HealingRuleUpdate } from '../../types';

jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  };
  return {
    create: jest.fn(() => mockInstance),
    __mockInstance: mockInstance,
  };
});

jest.mock('expo-secure-store', () => ({
  getItemSecure: jest.fn().mockResolvedValue('mock-token'),
  setItemSecure: jest.fn().mockResolvedValue(undefined),
  deleteItemSecure: jest.fn().mockResolvedValue(undefined),
}));

const mockAxios = (axios as unknown as { __mockInstance: Record<string, jest.Mock> }).__mockInstance;

describe('healingRuleApi.update (ext65)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('should send PUT /healing/rules/{id} with camelCase → snake_case body', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          name: 'Updated Rule',
          description: 'Updated desc',
          alarm_pattern: { severity: 'critical' },
          runbook_template: 'template-v2',
          auto_approve: true,
          max_retries: 5,
          cooldown_minutes: 60,
          priority: 10,
          enabled: false,
          created_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-14T01:30:00Z',
        },
        timestamp: 1786642000,
      },
    });

    const body: HealingRuleUpdate = {
      name: 'Updated Rule',
      description: 'Updated desc',
      alarmPattern: { severity: 'critical' },
      runbookTemplate: 'template-v2',
      autoApprove: true,
      maxRetries: 5,
      cooldownMinutes: 60,
      priority: 10,
      enabled: false,
    };

    const result = await healingRuleApi.update(1, body);

    expect(mockAxios.put).toHaveBeenCalledWith('/healing/rules/1', {
      name: 'Updated Rule',
      description: 'Updated desc',
      alarm_pattern: { severity: 'critical' },
      runbook_template: 'template-v2',
      auto_approve: true,
      max_retries: 5,
      cooldown_minutes: 60,
      priority: 10,
      enabled: false,
    });

    // snake → camel response mapping
    expect(result.data).toEqual({
      id: 1,
      name: 'Updated Rule',
      description: 'Updated desc',
      alarmPattern: { severity: 'critical' },
      runbookTemplate: 'template-v2',
      autoApprove: true,
      maxRetries: 5,
      cooldownMinutes: 60,
      priority: 10,
      enabled: false,
      createdAt: '2026-08-01T00:00:00Z',
      updatedAt: '2026-08-14T01:30:00Z',
    });
  });

  it('should send only provided fields (partial update)', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 2,
          name: 'Old Name',
          enabled: false,
        },
        timestamp: 1786642001,
      },
    });

    const body: HealingRuleUpdate = { enabled: false };

    const result = await healingRuleApi.update(2, body);

    // Only enabled field should be in payload
    expect(mockAxios.put).toHaveBeenCalledWith('/healing/rules/2', { enabled: false });
    expect(result.data.enabled).toBe(false);
    // Missing fields should default
    expect(result.data.name).toBe('Old Name');
    expect(result.data.maxRetries).toBe(0);
  });

  it('should handle null runbookTemplate', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 3,
          runbook_template: null,
        },
        timestamp: 1786642002,
      },
    });

    const result = await healingRuleApi.update(3, { runbookTemplate: null });

    expect(mockAxios.put).toHaveBeenCalledWith('/healing/rules/3', { runbook_template: null });
    expect(result.data.runbookTemplate).toBeNull();
  });

  it('should use correct endpoint and HTTP method', async () => {
    mockAxios.put.mockResolvedValue({
      data: { code: 200, message: 'success', data: { id: 1 }, timestamp: 0 },
    });

    await healingRuleApi.update(1, { name: 'test' });

    expect(mockAxios.put).toHaveBeenCalledTimes(1);
    const [url] = mockAxios.put.mock.calls[0];
    expect(url).toBe('/healing/rules/1');
  });

  it('should propagate business error (rule not exist)', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 400,
        message: '规则#999不存在',
        data: null,
        timestamp: 1786642003,
      },
    });

    const result = await healingRuleApi.update(999, { name: 'test' });

    expect(result.code).toBe(400);
    // null data → all defaults
    expect(result.data.id).toBe(0);
    expect(result.data.name).toBe('');
  });
});
