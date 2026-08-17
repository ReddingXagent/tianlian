import { renderHook, act } from '@testing-library/react-native';
import { paymentApi } from '../../services/api';
import { usePayment } from '../usePayment';

jest.mock('../../services/api', () => ({
  paymentApi: {
    pay: jest.fn(),
  },
}));

describe('usePayment', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should have correct initial state', () => {
    const { result } = renderHook(() => usePayment());

    expect(result.current.selectedMethod).toBe('wechat');
    expect(result.current.paying).toBe(false);
  });

  it('should accept initial method', () => {
    const { result } = renderHook(() => usePayment('alipay'));
    expect(result.current.selectedMethod).toBe('alipay');
  });

  it('should set selected method', () => {
    const { result } = renderHook(() => usePayment());
    act(() => result.current.setSelectedMethod('alipay'));
    expect(result.current.selectedMethod).toBe('alipay');
  });

  it('should pay successfully', async () => {
    (paymentApi.pay as jest.Mock).mockResolvedValue({
      data: { success: true, paidAmount: 29.99 },
    });

    const { result } = renderHook(() => usePayment());

    let payResult: { success: boolean; paidAmount?: number } | undefined;
    await act(async () => {
      payResult = await result.current.pay(1, 29.99);
    });

    expect(payResult?.success).toBe(true);
    expect(payResult?.paidAmount).toBe(29.99);
    expect(result.current.paying).toBe(false);
    expect(paymentApi.pay).toHaveBeenCalledWith({ orderId: 1, method: 'wechat' });
  });

  it('should handle pay response with success=false', async () => {
    (paymentApi.pay as jest.Mock).mockResolvedValue({
      data: { success: false, message: '余额不足' },
    });

    const { result } = renderHook(() => usePayment());

    let payResult: { success: boolean; message?: string } | undefined;
    await act(async () => {
      payResult = await result.current.pay(1, 29.99);
    });

    expect(payResult?.success).toBe(false);
    expect(payResult?.message).toBe('余额不足');
    expect(result.current.paying).toBe(false);
  });

  it('should handle pay axios error', async () => {
    (paymentApi.pay as jest.Mock).mockRejectedValue({
      response: { data: { message: '订单已支付' } },
    });

    const { result } = renderHook(() => usePayment());

    let payResult: { success: boolean; message?: string } | undefined;
    await act(async () => {
      payResult = await result.current.pay(1, 29.99);
    });

    expect(payResult?.success).toBe(false);
    expect(payResult?.message).toBe('订单已支付');
    expect(result.current.paying).toBe(false);
  });

  it('should handle pay network error', async () => {
    (paymentApi.pay as jest.Mock).mockRejectedValue(new Error('Network'));

    const { result } = renderHook(() => usePayment());

    let payResult: { success: boolean; isNetworkError?: boolean } | undefined;
    await act(async () => {
      payResult = await result.current.pay(1, 29.99);
    });

    expect(payResult?.success).toBe(false);
    expect(payResult?.isNetworkError).toBe(true);
    expect(result.current.paying).toBe(false);
  });

  it('should use selected method in pay call', async () => {
    (paymentApi.pay as jest.Mock).mockResolvedValue({
      data: { success: true, paidAmount: 10 },
    });

    const { result } = renderHook(() => usePayment());
    act(() => result.current.setSelectedMethod('alipay'));

    await act(async () => {
      await result.current.pay(5, 10);
    });

    expect(paymentApi.pay).toHaveBeenCalledWith({ orderId: 5, method: 'alipay' });
  });
});
