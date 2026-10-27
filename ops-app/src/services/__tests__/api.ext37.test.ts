/**
 * api ext37 — Auth Refresh Token API (POST /auth/refresh)
 * Target: token refresh endpoint returning { access_token, token_type, expires_in }
 */
import { authApi } from '../api';

// Mock expo-secure-store before axios mock
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

// Import mocked axios
import axios from 'axios';
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('authApi.refreshToken (POST /auth/refresh)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should map snake_case response to camelCase', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          access_token: 'new-token-abc123',
          token_type: 'bearer',
          expires_in: 86400,
        },
        timestamp: 1786571476,
      },
    });

    const res = await authApi.refreshToken();
    expect(res.data.accessToken).toBe('new-token-abc123');
    expect(res.data.tokenType).toBe('bearer');
    expect(res.data.expiresIn).toBe(86400);
  });

  it('should handle null data field with defaults', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: null,
        timestamp: 1786571476,
      },
    });

    const res = await authApi.refreshToken();
    expect(res.data.accessToken).toBe('');
    expect(res.data.tokenType).toBe('bearer');
    expect(res.data.expiresIn).toBe(0);
  });

  it('should handle missing fields with defaults', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          access_token: 'partial-token',
        },
        timestamp: 1786571476,
      },
    });

    const res = await authApi.refreshToken();
    expect(res.data.accessToken).toBe('partial-token');
    expect(res.data.tokenType).toBe('bearer');
    expect(res.data.expiresIn).toBe(0);
  });

  it('should call POST /auth/refresh', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { access_token: 't', token_type: 'bearer', expires_in: 3600 },
        timestamp: 0,
      },
    });

    await authApi.refreshToken();
    expect(mockedAxios.post).toHaveBeenCalledWith('/auth/refresh');
  });

  it('should preserve top-level response fields', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { access_token: 'tok', token_type: 'bearer', expires_in: 7200 },
        timestamp: 1786571476,
      },
    });

    const res = await authApi.refreshToken();
    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
    expect(res.timestamp).toBe(1786571476);
  });
});
