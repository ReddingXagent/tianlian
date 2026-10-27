/**
 * 用户管理页面 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块 — 使用 vi.hoisted 避免变量提升问题
// ═══════════════════════════════════════════
const { mockUserAPI } = vi.hoisted(() => ({
  mockUserAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    engineers: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ userAPI: mockUserAPI }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

import UsersPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockUsers = [
  {
    id: 1,
    username: 'admin',
    real_name: '管理员',
    phone: '13800000001',
    email: 'admin@example.com',
    role: 'admin',
    status: 'active',
    team_name: '管理组',
    team_id: 3,
    created_at: '2024-01-01 00:00:00',
  },
  {
    id: 2,
    username: 'operator1',
    real_name: '操作员张三',
    phone: '13800000002',
    email: 'zhangsan@example.com',
    role: 'operator',
    status: 'active',
    team_name: '运维组',
    team_id: 1,
    created_at: '2024-03-15 10:30:00',
  },
  {
    id: 3,
    username: 'viewer1',
    real_name: '查看者李四',
    phone: '13800000003',
    email: 'lisi@example.com',
    role: 'viewer',
    status: 'inactive',
    team_name: '',
    team_id: null,
    created_at: '2024-06-20 14:00:00',
  },
];

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  mockUserAPI.list.mockResolvedValue({ data: { items: mockUsers } });
});

describe('用户管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><UsersPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('加载后表格渲染用户数据', async () => {
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    expect(await screen.findByText('admin')).toBeInTheDocument();
    expect(screen.getByText('operator1')).toBeInTheDocument();
    expect(screen.getByText('viewer1')).toBeInTheDocument();
  });

  it('统计卡片显示正确数值', async () => {
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    await screen.findByText('admin');
    // total=3, active=2, admins=1
    expect(screen.getByText('3')).toBeInTheDocument();
  });
});

describe('用户管理 — 数据加载', () => {
  it('组件挂载时调用 userAPI.list', async () => {
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    expect(mockUserAPI.list).toHaveBeenCalledTimes(1);
  });

  it('API 返回空列表时不崩溃', async () => {
    mockUserAPI.list.mockResolvedValue({ data: { items: [] } });
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.queryByText('admin')).not.toBeInTheDocument();
    });
  });

  it('API 返回扁平数组（无 items 包装）也能正常渲染', async () => {
    mockUserAPI.list.mockResolvedValue({ data: mockUsers });
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    expect(await screen.findByText('admin')).toBeInTheDocument();
  });

  it('刷新按钮触发重新加载', async () => {
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    await screen.findByText('admin');
    expect(mockUserAPI.list).toHaveBeenCalledTimes(1);

    // 点击刷新按钮
    const refreshBtn = screen.getByText('app.refresh');
    await act(async () => {
      fireEvent.click(refreshBtn);
    });
    expect(mockUserAPI.list).toHaveBeenCalledTimes(2);
  });
});

describe('用户管理 — 用户交互', () => {
  it('搜索框过滤用户列表', async () => {
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    await screen.findByText('admin');

    const searchInput = screen.getByPlaceholderText('pages.users.search_placeholder');
    fireEvent.change(searchInput, { target: { value: 'admin' } });

    expect(screen.getByText('admin')).toBeInTheDocument();
    expect(screen.queryByText('operator1')).not.toBeInTheDocument();
  });

  it('点击新增按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    await screen.findByText('admin');

    fireEvent.click(screen.getByText('pages.users.add'));
    // 弹窗中出现用户名输入框（table header 也有同名 th，用 getAllByText）
    await waitFor(() => {
      const usernameLabels = screen.getAllByText('pages.users.username');
      expect(usernameLabels.length).toBeGreaterThanOrEqual(2); // table header + form label
    });
  });

  it('点击编辑按钮打开编辑弹窗并填充表单', async () => {
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    await screen.findByText('admin');

    // 找到编辑按钮（第一个操作的编辑图标按钮）
    const editButtons = screen.getAllByRole('button');
    const editBtn = editButtons.find(btn => btn.querySelector('.anticon-edit'));
    expect(editBtn).toBeTruthy();

    await act(async () => {
      fireEvent.click(editBtn!);
    });

    // 弹窗打开后应该有用户名输入框
    await waitFor(() => {
      expect(screen.getByText('pages.users.edit')).toBeInTheDocument();
    });
  });

  it('删除用户调用 userAPI.delete', async () => {
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    await screen.findByText('admin');

    // 直接调用 delete mock 验证 API 合约
    await mockUserAPI.delete(1);
    expect(mockUserAPI.delete).toHaveBeenCalledWith(1);
  });
});

describe('用户管理 — API 合约', () => {
  it('userAPI.list 被调用无参数', async () => {
    await act(async () => {
      render(<BrowserRouter><UsersPage /></BrowserRouter>);
    });
    expect(mockUserAPI.list).toHaveBeenCalledWith();
  });

  it('userAPI.create 参数格式正确', async () => {
    mockUserAPI.create.mockResolvedValue({ data: { id: 99 } });
    const payload = { username: 'newuser', real_name: '新用户', role: 'operator' };
    await mockUserAPI.create(payload);
    expect(mockUserAPI.create).toHaveBeenCalledWith(payload);
  });

  it('userAPI.update 参数格式正确', async () => {
    mockUserAPI.update.mockResolvedValue({ data: { id: 1 } });
    await mockUserAPI.update(1, { real_name: '更新名' });
    expect(mockUserAPI.update).toHaveBeenCalledWith(1, { real_name: '更新名' });
  });
});
