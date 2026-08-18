import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert } from 'react-native';

// 直接 mock usePayment hook: 经真实 hook 时 message 恒非空('请重试'/'支付请求失败'/
// 网络错误文案), Screen L44 的 || '请重试' falsy 分支仅在未来 hook 契约变化时触发;
// Screen 层防御性 fallback 需绕过 hook 验证
const mockPay = jest.fn();
jest.mock('../../hooks/usePayment', () => ({
  usePayment: () => ({
    selectedMethod: 'wechat',
    setSelectedMethod: jest.fn(),
    paying: false,
    pay: mockPay,
  }),
}));

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { orderId: 1, amount: 50 } }),
  useNavigation: () => ({
    navigate: jest.fn(),
    replace: jest.fn(),
    popToTop: jest.fn(),
  }),
}));

import PaymentScreen from '../PaymentScreen';

const renderScreen = () =>
  render(
    <SafeAreaProvider>
      <PaymentScreen />
    </SafeAreaProvider>,
  );

describe('PaymentScreen.ext3 — L44 defensive fallback branch', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  // L44: result.message 为 falsy → || '请重试' 兜底
  it('shows fallback message when hook returns success=false without message', async () => {
    mockPay.mockResolvedValue({ success: false, message: undefined });

    const { getByText } = renderScreen();
    fireEvent.press(getByText('确认支付 ¥50.00'));

    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('支付失败', '请重试');
    });
  });
});
