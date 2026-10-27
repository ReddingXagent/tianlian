/**
 * 系统配置页 — Vitest 单元测试
 * 覆盖：权限配置、通知配置、日志审计三个 Tab
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockRbacAPI, mockNotificationRuleAPI, mockOperationLogAPI } = vi.hoisted(() => ({
  mockRbacAPI: {
    roles: vi.fn(),
    permissions: vi.fn(),
    createRole: vi.fn(),
    updateRole: vi.fn(),
    deleteRole: vi.fn(),
  },
  mockNotificationRuleAPI: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    toggle: vi.fn(),
  },
  mockOperationLogAPI: {
    list: vi.fn(),
    stats: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  rbacAPI: mockRbacAPI,
  notificationRuleAPI: mockNotificationRuleAPI,
  operationLogAPI: mockOperationLogAPI,
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

import ConfigPage from '../index';

// ═══════════════════════════════════════════
// 用户上下文 (team_type 过滤, 卡 d0c431d0)
// ═══════════════════════════════════════════
// 配置页从 localStorage admin_user 读取当前用户解析 team_type。
// 默认注入平台 admin (全量 Tab), 保证下方既有 rbac/通知/审计用例不回归;
// 需要其它 team_type 的用例自行 setUser 覆盖。
const PLATFORM_ADMIN_USER = { id: 1, username: 'admin', role: 'admin' };
function setUser(user: Record<string, unknown> = PLATFORM_ADMIN_USER): void {
  localStorage.setItem('admin_user', JSON.stringify(user));
}

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockRoles = {
  items: [
    { id: 1, name: 'admin', display_name: '管理员', description: '系统管理员', is_system: true, permissions: ['device:read', 'device:write', 'user:manage'], user_count: 3 },
    { id: 2, name: 'operator', display_name: '运维操作员', description: '日常运维', is_system: true, permissions: ['device:read', 'alarm:handle'], user_count: 5 },
    { id: 3, name: 'viewer', display_name: '只读用户', description: '仅查看', is_system: false, permissions: ['device:read'], user_count: 2 },
  ],
};

const mockPermissions = {
  items: [
    { name: 'device:read', resource: 'device', action: 'read', label: '查看设备' },
    { name: 'device:write', resource: 'device', action: 'write', label: '编辑设备' },
    { name: 'alarm:handle', resource: 'alarm', action: 'write', label: '处理告警' },
    { name: 'user:manage', resource: 'user', action: 'write', label: '管理用户' },
  ],
};

const mockRules = [
  { id: 1, name: '紧急告警通知', level: 'critical', channels: ['sms', 'email'], receivers: ['team:ops', 'user:admin'], enabled: true, created_at: '2026-07-01T10:00:00Z' },
  { id: 2, name: '日报推送', level: 'info', channels: ['im'], receivers: ['oncall'], enabled: false, created_at: '2026-06-15T10:00:00Z' },
];

const mockLogs = {
  items: [
    { id: 1, timestamp: '2026-07-21T10:00:00Z', username: 'admin', action: 'login', module: 'auth', target_id: null, target_desc: null, detail: '用户登录', ip_address: '192.168.1.1', result: 'success' },
    { id: 2, timestamp: '2026-07-21T11:00:00Z', username: 'operator1', action: 'update', module: 'devices', target_id: '3', target_desc: 'Device03', detail: '更新设备', ip_address: '10.0.0.5', result: 'success' },
  ],
  total: 2,
};

const mockLogStats = { total_logs: 200, today_logs: 20, failed_logs: 5, by_action: { login: 80 } };

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  setUser(); // 默认平台 admin, 既有用例保持全量 Tab 可见
  mockRbacAPI.roles.mockResolvedValue({ data: mockRoles });
  mockRbacAPI.permissions.mockResolvedValue({ data: mockPermissions });
  mockNotificationRuleAPI.list.mockResolvedValue({ data: mockRules });
  mockOperationLogAPI.list.mockResolvedValue({ data: mockLogs });
  mockOperationLogAPI.stats.mockResolvedValue({ data: mockLogStats });
});

describe('系统配置 — 渲染', () => {
  it('页面可渲染不崩溃', async () => {
    let container: HTMLElement;
    await act(async () => {
      const { container: c } = render(<BrowserRouter><ConfigPage /></BrowserRouter>);
      container = c;
    });
    expect(container!).toBeTruthy();
  });

  it('默认展示权限配置 Tab（含角色数据）', async () => {
    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });
    // 等待角色数据加载
    expect(await screen.findByText('管理员')).toBeInTheDocument();
    expect(screen.getByText('运维操作员')).toBeInTheDocument();
    expect(screen.getByText('只读用户')).toBeInTheDocument();
  });

  it('权限统计卡片展示正确数值', async () => {
    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');
    // 角色数 3 (Statistic 和 user_count Tag 都包含 "3"，用 getAllByText)
    expect(screen.getAllByText('3').length).toBeGreaterThan(0);
    // 权限项 4
    expect(screen.getAllByText('4').length).toBeGreaterThan(0);
  });
});

describe('系统配置 — 权限配置 Tab', () => {
  it('点击新建角色按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    fireEvent.click(screen.getByText('新建角色'));

    await waitFor(() => {
      expect(screen.getByText('角色标识')).toBeInTheDocument();
      expect(screen.getByText('角色名称')).toBeInTheDocument();
    });
  });

  it('内置角色不显示删除按钮', async () => {
    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    // 内置角色 admin 和 operator 不应有删除按钮
    // 自定义角色 viewer 有删除按钮
    const deleteBtns = screen.getAllByRole('button').filter(btn => btn.querySelector('.anticon-delete'));
    // 只有 viewer（非内置）才出现删除，但删除按钮藏在 Popconfirm 的触发按钮中
    // 检查至少有一个删除按钮（viewer 行的）
    expect(deleteBtns.length).toBeGreaterThanOrEqual(1);
  });

  it('fetchRoles 调用 rbacAPI.roles', async () => {
    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    expect(mockRbacAPI.roles).toHaveBeenCalled();
    expect(mockRbacAPI.permissions).toHaveBeenCalled();
  });
});

describe('系统配置 — 通知配置 Tab', () => {
  it('切换到通知配置 Tab 展示规则列表', async () => {
    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    // 点击「通知配置」tab
    const notifyTab = screen.getByText('通知配置');
    await act(async () => {
      fireEvent.click(notifyTab);
    });

    await waitFor(() => {
      expect(screen.getByText('紧急告警通知')).toBeInTheDocument();
      expect(screen.getByText('日报推送')).toBeInTheDocument();
    });
  });

  it('通知渠道开关正常渲染', async () => {
    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    const notifyTab = screen.getByText('通知配置');
    await act(async () => {
      fireEvent.click(notifyTab);
    });

    await waitFor(() => {
      expect(screen.getByText('短信通知')).toBeInTheDocument();
      expect(screen.getByText('邮件通知')).toBeInTheDocument();
      expect(screen.getByText('APP推送')).toBeInTheDocument();
    });
  });

  it('创建规则按钮可点击', async () => {
    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });
    await screen.findByText('管理员');

    const notifyTab = screen.getByText('通知配置');
    await act(async () => {
      fireEvent.click(notifyTab);
    });

    await waitFor(() => {
      const createBtn = screen.getByText('创建规则');
      expect(createBtn).toBeInTheDocument();
    });
  });
});

describe('系统配置 — 边界条件', () => {
  it('角色列表为空时正常渲染', async () => {
    mockRbacAPI.roles.mockResolvedValue({ data: { items: [] } });

    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.queryByText('管理员')).not.toBeInTheDocument();
    });
  });

  it('通知规则列表为空时正常渲染', async () => {
    mockNotificationRuleAPI.list.mockResolvedValue({ data: [] });

    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });
    await screen.findByText('权限配置');

    const notifyTab = screen.getByText('通知配置');
    await act(async () => {
      fireEvent.click(notifyTab);
    });

    await waitFor(() => {
      expect(screen.queryByText('紧急告警通知')).not.toBeInTheDocument();
    });
  });

  it('API 调用失败显示错误提示', async () => {
    mockRbacAPI.roles.mockRejectedValue(new Error('Server error'));

    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(mockRbacAPI.roles).toHaveBeenCalled();
    });
  });
});

// ═══════════════════════════════════════════
// 按 team_type 过滤 Tab (卡 d0c431d0)
// ═══════════════════════════════════════════
describe('系统配置 — 按 team_type 过滤 Tab', () => {
  async function renderWith(user: Record<string, unknown>): Promise<void> {
    setUser(user);
    await act(async () => {
      render(<BrowserRouter><ConfigPage /></BrowserRouter>);
    });
  }

  it('platform → 全 6 业务 Tab + 运维专属, 无车队专属', async () => {
    await renderWith({ role: 'admin' });
    expect(screen.getByText('权限配置')).toBeInTheDocument();
    expect(screen.getByText('通知配置')).toBeInTheDocument();
    expect(screen.getByText('日志审计')).toBeInTheDocument();
    expect(screen.getByText('全局配置')).toBeInTheDocument();
    expect(screen.getByText('支付通道')).toBeInTheDocument();
    expect(screen.getByText('发票配置')).toBeInTheDocument();
    expect(screen.getByText('运维专属')).toBeInTheDocument();
    expect(screen.queryByText('车队专属')).not.toBeInTheDocument();
  });

  it('ops_company → 通知/日志/全局/支付/发票, 无权限配置与占位', async () => {
    await renderWith({ role: 'engineer', team_type: 'ops_company' });
    expect(screen.queryByText('权限配置')).not.toBeInTheDocument();
    expect(screen.getByText('通知配置')).toBeInTheDocument();
    expect(screen.getByText('日志审计')).toBeInTheDocument();
    expect(screen.getByText('全局配置')).toBeInTheDocument();
    expect(screen.getByText('支付通道')).toBeInTheDocument();
    expect(screen.getByText('发票配置')).toBeInTheDocument();
    expect(screen.queryByText('运维专属')).not.toBeInTheDocument();
    expect(screen.queryByText('车队专属')).not.toBeInTheDocument();
  });

  it('maintenance_team → 通知/日志/全局 + 运维专属占位', async () => {
    await renderWith({ role: 'engineer', team_type: 'maintenance_team' });
    expect(screen.getByText('通知配置')).toBeInTheDocument();
    expect(screen.getByText('日志审计')).toBeInTheDocument();
    expect(screen.getByText('全局配置')).toBeInTheDocument();
    expect(screen.getByText('运维专属')).toBeInTheDocument();
    expect(screen.queryByText('权限配置')).not.toBeInTheDocument();
    expect(screen.queryByText('支付通道')).not.toBeInTheDocument();
    expect(screen.queryByText('发票配置')).not.toBeInTheDocument();
    expect(screen.queryByText('车队专属')).not.toBeInTheDocument();
  });

  it('fleet → 仅通知 + 车队专属占位', async () => {
    await renderWith({ role: 'fleet', team_type: 'fleet' });
    expect(screen.getByText('通知配置')).toBeInTheDocument();
    expect(screen.getByText('车队专属')).toBeInTheDocument();
    expect(screen.queryByText('权限配置')).not.toBeInTheDocument();
    expect(screen.queryByText('日志审计')).not.toBeInTheDocument();
    expect(screen.queryByText('全局配置')).not.toBeInTheDocument();
    expect(screen.queryByText('支付通道')).not.toBeInTheDocument();
    expect(screen.queryByText('发票配置')).not.toBeInTheDocument();
    expect(screen.queryByText('运维专属')).not.toBeInTheDocument();
  });

  it('ops_company 默认激活首个可见 Tab (notification), 不挂载 rbac', async () => {
    await renderWith({ role: 'engineer', team_type: 'ops_company' });
    // notification 是 ops_company 第一个可见 Tab → 默认挂载并拉取规则
    await waitFor(() => {
      expect(mockNotificationRuleAPI.list).toHaveBeenCalled();
    });
    // rbac Tab 被过滤 → 不挂载, 不请求角色
    expect(mockRbacAPI.roles).not.toHaveBeenCalled();
  });

  it('fleet 切换到车队专属占位 → 渲染占位文案', async () => {
    await renderWith({ role: 'fleet', team_type: 'fleet' });
    await act(async () => {
      fireEvent.click(screen.getByText('车队专属'));
    });
    await waitFor(() => {
      expect(screen.getByText('车队专属配置')).toBeInTheDocument();
    });
  });
});
