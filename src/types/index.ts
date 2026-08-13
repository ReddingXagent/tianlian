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
// 工单统计 (WorkOrderStats)
// =====================
export interface WorkOrderStats {
  total: number;
  statusDistribution: Record<string, number>;
  levelDistribution: Record<string, number>;
  typeDistribution: Record<string, number>;
  groups: Record<string, number>;
}

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

/** GET /monitor/realtime — 实时监控总览 */
export interface RealtimeOverview {
  totalPower: number;
  powerTrend: number;
  todayGeneration: number;
  todayConsumption: number;
  gridImport: number;
  gridExport: number;
  efficiency: number;
  updateTime: string;
  devices: RealtimeDeviceStatus[];
}

export interface RealtimeDeviceStatus {
  id: number;
  name: string;
  type: string;
  power: number;
  status: string;
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
export interface StationBranding {
  operatorName: string;
  logoUrl: string;
  servicePhone: string;
  themeColor: string;
  source: string;
}

export interface Station {
  id: number;
  name: string;
  code: string;
  province: string;
  city: string;
  district: string;
  address: string;
  lat: number;
  lon: number;
  status: StationStatus;
  stationType: string | null;
  operatorId: number | null;
  operatorName: string | null;
  teamId: number | null;
  totalPower: number;
  totalDevices: number;
  gunCount: number;
  venueType: string | null;
  totalCost: number | null;
  parkingSpots: number | null;
  healthScore: number;
  branding: StationBranding | null;
  createdAt: string;
  updatedAt: string | null;
}

export type StationStatus = 'online' | 'offline' | 'maintenance' | 'normal';

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

/** POST /auth/refresh — 刷新令牌响应 */
export interface RefreshTokenResponse {
  accessToken: string;
  tokenType: string;
  expiresIn: number;
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

// 设备健康摘要 (Device Health Summary — from /devices/health, 全局设备健康列表)
export interface DeviceHealthSummary {
  id: number;
  code: string;
  name: string;
  type: string;
  healthScore: number;
  status: string;
}

// 设备健康历史记录 (Device Health History — from /devices/{id}/health/history)
export interface DeviceHealthHistory {
  deviceId: number;
  healthScore: number;
  healthStatus: string;
  healthStatusDisplay: string;
  dimensionScores: Record<string, number>;
  checkedAt: string;
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
// 权限树节点 (Permission Tree Node — from /roles/tree)
// =====================
export interface PermissionTreeNode {
  key: string;
  title: string;
  resource: string;
  name?: string;
  action?: string;
  label?: string;
  isLeaf?: boolean;
  children?: PermissionTreeNode[];
}

// =====================
// 权限项 (Permission — from /permissions)
// ====================
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
// 通知统计 (NotificationStats — from /notifications/stats)
// =====================
export interface NotificationStats {
  totalTemplates: number;
  totalMessages: number;
  sentToday: number;
  failedCount: number;
  channelDistribution: Record<string, number>;
}

// =====================
// 未读通知计数 (UnreadCount — from /notifications/unread-count)
// =====================
export interface UnreadCount {
  unreadCount: number;
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
// 充电订单 (ChargingOrder — from /charging-orders)
// =====================
export interface ChargingOrder {
  id: number;
  orderNo: string;
  stationId: number;
  deviceId: number;
  userId: number;
  userType: string | null;
  vehicleId: string | null;
  plateNumber: string | null;
  startTime: string | null;
  endTime: string | null;
  durationMinutes: number;
  startSoc: number | null;
  endSoc: number | null;
  startMeter: number | null;
  endMeter: number | null;
  stopReason: string | null;
  chargedKwh: number;
  electricityFee: number;
  serviceFee: number;
  parkingFee: number;
  idlePenalty: number;
  reservationFee: number;
  totalAmount: number;
  discountAmount: number;
  paidAmount: number;
  paymentStatus: ChargingPaymentStatus;
  orderStatus: ChargingOrderStatus;
  paymentMethod: string | null;
  remark: string | null;
  createdAt: string;
  updatedAt: string;
}

export type ChargingPaymentStatus = 'unpaid' | 'paid' | 'refunded' | 'refunding';

export type ChargingOrderStatus =
  | 'pending'
  | 'charging'
  | 'completed'
  | 'cancelled'
  | 'faulted';

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
  partName: string;
  partModel: string | null;
  totalQuantity: number;
  availableQuantity: number;
  warehouse: string;
  createdAt: string;
}

export interface SparePartCreate {
  partName: string;
  partModel?: string | null;
  totalQuantity?: number;
  availableQuantity?: number;
  warehouse?: string;
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
  description: string;
  alarmPattern: Record<string, unknown>;
  runbookTemplate: string | null;
  autoApprove: boolean;
  maxRetries: number;
  cooldownMinutes: number;
  priority: number;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

// HealingRule 创建请求
export interface HealingRuleCreate {
  name: string;
  alarmPattern: Record<string, unknown>;
  description?: string;
  runbookTemplate?: string | null;
  autoApprove?: boolean;
  maxRetries?: number;
  cooldownMinutes?: number;
  priority?: number;
  enabled?: boolean;
}

// ====================
// 自愈执行记录 (HealingExecution — from /healing/executions)
// ====================
export interface HealingExecution {
  id: number;
  ruleId: number;
  ruleName: string;
  deviceId: number;
  deviceName: string;
  stationId: number;
  stationName: string;
  triggeredAt: string;
  status: string; // success | failed | pending | running
  actionTaken: string;
  result: string | null;
  duration: number; // seconds
  errorMessage: string | null;
  createdAt: string;
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

// =====================
// 营收分析 (RevenueAnalytics — from /analytics/revenue)
// =====================
export interface RevenueAnalyticsSummary {
  totalRevenue: number;
  totalKwh: number;
  totalOrders: number;
  avgPerOrder: number;
}

export interface RevenueAnalytics {
  summary: RevenueAnalyticsSummary;
  trend: unknown[];
}

// =====================
// 安全威胁 (SecurityThreat — from /security/threats)
// =====================
export interface SecurityThreat {
  id: number;
  type: string;
  sourceIp: string;
  target: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'blocked' | 'active' | 'resolved';
  timestamp: string;
}

// =====================
// 设备健康度排名 (DeviceHealthRanking — from /health/devices)
// =====================
export interface DeviceHealthOverall {
  totalDevices: number;
  healthyCount: number;
  warningCount: number;
  criticalCount: number;
  pendingEval: number;
  overallScore: number;
}

export interface DeviceHealthRankingItem {
  id: number;
  deviceName: string;
  code: string;
  type: string;
  stationName: string;
  score: number;
  status: string;
}

export interface DeviceHealthRanking {
  overall: DeviceHealthOverall;
  rankings: {
    best: DeviceHealthRankingItem[];
    worst: DeviceHealthRankingItem[];
  };
}

// =====================
// 网关 (Gateway — from /gateways)
// =====================
export interface Gateway {
  id: number;
  sn: string;
  name: string;
  model: string | null;
  manufacturer: string | null;
  stationId: number | null;
  status: 'online' | 'offline' | 'warning';
  firmwareVersion: string | null;
  lastOnline: string | null;
  ipAddress: string | null;
  macAddress: string | null;
  location: string | null;
  healthScore: number;
  createdAt: string;
  updatedAt: string;
  notes: string | null;
}

// 网关固件包 (from /gateways/firmware)
export interface GatewayFirmware {
  id: number;
  version: string;
  fileId: string | null;
  fileSize: number | null;
  releaseNotes: string | null;
  status: string | null;
  createdAt: string;
  updatedAt: string | null;
}

// 网关状态统计 (from /gateways/status)
export interface GatewayStatus {
  onlineCount: number;
  offlineCount: number;
  maintenanceCount: number;
  faultCount: number;
  total: number;
}

// =====================
// VPP 虚拟电厂资源 (from /vpp/resources)
// =====================
export type VppResourceType = 'pv' | 'battery' | 'ev' | 'load';

export interface VppResource {
  resourceId: string;
  resourceType: VppResourceType;
  stationId: string;
  ratedPowerKw: number;
  currentPowerKw: number;
  availablePowerKw: number;
  soc: number | null;
  efficiency: number;
  priority: number;
  costPerKwh: number;
}

// =====================
// VPP 调度计划 (from POST /vpp/dispatch)
// =====================
export type VppDispatchMode = 'peak_shaving' | 'valley_filling' | 'frequency_regulation' | 'demand_response';

export interface VppDispatchCommand {
  resourceId: string;
  stationId: string;
  resourceType: VppResourceType;
  targetPowerKw: number;
  durationMin: number;
  priority: number;
  estimatedRevenue: number;
  estimatedCost: number;
  dispatchMode: VppDispatchMode;
}

export interface VppDispatchPlan {
  planId: string;
  mode: VppDispatchMode;
  trigger: string;
  stationsInvolved: string[];
  totalDispatchKw: number;
  estimatedRevenue: number;
  estimatedCost: number;
  netProfit: number;
  commands: VppDispatchCommand[];
  createdAt: string;
}

export interface VppDispatchHistory {
  planId: string;
  mode: VppDispatchMode;
  trigger: string;
  stationsInvolved: string[];
  totalDispatchKw: number;
  estimatedRevenue: number;
  estimatedCost: number;
  netProfit: number;
  commandsCount: number;
  createdAt: string;
  executed: boolean;
}

// =====================
// 租户 (Tenant — from /tenants)
// =====================
export interface Tenant {
  id: number;
  name: string;
  code: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}

// =====================
// AI对话 (Chat — from POST /chat)
// =====================
export interface ChatSource {
  title: string;
  url: string;
  type: string;
}

export interface ChatAction {
  type: string;
  label: string;
  target: string;
}

export interface ChatUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface ChatResponse {
  answer: string;
  confidence: number;
  sources: ChatSource[];
  actions: ChatAction[];
  needsHuman: boolean;
  usage: ChatUsage | null;
}

// =====================
// 主动通知发送 (from POST /notifications/send)
// =====================
export interface NotificationSendResult {
  success: boolean;
  messageId: string | null;
  channel: string | null;
  sentAt: string | null;
}

// =====================
// 系统健康检查 (from GET /readyz + GET /livez)
// =====================
export type HealthStatus = 'ok' | 'degraded' | 'error';

export interface DatabaseHealthCheck {
  status: HealthStatus;
  poolSize: number;
  activeConnections: number;
  idleConnections: number;
  waitingConnections: number;
  dbType: string;
}

export interface RedisHealthCheck {
  status: HealthStatus;
  version: string;
  usedMemoryHuman: string;
  connectedClients: number;
}

export interface MqttHealthCheck {
  status: HealthStatus;
  host: string;
  port: number;
  error: string | null;
}

export interface FilesystemPathInfo {
  totalGb: number;
  freeGb: number;
  freePct: number;
}

export interface FilesystemHealthCheck {
  paths: Record<string, FilesystemPathInfo>;
}

export interface SystemHealthChecks {
  database: DatabaseHealthCheck;
  redis: RedisHealthCheck;
  mqttBroker: MqttHealthCheck;
  filesystem: FilesystemHealthCheck;
  [key: string]: unknown;
}

export interface SystemHealth {
  status: HealthStatus;
  checks: SystemHealthChecks;
  uptimeSeconds: number;
  unhealthyChecks: string[];
}

export interface LivenessProbe {
  status: string;
  uptimeSeconds: number;
}

// =====================
// Runbook 模板步骤 (from GET /runbooks/templates/{id})
// ====================
export interface RunbookStep {
  stepId: number;
  actionType: string;
  description: string;
  command: string;
  params: Record<string, unknown>;
  riskLevel: string;
  timeoutSec: number;
  rollbackCommand: string;
  preCheck: string;
  postCheck: string;
  autoExecute: boolean;
  status: string;
  result: string;
  durationMs: number;
  errorMessage: string;
}

// =====================
// Runbook 模板摘要 (from GET /runbooks/templates list)
// =====================
export interface RunbookTemplateSummary {
  id: number;
  name: string;
  category: string;
  alarmType: string;
  description: string;
  stepCount: number;
  autoSteps: number;
  manualSteps: number;
  status: string;
  version: number;
  createdAt: string;
  updatedAt: string;
}

// =====================
// Runbook 模板详情 (from GET /runbooks/templates/{id})
// =====================
export interface RunbookTemplateDetail extends RunbookTemplateSummary {
  steps: RunbookStep[];
}

// =====================
// 缓存统计 (from GET /cache/stats)
// =====================
export interface CacheStats {
  hitRate: number;
  totalKeys: number;
  usedMemoryMb: number;
  backend: string;
}

// =====================
// 车队司机 (from GET /fleet/drivers)
// =====================
export interface FleetDriver {
  id: number;
  name: string;
  phone: string | null;
  licenseNumber: string | null;
  vehiclePlate: string | null;
  status: string;
  createdAt: string | null;
  updatedAt: string | null;
}