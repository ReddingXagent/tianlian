/**
 * api ext59 — knowledgeApi.createArticle + createCategory + createFaq
 * POST /knowledge/articles → KnowledgeArticleCreated
 * POST /knowledge/categories → KnowledgeCategoryCreated
 * POST /knowledge/faq → KnowledgeFaqCreated
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

jest.mock('expo-secure-store', () => ({
  getItemSecure: jest.fn().mockResolvedValue('mock-token'),
  setItemSecure: jest.fn().mockResolvedValue(undefined),
  deleteItemSecure: jest.fn().mockResolvedValue(undefined),
}));

const mockedAxios = axios.__mockInstance as jest.Mocked<{
  get: jest.ReturnMock;
  post: jest.ReturnMock;
  put: jest.ReturnMock;
  delete: jest.ReturnMock;
}>;

// =====================
// knowledgeApi.createArticle
// =====================
describe('knowledgeApi.createArticle (ext59)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('POST /knowledge/articles — maps snake_case response to camelCase', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 5,
          title: 'Guide',
          content: 'Body',
          category: 'general',
          tags: ['tag1'],
          view_count: 0,
          published: true,
          created_at: '2026-08-14T00:10:45Z',
          author_id: 1,
        },
        timestamp: 1786637445,
      },
    });

    const res = await knowledgeApi.createArticle({
      title: 'Guide',
      content: 'Body',
      categoryId: 1,
      tags: ['tag1'],
    });

    expect(res.data.id).toBe(5);
    expect(res.data.title).toBe('Guide');
    expect(res.data.category).toBe('general');
    expect(res.data.viewCount).toBe(0);
    expect(res.data.published).toBe(true);
    expect(res.data.authorId).toBe(1);
    expect(res.data.createdAt).toBe('2026-08-14T00:10:45Z');

    // Verify request payload
    expect(mockedAxios.post).toHaveBeenCalledWith('/knowledge/articles', {
      title: 'Guide',
      content: 'Body',
      category_id: 1,
      tags: ['tag1'],
    });
  });

  it('handles null/missing fields with defaults', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {},
        timestamp: 0,
      },
    });

    const res = await knowledgeApi.createArticle({ title: 'T', content: 'C' });

    expect(res.data.id).toBe(0);
    expect(res.data.title).toBe('');
    expect(res.data.tags).toBeNull();
    expect(res.data.published).toBe(false);
    expect(res.data.authorId).toBe(0);
  });
});

// =====================
// knowledgeApi.createCategory
// =====================
describe('knowledgeApi.createCategory (ext59)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('POST /knowledge/categories — maps response + sends name via query param', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 3,
          name: 'Tips',
          icon: '',
          sort_order: 2,
          description: 'desc',
          created_at: '2026-08-14T00:00:00Z',
        },
        timestamp: 0,
      },
    });

    const res = await knowledgeApi.createCategory({
      name: 'Tips',
      sortOrder: 2,
      description: 'desc',
    });

    expect(res.data.id).toBe(3);
    expect(res.data.name).toBe('Tips');
    expect(res.data.sortOrder).toBe(2);
    expect(res.data.icon).toBe('');
    expect(res.data.description).toBe('desc');

    // Verify name sent as query param, empty body
    expect(mockedAxios.post).toHaveBeenCalledWith(
      '/knowledge/categories',
      {},
      { params: { name: 'Tips', sort_order: 2, description: 'desc' } }
    );
  });

  it('handles missing optional fields', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {},
        timestamp: 0,
      },
    });

    const res = await knowledgeApi.createCategory({ name: 'Cat' });

    expect(res.data.id).toBe(0);
    expect(res.data.sortOrder).toBe(0);
    expect(res.data.icon).toBe('');
  });
});

// =====================
// knowledgeApi.createFaq
// =====================
describe('knowledgeApi.createFaq (ext59)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('POST /knowledge/faq — maps snake_case response to camelCase', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 7,
          question: 'What?',
          answer: 'Yes',
          category: 'general',
          tags: null,
          views: 0,
          helpful_count: 0,
          created_at: '2026-08-14T00:10:58Z',
        },
        timestamp: 0,
      },
    });

    const res = await knowledgeApi.createFaq({
      question: 'What?',
      answer: 'Yes',
      category: 'general',
    });

    expect(res.data.id).toBe(7);
    expect(res.data.question).toBe('What?');
    expect(res.data.category).toBe('general');
    expect(res.data.tags).toBeNull();
    expect(res.data.views).toBe(0);
    expect(res.data.helpfulCount).toBe(0);

    // Verify request payload
    expect(mockedAxios.post).toHaveBeenCalledWith('/knowledge/faq', {
      question: 'What?',
      answer: 'Yes',
      category: 'general',
    });
  });

  it('handles empty data object', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {},
        timestamp: 0,
      },
    });

    const res = await knowledgeApi.createFaq({
      question: 'Q',
      answer: 'A',
      category: 'cat',
    });

    expect(res.data.id).toBe(0);
    expect(res.data.question).toBe('');
    expect(res.data.helpfulCount).toBe(0);
    expect(res.data.views).toBe(0);
  });
});
