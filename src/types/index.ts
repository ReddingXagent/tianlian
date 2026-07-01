// =====================
// 站点 (Station)
// =====================
export interface Station {
  id: number;
  name: string;
  code: string;
  address: string;
  status: StationStatus;
  latitude: number;
  longitude: number;
  deviceCount: number;
  onlineDeviceCount: number;
  alarmCount: number;
  createdAt: string;
  updatedAt: string;
}

export type StationStatus = 'online' | 'offline' | 'maintenance';

// =====================
// 设备 (Device)
// =====================
export interface Device {
  id: number;
  stationId: number;
  name: string;
  code: string;
  type: DeviceType;
  status: DeviceStatus;
  model: string;
  manufacturer: string;
  lastHeartbeat: string;
  createdAt: string;
  updatedAt: string;
}

export type DeviceType = 'charger' | 'battery' | 'inverter' | 'sensor' | 'other';

export type DeviceStatus = 'online' | 'offline' | 'fault' | 'maintenance';

// =====================
// 告警 (Alarm)
// =====================
export interface Alarm {
  id: number;
  stationId: number;
  stationName: string;
  deviceId?: number;
  deviceName?: string;
  type: AlarmType;
  level: AlarmLevel;
  title: string;
  description: string;
  status: AlarmStatus;
  handledBy?: number;
  handledAt?: string;
  createdAt: string;
  updatedAt: string;
}

export type AlarmType = 'device_fault' | 'power_anomaly' | 'communication_loss' | 'temperature_warning' | 'other';

export type AlarmLevel = 'info' | 'warning' | 'critical';

export type AlarmStatus = 'unhandled' | 'processing' | 'resolved';

// =====================
// 工单 (WorkOrder)
// =====================
export interface WorkOrder {
  id: number;
  stationId: number;
  stationName: string;
  title: string;
  description: string;
  type: WorkOrderType;
  priority: WorkOrderPriority;
  status: WorkOrderStatus;
  assigneeId?: number;
  assigneeName?: string;
  creatorId: number;
  creatorName: string;
  alarmId?: number;
  scheduledAt?: string;
  completedAt?: string;
  createdAt: string;
  updatedAt: string;
}

export type WorkOrderType = 'repair' | 'inspection' | 'installation' | 'maintenance' | 'other';

export type WorkOrderPriority = 'low' | 'normal' | 'high' | 'urgent';

export type WorkOrderStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled';

// =====================
// 用户 (User)
// =====================
export interface User {
  id: number;
  username: string;
  nickname: string;
  email: string;
  phone: string;
  role: UserRole;
  avatar?: string;
  stationIds: number[];
  createdAt: string;
  updatedAt: string;
}

export type UserRole = 'admin' | 'station_master' | 'operator' | 'viewer';

// =====================
// 营收 (Revenue)
// =====================
export interface RevenueSummary {
  today: number;
  week: number;
  month: number;
  total: number;
}

export interface RevenueRecord {
  date: string;
  amount: number;
  orderCount: number;
}

// =====================
// 通用API响应
// =====================
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

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface DashboardStats {
  totalStations: number;
  onlineStations: number;
  offlineStations: number;
  totalAlarms: number;
  unhandledAlarms: number;
  revenueSummary: RevenueSummary;
}

export interface RevenueQuery {
  type: 'day' | 'week' | 'month';
  startDate?: string;
  endDate?: string;
}

export interface DeviceTelemetry {
  deviceId: number;
  power: number;        // kW
  voltage: number;      // V
  current: number;      // A
  temperature: number;  // °C
  energy: number;       // kWh 累计电量
  timestamp: string;
}

// =====================
// 充电桩实时监控 (Charger Monitor)
// =====================
export interface ChargerStatus {
  id: number;
  deviceId: number;
  deviceName: string;
  connectorStatus: ConnectorStatus;
  power: number;          // kW 实时功率
  voltage: number;        // V 实时电压
  current: number;        // A 实时电流
  temperature: number;    // °C 充电枪温度
  soc?: number | null;    // % 车辆电池SOC(0-100)，仅充电会话中有值
  energyTotal: number;    // kWh 累计电量
  sessionEnergy: number;  // kWh 当前会话电量
  sessionDuration: number; // 分钟 当前充电时长
  state: ChargingState;
  faultCode: string | null;
  faultMessage: string | null;
  lastHeartbeat: string;
  updatedAt: string;
}

// 充电桩实时趋势曲线（功率/电压/电流/SOC 历史）
export interface ChargerTrendPoint {
  timestamp: string;
  power: number;     // kW
  voltage: number;   // V
  current: number;   // A
  soc: number;       // %
}

export interface ChargerTrend {
  deviceId: number;
  points: ChargerTrendPoint[];
}

export type ChargerTrendMetric = 'power' | 'voltage' | 'current' | 'soc';

// 设备远程控制操作日志
export interface DeviceControlLog {
  id: number;
  deviceId: number;
  deviceName: string;
  command: DeviceControlCommand['command'];
  commandLabel: string;
  status: 'success' | 'failed';
  message: string;
  operator: string;
  createdAt: string;
}

export type ConnectorStatus = 'idle' | 'connected' | 'charging' | 'fault' | 'suspended';
export type ChargingState = 'idle' | 'preparing' | 'charging' | 'suspended' | 'finishing' | 'fault';

export interface ChargerFaultRecord {
  id: number;
  chargerId: number;
  deviceId: number;
  faultCode: string;
  faultMessage: string;
  level: AlarmLevel;
  occurredAt: string;
  clearedAt: string | null;
  clearedBy: string | null;
}

export interface ChargerMonitorSummary {
  totalChargers: number;
  chargingCount: number;
  idleCount: number;
  faultCount: number;
  totalPower: number;      // kW 总实时功率
  todayEnergy: number;     // kWh 今日充电量
  todaySessions: number;   // 今日充电次数
  avgPowerPerCharger: number; // kW 平均功率
}

// =====================
// 通知/消息 (Notification)
// =====================
export interface AppNotification {
  id: number;
  type: NotificationType;
  title: string;
  message: string;
  level: AlarmLevel;
  sourceId?: number;
  sourceType?: string;
  isRead: boolean;
  createdAt: string;
  readAt?: string;
}

export type NotificationType = 'alarm' | 'work_order' | 'system' | 'device' | 'revenue';

export interface DeviceControlCommand {
  deviceId: number;
  command: 'start' | 'stop' | 'restart' | 'reset';
}

export interface AlarmQuery {
  stationId?: number;
  level?: AlarmLevel;
  status?: AlarmStatus;
  page?: number;
  pageSize?: number;
}

export interface WorkOrderQuery {
  stationId?: number;
  status?: WorkOrderStatus;
  page?: number;
  pageSize?: number;
}

export interface CreateWorkOrderData {
  stationId: number;
  title: string;
  description: string;
  type: WorkOrderType;
  priority: WorkOrderPriority;
  alarmId?: number;
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