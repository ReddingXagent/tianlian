/**
 * Tests for energyApi — GET /energy/summary
 * F751: station-app energy summary API docking
 */
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, { energyApi } from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);

beforeEach(() => {
  jest.clearAllMocks();
  mockAxios.reset();
  (SecureStore.getItemAsync as jest.Mock).mockResolvedValue('test-token');
});

const mockEnergySummary = {
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

describe('energyApi contract', () => {
  it('getSummary maps snake_case → camelCase correctly', async () => {
    mockAxios.onGet('/energy/summary').reply(200, mockEnergySummary);

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
    mockAxios.onGet('/energy/summary').reply(200, mockEnergySummary);

    const res = await energyApi.getSummary();
    expect(res.data.yoy.pvGenerationYoY).toBe(8.7);
    expect(res.data.yoy.chargingAmountYoY).toBe(5.3);
    expect(res.data.yoy.dischargeAmountYoY).toBe(11.1);
    expect(res.data.yoy.totalRevenueYoY).toBe(13.6);
  });

  it('maps price_info nested fields', async () => {
    mockAxios.onGet('/energy/summary').reply(200, mockEnergySummary);

    const res = await energyApi.getSummary();
    expect(res.data.priceInfo.feedInTariff).toBe(0.42);
    expect(res.data.priceInfo.chargingPrice).toBe(0.85);
    expect(res.data.priceInfo.dischargePrice).toBe(0.42);
  });

  it('handles missing data gracefully (defaults to zeros)', async () => {
    mockAxios.onGet('/energy/summary').reply(200, {
      code: 200,
      message: 'success',
      data: {},
    });

    const res = await energyApi.getSummary();
    expect(res.data.pvGeneration).toBe(0);
    expect(res.data.totalRevenue).toBe(0);
    expect(res.data.yoy.pvGenerationYoY).toBe(0);
    expect(res.data.priceInfo.feedInTariff).toBe(0);
  });

  it('sends Authorization header with token', async () => {
    mockAxios.onGet('/energy/summary').reply(200, mockEnergySummary);

    await energyApi.getSummary();
    const req = mockAxios.history.get[0];
    expect(req.headers?.Authorization).toBe('Bearer test-token');
  });

  it('propagates error on 500', async () => {
    mockAxios.onGet('/energy/summary').reply(500, { detail: 'server error' });

    await expect(energyApi.getSummary()).rejects.toThrow();
  });
});
