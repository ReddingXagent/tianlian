/**
 * api ext7 — Energy Trend API (GET /energy/trend)
 * Target: snake_case → camelCase mapping for daily trend items
 */
import { energyApi } from '../api';

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

describe('api ext7 — Energy Trend API (GET /energy/trend)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case trend array → camelCase EnergyTrendItem[]', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          trend: [
            {
              date: '2026-08-09',
              pv_generation: 158.5,
              charging_amount: 58.2,
              discharge_amount: 68.8,
              pv_revenue: 66.57,
              charging_revenue: 49.47,
              discharge_revenue: 28.9,
              total_revenue: 144.94,
            },
            {
              date: '2026-08-10',
              pv_generation: 155.0,
              charging_amount: 57.0,
              discharge_amount: 68.0,
              pv_revenue: 65.1,
              charging_revenue: 48.45,
              discharge_revenue: 28.56,
              total_revenue: 142.11,
            },
          ],
        },
      },
    });

    const res = await energyApi.getTrend();

    expect(api.get).toHaveBeenCalledWith('/energy/trend');
    expect(res.data).toHaveLength(2);
    expect(res.data[0]).toEqual({
      date: '2026-08-09',
      pvGeneration: 158.5,
      chargingAmount: 58.2,
      dischargeAmount: 68.8,
      pvRevenue: 66.57,
      chargingRevenue: 49.47,
      dischargeRevenue: 28.9,
      totalRevenue: 144.94,
    });
    expect(res.data[1].date).toBe('2026-08-10');
    expect(res.data[1].pvGeneration).toBe(155.0);
  });

  it('handles empty trend array', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { trend: [] },
      },
    });

    const res = await energyApi.getTrend();
    expect(res.data).toEqual([]);
  });

  it('handles missing trend field with empty array default', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: {},
      },
    });

    const res = await energyApi.getTrend();
    expect(res.data).toEqual([]);
  });

  it('handles null data gracefully', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: null,
      },
    });

    const res = await energyApi.getTrend();
    expect(res.data).toEqual([]);
  });

  it('fills missing fields in trend items with defaults', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: {
          trend: [{ date: '2026-08-10' }],
        },
      },
    });

    const res = await energyApi.getTrend();
    expect(res.data).toHaveLength(1);
    expect(res.data[0]).toEqual({
      date: '2026-08-10',
      pvGeneration: 0,
      chargingAmount: 0,
      dischargeAmount: 0,
      pvRevenue: 0,
      chargingRevenue: 0,
      dischargeRevenue: 0,
      totalRevenue: 0,
    });
  });
});
