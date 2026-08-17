/**
 * types/modules/common.ts — 通用API响应 + 导航参数
 */
import type { NavigatorScreenParams } from '@react-navigation/native';

// 共享类型从 @tianlian/shared-types 重导出，保持仓内 import 路径不变
export { type ApiResponse, type PaginatedData } from '@tianlian/shared-types';

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
  Energy: undefined;
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
