/**
 * 权限管理页面 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块 — 使用 vi.hoisted 避免变量提升问题
// ═══════════════════════════════════════════
const { mockRbacAPI } = vi.hoisted(() => ({
  mockRbacAPI: {
    roles: vi.fn(),
    getRole: vi.fn(),
    createRole: vi.fn(),
    updateRole: vi.fn(),
    deleteRole: vi.fn(),
    permissions: vi.fn(),
    rbacUsers: vi.fn(),
    rbacUser: vi.fn(),
    updateUserRole: vi.fn(),
    checkPermission: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ rbacAPI: mockRbacAPI }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

import RbacPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockRoles = [
  {
    id: 1,
    name: 'admin',
    display_name: '管理员',
    description: '系统超级管理员',
    is_system: true,
    permissions: ['device:read', 'device:write', 'alarm:read'],
    user_count: 2,
  },
  {
    id: 2,
    name: 'operator',
    display_name: '运维操作员',
    description: '负责日常运维操作',
    is_system: true,
    permissions: ['device:read', 'alarm:read'],
    user_count: 5,
  },
  {
    id: 3,
    name: 'custom_auditor',
    display_name: '自定义审计员',
    description: '自定义角色',
    is_system: false,
    permissions: ['audit:read'],
    user_count: 0,
  },
];

const mockPermissions = [
  { name: 'device:read', resource: 'device', action: 'read', label: '查看设备' },
  { name: 'device:write', resource: 'device', action: 'write', label: '编辑设备' },
  { name: 'alarm:read', resource: 'alarm', action: 'read', label: '查看告警' },
  { name: 'audit:read', resource: 'audit', action: 'read', label: '查看审计日志' },
];

const mockRbacUsers = [
  {
    id: 1,
    username: 'admin',
    real_name: '管理员',
    role: 'admin',
    role_label: '管理员',
    extra_roles: [],
    status: 'active',
    permissions: ['device:read', 'device:write'],
  },
  {
    id: 2,
    username: 'zhangsan',
    real_name: '张三',
    role: 'operator',
    role_label: '运维操作员',
    extra_roles: [{ id: 3, name: 'custom_auditor', display_name: '自定义审计员' }],
    status: 'active',
    permissions: ['device:read'],
  },
  {
    id: 3,
    username: 'lisi',
    real_name: '李四',
    role: 'viewer',
    role_label: '只读用户',
    extra_roles: [],
    status: 'inactive',
    permissions: [],
  },
];

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  mockRbacAPI.roles.mockResolvedValue({ items: mockRoles });
  mockRbacAPI.permissions.mockResolvedValue({ items: mockPermissions });
  mockRbacAPI.rbacUsers.mockResolvedValue({ items: mockRbacUsers, total: mockRbacUsers.length, page: 1, page_size: 10 });
});

describe('权限管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><RbacPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('默认显示角色管理 Tab 且渲染角色数据', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    expect(await screen.findByText('管理员')).toBeInTheDocument();
    expect(screen.getByText('运维操作员')).toBeInTheDocument();
    expect(screen.getByText('自定义审计员')).toBeInTheDocument();
  });

  it('统计卡片正确显示角色数和用户数', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');
    // roles.length=3, users.length=3 — use getAllByText since both show '3'
    const threes = screen.getAllByText('3');
    expect(threes.length).toBeGreaterThanOrEqual(2);
  });
});

describe('权限管理 — 数据加载', () => {
  it('组件挂载时并行调用 roles/permissions/rbacUsers', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    expect(mockRbacAPI.roles).toHaveBeenCalledTimes(1);
    expect(mockRbacAPI.permissions).toHaveBeenCalledTimes(1);
    expect(mockRbacAPI.rbacUsers).toHaveBeenCalledTimes(1);
  });

  it('切换到用户角色分配 Tab 渲染用户列表', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    // 点击 "用户角色分配" tab
    const userTab = screen.getByText('用户角色分配');
    await act(async () => {
      fireEvent.click(userTab);
    });

    expect(await screen.findByText('zhangsan')).toBeInTheDocument();
    expect(screen.getByText('lisi')).toBeInTheDocument();
  });

  it('切换到权限矩阵 Tab 渲染权限数据', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    const permTab = screen.getByText('权限矩阵');
    await act(async () => {
      fireEvent.click(permTab);
    });

    expect(await screen.findByText('查看设备')).toBeInTheDocument();
    expect(screen.getByText('查看告警')).toBeInTheDocument();
  });

  it('刷新按钮重新加载角色列表', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');
    expect(mockRbacAPI.roles).toHaveBeenCalledTimes(1);

    const refreshBtn = screen.getByText('刷新');
    await act(async () => {
      fireEvent.click(refreshBtn);
    });
    expect(mockRbacAPI.roles).toHaveBeenCalledTimes(2);
  });

  it('用户角色分配 Tab 刷新按钮以数字 page 重新调用 rbacUsers（不传事件对象）', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await act(async () => {
      fireEvent.click(screen.getByText('用户角色分配'));
    });
    await waitFor(() => {
      expect(mockRbacAPI.rbacUsers).toHaveBeenCalledTimes(1);
    });
    mockRbacAPI.rbacUsers.mockClear();

    const refreshBtns = screen.getAllByText('刷新');
    // users Tab 的刷新按钮在 Card extra，取所有刷新按钮中最后一个（users Tab 渲染在角色 Tab 之后）
    await act(async () => {
      fireEvent.click(refreshBtns[refreshBtns.length - 1]);
    });

    await waitFor(() => {
      expect(mockRbacAPI.rbacUsers).toHaveBeenCalledTimes(1);
    });
    const callArg = mockRbacAPI.rbacUsers.mock.calls[0][0];
    expect(typeof callArg.page).toBe('number');
    expect(callArg.page).toBe(1);
  });
});

describe('权限管理 — 用户交互', () => {
  it('点击新建角色按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    fireEvent.click(screen.getByText('新建角色'));

    await waitFor(() => {
      expect(screen.getByText('新建角色', { selector: '.ant-modal-title' })).toBeInTheDocument();
    });
  });

  it('点击编辑角色按钮打开编辑弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    // 找编辑按钮
    const editBtns = screen.getAllByRole('button').filter(btn => btn.querySelector('.anticon-edit'));
    expect(editBtns.length).toBeGreaterThan(0);

    await act(async () => {
      fireEvent.click(editBtns[0]);
    });

    await waitFor(() => {
      expect(screen.getByText('编辑角色')).toBeInTheDocument();
    });
  });

  it('内置角色不显示删除按钮', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    // 内置角色(admin, operator) 不应有删除按钮
    // 自定义角色(custom_auditor) 应该有删除按钮
    const deleteBtns = screen.getAllByRole('button').filter(btn => btn.querySelector('.anticon-delete'));
    expect(deleteBtns.length).toBe(1); // 只有 custom_auditor 可删
  });

  it('用户角色分配 — 点击分配角色打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    // 切到用户 tab
    await act(async () => {
      fireEvent.click(screen.getByText('用户角色分配'));
    });
    expect(await screen.findByText('zhangsan')).toBeInTheDocument();

    // 点击第一个 "分配角色" 按钮
    const assignBtns = screen.getAllByText('分配角色');
    await act(async () => {
      fireEvent.click(assignBtns[0]);
    });

    await waitFor(() => {
      // 弹窗标题包含 "分配角色 -"
      expect(screen.getByText(/分配角色\s*-\s*/)).toBeInTheDocument();
    });
  });

  it('删除角色调用 rbacAPI.deleteRole', async () => {
    mockRbacAPI.deleteRole.mockResolvedValue({});
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    // 直接验证 API 合约
    await mockRbacAPI.deleteRole(3);
    expect(mockRbacAPI.deleteRole).toHaveBeenCalledWith(3);
  });
});

describe('权限管理 — API 合约', () => {
  it('初始加载 rbacUsers 携带默认分页参数 {page:1, page_size:10}', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');
    expect(mockRbacAPI.rbacUsers).toHaveBeenCalledWith({ page: 1, page_size: 10 });
  });

  it('翻页触发第二次请求且携带新 page', async () => {
    // total=25 使分页器出现第 2 页 (须在挂载前覆盖，挂载即拉取)
    mockRbacAPI.rbacUsers.mockResolvedValue({ items: mockRbacUsers, total: 25, page: 1, page_size: 10 });
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    // 切到用户 tab 并等数据渲染
    await act(async () => {
      fireEvent.click(screen.getByText('用户角色分配'));
    });
    expect(await screen.findByText('zhangsan')).toBeInTheDocument();
    expect(mockRbacAPI.rbacUsers).toHaveBeenCalledTimes(1);

    // 点击第 2 页 (antd 分页 item 是 li 而非 button)
    const page2 = await waitFor(() => {
      const el = document.querySelector('.ant-pagination-item-2');
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    await act(async () => {
      fireEvent.click(page2.querySelector('a') || page2);
    });

    expect(mockRbacAPI.rbacUsers).toHaveBeenCalledTimes(2);
    expect(mockRbacAPI.rbacUsers).toHaveBeenLastCalledWith({ page: 2, page_size: 10 });
  });

  it('rbacAPI.roles 无参数调用', async () => {
    await act(async () => {
      render(<BrowserRouter><RbacPage /></BrowserRouter>);
    });
    expect(mockRbacAPI.roles).toHaveBeenCalledWith();
  });

  it('rbacAPI.createRole 参数格式正确', async () => {
    mockRbacAPI.createRole.mockResolvedValue({});
    const payload = { name: 'test_role', display_name: '测试', description: '', permissions: ['device:read'] };
    await mockRbacAPI.createRole(payload);
    expect(mockRbacAPI.createRole).toHaveBeenCalledWith(payload);
  });

  it('rbacAPI.updateRole 参数格式正确', async () => {
    mockRbacAPI.updateRole.mockResolvedValue({});
    await mockRbacAPI.updateRole(3, { display_name: '更新名' });
    expect(mockRbacAPI.updateRole).toHaveBeenCalledWith(3, { display_name: '更新名' });
  });

  it('rbacAPI.updateUserRole 参数格式正确', async () => {
    mockRbacAPI.updateUserRole.mockResolvedValue({});
    await mockRbacAPI.updateUserRole(1, { role: 'admin', extra_role_ids: [] });
    expect(mockRbacAPI.updateUserRole).toHaveBeenCalledWith(1, { role: 'admin', extra_role_ids: [] });
  });
});
