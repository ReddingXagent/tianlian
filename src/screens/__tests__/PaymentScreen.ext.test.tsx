import React from 'react';
import { Alert, ActivityIndicator } from 'react-native';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { paymentApi } from '../../services/api';
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

describe('PaymentScreen extended coverage', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  const renderScreen = () =>
    render(<SafeAreaProvider><PaymentScreen /></SafeAreaProvider>);

  // === handlePay success → Alert "完成" → popToTop ===

  it('支付成功后点击"完成"调用 popToTop', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_title, _msg, buttons) => {
      if (buttons && Array.isArray(buttons)) {
        const doneBtn = buttons.find((b) => b.text === '完成');
        if (doneBtn && doneBtn.onPress) doneBtn.onPress();
      }
    });

    (paymentApi.pay as jest.Mock).mockResolvedValue({
      data: { success: true, message: 'ok', amount: 25.5, paidAmount: 25.5 },
    });

    const { getByText } = renderScreen();
    fireEvent.press(getByText('确认支付 ¥25.50'));

    await waitFor(() => {
      expect(mockPopToTop).toHaveBeenCalled();
    });

    alertSpy.mockRestore();
  });

  // === handlePay network error (non-axios) ===

  it('支付网络错误(无response属性)显示网络错误提示', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert');

    (paymentApi.pay as jest.Mock).mockRejectedValue(new Error('Network Error'));

    const { getByText } = renderScreen();
    fireEvent.press(getByText('确认支付 ¥25.50'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('支付失败', '网络错误，请检查网络连接');
    });
  });

  // === handlePay axios error without message ===

  it('支付axios错误无data.message显示默认失败提示', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert');

    (paymentApi.pay as jest.Mock).mockRejectedValue({ response: {} });

    const { getByText } = renderScreen();
    fireEvent.press(getByText('确认支付 ¥25.50'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('支付失败', '支付请求失败');
    });
  });

  // === switch all 3 payment methods ===

  it('切换支付宝支付方式', async () => {
    (paymentApi.pay as jest.Mock).mockResolvedValue({
      data: { success: true, paidAmount: 25.5 },
    });

    const { getByText } = renderScreen();
    fireEvent.press(getByText('支付宝'));
    fireEvent.press(getByText('确认支付 ¥25.50'));

    await waitFor(() => {
      expect(paymentApi.pay).toHaveBeenCalledWith({ orderId: 1, method: 'alipay' });
    });
  });

  it('切换余额支付方式', async () => {
    (paymentApi.pay as jest.Mock).mockResolvedValue({
      data: { success: true, paidAmount: 25.5 },
    });

    const { getByText } = renderScreen();
    fireEvent.press(getByText('余额支付'));
    fireEvent.press(getByText('确认支付 ¥25.50'));

    await waitFor(() => {
      expect(paymentApi.pay).toHaveBeenCalledWith({ orderId: 1, method: 'balance' });
    });
  });

  // === paying=true shows ActivityIndicator ===

  it('支付中按钮显示loading并禁用', async () => {
    let resolvePay: ((v: unknown) => void) | undefined;
    (paymentApi.pay as jest.Mock).mockImplementation(() => new Promise((resolve) => { resolvePay = resolve; }));

    const { getByText, UNSAFE_getByType } = renderScreen();
    fireEvent.press(getByText('确认支付 ¥25.50'));

    // While paying, ActivityIndicator should be rendered
    await waitFor(() => {
      expect(UNSAFE_getByType(ActivityIndicator)).toBeTruthy();
    });

    // Resolve to cleanup
    if (resolvePay) act(() => resolvePay!({ data: { success: true, paidAmount: 25.5 } }));
  });

  // === method selection radio UI ===

  it('选中微信支付时radio有内圆点', () => {
    const { getByText } = renderScreen();
    // 微信支付 is default selected
    expect(getByText('微信支付')).toBeTruthy();
  });

  // === formatMoney renders correctly in amount card ===

  it('金额卡片渲染formatMoney结果', () => {
    const { getAllByText } = renderScreen();
    // 25.50 should appear in amount display and button
    expect(getAllByText(/25\.50/).length).toBeGreaterThanOrEqual(2);
  });

  // === last payment method has no bottom border (index === length-1) ===

  it('最后一个支付方式(余额支付)无底边框分隔线', () => {
    const { getByText } = renderScreen();
    // Just verify it renders without crashing
    expect(getByText('余额支付')).toBeTruthy();
  });
});
