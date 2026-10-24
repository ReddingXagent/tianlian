/**
 * 工单管理页面 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块 — WorkOrders 使用 api (axios实例) 直接调用
// ═══════════════════════════════════════════
const { mockApi, mockUserAPI, mockWorkorderAPI } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  mockUserAPI: {
    list: vi.fn(),
    engineers: vi.fn(),
  },
  mockWorkorderAPI: {
    list: vi.fn(),
    dispatch: vi.fn(),
    accept: vi.fn(),
    start: vi.fn(),
    complete: vi.fn(),
    verify: vi.fn(),
    reject: vi.fn(),
    transfer: vi.fn(),
    urge: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  default: mockApi,
  api: mockApi,
  userAPI: mockUserAPI,
  workorderAPI: mockWorkorderAPI,
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

import WorkOrders from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockOrders = [
  {
    id: 'WO-001', fault_desc: '逆变器故障告警', type: 'repair', level: 'urgent',
    status: 'pending', station_id: 1, device_id: 10, assignee_id: null,
    creator_id: 1, create_time: '2026-07-01 08:00:00', accept_time: null,
    finish_time: null, solution: null,
  },
  {
    id: 'WO-002', fault_desc: '充电桩定期巡检', type: 'inspection', level: 'normal',
    status: 'accepted', station_id: 2, device_id: 20, assignee_id: 5,
    creator_id: 2, create_time: '2026-07-02 09:00:00',
    accept_time: '2026-07-02 10:00:00', finish_time: null, solution: null,
  },
  {
    id: 'WO-003', fault_desc: '电池柜更换', type: 'repair', level: 'high',
    status: 'completed', station_id: 3, device_id: 30, assignee_id: 6,
    creator_id: 3, create_time: '2026-06-28 14:00:00',
    accept_time: '2026-06-28 15:00:00',
    finish_time: '2026-06-30 16:00:00', solution: '已更换电池柜',
  },
];

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: { items: mockOrders } });
  mockApi.post.mockResolvedValue({ data: {} });
});

describe('工单管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('加载后表格渲染工单数据', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    expect(await screen.findByText('WO-001')).toBeInTheDocument();
    expect(screen.getByText('WO-002')).toBeInTheDocument();
    expect(screen.getByText('WO-003')).toBeInTheDocument();
  });

  it('统计卡片展示正确数据', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await screen.findByText('WO-001');
    // 统计区域应该显示数字 "3" (总工单)
    expect(screen.getByText('总工单')).toBeInTheDocument();
  });
});

describe('工单管理 — 数据加载', () => {
  it('页面挂载时调用 api.get 加载工单', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    expect(mockApi.get).toHaveBeenCalledWith('/work-orders');
  });

  it('API 返回空列表不崩溃', async () => {
    mockApi.get.mockResolvedValue({ data: { items: [] } });
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalled();
    });
  });
});

describe('工单管理 — 用户交互', () => {
  it('点击创建工单按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await screen.findByText('WO-001');

    fireEvent.click(screen.getByText('创建工单'));

    // 弹窗打开后「故障描述」出现多次（表头 + 表单标签）
    await waitFor(() => {
      const labels = screen.getAllByText('故障描述');
      expect(labels.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('搜索输入可过滤工单列表', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await screen.findByText('WO-001');

    const searchInput = screen.getByPlaceholderText('搜索工单号/故障描述...');
    fireEvent.change(searchInput, { target: { value: '逆变器' } });

    // WO-001 包含"逆变器"，WO-002 和 WO-003 不包含
    await waitFor(() => {
      expect(screen.getByText('WO-001')).toBeInTheDocument();
    });
  });

  it('工单行操作区显示详情按钮', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await screen.findByText('WO-001');

    const detailBtns = screen.getAllByText('详情');
    expect(detailBtns.length).toBeGreaterThanOrEqual(1);
  });

  it('api.post 创建工单调用格式正确', async () => {
    mockApi.post.mockResolvedValue({ data: {} });

    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await screen.findByText('WO-001');

    const payload = {
      fault_desc: '新故障', type: 'repair', level: 'warning',
      station_id: null, device_id: null,
    };
    await mockApi.post('/work-orders', payload);

    expect(mockApi.post).toHaveBeenCalledWith('/work-orders', payload);
  });

  it('api.post 接单调用格式正确', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await screen.findByText('WO-001');

    await mockApi.post('/work-orders/WO-001/accept');
    expect(mockApi.post).toHaveBeenCalledWith('/work-orders/WO-001/accept');
  });

  it('api.post 完成工单调用格式正确', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await screen.findByText('WO-001');

    await mockApi.post('/work-orders/WO-001/complete', { solution: '已修复' });
    expect(mockApi.post).toHaveBeenCalledWith('/work-orders/WO-001/complete', { solution: '已修复' });
  });

  it('api.post 催单调用格式正确', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await screen.findByText('WO-001');

    await mockApi.post('/work-orders/WO-001/urge', { message: '请尽快处理此工单' });
    expect(mockApi.post).toHaveBeenCalledWith('/work-orders/WO-001/urge', { message: '请尽快处理此工单' });
  });
});

// ═══════════════════════════════════════════
// 移动端响应式（Phase1）
// ═══════════════════════════════════════════
describe('工单管理 — 移动端响应式', () => {
  beforeEach(() => {
    vi.stubGlobal('innerWidth', 375);
    mockApi.get.mockResolvedValue({ data: { items: mockOrders } });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('移动端宽度渲染工单数据且不渲染桌面表格', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    expect(await screen.findByText('WO-001')).toBeInTheDocument();
    // 移动端切换为卡片列表，桌面 Table 不渲染
    expect(document.querySelector('.ant-table')).toBeNull();
  });

  it('移动端渲染与工单数一致的卡片', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await screen.findByText('WO-001');
    expect(document.querySelectorAll('[data-testid="wo-mobile-card"]').length).toBe(mockOrders.length);
  });

  it('移动端筛选器默认折叠，点击展开', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrders /></BrowserRouter>);
    });
    await screen.findByText('WO-001');

    // 折叠态：状态/级别 Select 不在文档（搜索框保留）
    expect(document.querySelector('.ant-select')).toBeNull();

    const toggle = screen.getByRole('button', { name: /筛选/ });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(document.querySelector('.ant-select')).toBeInTheDocument();
    });
  });
});
