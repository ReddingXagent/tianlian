/**
 * api ext17 — /engineers, /webhooks, /healing/rules, /api-keys 四新端点对接测试
 */
import {
  engineerApi,
  webhookApi,
  healingRuleApi,
  apiKeyApi,
} from '../api';

jest.mock('axios', () => {
  const mockAxios = {
    create: () => ({
      interceptors: {
        request: { use: jest.fn() },
        response: { use: jest.fn() },
      },
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      patch: jest.fn(),
      delete: jest.fn(),
    }),
  };
  return mockAxios;
});

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require('../api').default;

function makeResponse(data: unknown) {
  return { data: { code: 200, message: 'success', data, timestamp: 1786402857 } };
}

// =====================
// engineerApi
// =====================
describe('engineerApi.getList', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case response to camelCase correctly', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 23,
        username: 'mobile_operator',
        name: '移动端联调-运维',
        phone: null,
        level: 'junior',
        team_id: null,
        status: 'active',
        role: 'operator',
        created_at: '2026-07-26T22:08:45.694063+08:00',
        updated_at: '2026-07-31T07:56:19.131987+08:00',
      }],
      total: 1,
      page: 1,
      page_size: 20,
    }));

    const res = await engineerApi.getList();
    expect(res.data.items).toHaveLength(1);
    const e = res.data.items[0];
    expect(e.id).toBe(23);
    expect(e.username).toBe('mobile_operator');
    expect(e.name).toBe('移动端联调-运维');
    expect(e.phone).toBeNull();
    expect(e.level).toBe('junior');
    expect(e.teamId).toBeNull();
    expect(e.status).toBe('active');
    expect(e.role).toBe('operator');
    expect(res.data.total).toBe(1);
  });

  it('handles empty list', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    }));
    const res = await engineerApi.getList({ page: 1, pageSize: 20 });
    expect(res.data.items).toHaveLength(0);
    expect(res.data.total).toBe(0);
  });

  it('passes pagination params as snake_case', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [], total: 0, page: 2, page_size: 10,
    }));
    await engineerApi.getList({ page: 2, pageSize: 10 });
    expect(api.get).toHaveBeenCalledWith('/engineers', {
      params: { page: 2, page_size: 10 },
    });
  });
});

// =====================
// webhookApi
// =====================
describe('webhookApi.getList', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps webhook fields correctly', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 1,
        name: '告警通知',
        url: 'https://example.com/hook',
        events: ['alarm.created', 'alarm.resolved'],
        secret: 'whsec_abc',
        enabled: true,
        last_triggered_at: '2026-08-01T10:00:00+08:00',
        last_response_status: 200,
        created_at: '2026-07-01T00:00:00+08:00',
        updated_at: '2026-08-01T10:00:00+08:00',
      }],
      total: 1,
      page: 1,
      page_size: 20,
    }));

    const res = await webhookApi.getList();
    expect(res.data.items).toHaveLength(1);
    const w = res.data.items[0];
    expect(w.id).toBe(1);
    expect(w.name).toBe('告警通知');
    expect(w.url).toBe('https://example.com/hook');
    expect(w.events).toEqual(['alarm.created', 'alarm.resolved']);
    expect(w.secret).toBe('whsec_abc');
    expect(w.enabled).toBe(true);
    expect(w.lastTriggeredAt).toBe('2026-08-01T10:00:00+08:00');
    expect(w.lastResponseStatus).toBe(200);
  });

  it('handles null fields for never-triggered webhook', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 2,
        name: '未触发hook',
        url: 'https://example.com/new',
        events: [],
        secret: null,
        enabled: false,
        last_triggered_at: null,
        last_response_status: null,
        created_at: '2026-07-01T00:00:00+08:00',
        updated_at: '2026-07-01T00:00:00+08:00',
      }],
      total: 1,
      page: 1,
      page_size: 20,
    }));
    const res = await webhookApi.getList();
    const w = res.data.items[0];
    expect(w.lastTriggeredAt).toBeNull();
    expect(w.lastResponseStatus).toBeNull();
    expect(w.secret).toBeNull();
    expect(w.enabled).toBe(false);
  });

  it('handles empty list', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [], total: 0, page: 1, page_size: 20,
    }));
    const res = await webhookApi.getList();
    expect(res.data.items).toHaveLength(0);
  });
});

// =====================
// healingRuleApi
// =====================
describe('healingRuleApi.getList', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps healing rule fields correctly', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 1,
        name: '离线重启',
        device_type: 'charger',
        fault_code: 'E001',
        action: 'restart',
        conditions: { retry_count: 3, interval_sec: 60 },
        enabled: true,
        success_rate: 0.95,
        last_triggered_at: '2026-08-05T14:30:00+08:00',
        created_at: '2026-07-01T00:00:00+08:00',
        updated_at: '2026-08-05T14:30:00+08:00',
      }],
      total: 1,
      page: 1,
      page_size: 20,
    }));

    const res = await healingRuleApi.getList();
    expect(res.data.items).toHaveLength(1);
    const h = res.data.items[0];
    expect(h.id).toBe(1);
    expect(h.name).toBe('离线重启');
    expect(h.deviceType).toBe('charger');
    expect(h.faultCode).toBe('E001');
    expect(h.action).toBe('restart');
    expect(h.conditions).toEqual({ retry_count: 3, interval_sec: 60 });
    expect(h.enabled).toBe(true);
    expect(h.successRate).toBe(0.95);
    expect(h.lastTriggeredAt).toBe('2026-08-05T14:30:00+08:00');
  });

  it('handles empty list', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [], total: 0, page: 1, page_size: 20,
    }));
    const res = await healingRuleApi.getList();
    expect(res.data.items).toHaveLength(0);
    expect(res.data.total).toBe(0);
  });
});

// =====================
// apiKeyApi
// =====================
describe('apiKeyApi.getList', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps api key fields correctly', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 1,
        name: '边缘网关密钥',
        key_prefix: 'tl_live_',
        permissions: ['device:view', 'telemetry:report'],
        last_used_at: '2026-08-10T12:00:00+08:00',
        expires_at: '2027-01-01T00:00:00+08:00',
        enabled: true,
        created_at: '2026-07-01T00:00:00+08:00',
        updated_at: '2026-08-10T12:00:00+08:00',
      }],
      total: 1,
      page: 1,
      page_size: 20,
    }));

    const res = await apiKeyApi.getList();
    expect(res.data.items).toHaveLength(1);
    const k = res.data.items[0];
    expect(k.id).toBe(1);
    expect(k.name).toBe('边缘网关密钥');
    expect(k.keyPrefix).toBe('tl_live_');
    expect(k.permissions).toEqual(['device:view', 'telemetry:report']);
    expect(k.lastUsedAt).toBe('2026-08-10T12:00:00+08:00');
    expect(k.expiresAt).toBe('2027-01-01T00:00:00+08:00');
    expect(k.enabled).toBe(true);
  });

  it('handles never-used key with null fields', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [{
        id: 2,
        name: 'unused',
        key_prefix: 'tl_new_',
        permissions: [],
        last_used_at: null,
        expires_at: null,
        enabled: false,
        created_at: '2026-07-01T00:00:00+08:00',
        updated_at: '2026-07-01T00:00:00+08:00',
      }],
      total: 1,
      page: 1,
      page_size: 20,
    }));
    const res = await apiKeyApi.getList();
    const k = res.data.items[0];
    expect(k.lastUsedAt).toBeNull();
    expect(k.expiresAt).toBeNull();
    expect(k.enabled).toBe(false);
  });

  it('handles empty list', async () => {
    api.get.mockResolvedValueOnce(makeResponse({
      items: [], total: 0, page: 1, page_size: 20,
    }));
    const res = await apiKeyApi.getList();
    expect(res.data.items).toHaveLength(0);
  });
});
