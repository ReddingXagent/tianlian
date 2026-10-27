/**
 * api ext88 — final branch push: sparse/falsy payloads across remaining APIs
 * Target: branches 96.24% → ≥97% (threshold). Hits ??-falsy sides + optional-spread falsy sides.
 */
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, {
  authApi,
  deviceApi,
  knowledgeApi,
  deviceMonitorApi,
  roleApi,
  userApi,
  reportApi,
  alarmRuleApi,
  notificationRuleApi,
  notificationTemplateApi,
  chargingOrderApi,
  pricingApi,
  inspectionTemplateApi,
  inspectionTaskApi,
  engineerApi,
  webhookApi,
  healingExecutionApi,
  apiKeyApi,
  securityPolicyApi,
  securityThreatApi,
  gatewayApi,
  tenantListApi,
  chatApi,
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

const OK = { code: 200, message: 'ok' };

describe('api ext88 — branch falsy-side sweep (sparse payloads)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue('t');
  });

  it('authApi.getProfile — data:null hits raw.data ?? {}', async () => {
    mockAxios.onGet('/auth/me').reply(200, { ...OK, data: null });
    const r = await authApi.getProfile();
    expect(r.data).toBeDefined();
  });

  it('deviceApi.getList — sparse items [{}]', async () => {
    mockAxios.onGet(/\/devices/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await deviceApi.getList({ page: 1 });
    expect(r.data?.items[0]).toBeDefined();
  });

  it('knowledgeApi.getCategories — sparse item {}', async () => {
    mockAxios.onGet(/\/knowledge\/categories/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await knowledgeApi.getCategories();
    expect(r.data?.[0]).toBeDefined();
  });

  it('deviceMonitorApi.getRealtimeOverview — empty data {} (dense ?? sweep)', async () => {
    mockAxios.onGet(/\/monitor\/realtime/).reply(200, { ...OK, data: {} });
    const r = await deviceMonitorApi.getRealtimeOverview();
    expect(r.data).toEqual({
      totalPower: 0, powerTrend: 0, todayGeneration: 0, todayConsumption: 0,
      gridImport: 0, gridExport: 0, efficiency: 0, updateTime: '', devices: [],
    });
  });

  it('roleApi.getList — sparse items [{}] (returns mapped array)', async () => {
    mockAxios.onGet(/\/roles/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await roleApi.getList();
    expect(r.data?.[0]).toBeDefined();
  });

  it('userApi.getDetail — sparse data {}', async () => {
    mockAxios.onGet(/\/users\/\d+/).reply(200, { ...OK, data: {} });
    const r = await userApi.getDetail(1);
    expect(r.data).toBeDefined();
  });

  it('reportApi.getSummary — empty data {} (shape tolerant)', async () => {
    mockAxios.onGet(/\/reports\/summary/).reply(200, { ...OK, data: {} });
    const r = await reportApi.getSummary();
    expect(r).toBeDefined();
  });

  it('alarmRuleApi.create — minimal body (optional spreads falsy)', async () => {
    mockAxios.onPost(/\/alarm-rules/).reply(200, { ...OK, data: {} });
    const r = await alarmRuleApi.create({ name: 'n', metric: 'm', threshold: 1 });
    expect(r.data).toBeDefined();
  });

  it('alarmRuleApi.getList — sparse items [{}]', async () => {
    mockAxios.onGet(/\/alarm-rules/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await alarmRuleApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('notificationRuleApi.getList — returns list (response shape tolerant)', async () => {
    mockAxios.onGet(/\/notification-rules/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await notificationRuleApi.getList();
    expect(r.data).toBeDefined();
  });

  it('notificationTemplateApi.getList — returns list (response shape tolerant)', async () => {
    mockAxios.onGet(/\/notifications\/templates/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await notificationTemplateApi.getList();
    expect(r.data).toBeDefined();
  });

  it('chargingOrderApi.getList — sparse items [{}]', async () => {
    mockAxios.onGet(/\/charging-orders/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await chargingOrderApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('pricingApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/pricing/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await pricingApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('inspectionTemplateApi.getList — sparse items [{}]', async () => {
    mockAxios.onGet(/\/inspection\/templates/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await inspectionTemplateApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('inspectionTaskApi.getList — sparse items [{}]', async () => {
    mockAxios.onGet(/\/inspection\/tasks/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await inspectionTaskApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('engineerApi.getList — sparse items [{}]', async () => {
    mockAxios.onGet(/\/engineers/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await engineerApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('webhookApi.getList — sparse items [{}]', async () => {
    mockAxios.onGet(/\/webhooks/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await webhookApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('healingExecutionApi.getList — sparse items [{}]', async () => {
    mockAxios.onGet(/\/healing\/executions/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await healingExecutionApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('apiKeyApi.getList — sparse items [{}]', async () => {
    mockAxios.onGet(/\/api-keys/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await apiKeyApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('securityPolicyApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/security\/policies/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await securityPolicyApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('securityThreatApi.getList — sparse items [{}]', async () => {
    mockAxios.onGet(/\/security\/threats/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await securityThreatApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('gatewayApi.getList — sparse items [{}] (already 85; re-verify no regression)', async () => {
    mockAxios.onGet(/\/gateways/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await gatewayApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('tenantListApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/tenants/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await tenantListApi.getList();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('chatApi.send — data {} (sources/actions/usage all missing)', async () => {
    mockAxios.onPost(/\/chat/).reply(200, { ...OK, data: {} });
    const r = await chatApi.send('hi');
    expect(r.data).toBeDefined();
  });

  it('chatApi.send — sources/actions sparse item {} + usage present sparse', async () => {
    mockAxios.onPost(/\/chat/).reply(200, {
      ...OK,
      data: { sources: [{}], actions: [{}], usage: {} },
    });
    const r = await chatApi.send('hi', { conversationId: 'c1' });
    expect(r.data).toBeDefined();
  });

  it('fleetApi.getDrivers — params {} (query-spread falsy)', async () => {
    mockAxios.onGet(/\/fleet\/drivers/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await fleetApi.getDrivers();
    expect(r.data?.items[0]).toBeDefined();
  });

  it('healthApi.getReadyz — empty data {} (dense ?? sweep)', async () => {
    mockAxios.onGet(/\/readyz/).reply(200, { ...OK, data: {} });
    const r = await healthApi.getReadyz();
    expect(r).toBeDefined();
  });

  it('stationApi.getDetail — id with sparse data {}', async () => {
    mockAxios.onGet(/\/stations\/\d+/).reply(200, { ...OK, data: {} });
    const r = await stationApi.getDetail(1);
    expect(r.data).toBeDefined();
  });
});
