import { analyticsRevenueApi } from '../api';

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

const axios = require('axios');
const mockGet = axios.create().get as jest.Mock;

describe('analyticsRevenueApi', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case summary fields to camelCase', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          summary: {
            total_revenue: 12345.67,
            total_kwh: 890.5,
            total_orders: 42,
            avg_per_order: 293.95,
          },
          trend: [{ date: '2026-08-01', revenue: 1000 }],
        },
        timestamp: 1786463477,
      },
    });

    const res = await analyticsRevenueApi.getSummary();
    expect(res.data.summary.totalRevenue).toBe(12345.67);
    expect(res.data.summary.totalKwh).toBe(890.5);
    expect(res.data.summary.totalOrders).toBe(42);
    expect(res.data.summary.avgPerOrder).toBe(293.95);
    expect(res.data.trend).toHaveLength(1);
  });

  it('handles empty/zero data gracefully', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          summary: {
            total_revenue: 0.0,
            total_kwh: 0.0,
            total_orders: 0,
            avg_per_order: 0.0,
          },
          trend: [],
        },
        timestamp: 1786463477,
      },
    });

    const res = await analyticsRevenueApi.getSummary();
    expect(res.data.summary.totalRevenue).toBe(0);
    expect(res.data.summary.totalOrders).toBe(0);
    expect(res.data.trend).toEqual([]);
  });

  it('handles null data with defaults', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: null,
        timestamp: 1786463477,
      },
    });

    const res = await analyticsRevenueApi.getSummary();
    expect(res.data.summary.totalRevenue).toBe(0);
    expect(res.data.summary.totalKwh).toBe(0);
    expect(res.data.summary.totalOrders).toBe(0);
    expect(res.data.summary.avgPerOrder).toBe(0);
    expect(res.data.trend).toEqual([]);
  });

  it('handles missing summary fields with defaults', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          summary: {},
          trend: [],
        },
        timestamp: 1786463477,
      },
    });

    const res = await analyticsRevenueApi.getSummary();
    expect(res.data.summary.totalRevenue).toBe(0);
    expect(res.data.summary.totalKwh).toBe(0);
    expect(res.data.summary.totalOrders).toBe(0);
    expect(res.data.summary.avgPerOrder).toBe(0);
  });

  it('passes query params with snake_case conversion', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { summary: { total_revenue: 0 }, trend: [] },
        timestamp: 1786463477,
      },
    });

    await analyticsRevenueApi.getSummary({
      startDate: '2026-08-01',
      endDate: '2026-08-11',
      period: 'month',
      stationId: 5,
    });

    const callArgs = mockGet.mock.calls[0];
    expect(callArgs[0]).toBe('/analytics/revenue');
    expect(callArgs[1].params).toEqual({
      start_date: '2026-08-01',
      end_date: '2026-08-11',
      period: 'month',
      station_id: '5',
    });
  });

  it('passes no params when undefined', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { summary: { total_revenue: 0 }, trend: [] },
        timestamp: 1786463477,
      },
    });

    await analyticsRevenueApi.getSummary();

    const callArgs = mockGet.mock.calls[0];
    expect(callArgs[0]).toBe('/analytics/revenue');
    expect(callArgs[1].params).toEqual({});
  });

  it('handles trend array with multiple entries', async () => {
    const trendData = [
      { date: '2026-08-01', revenue: 1000, kwh: 50 },
      { date: '2026-08-02', revenue: 2000, kwh: 100 },
      { date: '2026-08-03', revenue: 1500, kwh: 75 },
    ];
    mockGet.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          summary: {
            total_revenue: 4500,
            total_kwh: 225,
            total_orders: 6,
            avg_per_order: 750,
          },
          trend: trendData,
        },
        timestamp: 1786463477,
      },
    });

    const res = await analyticsRevenueApi.getSummary();
    expect(res.data.trend).toHaveLength(3);
    expect(res.data.summary.totalRevenue).toBe(4500);
  });
});
