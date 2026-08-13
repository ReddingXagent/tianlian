/**
 * api ext73 — coverage: workOrderActionApi.requestSparePart
 *             + deviceMonitorApi.getRealtimeOverview
 *             + engineerApi.delete / webhookApi.delete / gatewayApi.delete / tenantListApi.delete
 *             + healthApi.getHealth
 * Targets uncovered lines: 982-993, 1017-1031, 2464-2466, 2554-2556,
 *   3370-3372, 3437-3439, 3816-3819
 */
import {
  workOrderActionApi,
  deviceMonitorApi,
  engineerApi,
  webhookApi,
  gatewayApi,
  tenantListApi,
  healthApi,
} from '../api';
import axios from 'axios';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return {
    create: jest.fn(() => mockInstance),
    __mockInstance: mockInstance,
  };
});

const mockAxios = (axios as unknown as { __mockInstance: any }).__mockInstance;

describe('ext73 — coverage push: requestSparePart + getRealtimeOverview + 4 delete APIs + getHealth', () => {

  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ── workOrderActionApi.requestSparePart (lines 982-993) ──

  it('requestSparePart: full body camelCase→snake_case + response mapping', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: {
          id: 42,
          order_id: 'WO-2026-001',
          part_name: '继电器',
          part_model: 'JQX-13F',
          quantity: 2,
          reason: '更换损坏件',
          status: 'requested',
          inventory_deducted: false,
          created_at: '2026-08-14T00:00:00Z',
        },
      },
    });
    const res = await workOrderActionApi.requestSparePart('WO-001', {
      partName: '继电器',
      reason: '更换损坏件',
      partModel: 'JQX-13F',
      quantity: 2,
    });
    expect(mockAxios.post).toHaveBeenCalledWith('/work-orders/WO-001/spare-parts', {
      part_name: '继电器',
      reason: '更换损坏件',
      part_model: 'JQX-13F',
      quantity: 2,
    });
    expect(res.data.id).toBe(42);
    expect(res.data.orderId).toBe('WO-2026-001');
    expect(res.data.partName).toBe('继电器');
    expect(res.data.partModel).toBe('JQX-13F');
    expect(res.data.quantity).toBe(2);
    expect(res.data.status).toBe('requested');
    expect(res.data.inventoryDeducted).toBe(false);
    expect(res.data.createdAt).toBe('2026-08-14T00:00:00Z');
  });

  it('requestSparePart: minimal body (omit optional fields)', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: {
          id: 1,
          order_id: 'WO-1',
          part_name: '保险丝',
          quantity: 1,
          status: 'requested',
          inventory_deducted: true,
          created_at: '',
        },
      },
    });
    const res = await workOrderActionApi.requestSparePart('1', {
      partName: '保险丝',
      reason: '需要更换',
    });
    expect(mockAxios.post).toHaveBeenCalledWith('/work-orders/1/spare-parts', {
      part_name: '保险丝',
      reason: '需要更换',
    });
    expect(res.data.partModel).toBeNull();
    expect(res.data.quantity).toBe(1);
  });

  it('requestSparePart: null data → null response', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 404, message: '工单不存在', data: null },
    });
    const res = await workOrderActionApi.requestSparePart('999', {
      partName: 'X',
      reason: 'Y',
    });
    expect(res.data).toBeNull();
    expect(res.code).toBe(404);
  });

  // ── deviceMonitorApi.getRealtimeOverview (lines 1017-1031) ──

  it('getRealtimeOverview: full mapping with devices', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: {
          totalPower: 1500.5,
          powerTrend: 5.2,
          todayGeneration: 8000,
          todayConsumption: 6000,
          gridImport: 200,
          gridExport: 50,
          efficiency: 92.5,
          update_time: '2026-08-14T03:00:00Z',
          devices: [
            { id: 1, name: '逆变器A', type: 'inverter', power: 500, status: 'online' },
            { id: 2, name: '逆变器B', type: 'inverter', power: 480, status: 'online' },
          ],
        },
      },
    });
    const res = await deviceMonitorApi.getRealtimeOverview();
    expect(res.data.totalPower).toBe(1500.5);
    expect(res.data.powerTrend).toBe(5.2);
    expect(res.data.todayGeneration).toBe(8000);
    expect(res.data.todayConsumption).toBe(6000);
    expect(res.data.gridImport).toBe(200);
    expect(res.data.gridExport).toBe(50);
    expect(res.data.efficiency).toBe(92.5);
    expect(res.data.updateTime).toBe('2026-08-14T03:00:00Z');
    expect(res.data.devices).toHaveLength(2);
    expect(res.data.devices[0].id).toBe(1);
    expect(res.data.devices[0].name).toBe('逆变器A');
    expect(res.data.devices[0].type).toBe('inverter');
    expect(res.data.devices[0].power).toBe(500);
    expect(res.data.devices[0].status).toBe('online');
  });

  it('getRealtimeOverview: empty/null data → defaults', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await deviceMonitorApi.getRealtimeOverview();
    expect(res.data.totalPower).toBe(0);
    expect(res.data.powerTrend).toBe(0);
    expect(res.data.todayGeneration).toBe(0);
    expect(res.data.todayConsumption).toBe(0);
    expect(res.data.gridImport).toBe(0);
    expect(res.data.gridExport).toBe(0);
    expect(res.data.efficiency).toBe(0);
    expect(res.data.updateTime).toBe('');
    expect(res.data.devices).toEqual([]);
  });

  // ── engineerApi.delete (lines 2464-2466) ──

  it('engineerApi.delete: returns ApiResponse<null>', async () => {
    mockAxios.delete.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await engineerApi.delete(5);
    expect(mockAxios.delete).toHaveBeenCalledWith('/engineers/5');
    expect(res.code).toBe(200);
    expect(res.data).toBeNull();
  });

  // ── webhookApi.delete (lines 2554-2556) ──

  it('webhookApi.delete: returns ApiResponse<null>', async () => {
    mockAxios.delete.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await webhookApi.delete(3);
    expect(mockAxios.delete).toHaveBeenCalledWith('/webhooks/3');
    expect(res.code).toBe(200);
    expect(res.data).toBeNull();
  });

  // ── gatewayApi.delete (lines 3370-3372) ──

  it('gatewayApi.delete: returns ApiResponse<null>', async () => {
    mockAxios.delete.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await gatewayApi.delete(7);
    expect(mockAxios.delete).toHaveBeenCalledWith('/gateways/7');
    expect(res.code).toBe(200);
    expect(res.data).toBeNull();
  });

  // ── tenantListApi.delete (lines 3437-3439) ──

  it('tenantListApi.delete: returns ApiResponse<null>', async () => {
    mockAxios.delete.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await tenantListApi.delete(2);
    expect(mockAxios.delete).toHaveBeenCalledWith('/tenants/2');
    expect(res.code).toBe(200);
    expect(res.data).toBeNull();
  });

  // ── healthApi.getHealth (lines 3816-3819) ──

  it('getHealth: maps status/version/service', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: {
          status: 'healthy',
          version: '3.1.0',
          service: 'tianlian-api',
        },
      },
    });
    const res = await healthApi.getHealth();
    expect(res.data.status).toBe('healthy');
    expect(res.data.version).toBe('3.1.0');
    expect(res.data.service).toBe('tianlian-api');
  });

  it('getHealth: null data → defaults (status=error, version=unknown)', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await healthApi.getHealth();
    expect(res.data.status).toBe('error');
    expect(res.data.version).toBe('unknown');
    expect(res.data.service).toBe('unknown');
  });
});
