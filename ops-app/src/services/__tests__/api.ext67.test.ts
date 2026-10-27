/**
 * api ext67 — notificationRuleApi.create (POST /notification-rules)
 * camelCase → snake_case request body, snake → camel response full mapping
 */
import { notificationRuleApi } from '../api';
import axios from 'axios';
import type { NotificationRuleCreate } from '../../types';

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

describe('ext67 — notificationRuleApi.create', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sends camelCase body as snake_case and maps response to camelCase', async () => {
    const body: NotificationRuleCreate = {
      name: '紧急通知',
      level: 'critical',
      channels: ['sms', 'email'],
      receivers: ['admin@example.com'],
      enabled: true,
    };
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          name: '紧急通知',
          level: 'critical',
          channels: ['sms', 'email'],
          receivers: ['admin@example.com'],
          enabled: true,
          created_at: '2026-08-14T02:10:33Z',
          updated_at: null,
        },
        timestamp: 1786644633,
      },
    });

    const res = await notificationRuleApi.create(body);
    expect(mockAxios.post).toHaveBeenCalledWith('/notification-rules', expect.objectContaining({
      name: '紧急通知',
      level: 'critical',
      channels: ['sms', 'email'],
      receivers: ['admin@example.com'],
      enabled: true,
    }));
    expect(res.data.id).toBe(1);
    expect(res.data.name).toBe('紧急通知');
    expect(res.data.level).toBe('critical');
    expect(res.data.channels).toEqual(['sms', 'email']);
    expect(res.data.receivers).toEqual(['admin@example.com']);
    expect(res.data.enabled).toBe(true);
    expect(res.data.updatedAt).toBeNull();
    expect(res.data.createdAt).toBe('2026-08-14T02:10:33Z');
  });

  it('handles null/missing fields with defaults', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {}, timestamp: 0 },
    });
    const res = await notificationRuleApi.create({ name: 't', level: 'info' });
    expect(res.data.id).toBe(0);
    expect(res.data.name).toBe('');
    expect(res.data.level).toBe('');
    expect(res.data.channels).toEqual([]);
    expect(res.data.receivers).toEqual([]);
    expect(res.data.enabled).toBe(false);
    expect(res.data.createdAt).toBe('');
    expect(res.data.updatedAt).toBeNull();
  });

  it('only sends name+level when no optional fields provided', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 3 }, timestamp: 0 },
    });
    await notificationRuleApi.create({ name: 'n', level: 'warn' });
    const callArg = mockAxios.post.mock.calls[0][1] as Record<string, unknown>;
    expect(callArg.name).toBe('n');
    expect(callArg.level).toBe('warn');
    expect(callArg).not.toHaveProperty('channels');
    expect(callArg).not.toHaveProperty('receivers');
    expect(callArg).not.toHaveProperty('enabled');
  });

  it('posts to /notification-rules endpoint', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 1 }, timestamp: 0 },
    });
    await notificationRuleApi.create({ name: 'x', level: 'y' });
    expect(mockAxios.post).toHaveBeenCalledTimes(1);
    expect(mockAxios.post.mock.calls[0][0]).toBe('/notification-rules');
  });

  it('passes through business error', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 400, message: 'duplicate rule', data: null, timestamp: 0 },
    });
    const res = await notificationRuleApi.create({ name: 'd', level: 'x' });
    expect(res.code).toBe(400);
    expect(res.data).toBeNull();
  });
});
