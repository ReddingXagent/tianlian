/**
 * api.ext.test.ts — 覆盖请求拦截器内部逻辑 + 401响应拦截器 catch 分支
 *
 * 目标行:
 *  - L41-51: request interceptor (token注入 + SecureStore异常静默)
 *  - L72: response interceptor SecureStore.deleteItemAsync catch
 *  - request reject handler
 */
import axios from 'axios';
import {
  setUnauthorizedHandler,
} from '../api';

// Mock axios and SecureStore at module level
jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return {
    __esModule: true,
    default: {
      create: jest.fn(() => mockInstance),
    },
  };
});

const mockGetItem = jest.fn();
const mockSetItem = jest.fn();
const mockDeleteItem = jest.fn();

jest.mock('expo-secure-store', () => ({
  __esModule: true,
  getItemAsync: (...args: any[]) => mockGetItem(...args),
  setItemAsync: (...args: any[]) => mockSetItem(...args),
  deleteItemAsync: (...args: any[]) => mockDeleteItem(...args),
}));

const mockAxiosInstance = (axios as any).create();

// Capture interceptor callbacks at module level (before clearAllMocks runs)
const _requestCalls = (mockAxiosInstance.interceptors.request.use as jest.Mock).mock.calls;
const _responseCalls = (mockAxiosInstance.interceptors.response.use as jest.Mock).mock.calls;

function getRequestInterceptor() {
  const [onFulfilled, onRejected] = _requestCalls[0] || [undefined, undefined];
  return [onFulfilled, onRejected] as const;
}

function getResponseInterceptor() {
  const [onFulfilled, onRejected] = _responseCalls[0] || [undefined, undefined];
  return [onFulfilled, onRejected] as const;
}

describe('API Service — interceptor internal logic', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetItem.mockResolvedValue(null);
    mockDeleteItem.mockResolvedValue(undefined);
  });

  describe('request interceptor (token injection)', () => {

    it('injects Authorization header when token exists and config.headers present', async () => {
      mockGetItem.mockResolvedValue('jwt-token-123');
      const [onFulfilled] = getRequestInterceptor();
      const config = { headers: {} };
      const result = await onFulfilled(config);
      expect(result.headers.Authorization).toBe('Bearer jwt-token-123');
    });

    it('does not set Authorization when token is null', async () => {
      mockGetItem.mockResolvedValue(null);
      const [onFulfilled] = getRequestInterceptor();
      const config = { headers: {} };
      const result = await onFulfilled(config);
      expect(result.headers.Authorization).toBeUndefined();
    });

    it('does not crash when config.headers is undefined even if token exists', async () => {
      mockGetItem.mockResolvedValue('tok');
      const [onFulfilled] = getRequestInterceptor();
      const config = { headers: undefined };
      // Should not throw — the `if (token && config.headers)` guard prevents it
      const result = await onFulfilled(config);
      expect(result).toBe(config);
    });

    it('silently handles SecureStore.getItemAsync rejection and returns config', async () => {
      mockGetItem.mockRejectedValue(new Error('secure store boom'));
      const [onFulfilled] = getRequestInterceptor();
      const config = { headers: {} };
      const result = await onFulfilled(config);
      expect(result).toBe(config);
      // Authorization should not be set since getItemAsync failed
      expect(result.headers.Authorization).toBeUndefined();
    });

    it('request reject handler propagates error', async () => {
      const [, onRejected] = getRequestInterceptor();
      const err = new Error('request setup failed');
      await expect(onRejected(err)).rejects.toEqual(err);
    });
  });

  describe('response interceptor — 401 SecureStore.deleteItemAsync catch', () => {

    const mockAxiosError = (status: number) => ({
      response: { status },
      message: 'Request failed',
    });

    afterEach(() => {
      setUnauthorizedHandler(null);
    });

    it('silently handles deleteItemAsync rejection during 401 cleanup', async () => {
      mockDeleteItem.mockRejectedValue(new Error('delete failed'));
      const [, errorHandler] = getResponseInterceptor();

      await expect(errorHandler(mockAxiosError(401))).rejects.toEqual(mockAxiosError(401));
      // deleteItemAsync was attempted even though it threw
      expect(mockDeleteItem).toHaveBeenCalledTimes(1);
    });

    it('silently handles unauthorizedHandler that throws', async () => {
      mockDeleteItem.mockResolvedValue(undefined);
      setUnauthorizedHandler(() => {
        throw new Error('handler crash');
      });
      const [, errorHandler] = getResponseInterceptor();

      await expect(errorHandler(mockAxiosError(401))).rejects.toEqual(mockAxiosError(401));
    });

    it('invokes async unauthorizedHandler successfully', async () => {
      mockDeleteItem.mockResolvedValue(undefined);
      const handler = jest.fn().mockResolvedValue(undefined);
      setUnauthorizedHandler(handler);
      const [, errorHandler] = getResponseInterceptor();

      await expect(errorHandler(mockAxiosError(401))).rejects.toEqual(mockAxiosError(401));
      expect(handler).toHaveBeenCalledTimes(1);
    });

    it('passes through non-error responses (onFulfilled)', () => {
      const [onFulfilled] = getResponseInterceptor();
      const response = { status: 200, data: 'ok' };
      expect(onFulfilled(response)).toBe(response);
    });

    it('rejects non-401 errors without touching SecureStore', async () => {
      const [, errorHandler] = getResponseInterceptor();
      await expect(errorHandler(mockAxiosError(500))).rejects.toEqual(mockAxiosError(500));
      expect(mockDeleteItem).not.toHaveBeenCalled();
    });

    it('rejects errors without response property', async () => {
      const [, errorHandler] = getResponseInterceptor();
      const networkErr = { message: 'Network Error' } as any;
      await expect(errorHandler(networkErr)).rejects.toEqual(networkErr);
      expect(mockDeleteItem).not.toHaveBeenCalled();
    });
  });
});
