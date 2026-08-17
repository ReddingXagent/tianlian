/**
 * api ext81 — mapper truthy branch coverage (full-data batches)
 * Targets: mapStation, mapWorkOrder, chargingOrderApi, inspectionTaskApi,
 *   gatewayApi, chatApi, deviceMonitorApi, sparePartApi mapper ?? left-side branches
 */
import {
  stationApi,
  chargingOrderApi,
  inspectionTaskApi,
  gatewayApi,
  chatApi,
  deviceMonitorApi,
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

// F1205: any收窄 — mock工厂返回结构已知, 用具体Mock接口替代any
const mockAxios = (axios as unknown as { __mockInstance: { get: jest.Mock; post: jest.Mock; put: jest.Mock; delete: jest.Mock; patch: jest.Mock } }).__mockInstance;

function ok(data: unknown) {
  return { data: { code: 200, message: 'ok', data } };
}

describe('ext81 — mapper truthy branch coverage (full data)', () => {
  beforeEach(() => jest.clearAllMocks());

  // ---- mapStation via stationApi.getList with full items ----
  it('stationApi.getList: full station items → all ?? truthy', async () => {
    const fullStation = {
      id: 21, name: '测试站', code: 'ZHN-001',
      province: '浙江省', city: '杭州市', district: '西湖区',
      address: '文三路100号', lat: 30.2741, lon: 120.1551,
      status: 'normal', station_type: 'charging',
      operator_id: 5, operator_name: '运维商A',
      team_id: 3, total_power: 500, total_devices: 12, gun_count: 8,
      venue_type: 'commercial', total_cost: 1000000, parking_spots: 20,
      health_score: 95,
      branding: {
        operator_name: '运营商', logo_url: 'https://logo.png',
        service_phone: '400-123', theme_color: '#FF0000', source: 'custom',
      },
      created_at: '2025-01-01T00:00:00Z', updated_at: '2025-06-01T00:00:00Z',
    };
    mockAxios.get.mockResolvedValueOnce(ok({ items: [fullStation], total: 1, page: 2, page_size: 15 }));
    const res = await stationApi.getList({ page: 2, pageSize: 15, status: 'normal', keyword: 'test' });
    expect(res.data.items[0]).toMatchObject({
      id: 21, name: '测试站', code: 'ZHN-001',
      province: '浙江省', city: '杭州市', district: '西湖区',
      stationType: 'charging', operatorId: 5, teamId: 3,
      branding: { operatorName: '运营商', themeColor: '#FF0000', source: 'custom' },
    });
    expect(res.data.total).toBe(1);
    expect(res.data.page).toBe(2);
    expect(res.data.pageSize).toBe(15);
  });

  it('stationApi.getDetail: full station → mapStation all fields', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({
      id: 1, name: 'S1', code: 'C1', province: 'P', city: 'CI', district: 'D',
      address: 'A', lat: 1.0, lon: 2.0, status: 'fault',
      station_type: 'solar', operator_id: 1, operator_name: 'OP',
      team_id: 2, total_power: 100, total_devices: 5, gun_count: 3,
      venue_type: 'highway', total_cost: 500000, parking_spots: 10,
      health_score: 88,
      branding: { operator_name: 'B', logo_url: 'u', service_phone: 'p', theme_color: '#000', source: 'api' },
      created_at: 'c', updated_at: 'u',
    }));
    const res = await stationApi.getDetail(1);
    expect(res.data.name).toBe('S1');
    expect(res.data.branding?.operatorName).toBe('B');
  });

  it('stationApi.create: full body → all optional fields sent', async () => {
    mockAxios.post.mockResolvedValueOnce(ok({ id: 1, name: 'N' }));
    await stationApi.create({
      name: 'N', code: 'CODE', province: 'PV', city: 'CT', district: 'DT',
      address: 'AD', lat: 1.5, lon: 2.5, stationType: 'charging',
      operatorId: 3, teamId: 4, totalPower: 200, venueType: 'commercial',
      totalCost: 999, parkingSpots: 15,
    });
    const arg = mockAxios.post.mock.calls[0][1];
    expect(arg).toMatchObject({
      name: 'N', code: 'CODE', province: 'PV', city: 'CT', district: 'DT',
      address: 'AD', lat: 1.5, lon: 2.5, station_type: 'charging',
      operator_id: 3, team_id: 4, total_power: 200, venue_type: 'commercial',
      total_cost: 999, parking_spots: 15,
    });
  });

  // ---- chargingOrderApi.getList with full items ----
  it('chargingOrderApi.getList: full order items → all ?? truthy', async () => {
    const fullOrder = {
      id: 1, order_no: 'ORD001', station_id: 10, device_id: 20, user_id: 30,
      user_type: 'member', vehicle_id: 'V1', plate_number: '浙A12345',
      start_time: '2025-01-01T08:00:00Z', end_time: '2025-01-01T10:00:00Z',
      duration_minutes: 120, start_soc: 30, end_soc: 80,
      start_meter: 1000, end_meter: 1100, stop_reason: 'full',
      charged_kwh: 50, electricity_fee: 30, service_fee: 10,
      parking_fee: 5, idle_penalty: 0, reservation_fee: 0,
      total_amount: 45, discount_amount: 5, paid_amount: 40,
      payment_status: 'paid', order_status: 'completed',
      payment_method: 'wechat', remark: 'good',
      created_at: '2025-01-01T08:00:00Z', updated_at: '2025-01-01T10:00:00Z',
    };
    mockAxios.get.mockResolvedValueOnce(ok({ items: [fullOrder], total: 1, page: 1, page_size: 20 }));
    const res = await chargingOrderApi.getList({ page: 1, pageSize: 20 });
    expect(res.data.items[0]).toMatchObject({
      orderNo: 'ORD001', stationId: 10, userId: 30,
      plateNumber: '浙A12345', chargedKwh: 50, paymentStatus: 'paid',
    });
  });

  // ---- inspectionTaskApi.getList with full items ----
  it('inspectionTaskApi.getList: full task items → all ?? truthy', async () => {
    const fullTask = {
      id: 1, station_id: 5, station_name: '站A', device_id: 3, device_name: '设备B',
      type: 'weekly', status: 'in_progress', scheduled_date: '2025-01-01',
      completed_date: '2025-01-02', assigned_to: 7, assigned_name: '张三',
      description: '周巡检',
      items: [
        { id: 1, name: '检查外观', expected: '无损伤', result: 'pass', note: 'ok' },
        { id: 2, name: '测电压', expected: '220V', result: 'fail', note: '异常' },
      ],
      created_at: '2025-01-01T00:00:00Z', updated_at: '2025-01-01T12:00:00Z',
    };
    mockAxios.get.mockResolvedValueOnce(ok({ items: [fullTask], total: 1, page: 1, page_size: 20 }));
    const res = await inspectionTaskApi.getList({ page: 1, pageSize: 20 });
    expect(res.data.items[0]).toMatchObject({
      stationId: 5, stationName: '站A', type: 'weekly', status: 'in_progress',
      items: [{ id: 1, name: '检查外观', result: 'pass' }, { id: 2, name: '测电压', result: 'fail' }],
    });
  });

  // ---- gatewayApi.getList with full items ----
  it('gatewayApi.getList: full gateway items → all ?? truthy', async () => {
    const fullGw = {
      id: 1, sn: 'GW001', name: '网关1', model: 'X1', manufacturer: 'HWT',
      station_id: 10, status: 'online', firmware_version: 'v2.0',
      last_online: '2025-01-01T00:00:00Z', ip_address: '192.168.1.1',
      mac_address: 'AA:BB:CC:DD:EE:FF', location: '机房', health_score: 99,
      created_at: '2024-01-01', updated_at: '2025-01-01', notes: '主网关',
    };
    mockAxios.get.mockResolvedValueOnce(ok({ items: [fullGw], total: 1, page: 1, page_size: 20 }));
    const res = await gatewayApi.getList();
    expect(res.data.items[0]).toMatchObject({
      sn: 'GW001', model: 'X1', manufacturer: 'HWT', stationId: 10,
      status: 'online', firmwareVersion: 'v2.0', ipAddress: '192.168.1.1',
      macAddress: 'AA:BB:CC:DD:EE:FF', notes: '主网关',
    });
  });

  // ---- gatewayApi.getFirmware with full items ----
  it('gatewayApi.getFirmware: full firmware items → all ?? truthy', async () => {
    const fullFw = {
      id: 1, version: 'v3.0', file_id: 'fw-001', file_size: 1048576,
      release_notes: 'Bug fixes', status: 'stable',
      created_at: '2025-01-01', updated_at: '2025-06-01',
    };
    mockAxios.get.mockResolvedValueOnce(ok({ items: [fullFw], total: 1, page: 1, page_size: 20 }));
    const res = await gatewayApi.getFirmware();
    expect(res.data.items[0]).toMatchObject({
      version: 'v3.0', fileId: 'fw-001', fileSize: 1048576,
      releaseNotes: 'Bug fixes', status: 'stable',
    });
  });

  // ---- gatewayApi.getStatus full data ----
  it('gatewayApi.getStatus: full data → all ?? truthy', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({
      online_count: 15, offline_count: 3, maintenance_count: 2, fault_count: 1, total: 21,
    }));
    const res = await gatewayApi.getStatus();
    expect(res.data).toMatchObject({
      onlineCount: 15, offlineCount: 3, maintenanceCount: 2, faultCount: 1, total: 21,
    });
  });

  // ---- chatApi.ask with full data including sources/actions/usage ----
  it('chatApi.ask: full response → all mapper ?? truthy', async () => {
    mockAxios.post.mockResolvedValueOnce(ok({
      answer: '结果是42',
      confidence: 0.95,
      sources: [
        { title: '文档A', url: 'https://a.com', type: 'manual' },
        { title: 'FAQ', url: 'https://faq.com', type: 'faq' },
      ],
      actions: [
        { type: 'redirect', label: '查看详情', target: '/detail/1' },
      ],
      needs_human: true,
      usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 },
    }));
    const res = await chatApi.send('测试问题', { conversationId: 'conv1', context: { k: 'v' } });
    expect(res.data).toMatchObject({
      answer: '结果是42', confidence: 0.95, needsHuman: true,
      sources: [{ title: '文档A', type: 'manual' }, { title: 'FAQ', type: 'faq' }],
      actions: [{ type: 'redirect', label: '查看详情', target: '/detail/1' }],
      usage: { promptTokens: 100, completionTokens: 50, totalTokens: 150 },
    });
  });

  // ---- deviceMonitorApi.getRealtimeOverview full data ----
  it('deviceMonitorApi.getRealtimeOverview: full data → all ?? truthy', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({
      totalPower: 500.5, powerTrend: 12.3,
      todayGeneration: 200, todayConsumption: 150,
      gridImport: 30, gridExport: 80,
      efficiency: 92.5, update_time: '2025-01-01T12:00:00Z',
      devices: [{
        id: 1, name: '逆变器1', type: 'inverter',
        status: 'online', power: 100.5, last_heartbeat: '2025-01-01T12:00:00Z',
        station_id: 10, station_name: '主站',
      }],
    }));
    const res = await deviceMonitorApi.getRealtimeOverview();
    expect(res.data).toMatchObject({
      totalPower: 500.5, powerTrend: 12.3, efficiency: 92.5,
      updateTime: '2025-01-01T12:00:00Z',
      devices: [{ id: 1, name: '逆变器1', type: 'inverter', status: 'online', power: 100.5 }],
    });
  });

  // ---- sparePartApi.getList full items ----
  it('sparePartApi.getList: full items → all ?? truthy', async () => {
    const fullPart = {
      id: 1, part_name: '电缆', part_model: 'C-10',
      total_quantity: 50, available_quantity: 45,
      warehouse: '仓库B', created_at: '2025-01-01',
    };
    mockAxios.get.mockResolvedValueOnce(ok({ items: [fullPart], total: 1, page: 1, page_size: 20 }));
    const res = await sparePartApi.getList();
    expect(res.data.items[0]).toMatchObject({
      partName: '电缆', partModel: 'C-10',
      totalQuantity: 50, availableQuantity: 45, warehouse: '仓库B',
    });
  });

  // ---- stationApi.getList query params with keyword ----
  it('stationApi.getList: keyword only (no page/pageSize) → defaults', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({ items: [], total: 0 }));
    await stationApi.getList({ keyword: 'test' });
    expect(mockAxios.get).toHaveBeenCalledWith('/stations', { params: { keyword: 'test' } });
  });
});
