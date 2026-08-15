/**
 * api ext80 — mapper fallback branches batch 7
 * Targets: gatewayApi.getList/getById/getFirmware, fleetApi.getDrivers,
 *   stationApi.getList/getDetail (mapStation), teamApi.getList/getDetail,
 *   chatApi.send, notificationSendApi.send
 */
import {
  gatewayApi,
  fleetApi,
  stationApi,
  teamApi,
  chatApi,
  notificationSendApi,
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

// F1205: any收窄 — mock工厂返回结构已知, 用具体Mock接口替代any
const mockAxios = (axios as unknown as { __mockInstance: { get: jest.Mock; post: jest.Mock; put: jest.Mock; delete: jest.Mock; patch: jest.Mock } }).__mockInstance;

describe('ext80 — mapper fallback branch coverage batch 7', () => {
  beforeEach(() => jest.clearAllMocks());

  // gatewayApi.getList — items [{}] → fallback
  it('gatewayApi.getList: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await gatewayApi.getList();
    expect(res.data.items[0]).toEqual({
      id: undefined, sn: '', name: '',
      model: null, manufacturer: null, stationId: null,
      status: 'offline', firmwareVersion: null, lastOnline: null,
      ipAddress: null, macAddress: null, location: null,
      healthScore: 0, createdAt: '', updatedAt: '', notes: null,
    });
  });

  // gatewayApi.getById — data {} → fallback
  it('gatewayApi.getById: data {} → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await gatewayApi.getById(1);
    expect(res.data).toEqual({
      id: undefined, sn: '', name: '',
      model: null, manufacturer: null, stationId: null,
      status: 'offline', firmwareVersion: null, lastOnline: null,
      ipAddress: null, macAddress: null, location: null,
      healthScore: 0, createdAt: '', updatedAt: '', notes: null,
    });
  });

  // fleetApi.getDrivers — items [{}] → fallback
  it('fleetApi.getDrivers: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await fleetApi.getDrivers();
    expect(res.data.items[0]).toEqual({
      id: 0, name: '', phone: null, licenseNumber: null,
      vehiclePlate: null, status: 'unknown',
      createdAt: null, updatedAt: null,
    });
  });

  // stationApi.getList — items [{}] → mapStation fallback
  it('stationApi.getList: items [{}] → mapStation fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await stationApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0, name: '', code: '', province: '', city: '', district: '',
      address: '', lat: 0, lon: 0, status: 'normal',
      stationType: null, operatorId: null, operatorName: null,
      teamId: null, totalPower: 0, totalDevices: 0, gunCount: 0,
      venueType: null, totalCost: null, parkingSpots: null,
      healthScore: 0, branding: null, createdAt: '', updatedAt: null,
    });
  });

  // stationApi.getDetail — data {} → mapStation fallback
  it('stationApi.getDetail: data {} → mapStation fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await stationApi.getDetail(1);
    expect(res.data).toEqual({
      id: 0, name: '', code: '', province: '', city: '', district: '',
      address: '', lat: 0, lon: 0, status: 'normal',
      stationType: null, operatorId: null, operatorName: null,
      teamId: null, totalPower: 0, totalDevices: 0, gunCount: 0,
      venueType: null, totalCost: null, parkingSpots: null,
      healthScore: 0, branding: null, createdAt: '', updatedAt: null,
    });
  });

  // teamApi.getList — items [{}] → fallback
  it('teamApi.getList: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await teamApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0, name: '', code: null, leaderId: null,
      leaderName: null, description: null,
      memberCount: 0, stationCount: 0,
      status: 'active', createdAt: null,
    });
  });

  // teamApi.getDetail — data {} → fallback
  it('teamApi.getDetail: data {} → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await teamApi.getDetail(1);
    // Just verify it doesn't crash
    expect(res.data).toBeDefined();
  });

  // notificationSendApi.send — data {} → fallback
  it('notificationSendApi.send: data {} → fallback', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await notificationSendApi.send({
      userId: 1, title: 'test', content: 'test',
    });
    expect(res.data).toEqual({
      status: '', channel: null, userId: null,
      title: null, sentAt: null,
    });
  });

  // chatApi.send — data {} → fallback
  it('chatApi.send: data {} → fallback', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await chatApi.send('test message');
    expect(res.data).toEqual({
      answer: '', confidence: 0,
      sources: [], actions: [],
      needsHuman: false, usage: null,
    });
  });
});
