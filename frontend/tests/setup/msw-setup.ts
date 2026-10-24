/**
 * 天链V3 - Mock Service Worker (MSW) 配置
 *
 * 提供:
 * - API Handlers
 * - Server Setup
 * - 测试环境初始化
 */
import { setupServer } from 'msw/node';
import { http, HttpResponse, delay } from 'msw';

// 导入测试数据
import { mockAPIResponses, mockUsers, mockStations, mockDevices, mockWorkOrders, mockAlarms } from '../fixtures/test-data';

// ============ API Handlers ============

/**
 * 认证相关 Handlers
 */
const authHandlers = [
  // 登录
  http.post('/api/auth/login', async ({ request }) => {
    const body = await request.json() as { username?: string; password?: string };
    await delay(100); // 模拟网络延迟

    const { username, password } = body;

    // 验证用户
    const user = mockUsers.find(u => u.username === username && u.password === password);
    
    if (user) {
      return HttpResponse.json({
        token: `mock-token-${username}`,
        user: { ...user, password: undefined },
      });
    }

    return HttpResponse.json(
      { message: '用户名或密码错误' },
      { status: 401 }
    );
  }),

  // 登出
  http.post('/api/auth/logout', () => {
    return HttpResponse.json({ message: '登出成功' });
  }),

  // 获取当前用户
  http.get('/api/auth/me', ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json(
        { message: '未授权' },
        { status: 401 }
      );
    }

    return HttpResponse.json(mockAPIResponses.loginSuccess.user);
  }),
];

/**
 * 站点相关 Handlers
 */
const stationHandlers = [
  // 获取站点列表
  http.get('/api/stations', async ({ request }) => {
    await delay(50);
    const url = new URL(request.url);
    const page = parseInt(url.searchParams.get('page') || '1');
    const pageSize = parseInt(url.searchParams.get('pageSize') || '10');
    const search = url.searchParams.get('search');

    let data = mockStations;
    if (search) {
      data = data.filter(s => s.name.includes(search) || s.code.includes(search));
    }

    return HttpResponse.json({
      data,
      total: data.length,
      page,
      pageSize,
    });
  }),

  // 获取单个站点
  http.get('/api/stations/:id', ({ params }) => {
    const station = mockStations.find(s => s.id === Number(params.id));
    
    if (!station) {
      return HttpResponse.json(
        { message: '站点不存在' },
        { status: 404 }
      );
    }

    return HttpResponse.json(station);
  }),

  // 创建站点
  http.post('/api/stations', async ({ request }) => {
    await delay(100);
    const body = await request.json() as object;
    
    const newStation = {
      id: mockStations.length + 1,
      ...body,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    return HttpResponse.json(newStation, { status: 201 });
  }),

  // 更新站点
  http.put('/api/stations/:id', async ({ params, request }) => {
    await delay(100);
    const body = await request.json() as object;
    
    const station = mockStations.find(s => s.id === Number(params.id));
    if (!station) {
      return HttpResponse.json(
        { message: '站点不存在' },
        { status: 404 }
      );
    }

    return HttpResponse.json({
      ...station,
      ...body,
      updated_at: new Date().toISOString(),
    });
  }),

  // 删除站点
  http.delete('/api/stations/:id', () => {
    return HttpResponse.json({ message: '删除成功' });
  }),
];

/**
 * 设备相关 Handlers
 */
const deviceHandlers = [
  // 获取设备列表
  http.get('/api/devices', async ({ request }) => {
    await delay(50);
    const url = new URL(request.url);
    const page = parseInt(url.searchParams.get('page') || '1');
    const pageSize = parseInt(url.searchParams.get('pageSize') || '10');
    const stationId = url.searchParams.get('station_id');

    let data = mockDevices;
    if (stationId) {
      data = data.filter(d => d.station_id === Number(stationId));
    }

    return HttpResponse.json({
      data,
      total: data.length,
      page,
      pageSize,
    });
  }),

  // 获取单个设备
  http.get('/api/devices/:id', ({ params }) => {
    const device = mockDevices.find(d => d.id === Number(params.id));
    
    if (!device) {
      return HttpResponse.json(
        { message: '设备不存在' },
        { status: 404 }
      );
    }

    return HttpResponse.json(device);
  }),
];

/**
 * 工单相关 Handlers
 */
const workOrderHandlers = [
  // 获取工单列表
  http.get('/api/workorders', async () => {
    await delay(50);
    return HttpResponse.json(mockAPIResponses.workOrdersList);
  }),

  // 创建工单
  http.post('/api/workorders', async ({ request }) => {
    await delay(100);
    const body = await request.json() as object;
    
    const newWorkOrder = {
      id: mockWorkOrders.length + 1,
      code: `WO${Date.now()}`,
      ...body,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    return HttpResponse.json(newWorkOrder, { status: 201 });
  }),
];

/**
 * 告警相关 Handlers
 */
const alarmHandlers = [
  // 获取告警列表
  http.get('/api/alarms', async () => {
    await delay(50);
    return HttpResponse.json(mockAPIResponses.alarmsList);
  }),

  // 获取告警统计
  http.get('/api/alarms/stats', () => {
    return HttpResponse.json({
      total: mockAlarms.length,
      critical: mockAlarms.filter(a => a.level === 'critical').length,
      warning: mockAlarms.filter(a => a.level === 'warning').length,
      info: mockAlarms.filter(a => a.level === 'info').length,
      active: mockAlarms.filter(a => a.status === 'active').length,
    });
  }),
];

/**
 * Dashboard Handlers
 */
const dashboardHandlers = [
  // 获取 Dashboard 统计
  http.get('/api/dashboard/stats', () => {
    return HttpResponse.json(mockAPIResponses.dashboardStats);
  }),

  // 获取趋势数据
  http.get('/api/dashboard/trends', () => {
    const days = 7;
    const trends = Array.from({ length: days }, (_, i) => ({
      date: new Date(Date.now() - (days - i) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
      alarms: Math.floor(Math.random() * 10),
      workorders: Math.floor(Math.random() * 5),
    }));

    return HttpResponse.json({ trends });
  }),
];

// ============ 合并所有 Handlers ============
const handlers = [
  ...authHandlers,
  ...stationHandlers,
  ...deviceHandlers,
  ...workOrderHandlers,
  ...alarmHandlers,
  ...dashboardHandlers,
];

// ============ 创建 MSW Server ============
export const mswServer = setupServer(...handlers);

// ============ 启动/停止 Server ============
/**
 * 在测试开始前启动 MSW Server
 */
export function setupMSW() {
  beforeAll(() => mswServer.listen({ onUnhandledRequest: 'warn' }));
  afterEach(() => mswServer.resetHandlers());
  afterAll(() => mswServer.close());
}

/**
 * 重置 MSW Handlers
 */
export function resetMSWHandlers() {
  mswServer.resetHandlers();
}

/**
 * 添加自定义 Handler
 */
export function addMSWHandler(handler: Parameters<typeof mswServer.use>[0]) {
  mswServer.use(handler);
}

/**
 * Mock API 错误响应
 */
export function mockAPIError(endpoint: string, status: number, message: string) {
  mswServer.use(
    http.all(endpoint, () => {
      return HttpResponse.json(
        { message },
        { status }
      );
    })
  );
}

/**
 * Mock API 延迟
 */
export function mockAPIDelay(endpoint: string, ms: number) {
  mswServer.use(
    http.all(endpoint, async () => {
      await delay(ms);
      return HttpResponse.json({});
    })
  );
}