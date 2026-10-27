/**
 * 设备参数配置面板测试 - 天链V3
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import DeviceConfigPanel from '../pages/Devices/DeviceConfigPanel';

// Mock deviceAPI for testing
jest.mock('../api', () => ({
  deviceAPI: {
    getConfig: jest.fn(),
    updateConfig: jest.fn(),
  },
}));

describe('DeviceConfigPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('应能渲染参数配置面板', () => {
    const { getByText } = render(
      <BrowserRouter>
        <DeviceConfigPanel
          deviceId={1}
          deviceName="测试充电桩"
          open={true}
          onClose={() => {}}
        />
      </BrowserRouter>
    );

    // 检查标题
    expect(getByText(/参数配置.*测试充电桩/)).toBeInTheDocument();
    
    // 检查表单元素
    expect(screen.getByPlaceholderText(/420/)).toBeInTheDocument(); // 电压上限
    expect(screen.getByPlaceholderText(/60/)).toBeInTheDocument(); // 电流上限
    expect(screen.getByPlaceholderText(/60/)).toBeInTheDocument(); // 最大功率
    
    // 检查按钮
    expect(getByText(/添加时段/)).toBeInTheDocument();
    expect(getByText(/保存/)).toBeInTheDocument();
    expect(getByText(/取消/)).toBeInTheDocument();
  });

  it('应在打开时获取设备配置', async () => {
    const mockConfig = {
      device_id: 1,
      voltage_limit: 440.0,
      current_limit: 80.0,
      max_power: 80.0,
      charge_mode: 'fast',
      overload_protection: false,
      time_periods: [
        {
          start_time: '00:00',
          end_time: '06:00',
          power_limit: 30.0,
          price_per_kwh: 0.5,
        },
        {
          start_time: '06:00',
          end_time: '18:00',
          power_limit: 60.0,
          price_per_kwh: 1.0,
        },
        {
          start_time: '18:00',
          end_time: '00:00',
          power_limit: 40.0,
          price_per_kwh: 0.8,
        },
      ],
    };

    // Mock the getConfig API
    require('../api').deviceAPI.getConfig.mockResolvedValue({ data: mockConfig });

    const { findByPlaceholderText } = render(
      <BrowserRouter>
        <DeviceConfigPanel
          deviceId={1}
          deviceName="测试充电桩"
          open={true}
          onClose={() => {}}
        />
      </BrowserRouter>
    );

    // 等待配置数据加载
    await waitFor(() => {
      expect(findByPlaceholderText('440.0')).resolves.toBeInTheDocument();
    });

    // 验证 API 调用
    expect(require('../api').deviceAPI.getConfig).toHaveBeenCalledWith(1);
  });

  it('应能添加时段配置', () => {
    render(
      <BrowserRouter>
        <DeviceConfigPanel
          deviceId={1}
          deviceName="测试充电桩"
          open={true}
          onClose={() => {}}
        />
      </BrowserRouter>
    );

    // 点击添加时段按钮
    fireEvent.click(screen.getByText(/添加时段/));
    
    // 应该出现时段输入框
    expect(screen.getAllByPlaceholderText(/HH:MM/)).toHaveLength(2);
    expect(screen.getAllByLabelText(/功率限制\(kW\)/)).toHaveLength(1);
    expect(screen.getAllByLabelText(/电价\(元\/kWh\)/)).toHaveLength(1);
  });

  it('应能提交配置更改', async () => {
    // Mock successful update
    require('../api').deviceAPI.updateConfig.mockResolvedValue({ data: {} });

    const handleSave = jest.fn();
    const { getByText } = render(
      <BrowserRouter>
        <DeviceConfigPanel
          deviceId={1}
          deviceName="测试充电桩"
          open={true}
          onClose={() => {}}
          onSave={handleSave}
        />
      </BrowserRouter>
    );

    // 修改一些值
    fireEvent.change(screen.getByPlaceholderText(/420/), { target: { value: '440' } });
    fireEvent.change(screen.getByPlaceholderText(/60/), { target: { value: '80' } });

    // 点击保存按钮
    fireEvent.click(getByText(/保存/));

    // 等待保存完成
    await waitFor(() => {
      expect(handleSave).toHaveBeenCalled();
    });

    // 验证调用了 updateConfig API
    expect(require('../api').deviceAPI.updateConfig).toHaveBeenCalledWith(1, expect.objectContaining({
      voltage_limit: 440,
      current_limit: 80,
    }));
  });
});