/**
 * 天链V3 - TypeScript 类型定义
 * 所有业务实体的TypeScript接口定义
 */

// ==================== 通用API响应 ====================
export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
  timestamp: number;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export interface PaginatedResponse<T> extends ApiResponse<PaginatedData<T>> {}

// ==================== 用户相关 ====================
export interface User {
  id: number;
  username: string;
  real_name: string;
  phone?: string;
  email?: string;
  role: UserRole;
  status: string;
  team_id?: number;
  created_at: string;
  updated_at: string;
  avatar?: string;
  department?: string;
}

export type UserRole = 'ADMIN' | 'ENGINEER' | 'TECHNICIAN' | 'OPERATOR' | 'VIEWER';

export interface LoginResponse {
  token: string;
  user: UserInfo;
  expires_in?: number;
}

export interface UserInfo {
  id: string | number;
  username: string;
  real_name: string;
  role: string;
  avatar?: string;
  permissions?: string[];
  team_id?: number;
  email?: string;
}

export interface UserCreateRequest {
  username: string;
  password: string;
  real_name: string;
  phone?: string;
  email?: string;
  role: UserRole;
  team_id?: number;
}

export interface UserUpdateRequest {
  real_name?: string;
  phone?: string;
  email?: string;
  role?: UserRole;
  status?: string;
  team_id?: number;
}

// ==================== 站点 ====================
export interface Station {
  id: number;
  name: string;
  code: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  status: string;
  capacity_kw?: number;
  operator_id?: number;
  device_count?: number;
  created_at: string;
  updated_at?: string;
  contact_name?: string;
  contact_phone?: string;
  region?: string;
  province?: string;
  city?: string;
  district?: string;
}

export interface StationCreateRequest {
  name: string;
  code: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  capacity_kw?: number;
  operator_id?: number;
  contact_name?: string;
  contact_phone?: string;
  region?: string;
  province?: string;
  city?: string;
  district?: string;
  total_power?: number;
  gun_count?: number;
  status?: string;
  contact_person?: string;
  description?: string;
  pv_capacity?: number;
  ess_capacity?: number;
}

export interface StationUpdateRequest {
  name?: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  status?: string;
  capacity_kw?: number;
  contact_name?: string;
  contact_phone?: string;
}

export type StationStatus = 'online' | 'offline' | 'maintenance' | 'planned' | 'decommissioned';

// ==================== C端场站公开视图 (契约 §1, GET /business/stations) ====================
// 与管理侧 Station 的区别: 不含 team_id/total_devices/total_cost/health_score 等运维内部字段;
// 携带 branding (运营商品牌)。列表用轻量 branding, 详情用全量。
export interface StationBranding {
  source?: string;            // tenant | default
  operator_name?: string;
  theme_color?: string;
  logo_url?: string;          // 仅详情返回
  service_phone?: string;     // 仅详情返回
}

export interface BusinessStation {
  id: number;
  name: string;
  tenant_id?: number;
  code?: string;
  province?: string;
  city?: string;
  district?: string;
  address?: string;
  lat?: number | null;
  lon?: number | null;
  operator_name?: string;
  total_power?: number | null;
  gun_count?: number | null;
  parking_spots?: number | null;
  station_type?: string;
  venue_type?: string;
  status: string;
  branding?: StationBranding;
  distance_km?: number;       // 仅 nearby 模式 (lat+lon 同传时) 携带
}

// /business/stations 列表查询参数。lat+lon 同传进入 nearby 模式 (按距离过滤排序 + distance_km)。
export interface BusinessStationListParams {
  lat?: number;
  lon?: number;
  radius?: number;            // 附近半径(km), 需与 lat/lon 同传
  keyword?: string;           // 名称/地址关键词
  city?: string;              // 城市过滤
  page?: number;
  page_size?: number;
}

// ==================== 设备 ====================
export interface Device {
  id: number;
  name: string;
  sn: string;
  type: DeviceType;
  model?: string;
  status: DeviceStatus;
  station_id: number;
  ip_address?: string;
  firmware_version?: string;
  health_score?: number;
  last_online?: string;
  created_at: string;
  updated_at?: string;
  manufacturer?: string;
  installed_date?: string;
  warranty_expiry?: string;
  power_rating?: number;
  voltage_rating?: number;
  current_rating?: number;
}

export type DeviceType = 'solar' | 'storage' | 'charger' | 'inverter' | 'transformer' | 'meter' | 'sensor' | 'controller' | 'gateway';

export type DeviceStatus = 'online' | 'offline' | 'maintenance' | 'fault' | 'idle' | 'standby';

export interface DeviceCreateRequest {
  name: string;
  sn: string;
  type: DeviceType;
  station_id: number;
  model?: string;
  ip_address?: string;
  manufacturer?: string;
  power_rating?: number;
  voltage_rating?: number;
}

export interface DeviceUpdateRequest {
  name?: string;
  status?: DeviceStatus;
  ip_address?: string;
  firmware_version?: string;
  health_score?: number;
  model?: string;
  manufacturer?: string;
}

// ==================== 告警 ====================
export interface Alarm {
  id: number;
  title: string;
  description?: string;
  level: AlarmLevel;
  status: AlarmStatus;
  station_id?: number;
  device_id?: number;
  handler_id?: number;
  created_at: string;
  updated_at?: string;
  resolved_at?: string;
  acknowledged_at?: string;
  station_name?: string;
  device_name?: string;
  handler_name?: string;
  metadata?: Record<string, any>;
}

export type AlarmLevel = 'critical' | 'major' | 'minor' | 'info';

export type AlarmStatus = 'active' | 'acknowledged' | 'resolved' | 'suppressed';

export interface AlarmCreateRequest {
  title: string;
  description?: string;
  level: AlarmLevel;
  station_id?: number;
  device_id?: number;
  metadata?: Record<string, any>;
}

export interface AlarmUpdateRequest {
  status?: AlarmStatus;
  handler_id?: number;
  description?: string;
  metadata?: Record<string, any>;
}

// ==================== 工单 ====================
export interface WorkOrder {
  id: number;
  title: string;
  description?: string;
  type: WorkOrderType;
  status: WorkOrderStatus;
  priority: WorkOrderPriority;
  creator_id: number;
  assignee_id?: number;
  station_id?: number;
  device_id?: number;
  created_at: string;
  updated_at?: string;
  completed_at?: string;
  closed_at?: string;
  estimated_hours?: number;
  actual_hours?: number;
  cost?: number;
  attachments?: string[];
  creator_name?: string;
  assignee_name?: string;
  station_name?: string;
  device_name?: string;
}

export type WorkOrderType = 'repair' | 'maintenance' | 'inspection' | 'emergency' | 'upgrade' | 'calibration';

export type WorkOrderStatus = 'pending' | 'in_progress' | 'completed' | 'closed' | 'cancelled';

export type WorkOrderPriority = 'urgent' | 'high' | 'medium' | 'low';

export interface WorkOrderCreateRequest {
  title: string;
  description?: string;
  type: WorkOrderType;
  priority?: WorkOrderPriority;
  station_id?: number;
  device_id?: number;
  assignee_id?: number;
  estimated_hours?: number;
  attachments?: string[];
}

export interface WorkOrderUpdateRequest {
  title?: string;
  description?: string;
  status?: WorkOrderStatus;
  priority?: WorkOrderPriority;
  assignee_id?: number;
  actual_hours?: number;
  cost?: number;
  attachments?: string[];
}

// ==================== 统计 ====================
export interface StatsOverview {
  stations: {
    total: number;
    online: number;
    offline: number;
    maintenance: number;
  };
  devices: {
    total: number;
    online: number;
    fault: number;
    maintenance: number;
    online_rate: number;
  };
  health: {
    average: number;
    good: number;
    warning: number;
    critical: number;
  };
  alarms: {
    active: number;
    critical: number;
    major: number;
    minor: number;
  };
  workorders: {
    pending: number;
    in_progress: number;
    completed_today: number;
    overdue: number;
  };
}

export interface DailyStats {
  date: string;
  device_count: number;
  alarm_count: number;
  workorder_count: number;
  health_score: number;
  energy_generated?: number;
  energy_consumed?: number;
}

export interface StationStats {
  station_id: number;
  station_name: string;
  device_count: number;
  online_devices: number;
  alarm_count: number;
  health_score: number;
  energy_generated_today?: number;
}

// ==================== 网关 ====================
export interface Gateway {
  id: number;
  sn: string;
  name: string;
  model?: string;
  status: string;
  firmware_version?: string;
  health_score?: number;
  ip_address?: string;
  last_online?: string;
  station_id?: number;
  created_at: string;
  updated_at?: string;
  protocol?: string;
  connection_type?: string;
  data_interval?: number;
  last_data_received?: string;
  battery_level?: number;
  signal_strength?: number;
}

export interface GatewayCreateRequest {
  sn: string;
  name: string;
  station_id?: number;
  model?: string;
  ip_address?: string;
  protocol?: string;
  connection_type?: string;
}

export interface GatewayUpdateRequest {
  name?: string;
  status?: string;
  ip_address?: string;
  firmware_version?: string;
  health_score?: number;
}

// ==================== 运维团队（平台管理） ====================
export interface Tenant {
  id: number;
  name: string;
  code: string;
  contact: string;
  phone?: string;
  email?: string;
  address?: string;
  status: TenantStatus;
  station_count: number;
  device_count: number;
  member_count: number;
  max_stations: number;
  max_devices: number;
  expired_at: string;
  storage_used: string;
  api_calls: number;
  created_at: string;
  updated_at?: string;
  logo_url?: string;
  website?: string;
  industry?: string;
  contract_start?: string;
  contract_end?: string;
}

export type TenantStatus = 'active' | 'trial' | 'expired' | 'disabled' | 'suspended';

export interface TenantCreateRequest {
  name: string;
  code: string;
  contact: string;
  phone?: string;
  email?: string;
  address?: string;
  max_stations?: number;
  max_devices?: number;
  contract_start?: string;
  contract_end?: string;
}

export interface TenantUpdateRequest {
  name?: string;
  contact?: string;
  phone?: string;
  email?: string;
  address?: string;
  status?: TenantStatus;
  max_stations?: number;
  max_devices?: number;
  contract_end?: string;
  logo_url?: string;
}

// ==================== 知识库 ====================
export interface KnowledgeArticle {
  id: number;
  title: string;
  content?: string;
  category?: string;
  tags?: string[];
  status: string;
  author_id?: number;
  view_count?: number;
  created_at: string;
  updated_at?: string;
  published_at?: string;
  author_name?: string;
  attachment_urls?: string[];
  related_articles?: number[];
  version?: number;
}

export type ArticleCategory = 'operation' | 'maintenance' | 'troubleshooting' | 'safety' | 'training' | 'faq';

export type ArticleStatus = 'draft' | 'published' | 'archived';

export interface ArticleCreateRequest {
  title: string;
  content: string;
  category?: string;
  tags?: string[];
  status?: string;
  attachment_urls?: string[];
  related_articles?: number[];
}

export interface ArticleUpdateRequest {
  title?: string;
  content?: string;
  category?: string;
  tags?: string[];
  status?: string;
  view_count?: number;
  attachment_urls?: string[];
  related_articles?: number[];
}

// ==================== 团队 ====================
export interface Team {
  id: number;
  name: string;
  code?: string;
  leader_id?: number;
  manager_name?: string;
  description?: string;
  member_count?: number;
  station_count?: number;
  device_count?: number;
  workorder_count?: number;
  alarm_count?: number;
  status: string;
  created_at: string;
  updated_at?: string;
  members?: User[];
}

export interface TeamMember {
  user_id: number;
  id?: number;
  real_name?: string;
  username?: string;
  role: string;
  status?: string;
  joined_at?: string;
}

// ==================== 排班 ====================
export interface OnCallRule {
  id: number;
  name: string;
  team_id: number;
  schedule_type: string;
  shift_duration_hours: number;
  overlap_minutes?: number;
  rotation_order: number[];
  escalation_level?: number;
  escalation_timeout_minutes?: number;
  auto_assign_workorders?: boolean;
  enabled: boolean;
  current_oncall?: { name: string };
  total_shifts?: number;
  upcoming_shifts?: number;
  notify_methods?: string[];
}

export interface OnCallShift {
  id: number;
  rule_id?: number;
  rule_name?: string;
  user_id: number;
  team_id?: number;
  start_time: string;
  end_time: string;
  status: string;
  user?: { name: string };
  backup_user?: { name: string };
  handover_completed?: boolean;
}

export interface OnCallLog {
  id: number;
  shift_id: number;
  user_id: number;
  event_type: string;
  content: string;
  severity?: string;
  alarm_id?: number;
  workorder_id?: string;
  created_at: string;
}

export interface OnCallStats {
  shifts: {
    total: number;
    completed: number;
    missed: number;
    completion_rate: number;
  };
  handover: {
    completed: number;
    rate: number;
  };
  logs: {
    total: number;
    by_event_type: Record<string, number>;
  };
  by_user: Array<{ user_id: number; name: string; shift_count: number }>;
}

export interface CurrentShiftInfo {
  shift_id: number;
  rule_name: string;
  primary?: { name: string };
  backup?: { name: string };
  remaining_hours: number;
  handover_completed: boolean;
}

// ==================== 巡检 ====================
export interface Inspection {
  id: number;
  title: string;
  type: string;
  status: string;
  station_id?: number;
  assignee_id?: number;
  scheduled_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface InspectionTask {
  id: number;
  name: string;
  plan_id?: number;
  plan_name?: string;
  station_id?: number;
  station_name?: string;
  assignee?: string;
  assignee_id?: number;
  status: string;
  total_items: number;
  completed_items: number;
  progress: number;
  scheduled_date?: string;
  actual_date?: string;
  description?: string;
  remark?: string;
  result?: any;
  created_at?: string;
  updated_at?: string;
}

export interface InspectionPlan {
  id: number;
  name: string;
  cycle: string;
  target: string;
  assignee?: string;
  assignee_id?: number;
  team_id?: number;
  status: string;
  next_execute?: string;
  last_execute?: string;
  description?: string;
  task_count: number;
  created_at?: string;
  updated_at?: string;
}

// ==================== 网关子类型 ====================
export interface SNCode {
  id: number;
  sn: string;
  model?: string;
  status: string;
  batch_no?: string;
  gateway_id?: number;
  generated_at?: string;
}

export interface Firmware {
  id: number;
  version: string;
  model?: string;
  status: string;
  file_size?: number;
  release_date?: string;
}

export interface UpgradeTask {
  id: number;
  gateway_id: number;
  firmware_id: number;
  status: string;
  progress?: number;
  created_at?: string;
}

// ==================== 设备协议 ====================
export interface DeviceProtocol {
  id: number;
  name: string;
  type: string;
  version: string;
  models?: string;
  status: string;
  data_points?: number;
  description?: string;
}

// ==================== 菜单 ====================
export type EntryType = 'platform' | 'ops';

export interface MenuItem {
  id: string;
  title: string;
  icon?: string;
  path?: string;
  children?: MenuItem[];
  permission?: string;
  order?: number;
  visible?: boolean;
  type?: 'item' | 'group' | 'divider';
}

// ==================== 扫码相关 ====================
export interface ScanResult {
  success: boolean;
  device_id: number;
  device_sn: string;
  device_name: string;
  device_type: string;
  device_status: string;
  station_id: number;
  station_name: string;
  station_address: string;
  health_score: number;
  last_maintenance: string | null;
  qr_code: string;
}

export interface QuickRepairRequest {
  device_id: number;
  fault_desc: string;
  fault_level?: 'info' | 'warning' | 'critical';
  contact_name?: string;
  contact_phone?: string;
  attachments?: string[];
}

export interface QuickRepairResult {
  success: boolean;
  workorder_id: string;
  device_name: string;
  station_name: string;
  fault_desc: string;
  status: string;
  create_time: string;
  message: string;
}

export interface QRCodeGenerateRequest {
  device_id: number;
  notes?: string;
}

export interface QRCodeGenerateResult {
  success: boolean;
  qr_code: string;
  qr_image_url: string;
  device_id: number;
  device_name: string;
  message?: string;
}

export interface DeviceQRCodeInfo {
  id: number;
  qr_code: string;
  device_id: number;
  device_name: string;
  device_sn: string;
  scan_count: number;
  is_active: boolean;
  created_at: string;
}

// ==================== 诊断相关 ====================
export interface DiagnosisResult {
  id: number;
  device_id: number;
  station_id: number;
  diagnosis_type: string;
  result: 'passed' | 'failed' | 'warning';
  score: number;
  details?: Record<string, any>;
  recommendations?: string[];
  created_at: string;
}

export interface Runbook {
  id: number;
  title: string;
  description?: string;
  category: string;
  steps: RunbookStep[];
  estimated_time?: number;
  difficulty?: 'easy' | 'medium' | 'hard';
  applicable_devices?: string[];
  author_id?: number;
  version?: string;
  created_at: string;
}

export interface RunbookStep {
  sequence: number;
  title: string;
  description?: string;
  action?: string;
  checkpoints?: string[];
  safety_warnings?: string[];
  estimated_time?: number;
  tools_required?: string[];
}

// ==================== WebSocket ====================
export interface WebSocketMessage<T = any> {
  type: string;
  data: T;
  timestamp: number;
  id?: string;
}

export interface RealtimeData {
  device_id: number;
  station_id: number;
  metrics: Record<string, number | string>;
  timestamp: number;
  health_score: number;
}

export interface AlarmNotification {
  alarm_id: number;
  title: string;
  level: AlarmLevel;
  station_name: string;
  device_name: string;
  timestamp: number;
}

// ==================== 工具类型 ====================
export type Nullable<T> = T | null;
export type Optional<T> = T | undefined;
export type Dictionary<T = any> = Record<string, T>;

// ==================== 事件总线类型 ====================
export interface EventPayload<T = any> {
  type: string;
  data: T;
  timestamp: number;
  source?: string;
}

// ==================== 协议实例管理 (Phase33) ====================
export interface ProtocolInstance {
  id: number;
  name: string;
  protocol_type: string;
  gateway_id?: number;
  device_type?: string;
  config?: Record<string, any>;
  parser_schema?: string;
  status: string;
  connection_status: string;
  last_connected?: string;
  description?: string;
  created_at: string;
  updated_at?: string;
}

export interface ParserConfig {
  id: number;
  name: string;
  device_type: string;
  protocol: string;
  parser_schema?: string;
  config?: Record<string, any>;
  status: string;
  description?: string;
  created_at: string;
  updated_at?: string;
}

export interface ConnectionDashboard {
  stats: {
    total: number;
    running: number;
    stopped: number;
    error: number;
    connected: number;
    disconnected: number;
    connecting: number;
    by_protocol: Record<string, number>;
  };
  recent_connections: Array<{
    id: number;
    name: string;
    protocol_type: string;
    connection_status: string;
    last_connected: string;
  }>;
  parser_count: number;
  protocol_count: number;
  timestamp: string;
}

// ==================== 运行效率类型 (Phase48) ====================
export interface UtilizationReport {
  sites: SiteUtilization[];
  warnings: UtilizationWarning[];
  overall_utilization_rate?: number;
}

export interface SiteUtilization {
  name: string;
  site_id?: number;
  utilization_rate: number;
  total_devices: number;
  active_devices: number;
  idling_devices: number;
  overloaded_devices: number;
}

export interface UtilizationWarning {
  device_name: string;
  station_name: string;
  utilization_rate: number;
  status: 'low' | 'overload';
  suggestion: string;
}

export interface EfficiencyReport {
  data: DeviceEfficiencyItem[];
  avg_charge_efficiency?: number;
  avg_discharge_efficiency?: number;
}

export interface DeviceEfficiencyItem {
  device_name: string;
  device_id?: number;
  charge_efficiency: number;
  discharge_efficiency: number;
  cycle_count?: number;
  energy_charged_kwh?: number;
  energy_discharged_kwh?: number;
}

export interface GenerationReport {
  data: DeviceGenerationItem[];
  avg_pr_ratio?: number;
  total_generation_kwh?: number;
}

export interface DeviceGenerationItem {
  device_name: string;
  device_id?: number;
  pv_pr_ratio: number;
  generation_efficiency: number;
  rated_capacity_kw?: number;
  actual_generation_kwh?: number;
}

export interface DeviceEfficiencyDetail {
  utilization: {
    current: number;
    trend: number;
    trend_data?: Array<{ date: string; value: number }>;
  };
  charge_efficiency: {
    current: number;
    trend: number;
    trend_data?: Array<{ date: string; value: number }>;
  };
  generation_efficiency: {
    current: number;
    trend: number;
    trend_data?: Array<{ date: string; value: number }>;
  };
  discharge_efficiency?: {
    current: number;
    trend: number;
    trend_data?: Array<{ date: string; value: number }>;
  };
}

// ==================== V2G 调度相关 (Phase48) ====================
export interface V2GDevice {
  id: number;
  name: string;
  sn: string;
  station_id: number;
  station_name?: string;
  type: string;
  status: string;
  health_score: number;
  current_mode: 'charging' | 'discharging' | 'standby';
  charge_power_kw: number;
  discharge_power_kw: number;
  charge_efficiency: number;
  discharge_efficiency: number;
  conversion_efficiency: number;
  rated_power_kw?: number;
}

export interface V2GOverview {
  total: number;
  charging_count: number;
  discharging_count: number;
  standby_count: number;
  today_charge_kwh: number;
  today_discharge_kwh: number;
}

export interface V2GDispatchRequest {
  dispatch_type: 'charge' | 'discharge' | 'standby';
  target_power_kw: number;
}

export interface V2GDispatchRecord {
  id: number;
  device_id: number;
  dispatch_type: string;
  target_power_kw: number;
  actual_power_kw?: number;
  status: 'pending' | 'success' | 'failed';
  created_at: string;
  message?: string;
}

export interface DeviceEfficiency {
  device_id: number;
  charge_efficiency: number;
  discharge_efficiency: number;
  conversion_efficiency: number;
  timestamp: string;
}

// ==================== 导出类型工具 ====================
export type {
  // 从其他模块重导出已有的类型
  ScanResult as ScanTypes_ScanResult,
  QuickRepairRequest as ScanTypes_QuickRepairRequest,
  QuickRepairResult as ScanTypes_QuickRepairResult,
  QRCodeGenerateRequest as ScanTypes_QRCodeGenerateRequest,
  QRCodeGenerateResult as ScanTypes_QRCodeGenerateResult,
  DeviceQRCodeInfo as ScanTypes_DeviceQRCodeInfo,
} from '../pages/Scan/types';