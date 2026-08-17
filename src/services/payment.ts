import { ApiResponse, PaymentRequest, PaymentResult } from '../types';
import api from './client';

// =====================
// 支付 API
// =====================
export const paymentApi = {
  pay(data: PaymentRequest): Promise<ApiResponse<PaymentResult>> {
    return api.post('/payment/pay', data).then((res) => res.data);
  },
  getPaymentInfo(orderId: number): Promise<ApiResponse<{ amount: number; balance: number; couponDiscount: number }>> {
    return api.get(`/payment/${orderId}/info`).then((res) => res.data);
  },
};
