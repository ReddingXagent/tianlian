/**
 * api ext60 — knowledgeApi.updateArticle + updateCategory
 * PUT /knowledge/articles/{id} → KnowledgeArticleUpdated
 * PUT /knowledge/categories/{id} → KnowledgeCategoryUpdated
 */
import { knowledgeApi } from '../api';
import axios from 'axios';

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

jest.mock('expo-secureStore', () => ({
  getItemSecure: jest.fn().mockResolvedValue('mock-token'),
  setItemSecure: jest.fn().mockResolvedValue(undefined),
  deleteItemSecure: jest.fn().mockResolvedValue(undefined),
}), { virtual: true });

jest.mock('expo-secure-store', () => ({
  getItemSecure: jest.fn().mockResolvedValue('mock-token'),
  setItemSecure: jest.fn().mockResolvedValue(undefined),
  deleteItemSecure: jest.fn().mockResolvedValue(undefined),
}));

const mockedAxios = (axios as unknown as {
  __mockInstance: {
    get: jest.Mock;
    post: jest.Mock;
    put: jest.Mock;
    delete: jest.Mock;
  },
}).__mockInstance;

// =====================
// knowledgeApi.updateArticle
// =====================
describe('knowledgeApi.updateArticle (ext60)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('PUT /knowledge/articles/{id} — maps snake_case response to camelCase', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 3,
          title: 'Updated Title',
          content: 'Updated content',
          category: 'general',
          tags: null,
          view_count: 5,
          published: true,
          updated_at: '2026-08-14T00:20:01Z',
          author_id: 1,
        },
        timestamp: 1786638001,
      },
    });

    const res = await knowledgeApi.updateArticle(3, { title: 'Updated Title', content: 'Updated content' });
    expect(res.code).toBe(200);
    expect(res.data.id).toBe(3);
    expect(res.data.title).toBe('Updated Title');
    expect(res.data.content).toBe('Updated content');
    expect(res.data.category).toBe('general');
    expect(res.data.tags).toBeNull();
    expect(res.data.viewCount).toBe(5);
    expect(res.data.published).toBe(true);
    expect(res.data.updatedAt).toBe('2026-08-14T00:20:01Z');
    expect(res.data.authorId).toBe(1);
  });

  it('null/missing defaults: all fields default on empty data', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {}, timestamp: 0 },
    });

    const res = await knowledgeApi.updateArticle(1, { title: 'x' });
    expect(res.data.id).toBe(0);
    expect(res.data.title).toBe('');
    expect(res.data.content).toBe('');
    expect(res.data.tags).toBeNull();
    expect(res.data.viewCount).toBe(0);
    expect(res.data.published).toBe(false);
    expect(res.data.updatedAt).toBe('');
    expect(res.data.authorId).toBe(0);
  });

  it('endpoint + payload: correct URL and camel→snake body', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 1 }, timestamp: 0 },
    });

    await knowledgeApi.updateArticle(5, {
      title: 'New Title',
      content: 'New Content',
      categoryId: 2,
      tags: ['a', 'b'],
    });

    expect(mockedAxios.put).toHaveBeenCalledWith('/knowledge/articles/5', {
      title: 'New Title',
      content: 'New Content',
      category_id: 2,
      tags: ['a', 'b'],
    });
  });

  it('partial update: only sent fields in payload', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 1 }, timestamp: 0 },
    });

    await knowledgeApi.updateArticle(1, { title: 'Only Title' });

    const payload = mockedAxios.put.mock.calls[0][1] as Record<string, unknown>;
    expect(payload.title).toBe('Only Title');
    expect(payload.content).toBeUndefined();
    expect(payload.category_id).toBeUndefined();
    expect(payload.tags).toBeUndefined();
  });
});

// =====================
// knowledgeApi.updateCategory
// =====================
describe('knowledgeApi.updateCategory (ext60)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('PUT /knowledge/categories/{id} — maps snake_case response to camelCase', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: {
        code: 200,
        message: '分类更新成功',
        data: {
          id: 1,
          name: 'Updated Cat',
          icon: 'icon-cat',
          sort_order: 3,
          description: 'Updated desc',
          created_at: '2026-08-13T23:54:42+08:00',
          updated_at: '2026-08-14T00:19:00+08:00',
        },
        timestamp: 1786637962,
      },
    });

    const res = await knowledgeApi.updateCategory(1, { name: 'Updated Cat', description: 'Updated desc' });
    expect(res.code).toBe(200);
    expect(res.data.id).toBe(1);
    expect(res.data.name).toBe('Updated Cat');
    expect(res.data.icon).toBe('icon-cat');
    expect(res.data.sortOrder).toBe(3);
    expect(res.data.description).toBe('Updated desc');
    expect(res.data.createdAt).toBe('2026-08-13T23:54:42+08:00');
    expect(res.data.updatedAt).toBe('2026-08-14T00:19:00+08:00');
  });

  it('null updatedAt preserved', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: {
          id: 1,
          name: 'Cat',
          icon: '',
          sort_order: 0,
          description: '',
          created_at: '2026-01-01',
          updated_at: null,
        },
        timestamp: 0,
      },
    });

    const res = await knowledgeApi.updateCategory(1, {});
    expect(res.data.updatedAt).toBeNull();
  });

  it('null/missing defaults: all fields default on empty data', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {}, timestamp: 0 },
    });

    const res = await knowledgeApi.updateCategory(1, {});
    expect(res.data.id).toBe(0);
    expect(res.data.name).toBe('');
    expect(res.data.icon).toBe('');
    expect(res.data.sortOrder).toBe(0);
    expect(res.data.description).toBe('');
    expect(res.data.createdAt).toBe('');
    expect(res.data.updatedAt).toBeNull();
  });

  it('endpoint + payload: correct URL and camel→snake body', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 1 }, timestamp: 0 },
    });

    await knowledgeApi.updateCategory(7, {
      name: 'New Name',
      sortOrder: 5,
      description: 'New Desc',
    });

    expect(mockedAxios.put).toHaveBeenCalledWith('/knowledge/categories/7', {
      name: 'New Name',
      sort_order: 5,
      description: 'New Desc',
    });
  });
});
