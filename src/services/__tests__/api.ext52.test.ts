/**
 * ext52 — alarmApi.resolve (PUT /alarms/{id}/resolve)
 * Cases: resolve endpoint+method, resolve return shape, resolve null handling,
 *        resolve error response, resolve status change
 */
import { alarmApi } from '../api';

// Mock axios
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

// Mock SecureStore
jest.mock('expo-secure-store', () => ({
  getItemSecure: jest.fn(),
  setItemSecure: jest.fn(),
  deleteItemSecure: jest.fn(),
}));

import axios from 'axios';
const mockAxios = (axios as unknown as {
  __mockInstance: { put: jest.Mock };
}).__mockInstance;

describe('ext52 — alarmApi.resolve (PUT /alarms/{id}/resolve)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('1. resolve: calls correct endpoint with PUT method', async () => {
    mockAxios.put.mockResolvedValue({
      data: { code: 200, message: 'success', data: { id: 1, status: 'resolved' }, timestamp: 0 },
    });

    await alarmApi.resolve(1);

    expect(mockAxios.put).toHaveBeenCalledTimes(1);
    expect(mockAxios.put).toHaveBeenCalledWith('/alarms/1/resolve');
  });

  it('2. resolve: returns response with alarm data (status=resolved)', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          device_id: 5,
          station_id: 14,
          alarm_type: '通讯延迟',
          level: 'warning',
          content: '通讯延迟',
          status: 'resolved',
          created_at: '2026-06-16T09:07:01+08:00',
          handled_at: '2026-08-13T23:09:52.927252+08:00',
          cleared_at: '2026-08-13T23:09:52.927326+08:00',
          device_name: 'TL-BAT-200AH-005',
          device_code: 'BATTERY202600005',
          station_name: '昆明光伏电站',
        },
        timestamp: 1786633792,
      },
    });

    const res = await alarmApi.resolve(1);
    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
    expect(res.data).toBeTruthy();
    expect(res.data.id).toBe(1);
    expect(res.data.status).toBe('resolved');
    expect(res.timestamp).toBe(1786633792);
  });

  it('3. resolve: handles null data in response', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 404,
        message: '告警不存在',
        data: null,
        timestamp: 1786633792,
      },
    });

    const res = await alarmApi.resolve(999);
    expect(res.code).toBe(404);
    expect(res.message).toBe('告警不存在');
    expect(res.data).toBeNull();
  });

  it('4. resolve: returns full alarm object with all snake_case fields', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 10,
          device_id: 1,
          station_id: 1,
          rule_id: null,
          alarm_type: '过温',
          level: 'critical',
          content: '设备温度过高',
          status: 'resolved',
          fault_code: 'E001',
          fault_source: 'sensor',
          trigger_metric: 'temperature',
          trigger_value: '95.5',
          trigger_threshold: '80',
          trigger_operator: '>',
          diagnosis_result: '散热风扇故障',
          repair_suggestion: '更换风扇',
          remote_fixable: true,
          created_at: '2026-08-01T10:00:00+08:00',
          handled_at: '2026-08-13T23:00:00+08:00',
          cleared_at: '2026-08-13T23:00:00+08:00',
          device_name: 'TL-INV-001',
          device_code: 'INV001',
          station_name: '测试站',
        },
        timestamp: 1786633792,
      },
    });

    const res = await alarmApi.resolve(10);
    expect((res.data as Record<string, unknown>).id).toBe(10);
    expect((res.data as Record<string, unknown>).fault_code).toBe('E001');
    expect((res.data as Record<string, unknown>).diagnosis_result).toBe('散热风扇故障');
    expect((res.data as Record<string, unknown>).remote_fixable).toBe(true);
    expect((res.data as Record<string, unknown>).trigger_value).toBe('95.5');
  });

  it('5. resolve: works with different alarm IDs', async () => {
    mockAxios.put.mockResolvedValue({
      data: { code: 200, message: 'ok', data: { id: 777, status: 'resolved' }, timestamp: 0 },
    });

    await alarmApi.resolve(777);
    expect(mockAxios.put).toHaveBeenCalledWith('/alarms/777/resolve');
  });
});
