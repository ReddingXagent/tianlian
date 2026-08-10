/**
 * api ext11 — AlarmRule & NotificationRule API (F752)
 * GET /alarm-rules (paginated), GET /notification-rules (array)
 */
import { alarmRuleApi, notificationRuleApi } from '../api';

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

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require('../api').default as jest.Mocked<{ get: jest.Mock }>;

describe('alarmRuleApi.getList() — GET /alarm-rules', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase AlarmRule[]', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            {
              id: 1,
              name: '高温告警',
              device_type: 'charger',
              metric: 'temperature',
              condition: '>',
              threshold: 80,
              level: 'critical',
              enabled: true,
              description: '充电桩温度超过80度',
              created_at: '2026-08-01T00:00:00Z',
              updated_at: '2026-08-05T12:00:00Z',
            },
            {
              id: 2,
              name: '电压异常',
              device_type: 'battery',
              metric: 'voltage',
              condition: '<',
              threshold: 200,
              level: 'warning',
              enabled: false,
              description: '电池电压低于200V',
              created_at: '2026-08-02T00:00:00Z',
              updated_at: '2026-08-06T08:30:00Z',
            },
          ],
          total: 2,
          page: 1,
          page_size: 20,
        },
        timestamp: 1786357882,
      },
    });

    const res = await alarmRuleApi.getList({ page: 1, pageSize: 20 });
    expect(res.data.items).toHaveLength(2);
    expect(res.data.total).toBe(2);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);

    const r0 = res.data.items[0];
    expect(r0.id).toBe(1);
    expect(r0.name).toBe('高温告警');
    expect(r0.deviceType).toBe('charger');
    expect(r0.metric).toBe('temperature');
    expect(r0.condition).toBe('>');
    expect(r0.threshold).toBe(80);
    expect(r0.level).toBe('critical');
    expect(r0.enabled).toBe(true);
    expect(r0.description).toBe('充电桩温度超过80度');
    expect(r0.createdAt).toBe('2026-08-01T00:00:00Z');
    expect(r0.updatedAt).toBe('2026-08-05T12:00:00Z');

    const r1 = res.data.items[1];
    expect(r1.enabled).toBe(false);
    expect(r1.level).toBe('warning');
  });

  it('handles empty items with defaults', async () => {
    api.get.mockResolvedValue({
      data: { code: 200, data: {} },
    });
    const res = await alarmRuleApi.getList();
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  it('handles partial item fields', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        data: {
          items: [{ id: 5, name: '部分规则' }],
          total: 1,
        },
      },
    });
    const res = await alarmRuleApi.getList();
    expect(res.data.items).toHaveLength(1);
    expect(res.data.items[0].id).toBe(5);
    expect(res.data.items[0].name).toBe('部分规则');
    expect(res.data.items[0].deviceType).toBe('');
    expect(res.data.items[0].threshold).toBe(0);
    expect(res.data.items[0].enabled).toBe(false);
    expect(res.data.items[0].level).toBe('warning');
  });
});

describe('notificationRuleApi.getList() — GET /notification-rules', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase NotificationRule[]', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: [
          {
            id: 1,
            name: '告警邮件通知',
            event: 'alarm.critical',
            channels: ['email', 'sms'],
            recipients: ['admin@test.com', 'ops@test.com'],
            enabled: true,
            template: '设备{device}发生{level}告警: {content}',
            created_at: '2026-08-01T00:00:00Z',
            updated_at: '2026-08-05T12:00:00Z',
          },
          {
            id: 2,
            name: '工单状态变更',
            event: 'workorder.status_changed',
            channels: ['wechat'],
            recipients: ['engineer1@test.com'],
            enabled: false,
            template: '工单{order_id}状态变更为{status}',
            created_at: '2026-08-03T00:00:00Z',
            updated_at: '2026-08-06T10:00:00Z',
          },
        ],
        timestamp: 1786357882,
      },
    });

    const res = await notificationRuleApi.getList();
    expect(res.data).toHaveLength(2);

    const r0 = res.data[0];
    expect(r0.id).toBe(1);
    expect(r0.name).toBe('告警邮件通知');
    expect(r0.event).toBe('alarm.critical');
    expect(r0.channels).toEqual(['email', 'sms']);
    expect(r0.recipients).toEqual(['admin@test.com', 'ops@test.com']);
    expect(r0.enabled).toBe(true);
    expect(r0.template).toBe('设备{device}发生{level}告警: {content}');
    expect(r0.createdAt).toBe('2026-08-01T00:00:00Z');

    const r1 = res.data[1];
    expect(r1.enabled).toBe(false);
    expect(r1.channels).toEqual(['wechat']);
  });

  it('handles empty array', async () => {
    api.get.mockResolvedValue({
      data: { code: 200, data: [] },
    });
    const res = await notificationRuleApi.getList();
    expect(res.data).toEqual([]);
  });

  it('handles null/missing data gracefully', async () => {
    api.get.mockResolvedValue({
      data: { code: 200, data: null },
    });
    const res = await notificationRuleApi.getList();
    expect(res.data).toEqual([]);
  });

  it('handles partial item fields', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        data: [{ id: 3, name: '仅名称' }],
      },
    });
    const res = await notificationRuleApi.getList();
    expect(res.data).toHaveLength(1);
    expect(res.data[0].id).toBe(3);
    expect(res.data[0].name).toBe('仅名称');
    expect(res.data[0].event).toBe('');
    expect(res.data[0].channels).toEqual([]);
    expect(res.data[0].recipients).toEqual([]);
    expect(res.data[0].enabled).toBe(false);
  });
});
