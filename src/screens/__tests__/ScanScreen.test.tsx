import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import ScanScreen from '../ScanScreen';

// Mock navigation
const mockNavigate = jest.fn();
const mockReplace = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({
    navigate: mockNavigate,
    replace: mockReplace,
  }),
}));

// Must define mock functions INSIDE jest.mock factory due to hoisting
jest.mock('../../services/api', () => {
  const scan = jest.fn();
  return { chargingApi: { scan } };
});

jest.mock('../../store/orderStore', () => ({
  useOrderStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ startCharging: jest.fn() }),
}));

jest.mock('../../components/StatusBadge', () => 'StatusBadge');

describe('ScanScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <ScanScreen />
      </SafeAreaProvider>
    );

  it('renders scanner hint text', () => {
    const { getByText } = renderScreen();
    expect(getByText('扫描充电桩二维码')).toBeTruthy();
  });

  it('renders manual input field', () => {
    const { getByPlaceholderText } = renderScreen();
    expect(getByPlaceholderText('输入充电桩编码')).toBeTruthy();
  });

  it('renders query button', () => {
    const { getByText } = renderScreen();
    expect(getByText('查询')).toBeTruthy();
  });

  it('renders quick input buttons', () => {
    const { getByText } = renderScreen();
    expect(getByText('CH-001')).toBeTruthy();
    expect(getByText('CH-002')).toBeTruthy();
    expect(getByText('CH-003')).toBeTruthy();
  });

  it('shows error when submitting empty code', async () => {
    const { getByText } = renderScreen();
    fireEvent.press(getByText('查询'));
    await waitFor(() => {
      expect(getByText('请输入充电桩编码')).toBeTruthy();
    });
  });

  it('calls scan API on valid code', async () => {
    const { getByPlaceholderText, getByText } = renderScreen();
    const input = getByPlaceholderText('输入充电桩编码');
    fireEvent.changeText(input, 'CH-001');

    // Get reference to the mock scan fn from the mocked module
    const { chargingApi } = require('../../services/api');
    chargingApi.scan.mockResolvedValue({
      data: {
        id: 1, type: 'charger', code: 'CH-001', name: '充电桩A',
        stationId: 1, stationName: '测试站', power: 60,
        pricePerKwh: 1.2, serviceFee: 0.8, status: 'idle',
      },
    });

    fireEvent.press(getByText('查询'));

    await waitFor(() => {
      expect(chargingApi.scan).toHaveBeenCalledWith('CH-001');
    });
  });

  it('handles scan API error', async () => {
    const { getByPlaceholderText, getByText } = renderScreen();
    const input = getByPlaceholderText('输入充电桩编码');
    fireEvent.changeText(input, 'INVALID');

    const { chargingApi } = require('../../services/api');
    chargingApi.scan.mockRejectedValue({ response: { data: { message: '充电桩不存在' } } });

    fireEvent.press(getByText('查询'));

    await waitFor(() => {
      expect(getByText('充电桩不存在')).toBeTruthy();
    });
  });

  it('handles network error', async () => {
    const { getByPlaceholderText, getByText } = renderScreen();
    const input = getByPlaceholderText('输入充电桩编码');
    fireEvent.changeText(input, 'CH-001');

    const { chargingApi } = require('../../services/api');
    chargingApi.scan.mockRejectedValue(new Error('Network Error'));

    fireEvent.press(getByText('查询'));

    await waitFor(() => {
      expect(getByText('网络错误，请检查网络连接')).toBeTruthy();
    });
  });
});