import React from 'react';
import { render, waitFor, fireEvent, act } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import ChargingScreen from '../ChargingScreen';

// Mock navigation
const mockReplace = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ replace: mockReplace }),
  useRoute: () => ({ params: { orderId: 42 } }),
}));

// Mock API
jest.mock('../../services/api', () => {
  const getStatus = jest.fn();
  return { chargingApi: { getStatus } };
});

// Mock order store
jest.mock('../../store/orderStore', () => ({
  useOrderStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ stopCharging: jest.fn() }),
}));

const mockChargingData = {
  orderId: 42, orderNo: 'ORD-001', chargerName: '充电桩A', stationName: '测试站',
  status: 'charging', power: 30.5, voltage: 400.2, current: 76.1,
  energy: 5.32, duration: 10.5, amount: 6.38, startTime: '2026-08-03T10:00:00Z',
};

describe('ChargingScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  const renderScreen = () =>
    render(<SafeAreaProvider><ChargingScreen /></SafeAreaProvider>);

  it('renders loading state initially', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockReturnValue(new Promise(() => {}));
    const { getByText } = renderScreen();
    expect(getByText('获取充电状态...')).toBeTruthy();
  });

  it('renders charging data after fetch', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('30.5')).toBeTruthy();
      expect(getByText('kW')).toBeTruthy();
    });
  });

  it('displays station and charger info', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('测试站')).toBeTruthy();
      expect(getByText('充电桩A')).toBeTruthy();
    });
  });

  it('displays energy and duration', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('5.32 kWh')).toBeTruthy();
      expect(getByText(/10分/)).toBeTruthy();
    });
  });

  it('renders stop charging button', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('停止充电')).toBeTruthy();
    });
  });

  it('navigates to payment when status is completed', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({
      data: { ...mockChargingData, status: 'completed', amount: 10.5 },
    });
    renderScreen();
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('Payment', { orderId: 42, amount: 10.5 });
    });
  });

  it('shows error state with retry when first fetch fails', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockRejectedValue(new Error('network down'));
    const { getByText } = renderScreen();
    // 首帧失败: 显示错误信息+重试按钮(此前实现会永远静默转圈)
    await waitFor(() => {
      expect(getByText('network down')).toBeTruthy();
      expect(getByText('重试')).toBeTruthy();
    });
    // 点重试后恢复 → 正常渲染数据
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    fireEvent.press(getByText('重试'));
    await waitFor(() => {
      expect(getByText('30.5')).toBeTruthy();
    });
  });

  it('keeps last data and shows hint when a polling tick fails', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus
      .mockResolvedValueOnce({ data: mockChargingData })
      .mockRejectedValue(new Error('flaky'));
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('30.5')).toBeTruthy();
    });
    // 下一轮询失败: 偶发错误不冻结页面, 显示失败提示且保留最后数据
    await act(async () => {
      jest.advanceTimersByTime(3000);
    });
    await waitFor(() => {
      expect(getByText(/刷新失败/)).toBeTruthy();
    });
    expect(getByText('30.5')).toBeTruthy();
  });
});