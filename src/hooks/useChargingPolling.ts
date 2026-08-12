import { useEffect, useRef, useCallback, useState } from 'react';
import { chargingApi } from '../services/api';
import { ChargingStatus } from '../types';
import { useAppLifecycle } from './useAppLifecycle';

interface UseChargingPollingOptions {
  orderId: number;
  interval?: number; // ms, default 3000
  enabled?: boolean;
  /** 后台/离线时暂停轮询, 回前台/恢复联网立即补拉 (默认 true) */
  pauseWhenInactive?: boolean;
  onStatusChange?: (status: ChargingStatus) => void;
  onComplete?: (status: ChargingStatus) => void;
  onError?: (error: Error) => void;
}

interface UseChargingPollingReturn {
  status: ChargingStatus | null;
  loading: boolean;
  error: string | null;
  /** enabled 但因后台/离线被暂停 */
  paused: boolean;
  refresh: () => Promise<void>;
}

/**
 * Hook for polling charging status in real time.
 *
 * Automatically polls the charging API every `interval` ms.
 * When charging completes (status !== 'charging'), polling stops
 * and `onComplete` is called.
 */
export function useChargingPolling({
  orderId,
  interval = 3000,
  enabled = true,
  pauseWhenInactive = true,
  onStatusChange,
  onComplete,
  onError,
}: UseChargingPollingOptions): UseChargingPollingReturn {
  const [status, setStatus] = useState<ChargingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { isForeground, isConnected } = useAppLifecycle();
  // NetInfo 首帧未到时(isConnected=null)不阻塞; 仅确认离线才暂停
  const active =
    enabled && (!pauseWhenInactive || (isForeground && isConnected !== false));
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onCompleteRef = useRef(onComplete);
  const onStatusChangeRef = useRef(onStatusChange);
  const onErrorRef = useRef(onError);

  // Keep callback refs current
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);
  useEffect(() => {
    onStatusChangeRef.current = onStatusChange;
  }, [onStatusChange]);
  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await chargingApi.getStatus(orderId);
      const data = response.data;
      setStatus(data);
      setLoading(false);
      setError(null);

      onStatusChangeRef.current?.(data);

      if (data.status !== 'charging') {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        onCompleteRef.current?.(data);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取充电状态失败';
      setError(message);
      setLoading(false);
      if (err instanceof Error) {
        onErrorRef.current?.(err);
      }
    }
  }, [orderId]);

  const refresh = useCallback(async () => {
    setLoading(true);
    await fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (!active) return;

    // active 由 false→true (回前台/恢复联网) 时立即补拉一次再续轮询
    // fire-and-forget via microtask to avoid set-state-in-effect warning
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) fetchStatus();
    });

    intervalRef.current = setInterval(fetchStatus, interval);

    return () => {
      cancelled = true;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [orderId, interval, active, fetchStatus]);

  return { status, loading, error, paused: enabled && !active, refresh };
}

/**
 * Hook to check for an active charging session on mount.
 * Used to resume charging monitoring if app was closed during charging.
 */
export function useActiveCharging() {
  const [activeOrderId, setActiveOrderId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const checkActive = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await chargingApi.getActiveOrder();
      if (response.data) {
        setActiveOrderId(response.data.orderId);
      } else {
        setActiveOrderId(null);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '检查进行中充电失败';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // fire-and-forget via microtask to avoid set-state-in-effect warning
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) checkActive();
    });
    return () => { cancelled = true; };
  }, [checkActive]);

  return { activeOrderId, loading, error, checkActive };
}