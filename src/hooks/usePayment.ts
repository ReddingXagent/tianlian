import { useState, useCallback } from 'react';
import { paymentApi } from '../services/api';
import { PaymentMethod } from '../types';

interface UsePaymentReturn {
  selectedMethod: PaymentMethod;
  setSelectedMethod: (method: PaymentMethod) => void;
  paying: boolean;
  pay: (orderId: number, amount: number) => Promise<{ success: boolean; paidAmount?: number; message?: string; isNetworkError?: boolean }>;
}

export function usePayment(initialMethod: PaymentMethod = 'wechat'): UsePaymentReturn {
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethod>(initialMethod);
  const [paying, setPaying] = useState(false);

  const pay = useCallback(async (orderId: number, _amount: number) => {
    setPaying(true);
    try {
      const response = await paymentApi.pay({
        orderId,
        method: selectedMethod,
      });
      if (response.data.success) {
        return { success: true, paidAmount: response.data.paidAmount };
      } else {
        return { success: false, message: response.data.message || '请重试' };
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        return { success: false, message: axiosErr.response?.data?.message || '支付请求失败' };
      } else {
        return { success: false, message: '网络错误，请检查网络连接', isNetworkError: true };
      }
    } finally {
      setPaying(false);
    }
  }, [selectedMethod]);

  return {
    selectedMethod,
    setSelectedMethod,
    paying,
    pay,
  };
}
