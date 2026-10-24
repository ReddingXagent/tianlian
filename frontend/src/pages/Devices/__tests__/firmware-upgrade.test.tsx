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
    await waitFor(() => expect(screen.getByText('请输入目标固件版本')).toBeInTheDocument());
    expect(mockDeviceAPI.firmware.upgrade).not.toHaveBeenCalled();
  });

  it('填写目标版本后提交调用 firmware.upgrade', async () => {
    render(<FirmwareUpgradeModal open device={device} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText('如 v2.3.1'), { target: { value: 'v2.3.1' } });
    fireEvent.click(screen.getByText('下发升级任务'));
    await waitFor(() =>
      expect(mockDeviceAPI.firmware.upgrade).toHaveBeenCalledWith(12, expect.objectContaining({ target_version: 'v2.3.1' })),
    );
  });

  it('未选设备时不提交', async () => {
    render(<FirmwareUpgradeModal open device={null} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText('如 v2.3.1'), { target: { value: 'v2.3.1' } });
    fireEvent.click(screen.getByText('下发升级任务'));
    await waitFor(() => expect(mockDeviceAPI.firmware.upgrade).not.toHaveBeenCalled());
  });
});
