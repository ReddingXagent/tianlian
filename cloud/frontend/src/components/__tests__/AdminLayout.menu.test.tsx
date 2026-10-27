/**
 * AdminLayout 菜单高亮 / 子菜单展开 测试（根因3、根因4）
 *
 * 根因3：selectedKeys 只用 pathname 不含 search → fleet 菜单 /fleet?tab=xxx 项永不高亮。
 *        修复：selectedKeys = [pathname + search]。
 * 根因4：defaultOpenKeys 仅在 /rbac 展开 → 直接 URL 进入子菜单页（/operate/users 等）父级不展开。
 *        修复：据 pathname 计算需展开的父级 key（受控 openKeys + onOpenChange）。
 *
 * 与 AdminLayout.test.tsx 区别：本文件用【真实 menuConfig】（不 mock），以验证真实菜单结构的高亮/展开。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import AdminLayout from '../Layout/AdminLayout';
import { setUserType } from '../../utils/auth';

// AdminLayout 渲染时会请求告警统计；屏蔽 API 副作用
vi.mock('../../api', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: {} }) },
  alarmAPI: { stats: vi.fn().mockResolvedValue({ data: { active: 0 } }) },
  stationAPI: { list: vi.fn().mockResolvedValue({ data: { items: [] } }) },
}));

describe('AdminLayout 菜单高亮 (根因3) — selectedKeys 须含 search', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('admin_token', 'test-token');
    setUserType('fleet');
  });

  it('/fleet?tab=vehicles 高亮"车辆管理"而非"车队总览"', () => {
    render(
      <MemoryRouter initialEntries={['/fleet?tab=vehicles']}>
        <Routes>
          <Route path="/" element={<AdminLayout />}>
            <Route path="fleet" element={<div>Fleet</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const selected = document.querySelectorAll('.ant-menu-item-selected');
    const selectedText = [...selected].map((el) => el.textContent || '').join(' | ');
    expect(selectedText).toContain('车辆管理');
    expect(selectedText).not.toContain('车队总览');
  });

  it('/fleet?tab=drivers 高亮"司机管理"', () => {
    render(
      <MemoryRouter initialEntries={['/fleet?tab=drivers']}>
        <Routes>
          <Route path="/" element={<AdminLayout />}>
            <Route path="fleet" element={<div>Fleet</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const selected = document.querySelectorAll('.ant-menu-item-selected');
    const selectedText = [...selected].map((el) => el.textContent || '').join(' | ');
    expect(selectedText).toContain('司机管理');
  });
});

describe('AdminLayout 子菜单展开 (根因4) — 直接 URL 进入须展开父级', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('admin_token', 'test-token');
  });

  it('operator /operate/users 自动展开父菜单"运营管理"', () => {
    setUserType('operator');
    render(
      <MemoryRouter initialEntries={['/operate/users']}>
        <Routes>
          <Route path="/" element={<AdminLayout />}>
            <Route path="operate" element={<div>Operate</div>} />
            <Route path="operate/:tab" element={<div>Operate Tab</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const openSubmenu = document.querySelector('.ant-menu-submenu-open');
    expect(openSubmenu).toBeInTheDocument();
    expect(openSubmenu?.textContent || '').toContain('运营管理');
  });

  it('engineer /teams/engineers 自动展开父菜单"团队管理"', () => {
    setUserType('engineer');
    render(
      <MemoryRouter initialEntries={['/teams/engineers']}>
        <Routes>
          <Route path="/" element={<AdminLayout />}>
            <Route path="teams" element={<div>Teams</div>} />
            <Route path="teams/engineers" element={<div>Engineers</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const openSubmenu = document.querySelector('.ant-menu-submenu-open');
    expect(openSubmenu).toBeInTheDocument();
    expect(openSubmenu?.textContent || '').toContain('团队管理');
  });

  // /tenants/data 同 pathname 双挂载（?type=ops_company|maintenance_team 仅 query 区分），
  // 展开归属须由 query 决定；无 type 降级仅按 pathname 命中菜单序在前的"运营公司管理"。
  it('admin /tenants/data?type=maintenance_team 自动展开父菜单"运维团队管理"', () => {
    setUserType('admin');
    render(
      <MemoryRouter initialEntries={['/tenants/data?type=maintenance_team']}>
        <Routes>
          <Route path="/" element={<AdminLayout />}>
            <Route path="tenants" element={<div>Tenants</div>} />
            <Route path="tenants/data" element={<div>Tenants Data</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const openSubmenus = document.querySelectorAll('.ant-menu-submenu-open');
    expect(openSubmenus.length).toBeGreaterThan(0);
    const openText = [...openSubmenus].map((el) => el.textContent || '').join(' | ');
    expect(openText).toContain('运维团队管理');
    expect(openText).not.toContain('运营公司管理');
  });

  it('admin /tenants/data?type=ops_company 自动展开父菜单"运营公司管理"', () => {
    setUserType('admin');
    render(
      <MemoryRouter initialEntries={['/tenants/data?type=ops_company']}>
        <Routes>
          <Route path="/" element={<AdminLayout />}>
            <Route path="tenants" element={<div>Tenants</div>} />
            <Route path="tenants/data" element={<div>Tenants Data</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const openSubmenus = document.querySelectorAll('.ant-menu-submenu-open');
    expect(openSubmenus.length).toBeGreaterThan(0);
    const openText = [...openSubmenus].map((el) => el.textContent || '').join(' | ');
    expect(openText).toContain('运营公司管理');
    expect(openText).not.toContain('运维团队管理');
  });

  it('admin /tenants/data 无 type 降级展开"运营公司管理"', () => {
    setUserType('admin');
    render(
      <MemoryRouter initialEntries={['/tenants/data']}>
        <Routes>
          <Route path="/" element={<AdminLayout />}>
            <Route path="tenants" element={<div>Tenants</div>} />
            <Route path="tenants/data" element={<div>Tenants Data</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const openSubmenu = document.querySelector('.ant-menu-submenu-open');
    expect(openSubmenu).toBeInTheDocument();
    expect(openSubmenu?.textContent || '').toContain('运营公司管理');
  });
});
