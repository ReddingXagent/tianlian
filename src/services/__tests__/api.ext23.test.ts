/**
 * api ext23 — /work-orders/stats 工单统计端点对接测试
 */
import { workOrderApi } from '../api';

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

// eslint-disable-next-line @typescript-eslint/no-require-imports
const axios = require('axios');
const mockGet = axios.create().get as jest.Mock;

describe('api.ext23 — /work-orders/stats 工单统计', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ---------- workOrderApi.getStats ----------
  describe('workOrderApi.getStats', () => {
    it('映射 /work-orders/stats 字段 (snake→camel)', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            total: 113,
            status_distribution: {
              processing: 4,
              accepted: 2,
              pending: 100,
              completed: 7,
            },
            level_distribution: {
              P1: 7,
              P2: 5,
              P0: 3,
              warning: 98,
            },
            type_distribution: {
              maintenance: 1,
              inspection: 6,
              upgrade: 4,
              repair: 102,
            },
            groups: {
              processing: 4,
              accepted: 2,
              pending: 100,
              completed: 7,
            },
          },
          timestamp: 1786463145,
        },
      });

      const res = await workOrderApi.getStats();

      expect(mockGet).toHaveBeenCalledWith('/work-orders/stats');
      expect(res.data.total).toBe(113);
      expect(res.data.statusDistribution).toEqual({
        processing: 4,
        accepted: 2,
        pending: 100,
        completed: 7,
      });
      expect(res.data.levelDistribution).toEqual({
        P1: 7,
        P2: 5,
        P0: 3,
        warning: 98,
      });
      expect(res.data.typeDistribution).toEqual({
        maintenance: 1,
        inspection: 6,
        upgrade: 4,
        repair: 102,
      });
      expect(res.data.groups).toEqual({
        processing: 4,
        accepted: 2,
        pending: 100,
        completed: 7,
      });
    });

    it('空 data 安全降级 — 全默认值', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {},
          timestamp: 1786463145,
        },
      });

      const res = await workOrderApi.getStats();

      expect(res.data.total).toBe(0);
      expect(res.data.statusDistribution).toEqual({});
      expect(res.data.levelDistribution).toEqual({});
      expect(res.data.typeDistribution).toEqual({});
      expect(res.data.groups).toEqual({});
    });

    it('data null 安全降级', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: null,
          timestamp: 1786463145,
        },
      });

      const res = await workOrderApi.getStats();

      expect(res.data.total).toBe(0);
      expect(res.data.statusDistribution).toEqual({});
    });

    it('部分缺失字段降级 — 只有 total', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            total: 50,
          },
          timestamp: 1786463145,
        },
      });

      const res = await workOrderApi.getStats();

      expect(res.data.total).toBe(50);
      expect(res.data.statusDistribution).toEqual({});
      expect(res.data.levelDistribution).toEqual({});
      expect(res.data.typeDistribution).toEqual({});
      expect(res.data.groups).toEqual({});
    });

    it('URL 路径验证', async () => {
      mockGet.mockResolvedValue({
        data: { code: 200, message: 'success', data: {}, timestamp: 0 },
      });

      await workOrderApi.getStats();

      expect(mockGet).toHaveBeenCalledTimes(1);
      expect(mockGet.mock.calls[0][0]).toBe('/work-orders/stats');
    });

    it('groups 字段独立于 statusDistribution — 可不同值', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            total: 10,
            status_distribution: { pending: 10 },
            level_distribution: { warning: 10 },
            type_distribution: { repair: 10 },
            groups: { group_a: 5, group_b: 5 },
          },
          timestamp: 1786463145,
        },
      });

      const res = await workOrderApi.getStats();

      expect(res.data.statusDistribution).toEqual({ pending: 10 });
      expect(res.data.groups).toEqual({ group_a: 5, group_b: 5 });
    });
  });
});
