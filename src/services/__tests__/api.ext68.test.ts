/**
 * api ext68 — inspectionTemplateApi.create (POST /inspection/templates)
 * camelCase → snake_case request body, snake → camel response full mapping
 */
import { inspectionTemplateApi } from '../api';
import axios from 'axios';
import type { InspectionTemplateCreate } from '../../types';

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

describe('ext68 — inspectionTemplateApi.create', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sends camelCase body and maps response to camelCase', async () => {
    const body: InspectionTemplateCreate = {
      name: '日常巡检',
      category: 'routine',
      description: '每日例行巡检模板',
      items: [{ name: '外观检查', required: true }, { name: '功能测试', required: false }],
    };
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: '模板创建成功',
        data: {
          id: 1,
          name: '日常巡检',
          description: '每日例行巡检模板',
          items: [{ name: '外观检查', required: true }, { name: '功能测试', required: false }],
          item_count: 2,
          device_types: [],
          target: null,
          status: 'active',
          created_at: '2026-08-14T02:10:23Z',
          updated_at: '2026-08-14T02:10:23Z',
        },
        timestamp: 1786644623,
      },
    });

    const res = await inspectionTemplateApi.create(body);
    expect(mockAxios.post).toHaveBeenCalledWith('/inspection/templates', expect.objectContaining({
      name: '日常巡检',
      category: 'routine',
      description: '每日例行巡检模板',
      items: [{ name: '外观检查', required: true }, { name: '功能测试', required: false }],
    }));
    expect(res.data.id).toBe(1);
    expect(res.data.name).toBe('日常巡检');
    expect(res.data.description).toBe('每日例行巡检模板');
    expect(res.data.items).toHaveLength(2);
    expect(res.data.items[0].name).toBe('外观检查');
    expect(res.data.items[0].required).toBe(true);
    expect(res.data.itemCount).toBe(2);
    expect(res.data.deviceTypes).toEqual([]);
    expect(res.data.target).toBeNull();
    expect(res.data.status).toBe('active');
    expect(res.data.createdAt).toBe('2026-08-14T02:10:23Z');
  });

  it('handles null/missing fields with defaults', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {}, timestamp: 0 },
    });
    const res = await inspectionTemplateApi.create({ name: 't' });
    expect(res.data.id).toBe(0);
    expect(res.data.name).toBe('');
    expect(res.data.description).toBeNull();
    expect(res.data.items).toEqual([]);
    expect(res.data.itemCount).toBe(0);
    expect(res.data.deviceTypes).toEqual([]);
    expect(res.data.target).toBeNull();
    expect(res.data.status).toBe('active');
    expect(res.data.createdAt).toBe('');
    expect(res.data.updatedAt).toBe('');
  });

  it('only sends name when no optional fields provided', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 5 }, timestamp: 0 },
    });
    await inspectionTemplateApi.create({ name: 'minimal' });
    const callArg = mockAxios.post.mock.calls[0][1] as Record<string, unknown>;
    expect(callArg.name).toBe('minimal');
    expect(callArg).not.toHaveProperty('category');
    expect(callArg).not.toHaveProperty('description');
    expect(callArg).not.toHaveProperty('items');
  });

  it('posts to /inspection/templates endpoint', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 1 }, timestamp: 0 },
    });
    await inspectionTemplateApi.create({ name: 'x' });
    expect(mockAxios.post).toHaveBeenCalledTimes(1);
    expect(mockAxios.post.mock.calls[0][0]).toBe('/inspection/templates');
  });

  it('maps null description and empty items array', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: {
          id: 2,
          name: 'empty',
          description: null,
          items: [],
          item_count: 0,
          device_types: ['inverter', 'meter'],
          target: 'station',
          status: 'active',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        timestamp: 0,
      },
    });
    const res = await inspectionTemplateApi.create({ name: 'empty' });
    expect(res.data.description).toBeNull();
    expect(res.data.items).toEqual([]);
    expect(res.data.deviceTypes).toEqual(['inverter', 'meter']);
    expect(res.data.target).toBe('station');
  });
});
