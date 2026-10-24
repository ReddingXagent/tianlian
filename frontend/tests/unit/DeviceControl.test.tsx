/**
 * 设备控制面板 & 控制历史 前端测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const mockControlPost = vi.fn();
const mockHistoryGet = vi.fn();

vi.mock('../../src/api', () => ({
  remoteAPI: {
    control: (...args: any[]) => mockControlPost(...args),
    history: (...args: any[]) => mockHistoryGet(...args),
  },
}));

// Hoisted mock for antd message
const { mockMessageError } = vi.hoisted(() => ({
  mockMessageError: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual('antd');
  return {
    ...actual,
    message: {
      ...actual.message,
      error: mockMessageError,
      success: vi.fn().mockResolvedValue(undefined),
    },
  };
});

import DeviceControlPanel from '../../src/pages/Devices/DeviceControlPanel';

const defaultProps = {
  deviceId: 2,
  deviceName: '充电桩#1',
  deviceType: 'charger_dc',
  deviceStatus: 'online',
};

const nonChargerProps = {
  deviceId: 1,
  deviceName: '逆变器#1',
  deviceType: 'pv_inverter',
  deviceStatus: 'online',
};

describe('DeviceControlPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHistoryGet.mockResolvedValue({ data: { items: [] } });
  });

  describe('rendering', () => {
    it('renders control buttons', () => {
      render(<DeviceControlPanel {...defaultProps} />);
      expect(screen.getByText('设备控制')).toBeTruthy();
      expect(screen.getByText('启动')).toBeTruthy();
      expect(screen.getByText('停止')).toBeTruthy();
      expect(screen.getByText('重启')).toBeTruthy();
      expect(screen.getByText('急停')).toBeTruthy();
    });

    it('renders parameter settings area', () => {
      render(<DeviceControlPanel {...defaultProps} />);
      expect(screen.getByText('参数设置')).toBeTruthy();
      expect(screen.getByText('设置参数')).toBeTruthy();
    });

    it('renders control history area', () => {
      render(<DeviceControlPanel {...defaultProps} />);
      expect(screen.getByText('控制历史')).toBeTruthy();
    });

    it('shows non-charger tip for non-charger devices', () => {
      render(<DeviceControlPanel {...nonChargerProps} />);
      expect(screen.getByText('仅支持充电桩类型设备控制')).toBeTruthy();
    });

    it('displays device name and status', () => {
      render(<DeviceControlPanel {...defaultProps} />);
      expect(screen.getByText('充电桩#1')).toBeTruthy();
    });
  });

  describe('control operations', () => {
    it('sends start control request on start button click', async () => {
      mockControlPost.mockResolvedValue({});
      render(<DeviceControlPanel {...defaultProps} />);

      fireEvent.click(screen.getByText('启动'));
      await waitFor(() => {
        const confirmBtn = document.querySelector('.ant-popconfirm-buttons .ant-btn-primary');
        if (confirmBtn) fireEvent.click(confirmBtn);
      });

      await waitFor(() => {
        expect(mockControlPost).toHaveBeenCalledWith(
          2,
          expect.objectContaining({ action: 'start' }),
        );
      });
    });

    it('sends stop control request on stop button', async () => {
      mockControlPost.mockResolvedValue({});
      render(<DeviceControlPanel {...defaultProps} />);

      fireEvent.click(screen.getByText('停止'));
      await waitFor(() => {
        const confirmBtn = document.querySelector('.ant-popconfirm-buttons .ant-btn-primary');
        if (confirmBtn) fireEvent.click(confirmBtn);
      });

      await waitFor(() => {
        expect(mockControlPost).toHaveBeenCalledWith(
          2,
          expect.objectContaining({ action: 'stop' }),
        );
      });
    });

    it('sends restart control request on restart button', async () => {
      mockControlPost.mockResolvedValue({});
      render(<DeviceControlPanel {...defaultProps} />);

      fireEvent.click(screen.getByText('重启'));
      await waitFor(() => {
        const confirmBtn = document.querySelector('.ant-popconfirm-buttons .ant-btn-primary');
        if (confirmBtn) fireEvent.click(confirmBtn);
      });

      await waitFor(() => {
        expect(mockControlPost).toHaveBeenCalledWith(
          2,
          expect.objectContaining({ action: 'restart' }),
        );
      });
    });

    it('loads control history on mount', async () => {
      mockHistoryGet.mockResolvedValue({
        data: {
          items: [
            {
              id: 1,
              device_id: 2,
              device_name: '充电桩#1',
              action: 'start',
              parameter: null,
              value: null,
              result: 'success',
              message: null,
              operator: 'admin',
              created_at: '2026-06-23T12:00:00Z',
            },
          ],
        },
      });

      render(<DeviceControlPanel {...defaultProps} />);

      await waitFor(() => {
        expect(mockHistoryGet).toHaveBeenCalledWith(2);
      });
    });

    it('sends set_param with parameter and value', async () => {
      mockControlPost.mockResolvedValue({});
      render(<DeviceControlPanel {...defaultProps} />);

      const valueInput = screen.getByPlaceholderText('参数值');
      fireEvent.change(valueInput, { target: { value: '80' } });

      fireEvent.click(screen.getByText('设置参数'));

      await waitFor(() => {
        expect(mockControlPost).toHaveBeenCalledWith(
          2,
          expect.objectContaining({
            action: 'set_param',
            parameter: 'power_limit',
            value: '80',
          }),
        );
      });
    });

    it('disables set param button when value is empty', () => {
      render(<DeviceControlPanel {...defaultProps} />);
      const btn = screen.getByText('设置参数').closest('button');
      expect(btn).toBeTruthy();
      // Button should not trigger API call when disabled
      fireEvent.click(btn!);
      expect(mockControlPost).not.toHaveBeenCalledWith(
        2,
        expect.objectContaining({ action: 'set_param' }),
      );
    });
  });

  describe('error handling', () => {
    it('shows error on control API failure', async () => {
      mockControlPost.mockRejectedValue({
        response: { data: { detail: '设备控制失败' } },
      });

      render(<DeviceControlPanel {...defaultProps} />);

      fireEvent.click(screen.getByText('启动'));
      await waitFor(() => {
        const confirmBtn = document.querySelector('.ant-popconfirm-buttons .ant-btn-primary');
        if (confirmBtn) fireEvent.click(confirmBtn);
      });

      await waitFor(() => {
        expect(mockMessageError).toHaveBeenCalled();
      });
    });

    it('handles history API failure gracefully', async () => {
      mockHistoryGet.mockRejectedValue(new Error('Network error'));

      render(<DeviceControlPanel {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('控制历史')).toBeTruthy();
      });
    });
  });
});

describe('RemoteControl API definitions', () => {
  it('defines control and history methods', async () => {
    const { remoteAPI } = await import('../../src/api');
    expect(remoteAPI.control).toBeDefined();
    expect(remoteAPI.history).toBeDefined();
    expect(typeof remoteAPI.control).toBe('function');
    expect(typeof remoteAPI.history).toBe('function');
  });
});
