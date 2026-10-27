import { getUserRaw } from './authStorage';

/**
 * 权限工具 - 天链V3 四入口权限模型（2026-07-02）
 * 
 * 用户类型（user_type）决定用户看到哪套菜单和首页：
 * - 'admin': 系统管理员（SaaS平台管理 + 公共服务）
 * - 'engineer': 运维工程师（站点/设备/告警/工单等运维业务）
 * - 'operator': 运营人员（运营分析/报表/数据看板）
 * - 'fleet': 车队管理（车队调度/充电站/车辆管理）
 */

export type UserType = 'admin' | 'engineer' | 'operator' | 'fleet';

/** 从后端 role 字段映射为用户类型 */
export function mapBackendRole(backendRole: string): UserType {
  const r = (backendRole || '').toLowerCase();
  if (r === 'admin' || r === 'platform_admin') return 'admin';
  if (r === 'engineer') return 'engineer';
  if (r === 'operator') return 'operator';
  if (r === 'fleet') return 'fleet';
  // 默认：运维工程师
  return 'engineer';
}

/** 获取当前用户类型 */
export function getUserType(): UserType {
  return (localStorage.getItem('user_type') as UserType) || 'engineer';
}

/** 设置用户类型 */
export function setUserType(type: UserType): void {
  localStorage.setItem('user_type', type);
}

/** 获取当前用户角色（从 localStorage 中存储的 user 对象读取） */
export function getUserRole(): string {
  try {
    const userStr = getUserRaw();
    if (userStr) {
      const user = JSON.parse(userStr);
      return (user.role || user.user_type || '').toLowerCase();
    }
  } catch { /* ignore */ }
  return 'engineer';
}

/** 获取当前用户信息 */
export function getCurrentUser(): any | null {
  try {
    const userStr = getUserRaw();
    if (userStr) return JSON.parse(userStr);
  } catch { /* ignore */ }
  return null;
}

/** 兼容旧版本 entry_type（逐步废弃） */
export function getEntryType(): 'platform' | 'ops' {
  const ut = getUserType();
  if (ut === 'admin') return 'platform';
  return 'ops';
}

/** 设置入口类型（兼容旧版本） */
export function setEntryType(type: 'platform' | 'ops'): void {
  // 已废弃，改用 setUserType
}

/** 是否为平台管理入口 */
export function isPlatformEntry(): boolean {
  return getUserType() === 'admin';
}

/** 是否为运维管理入口 */
export function isOpsEntry(): boolean {
  return ['engineer', 'operator', 'fleet'].includes(getUserType());
}

// 路由权限定义
const ADMIN_ROUTES = [
  '/gateway', '/tenants', '/device-library', '/device-protocols',
  '/protocols', '/links', '/cloud', '/terminals', '/edge-gateways',
];

const ENGINEER_ROUTES = [
  '/dashboard', '/stations', '/devices', '/alarms', '/workorders',
  '/workorder-stats', '/inspection-ops', '/on-call', '/healing',
  '/telemetry', '/telemetry-classic', '/fault-diagnosis',
  '/smart-diagnosis', '/runbook', '/predictive-maintenance',
  '/ops-dashboard', '/monitor', '/diagnosis', '/alarm-notices',
  '/map', '/health', '/teams',
];

const OPERATOR_ROUTES = [
  '/operate', '/reports', '/report-mgmt', '/energy-report',
  '/analytics-dashboard', '/vpp', '/digital-twin', '/owner-cockpit',
];

const FLEET_ROUTES = [
  '/fleet', '/stations', '/dashboard', '/alarms',
];

const SHARED_ROUTES = [
  '/knowledge', '/audit-log', '/config', '/rbac', '/scan', '/test',
  '/login', '/message-center',
];

/** 获取用户可访问的路由列表 */
export function getAllowedRoutes(): string[] {
  const ut = getUserType();
  switch (ut) {
    case 'admin':
      return [...ADMIN_ROUTES, ...SHARED_ROUTES];
    case 'engineer':
      return [...ENGINEER_ROUTES, ...OPERATOR_ROUTES, ...FLEET_ROUTES, ...SHARED_ROUTES];
    case 'operator':
      return [...OPERATOR_ROUTES, ...ENGINEER_ROUTES.filter(r =>
        ['/stations', '/devices', '/alarms', '/workorders', '/reports'].includes(r)
      ), ...SHARED_ROUTES];
    case 'fleet':
      return [...FLEET_ROUTES, ...ENGINEER_ROUTES.filter(r =>
        ['/stations', '/devices'].includes(r)
      ), ...SHARED_ROUTES];
    default:
      return [...ENGINEER_ROUTES, ...SHARED_ROUTES];
  }
}

/** 检查用户是否可以访问指定路由 */
export function canAccessRoute(pathname: string): boolean {
  if (pathname === '/login' || pathname === '/scan') return true;

  const ut = getUserType();

  // admin 可访问所有
  if (ut === 'admin') return true;

  // 共享路由所有人都可访问
  if (SHARED_ROUTES.some(r => pathname.startsWith(r))) return true;

  const allowed = getAllowedRoutes();
  return allowed.some(r => pathname.startsWith(r));
}

/** 获取路由被拒绝时应跳转的默认路由 */
export function getDefaultRoute(): string {
  const ut = getUserType();
  switch (ut) {
    case 'admin': return '/platform/dashboard';
    case 'engineer': return '/dashboard';
    case 'operator': return '/operate';
    case 'fleet': return '/fleet';
    default: return '/dashboard';
  }
}

/** 保存入口类型（登录时使用） */

/** 用户类型中文名称映射 */
export const USER_TYPE_LABELS: Record<UserType, string> = {
  admin: '系统管理员',
  engineer: '运维工程师',
  operator: '运营人员',
  fleet: '车队管理',
};

/** 用户类型描述 */
export const USER_TYPE_DESCRIPTIONS: Record<UserType, string> = {
  admin: '管理系统配置、团队账户与公共服务',
  engineer: '管理站点设备、告警工单等运维业务',
  operator: '运营数据分析、报表看板与决策支持',
  fleet: '车队调度管理、充电站运营与车辆监控',
};