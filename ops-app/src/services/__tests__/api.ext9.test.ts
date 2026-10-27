/**
 * api ext9 — DeviceHealth API (GET /devices/{id}/health)
 * Target: snake_case → camelCase mapping for device health scores
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

const api = require('../api').default as jest.Mocked<{ get: jest.Mock }>;

describe('deviceApi.getHealth() — GET /devices/{id}/health', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase DeviceHealth', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          device_id: 1,
          device_code: 'BATTERY202600001',
          device_name: 'TL-BAT-100AH-001',
          device_type: 'battery_inverter',
          health_score: 91.72,
          health_status: 'healthy',
          health_status_display: '健康',
          dimension_scores: { temperature: 95, voltage: 88 },
          checked_at: '2026-08-10T13:36:24.318126',
          last_health_check: null,
        },
        timestamp: 1786340184,
      },
    });

    const res = await deviceApi.getHealth(1);
    expect(api.get).toHaveBeenCalledWith('/devices/1/health');
    expect(res.data.deviceId).toBe(1);
    expect(res.data.deviceCode).toBe('BATTERY202600001');
    expect(res.data.deviceName).toBe('TL-BAT-100AH-001');
    expect(res.data.deviceType).toBe('battery_inverter');
    expect(res.data.healthScore).toBe(91.72);
    expect(res.data.healthStatus).toBe('healthy');
    expect(res.data.healthStatusDisplay).toBe('健康');
    expect(res.data.dimensionScores).toEqual({ temperature: 95, voltage: 88 });
    expect(res.data.checkedAt).toBe('2026-08-10T13:36:24.318126');
    expect(res.data.lastHealthCheck).toBeNull();
  });

  it('handles missing dimension_scores gracefully', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          device_id: 2,
          device_code: 'EVSE002',
          device_name: 'Charger-02',
          device_type: 'charger',
          health_score: 75.0,
          health_status: 'warning',
          health_status_display: '警告',
          checked_at: '2026-08-10T12:00:00',
        },
      },
    });

    const res = await deviceApi.getHealth(2);
    expect(res.data.deviceId).toBe(2);
    expect(res.data.healthScore).toBe(75.0);
    expect(res.data.healthStatus).toBe('warning');
    expect(res.data.dimensionScores).toEqual({});
    expect(res.data.lastHealthCheck).toBeNull();
  });

  it('handles minimal data with safe defaults', async () => {
    api.get.mockResolvedValue({
      data: { code: 200, message: 'ok', data: { device_id: 5 } },
    });

    const res = await deviceApi.getHealth(5);
    expect(res.data.deviceId).toBe(5);
    expect(res.data.deviceCode).toBe('');
    expect(res.data.deviceName).toBe('');
    expect(res.data.healthScore).toBe(0);
    expect(res.data.healthStatus).toBe('');
    expect(res.data.dimensionScores).toEqual({});
  });

  it('handles last_health_check with actual date', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: {
          device_id: 3,
          device_code: 'INV003',
          health_score: 100,
          health_status: 'healthy',
          health_status_display: '健康',
          checked_at: '2026-08-10T14:00:00',
          last_health_check: '2026-08-09T10:00:00',
        },
      },
    });

    const res = await deviceApi.getHealth(3);
    expect(res.data.lastHealthCheck).toBe('2026-08-09T10:00:00');
    expect(res.data.healthScore).toBe(100);
  });
});
