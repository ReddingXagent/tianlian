/**
 * api ext10 — NotificationTemplate API (GET /notifications/templates)
 * Target: pagination + snake_case → camelCase mapping
 */
import { notificationTemplateApi } from '../api';

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

describe('notificationTemplateApi.getList', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case response to camelCase', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            {
              id: 1,
              name: '告警邮件模板',
              channel: 'email',
              subject: '【告警】{{station_name}} - {{device_name}}',
              body: '设备 {{device_name}} 发生 {{level }} 级告警',
              variables: ['station_name', 'device_name', 'level'],
              enabled: true,
              created_at: '2026-01-15T08:00:00Z',
              updated_at: '2026-02-20T10:30:00Z',
            },
            {
              id: 2,
              name: '工单短信模板',
              channel: 'sms',
              subject: '工单通知',
              body: '您有新的工单: {{workorder_title}}',
              variables: ['workorder_title'],
              enabled: false,
              created_at: '2026-01-20T09:00:00Z',
              updated_at: '2026-03-01T14:00:00Z',
            },
          ],
          total: 2,
          page: 1,
          page_size: 20,
        },
        timestamp: 1786370000,
      },
    });

    const res = await notificationTemplateApi.getList({ page: 1, pageSize: 20 });

    expect(api.get).toHaveBeenCalledWith('/notifications/templates', {
      params: { page: 1, page_size: 20 },
    });

    const items = res.data.items;
    expect(items).toHaveLength(2);

    // First template
    expect(items[0]).toEqual({
      id: 1,
      name: '告警邮件模板',
      channel: 'email',
      subject: '【告警】{{station_name}} - {{device_name}}',
      body: '设备 {{device_name}} 发生 {{level }} 级告警',
      variables: ['station_name', 'device_name', 'level'],
      enabled: true,
      createdAt: '2026-01-15T08:00:00Z',
      updatedAt: '2026-02-20T10:30:00Z',
    });

    // Second template
    expect(items[1].id).toBe(2);
    expect(items[1].channel).toBe('sms');
    expect(items[1].enabled).toBe(false);
    expect(items[1].variables).toEqual(['workorder_title']);
  });

  it('handles empty list', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [],
          total: 0,
          page: 1,
          page_size: 100,
        },
        timestamp: 1786370000,
      },
    });

    const res = await notificationTemplateApi.getList();

    expect(res.data.items).toHaveLength(0);
    expect(res.data.total).toBe(0);
  });

  it('handles missing fields with defaults', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [{}],
          total: 1,
          page: 1,
          page_size: 20,
        },
        timestamp: 1786370000,
      },
    });

    const res = await notificationTemplateApi.getList();
    const item = res.data.items[0];

    expect(item).toEqual({
      id: 0,
      name: '',
      channel: '',
      subject: '',
      body: '',
      variables: [],
      enabled: false,
      createdAt: '',
      updatedAt: '',
    });
  });

  it('passes pagination params correctly', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 2, page_size: 50 },
        timestamp: 1786370000,
      },
    });

    await notificationTemplateApi.getList({ page: 2, pageSize: 50 });

    expect(api.get).toHaveBeenCalledWith('/notifications/templates', {
      params: { page: 2, page_size: 50 },
    });
  });
});
