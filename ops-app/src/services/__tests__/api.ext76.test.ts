/**
 * api ext76 — mapper `??` fallback branch coverage
 *
 * Targets (empty-item `{}` + null-data cases so every `??` fallback path is hit):
 *  - teamApi.getList / getDetail
 *  - sparePartApi.getList / getById
 *  - alarmApi.getList / getDetail (pass-through, sanity only)
 *  - workOrderApi.getList / getDetail (mapWorkOrder)
 */
import { teamApi, sparePartApi, alarmApi, workOrderApi } from '../api';
import axios from 'axios';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  };
  return {
    create: jest.fn(() => mockInstance),
    __mockInstance: mockInstance,
  };
});

// F1205: any收窄 — mock工厂返回结构已知, 用具体Mock接口替代any
const mockAxios = (axios as unknown as { __mockInstance: { get: jest.Mock; post: jest.Mock; put: jest.Mock; delete: jest.Mock; patch: jest.Mock } }).__mockInstance;

const ok = (data: unknown) => ({ data: { code: 200, message: 'ok', data, timestamp: 1 } });

describe('ext76 teamApi mapper fallbacks', () => {
  beforeEach(() => jest.clearAllMocks());

  const TEAM_FALLBACK = {
    id: 0,
    name: '',
    code: null,
    leaderId: null,
    leaderName: null,
    description: null,
    memberCount: 0,
    stationCount: 0,
    status: 'active',
    createdAt: null,
  };

  it('teamApi.getList: empty item {} → all ?? fallbacks', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({ items: [{}] }));
    const res = await teamApi.getList();
    expect(res.code).toBe(200);
    expect(res.data.items).toHaveLength(1);
    expect(res.data.items[0]).toEqual(TEAM_FALLBACK);
    // total falls back to items.length
    expect(res.data.total).toBe(1);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  it('teamApi.getList: data null → null guard path', async () => {
    mockAxios.get.mockResolvedValueOnce(ok(null));
    const res = await teamApi.getList();
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  it('teamApi.getList: params {} without page/page_size → query ?? fallbacks', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({ items: [] }));
    const res = await teamApi.getList({});
    expect(mockAxios.get).toHaveBeenCalledWith('/teams?page=1&page_size=20');
    expect(res.data.items).toEqual([]);
  });

  it('teamApi.update: full body → all if-defined true branches', async () => {
    mockAxios.put.mockResolvedValueOnce(ok({}));
    const res = await teamApi.update(1, { name: 'n', description: 'd', leaderId: 5, status: 'active' });
    expect(mockAxios.put).toHaveBeenCalledWith('/teams/1', {
      name: 'n',
      description: 'd',
      leader_id: 5,
      status: 'active',
    });
    expect(res.data).toEqual(TEAM_FALLBACK);
  });

  it('teamApi.create: full body → code/description true branches', async () => {
    mockAxios.post.mockResolvedValueOnce(ok({}));
    const res = await teamApi.create({ name: 't', code: 'c', description: 'd' });
    expect(mockAxios.post).toHaveBeenCalledWith('/teams', { name: 't', code: 'c', description: 'd' });
    expect(res.data).toEqual(TEAM_FALLBACK);
  });

  it('teamApi.addMember: with role → role truthy branch', async () => {
    mockAxios.post.mockResolvedValueOnce(ok({}));
    await teamApi.addMember(1, 2, 'leader');
    expect(mockAxios.post).toHaveBeenCalledWith('/teams/1/members', { user_id: 2, role: 'leader' });
  });

  it('teamApi.getDetail: empty data {} → all ?? fallbacks', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({}));
    const res = await teamApi.getDetail(1);
    expect(res.data).toEqual(TEAM_FALLBACK);
  });

  it('teamApi.getDetail: data null → null guard path', async () => {
    mockAxios.get.mockResolvedValueOnce(ok(null));
    const res = await teamApi.getDetail(1);
    expect(res.data).toEqual(TEAM_FALLBACK);
  });

  it('teamApi.update: data null → mapper ?? fallbacks', async () => {
    mockAxios.put.mockResolvedValueOnce(ok(null));
    const res = await teamApi.update(1, {});
    expect(res.data).toEqual(TEAM_FALLBACK);
  });

  it('teamApi.create: data null → mapper ?? fallbacks', async () => {
    mockAxios.post.mockResolvedValueOnce(ok(null));
    const res = await teamApi.create({ name: 't' });
    expect(res.data).toEqual(TEAM_FALLBACK);
  });

  it('teamApi.addMember: data null → mapper ?? fallbacks', async () => {
    mockAxios.post.mockResolvedValueOnce(ok(null));
    const res = await teamApi.addMember(1, 2);
    expect(res.data).toEqual({
      id: 0,
      userId: 0,
      username: '',
      realName: null,
      teamId: 0,
      role: 'member',
      level: null,
      phone: null,
      status: 'active',
      joinDate: null,
    });
  });
});

describe('ext76 sparePartApi mapper fallbacks', () => {
  beforeEach(() => jest.clearAllMocks());

  const PART_FALLBACK = {
    id: 0,
    partName: '',
    partModel: null,
    totalQuantity: 0,
    availableQuantity: 0,
    warehouse: '',
    createdAt: '',
  };

  it('sparePartApi.getList: empty item {} → all ?? fallbacks', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({ items: [{}] }));
    const res = await sparePartApi.getList();
    expect(res.data.items).toHaveLength(1);
    expect(res.data.items[0]).toEqual(PART_FALLBACK);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  it('sparePartApi.getList: data null → null guard path', async () => {
    mockAxios.get.mockResolvedValueOnce(ok(null));
    const res = await sparePartApi.getList();
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
  });

  it('sparePartApi.getById: empty data {} → all ?? fallbacks', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({}));
    const res = await sparePartApi.getById(1);
    expect(res.data).toEqual(PART_FALLBACK);
  });

  it('sparePartApi.getById: data null → null guard path', async () => {
    mockAxios.get.mockResolvedValueOnce(ok(null));
    const res = await sparePartApi.getById(1);
    expect(res.data).toEqual(PART_FALLBACK);
  });
});

describe('ext76 alarmApi (pass-through)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('alarmApi.getList: returns data as-is', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({ items: [{}], total: 1 }));
    const res = await alarmApi.getList();
    expect(res.code).toBe(200);
    expect(res.data).toBeDefined();
    // F1205: any收窄 — pass-through data局部断言形态
    expect((res.data as { items: unknown[] }).items).toEqual([{}]);
  });

  it('alarmApi.getList: data null', async () => {
    mockAxios.get.mockResolvedValueOnce(ok(null));
    const res = await alarmApi.getList();
    expect(res.data).toBeNull();
  });

  it('alarmApi.getDetail: returns data as-is', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({ id: 7 }));
    const res = await alarmApi.getDetail(7);
    expect(res.data).toBeDefined();
    // F1205: any收窄 — pass-through data局部断言形态
    expect((res.data as { id: number }).id).toBe(7);
  });

  it('alarmApi.getDetail: data null', async () => {
    mockAxios.get.mockResolvedValueOnce(ok(null));
    const res = await alarmApi.getDetail(7);
    expect(res.data).toBeNull();
  });
});

describe('ext76 workOrderApi mapWorkOrder fallbacks', () => {
  beforeEach(() => jest.clearAllMocks());

  const WO_FALLBACK = {
    id: 'undefined',
    stationId: 0,
    stationName: '',
    title: '',
    description: '',
    type: 'repair',
    priority: 'normal',
    status: 'pending',
    assigneeId: undefined,
    assigneeName: undefined,
    creatorId: 999,
    creatorName: '',
    completedAt: undefined,
    createdAt: '',
    updatedAt: '',
    solution: undefined,
  };

  it('workOrderApi.getList: empty item {} → all ?? fallbacks', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({ items: [{}] }));
    const res = await workOrderApi.getList();
    expect(res.data.items).toHaveLength(1);
    expect(res.data.items[0]).toEqual(WO_FALLBACK);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  it('workOrderApi.getList: known status → mapped to backend status', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({ items: [] }));
    await workOrderApi.getList({ status: 'in_progress' });
    expect(mockAxios.get).toHaveBeenCalledWith('/work-orders', {
      params: expect.objectContaining({ status: 'processing' }),
    });
  });

  it('workOrderApi.getList: unknown status → passed through (?? fallback)', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({ items: [] }));
    await workOrderApi.getList({ status: 'whatever' });
    expect(mockAxios.get).toHaveBeenCalledWith('/work-orders', {
      params: expect.objectContaining({ status: 'whatever' }),
    });
  });

  it('workOrderApi.getList: data null → null guard path', async () => {
    mockAxios.get.mockResolvedValueOnce(ok(null));
    const res = await workOrderApi.getList();
    expect(res.data.items).toEqual([]);
    expect(res.data.total).toBe(0);
    expect(res.data.page).toBe(1);
    expect(res.data.pageSize).toBe(20);
  });

  it('workOrderApi.getDetail: empty data {} → all ?? fallbacks', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({}));
    const res = await workOrderApi.getDetail('1');
    expect(res.data).toEqual(WO_FALLBACK);
  });

  it('workOrderApi.getDetail: data null → mapWorkOrder rejects (no null guard)', async () => {
    mockAxios.get.mockResolvedValueOnce(ok(null));
    await expect(workOrderApi.getDetail('1')).rejects.toThrow();
  });
});
