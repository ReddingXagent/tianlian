/**
 * 数据大屏 WebSocket Hook
 * 
 * Phase48: 大屏独立展示模式实时推送
 * 
 * 功能：
 * - 连接到 /ws/v1/dashboard/large-screen
 * - 自动重连 + 心跳保活
 * - 管理大屏实时数据状态
 * 
 * 更新时间: 2026-06-24 (Phase48)
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { WS_CONFIG, WS_ENDPOINTS } from '../../config/websocket';

// ─── 大屏实时数据类型 ───────────────────────────

export interface LargeScreenWSDevice {
  id: number;
  name: string;
  status: string;
  health_score?: number;
  station_name?: string;
}

export interface LargeScreenWSAlert {
  id: number;
  level: string;
  title: string;
  device_name?: string;
  station_name?: string;
  created_at?: string;
}

export interface LargeScreenWSStats {
  devices?: {
    total: number;
    online: number;
    offline: number;
    online_rate: number;
  };
  stations?: {
    total: number;
    normal: number;
    rate: number;
  };
  alarms?: {
    active: number;
    critical: number;
  };
  workorders?: {
    pending: number;
    processing: number;
    today_completed: number;
  };
  health?: {
    average: number;
    trend: string;
  };
  update_time?: string;
}

// ─── Hook ────────────────────────────────────────

export function useLargeScreenWS() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectAttemptsRef = useRef(0);

  const [connected, setConnected] = useState(false);
  const [stats, setStats] = useState<LargeScreenWSStats | null>(null);
  const [devices, setDevices] = useState<LargeScreenWSDevice[]>([]);
  const [alerts, setAlerts] = useState<LargeScreenWSAlert[]>([]);
  const [lastUpdateTime, setLastUpdateTime] = useState<string | null>(null);

  // ── 清理定时器 ──
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

  // ── 启动心跳 ──
  const startHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
    }
    heartbeatTimerRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, WS_CONFIG.heartbeatInterval * 1000);
  }, []);

  // ── 连接 ──
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const url = WS_ENDPOINTS.largeScreen;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        reconnectAttemptsRef.current = 0;
        startHeartbeat();
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.type === 'heartbeat' || msg.type === 'pong') {
            return;
          }

          if (msg.type === 'connected') {
            return;
          }

          const payload = msg.payload;
          if (!payload) return;

          // 更新统计数据
          if (payload.devices || payload.stations || payload.alarms || payload.workorders || payload.health) {
            setStats(payload as LargeScreenWSStats);
            setLastUpdateTime(new Date().toISOString());
          }

          // 更新设备状态
          if (payload.devices_summary) {
            setDevices(payload.devices_summary as LargeScreenWSDevice[]);
          }

          // 更新告警
          if (payload.alerts) {
            setAlerts(prev => {
              const existingIds = new Set(prev.map(a => a.id));
              const newAlerts = (payload.alerts as LargeScreenWSAlert[]).filter(
                a => !existingIds.has(a.id)
              );
              if (newAlerts.length === 0) return prev;
              return [...prev, ...newAlerts].slice(-50);
            });
          }
        } catch {
          // 静默处理：消息解析失败跳过该帧
        }
      };

      ws.onerror = () => {
        setConnected(false);
      };

      ws.onclose = () => {
        setConnected(false);
        clearTimers();

        if (reconnectAttemptsRef.current < WS_CONFIG.maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          reconnectTimerRef.current = setTimeout(connect, WS_CONFIG.reconnectInterval * 1000);
        }
      };
    } catch {
      setConnected(false);
    }
  }, [startHeartbeat, clearTimers]);

  // ── 断开 ──
  const disconnect = useCallback(() => {
    clearTimers();
    reconnectAttemptsRef.current = WS_CONFIG.maxReconnectAttempts;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, [clearTimers]);

  // ── 生命周期 ──
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return {
    connected,
    stats,
    devices,
    alerts,
    lastUpdateTime,
    disconnect,
  };
}

export default useLargeScreenWS;
