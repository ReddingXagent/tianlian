/**
 * api ext70 — DELETE endpoints: alarmRule / notificationRule / inspectionTemplate /
 * notificationTemplate / knowledgeCategory
 */
import {
  alarmRuleApi,
  notificationRuleApi,
  inspectionTemplateApi,
  notificationTemplateApi,
  knowledgeApi,
} from '../api';
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

const mockAxios = (axios as unknown as { __mockInstance: Record<string, jest.Mock> }).__mockInstance;

describe('ext70 — DELETE endpoints batch', () => {
  beforeEach(() => jest.clearAllMocks());

  it('alarmRuleApi.delete → DELETE /alarm-rules/:id', async () => {
    mockAxios.delete.mockResolvedValueOnce({
      data: { code: 200, message: '告警规则已删除', data: null },
    });
    const res = await alarmRuleApi.delete(1);
    expect(mockAxios.delete).toHaveBeenCalledWith('/alarm-rules/1');
    expect(res.code).toBe(200);
    expect(res.data).toBeNull();
  });

  it('notificationRuleApi.delete → DELETE /notification-rules/:id', async () => {
    mockAxios.delete.mockResolvedValueOnce({
      data: { code: 200, message: '规则 1 已删除', data: null },
    });
    const res = await notificationRuleApi.delete(1);
    expect(mockAxios.delete).toHaveBeenCalledWith('/notification-rules/1');
    expect(res.code).toBe(200);
  });

  it('inspectionTemplateApi.delete → DELETE /inspection/templates/:id', async () => {
    mockAxios.delete.mockResolvedValueOnce({
      data: { code: 200, message: '模板 1 已删除', data: null },
    });
    const res = await inspectionTemplateApi.delete(1);
    expect(mockAxios.delete).toHaveBeenCalledWith('/inspection/templates/1');
    expect(res.code).toBe(200);
  });

  it('notificationTemplateApi.delete → DELETE /notifications/templates/:id', async () => {
    mockAxios.delete.mockResolvedValueOnce({
      data: { code: 200, message: '模板已删除', data: null },
    });
    const res = await notificationTemplateApi.delete(1);
    expect(mockAxios.delete).toHaveBeenCalledWith('/notifications/templates/1');
    expect(res.code).toBe(200);
  });

  it('knowledgeApi.deleteCategory → DELETE /knowledge/categories/:id', async () => {
    mockAxios.delete.mockResolvedValueOnce({
      data: { code: 200, message: "分类 'test-cat' 已删除", data: null },
    });
    const res = await knowledgeApi.deleteCategory(1);
    expect(mockAxios.delete).toHaveBeenCalledWith('/knowledge/categories/1');
    expect(res.code).toBe(200);
  });
});
