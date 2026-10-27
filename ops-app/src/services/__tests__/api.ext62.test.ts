/**
 * api ext62 — workOrderActionApi.reject
 * POST /work-orders/{id}/reject?reason=xxx
 */
import { workOrderActionApi } from '../api';
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

describe('api.ext62 — workOrderActionApi.reject', () => {
  it('calls POST /work-orders/{id}/reject with reason as query param', async () => {
    const mockAxios = (axios as unknown as { __mockInstance: { post: jest.Mock } }).__mockInstance;
    mockAxios.post.mockResolvedValue({
      data: { code: 200, message: 'success', data: null, timestamp: 1700000000 },
    });

    await workOrderActionApi.reject('1', '不适合处理');

    expect(mockAxios.post).toHaveBeenCalledWith(
      '/work-orders/1/reject',
      null,
      { params: { reason: '不适合处理' } },
    );
  });

  it('returns ApiResponse<null> shape', async () => {
    const mockAxios = (axios as unknown as { __mockInstance: { post: jest.Mock } }).__mockInstance;
    mockAxios.post.mockResolvedValue({
      data: { code: 200, message: 'success', data: null, timestamp: 1700000000 },
    });

    const res = await workOrderActionApi.reject('1', 'test reason');
    expect(res).toEqual({
      code: 200,
      message: 'success',
      data: null,
      timestamp: 1700000000,
    });
  });

  it('passes business 404 through (工单不存在)', async () => {
    const mockAxios = (axios as unknown as { __mockInstance: { post: jest.Mock } }).__mockInstance;
    mockAxios.post.mockResolvedValue({
      data: { code: 404, message: '工单不存在', data: null, timestamp: 1700000000 },
    });

    const res = await workOrderActionApi.reject('999', 'no such');
    expect(res.code).toBe(404);
    expect(res.message).toBe('工单不存在');
    expect(res.data).toBeNull();
  });

  it('sends reason as query param, not body', async () => {
    const mockAxios = (axios as unknown as { __mockInstance: { post: jest.Mock } }).__mockInstance;
    mockAxios.post.mockClear();
    mockAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: null, timestamp: 1 },
    });

    await workOrderActionApi.reject('5', 'duplicate');

    const call = mockAxios.post.mock.calls[0];
    expect(call[0]).toBe('/work-orders/5/reject');
    expect(call[1]).toBeNull(); // body is null
    expect(call[2]).toEqual({ params: { reason: 'duplicate' } });
  });

  it('handles empty reason string', async () => {
    const mockAxios = (axios as unknown as { __mockInstance: { post: jest.Mock } }).__mockInstance;
    mockAxios.post.mockClear();
    mockAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: null, timestamp: 1 },
    });

    await workOrderActionApi.reject('1', '');
    expect(mockAxios.post).toHaveBeenCalledWith(
      '/work-orders/1/reject',
      null,
      { params: { reason: '' } },
    );
  });
});
