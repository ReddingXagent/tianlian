import { cacheApi } from '../api';

// Mock expo-secure-store
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

import axios from 'axios';
const mockAxios = axios as jest.Mocked<typeof axios>;

describe('cacheApi.getStats (ext39 — GET /cache/stats)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case to camelCase correctly', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          hit_rate: 87.5,
          total_keys: 128,
          used_memory_mb: 2.4,
          backend: 'mock',
        },
        timestamp: 1786578645,
      },
    });

    const res = await cacheApi.getStats();
    expect(res.data.hitRate).toBe(87.5);
    expect(res.data.totalKeys).toBe(128);
    expect(res.data.usedMemoryMb).toBe(2.4);
    expect(res.data.backend).toBe('mock');
  });

  it('handles null data gracefully', async () => {
    mockAxios.get.mockResolvedValue({
      data: { code: 200, message: 'success', data: null },
    });

    const res = await cacheApi.getStats();
    expect(res.data.hitRate).toBe(0);
    expect(res.data.totalKeys).toBe(0);
    expect(res.data.usedMemoryMb).toBe(0);
    expect(res.data.backend).toBe('unknown');
  });

  it('handles missing fields with defaults', async () => {
    mockAxios.get.mockResolvedValue({
      data: { code: 200, message: 'success', data: {} },
    });

    const res = await cacheApi.getStats();
    expect(res.data.hitRate).toBe(0);
    expect(res.data.totalKeys).toBe(0);
    expect(res.data.usedMemoryMb).toBe(0);
    expect(res.data.backend).toBe('unknown');
  });

  it('calls correct endpoint', async () => {
    mockAxios.get.mockResolvedValue({
      data: { code: 200, message: 'success', data: { hit_rate: 50, total_keys: 10, used_memory_mb: 1, backend: 'redis' } },
    });

    await cacheApi.getStats();
    expect(mockAxios.get).toHaveBeenCalledWith('/cache/stats');
  });

  it('preserves top-level fields', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { hit_rate: 99.9, total_keys: 500, used_memory_mb: 10.5, backend: 'redis' },
        timestamp: 1234567890,
      },
    });

    const res = await cacheApi.getStats();
    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
    expect(res.timestamp).toBe(1234567890);
  });
});
