/**
 * api ext82 — conditional branch coverage + more mapper truthy
 * Targets: if-branch truthy paths (body.X !== undefined),
 *   Array.isArray truthy paths, knowledgeApi.updateArticle/createFaq,
 *   roleApi.update, userApi.create, healingRuleApi.getList
 */
import {
  knowledgeApi,
  roleApi,
  userApi,
  healingRuleApi,
  healingExecutionApi,
  energyApi,
  reportApi,
  dashboardApi,
  notificationTemplateApi,
  pricingApi,
  inspectionPlanApi,
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

function ok(data: unknown) {
  return { data: { code: 200, message: 'ok', data } };
}

describe('ext82 — conditional branch + mapper truthy batch 2', () => {
  beforeEach(() => jest.clearAllMocks());

  // ---- knowledgeApi.updateArticle: all optional fields → if truthy ----
  it('knowledgeApi.updateArticle: full body → all if-branches true', async () => {
    mockAxios.put.mockResolvedValueOnce(ok({ id: 1, title: 'T', content: 'C', category_id: 2, tags: ['a', 'b'] }));
    await knowledgeApi.updateArticle(1, { title: 'T', content: 'C', categoryId: 2, tags: ['a', 'b'] });
    const arg = mockAxios.put.mock.calls[0][1];
    expect(arg).toMatchObject({ title: 'T', content: 'C', category_id: 2, tags: ['a', 'b'] });
  });

  // ---- knowledgeApi.createFaq: tags → if truthy ----
  it('knowledgeApi.createFaq: with tags → if-branch true', async () => {
    mockAxios.post.mockResolvedValueOnce(ok({ id: 1 }));
    await knowledgeApi.createFaq({ question: 'Q', answer: 'A', category: 'cat', tags: ['t1'] });
    const arg = mockAxios.post.mock.calls[0][1];
    expect(arg).toMatchObject({ question: 'Q', answer: 'A', category: 'cat', tags: ['t1'] });
  });

  // ---- roleApi.update: full body → all if-branches true ----
  it('roleApi.update: full body → all if-branches true', async () => {
    mockAxios.put.mockResolvedValueOnce(ok({ id: 1, name: 'R', display_name: 'DR' }));
    await roleApi.update(1, { displayName: 'DN', description: 'Desc', permissions: ['read', 'write'] });
    const arg = mockAxios.put.mock.calls[0][1];
    expect(arg).toMatchObject({ display_name: 'DN', description: 'Desc', permissions: ['read', 'write'] });
  });

  // ---- userApi.create: full body → all if-branches true ----
  it('userApi.create: full body → level + teamId if-branches true', async () => {
    mockAxios.post.mockResolvedValueOnce(ok({ id: 1, username: 'u' }));
    await userApi.create({
      username: 'u', password: 'p', realName: '张三', phone: '138',
      role: 'engineer', level: 'senior', teamId: 5,
    });
    const arg = mockAxios.post.mock.calls[0][1];
    expect(arg).toMatchObject({
      username: 'u', password: 'p', real_name: '张三', phone: '138',
      role: 'engineer', level: 'senior', team_id: 5,
    });
  });

  // ---- knowledgeApi.getFaqCategories: raw.data is array → Array.isArray true ----
  it('knowledgeApi.getFaqCategories: array response → Array.isArray true', async () => {
    mockAxios.get.mockResolvedValueOnce(ok([{ id: 1, name: 'Cat1', description: 'D1', faq_count: 3, sort_order: 1 }]));
    const res = await knowledgeApi.getFaqCategories();
    expect(res.data[0]).toMatchObject({ id: 1, name: 'Cat1', description: 'D1', faqCount: 3, sortOrder: 1 });
  });

  // ---- healingRuleApi.getList: raw.data is array → Array.isArray true ----
  it('healingRuleApi.getList: array response → Array.isArray true + full items', async () => {
    mockAxios.get.mockResolvedValueOnce(ok([{
      id: 1, name: 'Rule1', description: 'Desc',
      alarm_pattern: { severity: 'critical' },
      runbook_template: 'tpl1', auto_approve: true,
      max_retries: 3, cooldown_minutes: 30,
      priority: 'high', enabled: true,
      created_at: '2025-01-01', updated_at: '2025-06-01',
    }]));
    const res = await healingRuleApi.getList();
    expect(res.data[0]).toMatchObject({
      id: 1, name: 'Rule1', autoApprove: true, maxRetries: 3,
      cooldownMinutes: 30, priority: 'high', enabled: true,
    });
  });

  // ---- healingExecutionApi.getStats: full data ----
  it('healingExecutionApi.getStats: full data → all ?? truthy', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({
      total: 100,
      status_breakdown: { success: 80, failed: 10, pending: 10 },
      success_rate: 0.8,
      average_duration_ms: 5000,
      auto_approve_rate: 0.6,
      pending_approvals: 5,
    }));
    const res = await healingExecutionApi.getStats();
    expect(res.data).toMatchObject({
      total: 100, successRate: 0.8, averageDurationMs: 5000,
      autoApproveRate: 0.6, pendingApprovals: 5,
    });
  });

  // ---- energyApi.getSummary: full data ----
  it('energyApi.getSummary: full response → mapper ?? truthy', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({
      period: '2025-08', days: 30,
      pv_generation: 5000, charging_amount: 3000, discharge_amount: 1000,
      pv_revenue: 200, charging_revenue: 150, discharge_revenue: 50, total_revenue: 400,
      yoy: { pv_generation_yoy: 0.1, charging_amount_yoy: 0.2, discharge_amount_yoy: 0.05, total_revenue_yoy: 0.15 },
      price_info: { feed_in_tariff: 0.4, charging_price: 0.6, discharge_price: 0.5 },
    }));
    const res = await energyApi.getSummary();
    expect(res.data).toMatchObject({
      period: '2025-08', days: 30, pvGeneration: 5000,
      pvRevenue: 200, totalRevenue: 400,
      yoy: { pvGenerationYoY: 0.1, totalRevenueYoY: 0.15 },
      priceInfo: { feedInTariff: 0.4, chargingPrice: 0.6 },
    });
  });

  // ---- reportApi.getSummary: full data → mapper ?? truthy ----
  it('reportApi.getSummary: full response → nested mapper ?? truthy', async () => {
    mockAxios.get.mockResolvedValueOnce(ok({
      period_days: 30,
      overview: {
        total_devices: 50, online_devices: 45, offline_devices: 3,
        fault_devices: 2, maintenance_devices: 0,
        online_rate: 0.9, total_stations: 10,
        total_workorders: 20, completed_workorders: 18, completion_rate: 0.9,
        total_alarms: 5, active_alarms: 2,
      },
      station_health: {
        distribution: { normal: 8, warning: 1, critical: 1, offline: 0 },
        healthy_rate: 0.8,
      },
      team_performance: {
        engineers: [{ id: 1, name: '张三' }],
        total_engineers: 5,
        top_engineers: [{ id: 1, name: '张三', score: 95 }],
      },
    }));
    const res = await reportApi.getSummary();
    expect(res.data).toMatchObject({
      periodDays: 30,
      overview: { totalDevices: 50, onlineDevices: 45, onlineRate: 0.9, completionRate: 0.9 },
      stationHealth: { distribution: { normal: 8, warning: 1, critical: 1, offline: 0 }, healthyRate: 0.8 },
      teamPerformance: { totalEngineers: 5 },
    });
  });

  // ---- dashboardApi.getAlarmTrends: passthrough ----
  it('dashboardApi.getAlarmTrends: returns data directly', async () => {
    mockAxios.get.mockResolvedValueOnce({ data: { code: 200, message: 'ok', data: [{ date: '2025-01-01', count: 5 }] } });
    const res = await dashboardApi.getAlarmTrends({ days: 7 });
    expect(res.data).toHaveLength(1);
  });

  // ---- notificationTemplateApi.getList: full items ----
  it('notificationTemplateApi.getList: full items → mapper ?? truthy', async () => {
    const tpl = {
      id: 1, name: '模板A', channel: 'sms',
      subject: '告警通知', body: '设备异常',
      variables: ['device_name', 'alarm_msg'],
      enabled: true, created_at: '2025-01-01', updated_at: '2025-06-01',
    };
    mockAxios.get.mockResolvedValueOnce(ok({ items: [tpl], total: 1, page: 1, page_size: 20 }));
    const res = await notificationTemplateApi.getList();
    expect(res.data.items[0]).toMatchObject({
      name: '模板A', channel: 'sms', subject: '告警通知', enabled: true,
    });
  });

  // ---- pricingApi.getList: full items ----
  it('pricingApi.getList: full items → mapper ?? truthy', async () => {
    const price = {
      id: 1, name: '峰谷电价',
      period_type: 'peak', start_time: '10:00', end_time: '15:00',
      energy_price: 1.2, service_price: 0.1, power_limit: 7,
      enabled: true, created_at: '2025-01-01', updated_at: '2025-06-01',
    };
    mockAxios.get.mockResolvedValueOnce(ok({ items: [price], total: 1, page: 1, page_size: 20 }));
    const res = await pricingApi.getList();
    expect(res.data.items[0]).toMatchObject({
      name: '峰谷电价', periodType: 'peak', startTime: '10:00', enabled: true,
    });
  });

  // ---- inspectionPlanApi.getList: full items ----
  it('inspectionPlanApi.getList: full items → mapper ?? truthy', async () => {
    const plan = {
      id: 1, name: '月度巡检', station_id: 5, station_name: '站A',
      device_id: 3, device_name: '逆变器',
      type: 'monthly', status: 'in_progress',
      scheduled_date: '2025-09-01', cycle: 'monthly',
      assigned_to: 7, assigned_name: '李四',
      template_id: 2, description: '月度例行',
      created_at: '2025-01-01', updated_at: '2025-06-01',
    };
    mockAxios.get.mockResolvedValueOnce(ok({ items: [plan], total: 1, page: 1, page_size: 20 }));
    const res = await inspectionPlanApi.getList();
    expect(res.data.items[0]).toMatchObject({
      name: '月度巡检', stationId: 5, stationName: '站A',
      type: 'monthly', status: 'in_progress',
      assignedTo: 7, assignedName: '李四', templateId: 2,
    });
  });
});
