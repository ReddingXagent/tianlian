/**
 * WebSocket Hook (Phase31: 实时推送增强版)
 * 
 * 功能:
 * - 统一WebSocket连接管理
 * - Dashboard告警/设备状态实时更新
 * - 多频道支持（dashboard, alerts, devices, workorders）
 * - 自动重连 + 心跳保活
 * - 状态订阅/取消订阅
 * 
 * 更新时间: 2026-06-01 (Phase31)
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { getToken } from '../utils/authStorage';
import { WS_CONFIG as WSConfig, WSMessage, WSConnectionState, WSChannelType, WS_ENDPOINTS } from '../config/websocket';

interface UseWebSocketOptions {
  // WebSocket端点(使用配置中的端点)
  endpoint?: string;
  
  // 是否自动连接
  autoConnect?: boolean;
  
  // 自定义重连间隔(秒)
  reconnectInterval?: number;
  
  // 自定义最大重连次数
  maxReconnectAttempts?: number;
  
  // 自定义心跳间隔(秒)
  heartbeatInterval?: number;
  
  // 要自动订阅的频道列表
  autoSubscribeChannels?: WSChannelType[];
  
  // 消息回调
  onMessage?: (message: WSMessage) => void;
  
  // 连接成功回调
  onConnect?: () => void;
  
  // 错误回调
  onError?: (error: Event) => void;
  
  // 断开连接回调
  onClose?: (event: CloseEvent) => void;

  // 重试耗尽回调
  onMaxReconnectAttempts?: () => void;
}

// Dashboard 实时更新数据类型
export interface DashboardRealtimeUpdate {
  type: 'alarm' | 'device_status' | 'workorder' | 'health';
  payload: {
    alarm?: {
      id: number;
      level: string;
      title: string;
      status: string;
      device_name?: string;
      created_at: string;
    };
    device_status?: {
      device_id: number;
      status: string;
      health_score?: number;
    };
    workorder?: {
      id: number;
      status: string;
      title: string;
    };
    health?: {
      device_id: number;
      score: number;
      trend: string;
    };
  };
  timestamp: string;
}

export const useWebSocket = ({
  endpoint,
  autoConnect = true,
  reconnectInterval = WSConfig.reconnectInterval,
  maxReconnectAttempts = WSConfig.maxReconnectAttempts,
  heartbeatInterval = WSConfig.heartbeatInterval,
  autoSubscribeChannels,
  onMessage,
  onConnect,
  onError,
  onClose,
  onMaxReconnectAttempts,
}: UseWebSocketOptions) => {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const heartbeatTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const subscribedChannelsRef = useRef<Set<WSChannelType>>(new Set());
  // 主动 disconnect 标记：close 事件因主动断开触发时跳过重连/终态逻辑
  const intentionalCloseRef = useRef(false);

  // 渲染期同步最新配置/回调到 ref，保证 connect/disconnect 身份稳定（卡deddf61f）
  const endpointRef = useRef(endpoint);
  endpointRef.current = endpoint;
  const reconnectIntervalRef = useRef(reconnectInterval);
  reconnectIntervalRef.current = reconnectInterval;
  const maxReconnectAttemptsRef = useRef(maxReconnectAttempts);
  maxReconnectAttemptsRef.current = maxReconnectAttempts;
  const heartbeatIntervalRef = useRef(heartbeatInterval);
  heartbeatIntervalRef.current = heartbeatInterval;
  const autoSubscribeChannelsRef = useRef(autoSubscribeChannels);
  autoSubscribeChannelsRef.current = autoSubscribeChannels;
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onConnectRef = useRef(onConnect);
  onConnectRef.current = onConnect;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const onMaxReconnectAttemptsRef = useRef(onMaxReconnectAttempts);
  onMaxReconnectAttemptsRef.current = onMaxReconnectAttempts;
  
  const [connectionState, setConnectionState] = useState<WSConnectionState>('disconnected');
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  
  // Dashboard 实时数据状态
  const [dashboardAlarms, setDashboardAlarms] = useState<DashboardRealtimeUpdate['payload']['alarm'][]>([]);
  const [dashboardDeviceStatus, setDashboardDeviceStatus] = useState<DashboardRealtimeUpdate['payload']['device_status'][]>([]);
  const [lastDashboardUpdate, setLastDashboardUpdate] = useState<DashboardRealtimeUpdate | null>(null);
  
  // 清理定时器
  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);
  
  // 启动心跳
  const startHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
    }

    heartbeatTimerRef.current = window.setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, heartbeatIntervalRef.current * 1000);
  }, []);
  
  // 处理 Dashboard 实时更新
  const handleDashboardUpdate = useCallback((message: WSMessage) => {
    if (!message.payload) return;
    
    const update = message.payload as DashboardRealtimeUpdate;
    setLastDashboardUpdate(update as DashboardRealtimeUpdate);
    
    switch (update.type) {
      case 'alarm':
        if (update.payload?.alarm) {
          setDashboardAlarms(prev => {
            const newAlarms = [update.payload!.alarm!, ...prev].slice(0, 50);
            return newAlarms;
          });
        }
        break;
        
      case 'device_status':
        if (update.payload?.device_status) {
          setDashboardDeviceStatus(prev => {
            const newStatus = update.payload!.device_status!;
            const existingIdx = prev.findIndex(d => d.device_id === newStatus.device_id);
            if (existingIdx >= 0) {
              const updated = [...prev];
              updated[existingIdx] = newStatus;
              return updated;
            }
            return [...prev, newStatus];
          });
        }
        break;
        
      case 'workorder':
      case 'health':
        // 触发热更新 - 父组件可以监听 lastDashboardUpdate
        break;
    }
  }, []);
  
  // 连接WebSocket
  const connect = useCallback(() => {
    const readyState = wsRef.current?.readyState;
    if (readyState === WebSocket.OPEN || readyState === WebSocket.CONNECTING) {
      return;
    }
    intentionalCloseRef.current = false;

    try {
      const wsEndpoint = endpointRef.current || WS_ENDPOINTS.dashboard;
      setConnectionState('connecting');

      // 注入 JWT token (query param) — 配合后端 WS 鉴权 (app/ws/auth.py)
      const token = getToken();
      const wsUrl = token
        ? `${wsEndpoint}?token=${encodeURIComponent(token)}`
        : wsEndpoint;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => {
        setConnectionState('connected');
        reconnectAttemptsRef.current = 0;
        startHeartbeat();
        onConnectRef.current?.();

        // 自动订阅频道
        const channels = autoSubscribeChannelsRef.current;
        if (channels && channels.length > 0) {
          channels.forEach(channel => {
            ws.send(JSON.stringify({
              type: 'subscribe',
              channel,
            }));
            subscribedChannelsRef.current.add(channel);
          });
        }
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WSMessage;
          
          // 验证消息格式
          if (!data.type || !data.channel || !data.timestamp) {
            console.warn('[WebSocket] 收到非标准格式消息:', data);
          }
          
          setLastMessage(data);
          
          // 处理心跳响应
          if (data.type === 'heartbeat' || data.type === 'pong') {
            console.debug('[WebSocket] 收到心跳响应');
            return;
          }
          
          // 处理订阅确认
          if (data.type === 'subscribed') {
            return;
          }
          
          // 处理 Dashboard 实时数据更新
          if (data.channel === 'dashboard' || data.channel === 'alerts' || data.channel === 'realtime') {
            handleDashboardUpdate(data);
          }
          
          // 调用外部消息回调
          onMessageRef.current?.(data);
          
        } catch {
          // 静默处理：解析失败时降级为文本消息
          setLastMessage({
            type: 'data',
            channel: 'realtime' as WSChannelType,
            payload: event.data,
            timestamp: new Date().toISOString(),
          });
        }
      };
      
      ws.onerror = (error) => {
        setConnectionState('error');
        onErrorRef.current?.(error);
      };

      ws.onclose = (event) => {
        subscribedChannelsRef.current.clear();
        clearTimers();

        // 主动断开：状态已由 disconnect 置位，跳过重连逻辑
        if (intentionalCloseRef.current) {
          onCloseRef.current?.(event);
          return;
        }

        setConnectionState('disconnected');
        onCloseRef.current?.(event);

        // 自动重连逻辑
        if (reconnectAttemptsRef.current < maxReconnectAttemptsRef.current) {
          reconnectAttemptsRef.current++;

          reconnectTimerRef.current = window.setTimeout(() => {
            connect();
          }, reconnectIntervalRef.current * 1000);
        } else {
          // 达到最大重连次数：进入终态 failed，通知外部
          setConnectionState('failed');
          onMaxReconnectAttemptsRef.current?.();
        }
      };

    } catch {
      setConnectionState('error');
    }
  }, [startHeartbeat, clearTimers, handleDashboardUpdate]);
  
  // 断开连接
  const disconnect = useCallback(() => {
    clearTimers();
    intentionalCloseRef.current = true; // 阻止重连与终态回调
    reconnectAttemptsRef.current = maxReconnectAttemptsRef.current;
    subscribedChannelsRef.current.clear();
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setConnectionState('disconnected');
  }, [clearTimers]);
  
  // 发送消息
  const send = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const message = typeof data === 'string' ? data : JSON.stringify(data);
      wsRef.current.send(message);
    } else {
      console.warn('[WebSocket] 连接未打开,无法发送消息');
    }
  }, []);
  
  // 发送订阅消息
  const subscribe = useCallback((channel: WSChannelType, targetId?: number) => {
    if (subscribedChannelsRef.current.has(channel)) {
      return;
    }
    
    send({
      type: 'subscribe',
      channel,
      target_id: targetId,
    });
    subscribedChannelsRef.current.add(channel);
  }, [send]);
  
  // 发送取消订阅消息
  const unsubscribe = useCallback((channel: WSChannelType, targetId?: number) => {
    send({
      type: 'unsubscribe',
      channel,
      target_id: targetId,
    });
    subscribedChannelsRef.current.delete(channel);
  }, [send]);
  
  // 重置 Dashboard 数据
  const resetDashboardData = useCallback(() => {
    setDashboardAlarms([]);
    setDashboardDeviceStatus([]);
    setLastDashboardUpdate(null);
  }, []);
  
  // 组件挂载时自动连接
  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    
    // 组件卸载时断开连接
    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);
  
  return {
    // 连接状态
    connectionState,
    isConnected: connectionState === 'connected',
    
    // 最后收到的消息
    lastMessage,
    
    // Dashboard 实时数据
    dashboardAlarms,
    dashboardDeviceStatus,
    lastDashboardUpdate,
    
    // 操作方法
    connect,
    disconnect,
    send,
    subscribe,
    unsubscribe,
    resetDashboardData,
    
    // 重连次数
    reconnectAttempts: reconnectAttemptsRef.current,
    
    // 已订阅频道
    subscribedChannels: Array.from(subscribedChannelsRef.current),
  };
};

export default useWebSocket;