/**
 * 配置多租户化 (卡 d0c431d0) — Tab 可见性纯逻辑测试
 *
 * 覆盖:
 * - getVisibleTabKeys: 按 team_type 返回可见 Tab 集合 (4 类账户矩阵)
 * - resolveTeamType: 从用户上下文 (role + team_type) 解析当前 team_type
 */
import { describe, it, expect } from 'vitest';
import {
  getVisibleTabKeys,
  resolveTeamType,
  type ConfigTeamType,
  type ConfigTabKey,
} from '../configTabs';

// ═══════════════════════════════════════════
// getVisibleTabKeys — 4 类账户的 Tab 矩阵
// ═══════════════════════════════════════════
describe('getVisibleTabKeys — 按 team_type 过滤 Tab', () => {
  it('平台 admin → 全 6 业务 Tab + 运维专属占位', () => {
    const keys = getVisibleTabKeys('platform');
    // 六个业务 Tab 全部可见
    expect(keys).toEqual(expect.arrayContaining<ConfigTabKey>([
      'rbac', 'notification', 'audit', 'global', 'payment', 'invoice',
    ]));
    // 平台可见运维专属占位
    expect(keys).toContain('ops_panel');
  });

  it('ops_company → 通知/日志/全局/支付/发票 (无权限配置)', () => {
    const keys = getVisibleTabKeys('ops_company');
    expect(keys).toEqual(['notification', 'audit', 'global', 'payment', 'invoice']);
    // 运营公司看不到平台级权限配置
    expect(keys).not.toContain('rbac');
    // 运营公司无需运维专属/车队占位
    expect(keys).not.toContain('ops_panel');
    expect(keys).not.toContain('fleet_panel');
  });

  it('maintenance_team → 通知/日志/全局 + 运维专属占位', () => {
    const keys = getVisibleTabKeys('maintenance_team');
    expect(keys).toEqual(['notification', 'audit', 'global', 'ops_panel']);
    // 运维团队不涉及支付/发票/权限配置
    expect(keys).not.toContain('payment');
    expect(keys).not.toContain('invoice');
    expect(keys).not.toContain('rbac');
  });

  it('fleet → 仅通知 + 车队专属占位', () => {
    const keys = getVisibleTabKeys('fleet');
    expect(keys).toEqual(['notification', 'fleet_panel']);
    // 车队只看通知基础项, 不涉及日志/全局/支付/发票/权限
    expect(keys).not.toContain('audit');
    expect(keys).not.toContain('global');
    expect(keys).not.toContain('payment');
    expect(keys).not.toContain('invoice');
    expect(keys).not.toContain('rbac');
  });

  it('每个 team_type 至少返回一个 Tab (永远有可渲染内容)', () => {
    const types: ConfigTeamType[] = ['platform', 'ops_company', 'maintenance_team', 'fleet'];
    for (const t of types) {
      expect(getVisibleTabKeys(t).length).toBeGreaterThan(0);
    }
  });

  it('通知 Tab 对所有 team_type 可见 (最小公共项)', () => {
    const types: ConfigTeamType[] = ['platform', 'ops_company', 'maintenance_team', 'fleet'];
    for (const t of types) {
      expect(getVisibleTabKeys(t)).toContain('notification');
    }
  });

  it('返回新数组 (调用方 mutate 不污染内部常量)', () => {
    const a = getVisibleTabKeys('ops_company');
    a.push('rbac');
    const b = getVisibleTabKeys('ops_company');
    expect(b).not.toContain('rbac');
  });
});

// ═══════════════════════════════════════════
// resolveTeamType — 用户上下文解析
// ═══════════════════════════════════════════
describe('resolveTeamType — 从用户上下文解析 team_type', () => {
  it('role=admin → platform', () => {
    expect(resolveTeamType({ role: 'admin' })).toBe('platform');
  });

  it('role=super_admin → platform', () => {
    expect(resolveTeamType({ role: 'super_admin' })).toBe('platform');
  });

  it('user_type=admin (无 role) → platform', () => {
    expect(resolveTeamType({ user_type: 'admin' })).toBe('platform');
  });

  it('team_type=ops_company 优先于 role 映射', () => {
    expect(resolveTeamType({ role: 'engineer', team_type: 'ops_company' })).toBe('ops_company');
  });

  it('team_type=maintenance_team', () => {
    expect(resolveTeamType({ role: 'engineer', team_type: 'maintenance_team' })).toBe('maintenance_team');
  });

  it('team_type=fleet', () => {
    expect(resolveTeamType({ role: 'fleet', team_type: 'fleet' })).toBe('fleet');
  });

  it('平台角色压过 team_type (admin 即使带 team_type 仍判为 platform)', () => {
    // 平台管理员跨团队, 不应被锁进单团队视图
    expect(resolveTeamType({ role: 'admin', team_type: 'ops_company' })).toBe('platform');
  });

  it('无 team_type 时按 user_type=fleet 兜底为 fleet', () => {
    expect(resolveTeamType({ user_type: 'fleet' })).toBe('fleet');
  });

  it('无 team_type 的 engineer/operator 兜底为 ops_company (匹配后端 server_default)', () => {
    expect(resolveTeamType({ role: 'engineer' })).toBe('ops_company');
    expect(resolveTeamType({ user_type: 'operator' })).toBe('ops_company');
  });

  it('用户对象为 null/undefined → 兜底 ops_company', () => {
    expect(resolveTeamType(null)).toBe('ops_company');
    expect(resolveTeamType(undefined)).toBe('ops_company');
  });

  it('未知 team_type 值 → 走 role/user_type 兜底链', () => {
    expect(resolveTeamType({ role: 'engineer', team_type: 'unknown_type' })).toBe('ops_company');
  });

  it('role 大小写不敏感', () => {
    expect(resolveTeamType({ role: 'ADMIN' })).toBe('platform');
    expect(resolveTeamType({ role: 'Fleet' })).toBe('fleet');
  });
});
