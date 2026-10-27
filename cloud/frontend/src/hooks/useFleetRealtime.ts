/**
 * 车队实时数据 Hook (Phase40: WebSocket 实时推送 + 断连降级轮询)
 *
 * 复用 useWebSocket 做连接 / 重连 / 心跳，叠加降级策略：
 * - WS 已连接 → realtime 模式，由推送驱动刷新
 * - WS 未连接或断连 → polling 模式，自动按间隔回退轮询
 * - enabled=false → idle，不连接不轮询
 *
 * 页面用法：收到 onData 触发已有 REST load*；mode 可用于 UI 提示。
 */
import { useEffect } from 'react';
import { useWebSocket } from './useWebSocket';

export type FleetRealtimeMode = 'idle' | 'polling' | 'realtime';

interface UseFleetRealtimeOptions {
  /** WebSocket 端点 (来自 WS_ENDPOINTS) */
  endpoint: string;
  /** 是否启用 (默认 true) */
  enabled?: boolean;
  /** 收到 WS 数据 / 更新 / 通知 时回调 (payload) */
  onData?: (payload: any) => void;
  /** 降级轮询函数 (通常为页面的 load*) */
  pollFn: () => void;
  /** 轮询间隔 ms (默认 15000) */
  pollIntervalMs?: number;
}

export const useFleetRealtime = ({
  endpoint,
  enabled = true,
  onData,
  pollFn,
  pollIntervalMs = 15000,
}: UseFleetRealtimeOptions) => {
  const { isConnected } = useWebSocket({
    endpoint,
    autoConnect: enabled,
    onMessage: (message) => {
      if (!enabled) return;
      if (message.type === 'data' || message.type === 'update' || message.type === 'notification') {
        onData?.(message.payload);
      }
    },
  });

  // 降级轮询：仅在启用且 WS 未连接时启动
  useEffect(() => {
    if (!enabled || isConnected) return;
    const timer = window.setInterval(pollFn, pollIntervalMs);
    return () => window.clearInterval(timer);
  }, [enabled, isConnected, pollFn, pollIntervalMs]);

  const mode: FleetRealtimeMode = !enabled ? 'idle' : isConnected ? 'realtime' : 'polling';

  return { mode, isConnected };
};

export default useFleetRealtime;
