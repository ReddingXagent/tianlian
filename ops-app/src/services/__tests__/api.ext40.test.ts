import { stationApi } from '../api';

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// Mock axios
jest.mock('axios', () => {
  const mockAxios: Record<string, any> = {
    create: jest.fn(() => mockAxios),
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    defaults: { headers: { common: {} } },
  };
  return mockAxios;
});

import axios from 'axios';
const mockAxios = axios as jest.Mocked<typeof axios>;

describe('stationApi (ext40 — GET /stations, GET /stations/{id})', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('getList', () => {
    it('maps snake_case to camelCase correctly', async () => {
      mockAxios.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              {
                id: 1,
                name: '北京光伏电站',
                code: 'ST2026001',
                province: '北京省',
                city: '北京',
                district: '高新区',
                address: '北京市高新区新能源产业园47号',
                lat: 39.9042,
                lon: 116.4074,
                operator_id: null,
                operator_name: null,
                team_id: null,
                total_power: 1772.0,
                total_devices: 6,
                gun_count: 0,
                venue_type: null,
                total_cost: null,
                parking_spots: null,
                station_type: null,
                status: 'normal',
                health_score: 0.92,
                created_at: '2026-06-23T03:20:01+08:00',
                updated_at: null,
                branding: {
                  operator_name: '天链',
                  logo_url: '',
                  service_phone: '',
                  theme_color: '#00A86B',
                  source: 'default',
                },
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
          timestamp: 1786584661,
        },
      });

      const res = await stationApi.getList({ page: 1, pageSize: 20 });
      expect(res.data.items).toHaveLength(1);
      const s = res.data.items[0];
      expect(s.id).toBe(1);
      expect(s.name).toBe('北京光伏电站');
      expect(s.lat).toBe(39.9042);
      expect(s.lon).toBe(116.4074);
      expect(s.totalPower).toBe(1772.0);
      expect(s.totalDevices).toBe(6);
      expect(s.gunCount).toBe(0);
      expect(s.healthScore).toBe(0.92);
      expect(s.status).toBe('normal');
      expect(s.stationType).toBeNull();
      expect(s.operatorId).toBeNull();
      expect(s.branding).not.toBeNull();
      expect(s.branding!.operatorName).toBe('天链');
      expect(s.branding!.themeColor).toBe('#00A86B');
      expect(s.branding!.source).toBe('default');
      expect(res.data.total).toBe(1);
      expect(res.data.page).toBe(1);
      expect(res.data.pageSize).toBe(20);
    });

    it('handles empty list', async () => {
      mockAxios.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: { items: [], total: 0, page: 1, page_size: 20 },
        },
      });

      const res = await stationApi.getList();
      expect(res.data.items).toHaveLength(0);
      expect(res.data.total).toBe(0);
    });

    it('handles null/missing fields with defaults', async () => {
      mockAxios.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [{ id: 5, name: '测试站' }],
            total: 1,
          },
        },
      });

      const res = await stationApi.getList();
      const s = res.data.items[0];
      expect(s.id).toBe(5);
      expect(s.name).toBe('测试站');
      expect(s.code).toBe('');
      expect(s.province).toBe('');
      expect(s.lat).toBe(0);
      expect(s.lon).toBe(0);
      expect(s.totalPower).toBe(0);
      expect(s.healthScore).toBe(0);
      expect(s.branding).toBeNull();
      expect(s.updatedAt).toBeNull();
    });

    it('handles null data', async () => {
      mockAxios.get.mockResolvedValue({
        data: { code: 200, message: 'success', data: null },
      });

      const res = await stationApi.getList();
      expect(res.data.items).toHaveLength(0);
      expect(res.data.total).toBe(0);
    });

    it('calls correct endpoint', async () => {
      mockAxios.get.mockResolvedValue({
        data: { code: 200, message: 'success', data: { items: [], total: 0 } },
      });

      await stationApi.getList({ page: 2, pageSize: 10, status: 'normal', keyword: '北京' });
      expect(mockAxios.get).toHaveBeenCalledWith(
        '/stations',
        expect.objectContaining({
          params: { page: '2', page_size: '10', status: 'normal', keyword: '北京' },
        }),
      );
    });
  });

  describe('getDetail', () => {
    it('maps station detail correctly', async () => {
      mockAxios.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            id: 1,
            name: '北京光伏电站',
            code: 'ST2026001',
            province: '北京省',
            city: '北京',
            district: '高新区',
            address: '北京市高新区',
            lat: 39.9042,
            lon: 116.4074,
            total_power: 1772.0,
            total_devices: 6,
            gun_count: 0,
            health_score: 0.92,
            status: 'normal',
            station_type: 'pv_storage charging',
            operator_id: 3,
            operator_name: '运维一组',
            team_id: 7,
            venue_type: 'indoor',
            total_cost: 1500000,
            parking_spots: 50,
            created_at: '2026-06-23T03:20:01+08:00',
            updated_at: '2026-07-01T10:00:00+08:00',
            branding: {
              operator_name: '天链',
              logo_url: 'https://example.com/logo.png',
              service_phone: '400-123-4567',
              theme_color: '#00A86B',
              source: 'custom',
            },
          },
        },
      });

      const res = await stationApi.getDetail(1);
      const s = res.data;
      expect(s.id).toBe(1);
      expect(s.stationType).toBe('pv_storage charging');
      expect(s.operatorId).toBe(3);
      expect(s.operatorName).toBe('运维一组');
      expect(s.teamId).toBe(7);
      expect(s.venueType).toBe('indoor');
      expect(s.totalCost).toBe(1500000);
      expect(s.parkingSpots).toBe(50);
      expect(s.updatedAt).toBe('2026-07-01T10:00:00+08:00');
      expect(s.branding!.logoUrl).toBe('https://example.com/logo.png');
      expect(s.branding!.servicePhone).toBe('400-123-4567');
      expect(s.branding!.source).toBe('custom');
    });

    it('calls correct endpoint with id', async () => {
      mockAxios.get.mockResolvedValue({
        data: { code: 200, message: 'success', data: { id: 42 } },
      });

      await stationApi.getDetail(42);
      expect(mockAxios.get).toHaveBeenCalledWith('/stations/42');
    });
  });
});
