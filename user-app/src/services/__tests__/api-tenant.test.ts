/**
 * Tests for tenantApi — GET /tenants/{id}/branding
 * Covers snake→camel mapping, null data fallback, defaults
 */
import { tenantApi } from '../api';

import axios from 'axios';

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
    __esModule: true,
    default: {
      create: jest.fn(() => mockInstance),
    },
  };
});

jest.mock('expo-secure-store', () => ({
  __esModule: true,
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockApi = jest.mocked(axios.create).mock.results[0].value;

beforeEach(() => {
  jest.clearAllMocks();
});

describe('tenantApi.getBranding contract', () => {
  it('maps snake_case → camelCase correctly', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        code: 200,
        data: {
          tenant_id: 't-001',
          operator_name: '绿能科技',
          logo_url: 'https://example.com/logo.png',
          theme_color: '#00FF00',
          source: 'operator',
        },
      },
    });

    const res = await tenantApi.getBranding('t-001');
    expect(res.data.tenantId).toBe('t-001');
    expect(res.data.operatorName).toBe('绿能科技');
    expect(res.data.logoUrl).toBe('https://example.com/logo.png');
    expect(res.data.themeColor).toBe('#00FF00');
    expect(res.data.source).toBe('operator');
  });

  it('maps camelCase input correctly', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        code: 200,
        data: {
          tenantId: 't-002',
          operatorName: '天链新能源',
          themeColor: '#FF0000',
        },
      },
    });

    const res = await tenantApi.getBranding('t-002');
    expect(res.data.tenantId).toBe('t-002');
    expect(res.data.operatorName).toBe('天链新能源');
    expect(res.data.themeColor).toBe('#FF0000');
    expect(res.data.source).toBe('default');
  });

  it('returns raw res.data when data.data is null', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: null },
    });

    const res = await tenantApi.getBranding('t-003');
    expect(res.code).toBe(200);
    expect(res.data).toBeNull();
  });

  it('applies defaults for empty data object', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: { code: 200, data: {} },
    });

    const res = await tenantApi.getBranding('fallback-id');
    expect(res.data.tenantId).toBe('fallback-id');
    expect(res.data.operatorName).toBe('天链');
    expect(res.data.themeColor).toBe('#00A86B');
    expect(res.data.source).toBe('default');
    expect(res.data.logoUrl).toBeUndefined();
  });

  it('calls GET /tenants/{id}/branding', async () => {
    mockApi.get.mockResolvedValueOnce({ data: { code: 200, data: {} } });

    await tenantApi.getBranding('tenant-abc');
    expect(mockApi.get).toHaveBeenCalledWith('/tenants/tenant-abc/branding');
  });

  it('rejects on network error', async () => {
    mockApi.get.mockRejectedValueOnce(new Error('Network Error'));

    await expect(tenantApi.getBranding('t-004')).rejects.toThrow('Network Error');
  });
});
