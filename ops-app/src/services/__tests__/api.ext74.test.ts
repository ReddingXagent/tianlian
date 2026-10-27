/**
 * api ext74 — coverage: mapper fallback branch push
 * Tests `??` fallback paths by passing items with null/undefined fields.
 * Targets uncovered binary-expr branches in:
 *   authApi.getProfile (lines 225-232)
 *   deviceApi.getHealthList (lines 484-490)
 *   knowledgeApi.getArticles (lines 616-628)
 *   knowledgeApi.getFaq (lines 649-655)
 *   knowledgeApi.getFaqCategories (lines 667-673)
 *   knowledgeApi.getCategories (lines 685-692)
 *   knowledgeApi.search (lines 706-718)
 */
import {
  authApi,
  deviceApi,
  knowledgeApi,
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

// F1205: any收窄 — mock工厂返回结构已知, 用具体Mock接口替代any
const mockAxios = (axios as unknown as { __mockInstance: { get: jest.Mock; post: jest.Mock; put: jest.Mock; delete: jest.Mock; patch: jest.Mock } }).__mockInstance;

describe('ext74 — mapper fallback branch coverage', () => {

  beforeEach(() => {
    jest.clearAllMocks();
  });

  // authApi.getProfile — all fields null/missing → fallback
  it('getProfile: fields null → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await authApi.getProfile();
    expect(res.data).toEqual({
      id: 0,
      username: '',
      realName: '',
      role: '',
      permissions: [],
      teamType: null,
      teamId: null,
    });
  });

  // deviceApi.getHealthList — item with all null fields → fallback
  it('getHealthList: empty-item fields → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: { items: [{}], total: 1, page: 1, page_size: 1 },
      },
    });
    const res = await deviceApi.getHealthList();
    expect(res.data.items[0]).toEqual({
      id: 0,
      code: '',
      name: '',
      type: '',
      healthScore: 0,
      status: '',
    });
  });

  // deviceApi.getHealthList — data null → empty items + fallback
  it('getHealthList: data null → fallback total/page/pageSize', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await deviceApi.getHealthList();
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(0);
  });

  // knowledgeApi.getArticles — item with all null fields → fallback
  it('getArticles: empty-item fields → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: { items: [{}], total: 1, page: 1, page_size: 1 },
      },
    });
    const res = await knowledgeApi.getArticles();
    const item = res.data.items[0];
    expect(item).toEqual({
      id: 0,
      title: '',
      content: '',
      summary: '',
      categoryId: 0,
      categoryName: undefined,
      tags: [],
      author: '',
      viewCount: 0,
      status: 'draft',
      createdAt: '',
      updatedAt: '',
    });
  });

  // knowledgeApi.getArticles — data null → fallback total/page/pageSize
  it('getArticles: data null → fallback pagination', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await knowledgeApi.getArticles();
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  // knowledgeApi.getFaq — empty-item fields → fallback
  it('getFaq: empty-item fields → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: [{}] },
    });
    const res = await knowledgeApi.getFaq();
    expect(res.data[0]).toEqual({
      id: 0,
      question: '',
      answer: '',
      categoryId: undefined,
      sortOrder: undefined,
    });
  });

  // knowledgeApi.getFaqCategories — empty-item fields → fallback
  it('getFaqCategories: empty-item fields → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: [{}] },
    });
    const res = await knowledgeApi.getFaqCategories();
    expect(res.data[0]).toEqual({
      id: 0,
      name: '',
      description: undefined,
      faqCount: undefined,
      sortOrder: undefined,
    });
  });

  // knowledgeApi.getCategories — empty-item fields → fallback
  it('getCategories: empty-item fields → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: [{}] },
    });
    const res = await knowledgeApi.getCategories();
    expect(res.data[0]).toEqual({
      id: 0,
      name: '',
      description: '',
      articleCount: 0,
      createdAt: '',
      updatedAt: '',
    });
  });

  // knowledgeApi.search — empty-item fields → fallback
  it('search: empty-item fields → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: { items: [{}], total: 1, page: 1, page_size: 1 },
      },
    });
    const res = await knowledgeApi.search('test');
    const item = res.data.items[0];
    expect(item).toEqual({
      id: 0,
      title: '',
      category: 'general',
      summary: '',
      author: null,
      updatedAt: null,
      highlight: '',
    });
  });

  // knowledgeApi.search — data null → fallback pagination
  it('search: data null → fallback pagination', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await knowledgeApi.search('test');
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  // knowledgeApi.getArticles — params with null page/page_size → fallback
  it('getArticles: params null fields → default page/pageSize', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [] } },
    });
    await knowledgeApi.getArticles({ page: undefined, page_size: undefined });
    // Verify query string uses defaults
    expect(mockAxios.get).toHaveBeenCalledWith(
      expect.stringContaining('page=1&page_size=20'),
    );
  });

  // knowledgeApi.search — params null → default page/pageSize
  it('search: no params → default page=1 page_size=20 in query', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [] } },
    });
    await knowledgeApi.search('kw');
    expect(mockAxios.get).toHaveBeenCalledWith(
      expect.stringContaining('page=1&page_size=20'),
    );
  });
});
