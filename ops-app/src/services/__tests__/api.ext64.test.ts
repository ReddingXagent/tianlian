/**
 * api ext64 — reportApi.getUtilization (GET /reports/utilization)
 * Device utilization report with items + alerts (low_utilization/overload)
 */
import { reportApi } from '../api';
import axios from 'axios';
import type { UtilizationReport } from '../../types';

jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  };
  return {
    create: jest.fn(() => mockInstance),
    __mockInstance: mockInstance,
  };
});

jest.mock('expo-secure-store', () => ({
  getItemSecure: jest.fn().mockResolvedValue('mock-token'),
  setItemSecure: jest.fn(),
  deleteItemSecure: jest.fn(),
}));

const mockAxios = (axios as unknown as { __mockInstance: Record<string, jest.Mock> }).__mockInstance;

describe('ext64 — reportApi.getUtilization (GET /reports/utilization)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case response to camelCase correctly', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            { device_id: 1, device_name: 'TL-BAT-100AH-001', device_code: 'BATTERY202600001', device_type: 'battery_inverter', station_id: 15, station_name: '合肥光伏电站', utilization_rate: 0.0 },
            { device_id: 2, device_name: 'TL-INV-3000-002', device_code: 'INVERTER202600002', device_type: 'pv_inverter', station_id: 15, station_name: '合肥光伏电站', utilization_rate: 75.5 },
          ],
          total: 50,
          page: 1,
          page_size: 20,
          alerts: {
            low_utilization: {
              count: 40,
              threshold: '<30%',
              items: [
                { device_id: 1, device_name: 'TL-BAT-100AH-001', device_code: 'BATTERY202600001', device_type: 'battery_inverter', station_id: 15, station_name: '合肥光伏电站', utilization_rate: 0.0 },
              ],
            },
            overload: {
              count: 0,
              threshold: '>90%',
              items: [],
            },
          },
        },
        timestamp: 1786640502,
      },
    });

    const res = await reportApi.getUtilization();
    const data = res.data as UtilizationReport;

    // Top-level items mapping
    expect(data.items).toHaveLength(2);
    expect(data.items[0]).toEqual({
      deviceId: 1,
      deviceName: 'TL-BAT-100AH-001',
      deviceCode: 'BATTERY202600001',
      deviceType: 'battery_inverter',
      stationId: 15,
      stationName: '合肥光伏电站',
      utilizationRate: 0.0,
    });
    expect(data.items[1].utilizationRate).toBe(75.5);

    // Pagination
    expect(data.total).toBe(50);
    expect(data.page).toBe(1);
    expect(data.pageSize).toBe(20);

    // Alerts low_utilization
    expect(data.alerts.lowUtilization.count).toBe(40);
    expect(data.alerts.lowUtilization.threshold).toBe('<30%');
    expect(data.alerts.lowUtilization.items).toHaveLength(1);
    expect(data.alerts.lowUtilization.items[0].deviceId).toBe(1);

    // Alerts overload
    expect(data.alerts.overload.count).toBe(0);
    expect(data.alerts.overload.threshold).toBe('>90%');
    expect(data.alerts.overload.items).toHaveLength(0);
  });

  it('handles empty data gracefully', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 1, page_size: 20 },
        timestamp: 1786640502,
      },
    });

    const res = await reportApi.getUtilization();
    const data = res.data as UtilizationReport;

    expect(data.items).toEqual([]);
    expect(data.total).toBe(0);
    expect(data.alerts.lowUtilization.count).toBe(0);
    expect(data.alerts.lowUtilization.threshold).toBe('');
    expect(data.alerts.lowUtilization.items).toEqual([]);
    expect(data.alerts.overload.count).toBe(0);
    expect(data.alerts.overload.items).toEqual([]);
  });

  it('handles null/missing fields with undefined defaults', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [{ device_id: 1 }],
        },
        timestamp: 1786640502,
      },
    });

    const res = await reportApi.getUtilization();
    const data = res.data as UtilizationReport;

    expect(data.items[0]).toEqual({
      deviceId: 1,
      deviceName: undefined,
      deviceCode: undefined,
      deviceType: undefined,
      stationId: undefined,
      stationName: undefined,
      utilizationRate: undefined,
    });
  });

  it('calls correct endpoint with pagination params', async () => {
    mockAxios.get.mockResolvedValue({
      data: { code: 200, message: 'success', data: { items: [], total: 0, page: 2, page_size: 10 }, timestamp: 123 },
    });

    await reportApi.getUtilization({ page: 2, pageSize: 10 });

    expect(mockAxios.get).toHaveBeenCalledWith('/reports/utilization', {
      params: { page: 2, page_size: 10 },
    });
  });

  it('preserves top-level ApiResponse fields', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 1, page_size: 20 },
        timestamp: 1786640502,
      },
    });

    const res = await reportApi.getUtilization();

    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
    expect(res.timestamp).toBe(1786640502);
  });
});
