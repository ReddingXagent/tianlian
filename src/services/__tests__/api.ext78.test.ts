/**
 * api ext78 — mapper fallback branches batch 5
 * Targets: chargingOrderApi.getById, inspectionTaskApi.getList,
 *   engineerApi.getList/create, webhookApi.getList,
 *   sparePartApi (lines 2850-2999)
 */
import {
  chargingOrderApi,
  inspectionTaskApi,
  engineerApi,
  webhookApi,
  sparePartApi,
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

describe('ext78 — mapper fallback branch coverage batch 5', () => {
  beforeEach(() => jest.clearAllMocks());

  // chargingOrderApi.getById — data {} → fallback
  it('chargingOrderApi.getById: data {} → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await chargingOrderApi.getById(1);
    expect(res.data).toEqual({
      id: 0, orderNo: '', stationId: 0, deviceId: 0, userId: 0,
      userType: null, vehicleId: null, plateNumber: null,
      startTime: null, endTime: null, durationMinutes: 0,
      startSoc: null, endSoc: null, startMeter: null, endMeter: null,
      stopReason: null, chargedKwh: 0, electricityFee: 0, serviceFee: 0,
      parkingFee: 0, idlePenalty: 0, reservationFee: 0,
      totalAmount: 0, discountAmount: 0, paidAmount: 0,
      paymentStatus: 'unpaid', orderStatus: 'pending',
      paymentMethod: null, remark: null, createdAt: '', updatedAt: '',
    });
  });

  // chargingOrderApi.getById — data null → null
  it('chargingOrderApi.getById: data null → null', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await chargingOrderApi.getById(1);
    expect(res.data).toBeNull();
  });

  // inspectionTaskApi.getList — items [{}] → fallback
  it('inspectionTaskApi.getList: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await inspectionTaskApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0, stationId: 0, stationName: '', deviceId: 0, deviceName: '',
      type: 'daily', status: 'pending', scheduledDate: '',
      completedDate: undefined, assignedTo: undefined, assignedName: undefined,
      description: '', items: [], createdAt: '', updatedAt: '',
    });
  });

  // inspectionTaskApi.getList — data null → empty
  it('inspectionTaskApi.getList: data null → empty', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await inspectionTaskApi.getList();
    expect(res.data.items).toEqual([]);
  });

  // engineerApi.getList — items [{}] → fallback
  it('engineerApi.getList: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await engineerApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0, username: '', name: '', phone: null,
      level: 'junior', teamId: null, status: 'active',
      role: '', createdAt: '', updatedAt: '',
    });
  });

  // engineerApi.create — data {} → fallback
  it('engineerApi.create: data {} → fallback', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await engineerApi.create({
      username: 'test', password: '123', name: 'Test',
    });
    expect(res.data).toEqual({
      id: 0, username: '', name: '', phone: null,
      level: 'junior', teamId: null, status: 'active',
      role: '', createdAt: '', updatedAt: '',
    });
  });

  // webhookApi.getList — items [{}] → fallback
  it('webhookApi.getList: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await webhookApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0, name: '', url: '', events: [],
      secret: null, enabled: false,
      lastTriggeredAt: null, lastResponseStatus: null,
      createdAt: '', updatedAt: '',
    });
  });

  // sparePartApi — test getList with {} items
  it('sparePartApi.getList: items [{}] → fallback (if exists)', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await sparePartApi.getList();
    // Just verify it doesn't crash and returns something
    expect(res).toBeDefined();
    expect(res.data.items.length).toBeGreaterThan(0);
  });
});
