/**
 * types/modules/user.ts — 用户/认证/钱包类型
 */
export interface User {
  id: number;
  phone: string;
  nickname: string;
  avatar?: string;
  balance: number;
  createdAt: string;
  updatedAt: string;
}

export interface LoginRequest {
  phone: string;
  code?: string;
  password?: string;
}

export interface SendCodeRequest {
  phone: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export type WalletRecordType = 'recharge' | 'consume' | 'refund' | 'withdraw';

export interface WalletRecord {
  id: number;
  userId: number;
  type: WalletRecordType;
  amount: number;
  balance: number;
  description: string;
  createdAt: string;
}

export interface UserStats {
  totalOrders: number;
  totalEnergy: number;
  totalAmount: number;
  totalDuration: number;
  couponCount: number;
}
