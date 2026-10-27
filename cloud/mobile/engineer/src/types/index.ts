// 工程师APP类型定义

// 工单状态
export type WorkOrderStatus = 'pending' | 'accepted' | 'arrived' | 'processing' | 'completed';

// 紧急程度
export type UrgencyLevel = 'high' | 'medium' | 'low';

// 工单
export interface WorkOrder {
  id: string;
  orderNo: string;
  status: WorkOrderStatus;
  urgency: UrgencyLevel;
  deviceId: string;
  deviceName: string;
  stationId: string;
  stationName: string;
  stationAddress: string;
  faultDescription: string;
  createdAt: string;
  acceptedAt?: string;
  arrivedAt?: string;
  completedAt?: string;
  engineerId?: string;
  engineerName?: string;
  contactPhone?: string;
  lat?: number;
  lng?: number;
}

// 工单进度记录
export interface WorkOrderProgress {
  id: string;
  workOrderId: string;
  type: 'progress' | 'support' | 'parts' | 'complete';
  description: string;
  photos?: string[];
  createdAt: string;
}

// 处理流程步骤
export interface ProcessStep {
  status: WorkOrderStatus;
  label: string;
  completed: boolean;
  timestamp?: string;
}

// 知识库分类
export type KnowledgeCategory = 'fault_case' | 'manual';

// 知识库条目
export interface KnowledgeItem {
  id: string;
  category: KnowledgeCategory;
  title: string;
  content: string;
  tags?: string[];
  viewCount: number;
  createdAt: string;
  updatedAt: string;
}

// 工程师信息
export interface Engineer {
  id: string;
  name: string;
  employeeNo: string;
  level: string;
  phone: string;
  avatar?: string;
}

// 工作统计
export interface WorkStats {
  todayPending: number;
  todayProcessing: number;
  todayCompleted: number;
  monthTotal: number;
  avgRating: number;
  avgResponseTime: number;
}

// 消息通知
export interface Notification {
  id: string;
  title: string;
  content: string;
  type: 'work_order' | 'system' | 'alert';
  read: boolean;
  createdAt: string;
}

// 登录响应
export interface LoginResponse {
  token: string;
  engineer: Engineer;
}

// 发送验证码响应
export interface SendCodeResponse {
  success: boolean;
  message: string;
}

// API响应通用结构
export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
}

// ============ V2G 设备相关类型 ============

// V2G 设备
export interface V2GDevice {
  id: string;
  name: string;
  type: 'v2g_charger';
  status: 'online' | 'offline' | 'charging' | 'discharging' | 'standby';
  stationId: string;
  stationName: string;
  ratedPower: number; // 额定功率 kW
  batteryCapacity: number; // 电池容量 kWh
  currentPower: number; // 当前功率 kW
  efficiency: number; // 当前效率 %
  healthScore: number; // 电池健康度 0-100
  lastMaintenance: string;
}

// V2G 效率详情
export interface V2GEfficiency {
  deviceId: string;
  chargeEfficiency: number; // 充电效率 %
  dischargeEfficiency: number; // 放电效率 %
  conversionEfficiency: number; // 转换效率 %
  healthScore: number;
  temperature: number; // 电池温度 °C
  cycleCount: number; // 循环次数
  timestamp: string;
}

// V2G 效率趋势数据点
export interface V2GEfficiencyTrend {
  date: string;
  chargeEfficiency: number;
  dischargeEfficiency: number;
  conversionEfficiency: number;
}

// V2G 调度指令
export type DispatchType = 'charge' | 'discharge' | 'standby';
export type DispatchStatus = 'pending' | 'confirmed' | 'rejected' | 'executing' | 'completed' | 'failed';

export interface V2GDispatch {
  id: string;
  deviceId: string;
  deviceName: string;
  type: DispatchType;
  status: DispatchStatus;
  targetPower: number; // 目标功率 kW
  targetDuration: number; // 目标时长 分钟
  scheduledTime: string;
  rejectReason?: string;
  actualPower?: number;
  actualDuration?: number;
  createdAt: string;
  completedAt?: string;
}

// 效率检测记录
export interface EfficiencyRecord {
  id: string;
  deviceId: string;
  deviceName: string;
  inputEnergy: number; // 输入电量 kWh
  outputEnergy: number; // 输出电量 kWh
  efficiency: number; // 效率 %
  measurementType: 'charge' | 'discharge';
  createdAt: string;
}