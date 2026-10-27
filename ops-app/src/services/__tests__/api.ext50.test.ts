/**
 * ext50 — teamApi.create (POST /teams) + teamApi.delete (DELETE /teams/{id})
 * Cases: create camelCase, create null defaults, create endpoint+payload,
 *        delete endpoint, delete return shape
 */
import { teamApi } from '../api';
import { TeamCreate } from '../../types';

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
  __mockInstance: { post: jest.Mock; delete: jest.Mock };
}).__mockInstance;

describe('ext50 — teamApi.create + teamApi.delete', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // --- create ---

  it('1. create: maps snake_case response → camelCase', async () => {
    mockAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 7,
          name: '测试队',
          code: 'THN0001',
          leader_id: null,
          leader_name: null,
          description: 'auto-test',
          member_count: 0,
          station_count: 0,
          status: 'inactive',
          created_at: '2026-08-13T22:56:50.745913+08:00',
        },
        timestamp: 1786633010,
      },
    });

    const res = await teamApi.create({ name: '测试队', description: 'auto-test' });
    expect(res.data.id).toBe(7);
    expect(res.data.name).toBe('测试队');
    expect(res.data.code).toBe('THN0001');
    expect(res.data.leaderId).toBeNull();
    expect(res.data.leaderName).toBeNull();
    expect(res.data.description).toBe('auto-test');
    expect(res.data.memberCount).toBe(0);
    expect(res.data.stationCount).toBe(0);
    expect(res.data.status).toBe('inactive');
    expect(res.data.createdAt).toBe('2026-08-13T22:56:50.745913+08:00');
  });

  it('2. create: handles missing optional fields with defaults', async () => {
    mockAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 8,
          name: '最小',
        },
        timestamp: 1786633010,
      },
    });

    const res = await teamApi.create({ name: '最小' });
    expect(res.data.id).toBe(8);
    expect(res.data.code).toBeNull();
    expect(res.data.leaderId).toBeNull();
    expect(res.data.description).toBeNull();
    expect(res.data.memberCount).toBe(0);
    expect(res.data.status).toBe('active');
    expect(res.data.createdAt).toBeNull();
  });

  it('3. create: calls correct endpoint with POST and payload', async () => {
    mockAxios.post.mockResolvedValue({
      data: { code: 200, message: 'success', data: { id: 1, name: 'X' }, timestamp: 0 },
    });

    const body: TeamCreate = { name: '新建队', code: 'C001', description: '描述' };
    await teamApi.create(body);

    expect(mockAxios.post).toHaveBeenCalledTimes(1);
    expect(mockAxios.post).toHaveBeenCalledWith('/teams', {
      name: '新建队',
      code: 'C001',
      description: '描述',
    });
  });

  // --- delete ---

  it('4. delete: calls correct endpoint with DELETE', async () => {
    mockAxios.delete.mockResolvedValue({
      data: {
        code: 200,
        message: '团队 7 已删除',
        data: null,
        timestamp: 1786633017,
      },
    });

    const res = await teamApi.delete(7);

    expect(mockAxios.delete).toHaveBeenCalledTimes(1);
    expect(mockAxios.delete).toHaveBeenCalledWith('/teams/7');
    expect(res.code).toBe(200);
    expect(res.message).toBe('团队 7 已删除');
    expect(res.data).toBeNull();
  });

  it('5. delete: returns top-level fields', async () => {
    mockAxios.delete.mockResolvedValue({
      data: {
        code: 404,
        message: '团队不存在',
        data: null,
        timestamp: 1786633010,
      },
    });

    const res = await teamApi.delete(999);
    expect(res.code).toBe(404);
    expect(res.message).toBe('团队不存在');
    expect(res.data).toBeNull();
    expect(res.timestamp).toBe(1786633010);
  });
});
