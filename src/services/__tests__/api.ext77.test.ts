/**
 * api ext77 — mapper fallback branches batch 4
 * Targets: inspectionPlanApi.getList, inspectionTemplateApi.getList/create,
 *   tariffApi.getList, notificationRuleApi.create
 */
import {
  inspectionPlanApi,
  inspectionTemplateApi,
  notificationRuleApi,
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

// F1205: any收窄 — mock工厂返回结构已知, 用具体Mock接口替代any
const mockAxios = (axios as unknown as { __mockInstance: { get: jest.Mock; post: jest.Mock; put: jest.Mock; delete: jest.Mock; patch: jest.Mock } }).__mockInstance;

describe('ext77 — mapper fallback branch coverage batch 4', () => {
  beforeEach(() => jest.clearAllMocks());

  // inspectionPlanApi.getList — items [{}] → fallback
  it('inspectionPlanApi.getList: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await inspectionPlanApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0,
      name: '',
      stationId: 0,
      stationName: '',
      deviceId: undefined,
      deviceName: undefined,
      type: 'daily',
      status: 'pending',
      scheduledDate: '',
      cycle: undefined,
      assignedTo: undefined,
      assignedName: undefined,
      templateId: undefined,
      description: undefined,
      createdAt: '',
      updatedAt: '',
    });
  });

  // inspectionPlanApi.getList — data null → fallback
  it('inspectionPlanApi.getList: data null → empty', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await inspectionPlanApi.getList();
    expect(res.data.items).toEqual([]);
  });

  // inspectionTemplateApi.getList — items [{}] → fallback (nested items map)
  it('inspectionTemplateApi.getList: items [{}] → fallback', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await inspectionTemplateApi.getList();
    expect(res.data.items[0]).toEqual({
      id: 0,
      name: '',
      description: null,
      items: [],
      itemCount: 0,
      deviceTypes: [],
      target: null,
      status: 'active',
      createdAt: '',
      updatedAt: '',
    });
  });

  // inspectionTemplateApi.create — data {} → fallback
  it('inspectionTemplateApi.create: data {} → fallback', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await inspectionTemplateApi.create({ name: 'test' });
    expect(res.data).toEqual({
      id: 0,
      name: '',
      description: null,
      items: [],
      itemCount: 0,
      deviceTypes: [],
      target: null,
      status: 'active',
      createdAt: '',
      updatedAt: '',
    });
  });

  // inspectionTemplateApi.create — data null → fallback
  it('inspectionTemplateApi.create: data null → fallback', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await inspectionTemplateApi.create({ name: 'test' });
    expect(res.data).toEqual({
      id: 0,
      name: '',
      description: null,
      items: [],
      itemCount: 0,
      deviceTypes: [],
      target: null,
      status: 'active',
      createdAt: '',
      updatedAt: '',
    });
  });

  // notificationRuleApi.create — data {} → fallback
  it('notificationRuleApi.create: data {} → fallback', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await notificationRuleApi.create({
      name: 'test',
      level: 'info',
    });
    expect(res.data).toEqual({
      id: 0,
      name: '',
      level: '',
      channels: [],
      receivers: [],
      enabled: false,
      createdAt: '',
      updatedAt: null,
    });
  });

  // notificationRuleApi.create — data null → null
  it('notificationRuleApi.create: data null → null', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await notificationRuleApi.create({
      name: 'test',
      level: 'info',
    });
    expect(res.data).toBeNull();
  });
});
