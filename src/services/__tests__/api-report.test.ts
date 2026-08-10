/**
 * Report API — GET /reports/summary (F754)
 * snake_case → camelCase mapping for station-app
 */
import { reportApi } from '../api';

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


describe('reportApi.getSummary() — GET /reports/summary', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase ReportSummary', async () => {
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
            online_rate: 62.0,
            total_stations: 17,
            total_workorders: 100,
            completed_workorders: 80,
            completion_rate: 80.0,
            total_alarms: 4536,
            active_alarms: 4536,
          },
          station_health: {
            distribution: {
              normal: 1,
              warning: 5,
              critical: 10,
              offline: 1,
            },
            healthy_rate: 5.9,
          },
        },
        timestamp: 1786359969,
      },
    });

    const res = await reportApi.getSummary();

    expect(api.get).toHaveBeenCalledWith('/reports/summary');
    expect(res.code).toBe(200);
    expect(res.data.periodDays).toBe(30);

    const ov = res.data.overview;
    expect(ov.totalDevices).toBe(50);
    expect(ov.onlineDevices).toBe(31);
    expect(ov.offlineDevices).toBe(6);
    expect(ov.faultDevices).toBe(7);
    expect(ov.maintenanceDevices).toBe(6);
    expect(ov.onlineRate).toBe(62.0);
    expect(ov.totalStations).toBe(17);
    expect(ov.totalWorkorders).toBe(100);
    expect(ov.completedWorkorders).toBe(80);
    expect(ov.completionRate).toBe(80.0);
    expect(ov.totalAlarms).toBe(4536);
    expect(ov.activeAlarms).toBe(4536);

    const sh = res.data.stationHealth;
    expect(sh.normal).toBe(1);
    expect(sh.warning).toBe(5);
    expect(sh.critical).toBe(10);
    expect(sh.offline).toBe(1);
    expect(sh.healthyRate).toBe(5.9);
  });

  it('handles missing fields with fallback defaults', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        data: {},
      },
    });

    const res = await reportApi.getSummary();

    expect(res.data.periodDays).toBe(30);
    expect(res.data.overview.totalDevices).toBe(0);
    expect(res.data.overview.onlineRate).toBe(0);
    expect(res.data.overview.totalStations).toBe(0);
    expect(res.data.stationHealth.normal).toBe(0);
    expect(res.data.stationHealth.healthyRate).toBe(0);
  });

  it('handles null data gracefully', async () => {
    api.get.mockResolvedValue({
      data: { code: 200, data: null },
    });

    const res = await reportApi.getSummary();

    expect(res.data.periodDays).toBe(30);
    expect(res.data.overview.totalDevices).toBe(0);
    expect(res.data.stationHealth.normal).toBe(0);
  });

  it('handles partial overview/station_health', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        data: {
          period_days: 7,
          overview: { total_devices: 10 },
          station_health: { healthy_rate: 50.0 },
        },
      },
    });

    const res = await reportApi.getSummary();

    expect(res.data.periodDays).toBe(7);
    expect(res.data.overview.totalDevices).toBe(10);
    expect(res.data.overview.onlineDevices).toBe(0);
    expect(res.data.stationHealth.healthyRate).toBe(50.0);
    expect(res.data.stationHealth.normal).toBe(0);
  });
});
