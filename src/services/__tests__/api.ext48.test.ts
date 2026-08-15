/**
 * api ext48 — GET /teams 运维团队列表对接测试
 */
import { teamApi } from '../api';

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// Mock axios
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
    create: jest.fn(() => mockInstance),
    __mockInstance: mockInstance,
  };
});

import axios from 'axios';
// F1205: any收窄 — 对齐ext49+ __mockInstance模式, 替代逐调用as any
const mockAxios = (axios as unknown as { __mockInstance: { get: jest.Mock; post: jest.Mock; put: jest.Mock; delete: jest.Mock } }).__mockInstance;

describe('ext48 — teamApi.getList (GET /teams)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case fields to camelCase', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            {
              id: 1,
              name: '运维一组',
              code: 'OPS-1',
              leader_id: 10,
              leader_name: '张三',
              description: '负责东区站点',
              member_count: 5,
              station_count: 3,
              status: 'active',
              created_at: '2026-01-15T08:00:00+08:00',
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        },
        timestamp: 1700000000,
      },
    });
    const res = await teamApi.getList();
    expect(mockAxios.get).toHaveBeenCalledWith('/teams');
    expect(res.data.items).toHaveLength(1);
    expect(res.data.items[0]).toEqual({
      id: 1,
      name: '运维一组',
      code: 'OPS-1',
      leaderId: 10,
      leaderName: '张三',
      description: '负责东区站点',
      memberCount: 5,
      stationCount: 3,
      status: 'active',
      createdAt: '2026-01-15T08:00:00+08:00',
    });
  });

  it('handles empty items list', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 1, page_size: 20 },
        timestamp: 1700000000,
      },
    });
    const res = await teamApi.getList();
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
  });

  it('handles null/missing fields with defaults', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { items: [{ id: 2, name: 'Team B' }] },
        timestamp: 1700000000,
      },
    });
    const res = await teamApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 2,
      name: 'Team B',
      code: null,
      leaderId: null,
      leaderName: null,
      description: null,
      memberCount: 0,
      stationCount: 0,
      status: 'active',
      createdAt: null,
    });
  });

  it('passes page and page_size params', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 2, page_size: 5 },
        timestamp: 1700000000,
      },
    });
    await teamApi.getList({ page: 2, page_size: 5 });
    expect(mockAxios.get).toHaveBeenCalledWith('/teams?page=2&page_size=5');
  });

  it('calls correct endpoint with no params', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 1, page_size: 20 },
        timestamp: 1700000000,
      },
    });
    await teamApi.getList();
    expect(mockAxios.get).toHaveBeenCalledTimes(1);
    expect(mockAxios.get).toHaveBeenCalledWith('/teams');
  });

  it('getDetail maps snake_case fields correctly', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 3,
          name: '应急组',
          code: 'EMERG',
          leader_id: 15,
          leader_name: '李四',
          description: '应急响应',
          member_count: 8,
          station_count: 2,
          status: 'active',
          created_at: '2026-03-01T00:00:00+08:00',
          members: [],
        },
        timestamp: 1700000000,
      },
    });
    const res = await teamApi.getDetail(3);
    expect(mockAxios.get).toHaveBeenCalledWith('/teams/3');
    expect(res.data).toEqual({
      id: 3,
      name: '应急组',
      code: 'EMERG',
      leaderId: 15,
      leaderName: '李四',
      description: '应急响应',
      memberCount: 8,
      stationCount: 2,
      status: 'active',
      createdAt: '2026-03-01T00:00:00+08:00',
    });
  });

  it('getDetail handles null fields with defaults', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { id: 5, name: 'X' },
        timestamp: 1700000000,
      },
    });
    const res = await teamApi.getDetail(5);
    expect(res.data.id).toBe(5);
    expect(res.data.code).toBeNull();
    expect(res.data.memberCount).toBe(0);
    expect(res.data.status).toBe('active');
  });
});
