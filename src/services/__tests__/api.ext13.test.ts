/**
 * api ext13 — PricingRule API (GET /pricing, GET /pricing/{id})
 */
import { pricingApi } from '../api';

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

describe('pricingApi', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('getList', () => {
    it('calls GET /pricing with pagination params', async () => {
      api.get.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              {
                id: 1,
                name: '峰时电价',
                period_type: 'peak',
                start_time: '08:00',
                end_time: '12:00',
                energy_price: 1.2,
                service_price: 0.8,
                power_limit: 60,
                enabled: true,
                created_at: '2026-08-10T00:00:00Z',
                updated_at: '2026-08-10T00:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
          timestamp: 1786375874,
        },
      });

      const res = await pricingApi.getList({ page: 1, pageSize: 20 });

      expect(api.get).toHaveBeenCalledWith('/pricing', {
        params: { page: 1, page_size: 20 },
      });
      expect(res.data.items).toHaveLength(1);
      expect(res.data.items[0]).toEqual({
        id: 1,
        name: '峰时电价',
        periodType: 'peak',
        startTime: '08:00',
        endTime: '12:00',
        energyPrice: 1.2,
        servicePrice: 0.8,
        powerLimit: 60,
        enabled: true,
        createdAt: '2026-08-10T00:00:00Z',
        updatedAt: '2026-08-10T00:00:00Z',
      });
      expect(res.data.total).toBe(1);
    });

    it('handles empty list', async () => {
      api.get.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: { items: [], total: 0, page: 1, page_size: 20 },
          timestamp: 1786375874,
        },
      });

      const res = await pricingApi.getList();
      expect(res.data.items).toHaveLength(0);
      expect(res.data.total).toBe(0);
    });

    it('handles missing fields gracefully', async () => {
      api.get.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [{ id: 2 }],
            total: 1,
            page: 1,
            page_size: 20,
          },
          timestamp: 1786375874,
        },
      });

      const res = await pricingApi.getList();
      expect(res.data.items[0].name).toBe('');
      expect(res.data.items[0].periodType).toBe('');
      expect(res.data.items[0].enabled).toBe(false);
    });
  });

  describe('getById', () => {
    it('calls GET /pricing/{id} and maps fields', async () => {
      api.get.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: {
            id: 5,
            name: '谷时电价',
            period_type: 'valley',
            start_time: '00:00',
            end_time: '06:00',
            energy_price: 0.3,
            service_price: 0.2,
            power_limit: 30,
            enabled: true,
            created_at: '2026-08-09T00:00:00Z',
            updated_at: '2026-08-10T00:00:00Z',
          },
          timestamp: 1786375874,
        },
      });

      const res = await pricingApi.getById(5);
      expect(api.get).toHaveBeenCalledWith('/pricing/5');
      expect(res.data?.id).toBe(5);
      expect(res.data?.name).toBe('谷时电价');
      expect(res.data?.periodType).toBe('valley');
      expect(res.data?.startTime).toBe('00:00');
      expect(res.data?.endTime).toBe('06:00');
      expect(res.data?.energyPrice).toBe(0.3);
      expect(res.data?.servicePrice).toBe(0.2);
      expect(res.data?.powerLimit).toBe(30);
      expect(res.data?.enabled).toBe(true);
    });

    it('returns null when pricing rule not found', async () => {
      api.get.mockResolvedValueOnce({
        data: {
          code: 404,
          message: '定价规则不存在',
          data: null,
          timestamp: 1786375874,
        },
      });

      const res = await pricingApi.getById(999);
      expect(res.data).toBeNull();
    });
  });
});
