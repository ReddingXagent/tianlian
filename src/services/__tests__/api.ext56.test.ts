/**
 * api ext56 — apiKeyApi.getUsage + apiKeyApi.rotate + apiKeyApi.delete
 * GET /api-keys/{id}/usage → ApiKeyUsage(keyId/periodDays/totalRequests/avgDurationMs)
 * POST /api-keys/{id}/rotate → ApiKeyRotated(id/apiKey/keyPrefix)
 * DELETE /api-keys/{id} → ApiResponse<null>
 */
import { apiKeyApi } from '../api';
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

describe('apiKeyApi.getUsage (ext56)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case to camelCase correctly', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          key_id: 1,
          period_days: 7,
          total_requests: 142,
          avg_duration_ms: 35,
        },
        timestamp: 1786635981,
      },
    });

    const res = await apiKeyApi.getUsage(1);

    expect(res.code).toBe(200);
    expect(res.data.keyId).toBe(1);
    expect(res.data.periodDays).toBe(7);
    expect(res.data.totalRequests).toBe(142);
    expect(res.data.avgDurationMs).toBe(35);
  });

  it('applies null/missing defaults', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {},
        timestamp: 1786635981,
      },
    });

    const res = await apiKeyApi.getUsage(1);

    expect(res.data.keyId).toBe(0);
    expect(res.data.periodDays).toBe(0);
    expect(res.data.totalRequests).toBe(0);
    expect(res.data.avgDurationMs).toBe(0);
  });

  it('calls correct endpoint', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {}, timestamp: 0 },
    });

    await apiKeyApi.getUsage(1);

    expect(mockedAxios.get).toHaveBeenCalledWith('/api-keys/1/usage');
  });
});

describe('apiKeyApi.rotate (ext56)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case to camelCase correctly', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'API Key rotated',
        data: {
          id: 1,
          api_key: 'tl_newKey1234567890',
          key_prefix: 'tl_newKey1',
        },
        timestamp: 1786635981,
      },
    });

    const res = await apiKeyApi.rotate(1);

    expect(res.code).toBe(200);
    expect(res.message).toBe('API Key rotated');
    expect(res.data.id).toBe(1);
    expect(res.data.apiKey).toBe('tl_newKey1234567890');
    expect(res.data.keyPrefix).toBe('tl_newKey1');
  });

  it('applies null/missing defaults', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {},
        timestamp: 0,
      },
    });

    const res = await apiKeyApi.rotate(1);

    expect(res.data.id).toBe(0);
    expect(res.data.apiKey).toBe('');
    expect(res.data.keyPrefix).toBe('');
  });

  it('calls correct endpoint', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {}, timestamp: 0 },
    });

    await apiKeyApi.rotate(1);

    expect(mockedAxios.post).toHaveBeenCalledWith('/api-keys/1/rotate');
  });
});

describe('apiKeyApi.delete (ext56)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('calls correct endpoint and returns null data', async () => {
    mockedAxios.delete.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'API Key deleted',
        data: null,
        timestamp: 1786635981,
      },
    });

    const res = await apiKeyApi.delete(1);

    expect(mockedAxios.delete).toHaveBeenCalledWith('/api-keys/1');
    expect(res.code).toBe(200);
    expect(res.data).toBeNull();
  });

  it('handles top-level response', async () => {
    mockedAxios.delete.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: null,
        timestamp: 0,
      },
    });

    const res = await apiKeyApi.delete(1);

    expect(res.code).toBe(200);
    expect(res.data).toBeNull();
  });
});
