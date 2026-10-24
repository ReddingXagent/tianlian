/**
 * 配置多租户化 (卡 d0c431d0) — Tab 可见性与 team_type 解析
 *
 * 后端 cf614348 引入 Team.type (ops_company / maintenance_team / fleet) +
 * 平台 admin, 并按 team_type 隔离配置域。前端据此决定每个账户类型在
 * /config 页面可见的 Tab 集合, 数据隔离由后端 + X-Team-Id header 负责,
 * 前端只控制呈现并兜底处理 403。
 *
 * 矩阵:
 *   platform         通知/日志/全局/支付/发票/权限配置 + 运维专属占位 (全量)
 *   ops_company      通知/日志/全局/支付/发票 (本团队数据)
 *   maintenance_team 通知/日志/全局 + 运维专属占位
 *   fleet            通知 + 车队专属占位
 */

/** 账户层级类型: 平台 + 后端 TeamType 三值 */
export type ConfigTeamType = 'platform' | 'ops_company' | 'maintenance_team' | 'fleet';

/** /config 页面全部 Tab key (业务 Tab + 占位面板) */
export type ConfigTabKey =
  | 'rbac'
  | 'notification'
  | 'audit'
  | 'global'
  | 'payment'
  | 'invoice'
  | 'fleet_panel'
  | 'ops_panel';

/** 视为平台管理员的 role/user_type 集合 (跨团队, 见全量 Tab) */
export const PLATFORM_ADMIN_ROLES = new Set(['admin', 'super_admin', 'platform_admin']);

/** 平台 admin: 六个业务 Tab + 运维专属占位 */
const PLATFORM_TAB_KEYS: readonly ConfigTabKey[] = [
  'rbac', 'notification', 'audit', 'global', 'payment', 'invoice', 'ops_panel',
];

/** ops_company: 本团队通知/日志/全局/支付/发票 */
const OPS_COMPANY_TAB_KEYS: readonly ConfigTabKey[] = [
  'notification', 'audit', 'global', 'payment', 'invoice',
];

/** maintenance_team: 通知/日志/全局 + 运维专属占位 */
const MAINTENANCE_TAB_KEYS: readonly ConfigTabKey[] = [
  'notification', 'audit', 'global', 'ops_panel',
];

/** fleet: 仅通知基础项 + 车队专属占位 */
const FLEET_TAB_KEYS: readonly ConfigTabKey[] = ['notification', 'fleet_panel'];

const TAB_KEYS_BY_TEAM_TYPE: Record<ConfigTeamType, readonly ConfigTabKey[]> = {
  platform: PLATFORM_TAB_KEYS,
  ops_company: OPS_COMPANY_TAB_KEYS,
  maintenance_team: MAINTENANCE_TAB_KEYS,
  fleet: FLEET_TAB_KEYS,
};

/**
 * 按 team_type 返回可见 Tab key 列表。
 * 返回新数组, 调用方可安全 mutate。
 */
export function getVisibleTabKeys(teamType: ConfigTeamType): ConfigTabKey[] {
  return [...TAB_KEYS_BY_TEAM_TYPE[teamType]];
}

/**
 * 从用户上下文 (localStorage admin_user) 解析当前 team_type。
 *
 * 优先级:
 *   1. 平台管理员 role (admin/super_admin/platform_admin) → 'platform'
 *      (平台跨团队, 压过 team_type, 避免被锁进单团队视图)
 *   2. user.team_type (后端 /auth/me+login 应回填) → 原值
 *   3. user_type=fleet → 'fleet'
 *   4. 其余 (engineer/operator/未知/null) → 'ops_company'
 *      (匹配后端 Team.type server_default='ops_company')
 *
 * 说明: 后端 cf614348 已建 Team.type 列与 scope 矩阵, 但 /auth/me 与 login
 * 响应暂未回填 team_type; 在后端补回填前, 非 fleet 的非平台用户统一兜底为
 * ops_company, 与后端存量 Team 默认值一致, 不会出现“空 Tab 集”。
 */
export function resolveTeamType(user: unknown): ConfigTeamType {
  if (!user || typeof user !== 'object') return 'ops_company';
  const u = user as Record<string, unknown>;

  const roleRaw = String(u.role ?? u.user_type ?? '').toLowerCase();
  if (PLATFORM_ADMIN_ROLES.has(roleRaw)) return 'platform';

  const teamTypeRaw = String(u.team_type ?? '').toLowerCase();
  if (
    teamTypeRaw === 'ops_company' ||
    teamTypeRaw === 'maintenance_team' ||
    teamTypeRaw === 'fleet'
  ) {
    return teamTypeRaw;
  }

  if (roleRaw === 'fleet') return 'fleet';

  return 'ops_company';
}
