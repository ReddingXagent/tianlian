/**
 * api ext72 — coverage: healthApi.getReadyz/getLivez + engineerApi.create
 *             + webhookApi.create + gatewayApi.create + tenantListApi.create
 *             + roleApi.getTree deep mapping
 * Targets uncovered lines: 982-993, 1017-1031, 1228-1243, 2432-2466,
 *   2522-2556, 3333-3372, 3413-3439, 3738-3793, 3816-3819
 */
import {
  healthApi,
  engineerApi,
  webhookApi,
  gatewayApi,
  tenantListApi,
  roleApi,
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

describe('ext72 — coverage push: healthApi + create mappers', () => {
  beforeEach(() => jest.clearAllMocks());

  // ── healthApi.getReadyz ──

  it('healthApi.getReadyz: full snake_case → camelCase mapping', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: {
          status: 'healthy',
          checks: {
            database: {
              status: 'healthy',
              pool_size: 10,
              active_connections: 3,
              idle_connections: 7,
              waiting_connections: 0,
              db_type: 'postgresql',
            },
            redis: {
              status: 'healthy',
              version: '7.0.0',
              used_memory_human: '2M',
              connected_clients: 5,
            },
            mqtt_broker: {
              status: 'healthy',
              host: 'mqtt.example.com',
              port: 1883,
              error: null,
            },
            filesystem: {
              paths: {
                '/data': { total_gb: 100, free_gb: 50, free_pct: 50 },
                '/tmp': { total_gb: 20, free_gb: 15, free_pct: 75 },
              },
            },
          },
          uptime_seconds: 86400,
          unhealthy_checks: [],
        },
      },
    });

    const res = await healthApi.getReadyz();
    expect(res.code).toBe(200);
    expect(res.data.status).toBe('healthy');
    expect(res.data.uptimeSeconds).toBe(86400);
    expect(res.data.checks.database.poolSize).toBe(10);
    expect(res.data.checks.database.activeConnections).toBe(3);
    expect(res.data.checks.database.dbType).toBe('postgresql');
    expect(res.data.checks.redis.version).toBe('7.0.0');
    expect(res.data.checks.redis.usedMemoryHuman).toBe('2M');
    expect(res.data.checks.redis.connectedClients).toBe(5);
    expect(res.data.checks.mqttBroker.host).toBe('mqtt.example.com');
    expect(res.data.checks.mqttBroker.port).toBe(1883);
    expect(res.data.checks.filesystem.paths['/data'].freePct).toBe(50);
    expect(res.data.checks.filesystem.paths['/tmp'].freeGb).toBe(15);
  });

  it('healthApi.getReadyz: null data → all defaults', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await healthApi.getReadyz();
    expect(res.data.status).toBe('error');
    expect(res.data.uptimeSeconds).toBe(0);
    expect(res.data.checks.database.poolSize).toBe(0);
    expect(res.data.checks.database.dbType).toBe('unknown');
    expect(res.data.checks.redis.version).toBe('unknown');
    expect(res.data.checks.mqttBroker.host).toBe('unknown');
    expect(res.data.checks.filesystem.paths).toEqual({});
    expect(res.data.unhealthyChecks).toEqual([]);
  });

  // ── healthApi.getLivez ──

  it('healthApi.getLivez: maps status + uptime', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { status: 'ok', uptime_seconds: 3600 },
    });
    const res = await healthApi.getLivez();
    expect(res.status).toBe('ok');
    expect(res.uptimeSeconds).toBe(3600);
  });

  it('healthApi.getLivez: null → defaults', async () => {
    mockAxios.get.mockResolvedValueOnce({ data: null });
    const res = await healthApi.getLivez();
    expect(res.status).toBe('unknown');
    expect(res.uptimeSeconds).toBe(0);
  });

  // ── engineerApi.create ──

  it('engineerApi.create: camelCase → snake_case, response mapped', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'created',
        data: {
          id: 10,
          username: 'eng001',
          name: '张三',
          phone: '13800000000',
          level: 'senior',
          team_id: 2,
          status: 'active',
          role: 'engineer',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      },
    });
    const res = await engineerApi.create({
      username: 'eng001',
      password: '123456',
      name: '张三',
      phone: '13800000000',
      level: 'senior',
      role: 'engineer',
    });
    expect(res.data.id).toBe(10);
    expect(res.data.username).toBe('eng001');
    expect(res.data.name).toBe('张三');
    expect(res.data.phone).toBe('13800000000');
    expect(res.data.level).toBe('senior');
    expect(res.data.teamId).toBe(2);
    expect(res.data.status).toBe('active');
    expect(res.data.createdAt).toBe('2026-01-01T00:00:00Z');
    // Verify snake_case in request body
    expect(mockAxios.post).toHaveBeenCalledWith(
      '/engineers',
      expect.objectContaining({ username: 'eng001', name: '张三', phone: '13800000000', level: 'senior' }),
    );
  });

  it('engineerApi.create: null data → defaults', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await engineerApi.create({ username: 'x', password: 'y', name: 'z' });
    expect(res.data.id).toBe(0);
    expect(res.data.level).toBe('junior');
    expect(res.data.status).toBe('active');
    expect(res.data.phone).toBeNull();
    expect(res.data.teamId).toBeNull();
  });

  // ── webhookApi.create ──

  it('webhookApi.create: full mapping with optional fields', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'created',
        data: {
          id: 5,
          name: 'hook1',
          url: 'https://example.com/hook',
          events: ['alarm.created', 'wo.created'],
          secret: 'abc',
          enabled: true,
          last_triggered_at: '2026-08-14T00:00:00Z',
          last_response_status: 200,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      },
    });
    const res = await webhookApi.create({
      name: 'hook1',
      url: 'https://example.com/hook',
      events: ['alarm.created', 'wo.created'],
      secret: 'abc',
      enabled: true,
    });
    expect(res.data.id).toBe(5);
    expect(res.data.events).toEqual(['alarm.created', 'wo.created']);
    expect(res.data.secret).toBe('abc');
    expect(res.data.enabled).toBe(true);
    expect(res.data.lastTriggeredAt).toBe('2026-08-14T00:00:00Z');
    expect(res.data.lastResponseStatus).toBe(200);
  });

  it('webhookApi.create: null data → defaults', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await webhookApi.create({ name: 'x', url: 'https://x.com' });
    expect(res.data.id).toBe(0);
    expect(res.data.events).toEqual([]);
    expect(res.data.enabled).toBe(false);
    expect(res.data.secret).toBeNull();
  });

  // ── gatewayApi.create ──

  it('gatewayApi.create: full mapping', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'created',
        data: {
          id: 1,
          sn: 'GW001',
          name: '网关1',
          model: 'X1',
          manufacturer: 'Tesla',
          station_id: 21,
          status: 'online',
          firmware_version: '1.0',
          last_online: '2026-08-14T00:00:00Z',
          ip_address: '192.168.1.1',
          mac_address: 'AA:BB:CC:DD:EE:FF',
          location: '北京',
          health_score: 95,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          notes: '备注',
        },
      },
    });
    const res = await gatewayApi.create({
      sn: 'GW001',
      name: '网关1',
      stationId: 21,
      model: 'X1',
      manufacturer: 'Tesla',
    });
    expect(res.data.id).toBe(1);
    expect(res.data.sn).toBe('GW001');
    expect(res.data.model).toBe('X1');
    expect(res.data.stationId).toBe(21);
    expect(res.data.status).toBe('online');
    expect(res.data.firmwareVersion).toBe('1.0');
    expect(res.data.ipAddress).toBe('192.168.1.1');
    expect(res.data.macAddress).toBe('AA:BB:CC:DD:EE:FF');
    expect(res.data.healthScore).toBe(95);
    expect(res.data.notes).toBe('备注');
  });

  it('gatewayApi.create: null data → defaults', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await gatewayApi.create({ sn: 'X', name: 'Y' });
    expect(res.data.id).toBe(0);
    expect(res.data.status).toBe('offline');
    expect(res.data.model).toBeNull();
    expect(res.data.healthScore).toBe(0);
    expect(res.data.notes).toBeNull();
  });

  // ── tenantListApi.create ──

  it('tenantListApi.create: full mapping', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'created',
        data: {
          id: 1,
          name: '租户A',
          code: 'TNT_A',
          status: 'active',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      },
    });
    const res = await tenantListApi.create({ name: '租户A', code: 'TNT_A' });
    expect(res.data.id).toBe(1);
    expect(res.data.name).toBe('租户A');
    expect(res.data.code).toBe('TNT_A');
    expect(res.data.status).toBe('active');
    expect(res.data.createdAt).toBe('2026-01-01T00:00:00Z');
  });

  it('tenantListApi.create: null data → defaults', async () => {
    mockAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await tenantListApi.create({ name: 'x', code: 'y' });
    expect(res.data.id).toBe(0);
    expect(res.data.name).toBe('');
    expect(res.data.status).toBe('active');
  });

  // ── roleApi.getTree ──

  it('roleApi.getTree: nested tree mapping', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'ok',
        data: {
          tree: [
            {
              key: 'station',
              title: '充电站',
              resource: 'station',
              is_leaf: false,
              children: [
                { key: 'station:view', title: '查看', resource: 'station', name: 'view', action: 'view', label: '查看', is_leaf: true },
                { key: 'station:edit', title: '编辑', resource: 'station', name: 'edit', action: 'edit', label: '编辑', is_leaf: true },
              ],
            },
            {
              key: 'alarm',
              title: '告警',
              resource: 'alarm',
              is_leaf: true,
            },
          ],
        },
      },
    });
    const res = await roleApi.getTree();
    expect(res.data).toHaveLength(2);
    expect(res.data[0].key).toBe('station');
    expect(res.data[0].title).toBe('充电站');
    expect(res.data[0].isLeaf).toBe(false);
    expect(res.data[0].children).toHaveLength(2);
    expect(res.data[0].children![0].key).toBe('station:view');
    expect(res.data[0].children![0].action).toBe('view');
    expect(res.data[0].children![0].label).toBe('查看');
    expect(res.data[1].key).toBe('alarm');
    expect(res.data[1].isLeaf).toBe(true);
    expect(res.data[1].children).toBeUndefined();
  });

  it('roleApi.getTree: empty tree → empty array', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { tree: [] } },
    });
    const res = await roleApi.getTree();
    expect(res.data).toEqual([]);
  });

  it('roleApi.getTree: null data → empty array', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await roleApi.getTree();
    expect(res.data).toEqual([]);
  });
});
