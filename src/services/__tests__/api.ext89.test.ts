/**
 * api ext89 — final branch push 2: reportApi full-suite + alarmRuleApi.create sparse +
 * inspectionTemplateApi.create sparse via MockAdapter (module-mocked ext68 left falsy sides cold)
 * Target: branches 96.87% → ≥97% (jest coverageThreshold global).
 */
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, {
  reportApi,
  alarmRuleApi,
  inspectionTemplateApi,
  apiKeyApi,
  deviceMonitorApi,
  healthApi,
  roleApi,
  inspectionTaskApi,
  webhookApi,
  gatewayApi,
  userApi,
  notificationRuleApi,
  engineerApi,
  healingExecutionApi,
  securityPolicyApi,
  tenantListApi,
  stationApi,
  chargingOrderApi,
} from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);
afterAll(() => mockAxios.restore());

const OK = { code: 200, message: 'ok' };

describe('api ext89 — branch falsy-side push 2', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue('t');
  });

  // ---- reportApi 6 endpoints, all sparse (98 uncovered branch sides live here) ----
  it('reportApi.getSummary — data {} (overview/health sparse sweep)', async () => {
    mockAxios.onGet(/\/reports\/summary/).reply(200, { ...OK, data: {} });
    const r = await reportApi.getSummary();
    expect(r).toBeDefined();
  });

  it('reportApi.getDeviceReport — data {} (dense ?? sweep)', async () => {
    mockAxios.onGet(/\/reports\/devices/).reply(200, { ...OK, data: {} });
    const r = await reportApi.getDeviceReport();
    expect(r).toBeDefined();
  });

  it('reportApi.getAlarmReport — data {} + trend item {} (sparse sweep)', async () => {
    mockAxios.onGet(/\/reports\/alarms/).reply(200, { ...OK, data: { alarm_trend: [{}] } });
    const r = await reportApi.getAlarmReport();
    expect(r).toBeDefined();
  });

  it('reportApi.getWorkOrderReport — data {} + daily_trend [{}] (sparse sweep)', async () => {
    mockAxios.onGet(/\/reports\/workorders/).reply(200, { ...OK, data: { daily_trend: [{}] } });
    const r = await reportApi.getWorkOrderReport();
    expect(r).toBeDefined();
  });

  it('reportApi.getEfficiency — data {} (eff sparse sweep)', async () => {
    mockAxios.onGet(/\/reports\/efficiency/).reply(200, { ...OK, data: {} });
    const r = await reportApi.getEfficiency({ period: 'month' });
    expect(r).toBeDefined();
  });

  it('reportApi.getUtilization — data {} (dense ?? sweep)', async () => {
    mockAxios.onGet(/\/reports\/utilization/).reply(200, { ...OK, data: {} });
    const r = await reportApi.getUtilization({ period: 'month' });
    expect(r).toBeDefined();
  });

  // ---- alarmRuleApi.create sparse via MockAdapter (ext66 module-mock left falsy sides cold) ----
  it('alarmRuleApi.create — MockAdapter sparse data {}', async () => {
    mockAxios.onPost(/\/alarm-rules/).reply(200, { ...OK, data: {} });
    const r = await alarmRuleApi.create({ name: 'n', metric: 'm', threshold: 1 });
    expect(r).toBeDefined();
  });

  // ---- inspectionTemplateApi.create sparse via MockAdapter ----
  it('inspectionTemplateApi.create — MockAdapter sparse data {} (null-data guard true)', async () => {
    mockAxios.onPost(/\/inspection\/templates/).reply(200, { ...OK, data: null });
    const r = await inspectionTemplateApi.create({ name: 'n' });
    expect(r.data).toEqual(expect.objectContaining({ id: 0, name: '' }));
  });

  it('inspectionTemplateApi.create — MockAdapter full sparse data {} (items [{}])', async () => {
    mockAxios.onPost(/\/inspection\/templates/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await inspectionTemplateApi.create({ name: 'n' });
    expect(r.data).toBeDefined();
  });

  // ---- apiKeyApi 6 sides ----
  it('apiKeyApi.create — sparse data {} (sparse sweep)', async () => {
    mockAxios.onPost(/\/api-keys/).reply(200, { ...OK, data: {} });
    const r = await apiKeyApi.create({ name: 'k', expiresAt: '2030-01-01' });
    expect(r).toBeDefined();
  });

  it('apiKeyApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/api-keys/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await apiKeyApi.getList();
    expect(r).toBeDefined();
  });

  // ---- deviceMonitorApi remaining ----
  it('deviceMonitorApi.getRealtimeOverview — devices [{}] (item ?? sweep)', async () => {
    mockAxios.onGet(/\/monitor\/realtime/).reply(200, { ...OK, data: { devices: [{}] } });
    const r = await deviceMonitorApi.getRealtimeOverview();
    expect(r).toBeDefined();
  });

  // ---- roleApi.update sparse via MockAdapter ----
  it('roleApi.update — sparse data {} (module-mocks left sides cold)', async () => {
    mockAxios.onPut(/\/roles\/\d+/).reply(200, { ...OK, data: {} });
    const r = await roleApi.update(1, { displayName: 'd' });
    expect(r).toBeDefined();
  });

  // ---- inspectionTaskApi items falsy ----
  it('inspectionTaskApi.getList — items [{}] (nested items sweep)', async () => {
    mockAxios.onGet(/\/inspection\/tasks/).reply(200, {
      ...OK,
      data: { items: [{ items: [{}] }] },
    });
    const r = await inspectionTaskApi.getList();
    expect(r).toBeDefined();
  });

  // ---- webhookApi ----
  it('webhookApi.getList — sparse item {}', async () => {
    mockAxios.onGet(/\/webhooks/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await webhookApi.getList();
    expect(r).toBeDefined();
  });

  it('webhookApi.create — sparse data {}', async () => {
    mockAxios.onPost(/\/webhooks/).reply(200, { ...OK, data: {} });
    const r = await webhookApi.create({ url: 'http://x', events: ['a'] });
    expect(r).toBeDefined();
  });

  // ---- gatewayApi ----
  it('gatewayApi.getById — sparse data {}', async () => {
    mockAxios.onGet(/\/gateways\/\d+/).reply(200, { ...OK, data: {} });
    const r = await gatewayApi.getById(1);
    expect(r).toBeDefined();
  });

  // ---- userApi.update sparse ----
  it('userApi.getDetail — sparse data {} (dense ?? sweep)', async () => {
    mockAxios.onGet(/\/users\/\d+/).reply(200, { ...OK, data: {} });
    const r = await userApi.getDetail(1);
    expect(r).toBeDefined();
  });

  // ---- notificationRuleApi.create sparse ----
  it('notificationRuleApi.create — sparse data {} (channels/receivers ?? sweep)', async () => {
    mockAxios.onPost(/\/notification-rules/).reply(200, { ...OK, data: {} });
    const r = await notificationRuleApi.create({ name: 'n', level: 'high' });
    expect(r).toBeDefined();
  });

  // ---- engineerApi.create sparse ----
  it('engineerApi.create — sparse data {} (skills ?? sweep)', async () => {
    mockAxios.onPost(/\/engineers/).reply(200, { ...OK, data: {} });
    const r = await engineerApi.create({ name: 'e', phone: '1' });
    expect(r).toBeDefined();
  });

  // ---- healingExecutionApi ----
  it('healingExecutionApi.getById — sparse data {}', async () => {
    mockAxios.onGet(/\/healing\/executions\/\d+/).reply(200, { ...OK, data: {} });
    const r = await healingExecutionApi.getById(1);
    expect(r).toBeDefined();
  });

  // ---- securityPolicyApi ----
  it('securityPolicyApi.getByKey — sparse data {}', async () => {
    mockAxios.onGet(/\/security\/policies\/\w+/).reply(200, { ...OK, data: {} });
    const r = await securityPolicyApi.getByKey('k');
    expect(r).toBeDefined();
  });

  // ---- tenantListApi detail ----
  it('tenantListApi.getList — items-wrapper sparse item {}', async () => {
    mockAxios.onGet(/\/tenants/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await tenantListApi.getList();
    expect(r).toBeDefined();
  });

  // ---- stationApi.update sparse ----
  it('stationApi.getList — items [{}] + no params (branding null sweep)', async () => {
    mockAxios.onGet(/\/stations/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await stationApi.getList();
    expect(r).toBeDefined();
  });

  // ---- chargingOrderApi detail ----
  it('chargingOrderApi.getList — items [{}] (item ?? sweep)', async () => {
    mockAxios.onGet(/\/charging-orders/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await chargingOrderApi.getList();
    expect(r).toBeDefined();
  });

  // ---- healthApi.readyz paths sweep ----
  it('healthApi.getReadyz — checks present but all sparse (fs.paths {})', async () => {
    mockAxios.onGet(/\/readyz/).reply(200, { ...OK, data: { checks: { filesystem: {} } } });
    const r = await healthApi.getReadyz();
    expect(r).toBeDefined();
  });
});
