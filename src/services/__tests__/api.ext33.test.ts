import { vppApi } from '../api';

// Mock axios
jest.mock('axios', () => {
  const mockAxios: Record<string, any> = {
    create: jest.fn(() => mockAxios),
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return mockAxios;
});

// Mock SecureStore
jest.mock('expo-secure-store', () => ({
  getItem: jest.fn().mockResolvedValue('mock-token'),
  setItem: jest.fn(),
  deleteItem: jest.fn(),
}));

import axios from 'axios';
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('vppApi.getDispatchHistory — GET /vpp/dispatch/history', () => {
  beforeEach(() => jest.clearAllMocks());

  const mockHistoryItems = [
    {
      plan_id: 'ps_20260813020358_679a0c',
      mode: 'peak_shaving',
      trigger: '削峰(负荷787kW超阈值500kW, 需削减287kW)',
      stations_involved: ['ST-001', 'ST-002', 'ST-003', 'ST-004', 'ST-005'],
      total_dispatch_kw: 291.99,
      estimated_revenue: 21.9,
      estimated_cost: 0,
      net_profit: 21.9,
      commands_count: 3,
      created_at: '2026-08-13T02:03:58.375863',
      executed: false,
    },
    {
      plan_id: 'ps_20260813020351_cd1338',
      mode: 'peak_shaving',
      trigger: '削峰(负荷787kW超阈值500kW)',
      stations_involved: ['ST-001', 'ST-002'],
      total_dispatch_kw: 150.5,
      estimated_revenue: 11.3,
      estimated_cost: 5.0,
      net_profit: 6.3,
      commands_count: 2,
      created_at: '2026-08-13T02:03:51.286921',
      executed: true,
    },
  ];

  it('maps snake_case fields to camelCase correctly', async () => {
    const mockInstance = axios.create();
    mockInstance.get.mockResolvedValue({
      data: { success: true, data: mockHistoryItems },
    });

    const result = await vppApi.getDispatchHistory();
    expect(result.success).toBe(true);
    expect(result.data).toHaveLength(2);

    const first = result.data[0];
    expect(first.planId).toBe('ps_20260813020358_679a0c');
    expect(first.mode).toBe('peak_shaving');
    expect(first.trigger).toContain('削峰');
    expect(first.stationsInvolved).toEqual(['ST-001', 'ST-002', 'ST-003', 'ST-004', 'ST-005']);
    expect(first.totalDispatchKw).toBe(291.99);
    expect(first.estimatedRevenue).toBe(21.9);
    expect(first.estimatedCost).toBe(0);
    expect(first.netProfit).toBe(21.9);
    expect(first.commandsCount).toBe(3);
    expect(first.createdAt).toBe('2026-08-13T02:03:58.375863');
    expect(first.executed).toBe(false);
  });

  it('handles executed=true correctly', async () => {
    const mockInstance = axios.create();
    mockInstance.get.mockResolvedValue({
      data: { success: true, data: [mockHistoryItems[1]] },
    });

    const result = await vppApi.getDispatchHistory();
    expect(result.data[0].executed).toBe(true);
    expect(result.data[0].estimatedCost).toBe(5.0);
    expect(result.data[0].netProfit).toBe(6.3);
  });

  it('handles empty data array', async () => {
    const mockInstance = axios.create();
    mockInstance.get.mockResolvedValue({
      data: { success: true, data: [] },
    });

    const result = await vppApi.getDispatchHistory();
    expect(result.data).toEqual([]);
  });

  it('handles null data gracefully', async () => {
    const mockInstance = axios.create();
    mockInstance.get.mockResolvedValue({
      data: { success: true, data: null },
    });

    const result = await vppApi.getDispatchHistory();
    expect(result.data).toEqual([]);
  });

  it('applies defaults for missing fields', async () => {
    const mockInstance = axios.create();
    mockInstance.get.mockResolvedValue({
      data: { success: true, data: [{}] },
    });

    const result = await vppApi.getDispatchHistory();
    const item = result.data[0];
    expect(item.planId).toBe('');
    expect(item.mode).toBe('peak_shaving');
    expect(item.trigger).toBe('');
    expect(item.stationsInvolved).toEqual([]);
    expect(item.totalDispatchKw).toBe(0);
    expect(item.estimatedRevenue).toBe(0);
    expect(item.estimatedCost).toBe(0);
    expect(item.netProfit).toBe(0);
    expect(item.commandsCount).toBe(0);
    expect(item.createdAt).toBe('');
    expect(item.executed).toBe(false);
  });

  it('calls correct endpoint', async () => {
    const mockInstance = axios.create();
    mockInstance.get.mockResolvedValue({
      data: { success: true, data: [] },
    });

    await vppApi.getDispatchHistory();
    expect(mockInstance.get).toHaveBeenCalledWith('/vpp/dispatch/history');
  });
});
