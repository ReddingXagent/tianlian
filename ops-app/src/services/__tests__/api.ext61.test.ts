/**
 * api ext61 — workOrderActionApi.transfer
 * POST /work-orders/{id}/transfer (target_engineer_id + reason)
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

const mockedAxios = (axios as unknown as {
  __mockInstance: {
    get: jest.Mock;
    post: jest.Mock;
    put: jest.Mock;
    delete: jest.Mock;
  },
}).__mockInstance;

describe('ext61 — workOrderActionApi.transfer', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sends POST /work-orders/{id}/transfer with camelCase → snake_case body', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: '转单成功', data: null, timestamp: 1786639000 },
    });

    const res = await workOrderActionApi.transfer('WO-20260710-xxx', 23, '工程师休假转单');

    expect(mockedAxios.post).toHaveBeenCalledWith('/work-orders/WO-20260710-xxx/transfer', {
      target_engineer_id: 23,
      reason: '工程师休假转单',
    });
    expect(res.code).toBe(200);
    expect(res.message).toBe('转单成功');
    expect(res.data).toBeNull();
  });

  it('handles 404 target engineer not found', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 404, message: '目标工程师不存在', data: null, timestamp: 1786639001 },
    });

    const res = await workOrderActionApi.transfer('WO-20260710-xxx', 999, 'test');

    expect(res.code).toBe(404);
    expect(res.message).toBe('目标工程师不存在');
  });

  it('passes through 400 business validation errors', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 400, message: '工单当前不允许转单', data: null, timestamp: 1786639002 },
    });

    const res = await workOrderActionApi.transfer('WO-20260710-xxx', 23, 'test');

    expect(res.code).toBe(400);
    expect(res.message).toContain('不允许');
  });

  it('verifies endpoint path and payload shape', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: null, timestamp: 0 },
    });

    await workOrderActionApi.transfer('WO-123', 1, 'reason');

    const [url, body] = mockedAxios.post.mock.calls[0];
    expect(url).toBe('/work-orders/WO-123/transfer');
    expect(body).toEqual({ target_engineer_id: 1, reason: 'reason' });
  });

  it('returns null data on success', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: '转单成功', data: null, timestamp: 0 },
    });

    const res = await workOrderActionApi.transfer('WO-1', 5, 'shift change');
    expect(res.data).toBeNull();
  });
});
