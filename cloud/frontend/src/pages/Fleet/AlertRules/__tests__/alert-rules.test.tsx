/**
 * 告警规则引擎页面 — Vitest 单元测试
 *
 * 覆盖：渲染、统计卡片、规则列表、Tab切换(规则/记录)、新增规则Modal
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

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockEnterprises = [{ id: 1, name: '顺达物流' }];

const mockRules = [
  {
    id: 1, enterprise_id: 1, rule_type: 'low_battery',
    threshold: { soc_below: 20 }, notify_channels: ['im', 'sms'],
    enable: true, created_at: '2026-07-01T10:00:00Z',
  },
  {
    id: 2, enterprise_id: 1, rule_type: 'overtime_parking',
    threshold: { hours: 4 }, notify_channels: ['email'],
    enable: false, created_at: '2026-07-02T10:00:00Z',
  },
];

const mockRecords = [
  {
    id: 1, rule_id: 1, enterprise_id: 1, vehicle_id: 101, plate_number: '京A·12345',
    triggered_at: '2026-07-15T08:30:00Z', alert_value: 'SOC=15%', notified: true, status: 'active',
  },
  {
    id: 2, rule_id: 1, enterprise_id: 1, vehicle_id: 102, plate_number: '京A·67890',
    triggered_at: '2026-07-16T09:00:00Z', alert_value: 'SOC=18%', notified: false, status: 'resolved',
  },
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
    if (url.includes('/fleet/enterprises')) return Promise.resolve({ data: mockEnterprises });
    if (url.includes('/fleet/alert-records')) return Promise.resolve({ data: mockRecords });
    if (url.includes('/fleet/alert-rules')) return Promise.resolve({ data: mockRules });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetAlertRulesPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 列表
// ═══════════════════════════════════════════
describe('告警规则 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetAlertRulesPage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示四张统计卡片', async () => {
    renderWithRouter(<FleetAlertRulesPage />);
    await waitFor(() => {
      expect(screen.getByText('规则总数')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText('启用中')).toBeInTheDocument();
    expect(screen.getByText('低电量规则')).toBeInTheDocument();
    expect(screen.getByText('未处理告警')).toBeInTheDocument();
  }, 15000);

  it('渲染规则列表数据(规则类型标签 + 通知渠道)', async () => {
    renderWithRouter(<FleetAlertRulesPage />);
    await waitFor(() => {
      expect(screen.getByText('低电量')).toBeInTheDocument();
      expect(screen.getByText('超时未离桩')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText('im')).toBeInTheDocument();
    expect(screen.getByText('sms')).toBeInTheDocument();
  }, 15000);
});

// ═══════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════
describe('告警规则 — Tab切换', () => {
  it('切换到告警记录Tab显示记录列表', async () => {
    renderWithRouter(<FleetAlertRulesPage />);
    await waitFor(() => expect(screen.getByText('规则总数')).toBeInTheDocument(), { timeout: 8000 });

    clickTab('告警记录');

    await waitFor(() => {
      expect(screen.getByText('京A·12345')).toBeInTheDocument();
      expect(screen.getByText('京A·67890')).toBeInTheDocument();
    });
  }, 15000);
});

// ═══════════════════════════════════════════
// 新增规则 Modal
// ═══════════════════════════════════════════
describe('告警规则 — 新增Modal', () => {
  it('点击新增规则打开Modal', async () => {
    renderWithRouter(<FleetAlertRulesPage />);
    await waitFor(() => expect(screen.getByText('低电量')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('新增规则'));

    await waitFor(() => {
      expect(screen.getByText('新增告警规则')).toBeInTheDocument();
    });
  }, 15000);
});
