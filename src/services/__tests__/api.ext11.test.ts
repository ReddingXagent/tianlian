/**
 * api ext11 — WorkOrderReport API (GET /reports/workorders)
 * Target: 30天工单报告 snake_case → camelCase mapping
 */
import { reportApi } from '../api';

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

describe('reportApi.getWorkOrderReport', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case response to camelCase', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          period_days: 30,
          total_workorders: 150,
          type_distribution: { repair: 80, inspection: 50, maintenance: 20 },
          level_distribution: { info: 30, warning: 70, critical: 40, fatal: 10 },
          status_distribution: { completed: 120, processing: 20, pending: 10 },
          completion_rate: 0.8,
          efficiency: {
            avg_response_hours: 2.5,
            avg_completion_hours: 24.3,
          },
          engineer_performance: [
            {
              engineer_id: 1,
              engineer_name: '张三',
              completed_count: 45,
              avg_completion_hours: 18.2,
            },
            {
              engineer_id: 2,
              engineer_name: '李四',
              completed_count: 30,
              avg_completion_hours: 22.5,
            },
          ],
        },
        timestamp: 1786370000,
      },
    });

    const res = await reportApi.getWorkOrderReport();

    expect(api.get).toHaveBeenCalledWith('/reports/workorders');

    expect(res.data.periodDays).toBe(30);
    expect(res.data.totalWorkorders).toBe(150);
    expect(res.data.typeDistribution).toEqual({ repair: 80, inspection: 50, maintenance: 20 });
    expect(res.data.levelDistribution.fatal).toBe(10);
    expect(res.data.statusDistribution.completed).toBe(120);
    expect(res.data.completionRate).toBe(0.8);

    expect(res.data.efficiency.avgResponseHours).toBe(2.5);
    expect(res.data.efficiency.avgCompletionHours).toBe(24.3);

    expect(res.data.engineerPerformance).toHaveLength(2);
    expect(res.data.engineerPerformance[0]).toEqual({
      engineerId: 1,
      engineerName: '张三',
      completedCount: 45,
      avgCompletionHours: 18.2,
    });
    expect(res.data.engineerPerformance[1].engineerName).toBe('李四');
  });

  it('handles empty/default response', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          period_days: 30,
          total_workorders: 0,
          type_distribution: {},
          level_distribution: {},
          status_distribution: {},
          completion_rate: 0.0,
          efficiency: {
            avg_response_hours: 0.0,
            avg_completion_hours: 0.0,
          },
          engineer_performance: [],
        },
        timestamp: 1786370000,
      },
    });

    const res = await reportApi.getWorkOrderReport();

    expect(res.data.totalWorkorders).toBe(0);
    expect(res.data.engineerPerformance).toHaveLength(0);
    expect(res.data.efficiency.avgResponseHours).toBe(0);
  });

  it('handles missing fields with defaults', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {},
        timestamp: 1786370000,
      },
    });

    const res = await reportApi.getWorkOrderReport();

    expect(res.data.periodDays).toBe(30);
    expect(res.data.totalWorkorders).toBe(0);
    expect(res.data.typeDistribution).toEqual({});
    expect(res.data.completionRate).toBe(0);
    expect(res.data.efficiency).toEqual({
      avgResponseHours: 0,
      avgCompletionHours: 0,
    });
    expect(res.data.engineerPerformance).toEqual([]);
  });
});
