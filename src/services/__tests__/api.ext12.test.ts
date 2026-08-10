/**
 * api ext12 — SparePart API (GET /spare-parts)
 * Target: snake_case → camelCase mapping for spare parts inventory
 */
import { sparePartApi } from '../api';

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

describe('sparePartApi.getList() — GET /spare-parts', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase SparePart items', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            {
              id: 1,
              name: '继电器',
              model: 'JQC-3FF',
              manufacturer: '松下',
              stock_qty: 50,
              unit: '个',
              price: 12.5,
              warehouse: '北京仓',
              location: 'A-3-01',
              safety_stock: 10,
              status: 'normal',
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-02-01T00:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        },
        timestamp: 1786359645,
      },
    });

    const res = await sparePartApi.getList({ page: 1, pageSize: 20 });

    expect(api.get).toHaveBeenCalledWith('/spare-parts', {
      params: { page: 1, page_size: 20 },
    });
    expect(res.code).toBe(200);
    expect(res.data.total).toBe(1);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);

    const item = res.data.items[0];
    expect(item.id).toBe(1);
    expect(item.name).toBe('继电器');
    expect(item.model).toBe('JQC-3FF');
    expect(item.manufacturer).toBe('松下');
    expect(item.stockQty).toBe(50);
    expect(item.unit).toBe('个');
    expect(item.price).toBe(12.5);
    expect(item.warehouse).toBe('北京仓');
    expect(item.location).toBe('A-3-01');
    expect(item.safetyStock).toBe(10);
    expect(item.status).toBe('normal');
    expect(item.createdAt).toBe('2026-01-01T00:00:00Z');
    expect(item.updatedAt).toBe('2026-02-01T00:00:00Z');
  });

  it('handles empty items array', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 1, page_size: 20 },
        timestamp: 0,
      },
    });

    const res = await sparePartApi.getList();

    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  it('applies fallback defaults for missing fields', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { items: [{}], total: 1 },
        timestamp: 0,
      },
    });

    const res = await sparePartApi.getList({ page: 2, pageSize: 5 });

    const item = res.data.items[0];
    expect(item.id).toBe(0);
    expect(item.name).toBe('');
    expect(item.model).toBe('');
    expect(item.manufacturer).toBe('');
    expect(item.stockQty).toBe(0);
    expect(item.unit).toBe('');
    expect(item.price).toBe(0);
    expect(item.warehouse).toBe('');
    expect(item.location).toBe('');
    expect(item.safetyStock).toBe(0);
    expect(item.status).toBe('');
    expect(item.createdAt).toBe('');
    expect(item.updatedAt).toBe('');
  });

  it('handles null data gracefully', async () => {
    api.get.mockResolvedValue({
      data: { code: 200, data: null },
    });

    const res = await sparePartApi.getList();

    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
  });

  it('passes custom pagination params', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        data: { items: [], total: 0, page: 3, page_size: 50 },
      },
    });

    await sparePartApi.getList({ page: 3, pageSize: 50 });

    expect(api.get).toHaveBeenCalledWith('/spare-parts', {
      params: { page: 3, page_size: 50 },
    });
  });
});
