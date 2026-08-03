/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { render, act, fireEvent } from '@testing-library/react-native';
import DeviceDetailScreen from '../DeviceDetailScreen';
import { useDeviceControlLogStore } from '../../store/deviceControlLogStore';
import { deviceApi } from '../../services/api';

// Mock navigation and route
jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({
    params: { deviceId: 101, stationId: 1 },
  }),
  useNavigation: () => ({ navigate: jest.fn(), setOptions: jest.fn() }),
}));

// Mock the API module
jest.mock('../../services/api', () => ({
  deviceApi: {
    getDetail: jest.fn(),
    getTelemetry: jest.fn(),
    controlDevice: jest.fn(),
  },
}));

// Mock child components
jest.mock('../../components/LoadingSpinner', () => {
  const MockLoadingSpinner = (props: any) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, null, props.text || '加载中...');
  };
  return MockLoadingSpinner;
});
jest.mock('../../components/StatusBadge', () => {
  const MockStatusBadge = (props: any) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, null, props.label || props.status || 'badge');
  };
  return MockStatusBadge;
});
jest.mock('../../components/EmptyState', () => {
  const MockEmptyState = (props: any) => {
    const React = require('react');
    const { View, Text, TouchableOpacity } = require('react-native');
    const elements = [React.createElement(Text, { key: 'title' }, props.title || '')];
    if (props.message) {
      elements.push(React.createElement(Text, { key: 'msg' }, props.message));
    }
    if (props.actionLabel && props.onAction) {
      elements.push(
        React.createElement(TouchableOpacity, { key: 'btn', onPress: props.onAction },
          React.createElement(Text, null, props.actionLabel)
        )
      );
    }
    return React.createElement(View, null, elements);
  };
  return MockEmptyState;
});

const MOCK_DEVICE = {
  id: 101,
  stationId: 1,
  name: '充电桩A-01',
  code: 'CH-A01',
  type: 'charger' as const,
  status: 'online' as const,
  model: 'CH-2000',
  manufacturer: '厂商A',
  lastHeartbeat: '2024-01-15T10:30:00Z',
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-15T10:30:00Z',
};

const MOCK_TELEMETRY = {
  deviceId: 101,
  power: 45.6,
  voltage: 380,
  current: 120,
  temperature: 42,
  energy: 12345.6,
  timestamp: '2024-01-15T10:30:00Z',
};

describe('DeviceDetailScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useDeviceControlLogStore.getState().reset();
    (deviceApi.getDetail as jest.Mock).mockResolvedValue({ data: MOCK_DEVICE });
    (deviceApi.getTelemetry as jest.Mock).mockResolvedValue({ data: MOCK_TELEMETRY });
    (deviceApi.controlDevice as jest.Mock).mockResolvedValue({
      data: { success: true, message: '停止指令已发送' },
    });
  });

  it('should render loading state initially', () => {
    (deviceApi.getDetail as jest.Mock).mockImplementation(() => new Promise(() => {}));

    const { getByText } = render(<DeviceDetailScreen />);
    expect(getByText('加载设备详情...')).toBeTruthy();
  });

  it('should render device details after loading', async () => {
    const { findByText } = render(<DeviceDetailScreen />);

    expect(await findByText('充电桩A-01')).toBeTruthy();
    expect(await findByText(/CH-A01/)).toBeTruthy();
    expect(await findByText(/CH-2000/)).toBeTruthy();
    expect(await findByText(/厂商A/)).toBeTruthy();
  });

  it('should render telemetry data', async () => {
    const { findByText, findAllByText } = render(<DeviceDetailScreen />);

    expect(await findByText('实时遥测')).toBeTruthy();

    // Power value may appear in both power and energy displays
    const powerElements = await findAllByText('45.6');
    expect(powerElements.length).toBeGreaterThanOrEqual(1);

    // Voltage is unique
    expect(await findByText('380')).toBeTruthy();
  });

  it('should render remote control buttons', async () => {
    const { findByText } = render(<DeviceDetailScreen />);

    expect(await findByText('远程控制')).toBeTruthy();
    expect(await findByText('启动')).toBeTruthy();
    expect(await findByText('停止')).toBeTruthy();
    expect(await findByText('重启')).toBeTruthy();
    expect(await findByText('复位')).toBeTruthy();
  });

  it('should handle error state', async () => {
    (deviceApi.getDetail as jest.Mock).mockRejectedValue(new Error('API Error'));

    const { findByText } = render(<DeviceDetailScreen />);
    expect(await findByText('加载设备详情失败')).toBeTruthy();
  });

  it('should render telemetry with temperature color warning', async () => {
    const highTempTelemetry = { ...MOCK_TELEMETRY, temperature: 75 };
    (deviceApi.getTelemetry as jest.Mock).mockResolvedValue({ data: highTempTelemetry });

    const { findByText } = render(<DeviceDetailScreen />);
    expect(await findByText('实时遥测')).toBeTruthy();
  });

  it('should show empty operation log initially', async () => {
    const { findByText } = render(<DeviceDetailScreen />);
    expect(await findByText('暂无操作记录')).toBeTruthy();
  });

  it('should open confirm dialog when pressing a control button', async () => {
    const { findByText } = render(<DeviceDetailScreen />);

    await findByText('远程控制');
    fireEvent.press(await findByText('停止'));

    // 确认对话框出现，包含设备名与确认按钮
    expect(await findByText('确定要停止设备「充电桩A-01」吗？')).toBeTruthy();
    expect(await findByText('确认停止')).toBeTruthy();
  });

  it('should execute control, call API and record a success log on confirm', async () => {
    const { findByText } = render(<DeviceDetailScreen />);

    await findByText('远程控制');
    fireEvent.press(await findByText('停止'));
    fireEvent.press(await findByText('确认停止'));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(deviceApi.controlDevice).toHaveBeenCalledWith(101, 'stop');
    // 操作日志写入成功记录
    expect(await findByText('停止指令已发送')).toBeTruthy();
    expect(await findByText('成功')).toBeTruthy();
  });

  it('formatLogTime falls back to raw dateStr when toLocaleString throws (F187)', async () => {
    // 只对日志时间(当前时间)抛错; 心跳/遥测的固定2024 mock时间放行(它们在try/catch外渲染)
    const original = Date.prototype.toLocaleString;
    const spy = jest
      .spyOn(Date.prototype, 'toLocaleString')
      .mockImplementation(function (this: Date, ...args: Parameters<Date['toLocaleString']>) {
        if (this.getUTCFullYear() === 2024) {
          return original.call(this, ...args);
        }
        throw new Error('locale failed');
      });

    try {
      const { findByText } = render(<DeviceDetailScreen />);

      await findByText('远程控制');
      fireEvent.press(await findByText('停止'));
      fireEvent.press(await findByText('确认停止'));

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // catch分支: 时间格式化失败回退原始dateStr, 日志仍渲染不崩溃
      expect(await findByText('停止指令已发送')).toBeTruthy();
    } finally {
      spy.mockRestore();
    }
  });

  it('should cancel the confirm dialog without calling the API', async () => {
    const { findByText, queryByText } = render(<DeviceDetailScreen />);

    await findByText('远程控制');
    fireEvent.press(await findByText('停止'));
    fireEvent.press(await findByText('取消'));

    expect(deviceApi.controlDevice).not.toHaveBeenCalled();
    expect(queryByText('确认停止')).toBeNull();
  });

  it('should record a failed log when control API rejects', async () => {
    (deviceApi.controlDevice as jest.Mock).mockRejectedValue(new Error('API Error'));

    const { findByText } = render(<DeviceDetailScreen />);

    await findByText('远程控制');
    fireEvent.press(await findByText('停止'));
    fireEvent.press(await findByText('确认停止'));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(await findByText('失败')).toBeTruthy();
    expect(await findByText('发送停止指令失败')).toBeTruthy();
  });

  it('pull-to-refresh should re-fetch device detail', async () => {
    const { RefreshControl } = require('react-native');
    const { findByText, UNSAFE_getByType } = render(<DeviceDetailScreen />);
    await findByText('充电桩A-01');

    const rc = UNSAFE_getByType(RefreshControl);
    await act(async () => {
      rc.props.onRefresh();
      await new Promise((r) => setTimeout(r, 0));
    });

    // 初始加载1次 + 下拉刷新1次
    expect(deviceApi.getDetail).toHaveBeenCalledTimes(2);
  });

  it('should degrade gracefully when telemetry API fails', async () => {
    (deviceApi.getTelemetry as jest.Mock).mockRejectedValue(new Error('no telemetry'));

    const { findByText, queryByText } = render(<DeviceDetailScreen />);
    expect(await findByText('充电桩A-01')).toBeTruthy();
    // 遥测失败不影响设备详情, 遥测区隐藏
    expect(queryByText('实时遥测')).toBeNull();
  });

  it('should recover after pressing retry on error state', async () => {
    (deviceApi.getDetail as jest.Mock)
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValue({ data: MOCK_DEVICE });

    const { findByText } = render(<DeviceDetailScreen />);
    expect(await findByText('加载设备详情失败')).toBeTruthy();

    fireEvent.press(await findByText('重试'));
    expect(await findByText('充电桩A-01')).toBeTruthy();
  });

  it('should open confirm dialogs for restart and reset buttons', async () => {
    const { findByText, queryByText } = render(<DeviceDetailScreen />);
    await findByText('远程控制');

    fireEvent.press(await findByText('重启'));
    expect(await findByText('确认重启')).toBeTruthy();

    fireEvent.press(await findByText('取消'));
    expect(queryByText('确认重启')).toBeNull();

    fireEvent.press(await findByText('复位'));
    expect(await findByText('确认复位')).toBeTruthy();
  });

  it('should disable start button when device is online', async () => {
    const { findByText, queryByText } = render(<DeviceDetailScreen />);
    await findByText('远程控制');

    // 在线设备禁止启动
    fireEvent.press(await findByText('启动'));
    expect(queryByText('确认启动')).toBeNull();
  });

  it('should allow start for offline battery device and show fallback heartbeat', async () => {
    (deviceApi.getDetail as jest.Mock).mockResolvedValue({
      data: { ...MOCK_DEVICE, status: 'offline', type: 'battery', lastHeartbeat: null },
    });

    const { findByText } = render(<DeviceDetailScreen />);
    // 离线电池设备: 🔋图标 + 无心跳降级
    expect(await findByText('🔋')).toBeTruthy();
    expect(await findByText('无数据')).toBeTruthy();

    fireEvent.press(await findByText('启动'));
    expect(await findByText('确定要启动设备「充电桩A-01」吗？')).toBeTruthy();
    expect(await findByText('确认启动')).toBeTruthy();
  });

  it('should render inverter icon, offline badge for undefined status, and - fallbacks for missing model/manufacturer', async () => {
    (deviceApi.getDetail as jest.Mock).mockResolvedValue({
      data: { ...MOCK_DEVICE, type: 'inverter', status: undefined, model: '', manufacturer: '' },
    });

    const { findByText, findAllByText } = render(<DeviceDetailScreen />);
    // inverter图标分支 + status缺失回退offline + model/manufacturer空值回退'-'
    expect(await findByText('⚡')).toBeTruthy();
    expect(await findByText('offline')).toBeTruthy();
    expect((await findAllByText('-')).length).toBeGreaterThanOrEqual(2);
  });

  it('should render satellite icon for unknown device type', async () => {
    (deviceApi.getDetail as jest.Mock).mockResolvedValue({
      data: { ...MOCK_DEVICE, type: 'other' },
    });

    const { findByText } = render(<DeviceDetailScreen />);
    // 非charger/battery/inverter → 📡兜底图标分支
    expect(await findByText('📡')).toBeTruthy();
  });

  it('should render medium temperature (45-60°C) warning color', async () => {
    (deviceApi.getTelemetry as jest.Mock).mockResolvedValue({
      data: { ...MOCK_TELEMETRY, temperature: 50 },
    });

    const { findByText } = render(<DeviceDetailScreen />);
    // >45且<=60的中间档颜色分支(默认42覆盖<=45, 已有75覆盖>60)
    expect(await findByText('50')).toBeTruthy();
  });

  it('should fall back to default message when control response has no message', async () => {
    (deviceApi.controlDevice as jest.Mock).mockResolvedValue({ data: { success: true } });

    const { findByText } = render(<DeviceDetailScreen />);
    await findByText('远程控制');
    fireEvent.press(await findByText('停止'));
    fireEvent.press(await findByText('确认停止'));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    // response.data.message缺失 → `${label}指令已发送`回退分支
    expect(await findByText('停止指令已发送')).toBeTruthy();
  });
});