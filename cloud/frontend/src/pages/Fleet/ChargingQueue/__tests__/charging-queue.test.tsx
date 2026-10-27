/**
 * 充电排序队列页面 — Vitest 单元测试
 *
 * 覆盖：渲染、Tab切换(实时队列/排序规则)、统计卡片、入队Modal、规则Modal
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
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
    patch: vi.fn(),
  },
}));

vi.mock('../../../../api', () => ({ default: mockApi }));

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

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockQueue = [
  { id: 1, vehicle_id: 101, priority: 50, status: 'waiting', required_energy_kwh: 40.5, current_soc: 0.3, target_soc: 0.8, estimated_wait_minutes: 15 },
  { id: 2, vehicle_id: 102, priority: 80, status: 'waiting', required_energy_kwh: 25.0, current_soc: 0.5, target_soc: 0.8, estimated_wait_minutes: 5 },
  { id: 3, vehicle_id: 103, priority: 30, status: 'charging', required_energy_kwh: 50.0, current_soc: 0.6, target_soc: 0.9, estimated_wait_minutes: 0 },
];

const mockRules = [
  { id: 1, rule_name: '默认优先级规则', enterprise_id: 1, station_id: null, max_queue_length: 100, enable: true },
  { id: 2, rule_name: '夜间低谷规则', enterprise_id: 2, station_id: 5, max_queue_length: 50, enable: false },
];

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
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/fleet/charging/queue')) return Promise.resolve({ data: mockQueue });
    if (url.includes('/fleet/charging/rules')) return Promise.resolve({ data: mockRules });
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });

  // useFleetRealtime 在挂载时会 new WebSocket，stub 掉避免 jsdom 真实连接
  vi.stubGlobal('WebSocket', class MockWS {
    static OPEN = 1;
    static CONNECTING = 0;
    readyState = 0;
    onopen: ((e?: Event) => void) | null = null;
    onmessage: ((e: { data: string }) => void) | null = null;
    onerror: ((e: Event) => void) | null = null;
    onclose: ((e: CloseEvent) => void) | null = null;
    send() {}
    close() {}
    constructor(_url: string) {}
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

import FleetChargingQueuePage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 队列
// ═══════════════════════════════════════════
describe('充电队列 — 渲染', () => {
  it('页面正常渲染', async () => {
    renderWithRouter(<FleetChargingQueuePage />);
    await waitFor(() => {
      expect(screen.getByText('队列总数')).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 15000);

  it('显示统计卡片', async () => {
    renderWithRouter(<FleetChargingQueuePage />);
    await waitFor(() => {
      expect(screen.getByText('队列总数')).toBeInTheDocument();
      expect(screen.getByText('等待中')).toBeInTheDocument();
      expect(screen.getByText('充电中')).toBeInTheDocument();
      expect(screen.getByText('平均等待(min)')).toBeInTheDocument();
    });
  });

  it('显示队列中的车辆', async () => {
    renderWithRouter(<FleetChargingQueuePage />);
    await waitFor(() => {
      expect(screen.getByText('101')).toBeInTheDocument();
      expect(screen.getByText('102')).toBeInTheDocument();
      expect(screen.getByText('103')).toBeInTheDocument();
    });
  });

  it('显示优先级标签', async () => {
    renderWithRouter(<FleetChargingQueuePage />);
    await waitFor(() => {
      expect(screen.getByText('50')).toBeInTheDocument();
      expect(screen.getByText('80')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════
describe('充电队列 — Tab切换', () => {
  it('切换到排序规则Tab', async () => {
    renderWithRouter(<FleetChargingQueuePage />);
    await waitFor(() => expect(screen.getByText('队列总数')).toBeInTheDocument());

    clickTab('排序规则');

    await waitFor(() => {
      expect(screen.getByText('默认优先级规则')).toBeInTheDocument();
      expect(screen.getByText('夜间低谷规则')).toBeInTheDocument();
    });
  });

  it('规则Tab显示新增按钮', async () => {
    renderWithRouter(<FleetChargingQueuePage />);
    await waitFor(() => expect(screen.getByText('队列总数')).toBeInTheDocument());

    clickTab('排序规则');

    await waitFor(() => {
      expect(screen.getByText('新增规则')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 入队 Modal
// ═══════════════════════════════════════════
describe('充电队列 — 入队Modal', () => {
  it('点击车辆入队打开Modal', async () => {
    renderWithRouter(<FleetChargingQueuePage />);
    await waitFor(() => expect(screen.getByText('队列总数')).toBeInTheDocument(), { timeout: 5000 });

    fireEvent.click(screen.getByText('车辆入队'));

    await waitFor(() => {
      // '需电量(kWh)' appears in both table header and modal form
      expect(screen.getAllByText('需电量(kWh)').length).toBeGreaterThanOrEqual(2);
    }, { timeout: 5000 });
  }, 15000);
});

// ═══════════════════════════════════════════
// 规则 Modal
// ═══════════════════════════════════════════
describe('充电队列 — 规则Modal', () => {
  it('点击新增规则打开Modal', async () => {
    renderWithRouter(<FleetChargingQueuePage />);
    await waitFor(() => expect(screen.getByText('队列总数')).toBeInTheDocument());

    clickTab('排序规则');
    await waitFor(() => expect(screen.getByText('新增规则')).toBeInTheDocument());

    fireEvent.click(screen.getByText('新增规则'));

    await waitFor(() => {
      expect(screen.getByText('新增排序规则')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 状态标签
// ═══════════════════════════════════════════
describe('充电队列 — 状态', () => {
  it('显示等待中和充电中状态', async () => {
    renderWithRouter(<FleetChargingQueuePage />);
    await waitFor(() => {
      expect(screen.getAllByText('等待中').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('充电中').length).toBeGreaterThanOrEqual(1);
    });
  });
});
