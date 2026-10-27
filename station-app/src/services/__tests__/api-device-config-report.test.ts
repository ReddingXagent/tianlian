/**
 * Device Config + Report APIs (F756)
 * - deviceApi.getConfig() — GET /devices/{id}/config
 * - reportApi.getDevices() — GET /reports/devices
 * - reportApi.getAlarms() — GET /reports/alarms
 */
import { deviceApi, reportApi } from '../api';

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

// =====================
// deviceApi.getConfig()
// =====================
describe('deviceApi.getConfig() — GET /devices/{id}/config', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase DeviceConfig', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          device_id: 42,
          voltage_limit: 400,
          current_limit: 63,
          max_power: 25000,
          charge_mode: 'fast',
          overload_protection: true,
          time_periods: [
            { start: '00:00', end: '06:00', max_power: 7000 },
            { start: '22:00', end: '23:59', max_power: 7000 },
          ],
        },
      },
    });

    const res = await deviceApi.getConfig(42);

    expect(api.get).toHaveBeenCalledWith('/devices/42/config');
    expect(res.data.deviceId).toBe(42);
    expect(res.data.voltageLimit).toBe(400);
    expect(res.data.currentLimit).toBe(63);
    expect(res.data.maxPower).toBe(25000);
    expect(res.data.chargeMode).toBe('fast');
    expect(res.data.overloadProtection).toBe(true);
    expect(res.data.timePeriods).toHaveLength(2);
    expect(res.data.timePeriods![0]).toEqual({
      start: '00:00',
      end: '06:00',
      maxPower: 7000,
    });
  });

  it('handles missing time_periods gracefully', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          device_id: 5,
          voltage_limit: 220,
          current_limit: 32,
          max_power: 7000,
          charge_mode: 'standard',
          overload_protection: false,
        },
      },
    });

    const res = await deviceApi.getConfig(5);

    expect(res.data.timePeriods).toEqual([]);
    expect(res.data.overloadProtection).toBe(false);
  });

  it('handles already-camelCase response', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          deviceId: 10,
          voltageLimit: 380,
          currentLimit: 50,
          maxPower: 19000,
          chargeMode: 'slow',
          overloadProtection: true,
          timePeriods: [],
        },
      },
    });

    const res = await deviceApi.getConfig(10);

    expect(res.data.deviceId).toBe(10);
    expect(res.data.voltageLimit).toBe(380);
    expect(res.data.maxPower).toBe(19000);
  });
});

// =====================
// reportApi.getDevices()
// =====================
describe('reportApi.getDevices() — GET /reports/devices', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase DeviceReport', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          period_days: 30,
          overview: {
            total_devices: 50,
            online_devices: 31,
            offline_devices: 6,
            fault_devices: 7,
            maintenance_devices: 6,
          },
          type_distribution: { charger: 20, battery: 10, inverter: 15, sensor: 5 },
          status_distribution: { online: 31, offline: 6, fault: 7, maintenance: 6 },
          station_distribution: { 'Station A': 10, 'Station B': 40 },
        },
      },
    });

    const res = await reportApi.getDevices();

    expect(api.get).toHaveBeenCalledWith('/reports/devices');
    expect(res.data.periodDays).toBe(30);
    expect(res.data.totalDevices).toBe(50);
    expect(res.data.onlineDevices).toBe(31);
    expect(res.data.faultDevices).toBe(7);
    expect(res.data.typeDistribution.charger).toBe(20);
    expect(res.data.statusDistribution.online).toBe(31);
    expect(res.data.stationDistribution['Station A']).toBe(10);
  });

  it('handles empty/null fields gracefully', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {},
      },
    });

    const res = await reportApi.getDevices();

    expect(res.data.periodDays).toBe(30);
    expect(res.data.totalDevices).toBe(0);
    expect(res.data.typeDistribution).toEqual({});
  });
});

// =====================
// reportApi.getAlarms()
// =====================
describe('reportApi.getAlarms() — GET /reports/alarms', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase AlarmReport', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          period_days: 30,
          overview: {
            total_alarms: 200,
            active_alarms: 50,
            resolved_alarms: 150,
          },
          level_distribution: { critical: 10, high: 30, medium: 60, low: 100 },
          type_distribution: { overtemp: 50, comm_loss: 30, voltage: 120 },
          trend: [
            { date: '2026-08-01', count: 10 },
            { date: '2026-08-02', count: 15 },
          ],
          top_fault_devices: [
            { device_id: 1, device_name: 'Charger-001', alarm_count: 20 },
            { device_id: 2, device_name: 'Inverter-002', alarm_count: 15 },
          ],
        },
      },
    });

    const res = await reportApi.getAlarms();

    expect(api.get).toHaveBeenCalledWith('/reports/alarms');
    expect(res.data.periodDays).toBe(30);
    expect(res.data.totalAlarms).toBe(200);
    expect(res.data.activeAlarms).toBe(50);
    expect(res.data.resolvedAlarms).toBe(150);
    expect(res.data.levelDistribution.critical).toBe(10);
    expect(res.data.trend).toHaveLength(2);
    expect(res.data.trend[0]).toEqual({ date: '2026-08-01', count: 10 });
    expect(res.data.topFaultDevices[0]).toEqual({
      deviceId: 1,
      deviceName: 'Charger-001',
      alarmCount: 20,
    });
  });

  it('handles empty data gracefully', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {},
      },
    });

    const res = await reportApi.getAlarms();

    expect(res.data.periodDays).toBe(30);
    expect(res.data.totalAlarms).toBe(0);
    expect(res.data.trend).toEqual([]);
    expect(res.data.topFaultDevices).toEqual([]);
  });
});
