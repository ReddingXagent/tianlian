/**
 * api ext5 — WO_CLIENT_STATUS_TO_BACKEND ?? fallback (L211)
 * Target: unknown status string falls through to raw value
 */
import { workOrderApi } from '../api';

jest.mock('axios', () => {
  const mockAxios = {
    create: () => ({
      interceptors: {
        request: { use: jest.fn() },
        response: { use: jest.fn() },
      },
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      patch: jest.fn(),
      delete: jest.fn(),
    }),
  };
  return mockAxios;
});

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require('../api').default as jest.Mocked<{ get: jest.Mock }>;

describe('api ext5 — getList unknown status ?? fallback (L211)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('unknown status falls through to raw string via ??', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: { items: [], total: 0, page: 1, page_size: 20 },
      },
    });

    // 'cancelled' is NOT in WO_CLIENT_STATUS_TO_BACKEND → ?? fallback to raw
    await workOrderApi.getList({ status: 'cancelled' as never });

    expect(api.get).toHaveBeenCalledWith('/work-orders', expect.objectContaining({
      params: expect.objectContaining({ status: 'cancelled' }),
    }));
  });
});
