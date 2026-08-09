/**
 * api.ts ext4 — workOrderApi.getList fallback branches
 * Lines 211, 216, 221, 222: ?? fallback operators when rawPage fields are missing
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

// Access the mocked api instance via require to avoid duplicate import warnings
// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require('../api').default as jest.Mocked<{
  get: jest.Mock;
}>;

describe('workOrderApi.getList fallback branches', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('uses fallback values when rawPage has no items/total/page/page_size', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: {},
      },
    });

    const result = await workOrderApi.getList({ page: 3, pageSize: 50 });

    expect(result.data.items).toEqual([]);
    expect(result.data.total).toBe(0);
    expect(result.data.page).toBe(3);
    expect(result.data.pageSize).toBe(50);
  });

  it('uses default page=1 and pageSize=20 when params not provided and rawPage empty', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: null,
      },
    });

    const result = await workOrderApi.getList();

    expect(result.data.page).toBe(1);
    expect(result.data.pageSize).toBe(20);
  });

  it('maps rawPage items correctly when present', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: {
          items: [{
            id: 1, title: 'test', description: 'desc', status: 'pending',
            priority: 'high', type: 'fault', station_id: 1, station_name: 'S1',
            creator_id: 1, creator_name: 'admin', assignee_id: null, assignee_name: null,
            created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
          }],
          total: 1,
          page: 1,
          page_size: 20,
        },
      },
    });

    const result = await workOrderApi.getList({ page: 1, pageSize: 20 });
    expect(result.data.items).toHaveLength(1);
    expect(result.data.total).toBe(1);
  });
});
