/**
 * ext53 — knowledgeApi.getFaqCategories (GET /knowledge/faq/categories)
 * Cases: camelCase mapping, empty array, null/missing defaults,
 *        endpoint+payload verification, top-level response shape
 */
import { knowledgeApi } from '../api';

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
const mockedAxios = axios as unknown as { __mockInstance: { get: jest.Mock; post: jest.Mock; put: jest.Mock; delete: jest.Mock } };
const mockApi = mockedAxios.__mockInstance;

describe('ext53 — knowledgeApi.getFaqCategories', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('1) maps snake_case to camelCase', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: [
          { id: 1, name: '常见问题', description: '常见操作问题', faq_count: 5, sort_order: 1 },
          { id: 2, name: '故障排查', description: '故障诊断指南', faq_count: 3, sort_order: 2 },
        ],
        timestamp: 1700000000,
      },
    });

    const res = await knowledgeApi.getFaqCategories();
    expect(res.data).toHaveLength(2);
    expect(res.data[0]).toEqual({
      id: 1,
      name: '常见问题',
      description: '常见操作问题',
      faqCount: 5,
      sortOrder: 1,
    });
    expect(res.data[1]).toEqual({
      id: 2,
      name: '故障排查',
      description: '故障诊断指南',
      faqCount: 3,
      sortOrder: 2,
    });
  });

  it('2) handles empty array', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: [],
        timestamp: 1700000000,
      },
    });

    const res = await knowledgeApi.getFaqCategories();
    expect(res.data).toEqual([]);
    expect(res.code).toBe(200);
  });

  it('3) handles null/missing fields with defaults', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: [
          { id: 1, name: 'Only Name' },
        ],
        timestamp: 1700000000,
      },
    });

    const res = await knowledgeApi.getFaqCategories();
    expect(res.data[0]).toEqual({
      id: 1,
      name: 'Only Name',
      description: undefined,
      faqCount: undefined,
      sortOrder: undefined,
    });
  });

  it('4) calls correct endpoint with GET method', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: [],
        timestamp: 1700000000,
      },
    });

    await knowledgeApi.getFaqCategories();
    expect(mockApi.get).toHaveBeenCalledTimes(1);
    expect(mockApi.get).toHaveBeenCalledWith('/knowledge/faq/categories');
  });

  it('5) preserves top-level response fields', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: [{ id: 1, name: 'Cat1' }],
        timestamp: 1700000000,
      },
    });

    const res = await knowledgeApi.getFaqCategories();
    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
    expect(res.timestamp).toBe(1700000000);
  });
});
