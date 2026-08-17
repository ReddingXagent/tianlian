/**
 * api ext8 — AuthMe + UserDetail + ReportSummary API
 * Target: /auth/me (200), /users/{id} (200), /reports/summary (200)
 */
import { authApi, userApi, reportApi } from '../api';

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

describe('authApi.getProfile() — GET /auth/me', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase AuthMe with permissions', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          username: 'tl',
          real_name: '管理员',
          role: 'super_admin',
          permissions: ['station:view', 'device:edit', 'alarm:process'],
          team_type: null,
          team_id: null,
        },
        timestamp: 1786339856,
      },
    });

    const res = await authApi.getProfile();
    expect(api.get).toHaveBeenCalledWith('/auth/me');
    expect(res.data.id).toBe(1);
    expect(res.data.username).toBe('tl');
    expect(res.data.realName).toBe('管理员');
    expect(res.data.role).toBe('super_admin');
    expect(res.data.permissions).toEqual(['station:view', 'device:edit', 'alarm:process']);
    expect(res.data.teamType).toBeNull();
    expect(res.data.teamId).toBeNull();
  });

  it('handles missing permissions gracefully', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { id: 2, username: 'op1', real_name: '操作员', role: 'operator' },
      },
    });

    const res = await authApi.getProfile();
    expect(res.data.permissions).toEqual([]);
    expect(res.data.realName).toBe('操作员');
  });

  it('handles null team fields', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 3,
          username: 'eng1',
          real_name: '工程师',
          role: 'engineer',
          permissions: [],
          team_type: 'regional',
          team_id: 5,
        },
      },
    });

    const res = await authApi.getProfile();
    expect(res.data.teamType).toBe('regional');
    expect(res.data.teamId).toBe(5);
  });
});

describe('userApi.getDetail() — GET /users/{id}', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase UserDetail', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          username: 'tl',
          real_name: '管理员',
          phone: '13800000000',
          role: 'super_admin',
          level: 'senior',
          team_id: null,
          team_name: null,
          status: 'active',
          last_login: '2026-08-10T10:59:31.729307+08:00',
          created_at: '2026-07-10T12:14:12.470910+08:00',
          updated_at: '2026-08-10T10:59:31.404730+08:00',
          permissions: [],
        },
        timestamp: 1786339868,
      },
    });

    const res = await userApi.getDetail(1);
    expect(api.get).toHaveBeenCalledWith('/users/1');
    expect(res.data.id).toBe(1);
    expect(res.data.username).toBe('tl');
    expect(res.data.realName).toBe('管理员');
    expect(res.data.phone).toBe('13800000000');
    expect(res.data.role).toBe('super_admin');
    expect(res.data.level).toBe('senior');
    expect(res.data.status).toBe('active');
    expect(res.data.lastLogin).toBe('2026-08-10T10:59:31.729307+08:00');
  });

  it('handles null phone and team fields', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 23,
          username: 'mobile_operator',
          real_name: '移动端联调-运维',
          phone: null,
          role: 'operator',
          level: 'junior',
          team_id: null,
          team_name: null,
          status: 'active',
          last_login: '2026-07-31T07:56:19.131987+08:00',
          created_at: '2026-07-26T22:08:45.694063+08:00',
          updated_at: '2026-07-31T07:56:19.131987+08:00',
        },
      },
    });

    const res = await userApi.getDetail(23);
    expect(res.data.phone).toBeNull();
    expect(res.data.teamId).toBeNull();
    expect(res.data.teamName).toBeNull();
    expect(res.data.level).toBe('junior');
  });

  it('defaults missing fields to safe values', async () => {
    api.get.mockResolvedValue({
      data: { code: 200, message: 'ok', data: { id: 5 } },
    });

    const res = await userApi.getDetail(5);
    expect(res.data.id).toBe(5);
    expect(res.data.username).toBe('');
    expect(res.data.realName).toBe('');
    expect(res.data.role).toBe('');
    expect(res.data.status).toBe('');
    expect(res.data.lastLogin).toBe('');
  });
});

describe('reportApi.getSummary() — GET /reports/summary', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps nested snake_case → camelCase ReportSummary', async () => {
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
            total_workorders: 10,
            completed_workorders: 5,
            completion_rate: 50.0,
            total_alarms: 4505,
            active_alarms: 4505,
          },
          station_health: {
            distribution: { normal: 1, warning: 5, critical: 10, offline: 1 },
            healthy_rate: 5.9,
          },
          team_performance: {
            engineers: [{ id: 1, name: 'eng' }],
            total_engineers: 1,
            top_engineers: [{ id: 1, name: 'eng' }],
          },
        },
        timestamp: 1786339869,
      },
    });

    const res = await reportApi.getSummary();
    expect(api.get).toHaveBeenCalledWith('/reports/summary');
    expect(res.data.periodDays).toBe(30);
    expect(res.data.overview.totalDevices).toBe(50);
    expect(res.data.overview.onlineDevices).toBe(31);
    expect(res.data.overview.offlineDevices).toBe(6);
    expect(res.data.overview.faultDevices).toBe(7);
    expect(res.data.overview.onlineRate).toBe(62.0);
    expect(res.data.overview.totalStations).toBe(17);
    expect(res.data.overview.completionRate).toBe(50.0);
    expect(res.data.overview.activeAlarms).toBe(4505);
    expect(res.data.stationHealth.distribution.normal).toBe(1);
    expect(res.data.stationHealth.distribution.critical).toBe(10);
    expect(res.data.stationHealth.healthyRate).toBe(5.9);
    expect(res.data.teamPerformance.totalEngineers).toBe(1);
    expect(res.data.teamPerformance.engineers).toHaveLength(1);
  });

  it('handles empty/missing nested objects gracefully', async () => {
    api.get.mockResolvedValue({
      data: { code: 200, message: 'ok', data: {} },
    });

    const res = await reportApi.getSummary();
    expect(res.data.periodDays).toBe(30);
    expect(res.data.overview.totalDevices).toBe(0);
    expect(res.data.overview.onlineRate).toBe(0);
    expect(res.data.stationHealth.distribution.normal).toBe(0);
    expect(res.data.stationHealth.healthyRate).toBe(0);
    expect(res.data.teamPerformance.totalEngineers).toBe(0);
    expect(res.data.teamPerformance.engineers).toEqual([]);
  });

  it('handles partial overview data', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: {
          period_days: 7,
          overview: { total_devices: 10, online_devices: 8 },
        },
      },
    });

    const res = await reportApi.getSummary();
    expect(res.data.periodDays).toBe(7);
    expect(res.data.overview.totalDevices).toBe(10);
    expect(res.data.overview.onlineDevices).toBe(8);
    expect(res.data.overview.offlineDevices).toBe(0);
    expect(res.data.overview.completionRate).toBe(0);
  });
});
