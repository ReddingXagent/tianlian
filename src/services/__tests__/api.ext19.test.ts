/**
 * api ext19 — /knowledge/articles, /knowledge/categories, /knowledge/search 三新端点对接测试
 */
import { knowledgeApi } from '../api';

jest.mock('axios', () => {
  const mockInstance = {
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  };
  return {
    create: jest.fn(() => mockInstance),
  };
});

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// The mock create() returns the same instance each time.
const axios = require('axios');
const mockInstance = axios.create();

describe('knowledgeApi (ext19)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('getArticles', () => {
    it('should fetch articles with default pagination', async () => {
      mockInstance.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              {
                id: 1,
                title: '充电桩维护指南',
                content: '定期检查连接器...',
                summary: '维护指南摘要',
                category_id: 1,
                category_name: '维护',
                tags: ['充电桩', '维护'],
                author: 'admin',
                view_count: 42,
                status: 'published',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-02T00:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
          timestamp: 1786458972,
        },
      });

      const res = await knowledgeApi.getArticles();

      expect(mockInstance.get).toHaveBeenCalledWith('/knowledge/articles');
      expect(res.data.items).toHaveLength(1);
      expect(res.data.items[0].id).toBe(1);
      expect(res.data.items[0].title).toBe('充电桩维护指南');
      expect(res.data.items[0].categoryId).toBe(1);
      expect(res.data.items[0].categoryName).toBe('维护');
      expect(res.data.items[0].tags).toEqual(['充电桩', '维护']);
      expect(res.data.items[0].viewCount).toBe(42);
      expect(res.data.items[0].status).toBe('published');
    });

    it('should pass pagination params', async () => {
      mockInstance.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: { items: [], total: 0, page: 2, page_size: 5 },
          timestamp: 0,
        },
      });

      await knowledgeApi.getArticles({ page: 2, page_size: 5 });

      expect(mockInstance.get).toHaveBeenCalledWith('/knowledge/articles?page=2&page_size=5');
    });

    it('should handle empty response', async () => {
      mockInstance.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: { items: [], total: 0, page: 1, page_size: 20 },
          timestamp: 0,
        },
      });

      const res = await knowledgeApi.getArticles();

      expect(res.data.items).toHaveLength(0);
      expect(res.data.total).toBe(0);
    });
  });

  describe('getCategories', () => {
    it('should fetch categories as array', async () => {
      mockInstance.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: [
            {
              id: 1,
              name: '运维手册',
              description: '日常运维文档',
              article_count: 5,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
            {
              id: 2,
              name: '故障案例',
              description: '历史故障记录',
              article_count: 3,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
          ],
          timestamp: 0,
        },
      });

      const res = await knowledgeApi.getCategories();

      expect(mockInstance.get).toHaveBeenCalledWith('/knowledge/categories');
      expect(res.data).toHaveLength(2);
      expect(res.data[0].id).toBe(1);
      expect(res.data[0].name).toBe('运维手册');
      expect(res.data[0].articleCount).toBe(5);
      expect(res.data[1].name).toBe('故障案例');
    });

    it('should handle empty array response', async () => {
      mockInstance.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: [],
          timestamp: 0,
        },
      });

      const res = await knowledgeApi.getCategories();

      expect(res.data).toHaveLength(0);
    });
  });

  describe('search', () => {
    it('should search articles by keyword', async () => {
      mockInstance.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              {
                id: 10,
                title: '逆变器故障处理',
                content: '当逆变器报警...',
                summary: '逆变器故障',
                category_id: 2,
                tags: ['逆变器'],
                author: 'engineer1',
                view_count: 10,
                status: 'published',
                created_at: '2026-03-01T00:00:00Z',
                updated_at: '2026-03-01T00:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
          timestamp: 0,
        },
      });

      const res = await knowledgeApi.search('逆变器');

      expect(mockInstance.get).toHaveBeenCalledWith('/knowledge/search?q=%E9%80%86%E5%8F%98%E5%99%A8&page=1&page_size=20');
      expect(res.data.items).toHaveLength(1);
      expect(res.data.items[0].title).toBe('逆变器故障处理');
    });

    it('should encode special characters in keyword', async () => {
      mockInstance.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: { items: [], total: 0, page: 1, page_size: 20 },
          timestamp: 0,
        },
      });

      await knowledgeApi.search('充电 & 维护');

      expect(mockInstance.get).toHaveBeenCalledWith(
        '/knowledge/search?q=%E5%85%85%E7%94%B5%20%26%20%E7%BB%B4%E6%8A%A4&page=1&page_size=20',
      );
    });
  });
});
