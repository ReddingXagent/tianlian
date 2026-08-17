/**
 * types/modules/common.ts — 通用API响应 + 导航参数
 */
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
  Main: undefined;
  StationDetail: { stationId: number };
  DeviceList: { stationId: number; stationName: string };
  DeviceDetail: { deviceId: number; stationId: number };
  AlarmList: { stationId?: number };
  WorkOrder: { stationId?: number };
  ChargerMonitor: { stationId: number; stationName: string };
  NotificationCenter: undefined;
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
