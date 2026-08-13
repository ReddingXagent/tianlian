/**
 * API 映射兜底分支补充测试
 * 覆盖 getHealth/getConfig/energyApi/reportApi 中 camelCase 回退与默认值分支:
 * - getHealth: camelCase 字段 + 全缺失默认值
 * - getConfig: 全缺失默认值 + timePeriods 条目缺省字段
 * - energyApi.getSummary: 响应无 data 字段早返回分支
 * - reportApi.getDevices/getAlarms: 响应无 data 字段 (?? {}) + topFaultDevices camelCase/缺省
 */
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, { deviceApi, energyApi, reportApi } from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);

beforeEach(() => {
  jest.clearAllMocks();
  mockAxios.reset();
  (SecureStore.getItemAsync as jest.Mock).mockResolvedValue('test-token');
});

describe('deviceApi.getHealth fallback branches', () => {
  it('maps already-camelCase health fields', async () => {
    mockAxios.onGet('/devices/7/health').reply(200, {
      code: 200,
      message: 'success',
      data: {
        deviceId: 7,
        healthScore: 55,
        healthStatus: 'warning',
        dimensionScores: { thermal: 60 },
        checkedAt: '2026-08-12T00:00:00Z',
      },
    });
    const resp = await deviceApi.getHealth(7);
    expect(resp.data.deviceId).toBe(7);
    expect(resp.data.healthScore).toBe(55);
    expect(resp.data.healthStatus).toBe('warning');
    expect(resp.data.dimensionScores).toEqual({ thermal: 60 });
    expect(resp.data.checkedAt).toBe('2026-08-12T00:00:00Z');
  });

  it('falls back to defaults when all health fields are missing', async () => {
    mockAxios.onGet('/devices/8/health').reply(200, {
      code: 200,
      message: 'success',
      data: {},
    });
    const resp = await deviceApi.getHealth(8);
    expect(resp.data.deviceId).toBe(8); // 回退到路径参数 deviceId
    expect(resp.data.healthScore).toBe(0);
    expect(resp.data.healthStatus).toBe('good');
    expect(resp.data.dimensionScores).toEqual({});
    expect(typeof resp.data.checkedAt).toBe('string'); // new Date().toISOString()
  });
});

describe('deviceApi.getConfig fallback branches', () => {
  it('falls back to defaults when config data is empty', async () => {
    mockAxios.onGet('/devices/9/config').reply(200, {
      code: 200,
      message: 'success',
      data: {},
    });
    const resp = await deviceApi.getConfig(9);
    expect(resp.data.deviceId).toBe(9);
    expect(resp.data.voltageLimit).toBe(0);
    expect(resp.data.currentLimit).toBe(0);
    expect(resp.data.maxPower).toBe(0);
    expect(resp.data.chargeMode).toBe('standard');
    expect(resp.data.overloadProtection).toBe(false);
    expect(resp.data.timePeriods).toEqual([]);
  });

  it('fills timePeriod entry defaults and honors camelCase maxPower', async () => {
    mockAxios.onGet('/devices/10/config').reply(200, {
      code: 200,
      message: 'success',
      data: {
        device_id: 10,
        time_periods: [
          {}, // start/end/max_power 全缺失 → '' / '' / 0
          { start: '01:00', end: '02:00', maxPower: 7 }, // camelCase maxPower 分支
        ],
      },
    });
    const resp = await deviceApi.getConfig(10);
    expect(resp.data.timePeriods).toEqual([
      { start: '', end: '', maxPower: 0 },
      { start: '01:00', end: '02:00', maxPower: 7 },
    ]);
  });
});

describe('energyApi.getSummary missing-data branch', () => {
  it('returns raw response when data field is absent', async () => {
    mockAxios.onGet('/energy/summary').reply(200, {
      code: 200,
      message: 'success',
    });
    const resp = await energyApi.getSummary();
    expect(resp.code).toBe(200);
    expect(resp.data).toBeUndefined();
  });
});

describe('reportApi missing-data branches', () => {
  it('getDevices defaults everything when data field is absent', async () => {
    mockAxios.onGet('/reports/devices').reply(200, {
      code: 200,
      message: 'success',
    });
    const resp = await reportApi.getDevices();
    expect(resp.data.periodDays).toBe(30);
    expect(resp.data.totalDevices).toBe(0);
    expect(resp.data.onlineDevices).toBe(0);
    expect(resp.data.offlineDevices).toBe(0);
    expect(resp.data.faultDevices).toBe(0);
    expect(resp.data.maintenanceDevices).toBe(0);
    expect(resp.data.typeDistribution).toEqual({});
    expect(resp.data.statusDistribution).toEqual({});
    expect(resp.data.stationDistribution).toEqual({});
  });

  it('getAlarms defaults everything when data field is absent', async () => {
    mockAxios.onGet('/reports/alarms').reply(200, {
      code: 200,
      message: 'success',
    });
    const resp = await reportApi.getAlarms();
    expect(resp.data.periodDays).toBe(30);
    expect(resp.data.totalAlarms).toBe(0);
    expect(resp.data.activeAlarms).toBe(0);
    expect(resp.data.resolvedAlarms).toBe(0);
    expect(resp.data.trend).toEqual([]);
    expect(resp.data.topFaultDevices).toEqual([]);
  });

  it('getAlarms fills trend/topFault entry defaults and camelCase fallbacks', async () => {
    mockAxios.onGet('/reports/alarms').reply(200, {
      code: 200,
      message: 'success',
      data: {
        period_days: 30,
        overview: { total_alarms: 3, active_alarms: 1, resolved_alarms: 2 },
        trend: [
          {}, // date/count 缺失 → '' / 0
          { date: '2026-08-01', count: 5 },
        ],
        top_fault_devices: [
          {}, // 全缺失 → 0 / '' / 0
          { deviceId: 7, deviceName: 'CP-X', alarmCount: 4 }, // camelCase 分支
        ],
      },
    });
    const resp = await reportApi.getAlarms();
    expect(resp.data.trend).toEqual([
      { date: '', count: 0 },
      { date: '2026-08-01', count: 5 },
    ]);
    expect(resp.data.topFaultDevices).toEqual([
      { deviceId: 0, deviceName: '', alarmCount: 0 },
      { deviceId: 7, deviceName: 'CP-X', alarmCount: 4 },
    ]);
  });
});
