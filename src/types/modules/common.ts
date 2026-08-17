/**
 * types/modules/common.ts — 通用API响应 + 导航参数
 */
import type { NavigatorScreenParams } from '@react-navigation/native';

export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export type RootStackParamList = {
  Auth: undefined;
  Main: NavigatorScreenParams<MainTabParamList> | undefined;
  StationDetail: { stationId: number };
  Charging: { orderId: number };
  OrderDetail: { orderId: number };
  Payment: { orderId: number; amount: number };
  Vehicle: undefined;
  Wallet: undefined;
  Coupon: undefined;
  Login: undefined;
};

export type AuthStackParamList = {
  Login: undefined;
};

export type MainTabParamList = {
  Home: undefined;
  Orders: undefined;
  Scan: undefined;
  Profile: undefined;
};
