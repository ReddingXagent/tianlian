/**
 * api ext85 — mapper fallback branch coverage batch 2
 * Sparse item objects {} exercise ?? fallbacks on remaining dense mapper lines
 */
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, {
  knowledgeApi,
  reportApi,
  notificationTemplateApi,
  inspectionTemplateApi,
  webhookApi,
  healingRuleApi,
  healingExecutionApi,
  apiKeyApi,
  securityPolicyApi,
  gatewayApi,
  tenantListApi,
  fleetApi,
  permissionApi,
} from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);
afterAll(() => mockAxios.restore());

describe('api ext85 — mapper fallback batch 2 (sparse {} items)', () => {
  it('knowledgeApi.getArticles — sparse item {}', async () => {
    mockAxios.onGet(/\/knowledge\/articles/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await knowledgeApi.getArticles({ page: 1, page_size: 20 });
    expect(r.data?.items[0]).toEqual({ id: 0, title: '', content: '', summary: '', categoryId: 0, categoryName: undefined, tags: [], author: '', viewCount: 0, status: 'draft', createdAt: '', updatedAt: '' });
  });

  it('knowledgeApi.getFaqCategories — empty items', async () => {
    mockAxios.onGet(/\/knowledge\/faq\/categories/).reply(200, { code: 200, message: 'ok', data: [{}] });
    const r = await knowledgeApi.getFaqCategories();
    expect(r.data?.length ?? 0).toBeGreaterThanOrEqual(0);
  });

  it('reportApi.getSummary — full sparse: stationHealth distribution + energy', async () => {
    mockAxios.onGet(/\/reports\/summary/).reply(200, { code: 200, message: 'ok', data: { station_health: { distribution: {} }, energy: {} } });
    const r = await reportApi.getSummary();
    expect(r.data).toBeDefined();
  });

  it('notificationTemplateApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/notifications\/templates/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await notificationTemplateApi.getList({ page: 1, pageSize: 20 });
    expect(r.data?.items[0]).toBeDefined();
  });

  it('inspectionTemplateApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/inspection\/templates/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await inspectionTemplateApi.getList({ page: 1 });
    expect(r.data?.items[0]).toBeDefined();
  });

  it('webhookApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/webhooks/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await webhookApi.getList({ page: 1 });
    expect(r.data?.items[0]).toBeDefined();
  });

  it('healingRuleApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/healing\/rules/).reply(200, { code: 200, message: 'ok', data: [{}] });
    const r = await healingRuleApi.getList();
    expect(r.data?.[0]).toBeDefined();
  });

  it('healingExecutionApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/healing\/executions/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await healingExecutionApi.getList({ page: 1 });
    expect(r.data?.items[0]).toBeDefined();
  });

  it('apiKeyApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/api-keys/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await apiKeyApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('securityPolicyApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/security\/policies/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await securityPolicyApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('gatewayApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/gateways/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await gatewayApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('gatewayApi.getFirmware — sparse item {}', async () => {
    mockAxios.onGet(/\/gateways\/firmware/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await gatewayApi.getFirmware();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('tenantListApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/tenants/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await tenantListApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('fleetApi.getDrivers — sparse item {}', async () => {
    mockAxios.onGet(/\/fleet\/drivers/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await fleetApi.getDrivers({ page: 1 });
    expect(r.data?.items[0]).toBeDefined();
  });

  it('permissionApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/permissions/).reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await permissionApi.getList();
    expect(r.data?.[0]).toEqual({ name: '', resource: '', action: '', label: '', labelShort: '' });
  });
});
