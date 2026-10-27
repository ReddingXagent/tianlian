/**
 * types/modules/common.ts — 通用API响应 + 导航参数
 */
// 共享类型从 @tianlian/shared-types 重导出，保持仓内 import 路径不变
export { type ApiResponse, type PaginatedData } from '@tianlian/shared-types';

export type RootStackParamList = {
  Auth: undefined;
  Main: undefined;
  StationDetail: { stationId: number };
  DeviceList: { stationId: number; stationName: string };
  DeviceDetail: { deviceId: number; stationId: number };
  AlarmList: { stationId?: number };
  WorkOrder: { stationId?: number };
  ChargerMonitor: { stationId: number; stationName: string };
  NotificationCenter: undefined;
  MerchantKYC: undefined;
};

export type AuthStackParamList = {
  Login: undefined;
};

export type MainTabParamList = {
  Dashboard: undefined;
  Stations: undefined;
  Revenue: undefined;
  Profile: undefined;
};
