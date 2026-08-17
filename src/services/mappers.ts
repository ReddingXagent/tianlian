import {
  Alarm,
  AlarmLevel,
  AlarmStatus,
  WorkOrder,
  WorkOrderPriority,
  WorkOrderStatus,
  Station,
  PaginatedData,
} from '../types';

// =====================
// 真云端契约归一化 (闭环战役B2: snake_case → camelCase)
// =====================

// 告警级别: 后端含 fatal, 归一到 UI 三档
const ALARM_LEVEL_MAP: Record<string, AlarmLevel> = {
  info: 'info',
  warning: 'warning',
  critical: 'critical',
  fatal: 'critical',
};

// 告警状态: 后端 active/acknowledged/resolved/ignored → UI 三态
const ALARM_STATUS_MAP: Record<string, AlarmStatus> = {
  active: 'unhandled',
  acknowledged: 'processing',
  resolved: 'resolved',
  ignored: 'resolved',
};

// UI 状态 → 后端查询参数
const ALARM_STATUS_REVERSE: Record<string, string> = {
  unhandled: 'active',
  processing: 'acknowledged',
  resolved: 'resolved',
};

const ALARM_TYPE_LABEL: Record<string, string> = {
  high_temperature: '温度过高',
  device_fault: '设备故障',
  power_anomaly: '功率异常',
  communication_loss: '通讯中断',
  temperature_warning: '温度预警',
  health_warning: '健康度告警',
  offline: '设备离线',
};

// 工单级别: 后端 P0/P1/P2/warning/info → UI 优先级
const WO_LEVEL_TO_PRIORITY: Record<string, WorkOrderPriority> = {
  P0: 'urgent',
  P1: 'high',
  P2: 'normal',
  warning: 'low',
  info: 'low',
  critical: 'high',
  fatal: 'urgent',
};

const WO_PRIORITY_TO_LEVEL: Record<WorkOrderPriority, string> = {
  urgent: 'P0',
  high: 'P1',
  normal: 'P2',
  low: 'warning',
};

// 工单状态: 后端 pending/accepted/processing/completed/pending_verify/verified → UI 三态
const WO_STATUS_MAP: Record<string, WorkOrderStatus> = {
  pending: 'pending',
  accepted: 'in_progress',
  processing: 'in_progress',
  completed: 'completed',
  pending_verify: 'completed',
  verified: 'completed',
};

const WO_STATUS_REVERSE: Record<string, string> = {
  pending: 'pending',
  in_progress: 'processing',
  completed: 'completed',
};

type Raw = Record<string, unknown>;

// ── type-safe accessors for Raw ──
const num = (v: unknown, d = 0): number =>
  typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) || d : d;
const str = (v: unknown, d = ''): string =>
  v == null ? d : typeof v === 'string' ? v : String(v);
const numOrUndef = (v: unknown): number | undefined =>
  v == null ? undefined : typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) || undefined : undefined;
const strOrUndef = (v: unknown): string | undefined =>
  v == null ? undefined : typeof v === 'string' ? v : String(v);

export function mapAlarm(raw: Raw): Alarm {
  const alarmType = str(raw.alarm_type, 'other');
  return {
    id: num(raw.id),
    stationId: num(raw.station_id),
    stationName: str(raw.station_name),
    deviceId: numOrUndef(raw.device_id),
    deviceName: strOrUndef(raw.device_name),
    type: (ALARM_TYPE_LABEL[alarmType] ? alarmType : 'other') as Alarm['type'],
    level: ALARM_LEVEL_MAP[str(raw.level)] ?? 'info',
    title: ALARM_TYPE_LABEL[alarmType] ?? alarmType,
    description: str(raw.content),
    status: ALARM_STATUS_MAP[str(raw.status)] ?? 'unhandled',
    handledAt: strOrUndef(raw.handled_at),
    createdAt: str(raw.created_at),
    updatedAt: str(raw.handled_at ?? raw.created_at),
  };
}

export function mapWorkOrder(raw: Raw): WorkOrder {
  const level = str(raw.level, 'warning');
  const status = str(raw.status, 'pending');
  return {
    id: str(raw.id),
    stationId: num(raw.station_id),
    stationName: str(raw.station_name, `站点${str(raw.station_id)}`),
    title: str(raw.fault_desc ?? raw.title, '工单'),
    description: str(raw.fault_desc ?? raw.description),
    type: str(raw.type, 'other') as WorkOrder['type'],
    priority: WO_LEVEL_TO_PRIORITY[level] ?? 'normal',
    status: WO_STATUS_MAP[status] ?? 'pending',
    assigneeId: numOrUndef(raw.assignee_id),
    assigneeName: strOrUndef(raw.assignee_name),
    creatorId: num(raw.creator_id),
    creatorName: str(raw.creator_name),
    alarmId: numOrUndef(raw.alarm_id),
    solution: strOrUndef(raw.solution),
    completedAt: strOrUndef(raw.finish_time),
    createdAt: str(raw.create_time ?? raw.created_at),
    updatedAt: str(raw.finish_time ?? raw.create_time),
  };
}

export function mapStation(raw: Raw): Station {
  const rawStatus = str(raw.status);
  const status = rawStatus === 'normal' || rawStatus === 'online' ? 'online'
    : rawStatus === 'maintenance' ? 'maintenance' : 'offline';
  return {
    id: num(raw.id),
    name: str(raw.name),
    code: str(raw.code),
    address: str(raw.address),
    status,
    latitude: num(raw.lat ?? raw.latitude),
    longitude: num(raw.lon ?? raw.longitude),
    deviceCount: num(raw.total_devices ?? raw.device_count),
    onlineDeviceCount: num(raw.online_devices ?? raw.total_devices),
    alarmCount: num(raw.alarm_count),
    healthScore: numOrUndef(raw.health_score),
    totalPower: numOrUndef(raw.total_power),
    createdAt: str(raw.created_at),
    updatedAt: str(raw.updated_at ?? raw.created_at),
  };
}

export function mapPagination<T>(raw: Raw, mapper: (r: Raw) => T): PaginatedData<T> {
  return {
    items: Array.isArray(raw?.items) ? (raw.items as Raw[]).map(mapper) : [],
    total: num(raw?.total),
    page: num(raw?.page, 1),
    pageSize: num(raw?.page_size ?? raw?.pageSize, 20),
  };
}

// 导出映射常量供 API 模块使用
export {
  ALARM_STATUS_REVERSE,
  WO_PRIORITY_TO_LEVEL,
  WO_STATUS_REVERSE,
  ALARM_LEVEL_MAP,
  ALARM_STATUS_MAP,
  ALARM_TYPE_LABEL,
  WO_LEVEL_TO_PRIORITY,
  WO_STATUS_MAP,
};

// 导出类型和工具函数供 API 模块使用
export type { Raw };
export { num, str, numOrUndef, strOrUndef };
