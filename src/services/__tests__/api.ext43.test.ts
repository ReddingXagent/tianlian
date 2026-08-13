import { gatewayApi } from '../api';

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

describe('gatewayApi.getFirmware (ext43 — GET /gateways/firmware)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case to camelCase correctly', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            {
              id: 1,
              version: 'v2.1.0',
              file_id: 'fw-abc123',
              file_size: 1048576,
              release_notes: 'Stability improvements',
              status: 'published',
              created_at: '2026-08-01T00:00:00Z',
              updated_at: '2026-08-10T00:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        },
        timestamp: 1786606285,
      },
    });

    const res = await gatewayApi.getFirmware();
    expect(res.data.items).toHaveLength(1);
    const fw = res.data.items[0];
    expect(fw.id).toBe(1);
    expect(fw.version).toBe('v2.1.0');
    expect(fw.fileId).toBe('fw-abc123');
    expect(fw.fileSize).toBe(1048576);
    expect(fw.releaseNotes).toBe('Stability improvements');
    expect(fw.status).toBe('published');
    expect(fw.createdAt).toBe('2026-08-01T00:00:00Z');
    expect(fw.updatedAt).toBe('2026-08-10T00:00:00Z');
  });

  it('handles empty list', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [],
          total: 0,
          page: 1,
          page_size: 20,
        },
        timestamp: 1786606285,
      },
    });

    const res = await gatewayApi.getFirmware();
    expect(res.data.items).toHaveLength(0);
    expect(res.data.total).toBe(0);
  });

  it('handles null data with defaults', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: null,
        timestamp: 1786606285,
      },
    });

    const res = await gatewayApi.getFirmware();
    expect(res.data.items).toHaveLength(0);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  it('calls correct endpoint', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 1, page_size: 20 },
        timestamp: 1786606285,
      },
    });

    await gatewayApi.getFirmware();
    expect(mockAxios.get).toHaveBeenCalledWith('/gateways/firmware');
  });

  it('preserves top-level response fields', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 1, page_size: 20 },
        timestamp: 1786606285,
      },
    });

    const res = await gatewayApi.getFirmware();
    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
  });
});
