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

describe('vppApi.getResources', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should map snake_case to camelCase correctly', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200, message: 'success',
        data: [
          {
            resource_id: 'ST-001-PV',
            resource_type: 'pv',
            station_id: 'ST-001',
            rated_power_kw: 200,
            current_power_kw: 65.3,
            available_power_kw: 65.3,
            soc: null,
            efficiency: 0.95,
            priority: 5,
            cost_per_kwh: 0.0,
          },
          {
            resource_id: 'ST-001-BAT',
            resource_type: 'battery',
            station_id: 'ST-001',
            rated_power_kw: 250.0,
            current_power_kw: 0,
            available_power_kw: 80.4,
            soc: 0.402,
            efficiency: 0.95,
            priority: 2,
            cost_per_kwh: 0.0,
          },
        ],
      },
    });

    const res = await vppApi.getResources();
    expect(res.code).toBe(200);
    expect(res.data).toHaveLength(2);

    const pv = res.data[0];
    expect(pv.resourceId).toBe('ST-001-PV');
    expect(pv.resourceType).toBe('pv');
    expect(pv.stationId).toBe('ST-001');
    expect(pv.ratedPowerKw).toBe(200);
    expect(pv.currentPowerKw).toBe(65.3);
    expect(pv.availablePowerKw).toBe(65.3);
    expect(pv.soc).toBeNull();
    expect(pv.efficiency).toBe(0.95);
    expect(pv.priority).toBe(5);
    expect(pv.costPerKwh).toBe(0);

    const bat = res.data[1];
    expect(bat.resourceType).toBe('battery');
    expect(bat.soc).toBe(0.402);
  });

  it('should handle empty data array', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: [] },
    });
    const res = await vppApi.getResources();
    expect(res.data).toEqual([]);
  });

  it('should handle null data with empty fallback', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: null },
    });
    const res = await vppApi.getResources();
    expect(res.data).toEqual([]);
  });

  it('should provide defaults for missing fields', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200, message: 'success',
        data: [{}],
      },
    });
    const res = await vppApi.getResources();
    const r = res.data[0];
    expect(r.resourceId).toBe('');
    expect(r.resourceType).toBe('pv');
    expect(r.ratedPowerKw).toBe(0);
    expect(r.efficiency).toBe(0);
    expect(r.soc).toBeNull();
  });

  it('should call correct endpoint', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: [] },
    });
    await vppApi.getResources();
    expect(mockedAxios.get).toHaveBeenCalledWith('/vpp/resources');
  });
});

describe('vppApi.dispatch', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should map dispatch plan snake_case to camelCase', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200, message: 'success',
        data: {
          plan_id: 'ps_20260813020358_679a0c',
          mode: 'peak_shaving',
          trigger: '削峰(负荷787kW超阈值500kW)',
          stations_involved: ['ST-001', 'ST-002', 'ST-003'],
          total_dispatch_kw: 291.99,
          estimated_revenue: 21.9,
          estimated_cost: 0,
          net_profit: 21.9,
          commands: [
            {
              resource_id: 'ST-003-BAT',
              station_id: 'ST-003',
              resource_type: 'battery',
              target_power_kw: 129.4,
              duration_min: 15,
              priority: 2,
              estimated_revenue: 9.71,
              estimated_cost: 0,
              dispatch_mode: 'peak_shaving',
            },
          ],
          created_at: '2026-08-13T02:03:58.375863',
        },
      },
    });

    const res = await vppApi.dispatch();
    expect(res.code).toBe(200);

    const plan = res.data;
    expect(plan.planId).toBe('ps_20260813020358_679a0c');
    expect(plan.mode).toBe('peak_shaving');
    expect(plan.trigger).toContain('削峰');
    expect(plan.stationsInvolved).toEqual(['ST-001', 'ST-002', 'ST-003']);
    expect(plan.totalDispatchKw).toBe(291.99);
    expect(plan.estimatedRevenue).toBe(21.9);
    expect(plan.estimatedCost).toBe(0);
    expect(plan.netProfit).toBe(21.9);
    expect(plan.createdAt).toBe('2026-08-13T02:03:58.375863');

    const cmd = plan.commands[0];
    expect(cmd.resourceId).toBe('ST-003-BAT');
    expect(cmd.stationId).toBe('ST-003');
    expect(cmd.resourceType).toBe('battery');
    expect(cmd.targetPowerKw).toBe(129.4);
    expect(cmd.durationMin).toBe(15);
    expect(cmd.priority).toBe(2);
    expect(cmd.estimatedRevenue).toBe(9.71);
    expect(cmd.dispatchMode).toBe('peak_shaving');
  });

  it('should handle empty commands array', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200, message: 'success',
        data: {
          plan_id: 'ps_empty',
          mode: 'valley_filling',
          trigger: '',
          stations_involved: [],
          total_dispatch_kw: 0,
          estimated_revenue: 0,
          estimated_cost: 0,
          net_profit: 0,
          commands: [],
          created_at: '',
        },
      },
    });
    const res = await vppApi.dispatch();
    expect(res.data.commands).toEqual([]);
    expect(res.data.mode).toBe('valley_filling');
  });

  it('should handle null data with defaults', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: null },
    });
    const res = await vppApi.dispatch();
    expect(res.data.planId).toBe('');
    expect(res.data.mode).toBe('peak_shaving');
    expect(res.data.stationsInvolved).toEqual([]);
    expect(res.data.commands).toEqual([]);
  });

  it('should provide defaults for missing command fields', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200, message: 'success',
        data: {
          commands: [{}],
        },
      },
    });
    const res = await vppApi.dispatch();
    const cmd = res.data.commands[0];
    expect(cmd.resourceId).toBe('');
    expect(cmd.stationId).toBe('');
    expect(cmd.resourceType).toBe('battery');
    expect(cmd.targetPowerKw).toBe(0);
    expect(cmd.dispatchMode).toBe('peak_shaving');
  });

  it('should call POST /vpp/dispatch with empty body when no args', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { commands: [] } },
    });
    await vppApi.dispatch();
    expect(mockedAxios.post).toHaveBeenCalledWith('/vpp/dispatch', {});
  });

  it('should pass through body when provided', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { commands: [] } },
    });
    await vppApi.dispatch({ station_id: 1 });
    expect(mockedAxios.post).toHaveBeenCalledWith('/vpp/dispatch', { station_id: 1 });
  });

  it('should handle all resource types in commands', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200, message: 'success',
        data: {
          commands: [
            { resource_type: 'pv', dispatch_mode: 'peak_shaving' },
            { resource_type: 'battery', dispatch_mode: 'valley_filling' },
            { resource_type: 'ev', dispatch_mode: 'frequency_regulation' },
            { resource_type: 'load', dispatch_mode: 'demand_response' },
          ],
        },
      },
    });
    const res = await vppApi.dispatch();
    expect(res.data.commands[0].resourceType).toBe('pv');
    expect(res.data.commands[1].resourceType).toBe('battery');
    expect(res.data.commands[2].resourceType).toBe('ev');
    expect(res.data.commands[3].resourceType).toBe('load');
    expect(res.data.commands[0].dispatchMode).toBe('peak_shaving');
    expect(res.data.commands[3].dispatchMode).toBe('demand_response');
  });
});
