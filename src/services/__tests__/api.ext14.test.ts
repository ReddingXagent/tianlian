/**
 * api ext14 — snake→camel adapter 空字段 fallback 分支覆盖
 * 集中测试所有 adapter 函数在 data 字段缺失时的默认值行为
 */
import {
  deviceApi,
  energyApi,
  userApi,
  reportApi,
  roleApi,
  permissionApi,
  alarmRuleApi,
  notificationRuleApi,
  sparePartApi,
  notificationTemplateApi,
  pricingApi,
  workOrderRecordApi,
} from '../api';

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

function makeEmptyResponse(data: unknown) {
  return { data: { code: 200, message: 'ok', data, timestamp: 0 } };
}

describe('adapter empty-field fallback coverage', () => {
  afterEach(() => jest.clearAllMocks());

  // ── deviceApi.getHealth ──
  describe('deviceApi.getHealth — empty fields', () => {
    it('returns defaults when all fields missing', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await deviceApi.getHealth(1);
      expect(res.data).toEqual({
        deviceId: 0, deviceCode: '', deviceName: '', deviceType: '',
        healthScore: 0, healthStatus: '', healthStatusDisplay: '',
        dimensionScores: {}, checkedAt: '', lastHealthCheck: null,
      });
    });

    it('returns defaults when data is null', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse(null));
      const res = await deviceApi.getHealth(1);
      expect(res.data.deviceId).toBe(0);
      expect(res.data.dimensionScores).toEqual({});
    });
  });

  // ── deviceApi.getConfig ──
  describe('deviceApi.getConfig — empty fields', () => {
    it('returns defaults when all fields missing', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await deviceApi.getConfig(1);
      expect(res.data).toEqual({
        deviceId: 0, voltageLimit: 0, currentLimit: 0, maxPower: 0,
        chargeMode: '', overloadProtection: false, timePeriods: [],
        createdAt: null, updatedAt: null,
      });
    });

    it('handles time_periods missing entries', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({ time_periods: [{}] }));
      const res = await deviceApi.getConfig(1);
      expect(res.data.timePeriods).toEqual([{ startTime: undefined, endTime: undefined, powerLimit: undefined }]);
    });
  });

  // ── energyApi.getSummary ──
  describe('energyApi.getSummary — empty fields', () => {
    it('returns defaults when all fields missing', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await energyApi.getSummary();
      expect(res.data).toEqual({
        period: 'month', days: 0,
        pvGeneration: 0, chargingAmount: 0, dischargeAmount: 0,
        pvRevenue: 0, chargingRevenue: 0, dischargeRevenue: 0, totalRevenue: 0,
        yoy: { pvGenerationYoy: 0, chargingAmountYoy: 0, dischargeAmountYoy: 0, totalRevenueYoy: 0 },
        priceInfo: { feedInTariff: 0, chargingPrice: 0, dischargePrice: 0 },
      });
    });

    it('handles null data', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse(null));
      const res = await energyApi.getSummary();
      expect(res.data.period).toBe('month');
      expect(res.data.totalRevenue).toBe(0);
    });
  });

  // ── energyApi.getTrend ──
  describe('energyApi.getTrend — empty fields', () => {
    it('maps trend items with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({ trend: [{ date: '2026-08-10' }, {}] }));
      const res = await energyApi.getTrend();
      expect(res.data).toHaveLength(2);
      expect(res.data[0].date).toBe('2026-08-10');
      expect(res.data[0].pvGeneration).toBe(0);
      expect(res.data[1].date).toBe('');
    });

    it('handles missing trend array', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await energyApi.getTrend();
      expect(res.data).toEqual([]);
    });
  });

  // ── userApi.getDetail ──
  describe('userApi.getDetail — empty fields', () => {
    it('returns defaults when all fields missing', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await userApi.getDetail(1);
      expect(res.data).toEqual({
        id: 0, username: '', realName: '', phone: null,
        role: '', level: '', teamId: null, teamName: null,
        status: '', lastLogin: '', createdAt: '', updatedAt: '',
      });
    });

    it('handles null data', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse(null));
      const res = await userApi.getDetail(1);
      expect(res.data.id).toBe(0);
      expect(res.data.phone).toBeNull();
    });
  });

  // ── reportApi.getSummary ──
  describe('reportApi.getSummary — empty fields', () => {
    it('returns defaults when all fields missing', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await reportApi.getSummary();
      expect(res.data.periodDays).toBe(30);
      expect(res.data.overview).toEqual({
        totalDevices: 0, onlineDevices: 0, offlineDevices: 0,
        faultDevices: 0, maintenanceDevices: 0, onlineRate: 0,
        totalStations: 0, totalWorkorders: 0, completedWorkorders: 0,
        completionRate: 0, totalAlarms: 0, activeAlarms: 0,
      });
      expect(res.data.stationHealth).toEqual({
        distribution: { normal: 0, warning: 0, critical: 0, offline: 0 },
        healthyRate: 0,
      });
      expect(res.data.teamPerformance).toEqual({
        engineers: [], totalEngineers: 0, topEngineers: [],
      });
    });
  });

  // ── reportApi.getDeviceReport ──
  describe('reportApi.getDeviceReport — empty fields', () => {
    it('returns defaults when all fields missing', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await reportApi.getDeviceReport();
      expect(res.data.periodDays).toBe(30);
      expect(res.data.typeDistribution).toEqual({});
      expect(res.data.stationDistribution).toEqual([]);
    });

    it('maps stationDistribution with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({
        station_distribution: [{ station_id: 1 }, {}],
      }));
      const res = await reportApi.getDeviceReport();
      expect(res.data.stationDistribution).toEqual([
        { stationId: 1, stationName: '', deviceCount: 0 },
        { stationId: 0, stationName: '', deviceCount: 0 },
      ]);
    });
  });

  // ── reportApi.getAlarmReport ──
  describe('reportApi.getAlarmReport — empty fields', () => {
    it('returns defaults when all fields missing', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await reportApi.getAlarmReport();
      expect(res.data.periodDays).toBe(30);
      expect(res.data.levelDistribution).toEqual({});
      expect(res.data.topFaultDevices).toEqual([]);
      expect(res.data.dailyTrend).toEqual([]);
    });

    it('maps topFaultDevices and dailyTrend with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({
        top_fault_devices: [{ device_id: 5 }, {}],
        daily_trend: [{ date: '2026-08-10' }],
      }));
      const res = await reportApi.getAlarmReport();
      expect(res.data.topFaultDevices).toEqual([
        { deviceId: 5, deviceName: '', alarmCount: 0 },
        { deviceId: 0, deviceName: '', alarmCount: 0 },
      ]);
      expect(res.data.dailyTrend[0].date).toBe('2026-08-10');
      expect(res.data.dailyTrend[0].count).toBe(0);
    });
  });

  // ── reportApi.getWorkOrderReport ──
  describe('reportApi.getWorkOrderReport — empty fields', () => {
    it('returns defaults when all fields missing', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await reportApi.getWorkOrderReport();
      expect(res.data.periodDays).toBe(30);
      expect(res.data.efficiency).toEqual({ avgResponseHours: 0, avgCompletionHours: 0 });
      expect(res.data.engineerPerformance).toEqual([]);
    });

    it('maps engineerPerformance with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({
        engineer_performance: [{ engineer_id: 1 }, {}],
      }));
      const res = await reportApi.getWorkOrderReport();
      expect(res.data.engineerPerformance).toEqual([
        { engineerId: 1, engineerName: '', completedCount: 0, avgCompletionHours: 0 },
        { engineerId: 0, engineerName: '', completedCount: 0, avgCompletionHours: 0 },
      ]);
    });
  });

  // ── roleApi.getList ──
  describe('roleApi.getList — empty fields', () => {
    it('maps roles with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({ items: [{ id: 1 }, {}] }));
      const res = await roleApi.getList();
      expect(res.data).toEqual([
        { id: 1, name: '', displayName: '', description: '', isSystem: false, permissions: [] },
        { id: 0, name: '', displayName: '', description: '', isSystem: false, permissions: [] },
      ]);
    });

    it('handles missing items array', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await roleApi.getList();
      expect(res.data).toEqual([]);
    });
  });

  // ── permissionApi.getList ──
  describe('permissionApi.getList — empty fields', () => {
    it('maps permissions with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({ items: [{ name: 'x' }, {}] }));
      const res = await permissionApi.getList();
      expect(res.data).toEqual([
        { name: 'x', resource: '', action: '', label: '', labelShort: '' },
        { name: '', resource: '', action: '', label: '', labelShort: '' },
      ]);
    });
  });

  // ── alarmRuleApi.getList ──
  describe('alarmRuleApi.getList — empty fields', () => {
    it('maps alarm rules with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({ items: [{ id: 1 }, {}] }));
      const res = await alarmRuleApi.getList({ page: 1, pageSize: 20 });
      expect(res.data.items).toHaveLength(2);
      expect(res.data.items[0]).toEqual({
        id: 1, name: '', deviceType: '', metric: '', condition: '',
        threshold: 0, level: 'warning', enabled: false,
        description: '', createdAt: '', updatedAt: '',
      });
      expect(res.data.items[1].id).toBe(0);
      expect(res.data.total).toBe(0);
    });

    it('handles null data', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse(null));
      const res = await alarmRuleApi.getList();
      expect(res.data.items).toEqual([]);
      expect(res.data.page).toBe(1);
    });
  });

  // ── notificationRuleApi.getList ──
  describe('notificationRuleApi.getList — empty fields', () => {
    it('maps notification rules with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse([{ id: 1 }, {}]));
      const res = await notificationRuleApi.getList();
      expect(res.data).toHaveLength(2);
      expect(res.data[0]).toEqual({
        id: 1, name: '', event: '', channels: [], recipients: [],
        enabled: false, template: '', createdAt: '', updatedAt: '',
      });
    });

    it('handles non-array data', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse(null));
      const res = await notificationRuleApi.getList();
      expect(res.data).toEqual([]);
    });
  });

  // ── sparePartApi.getList ──
  describe('sparePartApi.getList — empty fields', () => {
    it('maps spare parts with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({ items: [{ id: 1 }, {}] }));
      const res = await sparePartApi.getList({ page: 1, pageSize: 10 });
      expect(res.data.items[0]).toEqual({
        id: 1, partName: '', partModel: null, totalQuantity: 0,
        availableQuantity: 0, warehouse: '', createdAt: '',
      });
      expect(res.data.items[1].id).toBe(0);
    });

    it('handles null data', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse(null));
      const res = await sparePartApi.getList();
      expect(res.data.items).toEqual([]);
    });
  });

  // ── notificationTemplateApi.getList ──
  describe('notificationTemplateApi.getList — empty fields', () => {
    it('maps templates with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({ items: [{ id: 1 }, {}] }));
      const res = await notificationTemplateApi.getList({ page: 1, pageSize: 20 });
      expect(res.data.items[0]).toEqual({
        id: 1, name: '', channel: '', subject: '', body: '',
        variables: [], enabled: false, createdAt: '', updatedAt: '',
      });
    });
  });

  // ── pricingApi.getList ──
  describe('pricingApi.getList — empty fields', () => {
    it('maps pricing rules with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({ items: [{ id: 1 }, {}] }));
      const res = await pricingApi.getList({ page: 1, pageSize: 20 });
      expect(res.data.items[0]).toEqual({
        id: 1, name: '', periodType: '', startTime: '', endTime: '',
        energyPrice: undefined, servicePrice: undefined, powerLimit: undefined,
        enabled: false, createdAt: '', updatedAt: '',
      });
      expect(res.data.items[1].id).toBe(0);
    });

    it('handles null data', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse(null));
      const res = await pricingApi.getList();
      expect(res.data.items).toEqual([]);
    });
  });

  // ── pricingApi.getById ──
  describe('pricingApi.getById — empty fields', () => {
    it('maps detail with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({ id: 3 }));
      const res = await pricingApi.getById(3);
      expect(res.data?.id).toBe(3);
      expect(res.data?.name).toBe('');
      expect(res.data?.enabled).toBe(false);
    });
  });

  // ── workOrderRecordApi.getRecords ──
  describe('workOrderRecordApi.getRecords — empty fields', () => {
    it('maps records with missing fields', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({ items: [{ id: 1 }, {}] }));
      const res = await workOrderRecordApi.getRecords('WO-001');
      expect(res.data).toHaveLength(2);
      expect(res.data[0].id).toBe(1);
      expect(res.data[0].action).toBe('executing');
      expect(res.data[0].note).toBe('');
      expect(res.data[1].id).toBe(0);
    });

    it('handles missing items', async () => {
      api.get.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await workOrderRecordApi.getRecords('WO-001');
      expect(res.data).toEqual([]);
    });
  });

  // ── workOrderRecordApi.addRecord ──
  describe('workOrderRecordApi.addRecord — empty fields', () => {
    it('maps response with missing fields', async () => {
      api.post.mockResolvedValueOnce(makeEmptyResponse({}));
      const res = await workOrderRecordApi.addRecord('WO-001', { action: 'note', note: 'test' });
      expect(res.data.id).toBe(0);
      expect(res.data.action).toBe('note');
      expect(res.data.note).toBe('test');
      expect(res.data.orderId).toBe('WO-001');
    });
  });
});
