/**
 * api ext36 — Health Ping API (GET /ping)
 * Target: connectivity check endpoint returning { message: "pong" }
 */
import { healthApi } from '../api';

// Mock expo-secure-store before axios mock
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

// Import mocked axios
import axios from 'axios';
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('healthApi.getPing (ext36)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps response data correctly (pong)', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { message: 'pong' } },
    });
    const result = await healthApi.getPing();
    expect(result.data.message).toBe('pong');
    expect(result.code).toBe(200);
  });

  it('handles null data gracefully', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: null },
    });
    const result = await healthApi.getPing();
    expect(result.data.message).toBe('');
  });

  it('handles missing message field', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {} },
    });
    const result = await healthApi.getPing();
    expect(result.data.message).toBe('');
  });

  it('calls correct endpoint', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { message: 'pong' } },
    });
    await healthApi.getPing();
    expect(mockedAxios.get).toHaveBeenCalledWith('/ping');
  });

  it('preserves top-level fields', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', timestamp: 1786571080, data: { message: 'pong' } },
    });
    const result = await healthApi.getPing();
    expect(result.code).toBe(200);
    expect(result.message).toBe('success');
  });
});
