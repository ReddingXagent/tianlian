/**
 * 权限工具测试 — 匹配当前 UserType 模型 (admin/engineer/operator/fleet)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  mapBackendRole,
  getEntryType,
  setUserType,
  getUserType,
  getUserRole,
  getCurrentUser,
  isPlatformEntry,
  isOpsEntry,
  canAccessRoute,
  getDefaultRoute,
} from '../auth';

describe('auth utilities', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe('mapBackendRole', () => {
    it('ADMIN 应映射为 admin', () => {
      expect(mapBackendRole('ADMIN')).toBe('admin');
    });
    it('platform_admin 应映射为 admin', () => {
      expect(mapBackendRole('platform_admin')).toBe('admin');
    });
    it('ENGINEER 应映射为 engineer', () => {
      expect(mapBackendRole('ENGINEER')).toBe('engineer');
    });
    it('OPERATOR 应映射为 operator', () => {
      expect(mapBackendRole('OPERATOR')).toBe('operator');
    });
    it('FLEET 应映射为 fleet', () => {
      expect(mapBackendRole('FLEET')).toBe('fleet');
    });
    it('空字符串应默认 engineer', () => {
      expect(mapBackendRole('')).toBe('engineer');
    });
    it('null 应默认 engineer', () => {
      expect(mapBackendRole(null as any)).toBe('engineer');
    });
  });

  describe('user type (new API)', () => {
    it('默认应为 engineer', () => {
      expect(getUserType()).toBe('engineer');
    });
    it('setUserType 应正确设置', () => {
      setUserType('admin');
      expect(getUserType()).toBe('admin');
    });
  });

  describe('entry type (compat)', () => {
    it('默认应为 ops', () => {
      expect(getEntryType()).toBe('ops');
    });
    it('admin 用户对应 platform 入口', () => {
      setUserType('admin');
      expect(getEntryType()).toBe('platform');
    });
  });

  describe('isPlatformEntry / isOpsEntry', () => {
    it('admin 为 platform', () => {
      setUserType('admin');
      expect(isPlatformEntry()).toBe(true);
      expect(isOpsEntry()).toBe(false);
    });
    it('engineer 为 ops', () => {
      setUserType('engineer');
      expect(isPlatformEntry()).toBe(false);
      expect(isOpsEntry()).toBe(true);
    });
  });

  describe('getUserRole', () => {
    it('无用户时应返回 engineer', () => {
      expect(getUserRole()).toBe('engineer');
    });
    it('应正确解析用户角色（toLowerCase）', () => {
      localStorage.setItem('admin_user', JSON.stringify({ role: 'ADMIN' }));
      expect(getUserRole()).toBe('admin');
    });
    it('无效 JSON 应返回 engineer', () => {
      localStorage.setItem('admin_user', 'invalid');
      expect(getUserRole()).toBe('engineer');
    });
  });

  describe('getCurrentUser', () => {
    it('无用户应返回 null', () => {
      expect(getCurrentUser()).toBeNull();
    });
    it('应正确返回用户对象', () => {
      const user = { name: 'test', role: 'ENGINEER' };
      localStorage.setItem('admin_user', JSON.stringify(user));
      expect(getCurrentUser()).toEqual(user);
    });
  });

  describe('canAccessRoute', () => {
    it('admin 用户可访问所有页面', () => {
      setUserType('admin');
      expect(canAccessRoute('/gateway')).toBe(true);
      expect(canAccessRoute('/dashboard')).toBe(true);
      expect(canAccessRoute('/tenants')).toBe(true);
    });
    it('engineer 可访问运维路由，不可访问平台路由', () => {
      setUserType('engineer');
      expect(canAccessRoute('/dashboard')).toBe(true);
      expect(canAccessRoute('/stations')).toBe(true);
      expect(canAccessRoute('/gateway')).toBe(false);
      expect(canAccessRoute('/tenants')).toBe(false);
    });
    it('login 和 scan 始终可访问', () => {
      setUserType('engineer');
      expect(canAccessRoute('/login')).toBe(true);
      expect(canAccessRoute('/scan')).toBe(true);
    });
  });

  describe('canAccessRoute - platform entry', () => {
    it('platform 入口应允许平台路由', () => {
      setUserType('admin');
      expect(canAccessRoute('/gateway')).toBe(true);
      expect(canAccessRoute('/links')).toBe(true);
      expect(canAccessRoute('/tenants')).toBe(true);
    });
    it('platform 入口应允许共享路由', () => {
      setUserType('admin');
      expect(canAccessRoute('/audit-log')).toBe(true);
      expect(canAccessRoute('/report-mgmt')).toBe(true);
    });
    it('platform 入口应允许 rbac 路由', () => {
      setUserType('admin');
      expect(canAccessRoute('/rbac/users')).toBe(true);
    });
    it('platform 入口应允许 login', () => {
      setUserType('admin');
      expect(canAccessRoute('/login')).toBe(true);
    });
  });

  describe('canAccessRoute - ops entry', () => {
    it('ops 入口应允许运维路由', () => {
      setUserType('engineer');
      expect(canAccessRoute('/dashboard')).toBe(true);
      expect(canAccessRoute('/stations')).toBe(true);
      expect(canAccessRoute('/devices')).toBe(true);
      expect(canAccessRoute('/alarms')).toBe(true);
      expect(canAccessRoute('/workorders')).toBe(true);
      expect(canAccessRoute('/inspection-ops')).toBe(true);
      expect(canAccessRoute('/on-call')).toBe(true);
      expect(canAccessRoute('/telemetry')).toBe(true);
    });
    it('ops 入口应允许 login 和 scan', () => {
      setUserType('engineer');
      expect(canAccessRoute('/login')).toBe(true);
      expect(canAccessRoute('/scan')).toBe(true);
    });
    it('ops 入口应拒绝平台路由', () => {
      setUserType('engineer');
      expect(canAccessRoute('/gateway')).toBe(false);
      expect(canAccessRoute('/links')).toBe(false);
      expect(canAccessRoute('/tenants')).toBe(false);
    });
  });

  describe('getDefaultRoute', () => {
    it('admin 应返回 /platform/dashboard', () => {
      setUserType('admin');
      expect(getDefaultRoute()).toBe('/platform/dashboard');
    });
    it('engineer 应返回 /dashboard', () => {
      setUserType('engineer');
      expect(getDefaultRoute()).toBe('/dashboard');
    });
  });

  describe('getUserRole - various roles', () => {
    it('ops_admin 应 lowercase', () => {
      localStorage.setItem('admin_user', JSON.stringify({ role: 'OPS_ADMIN' }));
      expect(getUserRole()).toBe('ops_admin');
    });
    it('technician 应 lowercase', () => {
      localStorage.setItem('admin_user', JSON.stringify({ role: 'TECHNICIAN' }));
      expect(getUserRole()).toBe('technician');
    });
    it('未知角色应保留原值（lowercased）', () => {
      localStorage.setItem('admin_user', JSON.stringify({ role: 'UNKNOWN' }));
      expect(getUserRole()).toBe('unknown');
    });
  });

  describe('canAccessRoute - edge cases', () => {
    it('should allow ops route prefixes', () => {
      setUserType('engineer');
      expect(canAccessRoute('/stations/1')).toBe(true);
      expect(canAccessRoute('/devices/list')).toBe(true);
    });
    it('should handle rbac sub-routes', () => {
      setUserType('engineer');
      expect(canAccessRoute('/rbac/roles')).toBe(true);
      expect(canAccessRoute('/rbac/users/new')).toBe(true);
    });
  });
});