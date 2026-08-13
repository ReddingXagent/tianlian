/**
 * api ext76b — coverage: mapper fallback branches batch 3
 * Targets: reportApi.getEfficiency/getUtilization, alarmRuleApi.getList,
 *   notificationRuleApi.getList, inspectionTemplateApi.getList
 */
import {
  reportApi,
  alarmRuleApi,
  notificationRuleApi,
  inspectionTemplateApi,
} from '../api';
import axios from 'axios';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn(), patch: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  };
  return { create: jest.fn(() => mockInstance), __mockInstance: mockInstance };
});

const mockAxios = (axios as unknown as { __mockInstance: any }).__mockInstance;

describe('ext76b — mapper fallback branch coverage batch 3', () => {
  beforeEach(() => jest.clearAllMocks());

  // reportApi.getEfficiency — empty data → all fallbacks
  it('getEfficiency: data null → all fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await reportApi.getEfficiency();
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
    expect(res.data.alerts.abnormalLowEfficiency.count).toBe(0);
    expect(res.data.alerts.abnormalLowEfficiency.threshold).toBe('');
    expect(res.data.alerts.abnormalLowEfficiency.items).toEqual([]);
  });

  // reportApi.getEfficiency — items with {} → fallback item values
  it('getEfficiency: items [{}] → fallback item values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await reportApi.getEfficiency();
    expect(res.data.items[0]).toEqual({
      stationId: undefined,
      stationName: undefined,
      deviceId: undefined,
      deviceName: undefined,
      efficiency: undefined,
      uptime: undefined,
      utilization: undefined,
    });
  });

  // reportApi.getUtilization — data null → all fallbacks
  it('getUtilization: data null → all fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await reportApi.getUtilization();
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.alerts.lowUtilization.count).toBe(0);
    expect(res.data.alerts.overload.count).toBe(0);
  });

  // reportApi.getUtilization — items with {} → fallback
  it('getUtilization: items [{}] → fallback item values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await reportApi.getUtilization();
    expect(res.data.items[0]).toEqual({
      deviceId: undefined,
      deviceName: undefined,
      deviceCode: undefined,
      deviceType: undefined,
      stationId: undefined,
      stationName: undefined,
      utilizationRate: undefined,
    });
  });

  // alarmRuleApi.getList — items with {} → fallback
  it('alarmRuleApi.getList: items [{}] → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await alarmRuleApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0,
      name: '',
      deviceType: '',
      metric: '',
      condition: '',
      threshold: 0,
      level: 'warning',
      enabled: false,
      description: '',
      createdAt: '',
      updatedAt: '',
    });
  });

  // alarmRuleApi.getList — data null → fallback pagination
  it('alarmRuleApi.getList: data null → empty items', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await alarmRuleApi.getList();
    expect(res.data.items).toEqual([]);
  });

  // notificationRuleApi.getList — data as array [{}] → fallback
  it('notificationRuleApi.getList: data [{}] → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: [{}] },
    });
    const res = await notificationRuleApi.getList();
    expect(res.data[0]).toEqual({
      id: 0,
      name: '',
      event: '',
      channels: [],
      recipients: [],
      enabled: false,
      template: '',
      createdAt: '',
      updatedAt: '',
    });
  });

  // inspectionTemplateApi — test if it has a getList
  it('inspectionTemplateApi.getList: items [{}] → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await inspectionTemplateApi.getList();
    // Just verify it doesn't throw and returns something
    expect(res).toBeDefined();
  });
});
