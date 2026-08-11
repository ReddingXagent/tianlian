/**
 * api ext21 — /healing/executions 自愈执行记录端点对接测试
 */
import { healingExecutionApi } from '../api';

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

describe('api.ext21 — /healing/executions 自愈执行记录', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ---------- healingExecutionApi.getList ----------
  describe('healingExecutionApi.getList', () => {
    it('映射 /healing/executions 列表字段 (snake→camel)', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              {
                id: 1,
                rule_id: 5,
                rule_name: '电池过温自动降功率',
                device_id: 3,
                device_name: 'Battery-Bank-A',
                station_id: 1,
                station_name: '光储充示范站',
                triggered_at: '2026-08-11T10:00:00Z',
                status: 'success',
                action_taken: 'reduce_power_30pct',
                result: 'temperature_dropped_to_42c',
                duration: 120,
                error_message: null,
                created_at: '2026-08-11T10:02:00Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
          timestamp: 1786461964,
        },
      });

      const res = await healingExecutionApi.getList({ page: 1, pageSize: 20 });

      expect(mockGet).toHaveBeenCalledWith('/healing/executions', {
        params: { page: 1, page_size: 20 },
      });
      expect(res.code).toBe(200);
      expect(res.data.items).toHaveLength(1);
      const item = res.data.items[0];
      expect(item.id).toBe(1);
      expect(item.ruleId).toBe(5);
      expect(item.ruleName).toBe('电池过温自动降功率');
      expect(item.deviceId).toBe(3);
      expect(item.deviceName).toBe('Battery-Bank-A');
      expect(item.stationId).toBe(1);
      expect(item.triggeredAt).toBe('2026-08-11T10:00:00Z');
      expect(item.status).toBe('success');
      expect(item.actionTaken).toBe('reduce_power_30pct');
      expect(item.result).toBe('temperature_dropped_to_42c');
      expect(item.duration).toBe(120);
      expect(item.errorMessage).toBeNull();
    });

    it('空列表分页结构', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [],
            total: 0,
            page: 1,
            page_size: 20,
          },
          timestamp: 1786461964,
        },
      });

      const res = await healingExecutionApi.getList();

      expect(res.data.items).toHaveLength(0);
      expect(res.data.total).toBe(0);
      expect(res.data.page).toBe(1);
      expect(res.data.pageSize).toBe(20);
    });

    it('默认分页参数 (无 params)', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: { items: [], total: 0, page: 1, page_size: 20 },
          timestamp: 0,
        },
      });

      await healingExecutionApi.getList();

      expect(mockGet).toHaveBeenCalledWith('/healing/executions', {
        params: { page: undefined, page_size: undefined },
      });
    });

    it('缺失字段使用默认值', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [{}],
            total: 1,
            page: 1,
            page_size: 20,
          },
          timestamp: 0,
        },
      });

      const res = await healingExecutionApi.getList();
      const item = res.data.items[0];

      expect(item.id).toBe(0);
      expect(item.ruleId).toBe(0);
      expect(item.ruleName).toBe('');
      expect(item.deviceId).toBe(0);
      expect(item.status).toBe('');
      expect(item.result).toBeNull();
      expect(item.errorMessage).toBeNull();
      expect(item.duration).toBe(0);
    });

    it('多记录分页 page=2', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              { id: 21, rule_id: 1, status: 'success' },
              { id: 22, rule_id: 2, status: 'failed', error_message: 'timeout' },
            ],
            total: 50,
            page: 2,
            page_size: 20,
          },
          timestamp: 0,
        },
      });

      const res = await healingExecutionApi.getList({ page: 2, pageSize: 20 });

      expect(res.data.page).toBe(2);
      expect(res.data.total).toBe(50);
      expect(res.data.items).toHaveLength(2);
      expect(res.data.items[0].status).toBe('success');
      expect(res.data.items[1].status).toBe('failed');
      expect(res.data.items[1].errorMessage).toBe('timeout');
    });
  });

  // ---------- healingExecutionApi.getById ----------
  describe('healingExecutionApi.getById', () => {
    it('映射 /healing/executions/{id} 详情字段', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            id: 42,
            rule_id: 3,
            rule_name: '充电桩离线重启',
            device_id: 7,
            device_name: 'Charger-007',
            station_id: 2,
            station_name: '高速服务区充电站',
            triggered_at: '2026-08-10T15:30:00Z',
            status: 'failed',
            action_taken: 'remote_reboot',
            result: null,
            duration: 300,
            error_message: 'Device not responding after reboot',
            created_at: '2026-08-10T15:35:00Z',
          },
          timestamp: 1786462000,
        },
      });

      const res = await healingExecutionApi.getById(42);

      expect(mockGet).toHaveBeenCalledWith('/healing/executions/42');
      expect(res.code).toBe(200);
      expect(res.data.id).toBe(42);
      expect(res.data.ruleId).toBe(3);
      expect(res.data.ruleName).toBe('充电桩离线重启');
      expect(res.data.deviceName).toBe('Charger-007');
      expect(res.data.stationName).toBe('高速服务区充电站');
      expect(res.data.status).toBe('failed');
      expect(res.data.actionTaken).toBe('remote_reboot');
      expect(res.data.result).toBeNull();
      expect(res.data.duration).toBe(300);
      expect(res.data.errorMessage).toBe('Device not responding after reboot');
    });

    it('404 记录不存在仍映射字段默认值', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 404,
          message: '执行记录#999不存在',
          data: null,
          timestamp: 0,
        },
      });

      const res = await healingExecutionApi.getById(999);

      expect(res.code).toBe(404);
      expect(res.data.id).toBe(0);
      expect(res.data.ruleName).toBe('');
    });

    it('URL 参数正确传递', async () => {
      mockGet.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: { id: 1 },
          timestamp: 0,
        },
      });

      await healingExecutionApi.getById(1);
      expect(mockGet).toHaveBeenCalledWith('/healing/executions/1');

      await healingExecutionApi.getById(100);
      expect(mockGet).toHaveBeenLastCalledWith('/healing/executions/100');
    });
  });
});
