/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import PaymentScreen from '../PaymentScreen';

const mockPopToTop = jest.fn();
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ popToTop: mockPopToTop, navigate: mockNavigate }),
  useRoute: () => ({ params: { orderId: 1, amount: 25.5 } }),
}));

jest.mock('../../services/api', () => {
  const pay = jest.fn();
  return { paymentApi: { pay } };
});

describe('PaymentScreen', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  const renderScreen = () =>
    render(<SafeAreaProvider><PaymentScreen /></SafeAreaProvider>);

  it('renders amount display', () => {
    const { getByText, getAllByText } = renderScreen();
    expect(getByText('待支付金额')).toBeTruthy();
    expect(getAllByText(/25\.50/).length).toBeGreaterThanOrEqual(1);
  });

  it('renders payment method options', () => {
    const { getByText } = renderScreen();
    expect(getByText('微信支付')).toBeTruthy();
    expect(getByText('支付宝')).toBeTruthy();
    expect(getByText('余额支付')).toBeTruthy();
  });

  it('renders confirm button with amount', () => {
    const { getByText } = renderScreen();
    expect(getByText('确认支付 ¥25.50')).toBeTruthy();
  });

  it('renders service agreement text', () => {
    const { getByText } = renderScreen();
    expect(getByText(/充电服务协议/)).toBeTruthy();
  });

  it('can switch payment method', () => {
    const { getByText } = renderScreen();
    fireEvent.press(getByText('支付宝'));
    expect(getByText('确认支付 ¥25.50')).toBeTruthy();
  });

  it('calls pay API on confirm', async () => {
    const { paymentApi } = require('../../services/api');
    paymentApi.pay.mockResolvedValue({
      data: { success: true, message: 'ok', amount: 25.5, paidAmount: 25.5 },
    });
    const { getByText } = renderScreen();
    fireEvent.press(getByText('确认支付 ¥25.50'));
    await waitFor(() => {
      expect(paymentApi.pay).toHaveBeenCalledWith({ orderId: 1, method: 'wechat' });
    });
  });

  it('handles payment failure', async () => {
    const { paymentApi } = require('../../services/api');
    paymentApi.pay.mockResolvedValue({
      data: { success: false, message: '余额不足', amount: 25.5, paidAmount: 0 },
    });
    const { getByText } = renderScreen();
    fireEvent.press(getByText('确认支付 ¥25.50'));
    await waitFor(() => {
      expect(paymentApi.pay).toHaveBeenCalled();
    });
  });

  it('handles API error', async () => {
    const { paymentApi } = require('../../services/api');
    paymentApi.pay.mockRejectedValue({ response: { data: { message: '网络超时' } } });
    const { getByText } = renderScreen();
    fireEvent.press(getByText('确认支付 ¥25.50'));
    await waitFor(() => {
      expect(paymentApi.pay).toHaveBeenCalled();
    });
  });
});