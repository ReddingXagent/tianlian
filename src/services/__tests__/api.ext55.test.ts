/**
 * api ext55 — apiKeyApi.getDetail + apiKeyApi.update (GET/PUT /api-keys/{id})
 * 新增: getDetail返回详细shape(id/name/keyPrefix/description/scopes/rateLimit/isActive/isRevoked/lastUsedAt/expiresAt/createdAt)
 *       update返回data:null, camel→snake request (name/description/scopes/rate_limit/is_active/expires_at)
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

const makeResponse = (data: unknown) => ({
  code: 200,
  message: 'success',
  data,
  timestamp: Date.now(),
});

describe('apiKeyApi.getDetail', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps detail fields camelCase correctly', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          name: '边缘网关密钥',
          key_prefix: 'tl_live_abc',
          description: '用于边缘网关遥测',
          scopes: ['device:view', 'telemetry:report'],
          rate_limit: 1000,
          is_active: true,
          is_revoked: false,
          last_used_at: '2026-08-10T12:00:00+08:00',
          expires_at: '2027-01-01T00:00:00+08:00',
          created_at: '2026-07-01T00:00:00+08:00',
        },
        timestamp: Date.now(),
      },
    });

    const res = await apiKeyApi.getDetail(1);
    expect(res.code).toBe(200);
    const k = res.data;
    expect(k.id).toBe(1);
    expect(k.name).toBe('边缘网关密钥');
    expect(k.keyPrefix).toBe('tl_live_abc');
    expect(k.description).toBe('用于边缘网关遥测');
    expect(k.scopes).toEqual(['device:view', 'telemetry:report']);
    expect(k.rateLimit).toBe(1000);
    expect(k.isActive).toBe(true);
    expect(k.isRevoked).toBe(false);
    expect(k.lastUsedAt).toBe('2026-08-10T12:00:00+08:00');
    expect(k.expiresAt).toBe('2027-01-01T00:00:00+08:00');
    expect(k.createdAt).toBe('2026-07-01T00:00:00+08:00');
  });

  it('handles null/missing fields with defaults', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 2,
          name: 'minimal',
          key_prefix: 'tl_min_',
          description: null,
          scopes: [],
          is_active: false,
          is_revoked: true,
          last_used_at: null,
          expires_at: null,
          created_at: '',
        },
        timestamp: Date.now(),
      },
    });

    const res = await apiKeyApi.getDetail(2);
    const k = res.data;
    expect(k.description).toBeNull();
    expect(k.scopes).toEqual([]);
    expect(k.rateLimit).toBe(0);
    expect(k.isActive).toBe(false);
    expect(k.isRevoked).toBe(true);
    expect(k.lastUsedAt).toBeNull();
    expect(k.expiresAt).toBeNull();
  });

  it('calls correct endpoint', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: makeResponse({ id: 5, name: 'x', key_prefix: 'x_' }),
    });
    await apiKeyApi.getDetail(5);
    expect(mockedAxios.get).toHaveBeenCalledWith('/api-keys/5');
  });
});

describe('apiKeyApi.update', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sends PUT with camel→snake mapping and returns null data', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'API Key updated',
        data: null,
        timestamp: Date.now(),
      },
    });

    const res = await apiKeyApi.update(1, {
      name: 'updated-key',
      description: 'new desc',
      scopes: ['read'],
      rateLimit: 2000,
      isActive: false,
      expiresAt: '2028-01-01T00:00:00+08:00',
    });

    expect(res.code).toBe(200);
    expect(res.data).toBeNull();
    expect(mockedAxios.put).toHaveBeenCalledWith('/api-keys/1', {
      name: 'updated-key',
      description: 'new desc',
      scopes: ['read'],
      rate_limit: 2000,
      is_active: false,
      expires_at: '2028-01-01T00:00:00+08:00',
    });
  });

  it('sends only provided fields (partial update)', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: makeResponse(null),
    });

    await apiKeyApi.update(3, { name: 'renamed' });

    expect(mockedAxios.put).toHaveBeenCalledWith('/api-keys/3', { name: 'renamed' });
  });

  it('handles null expiresAt', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: makeResponse(null),
    });

    await apiKeyApi.update(1, { expiresAt: null });

    expect(mockedAxios.put).toHaveBeenCalledWith('/api-keys/1', { expires_at: null });
  });
});
