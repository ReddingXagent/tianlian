/**
 * api ext12 — SparePart API (GET /spare-parts, GET /spare-parts/{id}, POST, DELETE)
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

const api = require('../api').default as jest.Mocked<{
  get: jest.Mock;
  post: jest.Mock;
  delete: jest.Mock;
}>;

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
              part_name: '继电器',
              part_model: 'JQC-3FF',
              total_quantity: 50,
              available_quantity: 45,
              warehouse: '北京仓',
              created_at: '2026-01-01T00:00:00Z',
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
    expect(item.partName).toBe('继电器');
    expect(item.partModel).toBe('JQC-3FF');
    expect(item.totalQuantity).toBe(50);
    expect(item.availableQuantity).toBe(45);
    expect(item.warehouse).toBe('北京仓');
    expect(item.createdAt).toBe('2026-01-01T00:00:00Z');
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
    expect(item.partName).toBe('');
    expect(item.partModel).toBeNull();
    expect(item.totalQuantity).toBe(0);
    expect(item.availableQuantity).toBe(0);
    expect(item.warehouse).toBe('');
    expect(item.createdAt).toBe('');
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

describe('sparePartApi.getById() — GET /spare-parts/{id}', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case → camelCase for single item', async () => {
    api.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 5,
          part_name: '电容',
          part_model: 'CD-100UF',
          total_quantity: 100,
          available_quantity: 80,
          warehouse: '上海仓',
          created_at: '2026-03-01T00:00:00Z',
        },
        timestamp: 0,
      },
    });

    const res = await sparePartApi.getById(5);

    expect(api.get).toHaveBeenCalledWith('/spare-parts/5');
    expect(res.data.id).toBe(5);
    expect(res.data.partName).toBe('电容');
    expect(res.data.partModel).toBe('CD-100UF');
    expect(res.data.totalQuantity).toBe(100);
    expect(res.data.availableQuantity).toBe(80);
    expect(res.data.warehouse).toBe('上海仓');
  });

  it('applies defaults for empty object', async () => {
    api.get.mockResolvedValue({
      data: { code: 200, data: {} },
    });

    const res = await sparePartApi.getById(1);

    expect(res.data.id).toBe(0);
    expect(res.data.partName).toBe('');
    expect(res.data.partModel).toBeNull();
    expect(res.data.totalQuantity).toBe(0);
    expect(res.data.availableQuantity).toBe(0);
  });
});

describe('sparePartApi.create() — POST /spare-parts', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sends partName in body and maps response', async () => {
    api.post.mockResolvedValue({
      data: {
        code: 200,
        message: '备件已登记入库',
        data: {
          id: 10,
          part_name: '电阻',
          part_model: null,
          total_quantity: 0,
          available_quantity: 0,
          warehouse: 'WH-01',
          created_at: '2026-08-13T06:15:42+08:00',
        },
        timestamp: 0,
      },
    });

    const res = await sparePartApi.create({
      partName: '电阻',
      warehouse: 'WH-01',
    });

    expect(api.post).toHaveBeenCalledWith('/spare-parts', {
      partName: '电阻',
      warehouse: 'WH-01',
    });
    expect(res.data.id).toBe(10);
    expect(res.data.partName).toBe('电阻');
    expect(res.data.warehouse).toBe('WH-01');
  });

  it('handles null data response', async () => {
    api.post.mockResolvedValue({
      data: { code: 200, data: null },
    });

    const res = await sparePartApi.create({ partName: 'test' });

    expect(res.data.id).toBe(0);
    expect(res.data.partName).toBe('');
  });
});

describe('sparePartApi.delete() — DELETE /spare-parts/{id}', () => {
  beforeEach(() => jest.clearAllMocks());

  it('calls DELETE with correct id', async () => {
    api.delete.mockResolvedValue({
      data: {
        code: 200,
        message: '备件已删除',
        data: null,
        timestamp: 0,
      },
    });

    const res = await sparePartApi.delete(3);

    expect(api.delete).toHaveBeenCalledWith('/spare-parts/3');
    expect(res.code).toBe(200);
    expect(res.data).toBeNull();
  });
});
