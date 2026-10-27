import { knowledgeApi } from '../api';

// Mock axios
jest.mock('axios', () => {
  const mockAxios: Record<string, any> = {
    create: jest.fn(() => mockAxios),
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
  return mockAxios;
});

// Mock SecureStore
jest.mock('expo-secure-store', () => ({
  getItem: jest.fn().mockResolvedValue('mock-token'),
  setItem: jest.fn(),
  deleteItem: jest.fn(),
}));

import axios from 'axios';
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('knowledgeApi.getCategories', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case fields to camelCase', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: [
          {
            id: 1,
            name: '运维手册',
            description: '日常运维指南',
            article_count: 15,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-06-01T00:00:00Z',
          },
          {
            id: 2,
            name: '故障案例',
            description: '历史故障记录',
            article_count: 8,
            created_at: '2025-02-01T00:00:00Z',
            updated_at: '2025-07-01T00:00:00Z',
          },
        ],
        timestamp: 1786486905,
      },
    });

    const res = await knowledgeApi.getCategories();
    expect(res.code).toBe(200);
    expect(res.data).toHaveLength(2);
    expect(res.data[0]).toEqual({
      id: 1,
      name: '运维手册',
      description: '日常运维指南',
      articleCount: 15,
      createdAt: '2025-01-01T00:00:00Z',
      updatedAt: '2025-06-01T00:00:00Z',
    });
    expect(res.data[1].articleCount).toBe(8);
    expect(res.data[1].name).toBe('故障案例');
  });

  it('handles empty data array', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: [],
        timestamp: 1786486905,
      },
    });

    const res = await knowledgeApi.getCategories();
    expect(res.data).toEqual([]);
  });

  it('handles null data gracefully', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: null,
        timestamp: 1786486905,
      },
    });

    const res = await knowledgeApi.getCategories();
    expect(res.data).toEqual([]);
  });

  it('provides defaults for missing fields', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: [{}],
        timestamp: 1786486905,
      },
    });

    const res = await knowledgeApi.getCategories();
    expect(res.data).toHaveLength(1);
    expect(res.data[0]).toEqual({
      id: 0,
      name: '',
      description: '',
      articleCount: 0,
      createdAt: '',
      updatedAt: '',
    });
  });

  it('handles data wrapped in items property', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            { id: 5, name: 'FAQ', description: '常见问题', article_count: 3, created_at: '2025-03-01', updated_at: '2025-05-01' },
          ],
        },
        timestamp: 1786486905,
      },
    });

    const res = await knowledgeApi.getCategories();
    expect(res.data).toHaveLength(1);
    expect(res.data[0].id).toBe(5);
    expect(res.data[0].articleCount).toBe(3);
  });

  it('calls correct endpoint', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: { code: 200, message: 'success', data: [], timestamp: 0 },
    });

    await knowledgeApi.getCategories();
    expect(mockedAxios.get).toHaveBeenCalledWith('/knowledge/categories');
  });
});
