/**
 * api ext71 — stationApi.create (POST /stations) + userApi.create (POST /users)
 */
import { stationApi, userApi } from '../api';
import axios from 'axios';

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
  setItemSecure: jest.fn().mockResolvedValue(undefined),
  deleteItemSecure: jest.fn().mockResolvedValue(undefined),
}));

const mockAxios = (axios as unknown as { __mockInstance: Record<string, jest.Mock> }).__mockInstance;

describe('ext71 — stationApi.create + userApi.create', () => {
  beforeEach(() => jest.clearAllMocks());

  // ── stationApi.create ──

  it('stationApi.create: camelCase body → snake_case, returns mapped Station', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 30, name: '测试站', code: 'ZHN0010',
          province: '浙江省', city: '杭州市', district: null, address: '地址',
          lat: null, lon: null, operator_id: null, operator_name: null, team_id: null,
          total_power: null, total_devices: 0, gun_count: 0, venue_type: null,
          total_cost: null, parking_spots: null, station_type: null,
          status: 'normal', health_score: 100.0,
          created_at: '2026-08-14T03:04:00+08:00', updated_at: null,
          branding: { operator_name: '天链', logo_url: '', service_phone: '', theme_color: '#00A86B', source: 'default' },
        },
        timestamp: 1786647840,
      },
    });

    const res = await stationApi.create({
      name: '测试站', code: 'CUSTOM', province: '浙江省', city: '杭州市', address: '地址',
    });

    // endpoint
    expect(mockAxios.post.mock.calls[0][0]).toBe('/stations');
    // camel→snake request
    const payload = mockAxios.post.mock.calls[0][1] as Record<string, unknown>;
    expect(payload.name).toBe('测试站');
    expect(payload.code).toBe('CUSTOM');
    expect(payload.province).toBe('浙江省');
    expect(payload.city).toBe('杭州市');
    expect(payload.address).toBe('地址');

    // response mapping
    expect(res.code).toBe(200);
    expect(res.data.id).toBe(30);
    expect(res.data.name).toBe('测试站');
    expect(res.data.code).toBe('ZHN0010');
    expect(res.data.province).toBe('浙江省');
    expect(res.data.status).toBe('normal');
    expect(res.data.healthScore).toBe(100.0);
    expect(res.data.branding?.operatorName).toBe('天链');
    expect(res.data.branding?.themeColor).toBe('#00A86B');
    expect(res.data.createdAt).toBe('2026-08-14T03:04:00+08:00');
    expect(res.data.updatedAt).toBeNull();
  });

  it('stationApi.create: minimal body (only name) sends just name', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200, message: 'success',
        data: { id: 31, name: '最小站', code: 'ZHN0011', status: 'normal', health_score: 100.0, total_devices: 0, gun_count: 0, created_at: '2026-08-14T03:05:00+08:00', branding: null },
        timestamp: 1786647900,
      },
    });

    const res = await stationApi.create({ name: '最小站' });

    const payload = mockAxios.post.mock.calls[0][1] as Record<string, unknown>;
    expect(payload.name).toBe('最小站');
    expect(payload).not.toHaveProperty('code');
    expect(payload).not.toHaveProperty('province');

    expect(res.data.id).toBe(31);
    expect(res.data.branding).toBeNull();
  });

  it('stationApi.create: null/missing defaults in sparse response', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { id: 32, name: 'S' }, timestamp: 0 },
    });

    const res = await stationApi.create({ name: 'S' });

    expect(res.data.id).toBe(32);
    expect(res.data.name).toBe('S');
    expect(res.data.code).toBe('');
    expect(res.data.status).toBe('normal');
    expect(res.data.healthScore).toBe(0);
    expect(res.data.branding).toBeNull();
    expect(res.data.createdAt).toBe('');
  });

  // ── userApi.create ──

  it('userApi.create: camelCase body → snake_case, returns mapped UserDetail', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200, message: 'success',
        data: {
          id: 40, username: 'newuser', real_name: '新用户', phone: '13800138001',
          role: 'engineer', level: 'junior', team_id: null, team_name: null,
          status: 'active', last_login: null,
          created_at: '2026-08-14T03:06:00+08:00', updated_at: null,
        },
        timestamp: 1786647960,
      },
    });

    const res = await userApi.create({
      username: 'newuser', password: 'Pass1234!', realName: '新用户', phone: '13800138001', role: 'engineer',
    });

    expect(mockAxios.post.mock.calls[0][0]).toBe('/users');
    const payload = mockAxios.post.mock.calls[0][1] as Record<string, unknown>;
    expect(payload.username).toBe('newuser');
    expect(payload.password).toBe('Pass1234!');
    expect(payload.real_name).toBe('新用户');
    expect(payload.phone).toBe('13800138001');
    expect(payload.role).toBe('engineer');

    expect(res.code).toBe(200);
    expect(res.data.id).toBe(40);
    expect(res.data.username).toBe('newuser');
    expect(res.data.realName).toBe('新用户');
    expect(res.data.phone).toBe('13800138001');
    expect(res.data.role).toBe('engineer');
    expect(res.data.level).toBe('junior');
    expect(res.data.status).toBe('active');
    expect(res.data.lastLogin).toBe('');
    expect(res.data.createdAt).toBe('2026-08-14T03:06:00+08:00');
  });

  it('userApi.create: minimal body (only username) sends just username', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { id: 41, username: 'min' }, timestamp: 0 },
    });

    const res = await userApi.create({ username: 'min' });

    const payload = mockAxios.post.mock.calls[0][1] as Record<string, unknown>;
    expect(payload.username).toBe('min');
    expect(payload).not.toHaveProperty('password');
    expect(payload).not.toHaveProperty('real_name');

    expect(res.data.id).toBe(41);
    expect(res.data.username).toBe('min');
    expect(res.data.realName).toBe('');
    expect(res.data.role).toBe('');
    expect(res.data.status).toBe('');
  });

  it('userApi.create: business error (duplicate username) passes through', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 400, message: '用户名 test 已存在', data: null, timestamp: 1786648000 },
    });

    const res = await userApi.create({ username: 'test', password: 'X' });

    expect(res.code).toBe(400);
    expect(res.data).toBeNull();
  });
});
