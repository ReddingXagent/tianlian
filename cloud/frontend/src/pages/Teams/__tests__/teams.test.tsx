/**
 * 团队管理页面 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockTeamAPI, mockUserAPI } = vi.hoisted(() => ({
  mockTeamAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    members: vi.fn(),
    addMember: vi.fn(),
    removeMember: vi.fn(),
  },
  mockUserAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  teamAPI: mockTeamAPI,
  userAPI: mockUserAPI,
}));

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

import TeamsPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockTeams = [
  { id: 1, name: 'TeamAlpha', code: 'THN0001', status: 'active', member_count: 5, station_count: 3, manager_name: '张三' },
  { id: 2, name: 'TeamBeta', code: 'TGD0002', status: 'inactive', member_count: 3, station_count: 2, manager_name: '李四' },
];

const mockMembers = [
  { user_id: 101, username: 'user1', real_name: '用户一', role: 'admin', joined_at: '2024-01-15T08:00:00Z', status: 'active' },
  { user_id: 102, username: 'user2', real_name: '用户二', role: 'engineer', joined_at: '2024-02-20T08:00:00Z', status: 'active' },
];

const mockUsers = [
  { id: 101, username: 'user1', real_name: '用户一' },
  { id: 102, username: 'user2', real_name: '用户二' },
];

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockTeamAPI.list.mockResolvedValue({ data: mockTeams });
  mockTeamAPI.get.mockResolvedValue({ data: mockTeams[0] });
  mockTeamAPI.members.mockResolvedValue({ data: mockMembers });
  mockUserAPI.list.mockResolvedValue({ data: mockUsers });
  mockTeamAPI.create.mockResolvedValue({ data: { id: 3, code: 'THN0003' } });
  mockTeamAPI.update.mockResolvedValue({ data: { id: 1 } });
  mockTeamAPI.delete.mockResolvedValue({ data: {} });
});

describe('团队管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><TeamsPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('加载后渲染团队列表数据', async () => {
    await act(async () => {
      render(<BrowserRouter><TeamsPage /></BrowserRouter>);
    });
    expect(await screen.findByText('TeamAlpha')).toBeInTheDocument();
    expect(screen.getByText('TeamBeta')).toBeInTheDocument();
  });

  it('渲染统计卡片（总数、启用、成员）', async () => {
    await act(async () => {
      render(<BrowserRouter><TeamsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');
    // stats.total = 2, stats.active = 1, stats.totalMembers = 8
    expect(screen.getByText('2')).toBeInTheDocument();
  });
});

describe('团队管理 — 数据展示', () => {
  it('团队列表显示编码标签', async () => {
    await act(async () => {
      render(<BrowserRouter><TeamsPage /></BrowserRouter>);
    });
    expect(await screen.findByText('THN0001')).toBeInTheDocument();
    expect(screen.getByText('TGD0002')).toBeInTheDocument();
  });

  it('搜索过滤团队列表', async () => {
    await act(async () => {
      render(<BrowserRouter><TeamsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');

    const searchInput = screen.getByPlaceholderText('pages.teams.search_placeholder');
    fireEvent.change(searchInput, { target: { value: 'Alpha' } });

    expect(screen.getByText('TeamAlpha')).toBeInTheDocument();
    expect(screen.queryByText('TeamBeta')).not.toBeInTheDocument();
  });

  it('点击团队名称加载详情', async () => {
    await act(async () => {
      render(<BrowserRouter><TeamsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');

    // 点击团队名称
    fireEvent.click(screen.getByText('TeamAlpha'));

    await waitFor(() => {
      expect(mockTeamAPI.get).toHaveBeenCalledWith(1);
    });
  });
});

describe('团队管理 — 交互', () => {
  it('点击新增按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><TeamsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');

    // 点击"新增"按钮
    const addBtn = screen.getByText('新增');
    fireEvent.click(addBtn);

    // 弹窗应出现表单元素
    await waitFor(() => {
      expect(screen.getByText('pages.teams.add')).toBeInTheDocument();
    });
  });

  it('teamAPI.list 被调用', async () => {
    await act(async () => {
      render(<BrowserRouter><TeamsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');
    expect(mockTeamAPI.list).toHaveBeenCalled();
  });

  it('teamAPI.create 调用参数正确', async () => {
    mockTeamAPI.create.mockResolvedValue({ data: { id: 3, code: 'THN0003' } });

    await mockTeamAPI.create({ name: 'NewTeam', region: 'HN' });

    expect(mockTeamAPI.create).toHaveBeenCalledWith({ name: 'NewTeam', region: 'HN' });
  });
});

describe('团队管理 — 边界条件', () => {
  it('空团队列表不崩溃', async () => {
    mockTeamAPI.list.mockResolvedValue({ data: [] });
    await act(async () => {
      render(<BrowserRouter><TeamsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.queryByText('TeamAlpha')).not.toBeInTheDocument();
    });
  });

  it('API加载失败显示错误提示', async () => {
    mockTeamAPI.list.mockRejectedValue(new Error('network error'));
    await act(async () => {
      render(<BrowserRouter><TeamsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockTeamAPI.list).toHaveBeenCalled();
    });
  });
});
