/**
 * api ext66 — alarmRuleApi.create (POST /alarm-rules)
 * camelCase → snake_case request body, snake → camel response full mapping
 */
import { alarmRuleApi } from '../api';
import axios from 'axios';
import type { AlarmRuleCreate } from '../../types';

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

describe('ext66 — alarmRuleApi.create', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sends camelCase body as snake_case and maps response to camelCase', async () => {
    const body: AlarmRuleCreate = {
      name: '温度告警',
      metric: 'temperature',
      threshold: 80,
      severity: 'critical',
      enabled: true,
    };
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          name: '温度告警',
          description: '',
          device_type: null,
          device_ids: null,
          station_ids: null,
          metric: 'temperature',
          operator: '>',
          threshold: 80.0,
          duration: 0,
          level: 'warning',
          alarm_template: '{metric} = {value}, 超过阈值 {threshold}',
          notify_users: null,
          auto_create_workorder: false,
          workorder_priority: 'medium',
          enabled: true,
          silence_minutes: 0,
          created_at: '2026-08-14T02:10:33Z',
          updated_at: null,
        },
        timestamp: 1786644633,
      },
    });

    const res = await alarmRuleApi.create(body);
    expect(mockAxios.post).toHaveBeenCalledWith('/alarm-rules', expect.objectContaining({
      name: '温度告警',
      metric: 'temperature',
      threshold: 80,
      severity: 'critical',
      enabled: true,
    }));
    expect(res.data.id).toBe(1);
    expect(res.data.name).toBe('温度告警');
    expect(res.data.metric).toBe('temperature');
    expect(res.data.threshold).toBe(80.0);
    expect(res.data.operator).toBe('>');
    expect(res.data.alarmTemplate).toContain('{metric}');
    expect(res.data.autoCreateWorkorder).toBe(false);
    expect(res.data.workorderPriority).toBe('medium');
    expect(res.data.silenceMinutes).toBe(0);
    expect(res.data.deviceType).toBeNull();
    expect(res.data.notifyUsers).toBeNull();
    expect(res.data.updatedAt).toBeNull();
    expect(res.data.createdAt).toBe('2026-08-14T02:10:33Z');
  });

  it('handles null/missing fields with defaults', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {},
        timestamp: 0,
      },
    });
    const res = await alarmRuleApi.create({ name: 't', metric: 'm', threshold: 1 });
    expect(res.data.id).toBe(0);
    expect(res.data.name).toBe('');
    expect(res.data.description).toBe('');
    expect(res.data.operator).toBe('>');
    expect(res.data.threshold).toBe(0);
    expect(res.data.level).toBe('warning');
    expect(res.data.enabled).toBe(false);
    expect(res.data.deviceIds).toBeNull();
    expect(res.data.stationIds).toBeNull();
  });

  it('only sends provided optional fields (partial body)', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 5 }, timestamp: 0 },
    });
    await alarmRuleApi.create({ name: 'n', metric: 'm', threshold: 10 });
    const callArg = mockAxios.post.mock.calls[0][1] as Record<string, unknown>;
    expect(callArg.name).toBe('n');
    expect(callArg.metric).toBe('m');
    expect(callArg.threshold).toBe(10);
    expect(callArg).not.toHaveProperty('severity');
    expect(callArg).not.toHaveProperty('operator');
    expect(callArg).not.toHaveProperty('duration');
    expect(callArg).not.toHaveProperty('enabled');
    expect(callArg).not.toHaveProperty('description');
    expect(callArg).not.toHaveProperty('device_type');
  });

  it('posts to /alarm-rules endpoint', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 1 }, timestamp: 0 },
    });
    await alarmRuleApi.create({ name: 'x', metric: 'y', threshold: 0 });
    expect(mockAxios.post).toHaveBeenCalledTimes(1);
    expect(mockAxios.post.mock.calls[0][0]).toBe('/alarm-rules');
  });

  it('passes through business error code', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 400, message: 'metric already exists', data: null, timestamp: 0 },
    });
    const res = await alarmRuleApi.create({ name: 'dup', metric: 'm', threshold: 1 });
    expect(res.code).toBe(400);
    expect(res.data).toBeNull();
  });
});
