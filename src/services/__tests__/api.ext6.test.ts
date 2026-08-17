/**
 * api ext6 — Energy API (GET /energy/summary)
 * Target: snake_case → camelCase mapping with defaults
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

const api = require('../api').default as jest.Mocked<{ get: jest.Mock }>;

describe('api ext6 — energy API (GET /energy/summary)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case backend → camelCase EnergySummary', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          period: 'month',
          days: 10,
          pv_generation: 1650.0,
          charging_amount: 525.0,
          discharge_amount: 702.0,
          pv_revenue: 693.0,
          charging_revenue: 446.25,
          discharge_revenue: 294.84,
          total_revenue: 1434.09,
          yoy: {
            pv_generation_yoy: 8.7,
            charging_amount_yoy: 5.3,
            discharge_amount_yoy: 11.1,
            total_revenue_yoy: 13.6,
          },
          price_info: {
            feed_in_tariff: 0.42,
            charging_price: 0.85,
            discharge_price: 0.42,
          },
        },
      },
    });

    const res = await energyApi.getSummary();

    expect(api.get).toHaveBeenCalledWith('/energy/summary');
    expect(res.data).toEqual({
      period: 'month',
      days: 10,
      pvGeneration: 1650.0,
      chargingAmount: 525.0,
      dischargeAmount: 702.0,
      pvRevenue: 693.0,
      chargingRevenue: 446.25,
      dischargeRevenue: 294.84,
      totalRevenue: 1434.09,
      yoy: {
        pvGenerationYoy: 8.7,
        chargingAmountYoy: 5.3,
        dischargeAmountYoy: 11.1,
        totalRevenueYoy: 13.6,
      },
      priceInfo: {
        feedInTariff: 0.42,
        chargingPrice: 0.85,
        dischargePrice: 0.42,
      },
    });
  });

  it('handles missing fields with defaults', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: {},
      },
    });

    const res = await energyApi.getSummary();

    expect(res.data.period).toBe('month');
    expect(res.data.days).toBe(0);
    expect(res.data.pvGeneration).toBe(0);
    expect(res.data.totalRevenue).toBe(0);
    expect(res.data.yoy.pvGenerationYoy).toBe(0);
    expect(res.data.priceInfo.feedInTariff).toBe(0);
  });

  it('handles null data gracefully', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: null,
      },
    });

    const res = await energyApi.getSummary();

    expect(res.data.period).toBe('month');
    expect(res.data.days).toBe(0);
    expect(res.data.totalRevenue).toBe(0);
  });
});
