/**
 * api ext84 — mapper fallback branch coverage batch 1
 * Strategy: empty/partial payloads exercise ?? fallback sides on dense mapper lines
 */
import MockAdapter from 'axios-mock-adapter';
import api, {
  knowledgeApi,
  permissionApi,
  reportApi,
  alarmRuleApi,
  notificationTemplateApi,
  pricingApi,
  inspectionTemplateApi,
  webhookApi,
  healingRuleApi,
  healingExecutionApi,
  apiKeyApi,
  securityPolicyApi,
  gatewayApi,
  tenantListApi,
  fleetApi,
  healthApi,
  stationApi,
} from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);
afterAll(() => mockAxios.restore());

describe('api ext84 — mapper fallback batch 1 (empty payloads)', () => {
  it('knowledgeApi.getArticles — empty item / undefined fields hit ?? fallbacks', async () => {
    mockAxios.onGet(/\/knowledge\/articles/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await knowledgeApi.getArticles({ page: 2 });
    expect(r.data?.items[0]).toEqual({
      id: 0, title: '', content: '', summary: '', categoryId: 0, categoryName: undefined,
      tags: [], author: '', viewCount: 0, status: 'draft', createdAt: '', updatedAt: '',
    });

    mockAxios.onGet(/\/knowledge\/articles/).reply(200, { code: 200, message: 'ok', data: { items: undefined, total: undefined, page: undefined, page_size: undefined } });
    const r2 = await knowledgeApi.getArticles();
    expect(r2.data?.items).toEqual([]);
    expect(r2.data?.total).toBe(0);
    expect(r2.data?.page).toBe(1);
    expect(r2.data?.pageSize).toBe(20);
  });

  it('knowledgeApi.getFaq — array vs items-wrapper vs empty', async () => {
    mockAxios.onGet('/knowledge/faq').reply(200, { code: 200, message: 'ok', data: [{}] });
    const r = await knowledgeApi.getFaq();
    expect(r.data?.[0]).toEqual({ id: 0, question: '', answer: '', categoryId: undefined, sortOrder: undefined });

    mockAxios.onGet('/knowledge/faq').reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r2 = await knowledgeApi.getFaq();
    expect(r2.data?.[0]?.id).toBe(0);

    mockAxios.onGet('/knowledge/faq').reply(200, { code: 200, message: 'ok', data: {} });
    const r3 = await knowledgeApi.getFaq();
    expect(r3.data).toEqual([]);
  });

  it('permissionApi.getList — empty array items', async () => {
    mockAxios.onGet('/permissions').reply(200, { code: 200, message: 'ok', data: [] });
    const r = await permissionApi.getList();
    expect(r.data).toEqual([]);
  });

  it('reportApi.getSummary — empty data object', async () => {
    mockAxios.onGet('/reports/summary').reply(200, { code: 200, message: 'ok', data: {} });
    const r = await reportApi.getSummary();
    expect(r.data).toBeDefined();
  });

  it('alarmRuleApi.getList — empty items', async () => {
    mockAxios.onGet('/alarm-rules').reply(200, { code: 200, message: 'ok', data: { items: [] } });
    const r = await alarmRuleApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('notificationTemplateApi.getList — empty items', async () => {
    mockAxios.onGet('/notifications/templates').reply(200, { code: 200, message: 'ok', data: { items: [] } });
    const r = await notificationTemplateApi.getList({ page: 1 });
    expect(r.data?.items).toEqual([]);
  });

  it('pricingApi.getById — null data', async () => {
    mockAxios.onGet('/pricing/1').reply(200, { code: 200, message: 'ok', data: null });
    const r = await pricingApi.getById(1);
    expect(r.data).toBeNull();
  });

  it('inspectionTemplateApi.getList — empty items', async () => {
    mockAxios.onGet('/inspection/templates').reply(200, { code: 200, message: 'ok', data: { items: [] } });
    const r = await inspectionTemplateApi.getList({ page: 1 });
    expect(r.data?.items).toEqual([]);
  });

  it('webhookApi.getList — empty items', async () => {
    mockAxios.onGet('/webhooks').reply(200, { code: 200, message: 'ok', data: { items: [] } });
    const r = await webhookApi.getList({ page: 1 });
    expect(r.data?.items).toEqual([]);
  });

  it('healingRuleApi.getList — empty array', async () => {
    mockAxios.onGet('/healing/rules').reply(200, { code: 200, message: 'ok', data: [] });
    const r = await healingRuleApi.getList();
    expect(r.data).toEqual([]);
  });

  it('healingExecutionApi.getList — empty items', async () => {
    mockAxios.onGet(/\/healing\/executions/).reply(200, { code: 200, message: 'ok', data: { items: [] } });
    const r = await healingExecutionApi.getList({ page: 1 });
    expect(r.data?.items).toEqual([]);
  });

  it('apiKeyApi.getUsage — minimal fields', async () => {
    mockAxios.onGet(/\/api-keys\/\d+\/usage/).reply(200, { code: 200, message: 'ok', data: {} });
    const r = await apiKeyApi.getUsage(1);
    expect(r.data).toBeDefined();
  });

  it('securityPolicyApi.getByKey — minimal fields', async () => {
    mockAxios.onGet('/security/policies').reply(200, { code: 200, message: 'ok', data: {} });
    const r = await securityPolicyApi.getList();
    expect(r.data).toBeDefined();
  });

  it('gatewayApi.getList — empty items', async () => {
    mockAxios.onGet('/gateways').reply(200, { code: 200, message: 'ok', data: { items: [] } });
    const r = await gatewayApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('tenantListApi.getList — empty items', async () => {
    mockAxios.onGet('/tenants').reply(200, { code: 200, message: 'ok', data: { items: [] } });
    const r = await tenantListApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('fleetApi.getDrivers — empty items', async () => {
    mockAxios.onGet(/\/fleet\/drivers/).reply(200, { code: 200, message: 'ok', data: { items: [] } });
    const r = await fleetApi.getDrivers({ page: 1 });
    expect(r.data?.items).toEqual([]);
  });

  it('healthApi.getReadyz/getLivez — minimal payloads', async () => {
    mockAxios.onGet('/readyz').reply(200, { code: 200, message: 'ok', data: {} });
    const r = await healthApi.getReadyz();
    expect(r.data).toBeDefined();

    mockAxios.onGet('/livez').reply(200, { code: 200, message: 'ok', data: {} });
    const r2 = await healthApi.getLivez();
    expect(r2).toEqual({ status: 'unknown', uptimeSeconds: 0 });
  });

  it('stationApi.getDetail — sparse fields hit fallbacks', async () => {
    mockAxios.onGet(/\/stations\/\d+/).reply(200, { code: 200, message: 'ok', data: { id: 7 } });
    const r = await stationApi.getDetail(7);
    expect(r.data?.id).toBe(7);
  });
});
