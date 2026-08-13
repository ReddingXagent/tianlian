/**
 * api ext79 — mapper fallback branches batch 6
 * Targets: apiKeyApi.getList/getDetail/getUsage/rotate,
 *   securityLogApi.getList, securityPolicyApi.getList/getByKey
 */
import {
  apiKeyApi,
  securityLogApi,
  securityPolicyApi,
} from '../api';
import axios from 'axios';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn(), patch: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  };
  return { create: jest.fn(() => mockInstance), __mockInstance: mockInstance };
});

const mockAxios = (axios as unknown as { __mockInstance: any }).__mockInstance;

describe('ext79 — mapper fallback branch coverage batch 6', () => {
  beforeEach(() => jest.clearAllMocks());

  // apiKeyApi.getList — items [{}] → fallback
  it('apiKeyApi.getList: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await apiKeyApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0, name: '', keyPrefix: '', description: null,
      scopes: [], rateLimit: 0, isActive: false, isRevoked: false,
      lastUsedAt: null, expiresAt: null, createdAt: '',
    });
  });

  // apiKeyApi.getDetail — data {} → fallback
  it('apiKeyApi.getDetail: data {} → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await apiKeyApi.getDetail(1);
    expect(res.data).toEqual({
      id: 0, name: '', keyPrefix: '', description: null,
      scopes: [], rateLimit: 0, isActive: false, isRevoked: false,
      lastUsedAt: null, expiresAt: null, createdAt: '',
    });
  });

  // apiKeyApi.getUsage — data {} → fallback
  it('apiKeyApi.getUsage: data {} → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await apiKeyApi.getUsage(1);
    expect(res.data).toEqual({
      keyId: 0, periodDays: 0, totalRequests: 0, avgDurationMs: 0,
    });
  });

  // apiKeyApi.rotate — data {} → fallback
  it('apiKeyApi.rotate: data {} → fallback', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await apiKeyApi.rotate(1);
    expect(res.data).toEqual({
      id: 0, apiKey: '', keyPrefix: '',
    });
  });

  // securityLogApi.getList — items [{}] → fallback
  it('securityLogApi.getList: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await securityLogApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0, timestamp: '', userId: 0, username: '',
      userRole: null, action: '', module: '',
      targetId: '', targetDesc: '', detail: null,
      oldValue: null, newValue: null,
      ipAddress: null, userAgent: null,
      result: 'success', errorMsg: null,
    });
  });

  // securityLogApi.getList — data null → empty
  it('securityLogApi.getList: data null → empty', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await securityLogApi.getList();
    expect(res.data.items).toEqual([]);
  });

  // securityPolicyApi.getList — items [{}] → fallback
  it('securityPolicyApi.getList: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await securityPolicyApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0, policyKey: '', policyConfig: {},
      description: '', status: 'active',
      createdAt: '', updatedAt: '',
    });
  });

  // securityPolicyApi.getByKey — data {} → fallback
  it('securityPolicyApi.getByKey: data {} → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await securityPolicyApi.getByKey('test');
    expect(res.data).toEqual({
      id: 0, policyKey: '', policyConfig: {},
      description: '', status: 'active',
      createdAt: '', updatedAt: '',
    });
  });
});
