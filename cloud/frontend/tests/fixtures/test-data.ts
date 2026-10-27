/**
 * 天链V3 - 测试数据 Fixtures
 *
 * 提供:
 * - Mock Users
 * - Mock Stations
 * - Mock Devices
 * - Mock WorkOrders
 * - Mock Alarms
 */
import { vi } from 'vitest';

// ============ 用户数据 ============
export const mockUsers = [
  {
    id: 1,
    username: 'admin',
    password: 'admin123',
    real_name: '管理员',
    role: 'admin',
    email: 'admin@tianlian.com',
    phone: '13800138000',
    status: 'active',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 2,
    username: 'operator',
    password: 'operator123',
    real_name: '运维员',
    role: 'operator',
    email: 'operator@tianlian.com',
    phone: '13800138001',
    status: 'active',
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
  {
    id: 3,
    username: 'viewer',
    password: 'viewer123',
    real_name: '观察员',
    role: 'viewer',
    email: 'viewer@tianlian.com',
    phone: '13800138002',
    status: 'active',
    created_at: '2024-01-03T00:00:00Z',
    updated_at: '2024-01-03T00:00:00Z',
  },
];

export const mockCurrentUser = mockUsers[0];

// ============ 站点数据 ============
export const mockStations = [
  {
    id: 1,
    name: '站点A',
    code: 'STA001',
    address: '北京市朝阳区XX路XX号',
    latitude: 39.9042,
    longitude: 116.4074,
    status: 'active',
    device_count: 10,
    alarm_count: 2,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: '站点B',
    code: 'STA002',
    address: '上海市浦东新区XX路XX号',
    latitude: 31.2304,
    longitude: 121.4737,
    status: 'active',
    device_count: 15,
    alarm_count: 0,
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
  {
    id: 3,
    name: '站点C',
    code: 'STA003',
    address: '广州市天河区XX路XX号',
    latitude: 23.1291,
    longitude: 113.2644,
    status: 'inactive',
    device_count: 5,
    alarm_count: 1,
    created_at: '2024-01-03T00:00:00Z',
    updated_at: '2024-01-03T00:00:00Z',
  },
];

// ============ 设备数据 ============
export const mockDevices = [
  {
    id: 1,
    name: '设备A-001',
    code: 'DEV001',
    station_id: 1,
    station_name: '站点A',
    type: 'router',
    model: 'Huawei AR1200',
    ip_address: '192.168.1.1',
    mac_address: '00:11:22:33:44:55',
    status: 'online',
    last_heartbeat: '2024-01-15T10:00:00Z',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: '设备A-002',
    code: 'DEV002',
    station_id: 1,
    station_name: '站点A',
    type: 'switch',
    model: 'Cisco 2960',
    ip_address: '192.168.1.2',
    mac_address: '00:11:22:33:44:56',
    status: 'online',
    last_heartbeat: '2024-01-15T10:00:00Z',
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
  {
    id: 3,
    name: '设备B-001',
    code: 'DEV003',
    station_id: 2,
    station_name: '站点B',
    type: 'server',
    model: 'Dell R740',
    ip_address: '192.168.2.1',
    mac_address: '00:11:22:33:44:57',
    status: 'offline',
    last_heartbeat: '2024-01-14T10:00:00Z',
    created_at: '2024-01-03T00:00:00Z',
    updated_at: '2024-01-03T00:00:00Z',
  },
];

// ============ 工单数据 ============
export const mockWorkOrders = [
  {
    id: 1,
    title: '设备故障维修',
    code: 'WO202401001',
    station_id: 1,
    station_name: '站点A',
    device_id: 1,
    device_name: '设备A-001',
    type: 'repair',
    priority: 'high',
    status: 'pending',
    description: '路由器无法连接网络',
    creator_id: 1,
    creator_name: '管理员',
    assignee_id: 2,
    assignee_name: '运维员',
    created_at: '2024-01-15T08:00:00Z',
    updated_at: '2024-01-15T08:00:00Z',
  },
  {
    id: 2,
    title: '设备巡检',
    code: 'WO202401002',
    station_id: 2,
    station_name: '站点B',
    type: 'inspection',
    priority: 'medium',
    status: 'in_progress',
    description: '月度例行巡检',
    creator_id: 1,
    creator_name: '管理员',
    assignee_id: 2,
    assignee_name: '运维员',
    created_at: '2024-01-15T09:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
  },
  {
    id: 3,
    title: '设备安装',
    code: 'WO202401003',
    station_id: 3,
    station_name: '站点C',
    type: 'install',
    priority: 'low',
    status: 'completed',
    description: '新设备安装',
    creator_id: 1,
    creator_name: '管理员',
    assignee_id: 2,
    assignee_name: '运维员',
    created_at: '2024-01-14T08:00:00Z',
    updated_at: '2024-01-14T18:00:00Z',
  },
];

// ============ 告警数据 ============
export const mockAlarms = [
  {
    id: 1,
    title: '设备离线告警',
    station_id: 1,
    station_name: '站点A',
    device_id: 1,
    device_name: '设备A-001',
    level: 'critical',
    status: 'active',
    message: '设备已离线超过30分钟',
    created_at: '2024-01-15T10:30:00Z',
    updated_at: '2024-01-15T10:30:00Z',
  },
  {
    id: 2,
    title: 'CPU使用率过高',
    station_id: 2,
    station_name: '站点B',
    device_id: 3,
    device_name: '设备B-001',
    level: 'warning',
    status: 'active',
    message: 'CPU使用率达到85%',
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
  },
  {
    id: 3,
    title: '内存不足',
    station_id: 1,
    station_name: '站点A',
    device_id: 2,
    device_name: '设备A-002',
    level: 'info',
    status: 'resolved',
    message: '内存使用率达到70%',
    created_at: '2024-01-14T15:00:00Z',
    updated_at: '2024-01-14T16:00:00Z',
  },
];

// ============ API 响应 Mock ============
export const mockAPIResponses = {
  // 认证
  loginSuccess: {
    token: 'mock-token-12345',
    user: mockCurrentUser,
  },
  loginError: {
    message: '用户名或密码错误',
  },

  // 列表响应模板
  stationsList: {
    data: mockStations,
    total: mockStations.length,
    page: 1,
    pageSize: 10,
  },
  devicesList: {
    data: mockDevices,
    total: mockDevices.length,
    page: 1,
    pageSize: 10,
  },
  workOrdersList: {
    data: mockWorkOrders,
    total: mockWorkOrders.length,
    page: 1,
    pageSize: 10,
  },
  alarmsList: {
    data: mockAlarms,
    total: mockAlarms.length,
    page: 1,
    pageSize: 10,
  },
  usersList: {
    data: mockUsers,
    total: mockUsers.length,
    page: 1,
    pageSize: 10,
  },

  // Dashboard 统计
  dashboardStats: {
    stationCount: 3,
    deviceCount: 15,
    onlineDeviceCount: 12,
    alarmCount: 2,
    pendingWorkOrderCount: 1,
  },
};

// ============ Fixture Factory ============
/**
 * 创建 Mock 数据工厂函数
 */
export function createMockData<T>(template: T, overrides?: Partial<T>): T {
  return { ...template, ...overrides } as T;
}

/**
 * 创建批量 Mock 数据
 */
export function createMockList<T>(template: T, count: number, idStart = 1): T[] {
  return Array.from({ length: count }, (_, i) => ({
    ...template,
    id: idStart + i,
  } as T));
}