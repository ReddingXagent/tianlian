/**
 * api ext22 — /devices/{id}/health/history 设备健康历史记录端点对接测试
 */
import { deviceApi } from '../api';

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

describe('api.ext22 — /devices/{id}/health/history 设备健康历史', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ---------- deviceApi.getHealthHistory ----------
  describe('deviceApi.getHealthHistory', () => {
    it('映射 /devices/{id}/health/history 列表字段 (snake→camel)', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: [
            {
              device_id: 1,
              health_score: 95.5,
              health_status: 'healthy',
              health_status_display: '健康',
              dimension_scores: { performance: 90, connectivity: 100 },
              checked_at: '2026-08-11T10:00:00Z',
            },
            {
              device_id: 1,
              health_score: 88.0,
              health_status: 'warning',
              health_status_display: '警告',
              dimension_scores: { performance: 80, connectivity: 96 },
              checked_at: '2026-08-10T10:00:00Z',
            },
          ],
          timestamp: 1786462885,
        },
      });

      const res = await deviceApi.getHealthHistory(1);
      expect(res.code).toBe(200);
      expect(res.data).toHaveLength(2);
      expect(res.data[0]).toEqual({
        deviceId: 1,
        healthScore: 95.5,
        healthStatus: 'healthy',
        healthStatusDisplay: '健康',
        dimensionScores: { performance: 90, connectivity: 100 },
        checkedAt: '2026-08-11T10:00:00Z',
      });
      expect(res.data[1].healthStatus).toBe('warning');
      expect(res.data[1].dimensionScores.connectivity).toBe(96);
    });

    it('handles empty history list', async () => {
      mockGet.mockResolvedValue({
        data: { code: 200, message: 'success', data: [], timestamp: 1786462885 },
      });

      const res = await deviceApi.getHealthHistory(999);
      expect(res.code).toBe(200);
      expect(res.data).toEqual([]);
    });

    it('uses deviceId from URL when device_id missing in item', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: [
            {
              health_score: 70,
              health_status: 'fault',
              health_status_display: '故障',
              dimension_scores: {},
              checked_at: '2026-08-09T00:00:00Z',
            },
          ],
          timestamp: 1786462885,
        },
      });

      const res = await deviceApi.getHealthHistory(42);
      expect(res.data[0].deviceId).toBe(42);
    });

    it('falls back to created_at when checked_at missing', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: [
            {
              device_id: 5,
              health_score: 100,
              health_status: 'healthy',
              health_status_display: '健康',
              dimension_scores: {},
              created_at: '2026-08-01T00:00:00Z',
            },
          ],
          timestamp: 1786462885,
        },
      });

      const res = await deviceApi.getHealthHistory(5);
      expect(res.data[0].checkedAt).toBe('2026-08-01T00:00:00Z');
    });

    it('applies default values for missing fields', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: [{}],
          timestamp: 1786462885,
        },
      });

      const res = await deviceApi.getHealthHistory(7);
      expect(res.data[0]).toEqual({
        deviceId: 7,
        healthScore: 0,
        healthStatus: '',
        healthStatusDisplay: '',
        dimensionScores: {},
        checkedAt: '',
      });
    });

    it('calls correct URL', async () => {
      mockGet.mockResolvedValue({
        data: { code: 200, message: 'success', data: [], timestamp: 0 },
      });

      await deviceApi.getHealthHistory(123);
      expect(mockGet).toHaveBeenCalledWith('/devices/123/health/history');
    });

    it('handles null data field gracefully', async () => {
      mockGet.mockResolvedValue({
        data: { code: 200, message: 'success', data: null, timestamp: 0 },
      });

      const res = await deviceApi.getHealthHistory(1);
      expect(res.data).toEqual([]);
    });
  });
});
