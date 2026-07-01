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
});