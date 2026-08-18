/**
 * api ext92 — F1473 deviceApi.getMaintenanceRecords 新端点对接测试
 * GET /devices/{id}/maintenance-records — 设备维保记录列表 (分页)
 */
import MockAdapter from 'axios-mock-adapter';
import api, { deviceApi } from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mock = new MockAdapter(api);

afterEach(() => mock.reset());

describe('F1473 deviceApi.getMaintenanceRecords', () => {
  it('maps snake_case fields → camelCase and returns paginated data', async () => {
    mock.onGet('/devices/2/maintenance-records').reply(200, {
      code: 200,
      message: 'success',
      data: {
        items: [
          {
            id: 10,
            device_id: 2,
            type: 'routine',
            title: '日常保养',
            description: '设备定期保养检查',
            status: 'completed',
            scheduled_date: '2026-08-01',
            completed_date: '2026-08-01T14:30:00',
            engineer_id: 31,
            engineer_name: '张三',
            cost: 150.5,
            remark: '一切正常',
            created_at: '2026-07-15T09:00:00',
            updated_at: '2026-08-01T14:30:00',
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      },
      timestamp: 1787075800,
    });

    const res = await deviceApi.getMaintenanceRecords(2);
    expect(res.code).toBe(200);
    expect(res.data.items).toHaveLength(1);
    const r = res.data.items[0];
    expect(r.id).toBe(10);
    expect(r.deviceId).toBe(2);
    expect(r.type).toBe('routine');
    expect(r.title).toBe('日常保养');
    expect(r.status).toBe('completed');
    expect(r.scheduledDate).toBe('2026-08-01');
    expect(r.completedDate).toBe('2026-08-01T14:30:00');
    expect(r.engineerId).toBe(31);
    expect(r.engineerName).toBe('张三');
    expect(r.cost).toBe(150.5);
    expect(r.remark).toBe('一切正常');
    expect(r.createdAt).toBe('2026-07-15T09:00:00');
    expect(r.updatedAt).toBe('2026-08-01T14:30:00');
    expect(res.data.total).toBe(1);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  it('handles empty list (no maintenance records)', async () => {
    mock.onGet('/devices/2/maintenance-records').reply(200, {
      code: 200,
      message: 'success',
      data: { items: [], total: 0, page: 1, page_size: 20 },
      timestamp: 1787075800,
    });

    const res = await deviceApi.getMaintenanceRecords(2);
    expect(res.data.items).toHaveLength(0);
    expect(res.data.total).toBe(0);
  });

  it('passes pagination params to the request', async () => {
    mock.onGet('/devices/5/maintenance-records', { params: { page: 2, pageSize: 10 } }).reply(200, {
      code: 200, message: 'success',
      data: { items: [], total: 0, page: 2, page_size: 10 },
      timestamp: 1787075800,
    });

    const res = await deviceApi.getMaintenanceRecords(5, { page: 2, pageSize: 10 });
    expect(res.data.page).toBe(2);
    expect(mock.history.get).toHaveLength(1);
  });

  it('defaults missing fields to safe values', async () => {
    mock.onGet('/devices/3/maintenance-records').reply(200, {
      code: 200, message: 'success',
      data: {
        items: [{ id: 1 }],
        total: 1, page: 1, page_size: 20,
      },
      timestamp: 1787075800,
    });

    const res = await deviceApi.getMaintenanceRecords(3);
    const r = res.data.items[0];
    expect(r.id).toBe(1);
    expect(r.deviceId).toBe(3); // falls back to the path id
    expect(r.type).toBe('');
    expect(r.title).toBe('');
    expect(r.status).toBe('');
    expect(r.scheduledDate).toBeNull();
    expect(r.completedDate).toBeNull();
    expect(r.engineerId).toBeNull();
    expect(r.engineerName).toBeNull();
    expect(r.cost).toBeNull();
    expect(r.remark).toBeNull();
    expect(r.createdAt).toBe('');
    expect(r.updatedAt).toBeNull();
  });

  it('handles data:null with empty items and default pagination', async () => {
    mock.onGet('/devices/7/maintenance-records').reply(200, {
      code: 200,
      message: 'success',
      data: null,
      timestamp: 1787075900,
    });

    const res = await deviceApi.getMaintenanceRecords(7);
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(0);
  });

  it('handles items:null and missing pagination fields', async () => {
    mock.onGet('/devices/8/maintenance-records').reply(200, {
      code: 200,
      message: 'success',
      data: { items: null },
      timestamp: 1787076000,
    });

    const res = await deviceApi.getMaintenanceRecords(8);
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(0);
  });

  it('handles item with null/undefined id field', async () => {
    mock.onGet('/devices/9/maintenance-records').reply(200, {
      code: 200,
      message: 'success',
      data: {
        items: [{ id: null, device_id: null, type: null, title: null }],
        total: 1, page: 1, page_size: 10,
      },
      timestamp: 1787076100,
    });

    const res = await deviceApi.getMaintenanceRecords(9);
    const r = res.data.items[0];
    expect(r.id).toBe(0);
    expect(r.deviceId).toBe(9); // falls back to path id
    expect(r.type).toBe('');
    expect(r.title).toBe('');
  });
});
