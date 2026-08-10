/**
 * api ext15 — /reports/efficiency 端点对接测试
 * GET /reports/efficiency → 效率报告 (含低效率告警)
 */
import { reportApi } from '../api';

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
const api = require('../api').default;

function makeResponse(data: unknown) {
  return { data: { code: 200, message: 'success', data, timestamp: 1786377711 } };
}

describe('reportApi.getEfficiency', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case response to camelCase correctly', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [
        {
          station_id: 1,
          station_name: '测试站1',
          device_id: 10,
          device_name: '充电桩A',
          efficiency: 85.5,
          uptime: 99.2,
          utilization: 72.1,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      alerts: {
        abnormal_low_efficiency: {
          count: 1,
          threshold: '<70.0%',
          items: [
            { station_id: 2, station_name: '低效站', efficiency: 45.3 },
          ],
        },
      },
    }));

    const res = await reportApi.getEfficiency();

    expect(res.code).toBe(200);
    expect(res.data.total).toBe(1);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);

    expect(res.data.items).toHaveLength(1);
    expect(res.data.items[0].stationId).toBe(1);
    expect(res.data.items[0].stationName).toBe('测试站1');
    expect(res.data.items[0].deviceId).toBe(10);
    expect(res.data.items[0].deviceName).toBe('充电桩A');
    expect(res.data.items[0].efficiency).toBe(85.5);
    expect(res.data.items[0].uptime).toBe(99.2);
    expect(res.data.items[0].utilization).toBe(72.1);

    expect(res.data.alerts.abnormalLowEfficiency.count).toBe(1);
    expect(res.data.alerts.abnormalLowEfficiency.threshold).toBe('<70.0%');
    expect(res.data.alerts.abnormalLowEfficiency.items).toHaveLength(1);
    expect(res.data.alerts.abnormalLowEfficiency.items[0].stationId).toBe(2);
    expect(res.data.alerts.abnormalLowEfficiency.items[0].stationName).toBe('低效站');
    expect(res.data.alerts.abnormalLowEfficiency.items[0].efficiency).toBe(45.3);
  });

  it('handles empty data with defaults', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      alerts: {
        abnormal_low_efficiency: { count: 0, threshold: '<70.0%', items: [] },
      },
    }));

    const res = await reportApi.getEfficiency();

    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
    expect(res.data.alerts.abnormalLowEfficiency.count).toBe(0);
    expect(res.data.alerts.abnormalLowEfficiency.threshold).toBe('<70.0%');
    expect(res.data.alerts.abnormalLowEfficiency.items).toEqual([]);
  });

  it('handles missing data fields with safe defaults', async () => {
    api.get.mockResolvedValueOnce(makeResponse({}));

    const res = await reportApi.getEfficiency();

    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
    expect(res.data.alerts.abnormalLowEfficiency.count).toBe(0);
    expect(res.data.alerts.abnormalLowEfficiency.threshold).toBe('');
    expect(res.data.alerts.abnormalLowEfficiency.items).toEqual([]);
  });

  it('passes query params correctly', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      alerts: { abnormal_low_efficiency: { count: 0, threshold: '<70.0%', items: [] } },
    }));

    await reportApi.getEfficiency({ period: 'week', page: 2, pageSize: 50 });

    expect(api.get).toHaveBeenCalledWith(
      '/reports/efficiency',
      { params: { period: 'week', page: 2, page_size: 50 } },
    );
  });
});
