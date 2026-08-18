/**
 * api ext16 — /inspection/plans, /inspection/templates, /inspection/tasks 三新端点对接测试
 */
import {
  inspectionPlanApi,
  inspectionTemplateApi,
  inspectionTaskApi,
} from '../api';

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

function makeResponse(data: unknown) {
  return { data: { code: 200, message: 'success', data, timestamp: 1786379741 } };
}

describe('inspectionPlanApi.getList', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case response to camelCase correctly', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 1,
        name: '每日例行巡检',
        station_id: 5,
        station_name: '浦东充电站',
        type: 'daily',
        status: 'pending',
        scheduled_date: '2026-08-11',
        cycle: 'daily',
        assigned_to: 3,
        assigned_name: '张三',
        template_id: 2,
        description: '每日设备巡检',
        created_at: '2026-08-10T10:00:00Z',
        updated_at: '2026-08-10T10:00:00Z',
      }],
      total: 1,
      page: 1,
      page_size: 50,
    }));

    const result = await inspectionPlanApi.getList({ page: 1, pageSize: 50 });
    expect(result.data.items).toHaveLength(1);
    expect(result.data.items[0].name).toBe('每日例行巡检');
    expect(result.data.items[0].stationId).toBe(5);
    expect(result.data.items[0].stationName).toBe('浦东充电站');
    expect(result.data.items[0].templateId).toBe(2);
    expect(result.data.total).toBe(1);
  });

  it('handles empty result', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [], total: 0, page: 1, page_size: 50,
    }));
    const result = await inspectionPlanApi.getList();
    expect(result.data.items).toHaveLength(0);
    expect(result.data.total).toBe(0);
  });

  it('handles missing fields with defaults', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{ id: 2 }], total: 1, page: 1, page_size: 20,
    }));
    const result = await inspectionPlanApi.getList();
    expect(result.data.items[0].id).toBe(2);
    expect(result.data.items[0].name).toBe('');
    expect(result.data.items[0].stationId).toBe(0);
    expect(result.data.items[0].status).toBe('pending');
  });
});

describe('inspectionTemplateApi.getList', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps template with items array', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 1,
        name: '充电桩日常巡检模板',
        items: [
          { id: 1, name: '外观检查', expected: '无损坏' },
          { id: 2, name: '连接器检查', expected: '正常' },
        ],
        description: '标准日常巡检',
        item_count: 2,
        device_types: ['charger_dc'],
        target: 'charger',
        status: 'active',
        created_at: '2026-08-01T00:00:00Z',
        updated_at: '2026-08-01T00:00:00Z',
      }],
      total: 1, page: 1, page_size: 50,
    }));

    const result = await inspectionTemplateApi.getList({ page: 1, pageSize: 50 });
    expect(result.data.items).toHaveLength(1);
    expect(result.data.items[0].name).toBe('充电桩日常巡检模板');
    expect(result.data.items[0].items).toHaveLength(2);
    expect(result.data.items[0].items[0].name).toBe('外观检查');
    expect(result.data.items[0].itemCount).toBe(2);
    expect(result.data.items[0].status).toBe('active');
  });

  it('handles empty templates', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [], total: 0, page: 1, page_size: 50,
    }));
    const result = await inspectionTemplateApi.getList();
    expect(result.data.items).toHaveLength(0);
    expect(result.data.total).toBe(0);
  });

  it('handles template without items array', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{ id: 3, name: '空模板', item_count: 0, device_types: [], target: null, status: 'draft' }],
      total: 1, page: 1, page_size: 20,
    }));
    const result = await inspectionTemplateApi.getList();
    expect(result.data.items[0].items).toHaveLength(0);
    expect(result.data.items[0].itemCount).toBe(0);
    expect(result.data.items[0].status).toBe('draft');
  });
});

describe('inspectionTaskApi.getList', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps task with nested items and results', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 10,
        station_id: 3,
        station_name: '徐汇站',
        device_id: 7,
        device_name: '充电桩#7',
        type: 'weekly',
        status: 'in_progress',
        scheduled_date: '2026-08-11',
        completed_date: null,
        assigned_to: 5,
        assigned_name: '李四',
        description: '周度巡检',
        items: [
          { id: 1, name: '屏幕显示', expected: '正常', result: 'pass' },
          { id: 2, name: '充电接口', expected: '无异物', result: 'fail', note: '发现异物' },
        ],
        created_at: '2026-08-10T08:00:00Z',
        updated_at: '2026-08-10T12:00:00Z',
      }],
      total: 1, page: 1, page_size: 50,
    }));

    const result = await inspectionTaskApi.getList({ page: 1, pageSize: 50 });
    expect(result.data.items).toHaveLength(1);
    expect(result.data.items[0].stationName).toBe('徐汇站');
    expect(result.data.items[0].deviceName).toBe('充电桩#7');
    expect(result.data.items[0].status).toBe('in_progress');
    expect(result.data.items[0].items).toHaveLength(2);
    expect(result.data.items[0].items[1].result).toBe('fail');
    expect(result.data.items[0].items[1].note).toBe('发现异物');
  });

  it('handles empty tasks', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [], total: 0, page: 1, page_size: 50,
    }));
    const result = await inspectionTaskApi.getList();
    expect(result.data.items).toHaveLength(0);
    expect(result.data.total).toBe(0);
  });

  it('handles missing fields with defaults', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{ id: 99 }], total: 1, page: 1, page_size: 20,
    }));
    const result = await inspectionTaskApi.getList();
    expect(result.data.items[0].id).toBe(99);
    expect(result.data.items[0].stationId).toBe(0);
    expect(result.data.items[0].type).toBe('daily');
    expect(result.data.items[0].status).toBe('pending');
    expect(result.data.items[0].items).toHaveLength(0);
  });
});
