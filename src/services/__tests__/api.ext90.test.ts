/**
 * api ext90 — top branch-gap clusters: alarmRule create/update sparse, inspectionTemplate
 * update/getList sparse, mapStation branding sparse, deviceHealth/fleet/readyz sparse.
 * F1040 analysis: 88 branch gaps total; these clusters = ~44 of them, batch-coverable.
 */
import MockAdapter from 'axios-mock-adapter';
import api, {
  alarmRuleApi,
  inspectionTemplateApi,
  deviceHealthApi,
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

describe('api ext90 — top branch-gap clusters', () => {
  beforeEach(() => mockAxios.reset());

  // ---- alarmRuleApi.create sparse data {} (falsy sides of ~20 mapper ?? defaults) ----
  it('alarmRuleApi.create — sparse data {} covers mapper defaults', async () => {
    mockAxios.onPost(/\/alarm-rules/).reply(200, { ...OK, data: {} });
    const r = await alarmRuleApi.create({ name: 'n', metric: 'm', threshold: 1 });
    expect(r.data).toEqual(
      expect.objectContaining({
        id: 0,
        name: '',
        metric: '',
        operator: '>',
        level: 'warning',
        enabled: false,
        silenceMinutes: 0,
      }),
    );
  });

  // ---- alarmRuleApi.update: spread guards (undefined vs set) + mapper sparse ----
  it('alarmRuleApi.update — full body spread + sparse data {}', async () => {
    mockAxios
      .onPut(/\/alarm-rules\/\d+/)
      .reply((cfg) => [200, { ...OK, data: { name: 'x' } }, { 'content-type': 'application/json' }]);
    const r = await alarmRuleApi.update(1, {
      name: 'u',
      metric: 'm2',
      threshold: 9,
      deviceType: 'dt',
      severity: 'sev',
      operator: '>=',
      duration: 5,
      enabled: true,
      description: 'd',
    });
    expect(r.data).toBeDefined();
    expect(r.data?.name).toBe('x');
  });

  it('alarmRuleApi.update — minimal body {} + data {} (falsy spread sides + mapper defaults)', async () => {
    mockAxios.onPut(/\/alarm-rules\/\d+/).reply(200, { ...OK, data: {} });
    const r = await alarmRuleApi.update(2, {});
    expect(r.data).toEqual(
      expect.objectContaining({ id: 0, name: '', metric: '', operator: '>', enabled: false }),
    );
  });

  it('alarmRuleApi.update — null data guard', async () => {
    mockAxios.onPut(/\/alarm-rules\/\d+/).reply(200, { ...OK, data: null });
    const r = await alarmRuleApi.update(3, {});
    expect(r.data).toBeNull();
  });

  // ---- inspectionTemplateApi.update (11 gaps) ----
  it('inspectionTemplateApi.update — full body spread + sparse data {}', async () => {
    mockAxios.onPut(/\/inspection\/templates\/\d+/).reply(200, { ...OK, data: {} });
    const r = await inspectionTemplateApi.update(1, {
      name: 't',
      category: 'c',
      description: 'd',
      items: [{ name: 'i1', required: true }],
    });
    expect(r.data).toEqual(
      expect.objectContaining({ id: 0, name: '', itemCount: 0, deviceTypes: [], status: 'active' }),
    );
  });

  it('inspectionTemplateApi.update — items [{}] item-level defaults + updatedAt null', async () => {
    mockAxios.onPut(/\/inspection\/templates\/\d+/).reply(200, {
      ...OK,
      data: { items: [{}], updated_at: null },
    });
    const r = await inspectionTemplateApi.update(2, {});
    expect(r.data?.items).toEqual([{ name: '', required: false }]);
    expect(r.data?.updatedAt).toBe('');
  });

  it('inspectionTemplateApi.update — null data guard', async () => {
    mockAxios.onPut(/\/inspection\/templates\/\d+/).reply(200, { ...OK, data: null });
    const r = await inspectionTemplateApi.update(3, {});
    expect(r.data).toBeNull();
  });

  // ---- inspectionTemplateApi.getList (5 gaps) ----
  it('inspectionTemplateApi.getList — sparse data {}', async () => {
    mockAxios.onGet(/\/inspection\/templates/).reply(200, { ...OK, data: {} });
    const r = await inspectionTemplateApi.getList();
    expect(r.data?.items).toEqual([]);
  });

  it('inspectionTemplateApi.getList — item {} defaults', async () => {
    mockAxios.onGet(/\/inspection\/templates/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await inspectionTemplateApi.getList();
    expect(r.data?.items?.[0]).toEqual(
      expect.objectContaining({ name: '', enabled: true, createdAt: '', updatedAt: '' }),
    );
  });

  // ---- mapStation branding cluster (if@3859, 5 gaps): sparse station {} ----
  it('stationApi.getList — sparse station {} covers mapStation defaults + branding falsy', async () => {
    mockAxios.onGet(/\/stations/).reply(200, { ...OK, data: { items: [{}] } });
    const r = await stationApi.getList();
    expect(r.data?.items?.[0]).toEqual(
      expect.objectContaining({ id: 0, name: '', branding: null }),
    );
  });

  it('stationApi.getList — branding {} (all inner ?? falsy sides)', async () => {
    mockAxios.onGet(/\/stations/).reply(200, {
      ...OK,
      data: { items: [{ branding: {} }] },
    });
    const r = await stationApi.getList();
    expect(r.data?.items?.[0]?.branding).toEqual(
      expect.objectContaining({ operatorName: '', logoUrl: '', themeColor: '#00A86B', source: 'default' }),
    );
  });

  it('stationApi.create — sparse data {} mapStation defaults', async () => {
    mockAxios.onPost(/\/stations/).reply(200, { ...OK, data: {} });
    const r = await stationApi.create({ name: 's' });
    expect(r.data).toEqual(expect.objectContaining({ id: 0, name: '' }));
  });

  // ---- deviceHealthApi (2 gaps) ----
  it('deviceHealthApi.getRanking — plain passthrough', async () => {
    mockAxios.onGet(/\/health\/devices/).reply(200, { ...OK, data: { rank: [] } });
    const r = await deviceHealthApi.getRanking();
    expect(r.data).toEqual({ rank: [] });
  });

  // ---- fleetApi.getDrivers (1 gap) ----
  it('fleetApi.getDrivers — sparse data {}', async () => {
    mockAxios.onGet(/\/fleet\/drivers/).reply(200, { ...OK, data: {} });
    const r = await fleetApi.getDrivers({ page: 1, pageSize: 10 });
    expect(r.data?.items).toEqual([]);
  });

  // ---- healthApi.getReadyz fs.paths loop (3 gaps at 3750-3751 area) ----
  it('healthApi.getReadyz — sparse {} all checks + empty paths', async () => {
    mockAxios.onGet(/\/readyz/).reply(200, { ...OK, data: {} });
    const r = await healthApi.getReadyz();
    expect(r.data?.checks).toBeDefined();
  });

  it('healthApi.getReadyz — fs.paths {} entry defaults', async () => {
    mockAxios.onGet(/\/readyz/).reply(200, {
      ...OK,
      data: { status: 'healthy', checks: { filesystem: { paths: { data: {} } } } },
    });
    const r = await healthApi.getReadyz();
    expect(r.data?.checks.filesystem?.paths?.data).toEqual({ totalGb: 0, freeGb: 0, freePct: 0 });
  });
});
