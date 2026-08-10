/**
 * api ext10 — ChargerConfig API (GET /devices/{id}/config)
 * Target: snake_case → camelCase mapping for charging pile config
 */
import { deviceApi } from '../api';

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

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require('../api').default as jest.Mocked<{ get: jest.Mock }>;

describe('deviceApi.getConfig() — GET /devices/{id}/config', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase ChargerConfig', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          device_id: 6,
          voltage_limit: 420.0,
          current_limit: 60.0,
          max_power: 60.0,
          charge_mode: 'smart',
          overload_protection: true,
          time_periods: [],
          created_at: null,
          updated_at: null,
        },
      },
    });

    const res = await deviceApi.getConfig(6);
    expect(api.get).toHaveBeenCalledWith('/devices/6/config');
    expect(res.data).toEqual({
      deviceId: 6,
      voltageLimit: 420.0,
      currentLimit: 60.0,
      maxPower: 60.0,
      chargeMode: 'smart',
      overloadProtection: true,
      timePeriods: [],
      createdAt: null,
      updatedAt: null,
    });
  });

  it('handles time_periods with entries', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          device_id: 8,
          voltage_limit: 750.0,
          current_limit: 200.0,
          max_power: 240.0,
          charge_mode: 'timer',
          overload_protection: false,
          time_periods: [
            { start_time: '22:00', end_time: '06:00', power_limit: 100.0 },
          ],
          created_at: '2026-01-15T08:00:00Z',
          updated_at: '2026-08-01T12:00:00Z',
        },
      },
    });

    const res = await deviceApi.getConfig(8);
    expect(res.data.chargeMode).toBe('timer');
    expect(res.data.overloadProtection).toBe(false);
    expect(res.data.maxPower).toBe(240.0);
    expect(res.data.createdAt).toBe('2026-01-15T08:00:00Z');
    expect(res.data.updatedAt).toBe('2026-08-01T12:00:00Z');
  });

  it('defaults on missing fields', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {},
      },
    });

    const res = await deviceApi.getConfig(1);
    expect(res.data).toEqual({
      deviceId: 0,
      voltageLimit: 0,
      currentLimit: 0,
      maxPower: 0,
      chargeMode: '',
      overloadProtection: false,
      timePeriods: [],
      createdAt: null,
      updatedAt: null,
    });
  });

  it('handles 400 for non-charger devices', async () => {
    api.get.mockRejectedValue({
      response: {
        status: 400,
        data: { code: 400, message: '仅支持充电桩设备配置', data: null },
      },
    });

    await expect(deviceApi.getConfig(1)).rejects.toMatchObject({
      response: { status: 400 },
    });
  });
});
