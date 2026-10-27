/**
 * api ext93 — knowledge/search & inspection/templates API契约修正测试
 *
 * F1474: 修正两个映射不准确:
 * 1. knowledge/search: API返回 category/highlight/author(nullable)/updated_at(nullable)
 *    代码原映射 category_id/category_name/tags/view_count/status/created_at (不存在的字段)
 * 2. inspection/templates: API返回 item_count/device_types/target/status
 *    代码原映射 type/enabled (不存在的字段)
 */
import { knowledgeApi, inspectionTemplateApi } from '../api';

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

const api = require('../api').default;

function makeResponse(data: unknown) {
  return { data: { code: 200, message: 'success', data, timestamp: 1787076452 } };
}

describe('ext93a — knowledge/search API契约修正', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps real API response fields (category, highlight, author nullable, updated_at nullable)', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [
        {
          id: 2,
          title: '逆变器维护指南',
          category: 'maintenance',
          summary: '<mark>逆变器</mark>维护要点',
          author: null,
          updated_at: null,
          highlight: '<mark>逆变器</mark>维护',
        },
        {
          id: 1,
          title: '充电桩故障处理',
          category: 'troubleshooting',
          summary: '<mark>充电桩</mark>故障排查',
          author: '张三',
          updated_at: '2026-08-15T10:00:00Z',
          highlight: '<mark>充电桩</mark>故障',
        },
      ],
      total: 2,
      page: 1,
      page_size: 20,
    }));

    const res = await knowledgeApi.search('逆变器');
    expect(res.data.items).toHaveLength(2);

    // Item 1: nullable fields
    expect(res.data.items[0].id).toBe(2);
    expect(res.data.items[0].title).toBe('逆变器维护指南');
    expect(res.data.items[0].category).toBe('maintenance');
    expect(res.data.items[0].summary).toBe('<mark>逆变器</mark>维护要点');
    expect(res.data.items[0].author).toBeNull();
    expect(res.data.items[0].updatedAt).toBeNull();
    expect(res.data.items[0].highlight).toBe('<mark>逆变器</mark>维护');

    // Item 2: non-null fields
    expect(res.data.items[1].author).toBe('张三');
    expect(res.data.items[1].updatedAt).toBe('2026-08-15T10:00:00Z');
  });

  it('does not map non-existent fields (category_id, tags, view_count, status, created_at)', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 1,
        title: 'test',
        category: 'general',
        summary: 'test',
        author: null,
        updated_at: null,
        highlight: 'test',
      }],
      total: 1,
      page: 1,
      page_size: 20,
    }));

    const res = await knowledgeApi.search('test');
    const item = res.data.items[0];

    // Should not have legacy fields
    expect(item).not.toHaveProperty('categoryId');
    expect(item).not.toHaveProperty('categoryName');
    expect(item).not.toHaveProperty('tags');
    expect(item).not.toHaveProperty('viewCount');
    expect(item).not.toHaveProperty('status');
    expect(item).not.toHaveProperty('createdAt');
    expect(item).not.toHaveProperty('content');
  });

  it('maps sparse item {} with correct fallback defaults', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{}],
      total: 1,
      page: 1,
      page_size: 20,
    }));

    const res = await knowledgeApi.search('test');
    expect(res.data.items[0]).toEqual({
      id: 0,
      title: '',
      category: 'general',
      summary: '',
      author: null,
      updatedAt: null,
      highlight: '',
    });
  });

  it('handles pagination params', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [], total: 0, page: 2, page_size: 10,
    }));

    await knowledgeApi.search('test', { page: 2, page_size: 10 });

    expect(api.get).toHaveBeenCalledWith(
      '/knowledge/search?q=test&page=2&page_size=10',
    );
  });
});

describe('ext93b — inspection/templates API契约修正', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps real API response fields (item_count, device_types, target, status)', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 2,
        name: 'test',
        description: null,
        items: [],
        item_count: 0,
        device_types: [],
        target: null,
        status: 'active',
        created_at: '2026-08-14T02:45:15.734118',
        updated_at: '2026-08-14T02:45:15.734118',
      }],
      total: 1,
      page: 1,
      page_size: 50,
    }));

    const res = await inspectionTemplateApi.getList();
    expect(res.data.items).toHaveLength(1);
    expect(res.data.items[0].id).toBe(2);
    expect(res.data.items[0].name).toBe('test');
    expect(res.data.items[0].description).toBeNull();
    expect(res.data.items[0].itemCount).toBe(0);
    expect(res.data.items[0].deviceTypes).toEqual([]);
    expect(res.data.items[0].target).toBeNull();
    expect(res.data.items[0].status).toBe('active');
  });

  it('does not map non-existent fields (type, enabled)', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 1,
        name: 'template',
        description: 'desc',
        items: [],
        item_count: 3,
        device_types: ['charger_dc', 'pv_inverter'],
        target: 'station',
        status: 'active',
        created_at: '2026-08-01T00:00:00Z',
        updated_at: '2026-08-01T00:00:00Z',
      }],
      total: 1, page: 1, page_size: 50,
    }));

    const res = await inspectionTemplateApi.getList();
    const item = res.data.items[0];

    // Should not have legacy fields
    expect(item).not.toHaveProperty('type');
    expect(item).not.toHaveProperty('enabled');
  });

  it('maps template with nested items array', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 1,
        name: 'full-template',
        description: '完整模板',
        items: [
          { id: 1, name: '外观检查', expected: '无损坏' },
          { id: 2, name: '功能测试', expected: '正常', result: 'pass', note: '通过' },
        ],
        item_count: 2,
        device_types: ['charger_dc'],
        target: 'device',
        status: 'active',
        created_at: '2026-08-01T00:00:00Z',
        updated_at: '2026-08-02T00:00:00Z',
      }],
      total: 1, page: 1, page_size: 50,
    }));

    const res = await inspectionTemplateApi.getList({ page: 1, pageSize: 50 });
    expect(res.data.items[0].items).toHaveLength(2);
    expect(res.data.items[0].items[1].result).toBe('pass');
    expect(res.data.items[0].items[1].note).toBe('通过');
    expect(res.data.items[0].deviceTypes).toEqual(['charger_dc']);
    expect(res.data.items[0].target).toBe('device');
  });
});
