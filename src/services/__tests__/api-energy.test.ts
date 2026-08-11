/**
 * Tests for energyApi — GET /energy/summary
 * F751: user-app energy summary API docking
 */
import { energyApi } from '../api';

import axios from 'axios';

// Mock axios and SecureStore
jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return {
    __esModule: true,
    default: {
      create: jest.fn(() => mockInstance),
    },
  };
});

jest.mock('expo-secure-store', () => ({
  __esModule: true,
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockApi = jest.mocked(axios.create).mock.results[0].value;

const mockEnergyData = {
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
  timestamp: 1786356133,
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('energyApi contract', () => {
  it('getSummary maps snake_case → camelCase correctly', async () => {
    mockApi.get.mockResolvedValueOnce({ data: mockEnergyData });

    const res = await energyApi.getSummary();
    expect(res.code).toBe(200);
    expect(res.data.period).toBe('month');
    expect(res.data.days).toBe(10);
    expect(res.data.pvGeneration).toBe(1650.0);
    expect(res.data.chargingAmount).toBe(525.0);
    expect(res.data.dischargeAmount).toBe(702.0);
    expect(res.data.pvRevenue).toBe(693.0);
    expect(res.data.chargingRevenue).toBe(446.25);
    expect(res.data.dischargeRevenue).toBe(294.84);
    expect(res.data.totalRevenue).toBe(1434.09);
  });

  it('maps yoy nested fields', async () => {
    mockApi.get.mockResolvedValueOnce({ data: mockEnergyData });

    const res = await energyApi.getSummary();
    expect(res.data.yoy.pvGenerationYoY).toBe(8.7);
    expect(res.data.yoy.chargingAmountYoY).toBe(5.3);
    expect(res.data.yoy.dischargeAmountYoY).toBe(11.1);
    expect(res.data.yoy.totalRevenueYoY).toBe(13.6);
  });

  it('maps price_info nested fields', async () => {
    mockApi.get.mockResolvedValueOnce({ data: mockEnergyData });

    const res = await energyApi.getSummary();
    expect(res.data.priceInfo.feedInTariff).toBe(0.42);
    expect(res.data.priceInfo.chargingPrice).toBe(0.85);
    expect(res.data.priceInfo.dischargePrice).toBe(0.42);
  });

  it('handles missing data gracefully', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {} },
    });

    const res = await energyApi.getSummary();
    expect(res.data.pvGeneration).toBe(0);
    expect(res.data.totalRevenue).toBe(0);
    expect(res.data.yoy.pvGenerationYoY).toBe(0);
    expect(res.data.priceInfo.feedInTariff).toBe(0);
  });

  it('calls GET /energy/summary', async () => {
    mockApi.get.mockResolvedValueOnce({ data: mockEnergyData });

    await energyApi.getSummary();
    expect(mockApi.get).toHaveBeenCalledWith('/energy/summary');
  });

  it('returns raw res when data.data is null', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: null },
    });

    const res = await energyApi.getSummary();
    expect(res.code).toBe(200);
    // data is null so the if(!d) guard returns res.data directly
    expect(res.data).toBeNull();
  });

  it('handles missing yoy object with defaults', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        code: 200,
        data: { pv_generation: 100, total_revenue: 50 },
      },
    });

    const res = await energyApi.getSummary();
    expect(res.data.pvGeneration).toBe(100);
    expect(res.data.yoy.pvGenerationYoY).toBe(0);
    expect(res.data.yoy.chargingAmountYoY).toBe(0);
  });

  it('handles missing price_info object with defaults', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        code: 200,
        data: { total_revenue: 200 },
      },
    });

    const res = await energyApi.getSummary();
    expect(res.data.priceInfo.feedInTariff).toBe(0);
    expect(res.data.priceInfo.chargingPrice).toBe(0);
    expect(res.data.priceInfo.dischargePrice).toBe(0);
  });

  it('rejects on network error', async () => {
    mockApi.get.mockRejectedValueOnce(new Error('Network Error'));

    await expect(energyApi.getSummary()).rejects.toThrow('Network Error');
  });
});
