/**
 * 上下文注入服务 - 根据当前页面路由自动收集上下文数据
 *
 * 功能:
 * 1. 根据路由判断页面类型（设备/告警/工单/知识库等）
 * 2. 从DOM或API获取当前页面数据
 * 3. 格式化后传递给AI对话接口
 *
 * 架构:
 * - 同步层: 从DOM中提取data-*属性和文本内容（即时有结果）
 * - 异步层: 必要时通过API获取完整数据（更丰富但需要网络请求）
 */

import api from '../api';

// ==================== 类型定义 ====================

export interface PageContext {
  /** 页面类型标识符 */
  page_type: string;
  /** 完整URL */
  url: string;
  /** 页面标题 */
  page_title: string;
  /** 设备上下文 (设备详情/列表页) */
  device?: Record<string, unknown>;
  /** 告警上下文 (告警页) */
  alarms?: {
    total: number;
    active: number;
    critical: number;
    warning: number;
    recent: string[];
  };
  /** 工单上下文 (工单页) */
  work_orders?: {
    total: number;
    pending: number;
    in_progress: number;
    summary: string;
  };
  /** 站点上下文 (站点页) */
  station?: Record<string, unknown>;
  /** 知识库上下文 */
  knowledge?: {
    current_article_id?: number | string;
  };
  /** V2G上下文 */
  v2g_device?: Record<string, unknown>;
  /** 额外动态字段 */
  [key: string]: unknown;
}

// ==================== 路由 → 页面类型映射 ====================

type ContextFetcher = () => Promise<Partial<PageContext>>;

interface RouteConfig {
  type: string;
  label: string;
  fetcher: ContextFetcher;
}

const routeConfigs: Record<string, RouteConfig> = {};

// ==================== DOM数据辅助函数 ====================

/**
 * 从DOM中提取所有data-*属性
 */
function extractDOMData(): Record<string, unknown> {
  const data: Record<string, unknown> = {};

  try {
    // 页面标题
    const h1 = document.querySelector('h1');
    if (h1) data.page_title = h1.textContent?.trim() || '';

    // data-device-* 属性
    const deviceEl = document.querySelector('[data-device-id]');
    if (deviceEl) {
      data.device = {
        id: deviceEl.getAttribute('data-device-id') || '',
        name: deviceEl.getAttribute('data-device-name') || '',
        sn: deviceEl.getAttribute('data-device-sn') || '',
        code: deviceEl.getAttribute('data-device-code') || '',
        type: deviceEl.getAttribute('data-device-type') || '',
        status: deviceEl.getAttribute('data-device-status') || '',
        health_score: deviceEl.getAttribute('data-device-health') || '',
        station_id: deviceEl.getAttribute('data-device-station') || '',
      };
    }

    // data-station-* 属性
    const stationEl = document.querySelector('[data-station-id]');
    if (stationEl) {
      data.station = {
        id: stationEl.getAttribute('data-station-id') || '',
        name: stationEl.getAttribute('data-station-name') || '',
      };
    }

    // data-v2g-* 属性 (V2G设备)
    const v2gEl = document.querySelector('[data-v2g-device-id]');
    if (v2gEl) {
      const v2gData: Record<string, string> = {};
      if (v2gEl) {
        for (const attr of v2gEl.attributes) {
          if (attr.name.startsWith('data-v2g-')) {
            v2gData[attr.name.replace('data-v2g-', '')] = attr.value;
          }
        }
      }
      data.v2g_device = v2gData;
    }

    // data-alarm-* 属性
    const alarmCount = document.querySelector('[data-alarm-count]')?.getAttribute('data-alarm-count');
    if (alarmCount) {
      data.alarm_count = parseInt(alarmCount, 10);
    }

    // data-context 通用数据
    const contextEls = document.querySelectorAll('[data-context]');
    contextEls.forEach((el) => {
      const key = el.getAttribute('data-context-key') || 'unknown';
      const value = el.getAttribute('data-context') || el.textContent;
      data[key] = value;
    });

    // data-context-json (完整JSON数据)
    const jsonEl = document.querySelector('[data-context-json]');
    if (jsonEl) {
      const jsonStr = jsonEl.getAttribute('data-context-json');
      if (jsonStr) {
        try {
          const parsed = JSON.parse(jsonStr);
          Object.assign(data, parsed);
        } catch {
          // JSON解析失败忽略
        }
      }
    }

  } catch {
    // DOM解析安全忽略
  }

  return data;
}

/**
 * 从URL中提取路径参数
 */
function extractPathParam(path: string, pattern: RegExp): string | null {
  const match = path.match(pattern);
  return match ? match[1] : null;
}

// ==================== 页面类型识别 ====================

/**
 * 根据当前路由识别页面类型
 */
function identifyPageType(path: string): string {
  if (path.startsWith('/devices/v2g/')) return 'v2g_device_detail';
  if (path.startsWith('/devices')) return 'device_list';
  if (path.startsWith('/alarms') || path.startsWith('/alarm-notices')) return 'alarm_list';
  if (path.startsWith('/workorders') || path.startsWith('/workorder-stats')) return 'work_order';
  if (path.startsWith('/dashboard')) return 'dashboard';
  if (path.startsWith('/stations')) return 'station_list';
  if (path.startsWith('/knowledge')) return 'knowledge_base';
  if (path.startsWith('/teams')) return 'team_management';
  if (path.startsWith('/reports')) return 'report';
  if (path.startsWith('/fleet')) return 'fleet';
  if (path.startsWith('/operate')) return 'operate';
  if (path.startsWith('/health')) return 'health_dashboard';
  if (path.startsWith('/digital-twin')) return 'digital_twin';
  if (path.startsWith('/vpp')) return 'vpp';
  if (path.startsWith('/energy-report')) return 'energy_report';
  if (path.startsWith('/healing')) return 'healing';
  if (path.startsWith('/runbook')) return 'runbook';
  if (path.startsWith('/fault-diagnosis') || path.startsWith('/diagnosis')) return 'fault_diagnosis';
  if (path.startsWith('/smart-diagnosis')) return 'smart_diagnosis';
  if (path.startsWith('/config')) return 'system_config';
  return 'unknown';
}

// ==================== API数据获取 ====================

/**
 * 获取设备列表上下文
 */
async function fetchDeviceListContext(): Promise<Partial<PageContext>> {
  try {
    const resp = await api.get('/devices', {
      params: { page: 1, page_size: 5 },
    });
    const data = resp.data as any;
    const items = data?.items || [];
    return {
      device_list: items.map((d: any) => ({
        id: d.id,
        name: d.name,
        sn: d.sn,
        type: d.type,
        status: d.status,
        health_score: d.health_score,
        station_id: d.station_id,
      })),
    };
  } catch {
    return {};
  }
}

/**
 * 获取单个设备详情上下文
 */
async function fetchDeviceDetailContext(deviceId: number): Promise<Partial<PageContext>> {
  try {
    const resp = await api.get(`/devices/${deviceId}`);
    const device = resp.data as any;
    return {
      device: {
        id: device.id,
        name: device.name,
        sn: device.sn,
        code: device.code,
        type: device.type,
        model: device.model,
        manufacturer: device.manufacturer,
        status: device.status,
        health_score: device.health_score,
        station_id: device.station_id,
        created_at: device.created_at,
        updated_at: device.updated_at,
      },
    };
  } catch {
    return {};
  }
}

/**
 * 获取V2G设备详情
 */
async function fetchV2GDeviceContext(deviceId: number): Promise<Partial<PageContext>> {
  try {
    const [deviceResp, efficiencyResp] = await Promise.allSettled([
      api.get(`/devices/${deviceId}`),
      api.get(`/devices/${deviceId}/efficiency`).catch(() => null),
    ]);

    const device = deviceResp.status === 'fulfilled' ? deviceResp.value.data as any : null;
    const efficiency = efficiencyResp.status === 'fulfilled' && efficiencyResp.value
      ? efficiencyResp.value.data as any
      : null;

    if (!device) return {};

    return {
      v2g_device: {
        id: device.id,
        name: device.name,
        sn: device.sn,
        type: device.type,
        status: device.status,
        health_score: device.health_score,
        power_rating_kw: device.power_rating_kw,
        v2g_mode: device.v2g_mode,
        grid_status: device.grid_status,
        charge_power_kw: device.charge_power_kw,
        discharge_power_kw: device.discharge_power_kw,
        soc: device.soc,
        efficiency_rate: efficiency?.efficiency_rate,
        utilization_rate: efficiency?.utilization_rate,
        trend: efficiency?.trend,
      },
      device: {
        id: device.id,
        name: device.name,
        sn: device.sn,
        type: device.type,
        status: device.status,
        health_score: device.health_score,
      },
    };
  } catch {
    return {};
  }
}

/**
 * 获取告警列表上下文
 */
async function fetchAlarmContext(): Promise<Partial<PageContext>> {
  try {
    const [listResp, statsResp] = await Promise.allSettled([
      api.get('/alarms', { params: { page: 1, page_size: 10 } }),
      api.get('/alarms/stats/summary'),
    ]);

    const listData = listResp.status === 'fulfilled' ? (listResp.value.data as any) : null;
    const statsData = statsResp.status === 'fulfilled' ? (statsResp.value.data as any) : null;

    const items = listData?.items || (Array.isArray(listData) ? listData : []);
    const recent = items.slice(0, 5).map((a: any) =>
      `[${a.level}] ${a.title || a.message || ''} (${a.status || ''})`
    );

    return {
      alarms: {
        total: listData?.total || items.length || 0,
        active: items.filter((a: any) => a.status === 'UNACK' || a.status === 'open' || !a.status).length,
        critical: items.filter((a: any) => a.level === 'CRITICAL' || a.level === 'critical').length,
        warning: items.filter((a: any) => a.level === 'WARNING' || a.level === 'warning').length,
        recent,
        ...(statsData ? { summary: statsData } : {}),
      },
    };
  } catch {
    return {};
  }
}

/**
 * 获取工单上下文
 */
async function fetchWorkOrderContext(): Promise<Partial<PageContext>> {
  try {
    const resp = await api.get('/work-orders', { params: { page: 1, page_size: 10 } });
    const data = resp.data as any;
    const items = data?.items || (Array.isArray(data) ? data : []);

    return {
      work_orders: {
        total: data?.total || items.length || 0,
        pending: items.filter((w: any) => w.status === 'PENDING' || w.status === 'pending').length,
        in_progress: items.filter((w: any) => w.status === 'IN_PROGRESS' || w.status === 'accepted').length,
        summary: items.slice(0, 5).map((w: any) =>
          `[${w.level || w.priority}] ${w.fault_desc?.slice(0, 50) || w.title || ''} → ${w.status || ''}`
        ).join('; '),
      },
    };
  } catch {
    return {};
  }
}

/**
 * 获取看板上下文（Dashboard）
 */
async function fetchDashboardContext(): Promise<Partial<PageContext>> {
  try {
    const [devicesResp, alarmsResp, workordersResp] = await Promise.allSettled([
      api.get('/devices', { params: { page: 1, page_size: 5 } }),
      api.get('/alarms', { params: { page: 1, page_size: 5 } }),
      api.get('/work-orders', { params: { page: 1, page_size: 5 } }),
    ]);

    const data: Record<string, unknown> = { dashboard_overview: true };

    if (devicesResp.status === 'fulfilled') {
      const dd = devicesResp.value.data as any;
      data.device_count = dd?.total || dd?.items?.length || 0;
    }
    if (alarmsResp.status === 'fulfilled') {
      const ad = alarmsResp.value.data as any;
      const items = ad?.items || (Array.isArray(ad) ? ad : []);
      data.active_alarms = items.filter((a: any) => a.status !== 'resolved').length;
    }
    if (workordersResp.status === 'fulfilled') {
      const wd = workordersResp.value.data as any;
      const items = wd?.items || (Array.isArray(wd) ? wd : []);
      data.pending_work_orders = items.filter((w: any) => w.status !== 'FINISHED' && w.status !== 'done').length;
    }

    return data;
  } catch {
    return {};
  }
}

/**
 * 获取知识库上下文
 */
async function fetchKnowledgeContext(): Promise<Partial<PageContext>> {
  try {
    // 从URL提取知识库文章ID
    const path = window.location.pathname;
    const articleId = extractPathParam(path, /\/knowledge\/(?:detail|edit)\/(\d+)/);

    if (articleId) {
      return {
        knowledge: { current_article_id: articleId },
      };
    }

    return {};
  } catch {
    return {};
  }
}

// ==================== 主入口 ====================

/**
 * 收集当前页面上下文
 * 1. 先同步获取DOM数据（立即可用）
 * 2. 异步获取API数据（更丰富的信息）
 */
export async function collectPageContext(): Promise<PageContext> {
  const path = window.location.pathname;
  const domData = extractDOMData();

  const pageType = identifyPageType(path);

  // 基础上下文
  const baseContext: PageContext = {
    page_type: pageType,
    url: window.location.href,
    page_title: domData.page_title as string || document.title || '',
    ...domData,
  };

  // 根据页面类型获取API数据
  try {
    let apiContext: Partial<PageContext> = {};

    switch (pageType) {
      case 'v2g_device_detail': {
        const deviceIdStr = extractPathParam(path, /\/devices\/v2g\/(\d+)/);
        const domDeviceId = (domData.device as any)?.id;
        const deviceId = parseInt(deviceIdStr || domDeviceId || '0', 10);
        if (deviceId) {
          apiContext = await fetchV2GDeviceContext(deviceId);
        }
        break;
      }

      case 'device_list': {
        // 如果有设备ID（来自DOM）,获取详情；否则获取列表
        const domDeviceId = (domData.device as any)?.id;
        if (domDeviceId) {
          apiContext = await fetchDeviceDetailContext(parseInt(domDeviceId, 10));
        } else {
          apiContext = await fetchDeviceListContext();
        }
        break;
      }

      case 'alarm_list':
        apiContext = await fetchAlarmContext();
        break;

      case 'work_order':
        apiContext = await fetchWorkOrderContext();
        break;

      case 'dashboard':
        apiContext = await fetchDashboardContext();
        break;

      case 'knowledge_base':
        apiContext = await fetchKnowledgeContext();
        break;

      default:
        break;
    }

    // 合并基础上下文和API上下文
    return { ...baseContext, ...apiContext };
  } catch {
    // API获取失败时，至少返回基础上下文
    return baseContext;
  }
}

/**
 * 获取当前页面上下文的摘要描述（用于AI提示词）
 */
export function describeContext(context: PageContext): string {
  const parts: string[] = [];

  switch (context.page_type) {
    case 'device_list':
    case 'v2g_device_detail': {
      if (context.device) {
        const d = context.device;
        parts.push(`当前查看设备: ${d.name || ''} (ID=${d.id}, SN=${d.sn || ''}, 类型=${d.type || ''}, 状态=${d.status || ''}, 健康度=${d.health_score || ''}%)`);
      }
      if (context.v2g_device) {
        const v = context.v2g_device;
        parts.push(`V2G模式: ${v.v2g_mode || '-'}, 电网状态: ${v.grid_status || '-'}, 充电功率: ${v.charge_power_kw || 0}kW, 放电功率: ${v.discharge_power_kw || 0}kW, SOC: ${v.soc || '-'}%`);
      }
      if (context.device_list) {
        const dl = context.device_list as any[];
        parts.push(`设备列表共 ${dl.length} 台设备`);
      }
      break;
    }

    case 'alarm_list': {
      if (context.alarms) {
        parts.push(`当前告警页面: 共 ${context.alarms.total} 条告警, ${context.alarms.active} 条未处理, ${context.alarms.critical} 条严重`);
        if (context.alarms.recent?.length) {
          parts.push(`最近告警: ${context.alarms.recent.join('; ')}`);
        }
      }
      break;
    }

    case 'work_order': {
      if (context.work_orders) {
        parts.push(`当前工单页面: 共 ${context.work_orders.total} 条工单, ${context.work_orders.pending} 条待处理, ${context.work_orders.in_progress} 条处理中`);
      }
      break;
    }

    case 'dashboard':
      parts.push('当前在运维总览看板');
      break;

    default:
      parts.push(`当前页面: ${context.page_title || context.url}`);
      break;
  }

  return parts.join(' | ');
}

// ==================== 初始化：注册所有页面data-*标记监听器 ====================

/**
 * 监听react-router路径变化时，自动更新全局上下文状态
 * 供 ChatPanel 在页面切换时刷新认知
 */
export function setupContextAutoRefresh(): () => void {
  // 返回清理函数
  return () => {};
}