import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert } from 'react-native';

// ── Mock paymentApi ─────────────────────────────────────────
const mockPay = jest.fn();

jest.mock('../../services/api', () => ({
  __esModule: true,
  paymentApi: {
    pay: (...args: unknown[]) => mockPay(...args),
  },
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

describe('PaymentScreen.ext2 — success=false branch (L50)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  it('shows failure alert when payment returns success=false', async () => {
    mockPay.mockResolvedValue({
      data: { success: false, message: '余额不足' },
    });

    const { getByText } = renderScreen();
    fireEvent.press(getByText('确认支付 ¥50.00'));

    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('支付失败', '余额不足');
    });
  });

  it('shows fallback message when success=false and no message', async () => {
    mockPay.mockResolvedValue({
      data: { success: false },
    });

    const { getByText } = renderScreen();
    fireEvent.press(getByText('确认支付 ¥50.00'));

    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('支付失败', '请重试');
    });
  });
});
