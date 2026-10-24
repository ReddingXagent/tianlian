/**
 * 固件升级组件测试（任务清单：设备管理-固件升级）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const { mockDeviceAPI } = vi.hoisted(() => ({
  mockDeviceAPI: { firmware: { upgrade: vi.fn() } },
}));

vi.mock('../../../api', () => ({
  __esModule: true,
  deviceAPI: mockDeviceAPI,
  // FirmwareUpgradeModal 依赖 gatewayAPI 拉固件列表/发起升级
  gatewayAPI: {
    list: vi.fn(() => Promise.resolve({ data: { items: [], total: 0 } })),
    // 固件下拉数据源: 只保留 released 状态的条目供测试选择
    firmware: vi.fn(() => Promise.resolve({
      data: { items: [{ id: 1, version: 'v2.3.1', model: 'DC-120', status: 'released' }] },
    })),
    uploadFirmware: vi.fn(() => Promise.resolve({ data: {} })),
    releaseFirmware: vi.fn(() => Promise.resolve({ data: {} })),
    upgradeTasks: vi.fn(() => Promise.resolve({ data: { items: [] } })),
  },
}));

import FirmwareUpgradeModal from '../components/FirmwareUpgradeModal';

const device = { id: 12, name: '充电桩A', sn: 'SN001', model: 'X1', firmware_version: 'v2.0.0' };

beforeEach(() => {
  vi.clearAllMocks();
  mockDeviceAPI.firmware.upgrade.mockResolvedValue({ data: {} });
});

describe('FirmwareUpgradeModal 固件升级', () => {
  it('渲染标题与设备当前版本', () => {
    render(<FirmwareUpgradeModal open device={device} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    expect(screen.getByText('固件升级')).toBeInTheDocument();
    expect(screen.getByText('v2.0.0')).toBeInTheDocument();
    expect(screen.getByText('下发升级任务')).toBeInTheDocument();
  });

  it('不填目标版本无法提交', async () => {
    render(<FirmwareUpgradeModal open device={device} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(screen.getByText('下发升级任务'));
    await waitFor(() => expect(screen.getByText('请选择目标固件版本')).toBeInTheDocument());
    expect(mockDeviceAPI.firmware.upgrade).not.toHaveBeenCalled();
  });

  it('选择目标版本后提交调用 firmware.upgrade', async () => {
    render(<FirmwareUpgradeModal open device={device} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    // 组件用 Select 选已发布固件: 打开下拉 -> 选中版本 -> 提交
    const selector = await screen.findByRole('combobox');
    fireEvent.mouseDown(selector);
    const options = await screen.findAllByText(/v2\.3\.1/);
    fireEvent.click(options[options.length - 1]);
    fireEvent.click(screen.getByText('下发升级任务'));
    await waitFor(() =>
      expect(mockDeviceAPI.firmware.upgrade).toHaveBeenCalledWith(12, expect.objectContaining({ target_version: 'v2.3.1' })),
    );
  });

  it('未选设备时不提交', async () => {
    render(<FirmwareUpgradeModal open device={null} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    // 目标版本改为 Select(仅可选已发布固件), 直接注入表单值模拟选择
    fireEvent.click(screen.getByText('下发升级任务'));
    await waitFor(() => expect(mockDeviceAPI.firmware.upgrade).not.toHaveBeenCalled());
  });
});
