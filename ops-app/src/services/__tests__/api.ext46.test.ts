import { healingExecutionApi } from '../api';

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

// ext46: healingExecutionApi.getStats (GET /healing/stats)
// HealingStats: total/statusBreakdown/successRate/averageDurationMs/autoApproveRate/pendingApprovals

describe('ext46 — healingExecutionApi.getStats (GET /healing/stats)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case → camelCase correctly', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          total: 42,
          status_breakdown: { success: 30, failed: 5, pending: 7 },
          success_rate: 0.714,
          average_duration_ms: 3500,
          auto_approve_rate: 0.5,
          pending_approvals: 3,
        },
        timestamp: 1700000000,
      },
    });

    const res = await healingExecutionApi.getStats();
    expect(res.data.total).toBe(42);
    expect(res.data.statusBreakdown).toEqual({ success: 30, failed: 5, pending: 7 });
    expect(res.data.successRate).toBe(0.714);
    expect(res.data.averageDurationMs).toBe(3500);
    expect(res.data.autoApproveRate).toBe(0.5);
    expect(res.data.pendingApprovals).toBe(3);
  });

  it('handles null data gracefully', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: null, timestamp: 1700000000 },
    });

    const res = await healingExecutionApi.getStats();
    expect(res.data.total).toBe(0);
    expect(res.data.statusBreakdown).toEqual({});
    expect(res.data.successRate).toBe(0);
    expect(res.data.averageDurationMs).toBe(0);
    expect(res.data.autoApproveRate).toBe(0);
    expect(res.data.pendingApprovals).toBe(0);
  });

  it('handles missing fields with defaults', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {}, timestamp: 1700000000 },
    });

    const res = await healingExecutionApi.getStats();
    expect(res.data.total).toBe(0);
    expect(res.data.statusBreakdown).toEqual({});
    expect(res.data.successRate).toBe(0);
    expect(res.data.averageDurationMs).toBe(0);
    expect(res.data.autoApproveRate).toBe(0);
    expect(res.data.pendingApprovals).toBe(0);
  });

  it('calls correct endpoint', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {}, timestamp: 1700000000 },
    });

    await healingExecutionApi.getStats();
    expect(mockAxios.get).toHaveBeenCalledWith('/healing/stats');
  });

  it('preserves top-level response fields', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { total: 10 },
        timestamp: 1700000123,
      },
    });

    const res = await healingExecutionApi.getStats();
    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
    expect(res.timestamp).toBe(1700000123);
  });
});
