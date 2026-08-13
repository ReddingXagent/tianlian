/**
 * api ext58 — roleApi.create + roleApi.delete
 * POST /roles → Role(id/name/displayName/description/isSystem/permissions)
 * DELETE /roles/{id} → null
 */
import { roleApi } from '../api';
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

// =====================
// roleApi.create
// =====================
describe('roleApi.create (ext58)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps response snake_case → camelCase', async () => {
    mockedAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: {
          id: 10,
          name: 'operator',
          display_name: 'Operator',
          description: 'ops role',
          is_system: false,
          permissions: ['stations:read', 'devices:read'],
        },
      },
    });
    const res = await roleApi.create({
      name: 'operator',
      displayName: 'Operator',
      description: 'ops role',
      permissions: ['stations:read', 'devices:read'],
    });
    expect(res.data.id).toBe(10);
    expect(res.data.name).toBe('operator');
    expect(res.data.displayName).toBe('Operator');
    expect(res.data.description).toBe('ops role');
    expect(res.data.isSystem).toBe(false);
    expect(res.data.permissions).toEqual(['stations:read', 'devices:read']);
  });

  it('handles null/missing fields with defaults', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: { id: 11, name: 'basic' } },
    });
    const res = await roleApi.create({ name: 'basic' });
    expect(res.data.id).toBe(11);
    expect(res.data.name).toBe('basic');
    expect(res.data.displayName).toBe('');
    expect(res.data.description).toBe('');
    expect(res.data.isSystem).toBe(false);
    expect(res.data.permissions).toEqual([]);
  });

  it('sends camelCase → snake_case in request payload', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: { id: 12, name: 'x' } },
    });
    await roleApi.create({
      name: 'x',
      displayName: 'X',
      description: 'desc',
      permissions: ['a:b'],
    });
    expect(mockedAxios.post).toHaveBeenCalledWith('/roles', {
      name: 'x',
      display_name: 'X',
      description: 'desc',
      permissions: ['a:b'],
    });
  });

  it('only sends name when optional fields omitted', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: { id: 13, name: 'y' } },
    });
    await roleApi.create({ name: 'y' });
    expect(mockedAxios.post).toHaveBeenCalledWith('/roles', { name: 'y' });
  });
});

// =====================
// roleApi.delete
// =====================
describe('roleApi.delete (ext58)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('calls DELETE /roles/{id} and returns top-level', async () => {
    mockedAxios.delete.mockResolvedValue({
      data: { code: 200, message: 'deleted', data: null },
    });
    const res = await roleApi.delete(5);
    expect(mockedAxios.delete).toHaveBeenCalledWith('/roles/5');
    expect(res.code).toBe(200);
    expect(res.message).toBe('deleted');
    expect(res.data).toBeNull();
  });

  it('handles 404 for non-existent role', async () => {
    mockedAxios.delete.mockResolvedValue({
      data: { code: 404, message: '角色不存在', data: null },
    });
    const res = await roleApi.delete(9999);
    expect(res.code).toBe(404);
    expect(res.data).toBeNull();
  });
});
