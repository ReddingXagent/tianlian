/**
 * 菜单 ↔ 路由 一致性测试（验收点1）
 *
 * 校验四套菜单(admin/engineer/operator/fleet)的每个叶子菜单项：
 *   (a) canAccessRoute(stripQuery(key)) 在该 userType 下返回 true
 *   (b) stripQuery(key) 在 App.tsx 路由表中存在匹配（静态检查）
 * 并校验 admin 点击运维路由组(path="/")下的菜单不被 RouteGuard 弹回 /gateway（根因1）。
 *
 * 背景：左侧菜单项存在但点击后被 RouteGuard 静默重定向回首页，共 4 处漂移。
 * 本测试为 (a)/(b) 的全叶子回归网 + 根因1 的端到端守卫。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { getMenuItems, type MenuItem } from '../menuConfig';
import { canAccessRoute, setUserType, type UserType } from '../../utils/auth';
import App from '../../App';

// 渲染真实 App 时屏蔽非必要的全局浮窗（聚焦路由守卫判定，避免 lazy 副作用噪声）
vi.mock('../../components/ChatPanel', () => ({ default: () => null }));
vi.mock('../../components/OfflineNotice', () => ({ default: () => null }));

const USER_TYPES: UserType[] = ['admin', 'engineer', 'operator', 'fleet'];

/** 递归收集菜单叶子节点 key（无 children 的项；带 children 的是分组容器，非可达路由） */
function collectLeaves(items: MenuItem[]): string[] {
  const out: string[] = [];
  const walk = (list: MenuItem[]) => {
    for (const it of list) {
      if (it.children && it.children.length > 0) walk(it.children);
      else out.push(it.key);
    }
  };
  walk(items);
  return out;
}

/** 去掉 querystring（fleet 菜单 key 形如 /fleet?tab=vehicles，路由匹配只看 pathname） */
const stripQuery = (key: string) => key.split('?')[0];

/** 段级路由匹配：:param 段视为通配（/operate/:tab 匹配 /operate/users） */
function matchRoute(path: string, patterns: string[]): boolean {
  const pathSegs = path.split('/').filter(Boolean);
  return patterns.some((p) => {
    const pSegs = p.split('/').filter(Boolean);
    if (pSegs.length !== pathSegs.length) return false;
    return pSegs.every((seg, i) => seg.startsWith(':') || seg === pathSegs[i]);
  });
}

/**
 * App.tsx 路由表镜像 —— 列出 src/App.tsx 中所有 <Route path=...> 的可达路径模式。
 * ⚠️ 与 App.tsx 路由声明一一对应；App.tsx 增删路由时务必同步本清单，
 *   否则会误报（菜单指向路由表没有的“幽灵路由”）或漏报。
 */
const APP_ROUTE_PATTERNS = [
  // ===== path="/" 运维管理组 (engineer/operator/fleet，修复后含 admin) =====
  '/dashboard', '/devices', '/devices/v2g', '/devices/v2g/:id',
  '/stations', '/workorders', '/workorder-stats', '/alarms', '/reports',
  '/report-mgmt', '/teams', '/teams/engineers', '/teams/roles', '/users',
  '/health', '/security', '/inspection-ops', '/telemetry', '/telemetry-classic',
  '/fault-diagnosis', '/on-call', '/smart-diagnosis', '/runbook', '/healing',
  '/energy-report', '/digital-twin', '/digital-twin/:stationId', '/vpp',
  '/predictive-maintenance', '/ops-dashboard', '/analytics-dashboard',
  '/reports/utilization', '/reports/efficiency', '/reports/generation',
  '/monitor', '/diagnosis', '/alarm-notices', '/api-keys', '/log-analysis',
  '/notification-rules', '/message-center', '/runbook-approval',
  '/ssl-certificates', '/webhooks', '/operate', '/operate/:tab', '/fleet',
  '/map', '/data-ops', '/discount-management', '/coupon-management', '/points-management',
  '/user-type-management', '/interconnect', '/supervision',
  // ===== /platform 平台管理组 (admin) =====
  '/platform', '/platform/dashboard',
  // ===== admin 独立守卫组 =====
  '/gateway', '/device-library', '/device-protocols', '/protocols',
  '/tenants', '/tenants/data', '/tenants/accounts',
  '/links', '/cloud', '/terminals', '/edge-gateways',
  // 经营驾驶舱 (admin/operator 独立守卫组, App.tsx:303-312)
  '/owner-cockpit',
  // ===== admin 菜单用到的重定向源 =====
  '/admin', '/admin/interconnect', '/admin/supervision',
  // ===== 共享守卫组 (无 allowedUserTypes 限制) =====
  '/knowledge', '/knowledge/detail/:id', '/knowledge/edit/:id', '/knowledge/create',
  '/audit-log', '/config', '/ai-model_config',
  '/rbac', '/rbac/users', '/rbac/roles', '/rbac/teams', '/rbac/teams/engineers',
];

// ============================================================
// (a) canAccessRoute：四套菜单所有叶子在该 userType 下必须放行
//     覆盖根因2：auth.ts 白名单缺 /teams(engineer) /alarms(fleet) /message-center(operator)
// ============================================================
describe('菜单-路由一致性 (a) — canAccessRoute 全叶子放行', () => {
  for (const ut of USER_TYPES) {
    describe(`${ut} 菜单`, () => {
      const leaves = [...new Set(collectLeaves(getMenuItems(ut)))];
      beforeEach(() => setUserType(ut));

      it.each(leaves)('%s 可访问', (key) => {
        expect(canAccessRoute(stripQuery(key))).toBe(true);
      });
    });
  }
});

// ============================================================
// (b) 路由表存在性：四套菜单所有叶子去 query 后必须在 App.tsx 有匹配路由
//     防止“菜单指向路由表不存在的幽灵路径”（健康回归网）
// ============================================================
describe('菜单-路由一致性 (b) — App.tsx 路由表存在匹配', () => {
  for (const ut of USER_TYPES) {
    describe(`${ut} 菜单`, () => {
      const leaves = [...new Set(collectLeaves(getMenuItems(ut)))];

      it.each(leaves)('%s 在路由表中有匹配', (key) => {
        expect(matchRoute(stripQuery(key), APP_ROUTE_PATTERNS)).toBe(true);
      });
    });
  }
});

// ============================================================
// 根因1：admin 点击 path="/" 运维路由组下的菜单不被 RouteGuard 弹回 /gateway
//   path="/" 组 RouteGuard allowedUserTypes 原为 [engineer,operator,fleet]，缺 admin。
//   渲染真实 App + location probe，断言未被 Navigate 重定向到 admin 默认首页 /gateway。
// ============================================================
describe('根因1 — admin 菜单点击不被重定向到 /gateway', () => {
  let lastPathname = '';
  const Probe = () => {
    lastPathname = useLocation().pathname;
    return null;
  };

  beforeEach(() => {
    localStorage.setItem('admin_token', 'test-token');
    setUserType('admin');
    lastPathname = '';
  });

  const renderAppAt = (initial: string) =>
    render(
      <MemoryRouter initialEntries={[initial]}>
        <App />
        <Probe />
      </MemoryRouter>,
    );

  // admin 菜单中落在运维路由组(path="/" + RouteGuard) 的叶子，修复前会被弹回 /gateway
  const adminPathsInOpsGroup = [
    '/security',
    '/log-analysis',
    '/message-center',
    '/notification-rules',
    '/api-keys',
    '/runbook-approval',
    '/ssl-certificates',
  ];

  it.each(adminPathsInOpsGroup)('%s 应留在原页（不回 /gateway）', (path) => {
    const { unmount } = renderAppAt(path);
    expect(lastPathname).toBe(path);
    unmount();
  });

  it('/admin/supervision 重定向到 /operate/supervision（不回 /gateway）', () => {
    const { unmount } = renderAppAt('/admin/supervision');
    expect(lastPathname).toBe('/operate/supervision');
    unmount();
  });
});
