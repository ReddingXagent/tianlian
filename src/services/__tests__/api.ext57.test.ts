/**
 * api ext57 — roleApi.update + apiKeyApi.create
 * PUT /roles/{id} → Role(id/name/displayName/description/isSystem/permissions)
 * POST /api-keys → ApiKeyCreated(id/name/apiKey/keyPrefix/scopes/expiresAt)
 */
import { roleApi, apiKeyApi } from '../api';
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

const mockedAxios = (axios as unknown as {
  __mockInstance: {
    get: jest.Mock;
    post: jest.Mock;
    put: jest.Mock;
    delete: jest.Mock;
  },
}).__mockInstance;

// =====================
// roleApi.update
// =====================
describe('roleApi.update (ext57)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case response to camelCase correctly', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: {
        code: 200,
        message: '角色更新成功',
        data: {
          id: 2,
          name: 'operator',
          display_name: '运维人员',
          description: '运维操作员',
          is_system: false,
          permissions: ['device:view', 'station:view', 'alarm:view'],
        },
        timestamp: 1786636400,
      },
    });

    const res = await roleApi.update(2, {
      displayName: '运维人员',
      description: '运维操作员',
      permissions: ['device:view', 'station:view', 'alarm:view'],
    });

    expect(res.code).toBe(200);
    expect(res.data.id).toBe(2);
    expect(res.data.name).toBe('operator');
    expect(res.data.displayName).toBe('运维人员');
    expect(res.data.description).toBe('运维操作员');
    expect(res.data.isSystem).toBe(false);
    expect(res.data.permissions).toEqual(['device:view', 'station:view', 'alarm:view']);
  });

  it('maps null/missing fields to defaults', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {},
        timestamp: 1786636400,
      },
    });

    const res = await roleApi.update(99, { displayName: 'test' });

    expect(res.data.id).toBe(0);
    expect(res.data.name).toBe('');
    expect(res.data.displayName).toBe('');
    expect(res.data.description).toBe('');
    expect(res.data.isSystem).toBe(false);
    expect(res.data.permissions).toEqual([]);
  });

  it('sends camel→snake request payload', async () => {
    mockedAxios.put.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 1 }, timestamp: 0 },
    });

    await roleApi.update(1, {
      displayName: 'Admin',
      description: 'Updated admin role',
      permissions: ['*'],
    });

    expect(mockedAxios.put).toHaveBeenCalledWith('/roles/1', {
      display_name: 'Admin',
      description: 'Updated admin role',
      permissions: ['*'],
    });
  });
});

// =====================
// apiKeyApi.create
// =====================
describe('apiKeyApi.create (ext57)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case response to camelCase correctly', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'API Key created',
        data: {
          id: 5,
          name: 'my-key',
          api_key: 'tl_abc123XYZ',
          key_prefix: 'tl_abc1',
          scopes: ['read', 'write'],
          expires_at: null,
        },
        timestamp: 1786636500,
      },
    });

    const res = await apiKeyApi.create({
      name: 'my-key',
      scopes: ['read', 'write'],
    });

    expect(res.code).toBe(200);
    expect(res.data.id).toBe(5);
    expect(res.data.name).toBe('my-key');
    expect(res.data.apiKey).toBe('tl_abc123XYZ');
    expect(res.data.keyPrefix).toBe('tl_abc1');
    expect(res.data.scopes).toEqual(['read', 'write']);
    expect(res.data.expiresAt).toBeNull();
  });

  it('maps null/missing fields to defaults', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'created',
        data: {},
        timestamp: 1786636500,
      },
    });

    const res = await apiKeyApi.create({ name: 'x', scopes: [] });

    expect(res.data.id).toBe(0);
    expect(res.data.name).toBe('');
    expect(res.data.apiKey).toBe('');
    expect(res.data.keyPrefix).toBe('');
    expect(res.data.scopes).toEqual([]);
    expect(res.data.expiresAt).toBeNull();
  });

  it('sends camel→snake request with optional fields', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 1 }, timestamp: 0 },
    });

    await apiKeyApi.create({
      name: 'full-key',
      scopes: ['read'],
      description: 'test desc',
      rateLimit: 100,
      expiresAt: '2027-01-01T00:00:00Z',
    });

    expect(mockedAxios.post).toHaveBeenCalledWith('/api-keys', {
      name: 'full-key',
      scopes: ['read'],
      description: 'test desc',
      rate_limit: 100,
      expires_at: '2027-01-01T00:00:00Z',
    });
  });

  it('omits undefined optional fields from payload', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { id: 1 }, timestamp: 0 },
    });

    await apiKeyApi.create({ name: 'min', scopes: ['read'] });

    const payload = mockedAxios.post.mock.calls[0][1];
    expect(payload).not.toHaveProperty('description');
    expect(payload).not.toHaveProperty('rate_limit');
    expect(payload).not.toHaveProperty('expires_at');
  });
});
