/**
 * contextInjection 服务单元测试 (夜班 AI 对话补测)
 *
 * 覆盖:
 * - collectPageContext: 路由页面类型识别 / DOM data-* 提取 / API 失败降级 / API 数据 enrichment
 * - describeContext: 各页面类型格式化 + 空上下文不崩
 * - setupContextAutoRefresh: 返回 cleanup 函数
 *
 * 说明: setupContextAutoRefresh 当前源码实现是空桩 (return () => {};), 并无 setInterval/定时器。
 * 本文件只测其真实契约 (返回函数 + 可调用 + 幂等 + 不泄漏 timer),
 * 不臆造不存在的定时器清理行为 —— 这是源码现状的诚实反映。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// 隔离被测服务自身逻辑: 整体 mock '../../api'。
// 响应拦截器链已有 src/api/__tests__/interceptor.test.ts 覆盖, 此处不重复走真实拦截器。
const apiGet = vi.hoisted(() => vi.fn());
vi.mock('../../api', () => ({
  default: { get: apiGet },
}));

import {
  collectPageContext,
  describeContext,
  setupContextAutoRefresh,
  type PageContext,
} from '../contextInjection';

// ---------- helpers ----------
function goto(path: string) {
  window.history.pushState({}, '', path);
}

function setBody(html: string) {
  document.body.innerHTML = html;
}

beforeEach(() => {
  goto('/');
  setBody('');
  document.title = '';
  // 默认给一个良性返回, 避免 fetcher 内 `resp.data` 访问到 undefined 抛错 (即便抛了也有 try/catch, 但保持干净)
  apiGet.mockResolvedValue({ data: { items: [], total: 0 } });
});

afterEach(() => {
  apiGet.mockReset();
});

// ==================== 路由页面类型识别 ====================
describe('collectPageContext - 路由页面类型识别', () => {
  const cases: Array<[string, string]> = [
    ['/devices/v2g/123', 'v2g_device_detail'],
    ['/devices', 'device_list'],
    ['/devices/45', 'device_list'],
    ['/alarms', 'alarm_list'],
    ['/alarm-notices', 'alarm_list'],
    ['/workorders', 'work_order'],
    ['/workorder-stats', 'work_order'],
    ['/dashboard', 'dashboard'],
    ['/stations', 'station_list'],
    ['/knowledge', 'knowledge_base'],
    ['/knowledge/detail/42', 'knowledge_base'],
    ['/teams', 'team_management'],
    ['/reports', 'report'],
    ['/fleet', 'fleet'],
    ['/operate', 'operate'],
    ['/health', 'health_dashboard'],
    ['/digital-twin', 'digital_twin'],
    ['/vpp', 'vpp'],
    ['/energy-report', 'energy_report'],
    ['/healing', 'healing'],
    ['/runbook', 'runbook'],
    ['/fault-diagnosis', 'fault_diagnosis'],
    ['/diagnosis', 'fault_diagnosis'],
    ['/smart-diagnosis', 'smart_diagnosis'],
    ['/config', 'system_config'],
    ['/totally-unknown-route', 'unknown'],
    ['/', 'unknown'],
  ];

  it.each(cases)('路由 %s → page_type %s', async (path, expected) => {
    goto(path);
    const ctx = await collectPageContext();
    expect(ctx.page_type).toBe(expected);
  });

  it('基础上下文带 url 与 page_type', async () => {
    goto('/stations');
    const ctx = await collectPageContext();
    expect(ctx.url).toContain('/stations');
  });
});

// ==================== DOM data-* 提取 (同步层) ====================
describe('collectPageContext - DOM data-* 提取 (同步层)', () => {
  it('提取 h1 文本作为 page_title', async () => {
    goto('/stations'); // 不触发设备 fetcher, 纯 DOM
    setBody('<h1>充电站列表</h1>');
    const ctx = await collectPageContext();
    expect(ctx.page_title).toBe('充电站列表');
  });

  it('h1 缺失时 page_title 回退到 document.title', async () => {
    goto('/stations');
    document.title = '文档标题';
    setBody('<div>x</div>');
    const ctx = await collectPageContext();
    expect(ctx.page_title).toBe('文档标题');
  });

  it('提取 data-device-* 组装 device 对象', async () => {
    goto('/stations');
    setBody(
      '<div data-device-id="7" data-device-name="桩A" data-device-sn="SN001" data-device-code="C1" ' +
        'data-device-type="DC" data-device-status="ONLINE" data-device-health="92" data-device-station="S5"></div>',
    );
    const ctx = await collectPageContext();
    expect(ctx.device).toMatchObject({
      id: '7',
      name: '桩A',
      sn: 'SN001',
      code: 'C1',
      type: 'DC',
      status: 'ONLINE',
      health_score: '92',
      station_id: 'S5',
    });
  });

  it('提取 data-station-* 属性', async () => {
    goto('/stations');
    setBody('<div data-station-id="S9" data-station-name="东站"></div>');
    const ctx = await collectPageContext();
    expect(ctx.station).toMatchObject({ id: 'S9', name: '东站' });
  });

  it('提取 data-v2g-* 全部属性 (属性名去 data-v2g- 前缀)', async () => {
    goto('/stations');
    setBody('<div data-v2g-device-id="3" data-v2g-mode="V2G" data-v2g-soc="80"></div>');
    const ctx = await collectPageContext();
    expect(ctx.v2g_device).toMatchObject({ 'device-id': '3', mode: 'V2G', soc: '80' });
  });

  it('提取 data-alarm-count 并转 number', async () => {
    goto('/stations');
    setBody('<div data-alarm-count="12"></div>');
    const ctx = await collectPageContext();
    expect(ctx.alarm_count).toBe(12);
  });

  it('提取 data-context 通用键值 (优先属性值)', async () => {
    goto('/stations');
    setBody('<span data-context="foo" data-context-key="biz_key">fallback</span>');
    const ctx = await collectPageContext();
    expect(ctx.biz_key).toBe('foo');
  });

  it('data-context 无 key 时归入 unknown', async () => {
    goto('/stations');
    setBody('<span data-context="bar">x</span>');
    const ctx = await collectPageContext();
    expect(ctx.unknown).toBe('bar');
  });

  it('解析 data-context-json 并合并字段', async () => {
    goto('/stations');
    setBody(`<div data-context-json='{"extra_field":42,"flag":true}'></div>`);
    const ctx = await collectPageContext();
    expect(ctx.extra_field).toBe(42);
    expect(ctx.flag).toBe(true);
  });

  it('非法 data-context-json 静默忽略, 不崩', async () => {
    goto('/stations');
    setBody(`<div data-context-json='{not valid json}'></div>`);
    const ctx = await collectPageContext();
    expect(ctx).toBeDefined();
    expect(ctx.page_type).toBe('station_list');
  });
});

// ==================== API 失败降级 (try/catch 路径) ====================
describe('collectPageContext - API 失败降级', () => {
  it('device_list API reject → 返回基础上下文, page_type 保留, 不抛错', async () => {
    goto('/devices');
    apiGet.mockReset();
    apiGet.mockRejectedValue(new Error('network down'));
    const ctx = await collectPageContext();
    expect(ctx.page_type).toBe('device_list');
    expect(ctx.url).toContain('/devices');
    expect(ctx.device_list).toBeUndefined(); // 降级返回空对象, 无列表字段
  });

  it('alarm_list API reject → 降级为零值 alarms 对象, 不抛错', async () => {
    // fetchAlarmContext 用 Promise.allSettled, 永不抛错; 失败时各项为零值
    goto('/alarms');
    apiGet.mockRejectedValue(new Error('boom'));
    const ctx = await collectPageContext();
    expect(ctx.page_type).toBe('alarm_list');
    expect(ctx.alarms).toMatchObject({ total: 0, active: 0, critical: 0, warning: 0, recent: [] });
  });

  it('work_order API reject → 降级不抛错', async () => {
    goto('/workorders');
    apiGet.mockRejectedValue(new Error('boom'));
    const ctx = await collectPageContext();
    expect(ctx.page_type).toBe('work_order');
    expect(ctx.work_orders).toBeUndefined();
  });

  it('v2g_device_detail API reject → 降级不抛错', async () => {
    goto('/devices/v2g/9');
    apiGet.mockRejectedValue(new Error('boom'));
    const ctx = await collectPageContext();
    expect(ctx.page_type).toBe('v2g_device_detail');
  });

  it('dashboard 部分接口失败 (Promise.allSettled) → 仍聚合可用部分', async () => {
    goto('/dashboard');
    apiGet.mockReset();
    apiGet
      .mockResolvedValueOnce({ data: { total: 5 } }) // devices
      .mockRejectedValueOnce(new Error('alarms fail')) // alarms
      .mockResolvedValueOnce({ data: { items: [{ status: 'PENDING' }] } }); // work-orders
    const ctx = await collectPageContext();
    expect(ctx.page_type).toBe('dashboard');
    expect(ctx.dashboard_overview).toBe(true);
    expect(ctx.device_count).toBe(5);
    expect(ctx.pending_work_orders).toBe(1);
  });
});

// ==================== API 数据 enrichment (异步层) ====================
describe('collectPageContext - API 数据 enrichment', () => {
  it('device_list 列表数据按字段映射', async () => {
    goto('/devices');
    apiGet.mockResolvedValue({
      data: {
        total: 2,
        items: [
          { id: 1, name: 'A', sn: 's1', type: 'DC', status: 'ONLINE', health_score: 90, station_id: 5 },
          { id: 2, name: 'B', sn: 's2', type: 'AC', status: 'OFFLINE', health_score: 30, station_id: 6 },
        ],
      },
    });
    const ctx = await collectPageContext();
    expect(ctx.device_list).toEqual([
      { id: 1, name: 'A', sn: 's1', type: 'DC', status: 'ONLINE', health_score: 90, station_id: 5 },
      { id: 2, name: 'B', sn: 's2', type: 'AC', status: 'OFFLINE', health_score: 30, station_id: 6 },
    ]);
  });

  it('device_list 有 DOM 设备 ID 时走详情接口', async () => {
    goto('/devices');
    setBody('<div data-device-id="42"></div>');
    apiGet.mockResolvedValue({
      data: {
        id: 42, name: '桩42', sn: 'sn', code: 'c', type: 'DC', model: 'M', manufacturer: 'F',
        status: 'ONLINE', health_score: 88, station_id: 1, created_at: 't1', updated_at: 't2',
      },
    });
    const ctx = await collectPageContext();
    expect(ctx.device).toMatchObject({ id: 42, name: '桩42', model: 'M' });
    expect(ctx.device_list).toBeUndefined();
    expect(apiGet).toHaveBeenCalledWith('/devices/42');
  });

  it('alarm_list 统计 + 最近告警格式化', async () => {
    goto('/alarms');
    apiGet.mockReset();
    apiGet
      .mockResolvedValueOnce({
        data: {
          total: 3,
          items: [
            { level: 'CRITICAL', title: '失联', status: 'UNACK' },
            { level: 'WARNING', title: '高温', status: 'open' },
            { level: 'WARNING', message: '电压低', status: 'resolved' },
          ],
        },
      })
      .mockResolvedValueOnce({ data: { critical: 1 } }); // /alarms/stats/summary
    const ctx = await collectPageContext();
    expect(ctx.alarms).toMatchObject({
      total: 3,
      active: 2, // UNACK + open
      critical: 1, // CRITICAL
      warning: 2, // WARNING x2
    });
    expect(ctx.alarms?.recent).toHaveLength(3);
    expect(ctx.alarms?.recent?.[0]).toContain('失联');
  });

  it('work_order 聚合统计 + summary', async () => {
    goto('/workorders');
    apiGet.mockResolvedValue({
      data: {
        total: 2,
        items: [
          { status: 'PENDING', fault_desc: '故障A描述', level: 'HIGH' },
          { status: 'accepted', title: '任务B', priority: 'MID' },
        ],
      },
    });
    const ctx = await collectPageContext();
    expect(ctx.work_orders).toMatchObject({
      total: 2,
      pending: 1, // PENDING
      in_progress: 1, // accepted
    });
    expect(ctx.work_orders?.summary).toContain('故障A描述');
  });

  it('knowledge_base 从 URL 提取文章 ID (不走 API)', async () => {
    goto('/knowledge/detail/77');
    const ctx = await collectPageContext();
    expect(ctx.knowledge).toEqual({ current_article_id: '77' });
    expect(apiGet).not.toHaveBeenCalled();
  });
});

// ==================== describeContext 格式化 ====================
describe('describeContext - 格式化', () => {
  it('device 上下文 → 设备详情串', () => {
    const ctx: PageContext = {
      page_type: 'device_list',
      url: '',
      page_title: '',
      device: { id: 7, name: '桩A', sn: 'SN1', type: 'DC', status: 'ONLINE', health_score: 90 },
    };
    const s = describeContext(ctx);
    expect(s).toContain('当前查看设备');
    expect(s).toContain('桩A');
    expect(s).toContain('ID=7');
    expect(s).toContain('SN=SN1');
    expect(s).toContain('健康度=90%');
  });

  it('v2g_device 上下文 → V2G 运行参数串', () => {
    const ctx: PageContext = {
      page_type: 'v2g_device_detail',
      url: '',
      page_title: '',
      v2g_device: {
        v2g_mode: 'BIDIRECTIONAL', grid_status: 'CONNECTED',
        charge_power_kw: 50, discharge_power_kw: 30, soc: 75,
      },
    };
    const s = describeContext(ctx);
    expect(s).toContain('V2G模式');
    expect(s).toContain('SOC: 75%');
    expect(s).toContain('充电功率: 50kW');
    expect(s).toContain('放电功率: 30kW');
  });

  it('device_list 计数', () => {
    const ctx: PageContext = {
      page_type: 'device_list',
      url: '',
      page_title: '',
      device_list: [{ id: 1 }, { id: 2 }, { id: 3 }] as any,
    };
    expect(describeContext(ctx)).toContain('设备列表共 3 台设备');
  });

  it('alarm_list → 统计 + 最近告警', () => {
    const ctx: PageContext = {
      page_type: 'alarm_list',
      url: '',
      page_title: '',
      alarms: { total: 5, active: 2, critical: 1, warning: 3, recent: ['[CRITICAL] x', '[WARNING] y'] },
    };
    const s = describeContext(ctx);
    expect(s).toContain('共 5 条告警');
    expect(s).toContain('2 条未处理');
    expect(s).toContain('1 条严重');
    expect(s).toContain('[CRITICAL] x');
  });

  it('work_order → 工单统计', () => {
    const ctx: PageContext = {
      page_type: 'work_order',
      url: '',
      page_title: '',
      work_orders: { total: 4, pending: 1, in_progress: 2, summary: '' },
    };
    const s = describeContext(ctx);
    expect(s).toContain('共 4 条工单');
    expect(s).toContain('1 条待处理');
    expect(s).toContain('2 条处理中');
  });

  it('dashboard → 固定文案', () => {
    const ctx: PageContext = { page_type: 'dashboard', url: '', page_title: '' };
    expect(describeContext(ctx)).toContain('当前在运维总览看板');
  });

  it('默认分支 → 当前页面 + title', () => {
    const ctx: PageContext = { page_type: 'unknown', url: 'http://x/y', page_title: '某页' };
    expect(describeContext(ctx)).toContain('当前页面: 某页');
  });

  it('默认分支缺 title → 回退 url', () => {
    const ctx: PageContext = { page_type: 'stations', url: 'http://h/x', page_title: '' };
    expect(describeContext(ctx)).toContain('http://h/x');
  });

  it('空上下文不崩: device_list 无任何字段 → 返回空串', () => {
    const ctx: PageContext = { page_type: 'device_list', url: '', page_title: '' };
    expect(describeContext(ctx)).toBe('');
  });

  it('alarm_list 缺 alarms 字段 → 返回空串 (不崩)', () => {
    const ctx: PageContext = { page_type: 'alarm_list', url: '', page_title: '' };
    expect(describeContext(ctx)).toBe('');
  });
});

// ==================== setupContextAutoRefresh ====================
describe('setupContextAutoRefresh', () => {
  it('返回一个 cleanup 函数', () => {
    const cleanup = setupContextAutoRefresh();
    expect(typeof cleanup).toBe('function');
  });

  it('cleanup 可重复调用 (幂等不抛错)', () => {
    const cleanup = setupContextAutoRefresh();
    expect(() => {
      cleanup();
      cleanup();
    }).not.toThrow();
  });

  it('setup 不创建定时器 (源码现状为 no-op 桩, 无 setInterval)', () => {
    vi.useFakeTimers();
    const before = vi.getTimerCount();
    const cleanup = setupContextAutoRefresh();
    expect(vi.getTimerCount()).toBe(before); // 无定时器被调度
    cleanup();
    vi.useRealTimers();
  });
});
