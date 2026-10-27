/**
 * WebSocket 配置文件
 * 环境变量配置 WebSocket 基础 URL
 * 更新时间: 2026-05-25
 */

// WebSocket 基础 URL (从环境变量读取)
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000/ws/v1';

// 连接参数配置
export const WS_CONFIG = {
  // 心跳间隔(秒)
  heartbeatInterval: Number(import.meta.env.VITE_WS_HEARTBEAT_INTERVAL) || 30,
  
  // 重连间隔(秒)
  reconnectInterval: Number(import.meta.env.VITE_WS_RECONNECT_INTERVAL) || 3,
  
  // 最大重连次数
  maxReconnectAttempts: Number(import.meta.env.VITE_WS_MAX_RECONNECT_ATTEMPTS) || 5,
  
  // 连接超时(秒)
  connectionTimeout: Number(import.meta.env.VITE_WS_CONNECTION_TIMEOUT) || 10,
} as const;

// WebSocket 端点路由 (标准化前缀: /ws/v1/)
export const WS_ENDPOINTS = {
  // 实时数据推送(全局)
  realtime: `${WS_BASE_URL}/realtime`,
  
  // Dashboard实时数据
  dashboard: `${WS_BASE_URL}/dashboard`,
  
  // 设备状态实时推送
  devices: `${WS_BASE_URL}/devices`,
  
  // 告警实时推送
  alerts: `${WS_BASE_URL}/alerts`,
  
  // 工单实时推送
  workorders: `${WS_BASE_URL}/workorders`,
  
  // 数字孪生站点级推送
  digitalTwinStation: (stationId: number) => `${WS_BASE_URL}/digital-twin/station/${stationId}`,
  
  // 数字孪生设备级推送
  digitalTwinDevice: (deviceId: number) => `${WS_BASE_URL}/digital-twin/device/${deviceId}`,
  
  // 数字孪生全局推送
  digitalTwinGlobal: `${WS_BASE_URL}/digital-twin/global`,
  
  // 大屏独立展示模式实时推送
  largeScreen: `${WS_BASE_URL}/dashboard/large-screen`,

  // 车队充电排队队列实时推送 (按电站)
  fleetQueue: (stationId: number) => `${WS_BASE_URL}/fleet/queue/${stationId}`,

  // 车队 V2G 计划状态实时推送 (按企业)
  fleetV2G: (enterpriseId: number) => `${WS_BASE_URL}/fleet/v2g/${enterpriseId}`,
} as const;

// WebSocket 消息类型
export type WSMessageType =
  | 'connected'
  | 'disconnected'
  | 'data'
  | 'error'
  | 'heartbeat'
  | 'subscribe'
  | 'unsubscribe'
  | 'subscribed'
  | 'unsubscribed'
  | 'initial_data'
  | 'update'
  | 'notification'
  | 'pong';

// WebSocket 频道类型
export type WSChannelType =
  | 'realtime'
  | 'digital_twin'
  | 'dashboard'
  | 'alerts'
  | 'workorders'
  | 'devices'
  | 'station'
  | 'device'
  | 'fleet_queue'
  | 'fleet_v2g';

// WebSocket 消息格式 (标准化)
export interface WSMessage {
  type: WSMessageType;
  channel: WSChannelType;
  payload?: any;
  timestamp: string;
  id?: string;
  station_id?: number;
  device_id?: number;
  message?: string;
}

// WebSocket 连接状态
export type WSConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error' | 'failed';

// 导出配置对象
export const WebSocketConfig = {
  baseUrl: WS_BASE_URL,
  endpoints: WS_ENDPOINTS,
  config: WS_CONFIG,
} as const;

export default WebSocketConfig;