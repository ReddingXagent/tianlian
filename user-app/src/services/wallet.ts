import { ApiResponse, WalletRecord, PaginatedData } from '../types';
import api from './client';

// =====================
// 钱包 API
// =====================
export const walletApi = {
  getBalance(): Promise<ApiResponse<{ balance: number }>> {
    return api.get('/wallet/balance').then((res) => res.data);
  },
  getRecords(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<WalletRecord>>> {
    return api.get('/wallet/records', { params }).then((res) => res.data);
  },
  recharge(amount: number): Promise<ApiResponse<{ tradeNo: string; url?: string }>> {
    return api.post('/wallet/recharge', { amount }).then((res) => res.data);
  },
};
