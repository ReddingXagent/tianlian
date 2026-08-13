/**
 * api ext69 — alarmRuleApi.update / notificationRuleApi.update / inspectionTemplateApi.update
 * PUT endpoints for updating rules and templates
 * camelCase → snake_case request body, snake → camel response full mapping
 */
import { alarmRuleApi, notificationRuleApi, inspectionTemplateApi } from '../api';
import axios from 'axios';
import type {
  AlarmRuleUpdate,
  NotificationRuleUpdate,
  InspectionTemplateUpdate,
} from '../../types';

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

describe('ext69a — alarmRuleApi.update (PUT /alarm-rules/:id)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sends partial camelCase body as snake_case and maps response', async () => {
    const body: AlarmRuleUpdate = { threshold: 90, enabled: false };
    mockAxios.put.mockResolvedValueOnce({
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
          threshold: 90.0,
          duration: 0,
          level: 'warning',
          alarm_template: '{metric} = {value}',
          notify_users: null,
          auto_create_workorder: false,
          workorder_priority: 'medium',
          enabled: false,
          silence_minutes: 0,
          created_at: '2026-08-14T02:10:33Z',
          updated_at: '2026-08-14T02:22:04Z',
        },
      },
    });

    const res = await alarmRuleApi.update(1, body);
    expect(mockAxios.put).toHaveBeenCalledWith('/alarm-rules/1', {
      threshold: 90,
      enabled: false,
    });
    expect(res.data!.threshold).toBe(90);
    expect(res.data!.enabled).toBe(false);
    expect(res.data!.deviceType).toBeNull();
    expect(res.data!.updatedAt).toBe('2026-08-14T02:22:04Z');
  });

  it('handles null data response', async () => {
    mockAxios.put.mockResolvedValueOnce({
      data: { code: 404, message: 'rule not found', data: null },
    });
    const res = await alarmRuleApi.update(999, { name: 'test' });
    expect(res.data).toBeNull();
  });

  it('verifies endpoint and method', async () => {
    mockAxios.put.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { id: 1 } },
    });
    await alarmRuleApi.update(1, { name: 'updated' });
    expect(mockAxios.put).toHaveBeenCalledTimes(1);
    const [url, body] = mockAxios.put.mock.calls[0];
    expect(url).toBe('/alarm-rules/1');
    expect(body).toEqual({ name: 'updated' });
  });
});

describe('ext69b — notificationRuleApi.update (PUT /notification-rules/:id)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sends partial camelCase body as snake_case and maps response', async () => {
    const body: NotificationRuleUpdate = { channels: ['email', 'sms'], enabled: false };
    mockAxios.put.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          name: 'test',
          level: 'critical',
          channels: ['email', 'sms'],
          receivers: [],
          enabled: false,
          created_at: '2026-08-14T02:10:33Z',
          updated_at: '2026-08-14T02:22:04Z',
        },
      },
    });

    const res = await notificationRuleApi.update(1, body);
    expect(mockAxios.put).toHaveBeenCalledWith('/notification-rules/1', {
      channels: ['email', 'sms'],
      enabled: false,
    });
    expect(res.data!.channels).toEqual(['email', 'sms']);
    expect(res.data!.enabled).toBe(false);
    expect(res.data!.updatedAt).toBe('2026-08-14T02:22:04Z');
  });

  it('handles null data response', async () => {
    mockAxios.put.mockResolvedValueOnce({
      data: { code: 404, message: 'not found', data: null },
    });
    const res = await notificationRuleApi.update(999, { name: 'x' });
    expect(res.data).toBeNull();
  });

  it('verifies endpoint and partial body mapping', async () => {
    mockAxios.put.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { id: 1 } },
    });
    await notificationRuleApi.update(1, { level: 'warning' });
    expect(mockAxios.put).toHaveBeenCalledTimes(1);
    const [url, body] = mockAxios.put.mock.calls[0];
    expect(url).toBe('/notification-rules/1');
    expect(body).toEqual({ level: 'warning' });
  });
});

describe('ext69c — inspectionTemplateApi.update (PUT /inspection/templates/:id)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sends partial camelCase body and maps response with items', async () => {
    const body: InspectionTemplateUpdate = {
      name: 'Updated Template',
      items: [{ name: 'visual', required: true }],
    };
    mockAxios.put.mockResolvedValueOnce({
      data: {
        code: 200,
        message: '模板已更新',
        data: {
          id: 1,
          name: 'Updated Template',
          description: null,
          items: [{ name: 'visual', required: true }],
          item_count: 1,
          device_types: [],
          target: null,
          status: 'active',
          created_at: '2026-08-14T02:10:23Z',
          updated_at: '2026-08-14T02:22:04Z',
        },
      },
    });

    const res = await inspectionTemplateApi.update(1, body);
    expect(mockAxios.put).toHaveBeenCalledWith('/inspection/templates/1', {
      name: 'Updated Template',
      items: [{ name: 'visual', required: true }],
    });
    expect(res.data!.name).toBe('Updated Template');
    expect(res.data!.items).toEqual([{ name: 'visual', required: true }]);
    expect(res.data!.itemCount).toBe(1);
    expect(res.data!.deviceTypes).toEqual([]);
    expect(res.data!.description).toBeNull();
  });

  it('handles null data response', async () => {
    mockAxios.put.mockResolvedValueOnce({
      data: { code: 404, message: 'not found', data: null },
    });
    const res = await inspectionTemplateApi.update(999, { name: 'x' });
    expect(res.data).toBeNull();
  });

  it('verifies endpoint with description-only update', async () => {
    mockAxios.put.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          name: 'T1',
          description: 'new desc',
          items: [],
          item_count: 0,
          device_types: [],
          target: null,
          status: 'active',
          created_at: '',
          updated_at: '',
        },
      },
    });
    const res = await inspectionTemplateApi.update(1, { description: 'new desc' });
    const [url, body] = mockAxios.put.mock.calls[0];
    expect(url).toBe('/inspection/templates/1');
    expect(body).toEqual({ description: 'new desc' });
    expect(res.data!.description).toBe('new desc');
  });
});
