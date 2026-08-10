/**
 * api ext10 — Report/Role/Permission API (F748)
 * GET /reports/devices, /reports/alarms, /roles, /permissions
 */
import { reportApi, roleApi, permissionApi } from '../api';

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

describe('reportApi.getDeviceReport() — GET /reports/devices', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase DeviceReport', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          period_days: 30,
          total_devices: 50,
          type_distribution: { battery_inverter: 9, pv_inverter: 11 },
          status_distribution: { online: 31, offline: 6 },
          station_distribution: [
            { station_id: 1, station_name: '北京光伏站', device_count: 5 },
            { station_id: 2, station_name: '上海光伏站', device_count: 4 },
          ],
        },
        timestamp: 1786341633,
      },
    });

    const res = await reportApi.getDeviceReport();
    expect(res.data.periodDays).toBe(30);
    expect(res.data.totalDevices).toBe(50);
    expect(res.data.typeDistribution).toEqual({ battery_inverter: 9, pv_inverter: 11 });
    expect(res.data.statusDistribution).toEqual({ online: 31, offline: 6 });
    expect(res.data.stationDistribution).toHaveLength(2);
    expect(res.data.stationDistribution[0]).toEqual({
      stationId: 1,
      stationName: '北京光伏站',
      deviceCount: 5,
    });
  });

  it('handles empty/missing fields with defaults', async () => {
    api.get.mockResolvedValue({ data: { code: 200, data: {} } });
    const res = await reportApi.getDeviceReport();
    expect(res.data.periodDays).toBe(30);
    expect(res.data.totalDevices).toBe(0);
    expect(res.data.typeDistribution).toEqual({});
    expect(res.data.stationDistribution).toEqual([]);
  });
});

describe('reportApi.getAlarmReport() — GET /reports/alarms', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase AlarmReport', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        data: {
          period_days: 30,
          total_alarms: 100,
          level_distribution: { warning: 90, critical: 10 },
          type_distribution: { high_temperature: 60, device_warning: 40 },
          status_distribution: { active: 100 },
          resolved_rate: 0.0,
          active_alarms: 100,
          top_fault_devices: [
            { device_id: 1, device_name: 'TL-BAT-001', alarm_count: 50 },
          ],
          daily_trend: [
            { date: '2026-08-01', count: 5 },
            { date: '2026-08-02', count: 10 },
          ],
        },
      },
    });

    const res = await reportApi.getAlarmReport();
    expect(res.data.periodDays).toBe(30);
    expect(res.data.totalAlarms).toBe(100);
    expect(res.data.levelDistribution).toEqual({ warning: 90, critical: 10 });
    expect(res.data.resolvedRate).toBe(0.0);
    expect(res.data.activeAlarms).toBe(100);
    expect(res.data.topFaultDevices[0]).toEqual({
      deviceId: 1,
      deviceName: 'TL-BAT-001',
      alarmCount: 50,
    });
    expect(res.data.dailyTrend).toHaveLength(2);
    expect(res.data.dailyTrend[1]).toEqual({ date: '2026-08-02', count: 10 });
  });

  it('handles empty/missing fields with defaults', async () => {
    api.get.mockResolvedValue({ data: { code: 200, data: {} } });
    const res = await reportApi.getAlarmReport();
    expect(res.data.totalAlarms).toBe(0);
    expect(res.data.topFaultDevices).toEqual([]);
    expect(res.data.dailyTrend).toEqual([]);
  });
});

describe('roleApi.getList() — GET /roles', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase Role[]', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        data: {
          items: [
            {
              id: 1,
              name: 'super_admin',
              display_name: '超级管理员',
              description: '全部权限',
              is_system: true,
              permissions: ['device:view', 'device:edit'],
            },
            {
              id: 2,
              name: 'engineer',
              display_name: '工程师',
              description: '运维工程师',
              is_system: false,
              permissions: ['device:view'],
            },
          ],
        },
      },
    });

    const res = await roleApi.getList();
    expect(res.data).toHaveLength(2);
    expect(res.data[0]).toEqual({
      id: 1,
      name: 'super_admin',
      displayName: '超级管理员',
      description: '全部权限',
      isSystem: true,
      permissions: ['device:view', 'device:edit'],
    });
    expect(res.data[1].isSystem).toBe(false);
  });

  it('handles empty items', async () => {
    api.get.mockResolvedValue({ data: { code: 200, data: {} } });
    const res = await roleApi.getList();
    expect(res.data).toEqual([]);
  });
});

describe('permissionApi.getList() — GET /permissions', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase Permission[]', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        data: {
          items: [
            {
              name: 'device:control',
              resource: 'device',
              action: 'control',
              label: '设备管理 - 控制',
              label_short: '控制',
            },
            {
              name: 'station:view',
              resource: 'station',
              action: 'view',
              label: '站点管理 - 查看',
              label_short: '查看',
            },
          ],
        },
      },
    });

    const res = await permissionApi.getList();
    expect(res.data).toHaveLength(2);
    expect(res.data[0]).toEqual({
      name: 'device:control',
      resource: 'device',
      action: 'control',
      label: '设备管理 - 控制',
      labelShort: '控制',
    });
  });

  it('handles empty items', async () => {
    api.get.mockResolvedValue({ data: { code: 200, data: {} } });
    const res = await permissionApi.getList();
    expect(res.data).toEqual([]);
  });
});
