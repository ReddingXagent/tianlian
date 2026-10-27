import { healingExecutionApi } from '../api';

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

describe('healingExecutionApi actions (ext45 — POST /healing/executions/{id}/{action})', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('retry should POST to /healing/executions/{id}/retry', async () => {
    const mockResponse = {
      code: 200,
      message: 'success',
      data: { id: 1, status: 'retrying' },
      timestamp: 1786630000,
    };
    (mockAxios.post as jest.Mock).mockResolvedValue({ data: mockResponse });

    const result = await healingExecutionApi.retry(1);

    expect(mockAxios.post).toHaveBeenCalledWith('/healing/executions/1/retry');
    expect(result.code).toBe(200);
    expect(result.data).toEqual({ id: 1, status: 'retrying' });
  });

  it('retry should handle business error (执行记录不存在)', async () => {
    const mockResponse = {
      code: 400,
      message: '执行记录#1不存在',
      data: null,
      timestamp: 1786630001,
    };
    (mockAxios.post as jest.Mock).mockResolvedValue({ data: mockResponse });

    const result = await healingExecutionApi.retry(1);

    expect(result.code).toBe(400);
    expect(result.message).toBe('执行记录#1不存在');
  });

  it('approve should POST to /healing/executions/{id}/approve', async () => {
    const mockResponse = {
      code: 200,
      message: 'success',
      data: { id: 1, status: 'approved' },
      timestamp: 1786630000,
    };
    (mockAxios.post as jest.Mock).mockResolvedValue({ data: mockResponse });

    const result = await healingExecutionApi.approve(42);

    expect(mockAxios.post).toHaveBeenCalledWith('/healing/executions/42/approve');
    expect(result.code).toBe(200);
  });

  it('reject should POST with reason body', async () => {
    const mockResponse = {
      code: 200,
      message: 'success',
      data: { id: 1, status: 'rejected' },
      timestamp: 1786630000,
    };
    (mockAxios.post as jest.Mock).mockResolvedValue({ data: mockResponse });

    const result = await healingExecutionApi.reject(1, 'false positive');

    expect(mockAxios.post).toHaveBeenCalledWith('/healing/executions/1/reject', {
      reason: 'false positive',
    });
    expect(result.code).toBe(200);
  });

  it('reject should work without reason', async () => {
    const mockResponse = {
      code: 200,
      message: 'success',
      data: { id: 1, status: 'rejected' },
      timestamp: 1786630000,
    };
    (mockAxios.post as jest.Mock).mockResolvedValue({ data: mockResponse });

    await healingExecutionApi.reject(1);

    expect(mockAxios.post).toHaveBeenCalledWith('/healing/executions/1/reject', {
      reason: undefined,
    });
  });
});
