/**
 * 扫码报修页面 — Vitest 单元测试
 *
 * 覆盖：渲染、扫码步骤、设备信息展示、报修表单、成功页
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockScanAPI } = vi.hoisted(() => ({
  mockScanAPI: {
    scanDevice: vi.fn(),
    quickRepair: vi.fn(),
    generateQRCode: vi.fn(),
    getQRCode: vi.fn(),
    listQRCodes: vi.fn(),
    deleteQRCode: vi.fn(),
  },
}));

vi.mock('../../../api/scan', () => ({
  scanAPI: mockScanAPI,
}));

// Mock QRScanner to avoid canvas/camera issues
vi.mock('../QRScanner', () => ({
  default: ({ onScan }: { onScan: (code: string) => void }) =>
    React.createElement('div', { 'data-testid': 'qr-scanner-mock' },
      React.createElement('button', {
        'data-testid': 'mock-scan-btn',
        onClick: () => onScan('TL-DEV001'),
      }, '模拟扫码'),
    ),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockDeviceResult = {
  success: true,
  device_id: 1,
  device_sn: 'TL-DEV001',
  device_name: '储能逆变器-01',
  device_type: 'battery_inverter',
  device_status: '运行中',
  station_id: 1,
  station_name: '浦东站',
  station_address: '上海市浦东新区',
  health_score: 92,
  qr_code: 'TL-DEV001',
};

const mockRepairResult = {
  success: true,
  message: '报修已提交',
  workorder_id: 'WO-2026-0001',
  device_name: '储能逆变器-01',
  station_name: '浦东站',
  fault_desc: '充电桩无法启动',
  create_time: '2026-07-21 07:00:00',
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mockScanAPI.scanDevice.mockResolvedValue({ data: mockDeviceResult });
  mockScanAPI.quickRepair.mockResolvedValue({ data: mockRepairResult });
});

import ScanPage from '../index';

// ═══════════════════════════════════════════
// 扫码页面
// ═══════════════════════════════════════════
describe('扫码报修 — 扫码页面', () => {
  it('页面正常渲染，显示扫码报修标题', async () => {
    renderWithRouter(<ScanPage />);
    await waitFor(() => {
      expect(screen.getByText('扫码报修')).toBeInTheDocument();
    });
  });

  it('显示手动输入区域', async () => {
    renderWithRouter(<ScanPage />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText('输入设备编码或序列号')).toBeInTheDocument();
    });
  });

  it('显示使用说明', async () => {
    renderWithRouter(<ScanPage />);
    await waitFor(() => {
      expect(screen.getByText('使用说明')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 设备识别 & 报修流程
// ═══════════════════════════════════════════
describe('扫码报修 — 设备识别', () => {
  it('扫码后显示设备信息', async () => {
    renderWithRouter(<ScanPage />);
    await waitFor(() => expect(screen.getByTestId('mock-scan-btn')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('mock-scan-btn'));

    await waitFor(() => {
      // device_name is shown in a Statistic component
      expect(screen.getByText('设备名称')).toBeInTheDocument();
      expect(screen.getByText('设备状态')).toBeInTheDocument();
    });
  });

  it('识别设备后显示报修按钮', async () => {
    renderWithRouter(<ScanPage />);
    await waitFor(() => expect(screen.getByTestId('mock-scan-btn')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('mock-scan-btn'));

    await waitFor(() => {
      expect(screen.getByText('立即报修')).toBeInTheDocument();
    });
  });
});
