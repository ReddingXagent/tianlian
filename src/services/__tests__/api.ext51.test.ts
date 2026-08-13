/**
 * ext51 — notificationActionApi.readAll (POST /notifications/read-all)
 *          + notificationActionApi.readById (POST /notifications/{id}/read)
 * Cases: readAll camelCase mapping, readAll null defaults, readAll endpoint+payload,
 *        readById endpoint, readById return shape
 */
import { notificationActionApi } from '../api';

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
const mockAxios = (axios as unknown as {
  __mockInstance: { post: jest.Mock };
}).__mockInstance;

describe('ext51 — notificationActionApi.readAll + readById', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // --- readAll ---

  it('1. readAll: maps snake_case response → camelCase', async () => {
    mockAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: '全部已标记为已读',
        data: {
          marked_count: 5,
        },
        timestamp: 1786633637,
      },
    });

    const res = await notificationActionApi.readAll();
    expect(res.code).toBe(200);
    expect(res.message).toBe('全部已标记为已读');
    expect(res.data.markedCount).toBe(5);
    expect(res.timestamp).toBe(1786633637);
  });

  it('2. readAll: handles null/missing data with defaults', async () => {
    mockAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: null,
        timestamp: 0,
      },
    });

    const res = await notificationActionApi.readAll();
    expect(res.data.markedCount).toBe(0);
  });

  it('3. readAll: calls correct endpoint with POST (no body)', async () => {
    mockAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: { marked_count: 0 }, timestamp: 0 },
    });

    await notificationActionApi.readAll();

    expect(mockAxios.post).toHaveBeenCalledTimes(1);
    expect(mockAxios.post).toHaveBeenCalledWith('/notifications/read-all');
  });

  // --- readById ---

  it('4. readById: calls correct endpoint with POST', async () => {
    mockAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: null,
        timestamp: 1786633637,
      },
    });

    await notificationActionApi.readById(42);

    expect(mockAxios.post).toHaveBeenCalledTimes(1);
    expect(mockAxios.post).toHaveBeenCalledWith('/notifications/42/read');
  });

  it('5. readById: returns top-level fields (404 when not found)', async () => {
    mockAxios.post.mockResolvedValue({
      data: {
        code: 404,
        message: '消息不存在',
        data: null,
        timestamp: 1786633637,
      },
    });

    const res = await notificationActionApi.readById(999);
    expect(res.code).toBe(404);
    expect(res.message).toBe('消息不存在');
    expect(res.data).toBeNull();
    expect(res.timestamp).toBe(1786633637);
  });
});
