/**
 * 协议管理页面 — Vitest 单元测试
 *
 * 覆盖：渲染、Tab切换(网关实例/解析器配置/连接仪表板)、子组件加载
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
vi.mock('../../../api', () => ({
  default: { get: vi.fn(() => Promise.resolve({ data: { items: [] } })) },
  protocolInstanceAPI: {
    list: vi.fn(() => Promise.resolve({ data: { items: [], total: 0 } })),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
  },
  parserConfigAPI: {
    list: vi.fn(() => Promise.resolve({ data: { data: { items: [], total: 0 } } })),
    create: vi.fn(() => Promise.resolve({})),
    update: vi.fn(() => Promise.resolve({})),
    delete: vi.fn(() => Promise.resolve({})),
  },
  connectionDashboardAPI: {
    get: vi.fn(() => Promise.resolve({ data: { data: { stats: { total: 0 } } } })),
  },
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

function clickTab(label: string) {
  const tabs = document.querySelectorAll('.ant-tabs-tab');
  for (let i = 0; i < tabs.length; i++) {
    if (tabs[i].textContent?.includes(label)) {
      fireEvent.click(tabs[i]);
      return;
    }
  }
}

beforeEach(() => {
  vi.clearAllMocks();
});

import ProtocolsPage from '../index';
import ParserConfigPage from '../ParserConfig';
import ConnectionDashboard, { REFRESH_INTERVAL } from '../ConnectionDashboard';
import { parserConfigAPI, connectionDashboardAPI } from '../../../api';

// ═══════════════════════════════════════════
// 渲染
// ═══════════════════════════════════════════
describe('协议管理 — 渲染', () => {
  it('页面正常渲染，显示协议管理标题', async () => {
    renderWithRouter(<ProtocolsPage />);
    await waitFor(() => {
      expect(screen.getByText('协议管理')).toBeInTheDocument();
    });
  });

  it('显示Phase33标签', async () => {
    renderWithRouter(<ProtocolsPage />);
    await waitFor(() => {
      expect(screen.getByText('Phase33')).toBeInTheDocument();
    });
  });

  it('默认显示网关实例Tab', async () => {
    renderWithRouter(<ProtocolsPage />);
    await waitFor(() => {
      expect(screen.getByText('网关实例')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════
describe('协议管理 — Tab切换', () => {
  it('切换到解析器配置Tab', async () => {
    renderWithRouter(<ProtocolsPage />);
    await waitFor(() => expect(screen.getByText('网关实例')).toBeInTheDocument());

    clickTab('解析器配置');

    await waitFor(() => {
      expect(screen.getByText('解析器配置')).toBeInTheDocument();
    });
  });

  it('切换到连接仪表板Tab', async () => {
    renderWithRouter(<ProtocolsPage />);
    await waitFor(() => expect(screen.getByText('网关实例')).toBeInTheDocument());

    clickTab('连接仪表板');

    await waitFor(() => {
      expect(screen.getByText('连接仪表板')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 解析器启用/禁用切换
// ═══════════════════════════════════════════
describe('解析器配置 — 启用/禁用切换', () => {
  it('点击状态开关：active→inactive 调用 update(id, {status:"inactive"})', async () => {
    (parserConfigAPI.list as any).mockResolvedValue({
      data: { data: { items: [
        { id: 7, name: '逆变器解析', device_type: 'inverter_eahi_20k', protocol: 'modbus_rtu', status: 'active' },
      ], total: 1 } },
    });
    renderWithRouter(<ParserConfigPage />);
    const sw = await screen.findByRole('switch', { name: /逆变器解析/ });
    expect(sw).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(sw);
    await waitFor(() => {
      expect(parserConfigAPI.update).toHaveBeenCalledWith(7, { status: 'inactive' });
    });
  });

  it('点击状态开关：inactive→active 调用 update(id, {status:"active"})', async () => {
    (parserConfigAPI.list as any).mockResolvedValue({
      data: { data: { items: [
        { id: 9, name: 'PCS解析', device_type: 'pcs_100kw', protocol: 'modbus_tcp', status: 'inactive' },
      ], total: 1 } },
    });
    renderWithRouter(<ParserConfigPage />);
    const sw = await screen.findByRole('switch', { name: /PCS解析/ });
    expect(sw).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(sw);
    await waitFor(() => {
      expect(parserConfigAPI.update).toHaveBeenCalledWith(9, { status: 'active' });
    });
  });
});

// ═══════════════════════════════════════════
// 连接仪表板 自动轮询
// ═══════════════════════════════════════════
describe('连接仪表板 — 自动轮询', () => {
  it('挂载后按 REFRESH_INTERVAL 周期自动刷新 connectionDashboardAPI.get', async () => {
    vi.useFakeTimers();
    try {
      const { unmount } = renderWithRouter(<ConnectionDashboard />);
      // flush 首次加载的 microtask（fake timers 下 waitFor 自身定时器被冻结，改用 advance flush）
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(connectionDashboardAPI.get).toHaveBeenCalledTimes(1);
      // 推进一个轮询周期，应触发第二次拉取
      await act(async () => { await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL); });
      expect(connectionDashboardAPI.get).toHaveBeenCalledTimes(2);
      // 再推进一个周期，应触发第三次
      await act(async () => { await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL); });
      expect(connectionDashboardAPI.get).toHaveBeenCalledTimes(3);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it('关闭自动刷新后不再轮询', async () => {
    vi.useFakeTimers();
    try {
      const { unmount } = renderWithRouter(<ConnectionDashboard />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(connectionDashboardAPI.get).toHaveBeenCalledTimes(1);
      // 关闭自动刷新开关
      const toggle = screen.getByRole('switch', { name: /自动刷新/ });
      fireEvent.click(toggle);
      await act(async () => { await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL * 3); });
      // 关闭后调用次数不应继续增长
      expect(connectionDashboardAPI.get).toHaveBeenCalledTimes(1);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });
});
