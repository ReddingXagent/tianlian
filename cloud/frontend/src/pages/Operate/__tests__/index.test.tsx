/**
 * 运营管理页面 — Vitest 单元测试
 * 测试：渲染、Tab切换(订单管理/退款管理/对账结算)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter, MemoryRouter, Routes, Route, useNavigate } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ default: mockApi }));

vi.mock('echarts-for-react', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

// Mock 各懒加载子页面，避免其内部 API 调用影响测试
vi.mock('../Pricing', () => ({
  default: () => React.createElement('div', { 'data-testid': 'pricing-mock' }, 'Pricing Mock'),
}));
vi.mock('../Analytics', () => ({
  default: () => React.createElement('div', { 'data-testid': 'analytics-mock' }, 'Analytics Mock'),
}));
vi.mock('../Dashboard', () => ({
  default: () => React.createElement('div', { 'data-testid': 'dashboard-mock' }, 'Dashboard Mock'),
}));
vi.mock('../../UserTypeManagement', () => ({
  default: () => React.createElement('div', { 'data-testid': 'users-mock' }, 'Users Mock'),
}));
vi.mock('../../DiscountManagement', () => ({
  default: () => React.createElement('div', { 'data-testid': 'discounts-mock' }, 'Discounts Mock'),
}));
vi.mock('../../CouponManagement', () => ({
  default: () => React.createElement('div', { 'data-testid': 'coupons-mock' }, 'Coupons Mock'),
}));
vi.mock('../../PointsManagement', () => ({
  default: () => React.createElement('div', { 'data-testid': 'points-mock' }, 'Points Mock'),
}));
// 互联互通 / 市政监管 (本任务接入的新 Tab)
vi.mock('../Interconnect', () => ({
  default: () => React.createElement('div', { 'data-testid': 'interconnect-mock' }, 'Interconnect Mock'),
}));
vi.mock('../Supervision', () => ({
  default: () => React.createElement('div', { 'data-testid': 'supervision-mock' }, 'Supervision Mock'),
}));

import OperatePage from '../index';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url === '/operate/settlements') {
      return Promise.resolve({
        data: {
          items: [
            { id: 1, station_name: '郑州充电站A', period: '2026-07', total_amount: 45600.00, settlement_amount: 43200.00, status: 'paid', paid_at: '2026-07-15' },
          ],
        },
      });
    }
    if (url.includes('/operate/orders')) {
      return Promise.resolve({ data: { items: [], total: 0, page: 1, page_size: 20 } });
    }
    if (url === '/revenue/by-user-type') {
      return Promise.resolve({ data: { breakdown: [], summary: { total_orders: 0, total_kwh: 0, total_amount: 0 } } });
    }
    if (url.match(/\/orders\/\d+\/fee-items/)) {
      return Promise.resolve({ data: [] });
    }
    if (url.match(/\/orders\/\d+\/refunds/)) {
      return Promise.resolve({ data: [] });
    }
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({});
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

// ═══════════════════════════════════════════
// 辅助
// ═══════════════════════════════════════════
function clickTab(label: string) {
  const tabs = document.querySelectorAll('.ant-tabs-tab');
  for (let i = 0; i < tabs.length; i++) {
    if (tabs[i].textContent?.includes(label)) {
      fireEvent.click(tabs[i]);
      return;
    }
  }
}

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

describe('运营管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><OperatePage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('默认显示运营首页(Dashboard) Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><OperatePage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('运营首页')).toBeInTheDocument();
    });
    // 各 Tab 标签存在
    expect(screen.getByText('订单管理')).toBeInTheDocument();
    expect(screen.getByText('退款管理')).toBeInTheDocument();
    expect(screen.getByText('结算对账')).toBeInTheDocument();
    expect(screen.getByText('用户管理')).toBeInTheDocument();
    expect(screen.getByText('折扣管理')).toBeInTheDocument();
    expect(screen.getByText('优惠券')).toBeInTheDocument();
    expect(screen.getByText('积分')).toBeInTheDocument();
    expect(screen.getByText('互联互通')).toBeInTheDocument();
    expect(screen.getByText('市政监管')).toBeInTheDocument();
  });
});

describe('运营管理 — Tab切换', () => {
  it('切换到结算对账Tab渲染结算子页面', async () => {
    await act(async () => {
      render(<BrowserRouter><OperatePage /></BrowserRouter>);
    });

    // 等待默认 Tab 渲染
    await waitFor(() => {
      expect(screen.getByText('运营首页')).toBeInTheDocument();
    });

    // 找到外层 Tabs 的结算对账
    const allTabs = document.querySelectorAll('.ant-tabs-tab');
    const settleTab = Array.from(allTabs).find(t => t.textContent?.includes('结算对账'));
    expect(settleTab).toBeTruthy();
    if (settleTab) fireEvent.click(settleTab);

    // 结算对账子页面渲染其内嵌 Tab (日结汇总/支付对账/...)
    await waitFor(() => {
      expect(screen.getByText('日结汇总')).toBeInTheDocument();
    });
    expect(screen.getByText('企业结算')).toBeInTheDocument();
  });

  it('切换到退款管理Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><OperatePage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('订单管理')).toBeInTheDocument();
    });

    const allTabs = document.querySelectorAll('.ant-tabs-tab');
    const refundTab = Array.from(allTabs).find(t => t.textContent?.includes('退款管理'));
    if (refundTab) fireEvent.click(refundTab);

    // 退款管理子页面渲染
    await waitFor(() => {
      const historyTabs = screen.getAllByText('历史记录');
      expect(historyTabs.length).toBeGreaterThan(0);
    });
  });

  it('从结算对账切回订单管理', async () => {
    await act(async () => {
      render(<BrowserRouter><OperatePage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('运营首页')).toBeInTheDocument();
    });

    // 先切到结算对账
    const allTabs = document.querySelectorAll('.ant-tabs-tab');
    const settleTab = Array.from(allTabs).find(t => t.textContent?.includes('结算对账'));
    if (settleTab) fireEvent.click(settleTab);
    await waitFor(() => {
      expect(screen.getByText('日结汇总')).toBeInTheDocument();
    });

    // 切回订单管理
    const allTabs2 = document.querySelectorAll('.ant-tabs-tab');
    const orderTab = Array.from(allTabs2).find(t => t.textContent?.includes('订单管理'));
    if (orderTab) fireEvent.click(orderTab);
    await waitFor(() => {
      const allOrderTabs = screen.getAllByText('全部订单');
      expect(allOrderTabs.length).toBeGreaterThan(0);
    });
  });

  it('切换到用户管理Tab渲染用户管理页面', async () => {
    await act(async () => {
      render(<BrowserRouter><OperatePage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('运营首页')).toBeInTheDocument();
    });

    const allTabs = document.querySelectorAll('.ant-tabs-tab');
    const usersTab = Array.from(allTabs).find(t => t.textContent?.includes('用户管理'));
    expect(usersTab).toBeTruthy();
    if (usersTab) fireEvent.click(usersTab);

    await waitFor(() => {
      expect(screen.getByTestId('users-mock')).toBeInTheDocument();
    });
  });

  it('切换到折扣管理Tab渲染折扣管理页面', async () => {
    await act(async () => {
      render(<BrowserRouter><OperatePage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('运营首页')).toBeInTheDocument();
    });

    const allTabs = document.querySelectorAll('.ant-tabs-tab');
    const discTab = Array.from(allTabs).find(t => t.textContent?.includes('折扣管理'));
    if (discTab) fireEvent.click(discTab);

    await waitFor(() => {
      expect(screen.getByTestId('discounts-mock')).toBeInTheDocument();
    });
  });
});

describe('运营管理 — 互联互通/市政监管 Tab', () => {
  it('切换到互联互通Tab渲染互联互通页面', async () => {
    await act(async () => {
      render(<BrowserRouter><OperatePage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('运营首页')).toBeInTheDocument();
    });

    const allTabs = document.querySelectorAll('.ant-tabs-tab');
    const tab = Array.from(allTabs).find(t => t.textContent?.includes('互联互通'));
    expect(tab).toBeTruthy();
    if (tab) fireEvent.click(tab);

    await waitFor(() => {
      expect(screen.getByTestId('interconnect-mock')).toBeInTheDocument();
    });
  });

  it('切换到市政监管Tab渲染市政监管页面', async () => {
    await act(async () => {
      render(<BrowserRouter><OperatePage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('运营首页')).toBeInTheDocument();
    });

    const allTabs = document.querySelectorAll('.ant-tabs-tab');
    const tab = Array.from(allTabs).find(t => t.textContent?.includes('市政监管'));
    expect(tab).toBeTruthy();
    if (tab) fireEvent.click(tab);

    await waitFor(() => {
      expect(screen.getByTestId('supervision-mock')).toBeInTheDocument();
    });
  });
});

describe('运营管理 — 无 Mock 数据残留', () => {
  it('Operate/index.tsx 中无 mockOrders 引用', async () => {
    // 确认渲染不产生 mock 数据
    await act(async () => {
      render(<BrowserRouter><OperatePage /></BrowserRouter>);
    });
    // mockOrders 中有 TL-ORD-20260001 — 不应出现
    expect(screen.queryByText('TL-ORD-20260001')).not.toBeInTheDocument();
  });

  it('Operate/index.tsx 中无 mockSettlements 引用', async () => {
    await act(async () => {
      render(<BrowserRouter><OperatePage /></BrowserRouter>);
    });
    // mockSettlements 中有 2026-05 — 不应出现
    clickTab('对账结算');
    expect(screen.queryByText('2026-05')).not.toBeInTheDocument();
  });
});

// ═══════════════════════════════════════════
// 回归: 左侧菜单导航(URL参数变化)必须切换Tab内容
// 根因: activeTab 仅取 useState 初始值, /operate/:tab 复用同一组件实例,
//       菜单 navigate('/operate/orders') 后 URL 变但内容不切 → "点击没反应"
// ═══════════════════════════════════════════
function MenuSimulator() {
  const navigate = useNavigate();
  return (
    <div>
      <button data-testid="menu-orders" onClick={() => navigate('/operate/orders')}>m</button>
      <button data-testid="menu-settlement" onClick={() => navigate('/operate/settlement')}>m</button>
      <button data-testid="menu-home" onClick={() => navigate('/operate')}>m</button>
    </div>
  );
}

function renderWithMenu(initial: string) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <MenuSimulator />
      <Routes>
        <Route path="operate" element={<OperatePage />} />
        <Route path="operate/:tab" element={<OperatePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const activeTabLabel = () =>
  document.querySelector('.ant-tabs-tab-active')?.textContent ?? '';

describe('运营管理 — 左侧菜单导航回归 (URL→Tab同步)', () => {
  it('从运营首页点菜单进订单管理: 内容必须切换', async () => {
    await act(async () => { renderWithMenu('/operate'); });
    await waitFor(() => expect(activeTabLabel()).toContain('运营首页'));

    await act(async () => { fireEvent.click(screen.getByTestId('menu-orders')); });
    await waitFor(() => expect(activeTabLabel()).toContain('订单管理'));
  });

  it('Tab间连续点菜单(订单→结算对账): 同一route记录参数变化也要切换', async () => {
    await act(async () => { renderWithMenu('/operate/orders'); });
    await waitFor(() => expect(activeTabLabel()).toContain('订单管理'));

    await act(async () => { fireEvent.click(screen.getByTestId('menu-settlement')); });
    await waitFor(() => expect(activeTabLabel()).toContain('结算对账'));
  });

  it('点菜单回运营首页(/operate无参): 从子Tab返回也要切换', async () => {
    await act(async () => { renderWithMenu('/operate/settlement'); });
    await waitFor(() => expect(activeTabLabel()).toContain('结算对账'));

    await act(async () => { fireEvent.click(screen.getByTestId('menu-home')); });
    await waitFor(() => expect(activeTabLabel()).toContain('运营首页'));
  });
});
