/**
 * ext49 — teamApi.update (PUT /teams/{id})
 * Cases: camelCase mapping, null defaults, missing fields, endpoint, top-level
 */
import { teamApi } from '../api';
import { TeamUpdate } from '../../types';

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
const mockAxios = (axios as unknown as { __mockInstance: { put: jest.Mock } }).__mockInstance;

describe('ext49 — teamApi.update (PUT /teams/{id})', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('1. maps snake_case response → camelCase', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          name: '运维一队',
          code: 'OPS_01',
          leader_id: 5,
          leader_name: '张三',
          description: '华东区运维',
          member_count: 8,
          station_count: 12,
          status: 'active',
          created_at: '2026-06-23T03:20:01+08:00',
        },
        timestamp: 1786632483,
      },
    });

    const res = await teamApi.update(1, { name: '运维一队' });
    expect(res.data.id).toBe(1);
    expect(res.data.name).toBe('运维一队');
    expect(res.data.code).toBe('OPS_01');
    expect(res.data.leaderId).toBe(5);
    expect(res.data.leaderName).toBe('张三');
    expect(res.data.memberCount).toBe(8);
    expect(res.data.stationCount).toBe(12);
    expect(res.data.createdAt).toBe('2026-06-23T03:20:01+08:00');
  });

  it('2. handles null fields with defaults', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 2,
          name: '新团队',
          code: null,
          leader_id: null,
          leader_name: null,
          description: null,
          member_count: 0,
          station_count: 0,
          status: 'inactive',
          created_at: null,
        },
        timestamp: 1786632483,
      },
    });

    const res = await teamApi.update(2, { status: 'inactive' });
    expect(res.data.code).toBeNull();
    expect(res.data.leaderId).toBeNull();
    expect(res.data.leaderName).toBeNull();
    expect(res.data.description).toBeNull();
    expect(res.data.memberCount).toBe(0);
    expect(res.data.createdAt).toBeNull();
  });

  it('3. handles missing fields with defaults', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 3,
          name: '最小团队',
        },
        timestamp: 1786632483,
      },
    });

    const res = await teamApi.update(3, { name: '最小团队' });
    expect(res.data.id).toBe(3);
    expect(res.data.code).toBeNull();
    expect(res.data.leaderId).toBeNull();
    expect(res.data.memberCount).toBe(0);
    expect(res.data.status).toBe('active');
  });

  it('4. calls correct endpoint with PUT and payload', async () => {
    mockAxios.put.mockResolvedValue({
      data: { code: 200, message: 'success', data: { id: 1, name: 'X' }, timestamp: 0 },
    });

    const body: TeamUpdate = { name: '更新名', description: '新描述', leaderId: 10, status: 'active' };
    await teamApi.update(1, body);

    expect(mockAxios.put).toHaveBeenCalledTimes(1);
    expect(mockAxios.put).toHaveBeenCalledWith('/teams/1', {
      name: '更新名',
      description: '新描述',
      leader_id: 10,
      status: 'active',
    });
  });

  it('5. returns top-level fields (code, message, timestamp)', async () => {
    mockAxios.put.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { id: 1, name: 'T' },
        timestamp: 1786632483,
      },
    });

    const res = await teamApi.update(1, { name: 'T' });
    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
    expect(res.timestamp).toBe(1786632483);
  });
});
