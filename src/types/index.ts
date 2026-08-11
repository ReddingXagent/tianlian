// =====================
// 设备 (Device)
// =====================
export interface Device {
  id: number;
  stationId: number;
  stationName?: string;
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

export type AlarmType =
  | 'device_fault'
  | 'power_anomaly'
  | 'communication_loss'
  | 'temperature_warning'
  | 'other';

export type AlarmLevel = 'info' | 'warning' | 'critical';

export type AlarmStatus = 'unhandled' | 'processing' | 'resolved';

// =====================
// 工单 (WorkOrder)
// =====================
export interface WorkOrder {
  id: string;
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
  solution?: string;
}

export type WorkOrderType =
  | 'repair'
  | 'inspection'
  | 'installation'
  | 'maintenance'
  | 'other';

export type WorkOrderPriority = 'low' | 'normal' | 'high' | 'urgent';

export type WorkOrderStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'cancelled';

// =====================
// 知识库 (KnowledgeBase)
// =====================
export interface KnowledgeArticle {
  id: number;
  title: string;
  summary: string;
  content: string;
  category: KnowledgeCategory;
  tags: string[];
  authorId: number;
  authorName: string;
  viewCount: number;
  createdAt: string;
  updatedAt: string;
}

export type KnowledgeCategory =
  | 'operation'
  | 'maintenance'
  | 'troubleshooting'
  | 'safety'
  | 'regulation'
  | 'other';

// =====================
// 扫码相关
// =====================
export interface ScanResult {
  type: 'device' | 'station' | 'unknown';
  id: number;
  code: string;
  name?: string;
  status?: DeviceStatus;
}

// =====================
// 设备监控
// =====================
export interface DeviceMetrics {
  deviceId: number;
  deviceName: string;
  temperature?: number;
  humidity?: number;
  voltage?: number;
  current?: number;
  power?: number;
  status: DeviceStatus;
  lastUpdated: string;
}

export interface MonitorSummary {
  totalDevices: number;
  onlineDevices: number;
  faultDevices: number;
  criticalAlarms: number;
}

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

export type UserRole =
  | 'admin'
  | 'station_master'
  | 'operator'
  | 'viewer';

// =====================
// 站点 (Station) — 运维侧只读引用
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

// =====================
// 认证
// =====================
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

// =====================
// 工作台统计
// =====================
export interface WorkbenchStats {
  pendingOrders: number;
  inProgressOrders: number;
  todayCompleted: number;
  unhandledAlarms: number;
  criticalAlarms: number;
}

// =====================
// 故障诊断
// =====================
export interface DiagnosisResult {
  faultCode: string;
  description: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  possibleCauses: string[];
  solutions: string[];
  relatedArticles?: KnowledgeArticle[];
  deviceType?: DeviceType;
}

// =====================
// 工单执行记录
// =====================
export interface WorkOrderRecord {
  id: number;
  orderId: string;
  action: WorkOrderAction;
  operatorId: number;
  operatorName: string;
  note: string;
  createdAt: string;
}

export type WorkOrderAction =
  | 'created'
  | 'accepted'
  | 'check_in'
  | 'executing'
  | 'completed'
  | 'cancelled'
  | 'reassigned';

// =====================
// 导航参数
// =====================
export type RootStackParamList = {
  Auth: undefined;
  Main: undefined;
  WorkOrderDetail: { orderId: string };
  WorkOrderCreate: undefined;
  WorkOrderTransfer: { orderId: string };
  ScanResult: { result: ScanResult };
  KnowledgeArticle: { articleId: number };
  Diagnosis: undefined;
  Knowledge: undefined;
  KnowledgeDetail: { articleId: number };
  InspectionDetail: { taskId: number };
};

export type AuthStackParamList = {
  Login: undefined;
};

export type MainTabParamList = {
  Workbench: undefined;
  WorkOrders: undefined;
  Inspection: undefined;
  Scan: undefined;
  Monitor: undefined;
  Dashboard: undefined;
  Profile: undefined;
};

// =====================
// 设备巡检 (Inspection)
// =====================
export interface InspectionTask {
  id: number;
  stationId: number;
  stationName: string;
  deviceId: number;
  deviceName: string;
  type: InspectionType;
  status: InspectionStatus;
  scheduledDate: string;
  completedDate?: string;
  assignedTo?: number;
  assignedName?: string;
  description: string;
  items: InspectionItem[];
  result?: InspectionResult;
  createdAt: string;
  updatedAt: string;
}

export type InspectionType = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'annual' | 'special';
export type InspectionStatus = 'pending' | 'in_progress' | 'completed' | 'overdue';

export interface InspectionItem {
  id: number;
  name: string;
  expected: string;
  result?: 'pass' | 'fail' | 'na';
  note?: string;
}

export interface InspectionResult {
  overall: 'pass' | 'partial' | 'fail';
  summary: string;
  operatorId: number;
  operatorName: string;
  completedAt: string;
  images?: string[];
}

// =====================
// 巡检计划/模板 (Inspection Plans/Templates — /inspection/*)
// =====================
export interface InspectionPlan {
  id: number;
  name: string;
  stationId: number;
  stationName?: string;
  deviceId?: number;
  deviceName?: string;
  type: InspectionType;
  status: InspectionStatus;
  scheduledDate: string;
  cycle?: string;
  assignedTo?: number;
  assignedName?: string;
  templateId?: number;
  description?: string;
  createdAt: string;
  updatedAt: string;
}

export interface InspectionTemplate {
  id: number;
  name: string;
  type: InspectionType;
  items: InspectionItem[];
  description?: string;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

// =====================
// 数据看板 (Dashboard)
// =====================
export interface DashboardStats {
  totalOrders: number;
  completedOrders: number;
  pendingOrders: number;
  avgCompletionHours: number;
  onTimeRate: number;
}

export interface DeviceHealthStats {
  total: number;
  online: number;
  offline: number;
  fault: number;
  maintenance: number;
  onlineRate: number;
}

export interface AlarmTrend {
  date: string;
  total: number;
  critical: number;
  warning: number;
  info: number;
}

export interface WorkOrderTrend {
  date: string;
  created: number;
  completed: number;
}

export interface DashboardData {
  stats: DashboardStats;
  deviceHealth: DeviceHealthStats;
  alarmTrends: AlarmTrend[];
  workOrderTrends: WorkOrderTrend[];
  topFaultDevices: {
    deviceId: number;
    deviceName: string;
    stationName: string;
    faultCount: number;
  }[];
}

// =====================
// 能源概览 (Energy Summary)
// =====================
export interface EnergySummary {
  period: string;
  days: number;
  pvGeneration: number;
  chargingAmount: number;
  dischargeAmount: number;
  pvRevenue: number;
  chargingRevenue: number;
  dischargeRevenue: number;
  totalRevenue: number;
  yoy: {
    pvGenerationYoy: number;
    chargingAmountYoy: number;
    dischargeAmountYoy: number;
    totalRevenueYoy: number;
  };
  priceInfo: {
    feedInTariff: number;
    chargingPrice: number;
    dischargePrice: number;
  };
}

// =====================
// 能源趋势 (Energy Trend)
// =====================
export interface EnergyTrendItem {
  date: string;
  pvGeneration: number;
  chargingAmount: number;
  dischargeAmount: number;
  pvRevenue: number;
  chargingRevenue: number;
  dischargeRevenue: number;
  totalRevenue: number;
}

// =====================
// 报告概览 (Report Summary)
// =====================
export interface ReportSummary {
  periodDays: number;
  overview: {
    totalDevices: number;
    onlineDevices: number;
    offlineDevices: number;
    faultDevices: number;
    maintenanceDevices: number;
    onlineRate: number;
    totalStations: number;
    totalWorkorders: number;
    completedWorkorders: number;
    completionRate: number;
    totalAlarms: number;
    activeAlarms: number;
  };
  stationHealth: {
    distribution: {
      normal: number;
      warning: number;
      critical: number;
      offline: number;
    };
    healthyRate: number;
  };
  teamPerformance: {
    engineers: unknown[];
    totalEngineers: number;
    topEngineers: unknown[];
  };
}

// =====================
// 用户详情 (User Detail — from /users/{id})
// =====================
export interface UserDetail {
  id: number;
  username: string;
  realName: string;
  phone: string | null;
  role: string;
  level: string;
  teamId: number | null;
  teamName: string | null;
  status: string;
  lastLogin: string;
  createdAt: string;
  updatedAt: string;
}

// =====================
// 当前用户信息 (Auth Me — from /auth/me)
// =====================
export interface AuthMe {
  id: number;
  username: string;
  realName: string;
  role: string;
  permissions: string[];
  teamType: string | null;
  teamId: number | null;
}

// =====================
// 设备健康度 (Device Health — from /devices/{id}/health)
// =====================
export interface DeviceHealth {
  deviceId: number;
  deviceCode: string;
  deviceName: string;
  deviceType: string;
  healthScore: number;
  healthStatus: string;
  healthStatusDisplay: string;
  dimensionScores: Record<string, number>;
  checkedAt: string;
  lastHealthCheck: string | null;
}

// =====================
// 设备报告 (Device Report — from /reports/devices)
// =====================
export interface DeviceReport {
  periodDays: number;
  totalDevices: number;
  typeDistribution: Record<string, number>;
  statusDistribution: Record<string, number>;
  stationDistribution: {
    stationId: number;
    stationName: string;
    deviceCount: number;
  }[];
}

// =====================
// 告警报告 (Alarm Report — from /reports/alarms)
// =====================
export interface AlarmReport {
  periodDays: number;
  totalAlarms: number;
  levelDistribution: Record<string, number>;
  typeDistribution: Record<string, number>;
  statusDistribution: Record<string, number>;
  resolvedRate: number;
  activeAlarms: number;
  topFaultDevices: {
    deviceId: number;
    deviceName: string;
    alarmCount: number;
  }[];
  dailyTrend: {
    date: string;
    count: number;
  }[];
}

// =====================
// 角色 (Role — from /roles)
// =====================
export interface Role {
  id: number;
  name: string;
  displayName: string;
  description: string;
  isSystem: boolean;
  permissions: string[];
}

// =====================
// 权限项 (Permission — from /permissions)
// =====================
export interface Permission {
  name: string;
  resource: string;
  action: string;
  label: string;
  labelShort: string;
}

// =====================
// 告警规则 (Alarm Rule — from /alarm-rules)
// =====================
export interface AlarmRule {
  id: number;
  name: string;
  deviceType: string;
  metric: string;
  condition: string;
  threshold: number;
  level: AlarmLevel;
  enabled: boolean;
  description: string;
  createdAt: string;
  updatedAt: string;
}

// =====================
// 通知规则 (Notification Rule — from /notification-rules)
// =====================
export interface NotificationRule {
  id: number;
  name: string;
  event: string;
  channels: string[];
  recipients: string[];
  enabled: boolean;
  template: string;
  createdAt: string;
  updatedAt: string;
}

// =====================
// 通知模板 (Notification Template — from /notifications/templates)
// =====================
export interface NotificationTemplate {
  id: number;
  name: string;
  channel: string;
  subject: string;
  body: string;
  variables: string[];
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

// =====================
// 工单报告 (WorkOrderReport — from /reports/workorders)
// =====================
export interface WorkOrderReport {
  periodDays: number;
  totalWorkorders: number;
  typeDistribution: Record<string, number>;
  levelDistribution: Record<string, number>;
  statusDistribution: Record<string, number>;
  completionRate: number;
  efficiency: {
    avgResponseHours: number;
    avgCompletionHours: number;
  };
  engineerPerformance: {
    engineerId: number;
    engineerName: string;
    completedCount: number;
    avgCompletionHours: number;
  }[];
}

// =====================
// 充电桩配置 (ChargerConfig — from /devices/{id}/config)
// ====================
export interface ChargerConfig {
  deviceId: number;
  voltageLimit: number;
  currentLimit: number;
  maxPower: number;
  chargeMode: string;
  overloadProtection: boolean;
  timePeriods: {
    startTime: string;
    endTime: string;
    powerLimit: number;
  }[];
  createdAt: string | null;
  updatedAt: string | null;
}

// =====================
// 定价规则 (PricingRule — from /pricing)
// =====================
export interface PricingRule {
  id: number;
  name: string;
  periodType: string;
  startTime: string;
  endTime: string;
  energyPrice?: number;
  servicePrice?: number;
  powerLimit?: number;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

// =====================
// 备件 (SparePart — from /spare-parts)
// =====================
export interface SparePart {
  id: number;
  name: string;
  model: string;
  manufacturer: string;
  stockQty: number;
  unit: string;
  price: number;
  warehouse: string;
  location: string;
  safetyStock: number;
  status: string;
  createdAt: string;
  updatedAt: string;
}

// =====================
// 效率报告 (EfficiencyReport — from /reports/efficiency)
// ====================
export interface EfficiencyReport {
  items: EfficiencyItem[];
  total: number;
  page: number;
  pageSize: number;
  alerts: {
    abnormalLowEfficiency: {
      count: number;
      threshold: string;
      items: EfficiencyItem[];
    };
  };
}

export interface EfficiencyItem {
  stationId?: number;
  stationName?: string;
  deviceId?: number;
  deviceName?: string;
  efficiency?: number;
  uptime?: number;
  utilization?: number;
}

// =====================
// 工程师 (Engineer — from /engineers)
// ====================
export interface Engineer {
  id: number;
  username: string;
  name: string;
  phone: string | null;
  level: 'junior' | 'senior' | 'expert';
  teamId: number | null;
  status: 'active' | 'inactive' | 'on_leave';
  role: string;
  createdAt: string;
  updatedAt: string;
}

// =====================
// Webhook (from /webhooks)
// ====================
export interface Webhook {
  id: number;
  name: string;
  url: string;
  events: string[];
  secret: string | null;
  enabled: boolean;
  lastTriggeredAt: string | null;
  lastResponseStatus: number | null;
  createdAt: string;
  updatedAt: string;
}

// =====================
// 自愈规则 (HealingRule — from /healing/rules)
// ====================
export interface HealingRule {
  id: number;
  name: string;
  deviceType: string;
  faultCode: string;
  action: string;
  conditions: Record<string, unknown>;
  enabled: boolean;
  successRate: number;
  lastTriggeredAt: string | null;
  createdAt: string;
  updatedAt: string;
}

// =====================
// 安全审计日志 (SecurityLog — from /security/logs)
// =====================
export interface SecurityLog {
  id: number;
  timestamp: string;
  userId: number;
  username: string;
  userRole: string | null;
  action: string;
  module: string;
  targetId: string;
  targetDesc: string;
  detail: string | null;
  oldValue: string | null;
  newValue: string | null;
  ipAddress: string | null;
  userAgent: string | null;
  result: 'success' | 'failure';
  errorMsg: string | null;
}

// =====================
// 安全策略 (SecurityPolicy — from /security/policies)
// =====================
export interface SecurityPolicy {
  id: number;
  policyKey: string;
  policyConfig: Record<string, unknown>;
  description: string;
  status: 'active' | 'inactive';
  createdAt: string;
  updatedAt: string;
}

// =====================
// 知识库文章 (KnowledgeArticleItem — from /knowledge/articles API)
// =====================
export interface KnowledgeArticleItem {
  id: number;
  title: string;
  content: string;
  summary: string;
  categoryId: number;
  categoryName?: string;
  tags: string[];
  author: string;
  viewCount: number;
  status: 'published' | 'draft' | 'archived';
  createdAt: string;
  updatedAt: string;
}

// =====================
// 知识库分类 (KnowledgeCategoryItem — from /knowledge/categories API)
// =====================
export interface KnowledgeCategoryItem {
  id: number;
  name: string;
  description: string;
  articleCount: number;
  createdAt: string;
  updatedAt: string;
}

// =====================
// API密钥 (ApiKey — from /api-keys)
// ====================
export interface ApiKey {
  id: number;
  name: string;
  keyPrefix: string;
  permissions: string[];
  lastUsedAt: string | null;
  expiresAt: string | null;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}