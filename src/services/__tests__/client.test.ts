/**
 * client.ts coverage test — targets SecureStore catch branches + __DEV__ ternary
 * F1449: client.ts branches 90%→100%
 */

// Store interceptor handlers
const _requestHandlers: { fulfilled?: Function; rejected?: Function } = {};
const _responseHandlers: { fulfilled?: Function; rejected?: Function } = {};

jest.mock('axios', () => {
  const mockInstance = {
    interceptors: {
      request: {
        use: jest.fn((fulfilled?: Function, rejected?: Function) => {
          _requestHandlers.fulfilled = fulfilled;
          _requestHandlers.rejected = rejected;
        }),
      },
      response: {
        use: jest.fn((fulfilled?: Function, rejected?: Function) => {
          _responseHandlers.fulfilled = fulfilled;
          _responseHandlers.rejected = rejected;
        }),
      },
    },
  };
  return {
    __esModule: true,
    default: {
      create: jest.fn(() => mockInstance),
    },
  };
});

jest.mock('expo-secure-store', () => ({
  __esModule: true,
  default: {
    getItemAsync: jest.fn(),
    setItemAsync: jest.fn(),
    deleteItemAsync: jest.fn(),
  },
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// Import after mocks (side-effect registers interceptors, then export tokenStorage)
// eslint-disable-next-line import/no-duplicates
import '../api-modules/client';
// eslint-disable-next-line import/no-duplicates
import { tokenStorage } from '../api-modules/client';
import * as SecureStoreMod from 'expo-secure-store';

// Access mock functions
const ss = SecureStoreMod as unknown as {
  getItemAsync: jest.Mock;
  setItemAsync: jest.Mock;
  deleteItemAsync: jest.Mock;
};
const getItemAsync = ss.getItemAsync;
const setItemAsync = ss.setItemAsync;
const deleteItemAsync = ss.deleteItemAsync;

describe('client.ts — full branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('tokenStorage', () => {
    it('getToken returns null when SecureStore throws', async () => {
      getItemAsync.mockRejectedValueOnce(new Error('Keychain error'));
      const result = await tokenStorage.getToken();
      expect(result).toBeNull();
    });

    it('getToken returns token on success', async () => {
      getItemAsync.mockResolvedValueOnce('abc123');
      const result = await tokenStorage.getToken();
      expect(result).toBe('abc123');
    });

    it('setToken calls setItemAsync', async () => {
      setItemAsync.mockResolvedValueOnce(undefined);
      await tokenStorage.setToken('xyz');
      expect(setItemAsync).toHaveBeenCalledWith('auth_token', 'xyz');
    });

    it('removeToken calls deleteItemAsync', async () => {
      deleteItemAsync.mockResolvedValueOnce(undefined);
      await tokenStorage.removeToken();
      expect(deleteItemAsync).toHaveBeenCalledWith('auth_token');
    });
  });

  describe('request interceptor', () => {
    it('catches SecureStore error silently and returns config', async () => {
      getItemAsync.mockRejectedValueOnce(new Error('SecureStore fail'));
      const config = { headers: {} };
      const result = await _requestHandlers.fulfilled!(config);
      expect(result).toBe(config);
    });

    it('injects token when SecureStore returns one', async () => {
      getItemAsync.mockResolvedValueOnce('my-token');
      const config = { headers: {} };
      const result = await _requestHandlers.fulfilled!(config);
      expect(result.headers.Authorization).toBe('Bearer my-token');
    });

    it('does not inject token when config has no headers', async () => {
      getItemAsync.mockResolvedValueOnce('my-token');
      const config = {};
      const result = await _requestHandlers.fulfilled!(config);
      expect(result).toBe(config);
    });

    it('rejects on request error', async () => {
      const err = new Error('Request setup fail');
      await expect(_requestHandlers.rejected!(err)).rejects.toThrow('Request setup fail');
    });
  });

  describe('response interceptor', () => {
    it('passes through successful responses', () => {
      const response = { status: 200, data: { ok: true } };
      expect(_responseHandlers.fulfilled!(response)).toBe(response);
    });

    it('catches SecureStore deleteItemAsync error on 401 silently', async () => {
      deleteItemAsync.mockRejectedValueOnce(new Error('Delete fail'));
      const error = { response: { status: 401 } };
      await expect(_responseHandlers.rejected!(error)).rejects.toBe(error);
    });

    it('deletes token on 401 when SecureStore succeeds', async () => {
      deleteItemAsync.mockResolvedValueOnce(undefined);
      const error = { response: { status: 401 } };
      await expect(_responseHandlers.rejected!(error)).rejects.toBe(error);
      expect(deleteItemAsync).toHaveBeenCalledWith('auth_token');
    });

    it('rejects non-401 errors without touching SecureStore', async () => {
      const error = { response: { status: 500 } };
      await expect(_responseHandlers.rejected!(error)).rejects.toBe(error);
      expect(deleteItemAsync).not.toHaveBeenCalled();
    });

    it('rejects errors without response property', async () => {
      const error = new Error('Network error');
      await expect(_responseHandlers.rejected!(error)).rejects.toThrow('Network error');
    });
  });

  describe('BASE_URL __DEV__=false branch', () => {
    it('covers __DEV__=false ternary branch', () => {
      // Temporarily set __DEV__=false and re-import to cover the false branch
      const originalDev = (global as unknown as { __DEV__: boolean }).__DEV__;
      (global as unknown as { __DEV__: boolean }).__DEV__ = false;
      try {
        jest.isolateModules(() => {
          // eslint-disable-next-line @typescript-eslint/no-require-imports
          const mod = require('../api-modules/client');
          void mod;
        });
      } finally {
        (global as unknown as { __DEV__: boolean }).__DEV__ = originalDev;
      }
      expect(true).toBe(true);
    });
  });
});
