import React from 'react';
import { Alert, TouchableOpacity } from 'react-native';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
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

jest.mock('../../services/api', () => {
  const scan = jest.fn();
  return { chargingApi: { scan } };
});

// 捕获 startCharging 以验证不可用桩不会发起充电
const mockStartCharging = jest.fn();
jest.mock('../../store/orderStore', () => ({
  useOrderStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ startCharging: mockStartCharging }),
}));

jest.mock('../../components/StatusBadge', () => 'StatusBadge');

jest.mock('expo-camera', () => ({
  CameraView: () => null,
  useCameraPermissions: () => [
    { status: 'granted', granted: true, canAskAgain: true },
    () => Promise.resolve({ status: 'granted', granted: true, canAskAgain: true }),
  ],
}));

describe('ScanScreen.ext5 — 非idle充电桩启动拦截分支', () => {
  let alertSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  afterEach(() => {
    alertSpy.mockRestore();
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <ScanScreen />
      </SafeAreaProvider>
    );

  it('alerts 该充电桩当前不可用 and blocks start when charger status is not idle', async () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { chargingApi } = require('../../services/api');
    chargingApi.scan.mockResolvedValue({
      data: {
        id: 9, type: 'charger', code: 'CH-009', name: '充电桩B',
        stationId: 1, stationName: '测试站', power: 60,
        pricePerKwh: 1.2, serviceFee: 0.8, status: 'charging',
      },
    });

    const renderResult = renderScreen();
    const { getByPlaceholderText, getByText } = renderResult;
    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'CH-009');
    fireEvent.press(getByText('查询'));

    // 非idle → 按钮文案变为"当前不可用"
    await waitFor(() => {
      expect(getByText('当前不可用')).toBeTruthy();
    });

    // 按钮虽已disabled(UI首层防护), handleStartCharging自身仍须有状态校验(纵深防御):
    // 绕过disabled直接调用元素上的onPress(模拟自动化/无障碍直点、状态竞态)
    const containsText = (node: unknown, text: string): boolean => {
      if (typeof node === 'string') return node.includes(text);
      if (Array.isArray(node)) return node.some((n) => containsText(n, text));
      if (node && typeof node === 'object' && 'props' in node) {
        return containsText((node as { props: { children?: unknown } }).props.children, text);
      }
      return false;
    };
    const { UNSAFE_getAllByType } = renderResult;
    const startBtn = UNSAFE_getAllByType(TouchableOpacity).find(
      (el) => containsText(el.props.children, '当前不可用')
    );
    expect(startBtn).toBeTruthy();
    expect(startBtn!.props.disabled).toBe(true);
    act(() => {
      startBtn!.props.onPress();
    });

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('提示', '该充电桩当前不可用');
    });
    expect(mockStartCharging).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
