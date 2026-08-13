/**
 * api ext47 — GET /knowledge/faq 知识库FAQ列表对接测试
 */
import { knowledgeApi } from '../api';

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// Mock axios
jest.mock('axios', () => {
  const mockAxios: Record<string, any> = {
    create: jest.fn(() => mockAxios),
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    defaults: { headers: { common: {} } },
  };
  return mockAxios;
});

import axios from 'axios';
const mockAxios = axios as jest.Mocked<typeof axios>;

describe('ext47 — knowledgeApi.getFaq (GET /knowledge/faq)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case fields to camelCase', async () => {
    (mockAxios as any).get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: [
          {
            id: 1,
            question: '如何重置充电桩?',
            answer: '请参考操作手册第3章。',
            category_id: 5,
            sort_order: 10,
          },
          {
            id: 2,
            question: '报警如何处理?',
            answer: '在告警页面点击处理按钮。',
            category_id: 3,
            sort_order: 20,
          },
        ],
        timestamp: 1700000000,
      },
    });
    const res = await knowledgeApi.getFaq();

    expect((mockAxios as any).get).toHaveBeenCalledWith('/knowledge/faq');
    expect(res.data).toHaveLength(2);
    expect(res.data[0]).toEqual({
      id: 1,
      question: '如何重置充电桩?',
      answer: '请参考操作手册第3章。',
      categoryId: 5,
      sortOrder: 10,
    });
    expect(res.data[1]).toEqual({
      id: 2,
      question: '报警如何处理?',
      answer: '在告警页面点击处理按钮。',
      categoryId: 3,
      sortOrder: 20,
    });
  });

  it('handles empty list', async () => {
    (mockAxios as any).get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: [], timestamp: 1700000000 },
    });
    const res = await knowledgeApi.getFaq();
    expect(res.data).toEqual([]);
  });

  it('handles null/missing fields with defaults', async () => {
    (mockAxios as any).get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: [{ id: 1 }],
        timestamp: 1700000000,
      },
    });
    const res = await knowledgeApi.getFaq();
    expect(res.data).toHaveLength(1);
    expect(res.data[0]).toEqual({
      id: 1,
      question: '',
      answer: '',
      categoryId: undefined,
      sortOrder: undefined,
    });
  });

  it('handles data as object with items property', async () => {
    (mockAxios as any).get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { items: [{ id: 3, question: 'Q3', answer: 'A3' }] },
        timestamp: 1700000000,
      },
    });
    const res = await knowledgeApi.getFaq();
    expect(res.data).toHaveLength(1);
    expect(res.data[0].id).toBe(3);
  });

  it('calls correct endpoint', async () => {
    (mockAxios as any).get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: [], timestamp: 1700000000 },
    });
    await knowledgeApi.getFaq();
    expect((mockAxios as any).get).toHaveBeenCalledTimes(1);
    expect((mockAxios as any).get).toHaveBeenCalledWith('/knowledge/faq');
  });
});
