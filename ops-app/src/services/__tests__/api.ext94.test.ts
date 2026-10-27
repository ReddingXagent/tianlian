/**
 * api ext94 — apiKeyApi.getDetail real sparse response (5 of 11 fields)
 *
 * Real API /api-keys/{id} returns only: id, name, key_prefix, description, scopes
 * Missing: rate_limit, is_active, is_revoked, last_used_at, expires_at, created_at
 * This is the actual contract behavior observed F1475 — detail returns fewer fields than list.
 */
import { apiKeyApi } from '../api';

jest.mock('axios', () => {
  const mockAxios = {
    create: () => ({
      interceptors: {
        request: { use: jest.fn() },
        response: { use: jest.fn() },
      },
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      patch: jest.fn(),
      delete: jest.fn(),
    }),
  };
  return mockAxios;
});

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const api = require('../api').default;

describe('apiKeyApi.getDetail — real sparse (F1475)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps 5-field sparse response like real /api-keys/1', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          name: 'test',
          key_prefix: 'tl_TLImkVp',
          description: null,
          scopes: [],
        },
        timestamp: 1787077078,
      },
    });

    const res = await apiKeyApi.getDetail(1);
    expect(res.code).toBe(200);
    expect(res.data.id).toBe(1);
    expect(res.data.name).toBe('test');
    expect(res.data.keyPrefix).toBe('tl_TLImkVp');
    expect(res.data.description).toBeNull();
    expect(res.data.scopes).toEqual([]);
    // Missing fields fall to ?? defaults
    expect(res.data.rateLimit).toBe(0);
    expect(res.data.isActive).toBe(false);
    expect(res.data.isRevoked).toBe(false);
    expect(res.data.lastUsedAt).toBeNull();
    expect(res.data.expiresAt).toBeNull();
    expect(res.data.createdAt).toBe('');
  });

  it('maps 5-field sparse with non-empty scopes like real /api-keys/2', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 2,
          name: 'test-key',
          key_prefix: 'tl_J_XhRxq',
          description: null,
          scopes: ['read'],
        },
        timestamp: 1787077078,
      },
    });

    const res = await apiKeyApi.getDetail(2);
    expect(res.data.id).toBe(2);
    expect(res.data.name).toBe('test-key');
    expect(res.data.keyPrefix).toBe('tl_J_XhRxq');
    expect(res.data.scopes).toEqual(['read']);
    // Defaults for missing fields
    expect(res.data.rateLimit).toBe(0);
    expect(res.data.isActive).toBe(false);
    expect(res.data.isRevoked).toBe(false);
  });
});
