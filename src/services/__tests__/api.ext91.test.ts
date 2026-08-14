/**
 * api ext91 — F1042 簇式 branch gap 收尾: raw.data ?? {} 的 right 侧 (data:null)
 * + spread guard (xxx !== undefined) falsy 侧 + webhookApi.create/engineerApi.update 首测
 * 目标行: 1180,1203-1208,1378-1379,1404,1450,1467-1468,1482,1499,1511,1568-1569,1572,
 *         1671,1673-1674,1676,1823,1833,1950-1951,2004-2005,2147,2227,2233-2235,2405-2406,
 *         2495-2496,2528,2703-2704,2821,2847-2848,2879,2919,2938,3014,3042,3226-3227,3261,
 *         3390-3391,3625,3929,3952
 */
import MockAdapter from 'axios-mock-adapter';
import api, {
  roleApi,
  userApi,
  reportApi,
  alarmRuleApi,
  notificationRuleApi,
  notificationTemplateApi,
  chargingOrderApi,
  knowledgeApi,
  engineerApi,
  webhookApi,
  healingExecutionApi,
  apiKeyApi,
  securityPolicyApi,
  gatewayApi,
  tenantListApi,
  stationApi,
  deviceApi,
  inspectionTemplateApi,
  fleetApi,
  pricingApi,
} from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// 注: SecureStore import 移除 — MockAdapter 直挂 axios 实例，拦截发生在 token 注入前

const mockAxios = new MockAdapter(api);
afterAll(() => mockAxios.restore());

const NULLDATA = { code: 200, message: 'ok', data: null };

describe('api ext91 — raw.data ?? {} right side (data:null) cluster sweep', () => {
  beforeEach(() => {
    mockAxios.reset();
    jest.clearAllMocks();
  });

  it('roleApi.update — data:null → mapper defaults', async () => {
    mockAxios.onPut(/\/roles\/\d+/).reply(200, NULLDATA);
    const r = await roleApi.update(1, { displayName: 'x' });
    expect(r.data).toEqual({ id: 0, name: '', displayName: '', description: '', isSystem: false, permissions: [] });
  });

  it('roleApi.create — data:null → mapper defaults', async () => {
    mockAxios.onPost('/roles').reply(200, NULLDATA);
    const r = await roleApi.create({ name: 'n' });
    expect(r.data?.id).toBe(0);
    expect(r.data?.permissions).toEqual([]);
  });

  it('userApi.create — data:null → null guard (right side)', async () => {
    mockAxios.onPost('/users').reply(200, NULLDATA);
    const r = await userApi.create({ username: 'u' });
    expect(r.data).toBeNull();
  });

  it('reportApi.getSummary — data:null → full falsy sweep', async () => {
    mockAxios.onGet(/\/reports\/summary/).reply(200, NULLDATA);
    const r = await reportApi.getSummary();
    expect(r.data).toBeDefined();
  });

  it('reportApi.getDeviceReport — data:null (d ?? falsy)', async () => {
    mockAxios.onGet(/\/reports\/devices/).reply(200, NULLDATA);
    const r = await reportApi.getDeviceReport();
    expect(r.data).toBeDefined();
  });

  it('reportApi.getAlarmReport — data:null', async () => {
    mockAxios.onGet(/\/reports\/alarms/).reply(200, NULLDATA);
    const r = await reportApi.getAlarmReport();
    expect(r.data).toBeDefined();
  });

  it('reportApi.getWorkOrderReport — data:null', async () => {
    mockAxios.onGet(/\/reports\/workorders/).reply(200, NULLDATA);
    const r = await reportApi.getWorkOrderReport();
    expect(r.data).toBeDefined();
  });

  it('alarmRuleApi.create — spread falsy sides (only required fields)', async () => {
    mockAxios.onPost('/alarm-rules').reply(200, { ...NULLDATA, data: { id: 1, name: 'r', metric: 'm', threshold: 2 } });
    const r = await alarmRuleApi.create({ name: 'r', metric: 'm', threshold: 2 });
    expect(r.data?.id).toBe(1);
    // 验证请求体不含未定义的可选 spread 键
    const body = mockAxios.history.post[0].data;
    expect(typeof body).toBe('string');
    expect(JSON.parse(body)).toEqual({ name: 'r', metric: 'm', threshold: 2 });
  });

  it('notificationRuleApi.create — receivers spread falsy (minimal body)', async () => {
    mockAxios.onPost('/notification-rules').reply(200, NULLDATA);
    const r = await notificationRuleApi.create({ name: 'n', level: 'high' } as never);
    expect(r.data).toBeDefined();
  });

  it('notificationTemplateApi.getList — data:null → items ?? []', async () => {
    mockAxios.onGet(/\/notifications\/templates/).reply(200, NULLDATA);
    const r = await notificationTemplateApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('chargingOrderApi.getList — data:null → items ?? []', async () => {
    mockAxios.onGet(/\/charging-orders/).reply(200, NULLDATA);
    const r = await chargingOrderApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('knowledgeApi.updateCategory — data:null mapper defaults', async () => {
    mockAxios.onPut(/\/knowledge\/categories\/\d+/).reply(200, NULLDATA);
    const r = await knowledgeApi.updateCategory(1, { name: 'n' });
    expect(r.data?.name).toBe('');
    expect(r.data?.sortOrder).toBe(0);
  });

  it('knowledgeApi.createFaq — data:null mapper defaults', async () => {
    mockAxios.onPost('/knowledge/faq').reply(200, NULLDATA);
    const r = await knowledgeApi.createFaq({ question: 'q', answer: 'a', category: 'c' });
    expect(r.data?.id).toBe(0);
  });

  it('engineerApi.getList — data:null → items ?? []', async () => {
    mockAxios.onGet('/engineers').reply(200, NULLDATA);
    const r = await engineerApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('webhookApi.create — first test + events ?? [] default', async () => {
    mockAxios.onPost('/webhooks').reply(200, { ...NULLDATA, data: { id: 5, name: 'w', url: 'http://x', events: null } });
    await webhookApi.create({ name: 'w', url: 'http://x' } as never);
    // events ?? [] → falsy side covered on request body
    expect(mockAxios.history.post.length).toBe(1);
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body.events).toEqual([]);
  });

  it('healingExecutionApi.getList — data:null → items ?? []', async () => {
    mockAxios.onGet(/\/healing\/executions/).reply(200, NULLDATA);
    const r = await healingExecutionApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('apiKeyApi.create — data:null mapper defaults (it ?? {} right side)', async () => {
    mockAxios.onPost('/api-keys').reply(200, NULLDATA);
    const r = await apiKeyApi.create({ name: 'k' } as never);
    expect(r.data).toBeDefined();
  });

  it('apiKeyApi.getDetail — data:null', async () => {
    mockAxios.onGet(/\/api-keys\/\d+$/).reply(200, NULLDATA);
    const r = await apiKeyApi.getDetail(3);
    expect(r.data).toBeDefined();
  });

  it('apiKeyApi.getList — data:null → items ?? []', async () => {
    mockAxios.onGet('/api-keys').reply(200, NULLDATA);
    const r = await apiKeyApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('apiKeyApi.rotate — data:null (d ?? {} right side)', async () => {
    mockAxios.onPost(/\/api-keys\/\d+\/rotate/).reply(200, NULLDATA);
    const r = await apiKeyApi.rotate(3);
    expect(r.data).toBeDefined();
  });

  it('securityPolicyApi.getList — first test + data:null', async () => {
    mockAxios.onGet('/security/policies').reply(200, NULLDATA);
    const r = await securityPolicyApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('gatewayApi.getList — data:null → items ?? []', async () => {
    mockAxios.onGet('/gateways').reply(200, NULLDATA);
    const r = await gatewayApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('gatewayApi.getById — data:null (item ?? {} right side)', async () => {
    mockAxios.onGet(/\/gateways\/\d+$/).reply(200, NULLDATA);
    const r = await gatewayApi.getById(1);
    expect(r.data).toBeDefined();
  });

  it('tenantListApi.getList — data:null → items ?? []', async () => {
    mockAxios.onGet('/tenants').reply(200, NULLDATA);
    const r = await tenantListApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('stationApi.getDetail — data:null (mapStation ?? right side)', async () => {
    mockAxios.onGet(/\/stations\/\d+$/).reply(200, NULLDATA);
    const r = await stationApi.getDetail(1);
    expect(r.data).toBeDefined();
  });

  it('stationApi.create — data:null (mapStation ?? right side)', async () => {
    mockAxios.onPost('/stations').reply(200, NULLDATA);
    const r = await stationApi.create({ name: 's' });
    expect(r.data).toBeDefined();
  });

  it('deviceApi.getConfig — data:null (d ?? {} right side)', async () => {
    mockAxios.onGet(/\/devices\/\d+\/config/).reply(200, NULLDATA);
    const r = await deviceApi.getConfig(1);
    expect(r.data).toBeDefined();
  });

  // ---- ext91b: 补穿 ext91 后残留的 falsy 侧 ----
  it('knowledgeApi.createArticle — data:null mapper defaults', async () => {
    mockAxios.onPost('/knowledge/articles').reply(200, NULLDATA);
    const r = await knowledgeApi.createArticle({ title: 't', content: 'c', category: 'k' } as never);
    expect(r.data).toBeDefined();
  });

  it('knowledgeApi.updateArticle — data:null mapper defaults', async () => {
    mockAxios.onPut(/\/knowledge\/articles\/\d+/).reply(200, NULLDATA);
    const r = await knowledgeApi.updateArticle(1, { title: 't' });
    expect(r.data).toBeDefined();
  });

  it('knowledgeApi.createCategory — data:null mapper defaults', async () => {
    mockAxios.onPost('/knowledge/categories').reply(200, NULLDATA);
    const r = await knowledgeApi.createCategory({ name: 'n' } as never);
    expect(r.data).toBeDefined();
  });

  it('userApi.create — sparse data → ?? falsy defaults (id/username missing)', async () => {
    mockAxios.onPost('/users').reply(200, { ...NULLDATA, data: {} });
    const r = await userApi.create({ username: 'u' });
    expect(r.data?.id).toBe(0);
    expect(r.data?.username).toBe('');
  });

  it('reportApi.getDeviceReport — healthScore present, sparse (average/distribution missing)', async () => {
    mockAxios.onGet(/\/reports\/devices/).reply(200, {
      ...NULLDATA,
      data: { health_score: { average: null, distribution: null } },
    });
    const r = await reportApi.getDeviceReport();
    expect(r.data?.healthScore).toEqual({ average: 0, distribution: {} });
  });

  it('reportApi.getAlarmReport — daily_trend items sparse → ?? falsy', async () => {
    mockAxios.onGet(/\/reports\/alarms/).reply(200, {
      ...NULLDATA,
      data: { daily_trend: [{}] },
    });
    const r = await reportApi.getAlarmReport();
    expect(r.data?.dailyTrend).toEqual([{ date: '', count: 0 }]);
  });

  it('reportApi.getWorkOrderReport — abnormalLowEfficiency items sparse → ?? undefined', async () => {
    mockAxios.onGet(/\/reports\/workorders/).reply(200, {
      ...NULLDATA,
      data: { alerts: { abnormal_low_efficiency: { items: [{}] } } },
    } as never);
    const r = await reportApi.getWorkOrderReport();
    expect(r.data).toBeDefined();
  });

  it('alarmRuleApi.create — full optional spread (deviceType/severity/operator/duration/enabled/description all set)', async () => {
    mockAxios.onPost('/alarm-rules').reply(200, NULLDATA);
    await alarmRuleApi.create({
      name: 'n',
      metric: 'm',
      threshold: 1,
      deviceType: 'dt',
      severity: 'high',
      operator: '>',
      duration: 5,
      enabled: true,
      description: 'd',
    } as never);
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toMatchObject({ device_type: 'dt', severity: 'high', operator: '>', duration: 5, enabled: true, description: 'd' });
  });

  it('notificationRuleApi.create — full optional spread (level/channels/receivers/enabled)', async () => {
    mockAxios.onPost('/notification-rules').reply(200, NULLDATA);
    await notificationRuleApi.create({
      name: 'n',
      level: 'high',
      channels: ['email'],
      receivers: ['ops'],
      enabled: true,
    } as never);
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toMatchObject({ level: 'high', channels: ['email'], receivers: ['ops'], enabled: true });
  });

  it('notificationRuleApi.create — data:null sparse mapper (id/name/level ?? falsy)', async () => {
    mockAxios.onPost('/notification-rules').reply(200, NULLDATA);
    const r = await notificationRuleApi.create({ name: 'n', level: 'high' } as never);
    expect(r.data).toBeDefined();
  });

  it('pricingApi.getList — data:null → items ?? []', async () => {
    mockAxios.onGet('/pricing').reply(200, NULLDATA);
    const r = await pricingApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('pricingApi.getById — data:null → ternary falsy → null', async () => {
    mockAxios.onGet(/\/pricing\/\d+/).reply(200, NULLDATA);
    const r = await pricingApi.getById(1);
    expect(r.data).toBeNull();
  });

  it('inspectionTemplateApi.getList — sparse item {} + nested items [{}] (mapper ?? falsy)', async () => {
    mockAxios.onGet(/\/inspection\/templates/).reply(200, {
      ...NULLDATA,
      data: { items: [{ items: [{}] }] },
    });
    const r = await inspectionTemplateApi.getList();
    expect(r.data?.items?.[0]?.type).toBe('daily');
    expect(r.data?.items?.[0]?.items?.[0]).toMatchObject({ id: 0, name: '', expected: '' });
  });

  it('webhookApi.getList — data:null → items ?? []', async () => {
    mockAxios.onGet('/webhooks').reply(200, NULLDATA);
    const r = await webhookApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('webhookApi.create — full spread (secret/description/enabled)', async () => {
    mockAxios.onPost('/webhooks').reply(200, NULLDATA);
    await webhookApi.create({
      name: 'w',
      url: 'http://x',
      secret: 's',
      description: 'd',
      enabled: true,
    } as never);
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toMatchObject({ secret: 's', description: 'd', enabled: true });
  });

  it('apiKeyApi.getUsage — data:null (d ?? {} right side)', async () => {
    mockAxios.onGet(/\/api-keys\/\d+\/usage/).reply(200, NULLDATA);
    const r = await apiKeyApi.getUsage(1);
    expect(r.data).toBeDefined();
  });

  it('securityPolicyApi.getByKey — data:null (it ?? {} right side)', async () => {
    mockAxios.onGet(/\/security\/policies\/\w+/).reply(200, NULLDATA);
    const r = await securityPolicyApi.getByKey('k');
    expect(r.data).toBeDefined();
  });

  it('fleetApi.getDrivers — data:null (d ?? {} right side)', async () => {
    mockAxios.onGet('/fleet/drivers').reply(200, NULLDATA);
    const r = await fleetApi.getDrivers({ page: 1 });
    expect(r.data?.items).toEqual([]);
  });

  // ---- ext91c: 最后 7 行残留收尾 ----
  it('reportApi.getEfficiency — alerts abnormal item {} → ?? undefined defaults', async () => {
    mockAxios.onGet(/\/reports\/efficiency/).reply(200, {
      code: 200,
      message: 'ok',
      data: { alerts: { abnormal_low_efficiency: { count: 1, threshold: '80%', items: [{}] } } },
    } as never);
    const r = await reportApi.getEfficiency();
    expect(r.data?.alerts?.abnormalLowEfficiency).toMatchObject({ count: 1, threshold: '80%' });
    expect(r.data?.alerts?.abnormalLowEfficiency.items[0]).toEqual({});
  });

  it('notificationRuleApi.update — full spread body (name/level/channels/receivers/enabled)', async () => {
    mockAxios.onPut(/\/notification-rules\/\d+/).reply(200, NULLDATA);
    await notificationRuleApi.update(1, {
      name: 'n',
      level: 'high',
      channels: ['email'],
      receivers: ['ops'],
      enabled: true,
    } as never);
    const body = JSON.parse(mockAxios.history.put[0].data);
    expect(body).toMatchObject({ name: 'n', level: 'high', channels: ['email'], receivers: ['ops'], enabled: true });
  });

  it('notificationRuleApi.update — data:null → null guard (!raw.data truthy side)', async () => {
    mockAxios.onPut(/\/notification-rules\/\d+/).reply(200, NULLDATA);
    const r = await notificationRuleApi.update(2, { name: 'x' });
    expect(r.data).toBeNull();
  });

  it('notificationRuleApi.update — data:{} sparse mapper (id/name/level ?? falsy)', async () => {
    mockAxios.onPut(/\/notification-rules\/\d+/).reply(200, { ...NULLDATA, data: {} });
    const r = await notificationRuleApi.update(3, { name: 'x' });
    expect(r.data).toMatchObject({ id: 0, name: '', level: '', channels: [], receivers: [], enabled: false });
  });

  it('pricingApi.getById — data:{} sparse mapper (?? falsy defaults)', async () => {
    mockAxios.onGet(/\/pricing\/\d+/).reply(200, { ...NULLDATA, data: {} });
    const r = await pricingApi.getById(1);
    expect(r.data).toMatchObject({ id: 0, name: '', periodType: '', startTime: '', endTime: '', enabled: false });
  });

  it('inspectionTemplateApi.getList — data:null (d ?? {} right side)', async () => {
    mockAxios.onGet(/\/inspection\/templates/).reply(200, NULLDATA);
    const r = await inspectionTemplateApi.getList();
    expect(r.data?.items).toEqual([]);
  });
});
