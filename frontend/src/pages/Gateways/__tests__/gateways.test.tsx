/**
 * 网关管理页面 — Vitest 单元测试
 *
 * 覆盖：渲染、Tab切换(网关/SN码/固件/升级任务)、表格、弹窗
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockGatewayAPI, mockTeamAPI } = vi.hoisted(() => ({
  mockGatewayAPI: {
    list: vi.fn(),
    sn: vi.fn(),
    firmware: vi.fn(),
    upgradeTasks: vi.fn(),
    generateSn: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
  mockTeamAPI: {
    list: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  default: {},
  gatewayAPI: mockGatewayAPI,
  teamAPI: mockTeamAPI,
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

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockGateways = [
  { id: 1, sn: 'TL-GW-001', name: '网关-浦东', model: 'TL-GW-100', status: 'online', firmware_version: 'v2.1', health_score: 92, ip_address: '192.168.1.10', last_online: '2026-07-20T10:00:00Z' },
  { id: 2, sn: 'TL-GW-002', name: '网关-浦西', model: 'TL-GW-200', status: 'offline', firmware_version: 'v2.0', health_score: 75, ip_address: '192.168.1.11', last_online: '2026-07-19T10:00:00Z' },
];

const mockSnCodes = [
  { id: 1, sn: 'TL-HN-0001', model: 'TL-GW-100', status: 'generated', batch_no: 'B001', region: 'HN' },
  { id: 2, sn: 'TL-SH-0002', model: 'TL-GW-200', status: 'activated', batch_no: 'B002', region: 'SH', gateway_id: 1 },
];

const mockFirmware = [
  { id: 1, version: 'v2.1', model: 'TL-GW-100', status: 'released', file_size: 5242880, release_date: '2026-07-01T00:00:00Z' },
];

const mockTasks = [
  { id: 1, gateway_id: 1, firmware_id: 1, status: 'success', progress: 100, created_at: '2026-07-15T10:00:00Z' },
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
  mockGatewayAPI.list.mockResolvedValue({ data: mockGateways });
  mockGatewayAPI.sn.mockResolvedValue({ data: mockSnCodes });
  mockGatewayAPI.firmware.mockResolvedValue({ data: mockFirmware });
  mockGatewayAPI.upgradeTasks.mockResolvedValue({ data: mockTasks });
  mockGatewayAPI.generateSn.mockResolvedValue({ data: { message: 'SN码生成成功' } });
  mockTeamAPI.list.mockResolvedValue({ data: { items: [] } });
});

import GatewayPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 网关Tab
// ═══════════════════════════════════════════
describe('网关管理 — 渲染 & 网关Tab', () => {
  it('页面正常渲染，显示标题', async () => {
    renderWithRouter(<GatewayPage />);
    await waitFor(() => {
      expect(screen.getByText('pages.gateways.title')).toBeInTheDocument();
    });
  });

  it('显示网关列表数据', async () => {
    renderWithRouter(<GatewayPage />);
    await waitFor(() => {
      expect(screen.getByText('网关-浦东')).toBeInTheDocument();
      expect(screen.getByText('网关-浦西')).toBeInTheDocument();
    });
  });

  it('显示添加网关按钮', async () => {
    renderWithRouter(<GatewayPage />);
    await waitFor(() => {
      expect(screen.getByText('pages.gateways.add')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════
describe('网关管理 — Tab切换', () => {
  it('切换到SN码管理Tab', async () => {
    renderWithRouter(<GatewayPage />);
    await waitFor(() => expect(screen.getByText('网关-浦东')).toBeInTheDocument());

    clickTab('pages.gateways.sn_mgmt');

    await waitFor(() => {
      expect(screen.getByText('生成SN码')).toBeInTheDocument();
    });
  });

  it('切换到固件管理Tab', async () => {
    renderWithRouter(<GatewayPage />);
    await waitFor(() => expect(screen.getByText('网关-浦东')).toBeInTheDocument());

    clickTab('pages.gateways.firmware_mgmt');

    await waitFor(() => {
      expect(screen.getByText('上传固件')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 弹窗
// ═══════════════════════════════════════════
describe('网关管理 — 弹窗', () => {
  it('点击添加按钮打开新增网关弹窗', async () => {
    renderWithRouter(<GatewayPage />);
    await waitFor(() => expect(screen.getByText('pages.gateways.add')).toBeInTheDocument());

    fireEvent.click(screen.getByText('pages.gateways.add'));

    await waitFor(() => {
      // Modal should appear with form label
      expect(document.querySelector('.ant-modal')).toBeInTheDocument();
    });
  });
});
